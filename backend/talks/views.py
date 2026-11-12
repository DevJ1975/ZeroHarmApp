import datetime as dt
import hashlib
import json
import logging
import time

from django.conf import settings
from django.core.cache import caches
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from zeroharm.net import client_ip, network_key

from . import owner_alerts
from .integrations import sync_signup_to_ghl
from .models import AppSignup, SignupPhone, SignupRemoval, ToolboxTalk, split_name

log = logging.getLogger(__name__)


@require_GET
def health(request):
    return JsonResponse({"ok": True})


@require_GET
def talk_list(request):
    """Talks the app shows, newest first: released ones, plus (with TALKS_UNLOCK_EARLY) every reviewed talk with text."""
    talks = [t.as_api() for t in ToolboxTalk.objects.available()]
    return JsonResponse({"talks": talks})


@require_GET
def talk_detail(request, issue):
    talk = ToolboxTalk.objects.available().filter(issue=issue).first()
    if not talk:
        return JsonResponse({"error": "This talk isn’t available yet."}, status=404)
    return JsonResponse(talk.as_api())


def _client_ip(request):
    """The caller's address, or "" when it isn't known. zeroharm/net.py is the one place that works it out (on Railway
    it is in X-Real-IP; the last X-Forwarded-For entry is the edge's own address). Nothing in the apps calls this any
    more; the name stays only because a test in talks/tests.py imports it from here."""
    return client_ip(request)


def _network(request):
    """The network a request came from, as a salted hash. An IPv6 home or mobile connection owns a whole /64 and could
    otherwise switch addresses to dodge a limit, so net.network_key counts the /64; hashing means no readable address
    sits in the cache."""
    return hashlib.sha256(f"{settings.SECRET_KEY}:rate:{network_key(request)}".encode()).hexdigest()


def _rate_limited(name, request, limit=5, count=True, seconds=3600):
    """At most `limit` tries from one network in an hour. The hour starts with the first try and ends an hour later,
    whatever comes in between. (It used to start again with every try, so a plant Wi-Fi with a steady trickle was only
    let back in after a full hour of nobody trying.) With count=False it only says whether the limit has been
    reached, and uses up no try. `seconds` is for the one limit that is not hourly.

    The counts live in the "limits" cache (settings.CACHES), which holds nothing but counters. They used to share the
    300-entry default cache with weather and other content, which pushed them out: a used-up limit was fresh again."""
    counters = caches["limits"]
    key = f"{name}-rate:{_network(request)}"
    if not count:
        return counters.get(key, 0) >= limit
    if counters.add(key, 1, seconds):
        return False
    try:
        return counters.incr(key) > limit
    except ValueError:  # the hour ran out between the two calls
        counters.set(key, 1, seconds)
        return False


def _give_back(name, request):
    """Takes one try off a count again, for a try that turned out not to be the caller's doing."""
    try:
        caches["limits"].decr(f"{name}-rate:{_network(request)}")
    except ValueError:  # the hour ran out meanwhile: nothing left to give back
        pass


EMAIL_MAX = 254          # what the email columns hold; Django's own check lets longer addresses through
PG_INT_MAX = 2147483647  # the most a PostgreSQL integer column holds


def _json_body(request):
    """The request body as a JSON object, or None when it is anything else: not JSON, not UTF-8, or JSON that is a
    list, a number, a string or null. Every view here expects an object and used to crash (HTTP 500) on the rest."""
    try:
        data = json.loads(request.body or b"{}")
    except (ValueError, RecursionError):  # bad JSON and bad UTF-8 are both ValueErrors; very deep nesting is the other
        return None
    return data if isinstance(data, dict) else None


def _text(value, limit=None):
    """What someone typed, as text the database will take. Nothing for a missing or null value, and nothing for a
    list or an object sent where text belongs (it used to be stored as "['a', 'b']", or crashed). No NUL characters:
    PostgreSQL refuses them, which ended in a 500 that SQLite never showed. No half of a surrogate pair either
    (valid JSON can carry one, as "\\ud800"): it cannot be written as UTF-8, so saving or hashing it was a 500 too."""
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return ""
    text = str(value or "").replace("\x00", "").encode("utf-8", "ignore").decode("utf-8")
    return text[:limit] if limit else text


def _email(value):
    """A checked, lower-case email address that fits its column. Raises ValidationError otherwise."""
    email = _text(value).strip().lower()
    validate_email(email)
    if len(email) > EMAIL_MAX:
        raise ValidationError("That email address is too long.")
    return email


