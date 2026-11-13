import logging
from datetime import date, timedelta

from django.conf import settings
from django.core.cache import caches
from django.core.management.base import BaseCommand
from django.utils import timezone

from monday import ai, gate
from monday.api import screen_pending
from monday.eval_runner import close_stale_runs
from monday.generate import NO_ANSWER, due_week, generate_week, is_late, missed_week, next_week, note_attempt
from monday.models import MondayLock, MondayMinute
from monday.push import due_pushes, send_minute_push

log = logging.getLogger(__name__)

# The share of the step's AI time (MONDAY_STEP_BUDGET) that waiting comments may use. They are screened before the
# write so a long write cannot keep them back, but with one shared ceiling a queue of comments (up to 20, three minutes
# each) could use all of it and leave the write nothing, run after run. Comments not reached wait for the next run.
COMMENT_SHARE = 0.2
COMMENT_SHARE_MAX = 0.5  # with a small ceiling the share is stretched to fit one whole comment check, up to this much
PULLED_BY_CREWS = "Paused: reports from"  # how api.rate words a topic's pause when crews' reports pulled its talk
TELL_FOR = timedelta(days=7)              # how long after such a pull the owner email is still tried


class Command(BaseCommand):
    help = "Cron step for Monday Minute: write next week's talk when due, push Monday's, screen held comments."

    def add_arguments(self, parser):
        parser.add_argument("--week", help="Write this Monday's talk now (YYYY-MM-DD)")

    def handle(self, *args, week=None, **opts):
        # A safety test whose server process was stopped (a deploy, a restart) is marked as failed here, so its row
        # does not go on saying "Running" until somebody opens the admin.
        closed = close_stale_runs()
        if closed:
            self.stdout.write(f"Monday Minute: {closed} safety test run(s) marked as failed, the server stopped while they ran.")
        # The safety gate comes first and runs even when writing is switched off: the app serves talks either way.
        self.check_gate()
        if not settings.MONDAY_MINUTE_ENABLED:
            self.stdout.write("Monday Minute is off (MONDAY_MINUTE_ENABLED=0).")
            return
        # One ceiling on everything this step asks of the AI. Railway does not start a cron run while the last one is
        # still going, so a slow or stuck AI server used to hold back every other scheduled job (pushes, sign-up
        # syncs, owner alerts) for 30 minutes per call. 0 = no limit.
        budget = settings.MONDAY_STEP_BUDGET
        with ai.time_budget(budget):
            # The quick jobs first, so a long write cannot keep Monday's push, an owner notice or the waiting comments back.
            self.push()
            self.tell_owner_about_talks()
            if ai.available():
                with ai.time_budget(self.comment_time(budget)):  # their own small share; the write keeps the rest
                    n = screen_pending()
                if n:
                    self.stdout.write(f"Screened {n} held comment(s).")
            target = date.fromisoformat(week) if week else due_week()
            if target and self.write(target):
                # A talk written after its Monday 5:00 AM goes out now: same gate check, same push, in this run.
                self.check_gate()
                self.push()
        missed = missed_week()
        if missed:
            # Printed once per week (remembered in the database cache), not on every run until next Monday.
            if caches["shared"].add(f"monday-missed:{missed}", 1, 14 * 24 * 3600):
                self.stdout.write(f"Monday Minute {missed}: NO TALK went out this week. It could not be written and approved by Wednesday 5:00 AM "
                                  "Pacific, so the app keeps showing the last one. Look for earlier 'could not write it' lines.")
            # And emailed once. notify() keeps its own once-only note under the key and gives it back when the email
            # did not go out, so asking on every run sends one email, on the first run that can.
            self.tell_owner(f"Monday Minute: no talk went out for the week of {missed:%b %-d}",
                            [f"No Monday Minute was published or is waiting for approval for the week of {missed:%B %-d, %Y}.",
                             "It could not be written and pass its safety checks by Wednesday 5:00 AM Pacific, so the app keeps showing the last talk.",
                             "Why: look at the cron log for lines that say 'could not write it', and in the admin under Monday Minutes "
                             "for drafts of that week marked 'Blocked by the safety checks' (their check log says what failed).",
                             "The writer starts on next Monday's talk by itself. Nothing needs doing for that."],
                            f"monday-missed-{missed}")

    def comment_time(self, budget: float) -> float:
        """Seconds of the step's AI time that waiting comments may use: a fifth, or as long as one comment check may
        take if that is more (a share shorter than one check would screen nothing, ever), but never more than half."""
        return max(budget * COMMENT_SHARE, min(settings.LOCAL_AI_FAST_TIMEOUT, budget * COMMENT_SHARE_MAX))

    def tell_owner(self, subject, lines, key) -> bool:
        """One plain email to the owner through talks.owner_alerts.notify, at most once per key. Never lets a
        problem with the email stop the step."""
        try:
            from talks import owner_alerts  # looked up when used: this step must run even if owner alerts cannot load

            return bool(owner_alerts.notify(subject, lines, key))
        except Exception:
            log.exception("Monday Minute: could not send the owner notice '%s'", subject)
            return False

    def tell_owner_about_talks(self):
        """Two things that used to reach only the log. Each is emailed once (its key), and asked again on later runs
        only until the email has gone out."""
        now = timezone.now()
        this_week = next_week(now) - timedelta(days=7)
        # This week's talk has reached its publish time and is still waiting for a person: the safety gate held it
        # back, when it was written or at the last look, so crews are still shown last week's.
        for m in MondayMinute.objects.filter(status=MondayMinute.HELD, week__gte=this_week, publish_at__lte=now).select_related("topic"):
            self.tell_owner(f"Monday Minute for {m.week:%b %-d} is waiting for your approval",
                            [f"This week's Monday Minute ({m.title or m.topic.title}) has passed its publish time and has not gone out.",
                             "It passed its checks, but the AI setup that wrote it has no passing safety test on record, so a person has to approve it.",
                             "To publish it: admin, Monday Minutes, tick the talk, choose 'Approve and publish the selected talks'. "
                             "Until then the app keeps showing last week's talk."],
                            f"monday-held-{m.pk}")
        # Crews' "isn't safe or isn't right" reports pulled a talk from the app and paused its topic. The pause reason
        # names the talk by its week, which tells it from a talk on the same topic that was pulled by hand.
        pulled = MondayMinute.objects.filter(status=MondayMinute.PULLED, topic__active=False, topic__paused_reason__startswith=PULLED_BY_CREWS,
                                             topic__updated_at__gte=now - TELL_FOR).select_related("topic")
        for m in pulled:
            if f"the {m.week:%b %-d} talk" not in m.topic.paused_reason:
                continue
            self.tell_owner(f"Monday Minute for {m.week:%b %-d} was pulled after crew reports",
                            [f"Crews at several sites reported that the Monday Minute '{m.title or m.topic.title}' isn't safe or isn't right.",
                             "It has been taken out of the app and its topic is paused, so it will not be used again until you look.",
                             "What crews wrote is in the admin under Monday Minutes, on the talk's page (the thumbs-down notes). "
                             "To put the talk back, use 'Restore the selected talks'. To use the topic again, clear its pause reason and tick Active."],
                            f"monday-pulled-{m.pk}")

    def check_gate(self):
        """The gate is checked again here, not only when the talk was written: early for talks still ahead of their
        publish time, and one last time for a talk that has just reached it (nothing goes out before that)."""
        now = timezone.now()
        held = gate.hold_unpublished(now) + gate.release_due(now)[1]
        if held:
            self.stdout.write(f"Monday Minute: {held} talk(s) moved back to waiting for approval. The AI setup no longer has a passing safety test.")

    def push(self):
        for m in due_pushes():
            ok, detail = send_minute_push(m)
            self.stdout.write(f"Monday Minute push {m.week}: {'OK' if ok else detail}")

    def write(self, target) -> bool:
        """Writes the talk for `target`. True when a talk was saved that goes out now (written late, gate open)."""
        if not ai.available():
            need = "LOCAL_AI_URL" if ai.is_local() else "ANTHROPIC_API_KEY"
            self.stdout.write(f"Monday Minute: {need} is not set, so nothing was written.")
            return False
        note_attempt(target)  # from here on a week that ends without a talk is a missed one (see missed_week)
        if not MondayLock.acquire("write"):
            self.stdout.write(f"Monday Minute {target}: another run is still writing it.")
            return False
        try:
            if ai.is_local() and not ai.ensure_model():
                self.stdout.write("Monday Minute: the local model is still downloading. Will retry.")
                return False
            late = is_late(target)
            m = generate_week(target, late=late)
            out_now = bool(m) and late and m.status == MondayMinute.READY
            self.stdout.write(f"Monday Minute {target}: {m.get_status_display() if m else 'nothing to do'}"
                              + (" (written after its Monday 5:00 AM, so it goes out now)" if out_now else ""))
            if m and m.status == MondayMinute.HELD:
                self.stdout.write("  Waiting for approval in the admin. Run the safety test to let talks publish on their own.")
            if m and m.status == MondayMinute.BLOCKED:
                unusable = m.check_log.count(NO_ANSWER)
                self.stdout.write("  No draft on this topic passed, so nothing was published from it. Its check log in the admin says why."
                                  + (f" In {unusable} of its attempts the AI gave no usable answer (cut off, refused or not valid JSON) even "
                                     "when asked again; those steps were not asked a third time." if unusable else ""))
            return out_now
        except Exception as err:  # AI server down, API outage or out of time: the next run carries on
            self.stdout.write(f"Monday Minute {target}: could not write it ({err}). Will retry.")
            return False
        finally:
            MondayLock.release("write")
