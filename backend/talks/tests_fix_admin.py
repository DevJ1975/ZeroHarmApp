"""Tests for the admin actions in talks/admin.py and monday/admin.py, and the safety-test runner behind one of them.

Every test goes through the admin the way the owner does: signed in as staff, posting the action from the list page.
OneSignal, GoHighLevel and the AI server are replaced by stand-ins, so nothing leaves the machine."""
import datetime as dt
import threading
from io import StringIO
from unittest.mock import patch

from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from monday import eval_runner
from monday.ai import AIUnavailable
from monday.models import MondayComment, MondayEvalRun, MondayLock, MondayMinute, MondayTopic
from monday.tests import talk, topic

from .ghl import GhlError
from .models import Episode, FeedItem, GhlSync, OtisFeedback, SigninSheet, ToolboxTalk

PASSED = "Attempt 1: passed the CSP review.\nSafety gate: publishes on its own, the model passed the safety test."
ONESIGNAL = dict(ONESIGNAL_APP_ID="test-app", ONESIGNAL_REST_API_KEY="test-key")
REAL_THREAD = threading.Thread
PLAIN_STATIC = {"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
                "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}}


@override_settings(STORAGES=PLAIN_STATIC)  # admin pages link their stylesheets; tests have no collected static files
class AdminCase(TestCase):
    def setUp(self):
        cache.clear()
        self.owner = get_user_model().objects.create_superuser("owner", "owner@example.com", "a-long-test-password")
        self.client.force_login(self.owner)

    def act(self, path, action, rows, **extra):
        """Posts an admin action from a list page, as the Go button does. Returns the page the owner lands on."""
        data = {"action": action, "_selected_action": [str(pk) for pk in rows], "index": "0", **extra}
        return self.client.post(f"/admin/{path}/", data, follow=True)

    def confirm(self, path, action, rows, **extra):
        """Posts what the "Yes" button on the confirmation page posts."""
        data = {"action": action, "_selected_action": [str(pk) for pk in rows], "confirm_push": "yes", **extra}
        return self.client.post(f"/admin/{path}/", data, follow=True)

    def said(self, response):
        return " | ".join(str(m) for m in response.context["messages"])


# ---- Monday Minute: Pull and Restore ---------------------------------------------------------------------------

class PullRestoreTests(AdminCase):
    def setUp(self):
        super().setUp()
        MondayTopic.objects.all().delete()
        self.t = topic()
        self.week = dt.date(2026, 11, 9)
        self.out = timezone.now() - dt.timedelta(hours=1)

    def minute(self, status, text=True, **kw):
        kw.setdefault("publish_at", self.out)
        kw.setdefault("week", self.week)
        return MondayMinute.objects.create(topic=self.t, status=status, **(talk() if text else {}), **kw)

    def in_app(self):
        return [m["id"] for m in self.client.get("/api/v2/monday-minute").json()["minutes"]]

    def test_pull_then_restore_never_publishes_a_blocked_draft(self):
        blocked = self.minute(MondayMinute.BLOCKED, text=False, check_log="Attempt 1: CSP review failed:\n  Unsafe.")
        pulled = self.act("monday/mondayminute", "pull", [blocked.pk])
        blocked.refresh_from_db()
        self.assertEqual(blocked.status, MondayMinute.BLOCKED)  # a blocked draft is not in the app: nothing to pull
        self.assertIn("left alone", self.said(pulled))
        restored = self.act("monday/mondayminute", "restore", [blocked.pk])
        blocked.refresh_from_db()
        self.assertEqual((blocked.status, blocked.approved_by_person), (MondayMinute.BLOCKED, False))
        self.assertIn("Restored 0 talk(s)", self.said(restored))
        self.assertEqual(self.in_app(), [])

    def test_restore_refuses_a_blocked_draft_that_was_pulled_before_this_fix(self):
        empty = self.minute(MondayMinute.PULLED, text=False, check_log="Attempt 3: CSP review failed:\n  Unsafe.")
        no_pass = self.minute(MondayMinute.PULLED, week=self.week - dt.timedelta(days=7),
                              check_log="Attempt 1: first review passed, second review failed.")
        said = self.said(self.act("monday/mondayminute", "restore", [empty.pk, no_pass.pk]))
        for m in (empty, no_pass):
            m.refresh_from_db()
            self.assertEqual((m.status, m.approved_by_person), (MondayMinute.PULLED, False))
        self.assertIn("Restored 0 talk(s)", said)
        self.assertIn("2 stayed pulled", said)
        self.assertEqual(self.in_app(), [])
        # And the Monday push does not go out for either.
        pushed = []
        with patch("monday.management.commands.monday_minute.send_minute_push", lambda m: (pushed.append(m.pk), (True, ""))[1]), \
                patch("monday.management.commands.monday_minute.due_week", lambda: None), \
                patch("monday.management.commands.monday_minute.ai.available", lambda: False):
            call_command("monday_minute", stdout=StringIO())
        self.assertEqual(pushed, [])

    def test_a_talk_that_passed_can_be_pulled_and_restored(self):
        ready = self.minute(MondayMinute.READY, check_log=PASSED)
        self.assertEqual(self.in_app(), [ready.pk])
        self.assertIn("Pulled 1 talk(s)", self.said(self.act("monday/mondayminute", "pull", [ready.pk])))
        self.assertEqual(self.in_app(), [])
        self.assertIn("Restored 1 talk(s)", self.said(self.act("monday/mondayminute", "restore", [ready.pk])))
        ready.refresh_from_db()
        self.assertEqual((ready.status, ready.approved_by_person), (MondayMinute.READY, True))
        self.assertEqual(self.in_app(), [ready.pk])

    def test_pull_takes_a_talk_out_of_the_approval_queue_too(self):
        held = self.minute(MondayMinute.HELD, check_log=PASSED)
        self.act("monday/mondayminute", "pull", [held.pk])
        held.refresh_from_db()
        self.assertEqual(held.status, MondayMinute.PULLED)


# ---- "Send the push now" ---------------------------------------------------------------------------------------

@override_settings(**ONESIGNAL)
class PushNowTests(AdminCase):
    def setUp(self):
        super().setUp()
        self.posted = []
        stand_in = patch("talks.integrations._post", lambda url, headers, payload, timeout=10: (self.posted.append(payload["data"]), (200, {"id": "x"}))[1])
        stand_in.start()
        self.addCleanup(stand_in.stop)
        now = timezone.now()
        ToolboxTalk.objects.filter(issue=1).update(send_at=now - dt.timedelta(minutes=5), published=True, needs_review=False, push_sent_at=None)
        ToolboxTalk.objects.filter(issue=2).update(send_at=now + dt.timedelta(days=3), published=True, needs_review=False, push_sent_at=None)
        ToolboxTalk.objects.filter(issue=3).update(send_at=now - dt.timedelta(minutes=5), needs_review=True, push_sent_at=None)

    def test_a_talk_that_is_not_live_is_refused_and_keeps_its_scheduled_push(self):
        for issue in (2, 3):
            for go in (self.act, self.confirm):  # the first click, and a "Yes" posted straight at the action
                said = self.said(go("talks/toolboxtalk", "send_push_now", [issue]))
                self.assertIn("isn't live in the app yet", said)
        self.assertEqual(self.posted, [])
        self.assertIsNone(ToolboxTalk.objects.get(issue=2).push_sent_at)
        self.assertIsNone(ToolboxTalk.objects.get(issue=3).push_sent_at)
        # Once issue 2 goes live the scheduled push still goes out.
        ToolboxTalk.objects.filter(issue=2).update(send_at=timezone.now() - dt.timedelta(minutes=5))
        ToolboxTalk.objects.filter(issue=1).update(push_sent_at=timezone.now())
        call_command("send_talk_push", stdout=StringIO())
        self.assertEqual(self.posted, [{"issue": 2, "refresh": True}])

    def test_a_live_talk_asks_first_and_sends_once_on_yes(self):
        page = self.act("talks/toolboxtalk", "send_push_now", [1])
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Are you sure?")
        self.assertContains(page, 'name="confirm_push"')
        self.assertEqual(self.posted, [])
        self.assertIsNone(ToolboxTalk.objects.get(issue=1).push_sent_at)
        said = self.said(self.confirm("talks/toolboxtalk", "send_push_now", [1]))
        self.assertIn("Issue 1: sent", said)
        self.assertEqual(self.posted, [{"issue": 1, "refresh": True}])
        self.assertIsNotNone(ToolboxTalk.objects.get(issue=1).push_sent_at)

    def test_select_all_sends_nothing(self):
        ToolboxTalk.objects.update(send_at=timezone.now() - dt.timedelta(minutes=5), published=True, needs_review=False)
        self.assertGreater(ToolboxTalk.objects.count(), 10)
        for go in (self.act, self.confirm):
            said = self.said(go("talks/toolboxtalk", "send_push_now", [1], select_across="1"))
            self.assertIn("Select one", said)
        self.assertIn("Select one", self.said(self.confirm("talks/toolboxtalk", "send_push_now", [1, 4])))
        self.assertEqual(self.posted, [])

    def test_feed_items_follow_the_same_rules(self):
        now = timezone.now()
        soon = FeedItem.objects.create(external_id="t:soon", kind="alert", title="Soon", publish_at=now + dt.timedelta(days=1), send_push=True)
        live = FeedItem.objects.create(external_id="t:live", kind="alert", title="Live", publish_at=now - dt.timedelta(minutes=5), send_push=True)
        for go in (self.act, self.confirm):
            self.assertIn("isn't live in the app yet", self.said(go("talks/feeditem", "push_now", [soon.pk])))
        page = self.act("talks/feeditem", "push_now", [live.pk])
        self.assertContains(page, "Are you sure?")
        self.assertContains(page, "every phone with Regulatory alerts switched on")
        self.assertEqual(self.posted, [])
        self.assertIn("Select one", self.said(self.confirm("talks/feeditem", "push_now", [soon.pk, live.pk])))
        self.assertIn("Live: sent", self.said(self.confirm("talks/feeditem", "push_now", [live.pk])))
        self.assertEqual([p["feed_id"] for p in self.posted], [live.pk])
        soon.refresh_from_db()
        self.assertIsNone(soon.push_sent_at)
        # The cron still pushes the other one when it goes live.
        FeedItem.objects.filter(pk=soon.pk).update(publish_at=timezone.now() - dt.timedelta(minutes=1))
        self.assertTrue(FeedItem.objects.released().filter(pk=soon.pk, send_push=True, push_sent_at__isnull=True).exists())

    def test_episodes_follow_the_same_rules(self):
        now = timezone.now()
        Episode.objects.filter(number=1).update(release_at=now - dt.timedelta(minutes=5), published=True, needs_details=False, push_sent_at=None)
        Episode.objects.filter(number=2).update(release_at=now + dt.timedelta(days=2), published=True, needs_details=False, push_sent_at=None)
        Episode.objects.filter(number=3).update(release_at=now - dt.timedelta(minutes=5), published=True, needs_details=True, push_sent_at=None)
        out, soon, waiting = (Episode.objects.get(number=n) for n in (1, 2, 3))
        for ep in (soon, waiting):
            for go in (self.act, self.confirm):
                self.assertIn("isn't live in the app yet", self.said(go("talks/episode", "push_now", [ep.pk])))
        self.assertContains(self.act("talks/episode", "push_now", [out.pk]), "Are you sure?")
        self.assertEqual(self.posted, [])
        self.assertIn("EP 1: sent", self.said(self.confirm("talks/episode", "push_now", [out.pk])))
        self.assertEqual(self.posted, [{"episode": 1, "refresh": True}])
        self.assertIsNone(Episode.objects.get(number=2).push_sent_at)
        self.assertIsNone(Episode.objects.get(number=3).push_sent_at)


# ---- Look-only lists have no Add page --------------------------------------------------------------------------

class NoAddPageTests(AdminCase):
    def test_lists_that_only_the_app_fills_offer_no_add(self):
        for path in ("talks/signinsheet", "talks/otisfeedback", "monday/mondaycomment"):
            with self.assertLogs("django.request", level="WARNING"):  # the two refusals below
                self.assertEqual(self.client.get(f"/admin/{path}/add/").status_code, 403, path)
                self.assertEqual(self.client.post(f"/admin/{path}/add/", {"body": "x"}).status_code, 403, path)
            self.assertNotContains(self.client.get(f"/admin/{path}/"), f"/admin/{path}/add/")
        self.assertEqual((SigninSheet.objects.count(), OtisFeedback.objects.count(), MondayComment.objects.count()), (0, 0, 0))


# ---- GoHighLevel is down ---------------------------------------------------------------------------------------

class GhlDownTests(AdminCase):
    def down(self, *args, **kwargs):
        raise GhlError("GET /emails/builder -> 401: Invalid token", status=401)

    def test_run_now_records_the_failure_instead_of_crashing(self):
        job = GhlSync.objects.create(year=2027)
        with patch("talks.admin.sync_year", self.down):
            page = self.act("talks/ghlsync", "run_now", [job.pk])
        self.assertEqual(page.status_code, 200)
        self.assertIn("2027: failed", self.said(page))
        self.assertIn("Invalid token", self.said(page))
        job.refresh_from_db()
        self.assertEqual(job.status, "failed")
        self.assertIn("Invalid token", job.log)
        self.assertIsNotNone(job.finished_at)

    def test_run_now_still_works(self):
        job = GhlSync.objects.create(year=2027)
        with patch("talks.admin.sync_year", lambda year: [f"{year}: 2 issues"]):
            self.assertIn("2027: done", self.said(self.act("talks/ghlsync", "run_now", [job.pk])))
        job.refresh_from_db()
        self.assertEqual((job.status, job.log), ("done", "2027: 2 issues"))

    def test_zero_hour_check_says_what_went_wrong(self):
        ep = Episode.objects.first()
        with patch("talks.admin.sync_episodes", self.down):
            page = self.act("talks/episode", "sync_from_ghl", [ep.pk])
        self.assertEqual(page.status_code, 200)
        self.assertIn("Could not check GHL Media Storage", self.said(page))
        self.assertIn("Invalid token", self.said(page))


# ---- Work the admin starts in the background -------------------------------------------------------------------

class Threads:
    """Stands in for threading.Thread for the work the admin and the safety-test runner start: remembers what would
    have run, so a test can run it (or not) on its own terms. Threads started by anything else are real ones."""

    OURS = ("monday.admin", "monday.eval_runner")

    def __init__(self, fail_to_start=False):
        self.started, self.fail_to_start = [], fail_to_start

    def __call__(self, *args, target=None, **kw):
        if getattr(target, "__module__", "") not in self.OURS:
            return REAL_THREAD(*args, target=target, **kw)
        outer = self

        class Fake:
            def start(self):
                if outer.fail_to_start:
                    raise RuntimeError("can't start new thread")
                outer.started.append(target)

        return Fake()


@override_settings(AI_PROVIDER="local", LOCAL_AI_URL="http://ai.test.invalid:11434")
class BackgroundCase(AdminCase):
    def setUp(self):
        super().setUp()
        MondayTopic.objects.all().delete()
        self.t = topic()
        self.threads = Threads()
        # The background work closes its thread's database connection when it ends. Here it runs in the test's own
        # thread, so that close is replaced too.
        for stand_in in (patch("threading.Thread", self.threads), patch("monday.admin.connection"), patch("monday.eval_runner.connection")):
            stand_in.start()
            self.addCleanup(stand_in.stop)
        # A test may end with a lock still held (that is the point of some of them): let go, so nothing outlives it.
        self.addCleanup(MondayLock.release, "write")
        self.addCleanup(eval_runner.release)

    def fail_to_start(self):
        self.threads.fail_to_start = True


class WriteNextWeekTests(BackgroundCase):
    def setUp(self):
        super().setUp()
        self.m = MondayMinute.objects.create(week=dt.date(2026, 11, 9), publish_at=timezone.now(), topic=self.t, status=MondayMinute.READY, **talk())

    def write(self):
        return self.said(self.act("monday/mondayminute", "write_next_week", [self.m.pk]))

    @override_settings(LOCAL_AI_URL="")
    def test_no_ai_server_is_said_up_front(self):
        said = self.write()
        self.assertIn("LOCAL_AI_URL is not set", said)
        self.assertNotIn("in the background", said)
        self.assertEqual(self.threads.started, [])
        self.assertFalse(MondayLock.objects.exists())

    def test_a_second_click_is_refused_while_one_is_writing(self):
        self.assertIn("in the background", self.write())
        self.assertTrue(MondayLock.objects.filter(name="write").exists())  # taken before the owner is told it started
        said = self.write()
        self.assertIn("still being written", said)
        self.assertNotIn("in the background", said)
        self.assertEqual(len(self.threads.started), 1)

    def test_failing_to_start_is_reported_and_leaves_no_lock(self):
        self.fail_to_start()
        said = self.write()
        self.assertIn("Could not start", said)
        self.assertNotIn("in the background", said)
        self.assertFalse(MondayLock.objects.exists())

    def test_a_failure_in_the_background_is_written_down_for_the_owner(self):
        def down():
            raise AIUnavailable("Local AI server unavailable: connection refused")

        self.write()
        with patch("monday.admin.ensure_model", down), self.assertLogs("monday.admin", level="ERROR"):
            self.threads.started[0]()
        note = LogEntry.objects.get()
        self.assertEqual(note.user, self.owner)
        self.assertIn("could not write it", note.object_repr)
        self.assertIn("connection refused", note.object_repr)
        self.assertFalse(MondayLock.objects.exists())  # so the cron, or another click, can try again
        self.assertEqual(MondayMinute.objects.count(), 1)

    def test_the_result_is_written_down_too(self):
        self.write()
        made = MondayMinute(week=dt.date(2026, 11, 16), publish_at=timezone.now(), topic=self.t, status=MondayMinute.HELD, **talk())

        def wrote(week, **kw):
            made.save()
            return made

        with patch("monday.admin.ensure_model", lambda: True), patch("monday.admin.generate_week", wrote):
            self.threads.started[0]()
        note = LogEntry.objects.get()
        self.assertEqual(note.object_id, str(made.pk))
        self.assertIn("Waiting for approval", note.object_repr)
        self.assertFalse(MondayLock.objects.exists())


class SafetyTestActionTests(BackgroundCase):
    def start(self):
        return self.said(self.act("monday/mondaytopic", "safety_test", [self.t.pk]))

    def test_two_clicks_start_one_test(self):
        self.assertIn("Safety test started", self.start())
        said = self.start()
        self.assertIn("already running", said)
        self.assertNotIn("Safety test started", said)
        self.assertEqual(len(self.threads.started), 1)

    @override_settings(LOCAL_AI_URL="")
    def test_no_ai_server_is_said_up_front(self):
        said = self.start()
        self.assertIn("LOCAL_AI_URL is not set", said)
        self.assertEqual(self.threads.started, [])
        self.assertFalse(MondayLock.objects.exists())
        self.assertFalse(MondayEvalRun.objects.exists())

    def test_failing_to_start_is_reported_and_leaves_no_lock(self):
        self.fail_to_start()
        said = self.start()
        self.assertIn("Could not start", said)
        self.assertNotIn("Safety test started", said)
        self.assertFalse(MondayLock.objects.exists())

    def test_the_started_test_runs_and_frees_the_slot(self):
        self.start()
        with patch("monday.eval_runner.ensure_model", lambda: True), \
                patch("monday.eval_runner.ev.run", lambda topics, rag, strict, progress: {"rag": rag}), \
                patch("monday.eval_runner.gate.score", lambda r: {"catch_rate": 1.0, "false_block_rate": 0.0}), \
                patch("monday.eval_runner.gate.conclusive", lambda r, slugs: (False, "too small")), \
                patch("monday.eval_runner.ev.summarize", lambda r: "summary"):
            self.threads.started[0]()
        run = MondayEvalRun.objects.get()
        self.assertEqual(run.status, "done")
        self.assertFalse(MondayLock.objects.filter(name=eval_runner.LOCK).exists())
        self.assertIn("Safety test started", self.start())  # the next one may start


class StaleRunTests(BackgroundCase):
    """A deploy or restart stops the web process and the test with it. Its row must not say "Running" for good."""

    def running(self, **kw):
        return MondayEvalRun.objects.create(model="m", topics=[self.t.slug], progress="3 of 32 talks", **kw)

    def beat(self, minutes_ago):
        MondayLock.objects.update_or_create(name=eval_runner.LOCK, defaults={"locked_at": timezone.now() - dt.timedelta(minutes=minutes_ago)})

    def test_a_run_with_no_sign_of_life_is_marked_failed(self):
        run, finished = self.running(), self.running(status="done", summary="PASSED")
        self.beat(minutes_ago=60)  # what a killed process leaves behind
        self.assertEqual(eval_runner.close_stale_runs(), 1)
        run.refresh_from_db()
        finished.refresh_from_db()
        self.assertEqual(run.status, "failed")
        self.assertIsNotNone(run.finished_at)
        self.assertIn("Interrupted", run.summary)
        self.assertEqual(run.progress, "3 of 32 talks")  # how far it got stays on record
        self.assertEqual((finished.status, finished.summary), ("done", "PASSED"))
        self.assertEqual(eval_runner.close_stale_runs(), 0)

    def test_a_run_with_no_lock_at_all_is_marked_failed(self):
        run = self.running()
        self.assertEqual(eval_runner.close_stale_runs(), 1)
        run.refresh_from_db()
        self.assertEqual(run.status, "failed")

    def test_a_run_that_is_alive_is_left_alone(self):
        run = self.running()
        self.beat(minutes_ago=1)
        self.assertEqual(eval_runner.close_stale_runs(), 0)
        run.refresh_from_db()
        self.assertEqual((run.status, run.finished_at), ("running", None))

    def test_opening_the_runs_list_or_a_run_shows_the_truth(self):
        run = self.running()
        self.beat(minutes_ago=60)
        page = self.client.get("/admin/monday/mondayevalrun/")
        self.assertEqual(page.status_code, 200)
        run.refresh_from_db()
        self.assertEqual(run.status, "failed")
        other = self.running()
        self.assertContains(self.client.get(f"/admin/monday/mondayevalrun/{other.pk}/change/"), "Interrupted")

    def test_a_new_test_can_start_after_an_interrupted_one(self):
        run = self.running()
        self.beat(minutes_ago=60)
        said = self.said(self.act("monday/mondaytopic", "safety_test", [self.t.pk]))
        self.assertIn("Safety test started", said)
        run.refresh_from_db()
        self.assertEqual(run.status, "failed")

    def test_the_runner_refuses_while_another_run_is_alive(self):
        self.beat(minutes_ago=1)
        with self.assertRaises(eval_runner.AlreadyRunning):
            eval_runner.run_eval([self.t])
        self.assertFalse(MondayEvalRun.objects.exists())
        self.assertTrue(MondayLock.objects.filter(name=eval_runner.LOCK).exists())  # the other run's, untouched

    def test_the_sign_of_life_refreshes_the_lock(self):
        class OneBeat:  # lets one refresh through, then says stop
            waits = 0

            def wait(self, seconds):
                self.waits += 1
                return self.waits > 1

        self.beat(minutes_ago=8)
        eval_runner._keep_alive(OneBeat())
        self.assertGreater(MondayLock.objects.get(name=eval_runner.LOCK).locked_at, timezone.now() - dt.timedelta(minutes=1))
        self.assertEqual(eval_runner.close_stale_runs(), 0)

    def test_the_runner_keeps_a_sign_of_life_while_it_works(self):
        seen = {}

        def work(topics, rag, strict, progress):
            seen["lock"] = MondayLock.objects.filter(name=eval_runner.LOCK).exists()
            seen["beats"] = len(self.threads.started)
            raise AIUnavailable("Local AI server unavailable: timed out")

        with patch("monday.eval_runner.ensure_model", lambda: True), patch("monday.eval_runner.ev.run", work):
            run = eval_runner.run_eval([self.t])
        self.assertEqual(seen, {"lock": True, "beats": 1})
        self.assertEqual(run.status, "failed")
        self.assertIn("timed out", run.summary)
        self.assertFalse(MondayLock.objects.filter(name=eval_runner.LOCK).exists())