def _install_hash(value):
    """The salted hash of the phone's random install id, or "" when none (or a malformed one) was sent."""
    from monday.api import _hash  # one salt for install ids across the whole backend

    if not (isinstance(value, str) and 8 <= len(value) <= 80):
        return ""
    try:
        return _hash(value)
    except UnicodeEncodeError:  # half a surrogate pair, which no real id holds and which cannot be hashed
        return ""


# A whole crew often signs in together on one plant Wi-Fi, which is one network address, so new emails get a roomy
# limit. Repeat sign-ups of an email already here don't count toward it; they only get the wider limit on all tries.
NEW_SIGNUPS_PER_HOUR = 30
SIGNUP_TRIES_PER_HOUR = 120
REMOVALS_PER_HOUR = 5


@csrf_exempt  # called by the mobile app, which has no browser session or CSRF cookie
@require_POST
def signup(request):
    """Name and email from the welcome screen or Settings. One row per email. The lead goes to GoHighLevel and, for a
    new email, an alert to the owner.

    There is no password and no email check, so who may change a sign-up has to be a rule, and it is this one: the
    FIRST phone linked to a sign-up owns it. Only that phone can change the name, company, consent or offers choice.
    Any other phone that signs up with the email (a second phone, a reinstall, or a stranger who knows the address:
    the server cannot tell them apart) is linked so the app works on it, and changes nothing at all. It is told so:
    the answer is {"ok": true, "changed": false}, where the owner phone and a new email get {"ok": true}. So to a
    caller that sends a phone id the answer does show that an email is already signed up from another phone. That
    is the price of not telling a person their change was saved when it was not; a new email still costs the asker
    a sign-up, an alert to the owner and one of 30 new sign-ups an hour. A request with no phone id (an old app
    version) changes nothing either and gets {"ok": true}, the same for a new and a known email.
    A phone is only linked to a row that already has a phone: a row with none (signed up before phones were recorded,
    or from an old app) has no owner, and could otherwise be claimed by whoever sends the email first. Nobody can
    change those from the app."""
    refused = JsonResponse({"error": "Too many sign-ups from this network. Try again in an hour."}, status=429)
    if _rate_limited("signup", request, limit=SIGNUP_TRIES_PER_HOUR):
        return refused
    # Once this network has used up its new sign-ups, every sign-up from it gets this answer until the hour ends,
    # whether the email is here or not. (Refusing only the new ones told the caller which emails are signed up.)
    # Nothing is lost: the app keeps a refused sign-up in its outbox and sends it again later.
    if _rate_limited("signup-new", request, limit=NEW_SIGNUPS_PER_HOUR, count=False):
        return refused

    data = _json_body(request)
    if data is None:
        return JsonResponse({"error": "Send JSON."}, status=400)

    try:
        email = _email(data.get("email"))
    except ValidationError:
        return JsonResponse({"error": "Enter a valid email address."}, status=400)

    first, last = split_name(_text(data.get("name"), 120))
    if not first:  # app versions before the welcome screen send only a first name
        first = _text(data.get("first_name")).strip()[:80]
    fields = {"company": _text(data.get("company")).strip()[:120]}
    if first:
        fields.update(first_name=first, last_name=last)
    consent = _text(data.get("consent")).strip()[:200]
    if consent:
        fields.update(consent_text=consent, consent_at=timezone.now())
    install_hash = _install_hash(data.get("install_id"))

    record = AppSignup.objects.filter(email__iexact=email).first()
    created = False
    if record is None:
        if _rate_limited("signup-new", request, limit=NEW_SIGNUPS_PER_HOUR):
            return refused
        source = AppSignup.WELCOME if data.get("source") == AppSignup.WELCOME else AppSignup.SETTINGS
        try:
            with transaction.atomic():
                record = AppSignup.objects.create(email=email, source=source, wants_offers=bool(data.get("wants_offers")), **fields)
                if install_hash:
                    SignupPhone.objects.create(signup=record, install_hash=install_hash)
                _cancel_pending_removal(record)
            created = True
        except IntegrityError:  # the same email arrived twice at the same moment
            record = AppSignup.objects.get(email__iexact=email)
    if not created:
        phones = list(record.phones.order_by("created_at", "pk").values_list("install_hash", flat=True))  # oldest first
        if not (install_hash and phones and install_hash == phones[0]):
            # Not the phone that owns this sign-up. It used to fill in blanks and could switch offers off, and before
            # that it counted as "theirs" from its second request on: a stranger who knew the email could rewrite the
            # name, company, offers choice and consent. Now it is linked and nothing else: no change, no GoHighLevel call.
            if install_hash and phones and install_hash not in phones:
                try:
                    SignupPhone.objects.get_or_create(signup=record, install_hash=install_hash)
                except IntegrityError:  # the sign-up was removed at this very moment: nothing left to link to
                    pass
            # "changed": false is for the app on that phone. A request that names no phone (an old app version, or
            # a script) has no use for it and gets the plain answer, which tells it nothing about the email.
            return JsonResponse({"ok": True, "changed": False} if install_hash else {"ok": True})
        # The owner phone: bring the row up to date. Blanks never wipe what is there; where and when they first signed up stay.
        changes = {name: value for name, value in fields.items() if value}
        if "wants_offers" in data:
            changes["wants_offers"] = bool(data["wants_offers"])
        changes["ghl_synced_at"] = None  # so the sync_signups command retries if GoHighLevel is down right now
        # Only the columns this request sets are written. Saving the whole row from the copy loaded above put back
        # the old ghl_contact_id and ghl_had_tags over what an overlapping request for this email had just stored,
        # and the next sync then took the app's own tags for tags the person had before.
        if not AppSignup.objects.filter(pk=record.pk).update(**changes):
            return JsonResponse({"ok": True})  # removed at this very moment (a plain save() would have put the row back)
        for name, value in changes.items():
            setattr(record, name, value)

    # The phone is waiting, so GoHighLevel gets a few seconds and no more. Whatever fails here is retried by the cron.
    started = time.monotonic()
    synced = sync_signup_to_ghl(record, timeout=owner_alerts.QUICK)
    if created and synced and time.monotonic() - started < owner_alerts.QUICK:
        owner_alerts.alert_signup(record, timeout=owner_alerts.QUICK)  # GoHighLevel is slow today: the cron sends it
    return JsonResponse({"ok": True})


