"""Tests for the Monday Minute fixes: the write lock, late weeks, one talk per week, the safety gate at publish time,
separate rate limits per network, text that PostgreSQL can store, bounded comment screening and bounded AI time.
The second half (from "Round two") covers what the re-check of those fixes found: a push sent once, failed AI steps
remembered between runs, a share of the time for comments, a missed week only when a talk was due, a blank AI
address said plainly, and the Monday Minute admin.
No test here contacts an AI server, OneSignal or GoHighLevel: every one is a stand-in."""
import datetime as dt
import importlib
import json
import threading
import time
from io import BytesIO, StringIO
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.db import IntegrityError, connection, transaction
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from . import ai, api, eval_runner, gate, generate as g, moderation, push
from .models import LOCK_TTL, MondayComment, MondayCommentReport, MondayEvalRun, MondayFeedback, MondayLock, MondayMinute, MondayTopic
from .tests import INSTALL, PASS, talk, topic  # helpers only; importing a test class here would run it twice

UTC = dt.timezone.utc
CRON = "monday.management.commands.monday_minute"


def minute(t, week=dt.date(2026, 11, 9), status=MondayMinute.READY, **kw):
    kw.setdefault("publish_at", timezone.now() - dt.timedelta(hours=1))
    return MondayMinute.objects.create(week=week, topic=t, status=status, **{**talk(), **kw})


def passing_run(passed=True, **kw):
    """A safety test on record for the AI setup the tests run with."""
    want = gate.setup()
    defaults = dict(model=want["model"], rag=want["rag"], strict=want["strict"], status="done", passed=passed, conclusive=True,
                    verdict="caught 95%", finished_at=timezone.now())
    defaults.update(kw)
    return MondayEvalRun.objects.create(**defaults)


def fake_ai(system, user, schema, **kw):
    """Stands in for the AI in the cron tests: a good talk from the writer, a pass from the reviewer."""
    return (talk() if schema is g.TALK_SCHEMA else PASS), "test-model"


# ---- The write lock -------------------------------------------------------------------------------------

class LockTests(TestCase):
    def tearDown(self):
        MondayLock.release("write")  # stops the heartbeat of a lock a test left held

    def test_a_lock_left_by_a_killed_run_is_free_within_minutes(self):
        # A deploy stopped the container mid-write an hour ago: no `finally` ran, the row is still there.
        MondayLock.objects.create(name="write", locked_at=timezone.now() - dt.timedelta(hours=1))
        self.assertTrue(MondayLock.acquire("write"))  # used to be refused for 4 hours
        self.assertLessEqual(LOCK_TTL, dt.timedelta(minutes=10))

    def test_a_fresh_lock_is_respected(self):
        MondayLock.objects.create(name="write", locked_at=timezone.now() - dt.timedelta(seconds=90), owner="another-run")
        self.assertFalse(MondayLock.acquire("write"))

    def test_the_heartbeat_keeps_a_live_runs_lock(self):
        self.assertTrue(MondayLock.acquire("write"))
        owner = MondayLock.objects.get(name="write").owner
        self.assertTrue(owner)
        almost_stale = timezone.now() - LOCK_TTL + dt.timedelta(seconds=5)
        MondayLock.objects.filter(name="write").update(locked_at=almost_stale)
        self.assertTrue(MondayLock.beat("write", owner))
        self.assertGreater(MondayLock.objects.get(name="write").locked_at, timezone.now() - dt.timedelta(seconds=30))
        self.assertFalse(MondayLock.beat("write", "another-run"))  # only the owner can refresh it

    def test_holding_the_lock_runs_a_heartbeat_until_release(self):
        beats, beaten = [], threading.Event()

        def beat(name, owner):
            beats.append((name, owner))
            beaten.set()
            return True

        with patch("monday.models.LOCK_BEAT_SECONDS", 0.01), patch.object(MondayLock, "beat", beat):
            self.assertTrue(MondayLock.acquire("write"))
            owner = MondayLock.objects.get(name="write").owner
            self.assertTrue(beaten.wait(5), "no heartbeat while the lock was held")
            self.assertEqual(beats[0], ("write", owner))
            MondayLock.release("write")
            deadline = time.monotonic() + 5
            while any(t.name == "monday-lock-write" and t.is_alive() for t in threading.enumerate()) and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertFalse(any(t.name == "monday-lock-write" and t.is_alive() for t in threading.enumerate()))
        self.assertFalse(MondayLock.objects.filter(name="write").exists())

    def test_release_never_frees_another_runs_lock(self):
        MondayLock.objects.create(name="write", locked_at=timezone.now(), owner="another-run")
        self.assertFalse(MondayLock.acquire("write"))
        MondayLock.release("write")  # this process does not hold it
        self.assertEqual(MondayLock.objects.get(name="write").owner, "another-run")

    def test_a_run_that_lost_its_lock_does_not_free_the_new_holders(self):
        self.assertTrue(MondayLock.acquire("write"))
        # This run stalled past the expiry and another run took the lock over.
        MondayLock.objects.filter(name="write").update(owner="another-run", locked_at=timezone.now())
        MondayLock.release("write")
        self.assertEqual(MondayLock.objects.get(name="write").owner, "another-run")


# ---- Late weeks, and what the cron step does -------------------------------------------------------------

class LateWeekTests(TestCase):
    def setUp(self):
        MondayTopic.objects.all().delete()
        self.t = topic()

    def test_a_week_missed_at_5am_is_still_owed_until_wednesday(self):
        week = dt.date(2026, 11, 16)                                       # Monday 5:00 AM PST is 13:00 UTC
        self.assertEqual(g.due_week(dt.datetime(2026, 11, 16, 12, 59, tzinfo=UTC)), week)
        self.assertEqual(g.due_week(dt.datetime(2026, 11, 16, 13, 0, tzinfo=UTC)), week)   # used to be None from here on
        self.assertEqual(g.due_week(dt.datetime(2026, 11, 17, 20, 0, tzinfo=UTC)), week)   # Tuesday noon
        self.assertEqual(g.due_week(dt.datetime(2026, 11, 18, 13, 0, tzinfo=UTC)), dt.date(2026, 11, 23))  # Wednesday: next week's turn

    def test_a_week_that_has_its_talk_or_was_given_up_on_is_not_owed(self):
        monday_noon = dt.datetime(2026, 11, 16, 20, 0, tzinfo=UTC)
        written = minute(self.t, dt.date(2026, 11, 16), MondayMinute.HELD)
        self.assertIsNone(g.due_week(monday_noon))
        written.delete()
        for slug in ("a", "b"):
            minute(topic(slug), dt.date(2026, 11, 16), MondayMinute.BLOCKED)
        self.assertIsNone(g.due_week(monday_noon))  # both topic tries failed the checks: nothing unchecked goes out late either

    def test_is_late_only_for_this_weeks_talk_after_its_publish_time(self):
        now = dt.datetime(2026, 11, 16, 20, 0, tzinfo=UTC)
        self.assertTrue(g.is_late(dt.date(2026, 11, 16), now))
        self.assertFalse(g.is_late(dt.date(2026, 11, 23), now))  # next Monday: goes out at its own 5:00 AM
        self.assertFalse(g.is_late(dt.date(2026, 11, 9), now))   # an old week written by hand keeps its date and sends no push


