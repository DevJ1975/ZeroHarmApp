from django.core.management.base import BaseCommand

from talks.owner_alerts import send_due_digests


class Command(BaseCommand):
    help = "Emails the owner yesterday's new phones and sign-ups, once a day after 7:00 AM Pacific. Run by the cron."

    def handle(self, *args, **opts):
        for line in send_due_digests():
            self.stdout.write(line)
