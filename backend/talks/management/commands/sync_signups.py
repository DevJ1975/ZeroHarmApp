import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from talks.integrations import sync_signup_to_ghl
from talks.models import AppSignup

log = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Retries GoHighLevel sync for any sign-ups that have not synced yet."

    def add_arguments(self, parser):
        parser.add_argument("--min-age", type=int, default=0, metavar="MINUTES",
                            help="Leave sign-ups younger than this alone. The cron passes 2: the sign-up's own request may still be syncing it.")

    def handle(self, *args, min_age=0, **opts):
        pending = AppSignup.objects.filter(ghl_synced_at__isnull=True)
        if min_age:
            pending = pending.filter(created_at__lte=timezone.now() - timedelta(minutes=min_age))
        synced = tried = 0
        for signup in pending:
            tried += 1
            try:
                synced += bool(sync_signup_to_ghl(signup))
            except Exception:  # one sign-up that cannot be synced must not keep the others waiting
                log.exception("GHL sync for sign-up %s failed", signup.pk)
        self.stdout.write(f"Synced {synced} of {tried} pending sign-ups.")