def _owner_phone(record):
    """The install hash of the phone that owns a sign-up: the first one linked to it. None for a sign-up with no phone."""
    return record.phones.order_by("created_at", "pk").values_list("install_hash", flat=True).first()


def carry_out_removal(record):
    """Deletes a sign-up, with every phone linked to it, and returns the SignupRemoval row that holds what is still
    to do in GoHighLevel. Call it inside a transaction with the sign-up row locked, then pass the result to
    owner_alerts.finish_removal. The admin can use the same two steps to carry out a removal request."""
    removal = SignupRemoval.objects.create(email=record.email, name=record.full_name, ghl_contact_id=record.ghl_contact_id,
                                           ghl_had_tags=record.ghl_had_tags)
    record.delete()  # its phone links go with it
    return removal


def _tell_owner_of_removal_request(record):
    """One email to the app's owner about a removal request the server did not carry out. owner_alerts.notify sends it
    once per sign-up (the key) and never raises; the try is for the unexpected, so the person's request still gets
    its answer. The request is on the sign-up either way (removal_requested_at)."""
    asked = timezone.localtime(record.removal_requested_at).strftime("%b %-d, %Y at %-I:%M %p %Z")
    lines = [
        f"Email: {record.email}",
        f"Name: {record.full_name or '(not given)'}",
        f"Asked: {asked}",
        "A phone that did not make this sign-up asked to remove it. Nothing was deleted, because anyone who knows an "
        "email address can link a phone to it. The phone that asked is no longer linked.",
        "If the request is real: delete this sign-up in the admin (Sign-ups) and take the tags zero-harm-weekly, "
        "zero-harm-app-signup and zero-harm-offers-optin off the contact in GoHighLevel.",
        "If it is not: open the sign-up in the admin and clear 'Removal requested at'.",
    ]
    try:
        owner_alerts.notify(f"Zero Harm removal request to check: {record.email}", lines, key=f"signup-removal-request:{record.pk}")
    except Exception:
        log.exception("The owner could not be told about the removal request for sign-up %s", record.pk)


REQUEST_NOTICE_DAYS = 7  # well inside the 14 days owner_alerts.notify remembers a notice it has sent


def retry_removal_request_notices(now=None):
    """For the cron: tells the owner about removal requests of the last week again. A notice that already went out is
    not sent twice (notify remembers its key), so this only sends the ones that failed the first time, for example
    because GoHighLevel was down when the person asked. Returns how many sign-ups it looked at."""
    since = (now or timezone.now()) - dt.timedelta(days=REQUEST_NOTICE_DAYS)
    waiting = list(AppSignup.objects.filter(removal_requested_at__gte=since).order_by("removal_requested_at")[:50])
    for record in waiting:
        _tell_owner_of_removal_request(record)
    return len(waiting)


def _cancel_pending_removal(record):
    """They signed up again before an earlier removal of this email reached GoHighLevel: that removal is called off,
    so it can't take the tags off the new sign-up. What it knew about the contact's own tags carries over."""
    for removal in SignupRemoval.objects.filter(email__iexact=record.email, ghl_done_at__isnull=True):
        if record.ghl_had_tags is None and removal.ghl_had_tags is not None:
            record.ghl_had_tags = removal.ghl_had_tags
            record.save(update_fields=["ghl_had_tags"])
        removal.delete()


