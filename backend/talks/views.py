import json
import time

from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from . import owner_alerts
from .integrations import sync_signup_to_ghl
from .models import AppSignup, SignupPhone, SignupRemoval, ToolboxTalk, split_name


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
    """The address the trusted proxy saw. Railway appends it to X-Forwarded-For, so anything a client puts first is ignored."""
    hops = [h.strip() for h in request.META.get("HTTP_X_FORWARDED_FOR", "").split(",") if h.strip()]
    n = settings.NUM_PROXIES
    if n and hops:
        return hops[-min(n, len(hops))]
    return request.META.get("REMOTE_ADDR", "")


def _network(request):
    """The network a request came from, as a salted hash. An IPv6 home or mobile connection owns a whole /64 and could
    otherwise switch addresses to dodge a limit; hashing means no readable address sits in the cache."""
    import hashlib
    import ipaddress

    ident = _client_ip(request)
    try:
        address = ipaddress.ip_address(ident)
        if address.version == 6:
            ident = str(ipaddress.ip_network(f"{address}/64", strict=False).network_address)
    except ValueError:
        pass
    return hashlib.sha256(f"{settings.SECRET_KEY}:rate:{ident}".encode()).hexdigest()


def _rate_limited(name, request, limit=5):
    """At most `limit` tries an hour from one network."""
    key = f"{name}-rate:{_network(request)}"
    attempts = cache.get(key, 0)
    if attempts >= limit:
        return True
    cache.set(key, attempts + 1, 3600)
    return False


def _install_hash(value):
    """The salted hash of the phone's random install id, or "" when none (or a malformed one) was sent."""
    from monday.api import _hash  # one salt for install ids across the whole backend

    return _hash(value) if isinstance(value, str) and 8 <= len(value) <= 80 else ""


# A whole crew often signs in together on one plant Wi-Fi, which is one network address, so new emails get a roomy
# limit. Repeat sign-ups of an email already here don't count toward it; they only get the wider limit on all tries.
NEW_SIGNUPS_PER_HOUR = 30
SIGNUP_TRIES_PER_HOUR = 120
REMOVALS_PER_HOUR = 5


