from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from monday.api import screen_pending
from monday.generate import due_week, generate_week
from monday.models import MondayMinute
from monday.push import send_minute_push


class Command(BaseCommand):
    help = "Cron step for Monday Minute: write next week's talk when due, push Monday's, screen held comments."

    def add_arguments(self, parser):
        parser.add_argument("--week", help="Write this Monday's talk now (YYYY-MM-DD)")

    def handle(self, *args, week=None, **opts):
        if not settings.MONDAY_MINUTE_ENABLED:
            self.stdout.write("Monday Minute is off (MONDAY_MINUTE_ENABLED=0).")
            return
        target = timezone.datetime.fromisoformat(week).date() if week else due_week()
        if target and not settings.ANTHROPIC_API_KEY:
            self.stdout.write("Monday Minute: ANTHROPIC_API_KEY is not set, so nothing was written.")
        elif target:
            try:
                m = generate_week(target)
                self.stdout.write(f"Monday Minute {target}: {m.get_status_display() if m else 'nothing to do'}")
            except Exception as err:  # API outage: try again on the next run
                self.stdout.write(f"Monday Minute {target}: could not write it ({err}). Will retry.")
        now = timezone.now()
        for m in MondayMinute.objects.released().filter(push_sent_at__isnull=True, publish_at__gte=now - timedelta(hours=12)):
            ok, detail = send_minute_push(m)
            self.stdout.write(f"Monday Minute push {m.week}: {'OK' if ok else detail}")
        if settings.ANTHROPIC_API_KEY:
            n = screen_pending()
            if n:
                self.stdout.write(f"Screened {n} held comment(s).")