@csrf_exempt  # called by the mobile app, like signup
@require_POST
def signup_remove(request):
    """"Remove my info" in the app. What happens depends on whether this phone owns the sign-up (the first phone linked
    to it; see signup).

    The owner phone: the sign-up is deleted, with every phone linked to it, and its newsletter tags come off in
    GoHighLevel (only the ones the app added). The answer is {"ok": true}, the same as when nothing matched.

    Any other linked phone: that phone is unlinked and nothing is deleted. The request is written on the sign-up
    (removal_requested_at), the app's owner gets an email so they can check it and act, and the answer is
    {"ok": true, "pending": true}. Two rules were tried before this one and both failed. "A phone only unlinks
    itself" told people on a new or reinstalled phone they were removed and kept them on the list, with nobody told.
    "Any linked phone removes the sign-up" let anyone who knew an email take that person off the list with two
    requests, and then sign the address up again with a name, company and consent of their own. Now a stranger can
    remove nobody, and a real request from a second phone reaches a person who can carry it out.

    One phone can be linked to several sign-ups (a shared tablet). Each is handled by its own rule: the ones this
    phone made are deleted, the others get a request."""
    if _rate_limited("signup-remove", request, limit=REMOVALS_PER_HOUR):
        return JsonResponse({"error": "Too many requests from this network. Try again in an hour."}, status=429)
    data = _json_body(request)
    install_hash = _install_hash(data.get("install_id")) if data is not None else ""
    removals, requests = [], []
    if install_hash:
        with transaction.atomic():
            ids = list(SignupPhone.objects.filter(install_hash=install_hash).values_list("signup_id", flat=True))
            for record in AppSignup.objects.select_for_update().filter(pk__in=ids):
                if _owner_phone(record) == install_hash:
                    removals.append(carry_out_removal(record))
                    continue
                SignupPhone.objects.filter(signup=record, install_hash=install_hash).delete()
                if record.removal_requested_at is None:  # the first request stands; later ones do not move the date
                    record.removal_requested_at = timezone.now()
                    record.save(update_fields=["removal_requested_at"])
                requests.append(record)
    for removal in removals:  # if GoHighLevel is down, the row stays and the cron finishes it
        owner_alerts.finish_removal(removal, timeout=owner_alerts.QUICK)
    for record in requests:
        _tell_owner_of_removal_request(record)
    return JsonResponse({"ok": True, "pending": True} if requests else {"ok": True})


# ---- Feed: regulatory alerts and free resources -------------------------------------------------
import base64
import datetime as dt
import hmac
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils.dateparse import parse_date, parse_datetime

from .integrations import sync_sheet_to_ghl
from .models import FeedItem, GhlSync, SigninSheet

PACIFIC = ZoneInfo("America/Los_Angeles")


@require_GET
def feed_list(request):
    items = FeedItem.objects.released()
    kind = request.GET.get("kind")
    if kind:
        # Only kinds that exist go to the database. Anything else matches nothing anyway, and text PostgreSQL cannot
        # take (a NUL character) used to end in a 500 here.
        wanted = [k for k in kind.split(",") if k in dict(FeedItem.KINDS)]
        if not wanted:
            return JsonResponse({"items": []})
        items = items.filter(kind__in=wanted)
    return JsonResponse({"items": [i.as_api() for i in items[:100]]})


@require_GET
def feed_detail(request, pk):
    item = FeedItem.objects.released().filter(pk=pk).first()
    if not item:
        return JsonResponse({"error": "Not available."}, status=404)
    return JsonResponse(item.as_api())


def _when(value):
    """Accepts ISO date-times, plain dates and GHL's 'YYYY-MM-DD HH:MM'. Times without a zone are Pacific."""
    if not value:
        return dt.datetime.now(dt.timezone.utc)
    value = str(value).strip().replace("/", "-")
    moment = parse_datetime(value.replace(" ", "T")) if any(c in value for c in "T: ") else None
    if moment is None:
        day = parse_date(value[:10])
        if day is None:
            raise ValueError(f"Can't read the date '{value}'. Use YYYY-MM-DD HH:MM.")
        moment = dt.datetime.combine(day, dt.time(6, 0))
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=PACIFIC)
    return moment.astimezone(dt.timezone.utc)


def _day(value):
    """A calendar day from the spellings _when takes: 2027-01-03, 2027/01/03, or either with a time after it. The time
    is dropped: an effective date is the day as written, in no time zone. Raises ValueError for anything else."""
    text = _text(value).strip().replace("/", "-")
    day = parse_date(text[:10])  # None for text that is not shaped like a date; ValueError for one like 2027-02-30
    if day is None or (len(text) > 10 and parse_datetime(text.replace(" ", "T")) is None):
        raise ValueError("effective_date must be a date like 2027-01-03.")
    return day