@override_settings(AI_PROVIDER="anthropic", ANTHROPIC_API_KEY="test-key", MONDAY_RAG=False)
class CronStepTests(TestCase):
    def setUp(self):
        MondayTopic.objects.all().delete()
        self.t = topic()
        self.this_week = g.next_week() - dt.timedelta(days=7)  # its Monday 5:00 AM has passed

    def run_step(self, **kw):
        out, pushed = StringIO(), []
        with patch("monday.generate.ai_json", fake_ai), \
                patch(f"{CRON}.send_minute_push", lambda m: (pushed.append(m.pk), (True, ""))[1]):
            call_command("monday_minute", stdout=out, **kw)
        return out.getvalue(), pushed

    @override_settings(MONDAY_GATE=False)
    def test_a_late_talk_goes_out_when_written_with_its_push(self):
        said, pushed = self.run_step(week=self.this_week.isoformat())
        m = MondayMinute.objects.get(week=self.this_week)
        self.assertEqual(m.status, MondayMinute.READY)
        self.assertGreater(m.publish_at, timezone.now() - dt.timedelta(minutes=1))  # not back-dated to Monday 5:00 AM
        self.assertTrue(MondayMinute.objects.released().filter(pk=m.pk).exists())
        self.assertEqual(pushed, [m.pk])  # once: before the write there was nothing to push
        self.assertIn("goes out now", said)

    def test_a_late_talk_waits_for_approval_when_the_gate_is_closed(self):
        said, pushed = self.run_step(week=self.this_week.isoformat())  # no safety test on record
        m = MondayMinute.objects.get(week=self.this_week)
        self.assertEqual(m.status, MondayMinute.HELD)
        self.assertFalse(MondayMinute.objects.released().exists())
        self.assertEqual(pushed, [])
        self.assertIn("Waiting for approval", said)

    @override_settings(MONDAY_GATE=False)
    def test_next_weeks_talk_still_waits_for_monday(self):
        week = g.next_week()
        _, pushed = self.run_step(week=week.isoformat())
        m = MondayMinute.objects.get(week=week)
        self.assertEqual((m.status, m.publish_at), (MondayMinute.READY, g.publish_time(week)))
        self.assertFalse(MondayMinute.objects.released().exists())
        self.assertEqual(pushed, [])

    @override_settings(MONDAY_GATE=False)
    def test_a_killed_runs_lock_does_not_stop_the_next_run_from_writing(self):
        MondayLock.objects.create(name="write", locked_at=timezone.now() - dt.timedelta(minutes=16))  # one cron interval ago
        said, _ = self.run_step(week=self.this_week.isoformat())
        self.assertNotIn("another run is still writing", said)
        self.assertTrue(MondayMinute.objects.filter(week=self.this_week, status=MondayMinute.READY).exists())
        self.assertFalse(MondayLock.objects.exists())

    @override_settings(MONDAY_GATE=False)
    def test_a_live_runs_lock_is_left_alone(self):
        MondayLock.objects.create(name="write", locked_at=timezone.now(), owner="another-run")
        said, _ = self.run_step(week=self.this_week.isoformat())
        self.assertIn("another run is still writing", said)
        self.assertFalse(MondayMinute.objects.exists())
        self.assertEqual(MondayLock.objects.get().owner, "another-run")

    def test_quick_jobs_run_before_the_write(self):
        order = []
        with patch(f"{CRON}.Command.push", lambda self: order.append("push")), \
                patch(f"{CRON}.screen_pending", lambda: order.append("comments") or 0), \
                patch(f"{CRON}.Command.write", lambda self, target: order.append("write")):
            call_command("monday_minute", week=self.this_week.isoformat(), stdout=StringIO())
        self.assertEqual(order[:3], ["push", "comments", "write"])

    @override_settings(MONDAY_MINUTE_ENABLED=False)
    def test_the_gate_is_checked_even_when_writing_is_switched_off(self):
        ahead = minute(self.t, g.next_week(), publish_at=g.publish_time(g.next_week()))  # written under a pass; none on record now
        said, _ = self.run_step()
        ahead.refresh_from_db()
        self.assertEqual(ahead.status, MondayMinute.HELD)
        self.assertIn("Monday Minute is off", said)
        self.assertFalse(MondayMinute.objects.exclude(pk=ahead.pk).exists())  # and nothing was written

    @override_settings(MONDAY_STEP_BUDGET=50)
    def test_the_step_puts_one_ceiling_on_its_ai_time(self):
        left = []
        with patch(f"{CRON}.screen_pending", lambda: left.append(ai._time_for(1800)) or 0), patch(f"{CRON}.due_week", lambda: None):
            call_command("monday_minute", stdout=StringIO())
        self.assertTrue(0 < left[0] <= 50, left)
        self.assertEqual(ai._time_for(1800), 1800)  # the ceiling ends with the step


    def test_a_week_with_no_talk_is_said_once(self):
        def step():
            out = StringIO()
            with patch(f"{CRON}.due_week", lambda: None), patch(f"{CRON}.ai.available", lambda: False), \
                    patch(f"{CRON}.missed_week", lambda: dt.date(2026, 11, 9)):
                call_command("monday_minute", stdout=out)
            return out.getvalue()

        self.assertIn("Monday Minute 2026-11-09: NO TALK went out this week", step())
        self.assertNotIn("NO TALK", step())  # not again on every run until next Monday

    def test_missed_week_is_this_weeks_monday_once_the_late_window_is_over(self):
        tuesday, thursday = dt.datetime(2026, 11, 17, 20, 0, tzinfo=UTC), dt.datetime(2026, 11, 19, 20, 0, tzinfo=UTC)
        minute(topic("earlier"), dt.date(2026, 11, 9))  # Monday Minute was running the week before, so a talk was due
        self.assertIsNone(g.missed_week(tuesday))  # it can still be written late
        self.assertEqual(g.missed_week(thursday), dt.date(2026, 11, 16))
        blocked = minute(self.t, dt.date(2026, 11, 16), MondayMinute.BLOCKED)
        self.assertEqual(g.missed_week(thursday), dt.date(2026, 11, 16))  # a blocked draft is not a talk
        blocked.delete()
        minute(self.t, dt.date(2026, 11, 16), MondayMinute.HELD)
        self.assertIsNone(g.missed_week(thursday))


# ---- A write that was cut short carries on ------------------------------------------------------------------

@override_settings(MONDAY_GATE=False)
class ResumeTests(TestCase):
    def setUp(self):
        MondayTopic.objects.all().delete()
        self.t = topic()
        self.week = dt.date(2026, 11, 16)
        self.asked = []

    def write(self, t, findings):
        self.asked.append("write")
        return talk(), "m"

    def review(self, t, draft, second=False):
        self.asked.append("second review" if second else "review")
        return PASS, "m"

    def cut_short(self, t, draft, second=False):
        if second:
            raise ai.AIUnavailable("This run has used up its time for AI calls. The next run carries on.")
        return self.review(t, draft)

    def saved_steps(self):
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM zeroharm_cache WHERE cache_key LIKE %s", ["%monday-step:%"])
            return cursor.fetchone()[0]

    def test_the_next_run_carries_on_from_the_step_it_had_reached(self):
        with self.assertRaises(ai.AIUnavailable):
            g.generate_week(self.week, write_fn=self.write, review_fn=self.cut_short, strict=True)
        self.assertEqual(self.asked, ["write", "review"])
        self.assertFalse(MondayMinute.objects.exists())
        m = g.generate_week(self.week, write_fn=self.write, review_fn=self.review, strict=True)
        self.assertEqual(self.asked, ["write", "review", "second review"])  # used to start over: write, review, second review
        self.assertEqual((m.status, m.attempts, m.title), (MondayMinute.READY, 1, talk()["title"]))
        self.assertIn("passed both independent CSP reviews", m.check_log)
        self.assertEqual(self.saved_steps(), 0)  # nothing is kept once the talk is saved

    def test_a_kept_review_is_never_used_for_a_different_draft(self):
        from django.core.cache import caches

        shared = caches["shared"]
        with patch.object(shared, "set", wraps=shared.set) as sets:
            with self.assertRaises(ai.AIUnavailable):
                g.generate_week(self.week, write_fn=self.write, review_fn=self.cut_short, strict=True)
        draft = next(c[0][0] for c in sets.call_args_list if c[0][0].startswith("monday-step:"))  # the first step kept: the draft
        shared.delete(draft)  # the kept draft is lost (expired) while its review is still there
        reviewed = []

        def another_draft(t, findings):
            return talk(takeaway="Lock, tag and try. Every time."), "m"

        def review(t, draft, second=False):
            reviewed.append((draft["takeaway"], second))
            return PASS, "m"

        m = g.generate_week(self.week, write_fn=another_draft, review_fn=review, strict=True)
        self.assertEqual(reviewed, [("Lock, tag and try. Every time.", False), ("Lock, tag and try. Every time.", True)])
        self.assertEqual(m.takeaway, "Lock, tag and try. Every time.")

    def test_a_changed_brief_starts_over(self):
        with self.assertRaises(ai.AIUnavailable):
            g.generate_week(self.week, write_fn=self.write, review_fn=self.cut_short, strict=True)
        self.t.must_say = ["Never remove someone else's lock.", "Try the start button."]
        self.t.save()
        with self.assertRaises(ai.AIUnavailable):
            g.generate_week(self.week, write_fn=self.write, review_fn=self.cut_short, strict=True)
        self.assertEqual(self.asked.count("write"), 2)  # the draft from the old brief was not reused

    def test_a_blocked_topic_keeps_nothing(self):
        failing = {"verdict": "fail", "findings": [{"severity": "must_fix", "where": "point 2", "issue": "Unsafe.", "fix": "Say X."}],
                   "grounding": PASS["grounding"], "confidence": "high"}
        with self.assertLogs("monday.generate", "WARNING"):
            m = g.generate_week(self.week, write_fn=self.write, review_fn=lambda t, d, **kw: (failing, "m"), strict=False)
        self.assertEqual(m.status, MondayMinute.BLOCKED)
        self.assertEqual(self.saved_steps(), 0)


# ---- One talk per week ------------------------------------------------------------------------------------

@override_settings(MONDAY_GATE=False)
class OneTalkPerWeekTests(TestCase):
    def setUp(self):
        MondayTopic.objects.all().delete()
        self.t = topic()
        self.week = dt.date(2026, 11, 16)

    def test_the_database_refuses_a_second_talk_for_a_week(self):
        minute(self.t, self.week)
        minute(self.t, self.week, MondayMinute.BLOCKED)  # blocked drafts don't count: a week may have two
        minute(self.t, self.week, MondayMinute.BLOCKED)
        for status in (MondayMinute.READY, MondayMinute.HELD, MondayMinute.PULLED):
            with self.assertRaises(IntegrityError), transaction.atomic():
                minute(self.t, self.week, status)
        minute(self.t, self.week + dt.timedelta(days=7))  # another week is fine

    def test_a_second_writer_finishing_later_adds_nothing(self):
        def write(t, findings):
            # While this writer is still working, another one saves the week's talk.
            MondayMinute.objects.get_or_create(week=self.week, status=MondayMinute.READY,
                                               defaults=dict(publish_at=g.publish_time(self.week), topic=t, title="Theirs"))
            return talk(), "m"

        with self.assertLogs("monday.generate", "WARNING") as logs:
            self.assertIsNone(g.generate_week(self.week, write_fn=write, review_fn=lambda t, d, **kw: (PASS, "x"), strict=False))
        self.assertIn("another run saved this week's talk first", logs.output[0])
        self.assertEqual(list(MondayMinute.objects.filter(week=self.week).values_list("title", flat=True)), ["Theirs"])

    def test_migration_sets_aside_duplicates_that_already_exist(self):
        migration = importlib.import_module("monday.migrations.0008_lock_owner_gate_pending_screen_failures")
        from django.apps import apps

        with connection.cursor() as cursor:
            cursor.execute('DROP INDEX "one_talk_per_week"')  # as the table was before the rule; rolled back with the test
        pulled = minute(self.t, self.week, MondayMinute.PULLED)
        first = minute(self.t, self.week, title="First")
        second = minute(self.t, self.week, title="Second")
        approved = minute(self.t, self.week, MondayMinute.HELD, approved_by_person=True)
        blocked = minute(self.t, self.week, MondayMinute.BLOCKED)
        alone = minute(self.t, self.week + dt.timedelta(days=7), MondayMinute.HELD)
        migration.set_aside_duplicate_weeks(apps, None)
        for m in (pulled, first, second, approved, blocked, alone):
            m.refresh_from_db()
        self.assertEqual(first.status, MondayMinute.READY)  # the published one written first is kept
        self.assertEqual([m.status for m in (pulled, second, approved)], [MondayMinute.BLOCKED] * 3)
        self.assertIn(f"Talk {first.pk} is the one kept", second.check_log)
        self.assertEqual((blocked.status, blocked.check_log, alone.status), (MondayMinute.BLOCKED, "", MondayMinute.HELD))
        self.assertEqual(MondayMinute.objects.filter(week=self.week).exclude(status=MondayMinute.BLOCKED).count(), 1)

    def test_migration_marks_talks_that_are_not_out_yet(self):
        migration = importlib.import_module("monday.migrations.0008_lock_owner_gate_pending_screen_failures")
        from django.apps import apps

        soon = timezone.now() + dt.timedelta(days=3)
        ahead = minute(self.t, dt.date(2026, 11, 16), publish_at=soon)
        approved = minute(self.t, dt.date(2026, 11, 23), publish_at=soon, approved_by_person=True)
        out = minute(self.t, dt.date(2026, 11, 9))
        migration.mark_talks_not_out_yet(apps, None)
        self.assertEqual([MondayMinute.objects.get(pk=m.pk).gate_pending for m in (ahead, approved, out)], [True, False, False])


