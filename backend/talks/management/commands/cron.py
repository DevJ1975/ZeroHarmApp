from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Everything the Railway cron service runs: the Sunday push, then any pending GoHighLevel syncs."

    def handle(self, *args, **opts):
        call_command("send_talk_push")
        call_command("sync_signups")