def _truthy(v):
    return str(v).strip().lower() in ("1", "true", "yes", "y", "on", "send")


KIND_WORDS = {"alert": "alert", "regulatory alert": "alert", "course": "course", "free course": "course", "tool": "tool",
              "free tool": "tool", "video": "video", "newsletter": "newsletter", "newsletter issue": "newsletter"}
JURIS_WORDS = {"federal": "federal", "federal osha": "federal", "nevada": "nevada", "las vegas": "las_vegas", "las_vegas": "las_vegas", "": ""}


@csrf_exempt  # called by the GoHighLevel workflow, authenticated by the shared key instead
@require_POST
def ingest(request):
    """Publish from GoHighLevel. Header X-ZeroHarm-Key must match INGEST_KEY.
    Body: {"action": "publish" | "sync_year", ...}. Publishing the same external_id again updates the item."""
    key = settings.INGEST_KEY
    sent = request.headers.get("X-ZeroHarm-Key", "")
    # Compared as bytes: compare_digest raises on text with letters outside ASCII, which made such a wrong key a 500.
    if not key or not hmac.compare_digest(sent.encode(), key.encode()):
        return JsonResponse({"error": "Not authorized."}, status=401)
    data = _json_body(request)
    if data is None:
        return JsonResponse({"error": "Send JSON."}, status=400)
    data = {str(k).strip().lower().replace(" ", "_"): v for k, v in data.items()}

    if data.get("action") == "sync_zero_hour":
        from .zero_hour import sync_episodes
        return JsonResponse({"ok": True, "log": sync_episodes()})

    if data.get("action") == "sync_year":
        try:
            year = int(data.get("year"))
        except (TypeError, ValueError, OverflowError):
            year = 0
        if not 2020 <= year <= 2100:  # a negative or enormous year used to fail in the database instead
            return JsonResponse({"error": "Give the year, like 2028."}, status=400)
        job = GhlSync.objects.create(year=year, requested_by="ghl")
        return JsonResponse({"ok": True, "queued": f"{year} sync", "id": job.pk}, status=202)

    kind = KIND_WORDS.get(str(data.get("kind", data.get("type", ""))).strip().lower())
    title = _text(data.get("title")).strip()
    if not kind or not title:
        return JsonResponse({"error": "kind (alert, course, tool, video, newsletter) and title are required."}, status=400)
    juris = JURIS_WORDS.get(str(data.get("jurisdiction", "")).strip().lower())
    if juris is None:
        return JsonResponse({"error": "jurisdiction must be Federal, Nevada or Las Vegas."}, status=400)
    present = lambda *names: next((n for n in names if n in data and str(data[n]).strip() != ""), None)
    fields = {"kind": kind, "title": title[:200]}
    try:
        for name in ("publish_at", "expires_at"):
            if name == "expires_at" and name in data and data[name] is None:
                fields[name] = None  # null: it never expires. (It was read as "now", which took the item out of the app at once.)
            elif present(name):
                try:
                    fields[name] = _when(data[name])
                except OverflowError:  # year 9999 and the like: no such moment once it is turned into UTC
                    raise ValueError(f"{name} is too far in the past or the future.")
        if "effective_date" in data and data["effective_date"] is None:
            # null: no effective date. A new item goes out without one and an update clears the one it had, as
            # before. (For a while null was refused like unreadable text, and the item was not published at all.)
            fields["effective_date"] = None
        elif present("effective_date"):
            # Text that cannot be read as a date is refused. It used to be saved as "no date": the item went out
            # without one (or lost the one it had) and GoHighLevel was told 201.
            fields["effective_date"] = _day(data["effective_date"])
    except ValueError as err:
        return JsonResponse({"error": str(err)}, status=400)
    if present("jurisdiction"):
        fields["jurisdiction"] = juris
    for target, names, limit in (("summary", ("summary",), 2000), ("body_md", ("body", "body_md"), 20000)):
        name = present(*names)
        if name:
            fields[target] = _text(data[name]).strip()[:limit]
    for target, names in (("link_url", ("link", "link_url")), ("image_url", ("image", "image_url"))):
        name = present(*names)
        if name:
            # An address longer than its column used to be cut to 500 characters and then refused by PostgreSQL (the
            # column holds 200): a 500 with nothing published. Cutting it to fit would publish a dead link, so say so.
            fields[target] = _text(data[name]).strip()
            room = FeedItem._meta.get_field(target).max_length
            if len(fields[target]) > room:
                return JsonResponse({"error": f"{target} is {len(fields[target])} characters long and at most {room} fit. Use a shorter link."}, status=400)
    for flag in ("send_push", "featured"):
        if present(flag):
            fields[flag] = _truthy(data[flag])
    if present("unpublish"):
        fields["published"] = not _truthy(data["unpublish"])
    for f in ("link_url", "image_url"):
        if fields.get(f) and not fields[f].startswith("https://"):
            return JsonResponse({"error": f"{f} must start with https://"}, status=400)
    external_id = (_text(data.get("external_id")) or f"{kind}:{title.lower()}")[:120]
    item = FeedItem.objects.filter(external_id=external_id).first()
    created = item is None
    if created:
        fields.setdefault("publish_at", _when(None))
        item = FeedItem(external_id=external_id)
    for k, v in fields.items():
        setattr(item, k, v)
    item.save()
    return JsonResponse({"ok": True, "id": item.pk, "created": created, "publish_at": item.publish_at.isoformat()}, status=201 if created else 200)


