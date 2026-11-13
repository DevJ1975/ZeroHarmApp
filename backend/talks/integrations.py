"""OneSignal push and GoHighLevel contact sync. Standard library only, so no extra dependencies."""
import hashlib
import json
import logging
import time
import urllib.error
import urllib.request
import uuid
from datetime import timedelta

from django.conf import settings
from django.core.cache import caches
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .ghl import TRANSPORT_ERRORS, error_text

log = logging.getLogger(__name__)
QUICK = 4         # seconds per GoHighLevel call while a phone is waiting for its answer (owner_alerts uses the same)
PHONE_BUDGET = 7  # seconds for all the GoHighLevel calls of one request together: the app gives up after 10


def _post(url, headers, payload, timeout=10):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        # A named client: OneSignal is behind Cloudflare too, which can refuse Python's default client name.
        headers={"Content-Type": "application/json", "Accept": "application/json", "User-Agent": "ZeroHarmApp/1.0", **headers},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            status, body = res.status, json.loads(res.read() or b"{}")
    except urllib.error.HTTPError as err:
        return err.code, {"error": error_text(err, 500)}
    except TRANSPORT_ERRORS as err:
        # Status 0: no usable answer (see ghl.TRANSPORT_ERRORS for what that covers). The request may or may not
        # have arrived, so callers treat it as "not done" and the cron tries again.
        return 0, {"error": f"{type(err).__name__}: {err}"}
    if not isinstance(body, dict):  # every caller reads the answer as an object
        return 0, {"error": f"answered with JSON that is not an object: {str(body)[:100]}"}
    return status, body


ONESIGNAL_PUSH = "https://api.onesignal.com/notifications?c=push"
PUSH_KEY_DAYS = 30  # how long OneSignal remembers an idempotency key
SAME_KEY_TRIES = 3  # "try again later" answers (429, 5xx) one key may get before the next try uses a new key


def _refused_key(kind, pk):
    return f"push-refused:{kind}:{pk}"


def _push_state(kind, pk):
    """(which key this push is on, how many "try again later" answers that key has had). (0, 0) for a push OneSignal
    has not turned away. Kept in the shared cache, which the web server and the cron both read."""
    try:
        state = caches["shared"].get(_refused_key(kind, pk))
    except Exception:  # the cache table is not there: the push matters more than the count
        state = None
    return tuple(state) if isinstance(state, (tuple, list)) and len(state) == 2 else (0, 0)


def push_key(kind, pk, sent_before=None):
    """The idempotency key for a push the cron keeps trying until it is marked sent. OneSignal sends a key once: a
    second request with the same key gets the first one's answer back and no second notification.

    The same push keeps the same key from one try to the next, so a push OneSignal accepted but whose answer was lost
    (a timeout, a dropped connection) is not delivered again 15 minutes later. The key changes only when a new send is
    meant: after the push has been marked sent (`sent_before`, for "send it again" from the admin or the command line),
    and after OneSignal turned it away for good (see _note_refusal)."""
    seed = f"zero-harm-push:{settings.ONESIGNAL_APP_ID}:{kind}:{pk}:{sent_before.isoformat() if sent_before else 'first'}:{_push_state(kind, pk)[0]}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, seed))


def _note_refusal(kind, pk, status):
    """Decides whether the next try of this push keeps its key, after OneSignal answered with an error status.

    429 and 5xx mean "try again later", and OneSignal's own pages say the request may still be going through and to
    retry with the SAME key (documentation.onesignal.com/reference/rate-limits). So the key stays, and a push that
    did go out behind a 500 is not sent a second time. It stays for SAME_KEY_TRIES such answers, the number of tries
    OneSignal suggests; after that the next try gets a new key, so a weekly safety talk push can never sit for good
    behind a key OneSignal keeps answering the same way.

    Any other refusal (400, 401, 403: a bad request or a bad key) sent nothing, and a remembered "no" must not be
    what a corrected retry gets back, so the next try has a new key at once.

    Written with set(), never incr(): on the database cache incr() saves the count again for only 5 minutes, and the
    next cron run, 15 minutes later, would have forgotten it."""
    number, busy = _push_state(kind, pk)
    if status == 429 or status >= 500:
        busy += 1
        if busy >= SAME_KEY_TRIES:
            number, busy = number + 1, 0
    else:
        number, busy = number + 1, 0
    try:
        caches["shared"].set(_refused_key(kind, pk), (number, busy), PUSH_KEY_DAYS * 24 * 3600)
    except Exception as err:
        log.warning("Could not note that OneSignal refused the %s %s push: %s", kind, pk, err)


