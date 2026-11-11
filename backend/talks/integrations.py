"""OneSignal push and GoHighLevel contact sync. Standard library only, so no extra dependencies."""
import json
import logging
import urllib.error
import urllib.request

from django.conf import settings
from django.utils import timezone

log = logging.getLogger(__name__)


def _post(url, headers, payload, timeout=10):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Accept": "application/json", **headers},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return res.status, json.loads(res.read() or b"{}")
    except urllib.error.HTTPError as err:
        return err.code, {"error": err.read().decode(errors="replace")[:500]}
    except (urllib.error.URLError, TimeoutError) as err:
        return 0, {"error": str(err)}


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
    status, body = _post(
        "https://api.onesignal.com/notifications?c=push",
        {"Authorization": f"Key {settings.ONESIGNAL_REST_API_KEY}"},
        payload,
    )
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

    The first time, it also notes which newsletter tags the contact already had, so a removal later leaves those on,
    and takes zero-harm-removed off if they had removed an earlier sign-up. The sign-up can be removed while this runs,
    so it checks the row is still there before tagging, and takes its own tags back off if the row went meanwhile."""
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

    first = not signup.ghl_contact_id
    had, was_removed = signup.ghl_had_tags, False
    if first:
        try:
            tags_now = contact["tags"] if isinstance(contact.get("tags"), list) else ghl.contact_tags(contact_id, timeout=timeout)
        except ghl.GhlError as err:
            log.error("GHL sync for %s could not read the contact's tags: %s", signup.email, err)
            return False
        if had is None:
            had = [t for t in NEWSLETTER_TAGS if t in tags_now]
        was_removed = REMOVED_TAG in tags_now
    if not AppSignup.objects.filter(pk=signup.pk).update(ghl_contact_id=contact_id, ghl_had_tags=had):
        return False  # removed while GoHighLevel was answering: tag nothing
    signup.ghl_contact_id, signup.ghl_had_tags = contact_id, had

    tags = SIGNUP_TAGS + ([OFFERS_TAG] if signup.wants_offers else [])
    status, body = _post(f"{GHL_API}/contacts/{contact_id}/tags", headers, {"tags": tags}, timeout=timeout)
    if 200 <= status < 300:
        try:
            if not first and not signup.wants_offers and OFFERS_TAG not in (had or []):
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
    status, body = _post("https://api.onesignal.com/notifications?c=push", {"Authorization": f"Key {settings.ONESIGNAL_REST_API_KEY}"}, payload)
    if 200 <= status < 300:
        if mark_sent:
            item.push_sent_at = timezone.now()
            item.save(update_fields=["push_sent_at"])
        return True, body
    log.error("OneSignal push for feed item %s failed: %s %s", item.pk, status, body)
    return False, body


def sync_sheet_to_ghl(sheet):
    """Uploads the sign-in sheet PDF to GHL Media Storage, attaches a note to the supervisor's contact, then clears the local copy."""
    from . import ghl

    if not ghl.configured():
        return False
    try:
        safe = "".join(c if c.isalnum() else "-" for c in sheet.talk_title)[:50].strip("-") or "talk"
        name = f"ZeroHarm-SignIn-{sheet.held_on:%Y-%m-%d}-{safe}-{sheet.pk}.pdf"
        url = ghl.upload_media(name, bytes(sheet.pdf))
        contact = ghl.upsert_contact(sheet.supervisor_email, sheet.supervisor_name.split(" ")[0], sheet.company,
                                     ["zero-harm-app", "zero-harm-signin-sheet"] + (["monday-minute"] if sheet.program == "monday-minute" else []))
        if contact:
            photo = " Group photo included." if sheet.has_group_photo else ""
            ghl.add_note(contact, (
                f"Zero Harm crew sign-in sheet\nProgram: {sheet.get_program_display()}\nTalk: {sheet.talk_title}\nDate: {sheet.held_on:%B %-d, %Y}\n"
                f"Location: {sheet.location or 'not given'}\nAttendees: {sheet.attendee_count}.{photo}\nDownload: {url}"
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


def sync_suggestion_to_ghl(s):
    """Talk ideas land on the sender's GHL contact (tagged) so a workflow can alert you. Anonymous ideas stay in the admin."""
    from . import ghl

    if not (s.email and ghl.configured()):
        return False
    try:
        tags = ["zero-harm-app", "zero-harm-talk-suggestion"] + (["ok-to-contact"] if s.may_contact else [])
        contact = ghl.upsert_contact(s.email, s.name.split(" ")[0] if s.name else "", s.company, tags)
        if contact:
            ghl.add_note(contact, f"Toolbox talk suggestion from the Zero Harm app\nTopic: {s.topic}\nTheme: {s.month_theme or 'any'}\n"
                                  f"Details: {s.details or '(none)'}\nOK to contact: {'yes' if s.may_contact else 'no'}")
        s.ghl_contact_id = contact
        s.save(update_fields=["ghl_contact_id"])
        return True
    except Exception as err:
        log.error("Suggestion %s to GHL failed: %s", s.pk, err)
        return False


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
    status, body = _post("https://api.onesignal.com/notifications?c=push", {"Authorization": f"Key {settings.ONESIGNAL_REST_API_KEY}"}, payload)
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
    status, body = _post("https://api.onesignal.com/notifications?c=push", {"Authorization": f"Key {settings.ONESIGNAL_REST_API_KEY}"}, payload)
    if 200 <= status < 300:
        return True, body
    log.error("OneSignal broadcast to %s failed: %s %s", audience, status, body)
    return False, body