SHEETS_PER_HOUR = 30


def _sheet_sent_before(fingerprint, fields):
    """The sheet an earlier copy of this very request made, or None. Every sheet keeps a fingerprint (SHA-256) of its
    PDF in the database, also after GoHighLevel has taken the PDF and the copy here is emptied. The same PDF with the
    same details is the same sheet, however long ago it came and whatever restarted in between; the first one stored
    answers. (This used to rest on the server's memory, which a restart empties, and on comparing stored PDFs, which
    are gone once forwarded: such a resend was stored and forwarded a second time.)
    A sheet that only looks alike, such as a second crew on the same talk and day, has other signatures and so
    another PDF: it is always kept. Sheets forwarded before the fingerprint existed have none and are not found."""
    return SigninSheet.objects.filter(pdf_sha256=fingerprint, **fields).defer("pdf").order_by("pk").first()


@csrf_exempt  # called by the app
@require_POST
def signin_sheet(request):
    """Receives a finished crew sign-in sheet PDF from the app and forwards it to GoHighLevel.

    The app keeps a sheet in its outbox until it gets an answer, and gives up waiting after a minute while the
    forwarding here can take longer; a phone on a dock also loses its signal. So the same sheet can arrive twice. The
    second time the first sheet is answered again (200 instead of 201) and nothing is stored or forwarded twice."""
    if _rate_limited("sheet", request, limit=SHEETS_PER_HOUR):
        return JsonResponse({"error": "Too many sheets from this network. Try again in an hour."}, status=429)
    if len(request.body) > 20 * 1024 * 1024:
        return JsonResponse({"error": "That sheet is too large."}, status=413)
    data = _json_body(request)
    try:
        if data is None:
            raise ValueError("not a JSON object")
        pdf = base64.b64decode(data.get("pdf_base64") or "", validate=True)
        email = _email(data.get("supervisor_email"))
        held_on = parse_date(_text(data.get("held_on"))[:10]) or dt.date.today()
    except (TypeError, ValueError, ValidationError):  # TypeError: pdf_base64 was a number or a list
        return JsonResponse({"error": "Send the PDF, a valid supervisor email and the date."}, status=400)
    if not pdf.startswith(b"%PDF"):
        return JsonResponse({"error": "That file is not a PDF."}, status=400)
    try:
        attendees = max(0, int(data.get("attendee_count") or 0))
    except (TypeError, ValueError, OverflowError):
        attendees = PG_INT_MAX + 1
    if attendees > PG_INT_MAX:
        return JsonResponse({"error": "attendee_count must be a whole number."}, status=400)
    issue, program = data.get("issue"), data.get("program")
    fields = dict(
        # isinstance first: a list or an object here cannot be looked up in the dict, which was a 500
        program=program if isinstance(program, str) and program in dict(SigninSheet.PROGRAMS) else "zero-harm-weekly",
        issue=issue if type(issue) is int and 0 <= issue <= PG_INT_MAX else None,  # anything else the column can't hold
        talk_title=_text(data.get("talk_title"), 200), supervisor_name=_text(data.get("supervisor_name"), 120) or "Supervisor",
        supervisor_email=email, company=_text(data.get("company"), 120), location=_text(data.get("location"), 120),
        held_on=held_on, attendee_count=attendees, has_group_photo=bool(data.get("has_group_photo")),
    )
    fingerprint = hashlib.sha256(pdf).hexdigest()
    sheet = _sheet_sent_before(fingerprint, fields)
    if sheet:
        return JsonResponse({"ok": True, "id": sheet.pk, "saved_to_ghl": sheet.status == "synced"})
    sheet = SigninSheet.objects.create(pdf=pdf, pdf_sha256=fingerprint, **fields)
    synced = sync_sheet_to_ghl(sheet)  # if GHL is down, the cron retries
    return JsonResponse({"ok": True, "id": sheet.pk, "saved_to_ghl": synced}, status=201)