def post_push(payload, kind="", pk=None, sent_before=None):
    """Sends one notification to OneSignal. Returns (status, body) like _post; status 0 means no usable answer.

    Give `kind` and `pk` (and the item's push_sent_at as `sent_before`) for a push that is retried until it is marked
    sent: it then carries an idempotency key, see push_key. A one-off push sent by hand goes without one.
    The Monday Minute push (monday/push.py) comes through here too: post_push(payload, "monday", minute.pk,
    minute.push_sent_at)."""
    if kind:
        payload = {**payload, "idempotency_key": push_key(kind, pk, sent_before)}
    status, body = _post(ONESIGNAL_PUSH, {"Authorization": f"Key {settings.ONESIGNAL_REST_API_KEY}"}, payload)
    if kind and status and not 200 <= status < 300:
        _note_refusal(kind, pk, status)
    return status, body


def talk_push_payload(talk):
    return {
        "app_id": settings.ONESIGNAL_APP_ID,
        "target_channel": "push",
        "filters": [{"field": "tag", "key": "weekly_talk", "relation": "=", "value": "on"}],
        "headings": {"en": "This week’s toolbox talk"},
        "contents": {"en": f"🦺 {talk.title}. 5 minutes, ready for Monday’s crew meeting."},
        "data": {"issue": talk.issue, "refresh": True},  # the app opens /talk/<issue> and refetches content
    }


def send_talk_push(talk, dry_run=False, mark_sent=True):
    """Sends the weekly push to devices with weekly_talk = on. Returns (ok, detail).
    mark_sent=False (an early push from the console) leaves push_sent_at alone, so the release push still goes out."""
    payload = talk_push_payload(talk)
    if dry_run:
        return True, payload
    if not (settings.ONESIGNAL_APP_ID and settings.ONESIGNAL_REST_API_KEY):
        return False, "OneSignal is not configured (ONESIGNAL_APP_ID / ONESIGNAL_REST_API_KEY)."
    status, body = post_push(payload, "talk", talk.issue, talk.push_sent_at) if mark_sent else post_push(payload)
    if 200 <= status < 300:
        if mark_sent:
            talk.push_sent_at = timezone.now()
            talk.save(update_fields=["push_sent_at"])
        return True, body
    log.error("OneSignal push for issue %s failed: %s %s", talk.issue, status, body)
    return False, body


SIGNUP_TAGS = ["zero-harm-app", "zero-harm-weekly", "zero-harm-app-signup"]
OFFERS_TAG = "zero-harm-offers-optin"
NEWSLETTER_TAGS = ["zero-harm-weekly", OFFERS_TAG, "zero-harm-app-signup"]  # taken off when someone removes their sign-up
REMOVED_TAG = "zero-harm-removed"
GHL_API = "https://services.leadconnectorhq.com"


