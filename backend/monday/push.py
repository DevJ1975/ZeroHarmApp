import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from talks.integrations import post_push

log = logging.getLogger(__name__)
PUSH_WINDOW = timedelta(hours=12)  # a talk that has been out longer than this without its push no longer gets one


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
    # Through post_push, which gives the request an idempotency key that stays the same from one try to the next.
    # The cron sends this push again every 15 minutes until it is marked sent below. When OneSignal took it but its
    # answer was lost (a timeout, a dropped connection) it is not marked, and without the key every retry was
    # delivered: the same notification on every phone, run after run, for up to 12 hours.
    status, body = post_push(payload, "monday", minute.pk, minute.push_sent_at)
    if 200 <= status < 300:
        minute.push_sent_at = timezone.now()
        minute.save(update_fields=["push_sent_at"])
        return True, body
    log.error("Monday Minute push %s failed: %s %s", minute.pk, status, body)
    return False, body


def due_pushes(now=None):
    """Talks that are out in the app and have not had their push yet."""
    from .models import MondayMinute

    now = now or timezone.now()
    return MondayMinute.objects.released().filter(push_sent_at__isnull=True, publish_at__gte=now - PUSH_WINDOW)


def send_due(now=None) -> list[str]:
    """The Monday Minute part of a push pass, for a caller outside the monday_minute step (the cron's own push pass,
    which runs every 15 minutes beside its slow steps): the safety gate has its last word on talks that have reached
    their publish time, then every talk that is out gets its push. No AI call, so it is quick. Safe to run while the
    step itself is pushing: both use the same idempotency key, so OneSignal delivers once. Returns one line per
    thing done, for the cron output."""
    from . import gate

    now = now or timezone.now()
    lines = []
    held = gate.hold_unpublished(now) + gate.release_due(now)[1]
    if held:
        lines.append(f"Monday Minute: {held} talk(s) moved back to waiting for approval. The AI setup no longer has a passing safety test.")
    if not settings.MONDAY_MINUTE_ENABLED:
        return lines  # the gate still speaks when writing is off; pushes do not go out
    for m in due_pushes(now):
        ok, detail = send_minute_push(m)
        lines.append(f"Monday Minute push {m.week}: {'OK' if ok else detail}")
    return lines
