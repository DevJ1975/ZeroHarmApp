import logging

from django.conf import settings
from django.utils import timezone

from talks.integrations import _post

log = logging.getLogger(__name__)


def send_minute_push(minute, dry_run=False):
    """Monday's talk, to devices with 'Monday Minute' switched on."""
    payload = {
        "app_id": settings.ONESIGNAL_APP_ID,
        "target_channel": "push",
        "filters": [{"field": "tag", "key": "monday_minute", "relation": "=", "value": "on"}],
        "headings": {"en": "Monday Minute"},
        "contents": {"en": f"{minute.title}. A 5-minute talk for your crew, with sign-in."},
        "data": {"monday_minute": minute.pk},
    }
    if dry_run:
        return True, payload
    if not (settings.ONESIGNAL_APP_ID and settings.ONESIGNAL_REST_API_KEY):
        return False, "OneSignal is not configured."
    status, body = _post("https://api.onesignal.com/notifications?c=push", {"Authorization": f"Key {settings.ONESIGNAL_REST_API_KEY}"}, payload)
    if 200 <= status < 300:
        minute.push_sent_at = timezone.now()
        minute.save(update_fields=["push_sent_at"])
        return True, body
    log.error("Monday Minute push %s failed: %s %s", minute.pk, status, body)
    return False, body