# ---- The safety gate at the moment of publishing ------------------------------------------------------------

@override_settings(SECRET_KEY="test", AI_PROVIDER="anthropic")
class GateAtPublishTests(TestCase):
    def setUp(self):
        cache.clear()
        MondayTopic.objects.all().delete()
        self.t = topic()
        self.week = g.next_week()

    def write(self):
        return g.generate_week(self.week, write_fn=lambda t, f: (talk(), "m"), review_fn=lambda t, d, **kw: (PASS, "x"), strict=False)

    def reach_publish_time(self, m):
        MondayMinute.objects.filter(pk=m.pk).update(publish_at=timezone.now() - dt.timedelta(minutes=1))

    def listed(self):
        return [m["id"] for m in self.client.get("/api/v2/monday-minute").json()["minutes"]]

    def test_a_talk_does_not_go_out_if_the_gate_closed_after_it_was_written(self):
        passing_run(finished_at=timezone.now() - dt.timedelta(days=2))
        m = self.write()
        self.assertEqual(m.status, MondayMinute.READY)
        passing_run(passed=False, verdict="caught 60%")  # the setup lost its pass, and no cron step ran in between
        self.reach_publish_time(m)
        self.assertEqual(self.listed(), [])
        m.refresh_from_db()
        self.assertEqual(m.status, MondayMinute.HELD)
        self.assertIn("moved back to waiting for approval", m.check_log)
        self.assertIn("caught 60%", m.check_log)
        self.assertEqual(self.client.get(f"/api/v2/monday-minute/{m.pk}").status_code, 404)

    def test_the_detail_endpoint_checks_the_gate_too(self):
        passing_run(finished_at=timezone.now() - dt.timedelta(days=2))
        m = self.write()
        passing_run(passed=False, verdict="caught 60%")
        self.reach_publish_time(m)
        self.assertEqual(self.client.get(f"/api/v2/monday-minute/{m.pk}").status_code, 404)
        self.assertEqual(MondayMinute.objects.get(pk=m.pk).status, MondayMinute.HELD)
        res = self.client.post(f"/api/v2/monday-minute/{m.pk}/feedback", json.dumps({"install_id": INSTALL, "helpful": True}),
                               content_type="application/json")
        self.assertEqual(res.status_code, 404)

    def test_with_the_gate_open_the_talk_goes_out_and_stays_out(self):
        passing_run(finished_at=timezone.now() - dt.timedelta(days=2))
        m = self.write()
        self.assertFalse(MondayMinute.objects.released().exists())  # not before its publish time
        self.reach_publish_time(m)
        self.assertFalse(MondayMinute.objects.released().exists())  # and not before the gate has had its last word
        self.assertEqual(self.listed(), [m.pk])
        self.assertTrue(MondayMinute.objects.released().filter(pk=m.pk).exists())
        with self.assertNumQueries(1):  # once it is out, the list is back to one query
            self.assertEqual(self.listed(), [m.pk])
        passing_run(passed=False, verdict="caught 60%")  # a later failed test does not take back a talk that is out
        self.assertEqual(self.listed(), [m.pk])
        self.assertEqual(self.client.get(f"/api/v2/monday-minute/{m.pk}").status_code, 200)

    def test_a_talk_a_person_approved_goes_out_whatever_the_gate_says(self):
        m = minute(self.t, self.week, gate_pending=True, approved_by_person=True)  # no safety test on record
        self.assertEqual(self.listed(), [m.pk])
        self.assertEqual(self.client.get(f"/api/v2/monday-minute/{m.pk}").status_code, 200)
        self.assertEqual(gate.release_due(), (1, 0))
        self.assertEqual(MondayMinute.objects.get(pk=m.pk).status, MondayMinute.READY)

    def test_the_cron_step_gives_the_gate_its_last_word_before_the_push(self):
        passing_run(finished_at=timezone.now() - dt.timedelta(days=2))
        m = self.write()
        passing_run(passed=False, verdict="caught 60%")
        self.reach_publish_time(m)
        out, pushed = StringIO(), []
        with patch(f"{CRON}.send_minute_push", lambda m: (pushed.append(m.pk), (True, ""))[1]), \
                patch(f"{CRON}.due_week", lambda: None), patch(f"{CRON}.ai.available", lambda: False):
            call_command("monday_minute", stdout=out)
        self.assertEqual(pushed, [])
        self.assertEqual(MondayMinute.objects.get(pk=m.pk).status, MondayMinute.HELD)
        self.assertIn("1 talk(s) moved back to waiting for approval", out.getvalue())

    def test_holding_a_talk_early_leaves_it_ready_for_a_persons_approval(self):
        passing_run(finished_at=timezone.now() - dt.timedelta(days=2))
        m = self.write()
        passing_run(passed=False, verdict="caught 60%")
        self.assertEqual(gate.hold_unpublished(), 1)
        m.refresh_from_db()
        self.assertEqual((m.status, m.gate_pending), (MondayMinute.HELD, False))


# ---- Rate limits and the "different networks" rule ----------------------------------------------------------

@override_settings(SECRET_KEY="test", AI_PROVIDER="anthropic")
class NetworkTests(TestCase):
    def setUp(self):
        cache.clear()
        self.t = topic()
        self.m = minute(self.t)

    def post(self, path, body, ip="198.51.100.77", **headers):
        return self.client.post(f"/api/v2/monday-minute{path}", json.dumps(body), content_type="application/json",
                                HTTP_X_FORWARDED_FOR=ip, **headers)

    def from_railway(self, path, body, caller, n=0):
        """Headers as Railway's edge sends them: the caller in X-Real-IP, and an edge address of its own, different
        from request to request, last in X-Forwarded-For."""
        return self.post(path, body, ip=f"{caller}, 100.64.0.{n % 250 + 1}", HTTP_X_REAL_IP=caller)

    def comment(self, **kw):
        return {"install_id": INSTALL, "body": "We keep locks by the panel.", "accepted_rules": True, **kw}

    def test_thumbs_do_not_use_up_comments_reports_or_otis_ratings(self):
        with patch("monday.moderation.ai_check", return_value=(True, "")):
            first = self.post(f"/{self.m.pk}/comments", self.comment()).json()["comment"]["id"]
            for i in range(31):  # a crew on one plant Wi-Fi rates the talk
                self.assertEqual(self.post(f"/{self.m.pk}/feedback", {"install_id": f"{INSTALL}-{i}", "helpful": True}).status_code, 200)
            self.assertEqual(self.post(f"/{self.m.pk}/comments", self.comment()).status_code, 201)  # was 429 after ten thumbs
        self.assertEqual(self.post(f"/comments/{first}/report", {"install_id": INSTALL + "r"}).status_code, 200)  # was 429 after thirty
        otis = self.client.post("/api/v2/otis/feedback", json.dumps({"helpful": True, "question": "What is LOTO?"}),
                                content_type="application/json", HTTP_X_FORWARDED_FOR="198.51.100.77")
        self.assertNotEqual(otis.status_code, 429)

    def test_each_limit_still_holds_on_its_own(self):
        with patch("monday.moderation.ai_check", return_value=(True, "")):
            codes = [self.post(f"/{self.m.pk}/comments", self.comment()).status_code for _ in range(11)]
        self.assertEqual(codes, [201] * 10 + [429])
        self.assertEqual(self.post(f"/{self.m.pk}/feedback", {"install_id": INSTALL, "helpful": True}).status_code, 200)

    def test_one_ipv6_connection_is_one_network_for_the_limits(self):
        with patch("monday.moderation.ai_check", return_value=(True, "")):
            codes = [self.from_railway(f"/{self.m.pk}/comments", self.comment(), f"2001:db8:abcd:12::{i + 1:x}", i).status_code
                     for i in range(11)]  # eleven addresses inside one /64
            self.assertEqual(codes, [201] * 10 + [429])
            other = self.from_railway(f"/{self.m.pk}/comments", self.comment(), "2001:db8:abcd:13::1", 11)
        self.assertEqual(other.status_code, 201)  # the next /64 is someone else

    def report(self, i, caller):
        return self.from_railway(f"/{self.m.pk}/feedback", {"install_id": f"{INSTALL}-{i}", "helpful": False, "reasons": ["unsafe"]}, caller, i)

    def test_one_ipv6_connection_cannot_pull_a_talk_alone(self):
        for i in range(3):  # three made-up phones on three addresses of one home connection
            self.assertEqual(self.report(i, f"2001:db8:abcd:12::{i + 1}").status_code, 200)
        self.m.refresh_from_db()
        self.t.refresh_from_db()
        self.assertEqual((self.m.status, self.t.active), (MondayMinute.READY, True))
        self.assertEqual(MondayFeedback.objects.values("network_hash").distinct().count(), 1)
        # Three really different networks still pull it: one more IPv6 connection and one IPv4 site.
        self.report(10, "2001:db8:abcd:99::1")
        with self.assertLogs("monday.api", "WARNING") as logs:
            self.report(11, "203.0.113.50")
        self.m.refresh_from_db()
        self.t.refresh_from_db()
        self.assertEqual((self.m.status, self.t.active), (MondayMinute.PULLED, False))
        self.assertIn("was pulled", logs.output[0])

    def test_no_address_is_stored_readable(self):
        self.report(0, "2001:db8:abcd:12::1")
        stored = MondayFeedback.objects.get().network_hash
        self.assertEqual(len(stored), 64)
        self.assertNotIn("2001", stored[:4])