def sync_signup_to_ghl(signup, timeout=10):
    """Puts the sign-up into GoHighLevel as a lead. Returns True when synced.

    First the contact is created or updated (name, company). Then the tags are added: zero-harm-weekly is the list the
    weekly newsletter goes to, and zero-harm-app-signup is the one a GHL workflow listens for to notify the owner. The
    tags are not sent with the first call because there they would replace every tag the contact already has (a
    customer's tags, or the sign-in sheet tag).

    The first time, it also notes which newsletter tags the contact already had, so a removal later leaves those on.
    Every time, it takes zero-harm-removed off if they had removed an earlier sign-up. The sign-up can be removed while
    this runs, so it checks the row is still there before tagging, and takes its own tags back off if the row went
    meanwhile.

    `signup` may be an old copy: the cron loads its list first and works through it, and the sign-up's own request can
    be syncing at the same moment. So "is this the first sync", "what did the contact have before" and "did they tick
    offers" are read from the row as it is now, after GoHighLevel has answered."""
    from . import ghl
    from .models import AppSignup

    if not (settings.GHL_PRIVATE_TOKEN and settings.GHL_LOCATION_ID):
        return False
    headers = {"Authorization": f"Bearer {settings.GHL_PRIVATE_TOKEN}", "Version": "2021-07-28"}
    payload = {"locationId": settings.GHL_LOCATION_ID, "email": signup.email, "source": "Zero Harm app"}
    if signup.first_name:
        payload["firstName"] = signup.first_name
    if signup.last_name:
        payload["lastName"] = signup.last_name
    if signup.company:
        payload["companyName"] = signup.company
    status, body = _post(f"{GHL_API}/contacts/upsert", headers, payload, timeout=timeout)
    contact = (body.get("contact") or {}) if 200 <= status < 300 else {}
    contact_id = str(contact.get("id") or "")[:40]
    if not contact_id:
        log.error("GHL sync for %s failed: %s %s", signup.email, status, body)
        return False

    try:
        tags_now = contact["tags"] if isinstance(contact.get("tags"), list) else ghl.contact_tags(contact_id, timeout=timeout)
    except ghl.GhlError as err:
        log.error("GHL sync for %s could not read the contact's tags: %s", signup.email, err)
        return False
    # Decided on every try, not only the first: when the first try saved the contact and then failed to tag it, the
    # retry is no longer "first" but zero-harm-removed is still on.
    was_removed = REMOVED_TAG in tags_now
    # The row is read (and held) only now, after the tags. Any sync of this sign-up saves the contact id before it
    # adds a tag, so if tags_now already shows the app's own tags, this read finds the contact id and does not take
    # them for tags the person had before. What is already noted is never overwritten.
    with transaction.atomic():
        row = AppSignup.objects.select_for_update().filter(pk=signup.pk).values("ghl_contact_id", "ghl_had_tags", "wants_offers").first()
        if row is None:
            return False  # removed while GoHighLevel was answering: tag nothing
        first, had, wants_offers = not row["ghl_contact_id"], row["ghl_had_tags"], row["wants_offers"]
        if first and had is None:
            had = [t for t in NEWSLETTER_TAGS if t in tags_now]
        AppSignup.objects.filter(pk=signup.pk).update(ghl_contact_id=contact_id, ghl_had_tags=had)
    signup.ghl_contact_id, signup.ghl_had_tags = contact_id, had

    tags = SIGNUP_TAGS + ([OFFERS_TAG] if wants_offers else [])
    status, body = _post(f"{GHL_API}/contacts/{contact_id}/tags", headers, {"tags": tags}, timeout=timeout)
    if 200 <= status < 300:
        try:
            if not first and not wants_offers and OFFERS_TAG not in (had or []):
                # A repeat sign-up without the offers box ticked: take the offers tag off again, unless it was theirs before.
                ghl.remove_tags(contact_id, [OFFERS_TAG], timeout=timeout)
            if was_removed:  # signing up again after a removal
                ghl.remove_tags(contact_id, [REMOVED_TAG], timeout=timeout)
        except ghl.GhlError as err:
            status, body = 0, {"error": str(err)}
    if not 200 <= status < 300:
        log.error("GHL sync for %s failed: %s %s", signup.email, status, body)
        return False
    now = timezone.now()
    if AppSignup.objects.filter(pk=signup.pk).update(ghl_synced_at=now):
        signup.ghl_synced_at = now
        return True
    # Removed while the tags were going on. The removal could not see them yet, so take ours back off here.
    ours = [t for t in NEWSLETTER_TAGS if t in tags and t not in (had or [])]
    try:
        if ours:
            ghl.remove_tags(contact_id, ours, timeout=timeout)
    except ghl.GhlError as err:
        log.error("GHL sync for a removed sign-up could not take its tags back off contact %s: %s", contact_id, err)
    return False


