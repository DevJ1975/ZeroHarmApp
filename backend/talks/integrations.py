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
        "data": {"issue": talk.issue},  # the app opens /talk/<issue> when tapped
    }


def send_talk_push(talk, dry_run=False):
    """Sends the weekly push to devices with weekly_talk = on. Returns (ok, detail)."""
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
        talk.push_sent_at = timezone.now()
        talk.save(update_fields=["push_sent_at"])
        return True, body
    log.error("OneSignal push for issue %s failed: %s %s", talk.issue, status, body)
    return False, body


def sync_signup_to_ghl(signup):
    """Upserts the contact into GoHighLevel with app-specific tags. Returns True when synced."""
    if not (settings.GHL_PRIVATE_TOKEN and settings.GHL_LOCATION_ID):
        return False
    tags = ["zero-harm-app", "zero-harm-weekly"]
    if signup.wants_offers:
        tags.append("zero-harm-offers-optin")
    payload = {
        "locationId": settings.GHL_LOCATION_ID,
        "email": signup.email,
        "tags": tags,
        "source": "Zero Harm app",
    }
    if signup.first_name:
        payload["firstName"] = signup.first_name
    if signup.company:
        payload["companyName"] = signup.company
    status, body = _post(
        "https://services.leadconnectorhq.com/contacts/upsert",
        {"Authorization": f"Bearer {settings.GHL_PRIVATE_TOKEN}", "Version": "2021-07-28"},
        payload,
    )
    if 200 <= status < 300:
        signup.ghl_contact_id = (body.get("contact") or {}).get("id", "")[:40]
        signup.ghl_synced_at = timezone.now()
        signup.save(update_fields=["ghl_contact_id", "ghl_synced_at"])
        return True
    log.error("GHL sync for %s failed: %s %s", signup.email, status, body)
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
        "data": {"feed_id": item.pk, "kind": item.kind},
    }


def send_feed_push(item, dry_run=False):
    payload = feed_push_payload(item)
    if dry_run:
        return True, payload
    if not (settings.ONESIGNAL_APP_ID and settings.ONESIGNAL_REST_API_KEY):
        return False, "OneSignal is not configured."
    status, body = _post("https://api.onesignal.com/notifications?c=push", {"Authorization": f"Key {settings.ONESIGNAL_REST_API_KEY}"}, payload)
    if 200 <= status < 300:
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
        contact = ghl.upsert_contact(sheet.supervisor_email, sheet.supervisor_name.split(" ")[0], sheet.company, ["zero-harm-app", "zero-harm-signin-sheet"])
        if contact:
            photo = " Group photo included." if sheet.has_group_photo else ""
            ghl.add_note(contact, (
                f"Zero Harm crew sign-in sheet\nTalk: {sheet.talk_title}\nDate: {sheet.held_on:%B %-d, %Y}\n"
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