# ---- Counts ---------------------------------------------------------------------------------------------

class CountTests(TestCase):
    def test_counts_are_right_and_never_join_ratings_to_comments(self):
        t = topic()
        m, quiet = minute(t), minute(t, dt.date(2026, 11, 2))
        for i in range(5):
            MondayFeedback.objects.create(minute=m, install_hash=f"h{i}", helpful=i < 3)
        for status in (MondayComment.VISIBLE,) * 4 + (MondayComment.PENDING, MondayComment.HIDDEN):
            MondayComment.objects.create(minute=m, body="hi", install_hash="x", status=status)
        rows = MondayMinute.objects.with_counts()
        got = {r.pk: (r._up, r._down, r._comments) for r in rows}
        self.assertEqual(got, {m.pk: (3, 2, 4), quiet.pk: (0, 0, 0)})
        # Joining both tables to the talk made the database build ratings x comments rows before counting.
        self.assertNotIn("JOIN", str(rows.query).upper())
        self.assertEqual((m.as_api()["thumbs_up"], m.as_api()["comment_count"]), (3, 4))


# ---- Text a phone sends -----------------------------------------------------------------------------------

@override_settings(SECRET_KEY="test", AI_PROVIDER="anthropic")
class TextTests(TestCase):
    def setUp(self):
        cache.clear()
        self.t = topic()
        self.m = minute(self.t)

    def post(self, path, body):
        return self.client.post(f"/api/v2/monday-minute{path}", json.dumps(body), content_type="application/json")

    def comment(self, body, **kw):
        with patch("monday.moderation.ai_check", return_value=(True, "")):
            return self.post(f"/{self.m.pk}/comments", {"install_id": INSTALL, "body": body, "accepted_rules": True, **kw})

    def test_nul_and_control_characters_never_reach_the_database(self):
        # PostgreSQL refuses a NUL in text and the phone got a 500. They are dropped before anything is saved.
        r = self.post(f"/{self.m.pk}/feedback", {"install_id": INSTALL, "helpful": False, "reasons": ["confusing"], "note": "nul\u0000byte\u0007 "})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(MondayFeedback.objects.get().note, "nulbyte")
        r = self.comment("We lock\u0000 out at the panel.\nEvery time.", display_name="Dock\u0000 lead")
        self.assertEqual(r.status_code, 201)
        c = MondayComment.objects.get()
        self.assertEqual((c.body, c.display_name), ("We lock out at the panel.\nEvery time.", "Dock lead"))  # line breaks stay
        self.assertEqual(self.post(f"/comments/{c.pk}/report", {"install_id": INSTALL + "r", "reason": "sp\u0000am"}).status_code, 200)
        self.assertEqual(MondayCommentReport.objects.get().reason, "spam")

    def test_half_an_emoji_is_dropped_and_whole_ones_stay(self):
        # "\ud83d" alone is the first half of an emoji a keyboard cut in two; the database cannot store it.
        with patch("monday.moderation.ai_check", return_value=(True, "")):
            r = self.client.post(f"/api/v2/monday-minute/{self.m.pk}/comments",
                                 json.dumps({"install_id": INSTALL, "body": "Good talk 👍🏽 \ud83d", "accepted_rules": True}),
                                 content_type="application/json")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(MondayComment.objects.get().body, "Good talk 👍🏽")

    def test_a_comment_of_only_spaces_is_refused(self):
        self.assertEqual(self.comment(" " * 23).status_code, 422)   # used to be saved with an empty body
        self.assertEqual(self.comment("\u0000\u0000\u0000").status_code, 422)
        self.assertEqual(self.comment("  a  ").status_code, 422)    # one character once trimmed
        self.assertFalse(MondayComment.objects.exists())
        self.assertEqual(self.comment("  ok  ").status_code, 201)
        self.assertEqual(MondayComment.objects.get().body, "ok")


# ---- Comment screening --------------------------------------------------------------------------------------

class ScreeningTests(TestCase):
    def setUp(self):
        self.t = topic()
        self.m = minute(self.t)

    def waiting(self, body):
        return MondayComment.objects.create(minute=self.m, body=body, install_hash="x")

    def test_one_comment_the_ai_cannot_answer_for_does_not_block_the_rest(self):
        asked = []

        def check(body, name, title):
            asked.append(body)
            if body == "stuck":
                raise ai.GenerationError("The local model ran out of room before finishing.")
            return True, ""

        stuck, second, third = self.waiting("stuck"), self.waiting("second"), self.waiting("third")
        with patch("monday.moderation.ai_check", check):
            self.assertEqual(api.screen_pending(), 2)  # used to stop at the first one: 0, on every run
            self.assertEqual(asked, ["stuck", "second", "third"])
            stuck.refresh_from_db()
            self.assertEqual((stuck.status, stuck.screen_failures), (MondayComment.PENDING, 1))
            self.assertEqual(MondayComment.objects.filter(status=MondayComment.VISIBLE).count(), 2)
            fourth = self.waiting("fourth")
            self.assertEqual(api.screen_pending(), 1)
            self.assertEqual(api.screen_pending(), 0)
        stuck.refresh_from_db()
        fourth.refresh_from_db()
        self.assertEqual((stuck.status, stuck.screen_failures), (MondayComment.HIDDEN, 3))  # never shown unchecked; a person looks
        self.assertIn("Review in the admin", stuck.moderation)
        self.assertEqual(fourth.status, MondayComment.VISIBLE)
        self.assertEqual(asked.count("stuck"), 3)

    def test_an_outage_stops_the_run_and_counts_against_no_comment(self):
        asked = []

        def down(body, name, title):
            asked.append(body)
            raise ai.AIUnavailable("Local AI server unavailable: timed out")

        for body in ("one", "two", "three"):
            self.waiting(body)
        with patch("monday.moderation.ai_check", down):
            self.assertEqual(api.screen_pending(), 0)
        self.assertEqual(asked, ["one"])  # one timeout per run, not one per waiting comment
        self.assertEqual(set(MondayComment.objects.values_list("status", "screen_failures")), {(MondayComment.PENDING, 0)})

    def test_an_admin_decision_made_during_the_check_is_kept(self):
        c = self.waiting("hidden by a person while the AI was thinking")

        def check(body, name, title):
            MondayComment.objects.filter(pk=c.pk).update(status=MondayComment.HIDDEN, moderation="Hidden in the admin")
            return True, ""

        with patch("monday.moderation.ai_check", check):
            api.screen_one(c.pk)
        c.refresh_from_db()
        self.assertEqual((c.status, c.moderation), (MondayComment.HIDDEN, "Hidden in the admin"))

    def test_no_database_connection_is_held_while_the_ai_is_asked(self):
        c = self.waiting("We lock out at the panel.")
        closed_before_the_call = []
        conn = MagicMock(in_atomic_block=False)  # as in the web worker or the cron: no transaction open

        def check(body, name, title):
            closed_before_the_call.append(conn.close.called)
            return True, ""

        with patch.object(api, "connection", conn), patch("monday.moderation.ai_check", check):
            self.assertTrue(api.screen_one(c.pk))
        self.assertEqual(closed_before_the_call, [True])
        c.refresh_from_db()
        self.assertEqual(c.status, MondayComment.VISIBLE)

    @override_settings(AI_PROVIDER="local", LOCAL_AI_URL="http://ollama.test:11434")
    def test_one_background_worker_however_many_comments_wait(self):
        started, let_go, calls = threading.Event(), threading.Event(), []

        def slow(*args, **kw):  # an AI server that does not answer
            calls.append(1)
            started.set()
            let_go.wait(5)
            return 0

        def idle():
            deadline = time.monotonic() + 5
            while api._screening.locked() and time.monotonic() < deadline:
                time.sleep(0.01)
            return not api._screening.locked()

        before = set(threading.enumerate())
        with patch.object(api, "screen_pending", slow), patch.object(api, "screen_one", slow):
            for pk in range(8):  # eight comments arrive while the AI is stuck
                api._screen_soon(pk)
            self.assertTrue(started.wait(5))
            workers = [t for t in threading.enumerate() if t not in before]
            self.assertEqual(len(workers), 1)  # used to be one thread, and one connection, per comment
            self.assertEqual(len(calls), 1)
            let_go.set()
            self.assertTrue(idle())
            api._screen_soon(99)  # a comment that arrives after the worker finished starts it again
            self.assertTrue(idle())
            self.assertEqual(len(calls), 2)


# ---- AI time ----------------------------------------------------------------------------------------------