def feed_push_payload(item):
    """Alerts go to people with 'Regulatory alerts' on; resources are promotional, so only 'News and offers'."""
    tag = "alerts" if item.kind == item.ALERT else "offers"
    heading = "Regulatory alert" if item.kind == item.ALERT else f"New free {item.get_kind_display().replace('Free ', '').lower()}"
    if item.jurisdiction and item.kind == item.ALERT:
        heading += f" · {item.get_jurisdiction_display()}"
    return {
        "app_id": settings.ONESIGNAL_APP_ID,
        "target_channel": "push",
        "filters": [{"field": "tag", "key": tag, "relation": "=", "value": "on"}],
        "headings": {"en": heading},
        "contents": {"en": item.title},
        "data": {"feed_id": item.pk, "kind": item.kind, "refresh": True},
    }


def send_feed_push(item, dry_run=False, mark_sent=True):
    payload = feed_push_payload(item)
    if dry_run:
        return True, payload
    if not (settings.ONESIGNAL_APP_ID and settings.ONESIGNAL_REST_API_KEY):
        return False, "OneSignal is not configured."
    status, body = post_push(payload, "feed", item.pk, item.push_sent_at) if mark_sent else post_push(payload)
    if 200 <= status < 300:
        if mark_sent:
            item.push_sent_at = timezone.now()
            item.save(update_fields=["push_sent_at"])
        return True, body
    log.error("OneSignal push for feed item %s failed: %s %s", item.pk, status, body)
    return False, body


def sync_sheet_to_ghl(sheet):
    """Uploads the sign-in sheet PDF to GHL Media Storage, attaches a note to the supervisor's contact, then clears the local copy.

    Safe to repeat: the file's address is saved the moment the upload works, so when a later step fails the retry
    carries on from there instead of putting another copy of the PDF (signatures, maybe a group photo) in Media
    Storage. Making the contact and tagging it again changes nothing in GoHighLevel. The note carries a mark
    (note_mark), and every try after the first looks for it on the contact before adding the note, so a note
    GoHighLevel took without its answer arriving is not written a second time.

    Every try is counted on the sheet (attempts), before it starts, so a try cut short by a deploy counts too. The
    cron reads the count to slow down on a sheet that keeps failing and to tell the owner about it."""
    from . import ghl

    if not ghl.configured():
        return False
    type(sheet).objects.filter(pk=sheet.pk).update(attempts=F("attempts") + 1)
    sheet.attempts += 1
    try:
        url = sheet.ghl_media_url
        if not url:
            safe = "".join(c if c.isalnum() else "-" for c in sheet.talk_title)[:50].strip("-") or "talk"
            name = f"ZeroHarm-SignIn-{sheet.held_on:%Y-%m-%d}-{safe}-{sheet.pk}.pdf"
            url = sheet.ghl_media_url = ghl.upload_media(name, bytes(sheet.pdf))
            sheet.save(update_fields=["ghl_media_url"])
        contact = ghl.upsert_contact(sheet.supervisor_email, sheet.supervisor_name.split(" ")[0], sheet.company,
                                     ["zero-harm-app", "zero-harm-signin-sheet"] + (["monday-minute"] if sheet.program == "monday-minute" else []))
        mark = note_mark("sheet", sheet.pk)
        if contact and (sheet.attempts <= 1 or not _note_is_there(contact, mark, 30)):
            photo = " Group photo included." if sheet.has_group_photo else ""
            ghl.add_note(contact, (
                f"Zero Harm crew sign-in sheet\nProgram: {sheet.get_program_display()}\nTalk: {sheet.talk_title}\nDate: {sheet.held_on:%B %-d, %Y}\n"
                f"Location: {sheet.location or 'not given'}\nAttendees: {sheet.attendee_count}.{photo}\nDownload: {url}\nRef: {mark}"
            ))
        sheet.ghl_media_url, sheet.ghl_contact_id = url, contact
        sheet.status, sheet.error, sheet.synced_at, sheet.pdf = "synced", "", timezone.now(), b""
        sheet.save()
        return True
    except Exception as err:  # keep the PDF and retry on the next cron run
        sheet.status, sheet.error = "failed", str(err)[:500]
        sheet.save(update_fields=["status", "error"])
        log.error("Sign-in sheet %s to GHL failed: %s", sheet.pk, err)
        return False


