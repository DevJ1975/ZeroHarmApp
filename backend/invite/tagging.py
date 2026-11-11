"""Tags the GoHighLevel contact who tapped the invite link, so a GHL workflow can send a follow-up."""
import datetime as dt
import logging

from django.utils import timezone

from talks import ghl

from .models import InviteClick

log = logging.getLogger(__name__)
TAG = "zero-harm-invite-clicked"
RETRY_DAYS = 2


def _no_such_contact(err):
    """GoHighLevel says the contact isn't there (deleted, merged, or a made-up id in the link). Retrying won't help.
    Sign-in, permission and rate-limit answers (401, 403, 429) are worth another try."""
    return 400 <= err.status < 500 and err.status not in (401, 403, 408, 429)


def tag_click(click, timeout=10):
    """Adds the tag. Returns True when the click needs nothing more (tagged, or no such contact)."""
    if not ghl.configured():
        return False
    try:
        ghl.add_tags(click.contact_id, [TAG], timeout=timeout)
        missing = False
    except ghl.GhlError as err:
        if not _no_such_contact(err):
            log.warning("Invite tag for contact %s failed: %s", click.contact_id, err)
            return False
        missing = True
    InviteClick.objects.filter(pk=click.pk).update(tagged_at=timezone.now(), contact_missing=missing)
    return True


def retry_tags(limit=50):
    """For the cron: tag the clicks from the last 2 days that GoHighLevel didn't take the first time."""
    if not ghl.configured():
        return 0
    since = timezone.now() - dt.timedelta(days=RETRY_DAYS)
    waiting = InviteClick.objects.filter(tagged_at__isnull=True, created_at__gte=since).order_by("created_at")[:limit]
    return sum(tag_click(c) for c in waiting)
