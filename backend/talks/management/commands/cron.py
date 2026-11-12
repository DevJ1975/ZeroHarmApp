import logging
import threading
from datetime import timedelta

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.models import F, Q
from django.utils import timezone

from invite.tagging import retry_tags as retry_invite_tags
from talks import ghl, owner_alerts
from talks.ghl_sync import sync_year
from talks.integrations import retry_suggestions, send_episode_push, send_feed_push, sync_sheet_to_ghl, turn
from talks.models import Episode, FeedItem, GhlSync, SigninSheet
from talks.zero_hour import sync_episodes

log = logging.getLogger(__name__)
PUSH_EVERY = 15 * 60                 # seconds between push passes while the slow steps of one run are still going
ZERO_HOUR_LOOK = 10                  # seconds a listing call of the hourly Zero Hour look may take: episode pushes wait behind it
SHEET_GRACE = timedelta(minutes=5)   # the app's own upload of a sheet can take a few minutes: leave it alone until then
SHEETS_PER_RUN = 20
SHEET_FAST_TRIES = 8                 # a sheet is tried on every run for its first tries (about two hours), then the owner is told
SHEET_SLOW_EVERY = 16                # and after that on one run in 16 (every 4 hours) until it is 14 days old


class Command(BaseCommand):
    help = "Runs every 15 minutes on Railway: due pushes, queued GHL year syncs, and retries."

    def handle(self, *args, **opts):
        self.failed = []
        now = timezone.now()
        # First: these are the steps with a clock on them. Once an hour the look for new Zero Hour files goes with them.
        self.pushes(zero_hour=now.minute < 15)

        # Railway skips a scheduled run while the one before is still going, and the steps below can be slow (a Monday
        # Minute write on the CPU model can take hours). Pushes that come due meanwhile must not wait for it, so until
        # this run ends they are sent from here every 15 minutes, exactly as a new run would.
        done = threading.Event()
        pusher = threading.Thread(target=self.keep_pushing, args=(done,), daemon=True)
        pusher.start()
        try:
            self.step("Safety test runs", self.stale_safety_tests)
            for job in self.step("GHL year syncs", lambda: list(GhlSync.objects.filter(status="pending")[:2])) or []:
                self.step(f"GHL sync {job.year}", self.year_sync, job)
            self.step("Sign-in sheets", self.sheets, now)
            # Sign-ups younger than 2 minutes are left to their own request, which may still be syncing them.
            self.step("sync_signups", call_command, "sync_signups", min_age=2)
            self.step("Talk suggestions", retry_suggestions)
            # Emails to the owner: sign-up alerts and removals that did not go out the first time, then the daily summary.
            alerts = self.step("Owner sign-up alerts", owner_alerts.retry_signup_alerts)
            removals = self.step("Removals", owner_alerts.retry_removals)
            if alerts or removals:
                self.stdout.write(f"Owner alerts: {alerts or 0} sign-up alerts sent late, {removals or 0} removals finished")
            self.step("Removal request notices", self.removal_request_notices)
            tagged = self.step("Invite link tags", retry_invite_tags)  # taps GoHighLevel didn't tag the first time, last 2 days
            if tagged:
                self.stdout.write(f"Invite link: {tagged} taps tagged late")
            self.step("owner_digest", call_command, "owner_digest")
            self.step("regs_sync", call_command, "regs_sync")  # weekly; pauses topics and OTIS entries if OSHA changes a cited rule
            self.step("monday_minute", call_command, "monday_minute")
            if now.minute < 15:  # hourly is plenty: one small delete of anonymous app-open rows past USAGE_KEEP_DAYS
                self.step("usage_prune", call_command, "usage_prune")
        finally:
            done.set()
            pusher.join()
        if self.failed:
            # Every step has run. The exit code is non-zero so the run shows as failed in Railway instead of looking fine.
            raise CommandError(f"Cron finished, but {len(self.failed)} step(s) failed: {', '.join(self.failed)}. Tracebacks are in the log above.")

    def step(self, name, run, *args, **kwargs):
        """Runs one step and gives back its result. A step that raises is written to the log with its traceback and
        remembered for the exit code; the steps after it still run. Before this, the first error ended the whole run,
        so one bad answer from OneSignal or GoHighLevel skipped everything behind it, every 15 minutes."""
        try:
            return run(*args, **kwargs)
        except Exception:
            log.exception("Cron step '%s' failed. The other steps still run.", name)
            self.stdout.write(f"{name}: FAILED (traceback in the log)")
            self.failed.append(name)
            return None

    def pushes(self, zero_hour=False):
        """Everything with a send time: the weekly talk, feed alerts, Monday Minute and Zero Hour episodes. Each push
        is its own step, and each one is marked sent the moment OneSignal takes it, so running this again sends
        nothing twice."""
        self.step("send_talk_push", call_command, "send_talk_push")
        now = timezone.now()
        # Live items only (no early grace): the push makes phones refetch, so it must not land before the item shows.
        due = FeedItem.objects.released().filter(send_push=True, push_sent_at__isnull=True, publish_at__gte=now - timedelta(days=1))
        for item in self.step("Feed pushes", list, due) or []:
            self.step(f"Feed push {item.pk}", self.feed_push, item)
        # Monday's talk. The monday_minute step near the end of the run sends it too, but that step sits behind the
        # slow ones and can itself be hours into a write; from here the push goes out on time either way.
        self.step("Monday Minute pushes", self.monday_pushes)
        if zero_hour:
            # Zero Hour: look for new episode files in GoHighLevel once an hour. Before the episode pushes, where it
            # was before the pushes moved to the front of the run: the push makes phones refetch, and a video or
            # huddle card this look links should be on the episode when they do. The look is a listing call or two
            # with a short time limit, and when it fails or times out the pushes below still go out.
            self.step("Zero Hour sync", self.zero_hour)
        due = Episode.objects.released().filter(send_push=True, push_sent_at__isnull=True, release_at__gte=now - timedelta(days=1))
        for ep in self.step("Episode pushes", list, due) or []:
            self.step(f"Episode {ep.number} push", self.episode_push, ep)

    def feed_push(self, item):
        ok, detail = send_feed_push(item)
        self.stdout.write(f"Feed push {item.pk} {item.title}: {'OK' if ok else 'FAILED'} {'' if ok else detail}")

    def episode_push(self, ep):
        ok, detail = send_episode_push(ep)
        self.stdout.write(f"Episode {ep.number} push: {'OK' if ok else detail}")

    def monday_pushes(self):
        from monday.push import send_due  # here, not at the top: a fault in that module is then one failed step

        for line in send_due():  # the safety gate's last word on talks that reached their publish time, then their push
            self.stdout.write(line)

    def keep_pushing(self, done):
        """Runs beside the slow steps (see handle): a push pass every PUSH_EVERY seconds until the run is over."""
        while not done.wait(PUSH_EVERY):
            try:
                self.pushes()
            finally:
                connection.close()  # this thread's own database connection; the next pass opens a new one

    def stale_safety_tests(self):
        """A Monday Minute safety test runs inside the web server, so a deploy or restart stops it without a word.
        The admin marks such a run as failed when someone opens the runs list; this does the same every 15 minutes,
        so the row does not go on saying "Running" until somebody looks."""
        from monday.eval_runner import close_stale_runs  # here, not at the top: a fault in that module is then one failed step

        closed = close_stale_runs()
        if closed:
            self.stdout.write(f"Monday Minute: {closed} safety test run(s) marked as failed, the server stopped while they ran.")

    def year_sync(self, job):
        try:
            lines = sync_year(job.year)
            job.status = "done"
        except ghl.NotConfigured as err:
            # Nothing was read, so this is not "done". The job stays pending and runs once the settings are there.
            job.log = str(err)
            job.save(update_fields=["log"])
            self.stdout.write(f"GHL sync {job.year}: waiting, GoHighLevel is not configured")
            return
        except Exception as err:  # keep the error visible in the admin
            lines, job.status = [f"Failed: {err}"], "failed"
        job.log, job.finished_at = "\n".join(lines), timezone.now()
        job.save()
        self.stdout.write(f"GHL sync {job.year}: {job.status}")

    def zero_hour(self):
        try:
            for line in sync_episodes(timeout=ZERO_HOUR_LOOK):
                self.stdout.write(f"Zero Hour sync: {line}")
        except Exception as err:
            self.stdout.write(f"Zero Hour sync failed: {err}")

    def removal_request_notices(self):
        """Removal requests the server did not carry out by itself (talks/views.py): the owner is emailed about each
        one once. This sends the ones whose email could not go out when the person asked."""
        from talks.views import retry_removal_request_notices  # here, not at the top: a fault there is then one failed step

        retry_removal_request_notices()

    def sheets(self, now):
        """Sign-in sheets from the last 14 days that are not in GoHighLevel yet, oldest first, 20 a run.

        A sheet is tried on every run for its first SHEET_FAST_TRIES tries. One that still fails then (GoHighLevel
        refuses that contact or that file, or has been down for hours) is tried on one run in SHEET_SLOW_EVERY: about
        90 tries in its 14 days where there used to be over 1,300, and it still goes through by itself once whatever
        was wrong is put right. The runs are spread by the sheet's number, so stuck sheets do not all come up at once."""
        slot = int(now.timestamp()) // 900 % SHEET_SLOW_EVERY
        waiting = (SigninSheet.objects.exclude(status="synced")
                   .filter(created_at__gte=now - timedelta(days=14), created_at__lte=now - SHEET_GRACE)
                   .annotate(slot=F("pk") % SHEET_SLOW_EVERY).filter(Q(attempts__lt=SHEET_FAST_TRIES) | Q(slot=slot))
                   .order_by("created_at", "pk"))
        for pk in turn(waiting, SHEETS_PER_RUN, now):
            sheet = SigninSheet.objects.filter(pk=pk).exclude(status="synced").first()  # as it is now, with its PDF
            if sheet:
                self.step(f"Sign-in sheet {pk}", self.sheet, sheet)

    def sheet(self, sheet):
        if sync_sheet_to_ghl(sheet) or sheet.attempts < SHEET_FAST_TRIES:
            return
        # A crew's sign-in sheet is a record somebody may be asked for. One that will not go through must not sit
        # unnoticed as "Failed" in the admin: the owner gets one email (notify sends it once per sheet).
        owner_alerts.notify(
            f"Zero Harm sign-in sheet not saved to GoHighLevel: {sheet.talk_title or 'no title'}",
            [f"Sign-in sheet {sheet.pk}: {sheet.talk_title or 'no title'}, held {sheet.held_on:%B %-d, %Y}, "
             f"sent by {sheet.supervisor_name} ({sheet.supervisor_email}).",
             f"GoHighLevel has not taken it after {sheet.attempts} tries. The last error: {sheet.error[:300] or 'none recorded'}",
             "The sheet and its PDF are safe on the app's server. The server keeps trying by itself about every 4 hours until the "
             "sheet is 14 days old.",
             "To try it by hand: admin, Sign-in sheets, tick the sheet, choose 'Retry saving to GoHighLevel'."],
            key=f"sheet-stuck:{sheet.pk}", timeout=30)
