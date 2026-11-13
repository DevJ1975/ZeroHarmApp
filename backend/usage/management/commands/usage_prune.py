from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from usage.models import AppOpen


class Command(BaseCommand):
    help = "Deletes anonymous app-open rows older than USAGE_KEEP_DAYS (default 400). Run by the cron."

    def handle(self, *args, **opts):
        cutoff = timezone.localdate() - timedelta(days=settings.USAGE_KEEP_DAYS)
        deleted, _ = AppOpen.objects.filter(day__lt=cutoff).delete()
        if deleted:
            self.stdout.write(f"Usage: deleted {deleted} app-open rows from before {cutoff}")
