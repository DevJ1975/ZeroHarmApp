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