@override_settings(AI_PROVIDER="local", LOCAL_AI_URL="http://ollama.test:11434", LOCAL_AI_MODEL="qwen3:8b", LOCAL_AI_TIMEOUT=1800.0)
class AiTimeTests(TestCase):
    def setUp(self):
        self.timeouts = []

    def server(self, req, timeout):
        self.timeouts.append(timeout)
        res = MagicMock()
        res.__enter__.return_value = BytesIO(json.dumps(
            {"model": "qwen3:8b", "done_reason": "stop", "message": {"content": '{"allow": true, "rule": "", "message": ""}'}}).encode())
        return res

    def test_a_comment_check_does_not_wait_as_long_as_a_talk(self):
        with patch("urllib.request.urlopen", self.server):
            self.assertEqual(moderation.ai_check("We lock out at the panel.", "Dock lead", "Lockout"), (True, ""))
            ai.ai_json("s", "u", {}, role="review")
            with override_settings(LOCAL_AI_FAST_TIMEOUT=45.0):
                moderation.ai_check("Same here.", "Dock lead", "Lockout")
            with override_settings(LOCAL_AI_TIMEOUT=20.0):  # never longer than the general timeout
                moderation.ai_check("Same here.", "Dock lead", "Lockout")
        self.assertEqual(self.timeouts, [180.0, 1800.0, 45.0, 20.0])  # the first used to be 1800 too

    def test_calls_inside_a_time_budget_share_one_deadline(self):
        clock = [1000.0]
        with patch("monday.ai.time", SimpleNamespace(monotonic=lambda: clock[0])), patch("urllib.request.urlopen", self.server):
            with ai.time_budget(600):
                ai.ai_json("s", "u", {})
                clock[0] += 400
                ai.ai_json("s", "u", {})
                clock[0] += 250  # 650 s gone: the budget is used up
                with self.assertRaises(ai.AIUnavailable):
                    ai.ai_json("s", "u", {})
                with ai.time_budget(5000):  # a budget inside another cannot extend it
                    with self.assertRaises(ai.AIUnavailable):
                        ai.ai_json("s", "u", {})
            ai.ai_json("s", "u", {})  # outside the budget: the usual timeout again
            with ai.time_budget(0):   # 0 = no limit
                ai.ai_json("s", "u", {})
        self.assertEqual(self.timeouts, [600.0, 200.0, 1800.0, 1800.0])  # the refused calls never reached the server

    @override_settings(MONDAY_GATE=False)
    def test_a_write_that_runs_out_of_time_records_nothing(self):
        MondayTopic.objects.all().delete()
        topic()
        week, clock = dt.date(2026, 11, 16), [1000.0]

        def server(req, timeout):  # the writer answers, slowly; there is no time left for the review
            clock[0] += 900
            res = MagicMock()
            res.__enter__.return_value = BytesIO(json.dumps({"done_reason": "stop", "message": {"content": json.dumps(talk())}}).encode())
            return res

        with patch("monday.ai.time", SimpleNamespace(monotonic=lambda: clock[0])), patch("urllib.request.urlopen", server), \
                override_settings(MONDAY_RAG=False):
            with ai.time_budget(600), self.assertRaises(ai.AIUnavailable):
                g.generate_week(week)
        self.assertFalse(MondayMinute.objects.filter(week=week).exists())  # not a failed draft: the next run tries again
        self.assertEqual(g.due_week(dt.datetime(2026, 11, 12, tzinfo=UTC)), week)

    @override_settings(AI_PROVIDER="anthropic")
    def test_a_time_budget_caps_claude_calls_too(self):
        res = SimpleNamespace(stop_reason="end_turn", model="claude-opus-5-5", content=[SimpleNamespace(type="text", text='{"a": 1}')])
        options = []
        client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=lambda **kw: res)))
        client.with_options = lambda **kw: options.append(kw) or client
        with patch.object(ai, "_client", return_value=client):
            with ai.time_budget(30):
                ai.claude_json("s", "u", {}, "high")
        self.assertTrue(0 < options[0]["timeout"] <= 30)


# ==== Round two: what the re-check of the fixes above found ==================================================

class OneSignal:
    """Stands in for OneSignal the way its pages describe an idempotency key: a request whose key it has seen before
    gets the first answer back and no second notification. `lose` answers are lost on the way back (the request
    arrived and went out to phones, but the cron saw a timeout)."""

    def __init__(self, lose=0):
        self.lose, self.requests, self.delivered, self.seen = lose, [], [], set()

    def post(self, url, headers, payload, timeout=10):  # same arguments as talks.integrations._post
        key = payload.get("idempotency_key")
        self.requests.append(key)
        if key is None or key not in self.seen:
            self.delivered.append(payload["data"])
        self.seen.add(key)
        if self.lose:
            self.lose -= 1
            return 0, {"error": "TimeoutError: The read operation timed out"}
        return 200, {"id": "notification-1"}


def quiet_step():
    """Runs the cron step with nothing to write and no AI, so only its quick jobs run. Returns what it printed."""
    out = StringIO()
    with patch(f"{CRON}.due_week", lambda: None), patch(f"{CRON}.ai.available", lambda: False):
        call_command("monday_minute", stdout=out)
    return out.getvalue()


# ---- The Monday push goes out once ------------------------------------------------------------------------

@override_settings(ONESIGNAL_APP_ID="test-app", ONESIGNAL_REST_API_KEY="test-key", MONDAY_GATE=False)
class PushOnceTests(TestCase):
    def setUp(self):
        MondayTopic.objects.all().delete()
        self.m = minute(topic())
        self.onesignal = OneSignal()
        stand_in = patch("talks.integrations._post", self.onesignal.post)
        stand_in.start()
        self.addCleanup(stand_in.stop)

    def test_a_push_onesignal_took_but_whose_answer_was_lost_is_not_sent_again(self):
        self.onesignal.lose = 2
        for run in range(4):  # four cron runs: the answer is lost twice, then OneSignal is heard
            quiet_step()
        self.assertEqual(self.onesignal.delivered, [{"monday_minute": self.m.pk}])  # used to be three notifications on every phone
        self.assertEqual(len(self.onesignal.requests), 3)                           # run 4 had nothing left to send
        self.assertEqual(len(set(self.onesignal.requests)), 1)                      # one push, one key, every try
        self.assertIsNotNone(self.onesignal.requests[0])
        self.m.refresh_from_db()
        self.assertIsNotNone(self.m.push_sent_at)

    def test_sending_it_again_on_purpose_is_a_new_push(self):
        self.assertTrue(push.send_minute_push(self.m)[0])
        self.assertTrue(push.send_minute_push(self.m)[0])  # by hand, after it was marked sent
        self.assertEqual(len(self.onesignal.delivered), 2)
        self.assertEqual(len(set(self.onesignal.requests)), 2)

    def test_the_push_pass_other_jobs_can_call(self):
        ahead = minute(topic("ladders"), g.next_week(), publish_at=g.publish_time(g.next_week()))
        self.assertEqual(push.send_due(), [f"Monday Minute push {self.m.week}: OK"])  # the talk that is out; not the one still ahead
        self.assertEqual(push.send_due(), [])
        self.assertEqual(self.onesignal.delivered, [{"monday_minute": self.m.pk}])
        ahead.refresh_from_db()
        self.assertIsNone(ahead.push_sent_at)

    @override_settings(MONDAY_MINUTE_ENABLED=False, MONDAY_GATE=True)
    def test_the_push_pass_sends_nothing_while_monday_minute_is_off_but_the_gate_still_speaks(self):
        ahead = minute(topic("ladders"), g.next_week(), publish_at=g.publish_time(g.next_week()))  # no safety test on record
        lines = push.send_due()
        self.assertEqual(len(lines), 1)
        self.assertIn("moved back to waiting for approval", lines[0])
        self.assertEqual(self.onesignal.requests, [])
        ahead.refresh_from_db()
        self.assertEqual(ahead.status, MondayMinute.HELD)


# ---- A step the AI cannot answer is remembered, asked once more differently, then left alone ----------------

CUT_OFF = "The local model ran out of room before finishing."