def note_mark(kind, pk):
    """A short mark that goes on the last line of a note, so a retry can see that the note is already on the contact.
    It is different for every row and every server (it is made from SECRET_KEY), and plain letters and digits, so
    it reads the same however GoHighLevel lays the note out."""
    return "zh-" + hashlib.sha256(f"{settings.SECRET_KEY}:note:{kind}:{pk}".encode()).hexdigest()[:12]


def _note_is_there(contact, mark, timeout):
    """Looks for a note carrying `mark` on the contact. When GoHighLevel cannot be asked just now (no answer, 429,
    5xx) the error goes up and the whole step is tried again on the next run: waiting is better than a second note.
    When it refuses to list notes at all (the token may not be allowed to), the answer is "not there", which is how
    it worked before the look was added: a rare second note is better than an idea with none."""
    from . import ghl

    try:
        return ghl.has_note(contact, mark, timeout=timeout)
    except ghl.GhlError as err:
        if err.status == 429 or not 400 <= err.status < 500:
            raise
        log.warning("GoHighLevel would not list the notes of contact %s (%s), so a note may be added twice.", contact, err)
        return False


def sync_suggestion_to_ghl(s, budget=PHONE_BUDGET):
    """Talk ideas land on the sender's GHL contact (tagged) so a workflow can alert you. Anonymous ideas stay in the admin.

    The app's request calls this while the phone waits, and the app gives up after 10 seconds. So with a `budget`
    (seconds) each GoHighLevel call gets a few seconds at most and the three calls together never more than the
    budget. Whatever is not finished is done by the cron (retry_suggestions), which passes budget=None for the normal
    30 seconds a call. ghl_contact_id is filled in only when the note is on the contact, so blank means "not done".

    Blank can also mean "the note is on, but its answer never came back": a slow GoHighLevel can store the note and
    then be cut off by the few seconds the phone allows. Making the contact and tagging it again changes nothing, but
    a second note call makes a second note. So the note carries a mark (note_mark), and a retry looks for it on the
    contact before adding anything."""
    from . import ghl

    if not (s.email and ghl.configured()):
        return False
    deadline = time.monotonic() + budget if budget else None

    def limit():
        """Seconds the next call may take."""
        if deadline is None:
            return 30
        left = deadline - time.monotonic()
        if left < 1:
            raise ghl.GhlError("out of time while the phone waits; the cron finishes it")
        return min(QUICK, left)

    try:
        tags = ["zero-harm-app", "zero-harm-talk-suggestion"] + (["ok-to-contact"] if s.may_contact else [])
        contact = ghl.upsert_contact(s.email, s.name.split(" ")[0] if s.name else "", s.company, timeout=limit())
        if not contact:
            raise ghl.GhlError("GoHighLevel returned no contact")
        ghl.add_tags(contact, tags, timeout=limit())  # after the upsert, as in upsert_contact: never replace the contact's own tags
        mark = note_mark("idea", s.pk)
        # The request (it has a budget) is the first try for its row, so there is nothing to look for yet.
        if deadline is not None or not _note_is_there(contact, mark, limit()):
            ghl.add_note(contact, f"Toolbox talk suggestion from the Zero Harm app\nTopic: {s.topic}\nTheme: {s.month_theme or 'any'}\n"
                                  f"Details: {s.details or '(none)'}\nOK to contact: {'yes' if s.may_contact else 'no'}\nRef: {mark}", timeout=limit())
        s.ghl_contact_id = contact
        s.save(update_fields=["ghl_contact_id"])
        return True
    except Exception as err:
        log.error("Suggestion %s to GHL failed: %s", s.pk, err)
        return False


