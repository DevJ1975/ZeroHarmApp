from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from talks.integrations import send_talk_push
from talks.models import ToolboxTalk


class Command(BaseCommand):
    help = "Sends the weekly push for any talk that is due and not yet sent. Safe to run repeatedly."

    def add_arguments(self, parser):
        parser.add_argument("--issue", type=int, help="Send this issue now, even if it was sent before")
        parser.add_argument("--dry-run", action="store_true", help="Show the payload without sending")

    def handle(self, *args, issue=None, dry_run=False, **opts):
        now = timezone.now()
        if issue:
            talks = ToolboxTalk.objects.filter(issue=issue)
        else:
            # Only once the talk is live in the app (no early grace: the push makes phones refetch right away,
            # so it must not land before the talk shows). Held talks wait; skip anything over a day late.
            talks = ToolboxTalk.objects.filter(
                published=True,
                needs_review=False,
                push_sent_at__isnull=True,
                send_at__lte=now,
                send_at__gte=now - timedelta(days=1),
            )
        if not talks:
            self.stdout.write("No talk is due.")
        for talk in talks:
            ok, detail = send_talk_push(talk, dry_run=dry_run)
            self.stdout.write(f"Issue {talk.issue}: {'OK' if ok else 'FAILED'} {detail}")
