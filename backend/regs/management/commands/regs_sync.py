from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from regs.models import RegSection
from regs.sync import sync


class Command(BaseCommand):
    help = "Refreshes the OSHA regulation library from the eCFR (weekly) and pauses what depends on amended sections."

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true", help="Sync now even if the last sync was this week")

    def handle(self, *args, force=False, **opts):
        last = RegSection.objects.order_by("-fetched_at").values_list("fetched_at", flat=True).first()
        if not force and last and last > timezone.now() - timedelta(days=7):
            return
        try:
            for line in sync():
                self.stdout.write(f"Regs: {line}")
        except Exception as err:  # eCFR down: try again on the next run
            self.stdout.write(f"Regs sync failed: {err}")