def turn(waiting, per_run, now):
    """The ids of the next `per_run` rows of a waiting list (a queryset in a fixed order). Each cron run takes the
    stretch after the one the run before took, and starts over at the end, so rows that keep failing cannot keep the
    others from ever being tried. There is no "last tried" column on these rows to sort by, so the place in the list
    comes from the clock: one step per quarter hour, which is how often the cron runs."""
    ids = list(waiting.values_list("pk", flat=True))
    if len(ids) <= per_run:
        return ids
    start = (int(now.timestamp()) // 900 * per_run) % len(ids)
    return (ids + ids)[start:start + per_run]


def retry_suggestions(now=None):
    """Cron: talk ideas with an email whose GoHighLevel step did not finish when they came in (it was down or slow, or
    not set up yet), from the last 14 days. Rows younger than 2 minutes are left alone: the request itself may still
    be at it. Returns how many were finished."""
    from . import ghl
    from .models import TalkSuggestion

    if not ghl.configured():
        return 0
    now = now or timezone.now()
    waiting = (TalkSuggestion.objects.filter(ghl_contact_id="", created_at__gte=now - timedelta(days=14), created_at__lte=now - timedelta(minutes=2))
               .exclude(email="").order_by("created_at", "pk"))
    done = 0
    for pk in turn(waiting, 20, now):
        s = TalkSuggestion.objects.filter(pk=pk, ghl_contact_id="").first()
        done += bool(s and sync_suggestion_to_ghl(s, budget=None))
    return done


def send_episode_push(ep, dry_run=False, mark_sent=True):
    """New Zero Hour episode, to devices with 'Zero Hour episodes' switched on."""
    payload = {
        "app_id": settings.ONESIGNAL_APP_ID,
        "target_channel": "push",
        "filters": [{"field": "tag", "key": "zero_hour", "relation": "=", "value": "on"}],
        "headings": {"en": f"Zero Hour · Episode {ep.number}"},
        "contents": {"en": f"{ep.title}. 5 minutes, sound on, then a 10-minute huddle."},
        "data": {"episode": ep.number, "refresh": True},
    }
    if dry_run:
        return True, payload
    if not (settings.ONESIGNAL_APP_ID and settings.ONESIGNAL_REST_API_KEY):
        return False, "OneSignal is not configured."
    status, body = post_push(payload, "episode", ep.pk, ep.push_sent_at) if mark_sent else post_push(payload)
    if 200 <= status < 300:
        if mark_sent:
            ep.push_sent_at = timezone.now()
            ep.save(update_fields=["push_sent_at"])
        return True, body
    log.error("OneSignal push for episode %s failed: %s %s", ep.number, status, body)
    return False, body


BROADCAST_TAGS = ("weekly_talk", "alerts", "zero_hour", "offers")


def broadcast_payload(audience, heading, message, route=None):
    """A one-off push from the console to everyone with ONE topic switched on. Never sent to all devices."""
    if audience not in BROADCAST_TAGS:
        raise ValueError(f"Unknown audience {audience!r}")
    return {
        "app_id": settings.ONESIGNAL_APP_ID,
        "target_channel": "push",
        "filters": [{"field": "tag", "key": audience, "relation": "=", "value": "on"}],
        "headings": {"en": heading},
        "contents": {"en": message},
        "data": {"route": route, "refresh": True},  # the app refetches content, then opens route if there is one
    }


def send_broadcast(audience, heading, message, route=None, dry_run=False):
    payload = broadcast_payload(audience, heading, message, route)
    if dry_run:
        return True, payload
    if not (settings.ONESIGNAL_APP_ID and settings.ONESIGNAL_REST_API_KEY):
        return False, "OneSignal is not configured."
    status, body = post_push(payload)
    if 200 <= status < 300:
        return True, body
    log.error("OneSignal broadcast to %s failed: %s %s", audience, status, body)
    return False, body
