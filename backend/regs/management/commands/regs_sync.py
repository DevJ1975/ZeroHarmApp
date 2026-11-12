from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Max
from django.utils import timezone

from regs.models import RegSection
from regs.sync import sync


class Command(BaseCommand):
    help = "Refreshes the OSHA regulation library from the eCFR (weekly) and pauses what depends on amended sections."

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true", help="Sync now even if the last sync was this week")

    def handle(self, *args, force=False, **opts):
        # The newest fetch time of any section. Max leaves out sections that were never fetched. Sorting newest-first
        # and taking the first row did not: PostgreSQL puts empty values first there, so one section that had failed
        # to download made this look like "never synced" and every cron run (every 15 minutes) did a full sync.
        last = RegSection.objects.aggregate(last=Max("fetched_at"))["last"]
        # Everything on file: once a week. While a section is still missing, once a day, so the library is not left
        # without a cited rule for a whole week.
        missing = RegSection.objects.filter(fetched_at__isnull=True).exists()
        if not force and last and last > timezone.now() - timedelta(days=1 if missing else 7):
            return
        try:
            for line in sync():
                self.stdout.write(f"Regs: {line}")
        except Exception as err:  # eCFR down: try again on the next run
            self.stdout.write(f"Regs sync failed: {err}")