@override_settings(MONDAY_GATE=False, MONDAY_RAG=False)
class FailedStepTests(TestCase):
    def setUp(self):
        MondayTopic.objects.all().delete()
        self.t = topic()
        self.week = dt.date(2026, 11, 16)

    def saved_steps(self):
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM zeroharm_cache WHERE cache_key LIKE %s", ["%monday-step:%"])
            return cursor.fetchone()[0]

    def test_a_write_with_cut_off_reviews_still_finishes_under_the_time_ceiling(self):
        # The case that never finished: 30 minutes of AI time per run, a draft takes 8 minutes, a review 12, and the
        # review of each of the first two drafts is cut off however often it is asked. Every run asked for both
        # cut-off reviews again (24 minutes) and had no time left to get any further.
        clock, answered, drafts = [0.0], [], []

        def spend(seconds):  # what ai._ollama does with its timeout
            allowed = ai._time_for(1800)
            if seconds > allowed:
                clock[0] += allowed
                raise ai.AIUnavailable("Local AI server unavailable: timed out")
            clock[0] += seconds

        def write(t, findings):
            spend(8 * 60)
            drafts.append(talk(takeaway="Your lock, your key, your life. " + "Every time. " * (len(drafts) + 1)))
            return drafts[-1], "m"

        def review(t, draft, second=False):
            spend(12 * 60)
            answered.append((drafts.index(draft), second))
            if not second and drafts.index(draft) < 2:
                raise ai.GenerationError(CUT_OFF)
            return PASS, "m"

        m, runs = None, 0
        with patch("monday.ai.time", SimpleNamespace(monotonic=lambda: clock[0])):
            while m is None and runs < 12:  # twelve cron runs
                runs += 1
                try:
                    with ai.time_budget(1800):
                        m = g.generate_week(self.week, write_fn=write, review_fn=review, strict=True)
                except ai.AIUnavailable:
                    pass  # out of time: the next run carries on
        self.assertIsNotNone(m, "never written in twelve runs")
        self.assertEqual((m.status, m.attempts), (MondayMinute.READY, 3))
        self.assertLessEqual(runs, 6)
        for draft in (0, 1):  # asked, asked again, then never again
            self.assertEqual(answered.count((draft, False)), g.STEP_TRIES)
        self.assertEqual(len(drafts), 3)  # no draft was written twice
        self.assertIn(f"Attempt 1: {g.NO_ANSWER} for the review in 2 tries, so it was not asked again. Last reason: {CUT_OFF}", m.check_log)
        self.assertEqual(self.saved_steps(), 0)

    def test_a_failed_step_is_remembered_between_runs_and_never_asked_a_third_time(self):
        plan = iter(["cut off", "out of time",   # run 1: the review fails, and the run ends while it is asked again
                     "cut off", "out of time",   # run 2: it fails again and is given up; the review of the next draft is cut short
                     "pass"])                    # run 3
        written, reviewed = [], []

        def write(t, findings):
            written.append(talk(takeaway="Your lock, your key, your life. " + "Every time. " * (len(written) + 1)))
            return written[-1], "m"

        def review(t, draft, second=False):
            what = next(plan)
            reviewed.append((written.index(draft), what))
            if what == "cut off":
                raise ai.GenerationError(CUT_OFF)
            if what == "out of time":
                raise ai.AIUnavailable("This run has used up its time for AI calls. The next run carries on.")
            return PASS, "m"

        for run in (1, 2):
            with self.assertRaises(ai.AIUnavailable):
                g.generate_week(self.week, write_fn=write, review_fn=review, strict=False)
            self.assertFalse(MondayMinute.objects.exists())
        m = g.generate_week(self.week, write_fn=write, review_fn=review, strict=False)
        self.assertEqual(reviewed, [(0, "cut off"), (0, "out of time"), (0, "cut off"), (1, "out of time"), (1, "pass")])
        self.assertEqual(len(written), 2)  # run 3 asked the AI for one thing only: the review it had not finished
        self.assertEqual((m.status, m.attempts, m.takeaway), (MondayMinute.READY, 2, written[1]["takeaway"]))
        self.assertIn(g.NO_ANSWER, m.check_log)
        self.assertEqual(self.saved_steps(), 0)  # failures are cleared with the answers once the talk is saved

    def test_the_second_try_is_asked_differently(self):
        asked = []

        def fake(system, user, schema, **kw):
            asked.append((schema is g.TALK_SCHEMA, user, kw.get("seed")))
            if schema is g.REVIEW_SCHEMA and sum(1 for is_draft, _, _ in asked if not is_draft) == 1:
                raise ai.GenerationError(CUT_OFF)  # the same request would be cut off the same way: the review runs at temperature 0
            return (talk() if schema is g.TALK_SCHEMA else PASS), "m"

        with patch("monday.generate.ai_json", fake):
            m = g.generate_week(self.week, strict=False)
        first, again = [(user, seed) for is_draft, user, seed in asked if not is_draft]
        self.assertNotIn("COULD NOT BE USED", first[0])
        self.assertIn(f"YOUR LAST ANSWER TO THIS REQUEST COULD NOT BE USED: {CUT_OFF}", again[0])
        self.assertTrue(again[0].startswith(first[0]))  # the same brief and the same draft, plus the note
        self.assertNotEqual(first[1], again[1])         # and another seed
        self.assertEqual(sum(1 for is_draft, _, _ in asked if is_draft), 1)  # the draft was kept: no second write
        self.assertEqual((m.status, m.attempts), (MondayMinute.READY, 1))
        self.assertNotIn("COULD NOT BE USED", g.review(self.t, talk(), call=lambda s, u, sc, e: (u, "m"))[0])  # the note ends with the retry

    def test_a_second_independent_review_keeps_its_own_seed_when_asked_again(self):
        seeds = []

        def fake(system, user, schema, **kw):
            if schema is g.TALK_SCHEMA:
                return talk(), "m"
            seeds.append(kw.get("seed"))
            if len(seeds) in (1, 3):
                raise ai.GenerationError(CUT_OFF)
            return PASS, "m"

        with patch("monday.generate.ai_json", fake):
            m = g.generate_week(self.week, strict=True)
        self.assertEqual(m.status, MondayMinute.READY)
        self.assertEqual(len(set(seeds)), 4)  # first review, the same again, second review, the same again: all different

    def test_an_outage_is_not_a_failed_step(self):
        def down(t, draft, second=False):
            raise ai.AIUnavailable("Local AI server unavailable: connection refused")

        for run in range(5):
            with self.assertRaises(ai.AIUnavailable):
                g.generate_week(self.week, write_fn=lambda t, f: (talk(), "m"), review_fn=down, strict=False)
        m = g.generate_week(self.week, write_fn=lambda t, f: (talk(), "m"), review_fn=lambda t, d, **kw: (PASS, "m"), strict=False)
        self.assertEqual((m.status, m.attempts), (MondayMinute.READY, 1))  # five outages used up nothing
        self.assertNotIn(g.NO_ANSWER, m.check_log)

    @override_settings(AI_PROVIDER="anthropic", ANTHROPIC_API_KEY="test-key")
    def test_the_cron_step_stops_asking_and_says_so(self):
        asked = []

        def fake(system, user, schema, **kw):
            asked.append(schema is g.TALK_SCHEMA)
            if schema is g.TALK_SCHEMA:
                return talk(), "m"
            raise ai.GenerationError("The response was cut off.")

        def step():
            out = StringIO()
            with patch("monday.generate.ai_json", fake), patch(f"{CRON}.send_minute_push", lambda m: (True, "")), \
                    self.assertLogs("monday.generate", "WARNING"):
                call_command("monday_minute", week=self.week.isoformat(), stdout=out)
            return out.getvalue()

        said = step()
        blocked = MondayMinute.objects.get(week=self.week)
        self.assertEqual(blocked.status, MondayMinute.BLOCKED)
        self.assertEqual((asked.count(True), asked.count(False)), (3, 3 * g.STEP_TRIES))  # three drafts, each review asked twice
        self.assertEqual(blocked.check_log.count(g.NO_ANSWER), 3)
        self.assertIn("The response was cut off.", blocked.check_log)
        self.assertIn("Blocked by the safety checks", said)
        self.assertIn("In 3 of its attempts the AI gave no usable answer", said)
        self.assertEqual(self.saved_steps(), 0)
        with patch("monday.generate.ai_json", fake):  # the next run spends nothing more on it
            out = StringIO()
            call_command("monday_minute", week=self.week.isoformat(), stdout=out)
        self.assertEqual(len(asked), 9)
        self.assertIn("nothing to do", out.getvalue())


# ---- Waiting comments get a share of the step's time, the write keeps the rest ------------------------------

@override_settings(AI_PROVIDER="anthropic", ANTHROPIC_API_KEY="test-key", MONDAY_RAG=False, MONDAY_GATE=False)
class CommentShareTests(TestCase):
    def setUp(self):
        MondayTopic.objects.all().delete()
        self.t = topic()
        self.old = minute(self.t, dt.date(2026, 10, 26), push_sent_at=timezone.now())
        self.clock, self.takes = [5000.0], 100

    def slow_check(self, body, name, title):
        """A comment check that takes 100 seconds on a slow AI server, with the timeout a real one has."""
        allowed = ai._time_for(settings.LOCAL_AI_FAST_TIMEOUT)
        if allowed < self.takes:
            self.clock[0] += allowed
            raise ai.AIUnavailable("Local AI server unavailable: timed out")
        self.clock[0] += self.takes
        return True, ""

    def step(self, write):
        with patch("monday.ai.time", SimpleNamespace(monotonic=lambda: self.clock[0])), patch("monday.moderation.ai_check", self.slow_check), \
                patch(f"{CRON}.Command.write", write), patch(f"{CRON}.due_week", lambda: dt.date(2026, 11, 16)):
            call_command("monday_minute", stdout=StringIO())

    @override_settings(MONDAY_STEP_BUDGET=1800.0)
    def test_a_queue_of_comments_cannot_use_up_the_time_for_the_write(self):
        for i in range(20):
            MondayComment.objects.create(minute=self.old, body=f"comment {i}", install_hash="x")
        left = []
        self.step(lambda command, target: left.append(ai._time_for(10 ** 6)) and False)
        # Used to be 0: eighteen comments took the whole 30 minutes and the write was refused, run after run.
        self.assertGreaterEqual(left[0], 0.8 * 1800)
        self.assertEqual(MondayComment.objects.filter(status=MondayComment.VISIBLE).count(), 3)  # 360 s of comments
        self.assertEqual(MondayComment.objects.filter(status=MondayComment.PENDING, screen_failures=0).count(), 17)  # the rest wait, uncounted

    @override_settings(MONDAY_STEP_BUDGET=1800.0)
    def test_a_few_comments_are_all_screened(self):
        for i in range(3):
            MondayComment.objects.create(minute=self.old, body=f"comment {i}", install_hash="x")
        left = []
        self.step(lambda command, target: left.append(ai._time_for(10 ** 6)) and False)
        self.assertEqual(MondayComment.objects.filter(status=MondayComment.VISIBLE).count(), 3)
        self.assertEqual(left[0], 1500)  # the write gets everything the comments did not use

    @override_settings(MONDAY_STEP_BUDGET=600.0, LOCAL_AI_FAST_TIMEOUT=180.0)
    def test_with_a_small_ceiling_the_share_still_fits_one_whole_check(self):
        for i in range(20):
            MondayComment.objects.create(minute=self.old, body=f"comment {i}", install_hash="x")
        left, self.takes = [], 150
        self.step(lambda command, target: left.append(ai._time_for(10 ** 6)) and False)
        self.assertEqual(MondayComment.objects.filter(status=MondayComment.VISIBLE).count(), 1)  # a fifth (120 s) would have screened none
        self.assertGreaterEqual(left[0], 0.5 * 600)                                               # and the write still has most of it

    @override_settings(MONDAY_STEP_BUDGET=0)
    def test_no_ceiling_means_no_share_either(self):
        for i in range(20):
            MondayComment.objects.create(minute=self.old, body=f"comment {i}", install_hash="x")
        self.step(lambda command, target: False)
        self.assertEqual(MondayComment.objects.filter(status=MondayComment.VISIBLE).count(), 20)

    def test_the_two_time_settings_are_real_settings(self):
        # Read as settings.X by ai.py and the cron step, so both must exist (settings.py reads them from the environment).
        self.assertIsInstance(settings.MONDAY_STEP_BUDGET, float)
        self.assertIsInstance(settings.LOCAL_AI_FAST_TIMEOUT, float)