@csrf_exempt  # called by the mobile app, which has no browser session or CSRF cookie
@require_POST
def signup(request):
    """Name and email from the welcome screen or Settings. One row per email. The answer is 200 whether the email is
    new or already here, so it can't be used to find out who has signed up. The lead goes to GoHighLevel and, for a new email, an alert to the owner.

    Each phone that signs up with the email is linked to the row. A repeat from a linked phone updates the row. A repeat
    from any other phone (or an old app version that sends no phone id) only links that phone and fills in what is
    blank: it never changes the name, company, offers choice or consent someone else gave. A phone is only linked to a
    row that already has a phone: a row with none (signed up before phones were recorded, or from an old app) could
    otherwise be claimed by anyone who knows the email and then removed. Those people use "Delete my data"."""
    if _rate_limited("signup", request, limit=SIGNUP_TRIES_PER_HOUR):
        return JsonResponse({"error": "Too many sign-ups from this network. Try again in an hour."}, status=429)

    try:
        data = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        data = None
    if not isinstance(data, dict):
        return JsonResponse({"error": "Send JSON."}, status=400)

    email = str(data.get("email", "")).strip().lower()
    try:
        validate_email(email)
    except ValidationError:
        return JsonResponse({"error": "Enter a valid email address."}, status=400)

    first, last = split_name(str(data.get("name") or "")[:120])
    if not first:  # app versions before the welcome screen send only a first name
        first = str(data.get("first_name") or "").strip()[:80]
    fields = {"company": str(data.get("company") or "").strip()[:120]}
    if first:
        fields.update(first_name=first, last_name=last)
    consent = str(data.get("consent") or "").strip()[:200]
    if consent:
        fields.update(consent_text=consent, consent_at=timezone.now())
    install_hash = _install_hash(data.get("install_id"))

    record = AppSignup.objects.filter(email__iexact=email).first()
    created = False
    if record is None:
        if _rate_limited("signup-new", request, limit=NEW_SIGNUPS_PER_HOUR):
            return JsonResponse({"error": "Too many sign-ups from this network. Try again in an hour."}, status=429)
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
        linked = bool(install_hash) and record.phones.filter(install_hash=install_hash).exists()
        if install_hash and not linked and record.phones.exists():
            SignupPhone.objects.get_or_create(signup=record, install_hash=install_hash)
        if linked:
            # Their own phone: bring the row up to date. Blanks never wipe what is there; where and when they first signed up stay.
            for name, value in fields.items():
                if value:
                    setattr(record, name, value)
            if "wants_offers" in data:
                record.wants_offers = bool(data["wants_offers"])
        else:
            if not record.first_name and first:
                record.first_name, record.last_name = first, last
            if not record.company and fields["company"]:
                record.company = fields["company"]
            if not record.consent_text and consent:
                record.consent_text, record.consent_at = consent, fields["consent_at"]
        record.ghl_synced_at = None  # so the sync_signups command retries if GoHighLevel is down right now
        record.save()

    # The phone is waiting, so GoHighLevel gets a few seconds and no more. Whatever fails here is retried by the cron.
    started = time.monotonic()
    synced = sync_signup_to_ghl(record, timeout=owner_alerts.QUICK)
    if created and synced and time.monotonic() - started < owner_alerts.QUICK:
        owner_alerts.alert_signup(record, timeout=owner_alerts.QUICK)  # GoHighLevel is slow today: the cron sends it
    return JsonResponse({"ok": True})


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
    """"Remove my info" in the app. Unlinks this phone from its sign-up. When no other phone is linked, the sign-up is
    deleted and its newsletter tags come off in GoHighLevel (only the ones the app added). The answer is the same
    whether or not anything matched, so it can't be used to find out who signed up."""
    if _rate_limited("signup-remove", request, limit=REMOVALS_PER_HOUR):
        return JsonResponse({"error": "Too many requests from this network. Try again in an hour."}, status=429)
    try:
        data = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        data = None
    install_hash = _install_hash(data.get("install_id")) if isinstance(data, dict) else ""
    removals = []
    if install_hash:
        with transaction.atomic():
            ids = list(SignupPhone.objects.filter(install_hash=install_hash).values_list("signup_id", flat=True))
            for record in AppSignup.objects.select_for_update().filter(pk__in=ids):
                record.phones.filter(install_hash=install_hash).delete()
                if record.phones.exists():
                    continue  # another phone still has this sign-up
                removals.append(SignupRemoval.objects.create(email=record.email, name=record.full_name, ghl_contact_id=record.ghl_contact_id,
                                                             ghl_had_tags=record.ghl_had_tags))
                record.delete()
    for removal in removals:  # if GoHighLevel is down, the row stays and the cron finishes it
        owner_alerts.finish_removal(removal, timeout=owner_alerts.QUICK)
    return JsonResponse({"ok": True})


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
        items = items.filter(kind__in=kind.split(","))
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
    if not key or not hmac.compare_digest(sent, key):
        return JsonResponse({"error": "Not authorized."}, status=401)
    try:
        data = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "Send JSON."}, status=400)
    data = {str(k).strip().lower().replace(" ", "_"): v for k, v in data.items()}

    if data.get("action") == "sync_zero_hour":
        from .zero_hour import sync_episodes
        return JsonResponse({"ok": True, "log": sync_episodes()})

    if data.get("action") == "sync_year":
        try:
            year = int(data.get("year"))
        except (TypeError, ValueError):
            return JsonResponse({"error": "Give the year, like 2028."}, status=400)
        job = GhlSync.objects.create(year=year, requested_by="ghl")
        return JsonResponse({"ok": True, "queued": f"{year} sync", "id": job.pk}, status=202)

    kind = KIND_WORDS.get(str(data.get("kind", data.get("type", ""))).strip().lower())
    title = str(data.get("title", "")).strip()
    if not kind or not title:
        return JsonResponse({"error": "kind (alert, course, tool, video, newsletter) and title are required."}, status=400)
    juris = JURIS_WORDS.get(str(data.get("jurisdiction", "")).strip().lower())
    if juris is None:
        return JsonResponse({"error": "jurisdiction must be Federal, Nevada or Las Vegas."}, status=400)
    present = lambda *names: next((n for n in names if n in data and str(data[n]).strip() != ""), None)
    fields = {"kind": kind, "title": title[:200]}
    try:
        if present("publish_at"):
            fields["publish_at"] = _when(data["publish_at"])
        if present("expires_at"):
            fields["expires_at"] = _when(data["expires_at"])
        if present("effective_date"):
            fields["effective_date"] = parse_date(str(data["effective_date"])[:10])
    except ValueError as err:
        return JsonResponse({"error": str(err)}, status=400)
    if present("jurisdiction"):
        fields["jurisdiction"] = juris
    for target, names, limit in (("summary", ("summary",), 2000), ("body_md", ("body", "body_md"), 20000),
                                 ("link_url", ("link", "link_url"), 500), ("image_url", ("image", "image_url"), 500)):
        name = present(*names)
        if name:
            fields[target] = str(data[name]).strip()[:limit]
    for flag in ("send_push", "featured"):
        if present(flag):
            fields[flag] = _truthy(data[flag])
    if present("unpublish"):
        fields["published"] = not _truthy(data["unpublish"])
    for f in ("link_url", "image_url"):
        if fields.get(f) and not fields[f].startswith("https://"):
            return JsonResponse({"error": f"{f} must start with https://"}, status=400)
    external_id = str(data.get("external_id") or f"{kind}:{title.lower()}")[:120]
    item = FeedItem.objects.filter(external_id=external_id).first()
    created = item is None
    if created:
        fields.setdefault("publish_at", _when(None))
        item = FeedItem(external_id=external_id)
    for k, v in fields.items():
        setattr(item, k, v)
    item.save()
    return JsonResponse({"ok": True, "id": item.pk, "created": created, "publish_at": item.publish_at.isoformat()}, status=201 if created else 200)


