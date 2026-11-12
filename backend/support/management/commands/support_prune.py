from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from support.models import CrashKey, CrashReport, Ticket

KEYS_KEPT_DAYS = 7  # how long "this report was counted" is remembered; no phone waits that long to send one again


class Command(BaseCommand):
    help = ("Deletes single crash reports older than SUPPORT_CRASH_KEEP_DAYS (default 90), and clears the phone model, "
            "system version and screen a crash ticket was first given once that first report is that old. Tickets, their "
            "error text and their counts stay. Run by the cron.")

    def handle(self, *args, **opts):
        days = settings.SUPPORT_CRASH_KEEP_DAYS
        if not isinstance(days, int) or days < 1:
            raise CommandError(f"SUPPORT_CRASH_KEEP_DAYS is {days!r}. It has to be 1 or more; nothing was deleted.")
        now = timezone.now()
        cutoff = now - timedelta(days=days)
        deleted, _ = CrashReport.objects.filter(created_at__lt=cutoff).delete()
        if deleted:
            self.stdout.write(f"Support: deleted {deleted} crash reports from before {cutoff:%Y-%m-%d}")
        # The ticket was given the first report's phone details. They go when that report would have.
        cleared = (Ticket.objects.filter(kind=Ticket.CRASH, first_seen__lt=cutoff).exclude(device="", os_version="", screen="")
                   .update(device="", os_version="", screen=""))
        if cleared:
            self.stdout.write(f"Support: cleared the phone details on {cleared} crash tickets first seen before {cutoff:%Y-%m-%d}")
        CrashKey.objects.filter(created_at__lt=now - timedelta(days=KEYS_KEPT_DAYS)).delete()