# ---- OTIS knowledge base, weather and talk suggestions ------------------------------------------
from . import weather as wx
from .integrations import sync_suggestion_to_ghl
from .models import KbEntry, TalkSuggestion, ToolboxTalk


def _talk_chunks(talk, lang="en"):
    """Splits a released talk into sections so OTIS can retrieve and cite just the relevant part."""
    if lang == "es":
        title, question = talk.title_es, talk.crew_question_es
    else:
        title, question = talk.title, talk.crew_question
    body = talk.public_body(lang)  # no last week's answer before the Sunday send
    label = f"Zero Harm Weekly #{talk.number or talk.issue}: {title}"
    sections, head = [], "Overview"
    for block in (body or "").split("\n\n## "):
        block = block.strip().lstrip("#").strip()
        if not block:
            continue
        if sections or (body or "").startswith("## "):
            head, _, block = block.partition("\n\n")
        sections.append((head.strip(), block.strip()))
    out = [{"id": f"t{talk.issue}-{lang}-q", "title": label, "text": f"Crew question: {question}", "source": label, "lang": lang, "issue": talk.issue}]
    for i, (h, text) in enumerate(sections):
        if text:
            out.append({"id": f"t{talk.issue}-{lang}-{i}", "title": f"{label} · {h}", "text": text, "source": label, "lang": lang, "issue": talk.issue})
    return out


@require_GET
def otis_kb(request):
    """Everything OTIS may answer from (v1). The app now uses /api/v2/otis/kb, which only downloads when it changed."""
    items = kb_items()
    version = max([e.updated_at for e in KbEntry.objects.all()] + [t.updated_at for t in ToolboxTalk.objects.available()], default=None)
    return JsonResponse({"version": version.isoformat() if version else "0", "items": items})


def kb_items():
    """Reviewed KB entries plus every released talk (English, and approved Spanish) and Zero Hour huddle card."""
    items = [{"id": f"k{e.pk}", "title": e.title, "text": e.body, "source": e.source or e.title, "lang": "en", "tags": e.tags, "issue": None}
             for e in KbEntry.objects.filter(published=True)]
    for talk in ToolboxTalk.objects.available():
        items += _talk_chunks(talk)
        if talk.spanish_status == ToolboxTalk.ES_APPROVED:
            items += _talk_chunks(talk, "es")
    for ep in Episode.objects.released():
        items += _episode_chunks(ep)
    items += _regulation_chunks()
    return items


def _regulation_chunks():
    """The official OSHA wording behind OTIS's entries, so answers can quote and link the actual rule."""
    from regs.retrieve import for_otis

    return [{"id": f"r{c.pk}", "title": f"OSHA regulation text: {c.section.heading} {c.label}".strip(), "text": c.text,
             "source": c.citation, "lang": "en", "issue": None, "tags": "osha regulation rule standard law"}
            for c in for_otis()]


@require_GET
def otis_config(request):
    """Which on-device model the app downloads. Phones with less memory get the small one."""
    return JsonResponse({
        "enabled": settings.OTIS_ENABLED,
        "model": settings.OTIS_MODEL,
        "small_model": settings.OTIS_SMALL_MODEL,
        "min_memory_gb_for_model": 6,
    })


# Lookups one network may send to the weather service in an hour. Each is three requests, one after the other, on a
# server with 8 threads. One network is often many phones: a phone carrier puts whole crews behind one address, and
# each phone asks again every 10 minutes from its own site. 50 such phones are 300 lookups an hour; 360 leaves room.
# (It was 60, which 12 phones behind one address used up: their weather and heat card went blank until the hour ended.)
WEATHER_LOOKUPS_PER_HOUR = 360
# Failed lookups do not use the hour's allowance up (they are given back), so an outage of the weather service
# cannot leave a crew refused once it is over. What keeps a failing service from being hammered instead: a point
# that failed is not tried again for two minutes (weather.failed_lately), and one network gets at most this many
# failed lookups in two minutes; after that its new points are answered "unavailable" without asking, until the two
# minutes end. 12 per two minutes is the same 360 an hour.
WEATHER_FAILURES = 12
WEATHER_FAILURE_SECONDS = 120