@csrf_exempt  # called by the app
@require_POST
def signin_sheet(request):
    """Receives a finished crew sign-in sheet PDF from the app and forwards it to GoHighLevel."""
    ipkey = f"sheet-rate:{_client_ip(request)}"
    if cache.get(ipkey, 0) >= 30:
        return JsonResponse({"error": "Too many sheets from this network. Try again in an hour."}, status=429)
    cache.set(ipkey, cache.get(ipkey, 0) + 1, 3600)
    if len(request.body) > 20 * 1024 * 1024:
        return JsonResponse({"error": "That sheet is too large."}, status=413)
    try:
        data = json.loads(request.body)
        pdf = base64.b64decode(data.get("pdf_base64", ""), validate=True)
        email = str(data.get("supervisor_email", "")).strip().lower()
        validate_email(email)
        held_on = parse_date(str(data.get("held_on", ""))[:10]) or dt.date.today()
    except (json.JSONDecodeError, ValueError, ValidationError):
        return JsonResponse({"error": "Send the PDF, a valid supervisor email and the date."}, status=400)
    if not pdf.startswith(b"%PDF"):
        return JsonResponse({"error": "That file is not a PDF."}, status=400)
    program = data.get("program") if data.get("program") in dict(SigninSheet.PROGRAMS) else "zero-harm-weekly"
    sheet = SigninSheet.objects.create(
        program=program,
        issue=data.get("issue") if isinstance(data.get("issue"), int) else None,
        talk_title=str(data.get("talk_title", ""))[:200], supervisor_name=str(data.get("supervisor_name", ""))[:120] or "Supervisor",
        supervisor_email=email, company=str(data.get("company", ""))[:120], location=str(data.get("location", ""))[:120],
        held_on=held_on, attendee_count=max(0, int(data.get("attendee_count") or 0)), has_group_photo=bool(data.get("has_group_photo")), pdf=pdf,
    )
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


@require_GET
def weather(request):
    try:
        lat = round(float(request.GET["lat"]), 2)
        lon = round(float(request.GET["lon"]), 2)
    except (KeyError, ValueError):
        return JsonResponse({"error": "lat and lon are required."}, status=400)
    if not (18 <= lat <= 72 and -180 <= lon <= -64):
        return JsonResponse({"error": "Weather is available for US locations."}, status=404)
    try:
        return JsonResponse(wx.conditions(lat, lon))
    except Exception:
        return JsonResponse({"error": "Weather is unavailable right now."}, status=503)


@csrf_exempt  # called by the app
@require_POST
def suggestion(request):
    key = f"suggest-rate:{_client_ip(request)}"
    if cache.get(key, 0) >= 10:
        return JsonResponse({"error": "Thanks! That's a lot of ideas at once. Try again in an hour."}, status=429)
    cache.set(key, cache.get(key, 0) + 1, 3600)
    try:
        data = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "Send JSON."}, status=400)
    topic = str(data.get("topic", "")).strip()
    if len(topic) < 3:
        return JsonResponse({"error": "Tell us the topic in a few words."}, status=400)
    email = str(data.get("email", "")).strip().lower()
    if email:
        try:
            validate_email(email)
        except ValidationError:
            return JsonResponse({"error": "Check the email address, or leave it blank."}, status=400)
    s = TalkSuggestion.objects.create(
        topic=topic[:200], details=str(data.get("details", ""))[:4000], month_theme=str(data.get("month_theme", ""))[:80],
        name=str(data.get("name", ""))[:120], email=email, company=str(data.get("company", ""))[:120],
        may_contact=bool(data.get("may_contact")) and bool(email),
    )
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
