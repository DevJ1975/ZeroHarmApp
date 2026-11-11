from datetime import timedelta

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone

from invite.tagging import retry_tags as retry_invite_tags
from talks import owner_alerts
from talks.ghl_sync import sync_year
from talks.integrations import send_episode_push, send_feed_push, sync_sheet_to_ghl
from talks.models import Episode, FeedItem, GhlSync, SigninSheet
from talks.zero_hour import sync_episodes


class Command(BaseCommand):
    help = "Runs every 15 minutes on Railway: due pushes, queued GHL year syncs, and retries."

    def handle(self, *args, **opts):
        call_command("send_talk_push")

        now = timezone.now()
        # Live items only (no early grace): the push makes phones refetch, so it must not land before the item shows.
        due = FeedItem.objects.released().filter(send_push=True, push_sent_at__isnull=True, publish_at__gte=now - timedelta(days=1))
        for item in due:
            ok, detail = send_feed_push(item)
            self.stdout.write(f"Feed push {item.pk} {item.title}: {'OK' if ok else 'FAILED'} {'' if ok else detail}")

        for job in GhlSync.objects.filter(status="pending")[:2]:
            try:
                lines = sync_year(job.year)
                job.status = "done"
            except Exception as err:  # keep the error visible in the admin
                lines, job.status = [f"Failed: {err}"], "failed"
            job.log, job.finished_at = "\n".join(lines), timezone.now()
            job.save()
            self.stdout.write(f"GHL sync {job.year}: {job.status}")

        # Zero Hour: look for new episode files in GHL once an hour, and push any episode that just released.
        if now.minute < 15:
            try:
                for line in sync_episodes():
                    self.stdout.write(f"Zero Hour sync: {line}")
            except Exception as err:
                self.stdout.write(f"Zero Hour sync failed: {err}")
        for ep in Episode.objects.released().filter(send_push=True, push_sent_at__isnull=True, release_at__gte=now - timedelta(days=1)):
            ok, detail = send_episode_push(ep)
            self.stdout.write(f"Episode {ep.number} push: {'OK' if ok else detail}")

        for sheet in SigninSheet.objects.exclude(status="synced").filter(created_at__gte=now - timedelta(days=14))[:20]:
            sync_sheet_to_ghl(sheet)

        call_command("sync_signups")
        # Emails to the owner: sign-up alerts and removals that did not go out the first time, then the daily summary.
        alerts, removals = owner_alerts.retry_signup_alerts(), owner_alerts.retry_removals()
        if alerts or removals:
            self.stdout.write(f"Owner alerts: {alerts} sign-up alerts sent late, {removals} removals finished")
        tagged = retry_invite_tags()  # invite-link taps GoHighLevel didn't tag the first time, from the last 2 days
        if tagged:
            self.stdout.write(f"Invite link: {tagged} taps tagged late")
        call_command("owner_digest")
        call_command("regs_sync")  # weekly; pauses topics and OTIS entries if OSHA changes a cited rule
        call_command("monday_minute")
        if now.minute < 15:  # hourly is plenty: one small delete of anonymous app-open rows past USAGE_KEEP_DAYS
            call_command("usage_prune")