@require_GET
def weather(request):
    try:
        lat = round(float(request.GET["lat"]), 2)
        lon = round(float(request.GET["lon"]), 2)
    except (KeyError, ValueError):
        return JsonResponse({"error": "lat and lon are required."}, status=400)
    if not (18 <= lat <= 72 and -180 <= lon <= -64):
        return JsonResponse({"error": "Weather is available for US locations."}, status=404)
    # Only a lookup that really goes to the weather service counts. A point looked up in the last 10 minutes is
    # answered from the cache and costs nothing, so it is never refused: a whole crew on one plant Wi-Fi asks for
    # the same point.
    hit = wx.cached(lat, lon)
    if hit:
        return JsonResponse(hit)
    unavailable = JsonResponse({"error": "Weather is unavailable right now."}, status=503)
    if wx.failed_lately(lat, lon) or _rate_limited("weather-failed", request, limit=WEATHER_FAILURES, count=False, seconds=WEATHER_FAILURE_SECONDS):
        return unavailable  # no outside request, and nothing counted
    if _rate_limited("weather", request, limit=WEATHER_LOOKUPS_PER_HOUR):
        return JsonResponse({"error": "Too many weather lookups from this network. Try again in an hour."}, status=429)
    try:
        return JsonResponse(wx.conditions(lat, lon))
    except Exception:
        _give_back("weather", request)
        _rate_limited("weather-failed", request, limit=WEATHER_FAILURES, seconds=WEATHER_FAILURE_SECONDS)
        return unavailable


SUGGESTIONS_PER_HOUR = 10
SUGGESTION_RESEND_MINUTES = 10  # the same idea, word for word, inside this long is the phone sending it again


@csrf_exempt  # called by the app
@require_POST
def suggestion(request):
    if _rate_limited("suggest", request, limit=SUGGESTIONS_PER_HOUR):
        return JsonResponse({"error": "Thanks! That's a lot of ideas at once. Try again in an hour."}, status=429)
    data = _json_body(request)
    if data is None:
        return JsonResponse({"error": "Send JSON."}, status=400)
    topic = _text(data.get("topic")).strip()
    if len(topic) < 3:
        return JsonResponse({"error": "Tell us the topic in a few words."}, status=400)
    email = _text(data.get("email")).strip()
    if email:
        try:
            email = _email(email)
        except ValidationError:
            return JsonResponse({"error": "Check the email address, or leave it blank."}, status=400)
    fields = dict(
        topic=topic[:200], details=_text(data.get("details"), 4000), month_theme=_text(data.get("month_theme"), 80),
        name=_text(data.get("name"), 120), email=email, company=_text(data.get("company"), 120),
        may_contact=bool(data.get("may_contact")) and bool(email),
    )
    # The app gives up waiting after 10 seconds and sends the idea again, and a phone on a dock loses its signal: the
    # same idea used to be stored twice (and noted twice in GoHighLevel). An idea carries no phone id, so "the same
    # phone again" is told by the idea itself: every field equal, inside ten minutes. The first one answers (200, not
    # 201) and its GoHighLevel step is not started a second time; if that did not finish, the cron finishes it.
    since = timezone.now() - dt.timedelta(minutes=SUGGESTION_RESEND_MINUTES)
    first = TalkSuggestion.objects.filter(created_at__gte=since, **fields).order_by("pk").first()
    if first:
        return JsonResponse({"ok": True, "id": first.pk})
    s = TalkSuggestion.objects.create(**fields)
    sync_suggestion_to_ghl(s)
    return JsonResponse({"ok": True, "id": s.pk}, status=201)


# ---- Zero Hour ------------------------------------------------------------------------------------
from .models import Episode


@require_GET
def episode_list(request):
    return JsonResponse({"episodes": [e.as_api() for e in Episode.objects.released()]})


@require_GET
def episode_detail(request, number):
    ep = Episode.objects.released().filter(number=number).first()
    if not ep:
        return JsonResponse({"error": "This episode isn't out yet."}, status=404)
    return JsonResponse(ep.as_api())


def _episode_chunks(ep):
    label = f"Zero Hour EP {ep.number:02d}: {ep.title} (huddle card)"
    base = {"lang": "en", "issue": None, "episode": ep.number, "source": label}
    return [
        {**base, "id": f"z{ep.number}-story", "title": f"{label} · The story", "text": f"{ep.hazard}. {ep.story}"},
        {**base, "id": f"z{ep.number}-chain", "title": f"{label} · Where the chain could have broken", "text": " ".join(ep.chain)},
        {**base, "id": f"z{ep.number}-checks", "title": f"{label} · {ep.checks_label}", "text": ". ".join(ep.checks) + "."},
        {**base, "id": f"z{ep.number}-stop", "title": f"{label} · Say stop when you see", "text": ep.stop_when},
        {**base, "id": f"z{ep.number}-emergency", "title": f"{label} · {ep.emergency_label}", "text": ep.emergency},
    ]