# ---- "No talk went out this week" only for a week that was meant to have one --------------------------------

THURSDAY = dt.datetime(2026, 11, 19, 20, 0, tzinfo=UTC)  # the late window for the week of Nov 16 is over
MISSED = dt.date(2026, 11, 16)


class MissedWeekTests(TestCase):
    def setUp(self):
        MondayTopic.objects.all().delete()
        self.t = topic()

    def test_a_database_with_no_talks_has_missed_nothing(self):
        self.assertIsNone(g.missed_week(THURSDAY))  # used to be Nov 16: a false alarm on the first run after every fresh deploy

    def test_the_week_the_feature_was_switched_on_is_not_missed(self):
        minute(self.t, dt.date(2026, 11, 23), publish_at=g.publish_time(dt.date(2026, 11, 23)))  # the first talk ever: next Monday's
        self.assertIsNone(g.missed_week(THURSDAY))

    def test_a_week_is_missed_when_monday_minute_was_running_before(self):
        earlier = minute(self.t, dt.date(2026, 11, 9))
        self.assertEqual(g.missed_week(THURSDAY), MISSED)
        MondayMinute.objects.filter(pk=earlier.pk).update(status=MondayMinute.PULLED)
        self.assertEqual(g.missed_week(THURSDAY), MISSED)  # it went out, so the feature was running
        MondayMinute.objects.filter(pk=earlier.pk).update(status=MondayMinute.BLOCKED)
        self.assertIsNone(g.missed_week(THURSDAY))  # a blocked draft weeks ago is not "a talk was due this week"

    def test_a_week_is_missed_when_a_write_was_started_for_it(self):
        g.note_attempt(dt.date(2026, 11, 9))
        self.assertIsNone(g.missed_week(THURSDAY))  # another week's attempt says nothing about this one
        g.note_attempt(MISSED)
        self.assertEqual(g.missed_week(THURSDAY), MISSED)

    def test_a_blocked_draft_shows_the_week_was_tried(self):
        minute(self.t, MISSED, MondayMinute.BLOCKED)
        self.assertEqual(g.missed_week(THURSDAY), MISSED)

    def test_a_write_that_never_got_an_answer_counts_as_tried(self):
        def down(t, findings):
            raise ai.AIUnavailable("Local AI server unavailable: connection refused")

        with self.assertRaises(ai.AIUnavailable):
            g.generate_week(MISSED, write_fn=down, review_fn=None, strict=False)
        self.assertEqual(g.missed_week(THURSDAY), MISSED)

    def test_a_talk_that_went_out_or_waits_for_approval_is_not_missed(self):
        minute(self.t, dt.date(2026, 11, 9))
        for status in (MondayMinute.READY, MondayMinute.HELD, MondayMinute.PULLED):
            m = minute(topic(status), MISSED, status)
            self.assertIsNone(g.missed_week(THURSDAY))
            m.delete()
        self.assertIsNone(g.missed_week(dt.datetime(2026, 11, 17, 20, 0, tzinfo=UTC)))  # Tuesday: it can still be written late


@override_settings(AI_PROVIDER="anthropic", ANTHROPIC_API_KEY="test-key", MONDAY_RAG=False, MONDAY_GATE=False)
class OwnerNoticeTests(TestCase):
    def setUp(self):
        MondayTopic.objects.all().delete()
        self.t = topic()
        self.sent = []

    def step(self, notify=None, **kw):
        """One run of the cron step on the Thursday after a week with no talk. Returns what it printed."""
        out = StringIO()
        notify = notify or (lambda subject, lines, key: self.sent.append((subject, lines, key)) or True)
        with patch(f"{CRON}.due_week", lambda: None), patch(f"{CRON}.ai.available", lambda: False), \
                patch(f"{CRON}.missed_week", lambda: g.missed_week(THURSDAY)), patch("talks.owner_alerts.notify", notify, create=True):
            call_command("monday_minute", stdout=out, **kw)
        return out.getvalue()

    def test_the_first_run_after_a_fresh_deploy_reports_nothing(self):
        self.assertNotIn("NO TALK", self.step())
        self.assertEqual(self.sent, [])

    def test_a_missed_week_is_printed_once_and_the_owner_is_told(self):
        minute(self.t, dt.date(2026, 11, 9), push_sent_at=timezone.now())
        self.assertIn("Monday Minute 2026-11-16: NO TALK went out this week", self.step())
        subject, lines, key = self.sent[0]
        self.assertEqual(key, "monday-missed-2026-11-16")
        self.assertIn("no talk went out for the week of Nov 16", subject)
        self.assertTrue(all(isinstance(line, str) for line in lines))
        self.assertNotIn("NO TALK", self.step())  # printed once, not on every run until next Monday

    def test_the_email_is_sent_once_and_tried_again_only_until_it_has_gone_out(self):
        from talks import owner_alerts

        minute(self.t, dt.date(2026, 11, 9), push_sent_at=timezone.now())
        answers, emails = iter([False, True]), []  # GoHighLevel does not take the first one

        def send(subject, html, timeout=30):
            emails.append(subject)
            return next(answers)

        with patch.object(owner_alerts, "enabled", lambda: True), patch.object(owner_alerts, "send", send):
            for run in range(5):
                self.step(notify=owner_alerts.notify)  # the real one: it keeps the once-only note
        self.assertEqual(len(emails), 2)  # the one that failed and the one that went out; nothing in runs 3 to 5
        self.assertIn("no talk went out", emails[0])

    @override_settings(MONDAY_MINUTE_ENABLED=False)
    def test_nothing_is_reported_while_monday_minute_is_off(self):
        minute(self.t, dt.date(2026, 11, 9), push_sent_at=timezone.now())
        self.assertNotIn("NO TALK", self.step())
        self.assertEqual(self.sent, [])

    def test_a_problem_with_the_email_does_not_stop_the_step(self):
        minute(self.t, dt.date(2026, 11, 9), push_sent_at=timezone.now())

        def broken(subject, lines, key):
            raise RuntimeError("owner alerts are broken")

        with self.assertLogs(CRON, "ERROR"):
            self.assertIn("NO TALK", self.step(notify=broken))

    def test_this_weeks_talk_still_waiting_at_its_publish_time_is_emailed(self):
        this_week = g.next_week() - dt.timedelta(days=7)
        waiting = minute(self.t, this_week, MondayMinute.HELD, publish_at=timezone.now() - dt.timedelta(minutes=1))
        minute(topic("ahead"), g.next_week(), MondayMinute.HELD, publish_at=g.publish_time(g.next_week()))   # its Monday has not come
        minute(topic("old"), this_week - dt.timedelta(days=21), MondayMinute.HELD)                           # weeks ago: old news
        self.step()
        self.assertEqual([key for _, _, key in self.sent], [f"monday-held-{waiting.pk}"])
        self.assertIn("waiting for your approval", self.sent[0][0])

    def test_a_talk_crews_reports_pulled_is_emailed_and_one_pulled_in_the_admin_is_not(self):
        reported, by_hand = minute(self.t, push_sent_at=timezone.now()), minute(topic("ladders"), dt.date(2026, 11, 2), push_sent_at=timezone.now())
        for i, net in enumerate(("203.0.113.1", "203.0.113.2", "203.0.113.3")):
            with self.assertLogs("monday.api", "WARNING") if i == 2 else patch("monday.api.log"):
                code = self.client.post(f"/api/v2/monday-minute/{reported.pk}/feedback",
                                        json.dumps({"install_id": f"{INSTALL}-{i}", "helpful": False, "reasons": ["unsafe"]}),
                                        content_type="application/json", HTTP_X_REAL_IP=net).status_code
            self.assertEqual(code, 200)
        MondayMinute.objects.filter(pk=by_hand.pk).update(status=MondayMinute.PULLED)  # the owner's own "Pull" action
        minute(self.t, dt.date(2025, 3, 3), MondayMinute.PULLED)  # and an old talk on the reported topic, pulled by hand long ago
        self.step()
        self.assertEqual([key for _, _, key in self.sent if "pulled" in key], [f"monday-pulled-{reported.pk}"])
        self.assertIn("pulled after crew reports", self.sent[0][0])
        # More than a week after the pull the email is no longer tried (the once-only note is kept for two weeks).
        self.sent.clear()
        MondayTopic.objects.filter(pk=self.t.pk).update(updated_at=timezone.now() - dt.timedelta(days=8))
        self.step()
        self.assertEqual([key for _, _, key in self.sent if "pulled" in key], [])

    def test_the_step_marks_a_safety_test_whose_server_stopped_as_failed(self):
        run = MondayEvalRun.objects.create(model="local:qwen3:8b", status="running", progress="3 of 40 talks")  # no sign of life
        said = self.step()
        run.refresh_from_db()
        self.assertEqual(run.status, "failed")  # used to say "Running" until somebody opened the admin
        self.assertIn("1 safety test run(s) marked as failed", said)
        self.assertNotIn("marked as failed", self.step())


# ---- No AI address set: one plain line, no traceback --------------------------------------------------------

