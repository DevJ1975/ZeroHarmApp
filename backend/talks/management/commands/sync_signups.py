from django.core.management.base import BaseCommand

from talks.integrations import sync_signup_to_ghl
from talks.models import AppSignup


class Command(BaseCommand):
    help = "Retries GoHighLevel sync for any sign-ups that have not synced yet."

    def handle(self, *args, **opts):
        pending = AppSignup.objects.filter(ghl_synced_at__isnull=True)
        synced = sum(sync_signup_to_ghl(s) for s in pending)
        self.stdout.write(f"Synced {synced} of {pending.count() + synced} pending sign-ups.")
