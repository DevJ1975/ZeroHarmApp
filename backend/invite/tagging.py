"""Tags the GoHighLevel contact who tapped the invite link, so a GHL workflow can send a follow-up."""
import datetime as dt
import logging
import re

from django.utils import timezone

from talks import ghl

from .models import InviteClick

log = logging.getLogger(__name__)
TAG = "zero-harm-invite-clicked"
RETRY_DAYS = 2
# GoHighLevel contact ids are 20 letters and digits today. Allow some room, and nothing else, so junk never gets
# stored. Always use it with fullmatch: with match, "$" also matches just before a line break at the end.
CONTACT_ID = re.compile(r"[A-Za-z0-9]{10,40}")


def _no_such_contact(err):
    """GoHighLevel says the contact isn't there (deleted, merged, or a made-up id in the link). Retrying won't help.
    Sign-in, permission and rate-limit answers (401, 403, 429) are worth another try."""
    return 400 <= err.status < 500 and err.status not in (401, 403, 408, 429)


def tag_click(click, timeout=10):
    """Adds the tag. Returns True when the click needs nothing more (tagged, or no such contact). Never raises: the
    visitor is waiting for the page, and the cron has other work after this."""
    if not ghl.configured():
        return False
    if not CONTACT_ID.fullmatch(click.contact_id):
        # A stored id that could never be a contact (one with a line break got in before the check was fixed). There
        # is nothing to tag, and asking GoHighLevel would fail the same way on every run, so the click is closed.
        missing = True
    else:
        try:
            ghl.add_tags(click.contact_id, [TAG], timeout=timeout)
            missing = False
        except ghl.GhlError as err:
            if not _no_such_contact(err):
                log.warning("Invite tag for contact %s failed: %s", click.contact_id, err)
                return False
            missing = True
        except Exception as err:
            # Anything else (an address Python's HTTP client refuses, say). It used to escape: the visitor got a 500,
            # and the cron stopped at this click on every run for 2 days, skipping everything it does afterwards.
            log.error("Invite tag for click %s failed in a way nobody expected: %r", click.pk, err)
            return False
    InviteClick.objects.filter(pk=click.pk).update(tagged_at=timezone.now(), contact_missing=missing)
    return True


def retry_tags(limit=50):
    """For the cron: tag the clicks from the last 2 days that GoHighLevel didn't take the first time."""
    if not ghl.configured():
        return 0
    since = timezone.now() - dt.timedelta(days=RETRY_DAYS)
    waiting = InviteClick.objects.filter(tagged_at__isnull=True, created_at__gte=since).order_by("created_at")[:limit]
    done = 0
    for click in waiting:
        try:
            done += bool(tag_click(click))
        except Exception as err:  # one click that cannot be handled must not stop the ones after it, or the cron
            log.error("Invite tag retry for click %s failed: %r", click.pk, err)
    return done