@override_settings(AI_PROVIDER="local", LOCAL_AI_URL="", SECRET_KEY="test")
class NoAiAddressTests(TestCase):
    PLAIN = "The AI server address is not set (LOCAL_AI_URL)."

    def setUp(self):
        cache.clear()
        MondayTopic.objects.all().delete()
        self.t = topic()
        self.m = minute(self.t, push_sent_at=timezone.now())

    def test_every_call_says_which_setting_is_missing(self):
        for call in (lambda: ai._ollama("/api/tags", None, 30), ai.ensure_model, lambda: ai.ai_json("s", "u", {}, role="moderate"),
                     lambda: moderation.ai_check("We lock out at the panel.", "Dock lead", "Lockout")):
            with self.assertRaises(ai.AIUnavailable) as raised:  # used to be ValueError: unknown url type: '/api/tags'
                call()
            self.assertEqual(str(raised.exception), self.PLAIN)
        self.assertFalse(ai.available())
        with override_settings(LOCAL_AI_URL="   "):
            self.assertFalse(ai.available())

    def test_an_address_that_is_not_a_web_address_is_said_plainly_too(self):
        for wrong in ("my-ai-box:11434", "/my-ai-box", "ftp://my-ai-box"):
            with override_settings(LOCAL_AI_URL=wrong), self.assertRaises(ai.AIUnavailable) as raised:
                ai.ensure_model()
            self.assertIn("LOCAL_AI_URL", str(raised.exception))
            self.assertIn("http://", str(raised.exception))
            self.assertNotIn("unknown url type", str(raised.exception))
            self.assertNotIn(wrong, str(raised.exception))  # the address itself is not repeated in logs

    def test_a_posted_comment_waits_without_a_worker_or_a_traceback(self):
        body = {"install_id": INSTALL, "body": "We keep locks by the panel.", "accepted_rules": True}
        with patch("monday.api.threading.Thread") as thread, self.assertNoLogs("monday.api", "ERROR"):
            res = self.client.post(f"/api/v2/monday-minute/{self.m.pk}/comments", json.dumps(body), content_type="application/json")
        self.assertEqual((res.status_code, res.json()["status"]), (201, "pending"))
        thread.assert_not_called()  # used to start a worker that could only fail, with a full traceback per comment
        self.assertEqual(MondayComment.objects.get().status, MondayComment.PENDING)

    def test_screening_without_an_address_counts_against_no_comment_and_logs_no_error(self):
        MondayComment.objects.create(minute=self.m, body="hi", install_hash="x")
        with self.assertNoLogs("monday.api", "ERROR"):
            self.assertEqual(api.screen_pending(), 0)
        self.assertEqual(set(MondayComment.objects.values_list("status", "screen_failures")), {(MondayComment.PENDING, 0)})

    def test_the_safety_test_command_says_it_in_one_line(self):
        out = StringIO()
        call_command("monday_eval", stdout=out)
        self.assertEqual(out.getvalue().strip(), f"{self.PLAIN} Nothing was started.")
        self.assertFalse(MondayEvalRun.objects.exists())  # used to leave a failed run on record

    @override_settings(LOCAL_AI_URL="http://ollama.test:11434")
    def test_a_second_safety_test_from_the_command_line_is_refused_in_one_line(self):
        MondayLock.objects.create(name=eval_runner.LOCK, locked_at=timezone.now(), owner="the-test-that-is-running")
        out = StringIO()
        call_command("monday_eval", stdout=out)  # used to end in a traceback (AlreadyRunning)
        self.assertEqual(out.getvalue().strip(), "A safety test is already running. Wait for it to finish. Nothing was started.")
        self.assertFalse(MondayEvalRun.objects.exists())

    @override_settings(LOCAL_AI_URL="ollama.railway.internal:11434")
    def test_the_cron_step_run_by_hand_names_the_setting(self):
        out = StringIO()
        call_command("monday_minute", week="2026-11-16", stdout=out)
        self.assertIn("could not write it (The AI server address (LOCAL_AI_URL) is not a web address.", out.getvalue())
        self.assertNotIn("unknown url type", out.getvalue())
        self.assertFalse(MondayLock.objects.exists())


# ---- A report from a network that cannot be read ------------------------------------------------------------

class UnknownNetworkTests(TestCase):
    def setUp(self):
        cache.clear()
        self.t = topic()
        self.m = minute(self.t)

    def report(self, i, **where):
        body = {"install_id": f"{INSTALL}-{i}", "helpful": False, "reasons": ["unsafe"]}
        return self.client.post(f"/api/v2/monday-minute/{self.m.pk}/feedback", json.dumps(body), content_type="application/json", **where)

    def test_it_is_kept_but_is_not_one_of_the_three(self):
        self.report(0, HTTP_X_REAL_IP="203.0.113.1")
        self.report(1, HTTP_X_REAL_IP="203.0.113.2")
        for i in (2, 3):
            self.assertEqual(self.report(i, REMOTE_ADDR="").status_code, 200)  # no address anywhere
        self.m.refresh_from_db()
        self.assertEqual(self.m.status, MondayMinute.READY)  # two networks that can be told apart, not three
        self.assertEqual(self.m.feedback.count(), 4)
        with self.assertLogs("monday.api", "WARNING"):
            self.report(4, HTTP_X_REAL_IP="203.0.113.3")
        self.m.refresh_from_db()
        self.assertEqual(self.m.status, MondayMinute.PULLED)


# ---- The Monday Minute admin --------------------------------------------------------------------------------

PLAIN_STATIC = {"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
                "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}}


@override_settings(STORAGES=PLAIN_STATIC, AI_PROVIDER="anthropic", ANTHROPIC_API_KEY="test-key")  # admin pages link stylesheets; tests have none collected
class MondayAdminTests(TestCase):
    def setUp(self):
        cache.clear()
        MondayTopic.objects.all().delete()
        self.t = topic()
        self.m = minute(self.t, push_sent_at=timezone.now())
        self.client.force_login(get_user_model().objects.create_superuser("owner", "owner@example.com", "a-long-test-password"))
        self.addCleanup(MondayLock.release, "write")  # stops the heartbeat of a lock a test left held

    def write_next_week(self):
        """Posts the action from the list page, as the Go button does. Returns what the owner is told."""
        page = self.client.post("/admin/monday/mondayminute/", {"action": "write_next_week", "_selected_action": [str(self.m.pk)], "index": "0"}, follow=True)
        return " | ".join(str(m) for m in page.context["messages"])

    def test_the_list_counts_without_joining_ratings_to_comments(self):
        for i in range(5):
            MondayFeedback.objects.create(minute=self.m, install_hash=f"h{i}", helpful=i < 3)
        for status in (MondayComment.VISIBLE,) * 4 + (MondayComment.PENDING, MondayComment.HIDDEN):
            MondayComment.objects.create(minute=self.m, body="hi", install_hash="x", status=status)
        with CaptureQueriesContext(connection) as queries:
            page = self.client.get("/admin/monday/mondayminute/")
        self.assertEqual(page.status_code, 200)
        row = page.context["cl"].result_list[0]
        self.assertEqual((row._up, row._down, row._comments), (3, 2, 4))
        # Joining both to the talk made the database build ratings x comments rows per talk before counting.
        joined = [q["sql"] for q in queries if 'JOIN "monday_mondayfeedback"' in q["sql"] or 'JOIN "monday_mondaycomment"' in q["sql"]]
        self.assertEqual(joined, [])
        for column in ("6", "-7", "9"):  # the three counts can still be sorted on
            self.assertEqual(self.client.get(f"/admin/monday/mondayminute/?o={column}").status_code, 200)

    def test_fields_the_code_keeps_are_shown_not_typed(self):
        page = self.client.get(f"/admin/monday/mondayminute/{self.m.pk}/change/")
        self.assertContains(page, "Gate pending")
        self.assertNotContains(page, 'name="gate_pending"')  # used to be a tick box
        c = MondayComment.objects.create(minute=self.m, body="hi", install_hash="x")
        page = self.client.get(f"/admin/monday/mondaycomment/{c.pk}/change/")
        self.assertContains(page, "Screen failures")
        self.assertNotContains(page, 'name="screen_failures"')

    def test_on_claude_a_write_that_is_going_refuses_a_second_one(self):
        MondayLock.objects.create(name="write", locked_at=timezone.now(), owner="the-cron")
        with patch("monday.admin.generate_week") as write:
            said = self.write_next_week()
        write.assert_not_called()  # used to write (and pay for) a second talk that the database then refused
        self.assertIn("still being written", said)
        self.assertEqual(MondayLock.objects.get().owner, "the-cron")

    def test_on_claude_the_write_holds_the_lock_and_lets_go_of_it(self):
        held = []

        def wrote(week, **kw):
            held.append(MondayLock.objects.filter(name="write").exists())
            return None

        with patch("monday.admin.generate_week", wrote):
            self.assertIn("already has a Monday Minute", self.write_next_week())
        self.assertEqual(held, [True])
        self.assertFalse(MondayLock.objects.exists())

        def down(week, **kw):
            raise ai.AIUnavailable("Claude API unavailable: connection error")

        with patch("monday.admin.generate_week", down):
            self.assertIn("Could not write it", self.write_next_week())
        self.assertFalse(MondayLock.objects.exists())  # so the cron, or another click, can try again

    def test_it_writes_this_weeks_talk_while_that_is_still_owed(self):
        this_week = g.next_week() - dt.timedelta(days=7)
        asked = []

        def wrote(week, **kw):
            asked.append((week, kw))
            return None

        with patch("monday.admin.generate_week", wrote), patch("monday.admin.due_week", lambda: this_week):  # Monday or Tuesday, never written
            self.write_next_week()
        with patch("monday.admin.generate_week", wrote), patch("monday.admin.due_week", lambda: None):       # nothing owed
            self.write_next_week()
        self.assertEqual(asked, [(this_week, {"late": True}), (g.next_week(), {"late": False})])  # the first used to be next week too
