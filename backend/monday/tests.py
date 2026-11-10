import datetime as dt
import json
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from . import generate as g
from .models import MondayComment, MondayFeedback, MondayMinute, MondayTopic

UTC = dt.timezone.utc
INSTALL = "test-install-0000000001"


def topic(slug="loto", **kw):
    base = dict(slug=slug, title="Lockout steps", category="Hazardous energy", months=[], hazard="Machines start up.",
                key_points=["Lock it out.", "Verify it is dead.", "Remove only your own lock.", "Follow your site's procedure."],
                must_say=["Never remove someone else's lock."], never_say=["You can skip the try-out."],
                facts=[{"text": "Remove locks within 1 day.", "cite": "1910.147"}], story_seed="A mechanic almost reached in.",
                crew_questions=["Where do we keep locks?", "Who verifies?"], references=["1910.147"])
    base.update(kw)
    return MondayTopic.objects.create(**base)


def talk(**kw):
    base = dict(
        title="Prove it is dead", intro="Machines can start while you work on them. Lockout keeps them off, and the try-out proves it. " * 2,
        points=["Shut it down and lock every energy source with your own lock. " * 3,
                "Verify it is dead before you reach in. Try the start button, then return it to off. " * 2,
                "Never remove someone else's lock. Ask the person who put it on. " * 2],
        story_title="Almost reached in", story="A mechanic almost reached into a press that was still live. Her lead stopped her and they verified it together. " * 3,
        crew_question="Where are our lockout procedures kept?", takeaway="Your lock, your key, your life. " * 2,
    )
    base.update(kw)
    return base


PASS = {"verdict": "pass", "findings": []}
FAIL = {"verdict": "fail", "findings": [{"severity": "must_fix", "where": "point 2", "issue": "Unsafe.", "fix": "Say X."}]}


class ScheduleTests(TestCase):
    def test_publishes_monday_5am_pacific(self):
        self.assertEqual(g.publish_time(dt.date(2027, 1, 4)), dt.datetime(2027, 1, 4, 13, 0, tzinfo=UTC))   # PST
        self.assertEqual(g.publish_time(dt.date(2027, 7, 5)), dt.datetime(2027, 7, 5, 12, 0, tzinfo=UTC))   # PDT

    def test_next_week_and_write_window(self):
        tue = dt.datetime(2026, 11, 10, 18, 0, tzinfo=UTC)
        self.assertEqual(g.next_week(tue), dt.date(2026, 11, 16))
        self.assertIsNone(g.due_week(tue))  # window opens Wednesday
        wed = dt.datetime(2026, 11, 11, 14, 0, tzinfo=UTC)
        topic()
        self.assertEqual(g.due_week(wed), dt.date(2026, 11, 16))
        monday_after = dt.datetime(2026, 11, 16, 14, 0, tzinfo=UTC)
        self.assertEqual(g.next_week(monday_after), dt.date(2026, 11, 23))


class HardCheckTests(TestCase):
    def setUp(self):
        self.t = topic()

    def test_good_talk_passes(self):
        self.assertEqual(g.hard_checks(self.t, talk()), [])

    def test_missing_line_new_number_link_and_question(self):
        bad = talk(points=["Lock it out with 3 locks. " * 10, "Verify it. " * 10, "See www.example.com " * 5],
                   crew_question="Where are they? Who has keys?")
        problems = " ".join(g.hard_checks(self.t, bad))
        self.assertIn("Missing required line", problems)
        self.assertIn("number 3", problems)
        self.assertIn("link", problems)
        self.assertIn("one question", problems)

    def test_numbers_from_brief_and_911_allowed(self):
        ok = talk(intro="Call 911 if someone is hurt. Remove locks within 1 day. Machines can start.")
        self.assertEqual(g.hard_checks(self.t, ok), [])


class PipelineTests(TestCase):
    def setUp(self):
        MondayTopic.objects.all().delete()  # these tests use their own small bank
        self.t = topic()
        self.week = dt.date(2026, 11, 16)

    def test_passes_first_try_and_publishes(self):
        m = g.generate_week(self.week, write_fn=lambda t, f: (talk(), "claude-opus-5-5"), review_fn=lambda t, d: (PASS, "x"))
        self.assertEqual((m.status, m.attempts, m.topic, m.publish_at), (MondayMinute.READY, 1, self.t, g.publish_time(self.week)))
        self.assertIsNone(g.generate_week(self.week))  # already done for the week

    def test_rewrites_with_findings_then_passes(self):
        seen = []
        reviews = iter([(FAIL, "x"), (PASS, "x")])

        def write(t, findings):
            seen.append(list(findings))
            return talk(), "m"

        m = g.generate_week(self.week, write_fn=write, review_fn=lambda t, d: next(reviews))
        self.assertEqual((m.status, m.attempts), (MondayMinute.READY, 2))
        self.assertEqual(seen[0], [])
        self.assertIn("point 2: Unsafe. Use: Say X.", seen[1][0])

    def test_blocks_when_nothing_passes_and_tries_second_topic(self):
        topic("ladders", title="Ladders")
        m = g.generate_week(self.week, write_fn=lambda t, f: (talk(), "m"), review_fn=lambda t, d: (FAIL, "x"))
        self.assertEqual(m.status, MondayMinute.BLOCKED)
        self.assertEqual(MondayMinute.objects.filter(week=self.week, status=MondayMinute.BLOCKED).count(), 2)
        self.assertFalse(MondayMinute.objects.released().exists())
        self.assertIsNone(g.due_week(dt.datetime(2026, 11, 12, tzinfo=UTC)))  # gives up for the week

    def test_hard_check_failure_never_reaches_review(self):
        reviewed = []
        m = g.generate_week(self.week, write_fn=lambda t, f: (talk(points=["Lock it."]), "m"),
                            review_fn=lambda t, d: reviewed.append(1) or (PASS, "x"))
        self.assertEqual(m.status, MondayMinute.BLOCKED)
        self.assertEqual(reviewed, [])

    def test_refusal_counts_as_failed_attempt(self):
        def write(t, f):
            raise g.GenerationError("The model declined this request.")
        m = g.generate_week(self.week, write_fn=write, review_fn=lambda t, d: (PASS, "x"))
        self.assertEqual(m.status, MondayMinute.BLOCKED)
        self.assertIn("declined", m.check_log)

    def test_no_repeat_and_season(self):
        heat = topic("heat", title="Heat", months=[11])
        self.assertEqual(g.candidates(self.week)[0], heat)  # in season first
        MondayMinute.objects.create(week=self.week - dt.timedelta(weeks=1), publish_at=timezone.now(), topic=heat, status=MondayMinute.READY)
        self.assertNotIn(heat, g.candidates(self.week))
        self.t.active = False
        self.t.save()
        self.assertEqual(g.candidates(self.week), [heat])  # bank used up: least recent comes back, paused never does


@override_settings(SECRET_KEY="test")
class ApiTests(TestCase):
    def setUp(self):
        cache.clear()
        self.t = topic()
        self.m = MondayMinute.objects.create(week=dt.date(2026, 11, 9), publish_at=timezone.now() - dt.timedelta(hours=1),
                                             topic=self.t, status=MondayMinute.READY, **{k: v for k, v in talk().items()})

    def post(self, path, body):
        return self.client.post(f"/api/v2/monday-minute{path}", json.dumps(body), content_type="application/json")

    def test_list_and_detail_only_released(self):
        MondayMinute.objects.create(week=dt.date(2026, 11, 16), publish_at=timezone.now() + dt.timedelta(days=3), topic=self.t, status=MondayMinute.READY)
        MondayMinute.objects.create(week=dt.date(2026, 11, 2), publish_at=timezone.now() - dt.timedelta(days=7), topic=self.t, status=MondayMinute.BLOCKED)
        res = self.client.get("/api/v2/monday-minute").json()["minutes"]
        self.assertEqual([m["id"] for m in res], [self.m.pk])
        self.assertEqual(res[0]["references"], ["1910.147"])
        self.assertEqual(self.client.get(f"/api/v2/monday-minute/{self.m.pk}").status_code, 200)

    def test_thumbs_one_vote_per_phone(self):
        r = self.post(f"/{self.m.pk}/feedback", {"install_id": INSTALL, "helpful": True}).json()
        self.assertEqual(r, {"thumbs_up": 1, "thumbs_down": 0})
        r = self.post(f"/{self.m.pk}/feedback", {"install_id": INSTALL, "helpful": False, "reasons": ["too_long"]}).json()
        self.assertEqual(r, {"thumbs_up": 0, "thumbs_down": 1})
        self.assertEqual(self.post(f"/{self.m.pk}/feedback", {"install_id": "bad id!", "helpful": True}).status_code, 422)

    def test_unsafe_reports_pull_talk_and_pause_topic(self):
        for i in range(3):
            self.post(f"/{self.m.pk}/feedback", {"install_id": f"{INSTALL}{i}", "helpful": False, "reasons": ["unsafe"]})
        self.m.refresh_from_db()
        self.t.refresh_from_db()
        self.assertEqual(self.m.status, MondayMinute.PULLED)
        self.assertFalse(self.t.active)
        self.assertIn("3 crew reports", self.t.paused_reason)
        self.assertEqual(self.client.get(f"/api/v2/monday-minute/{self.m.pk}").status_code, 404)

    def comment(self, body="We keep locks by the panel.", **kw):
        return self.post(f"/{self.m.pk}/comments", {"install_id": INSTALL, "body": body, "accepted_rules": True, **kw})

    def test_comment_screened_then_visible_with_replies(self):
        with patch("monday.moderation.ai_check", return_value=(True, "")):
            top = self.comment(display_name="  Dock   lead ").json()
            self.assertEqual((top["status"], top["comment"]["display_name"]), ("visible", "Dock lead"))
            reply = self.comment("Same here.", parent_id=top["comment"]["id"]).json()
            self.assertEqual(reply["status"], "visible")
            self.assertEqual(self.comment("x" * 10, parent_id=reply["comment"]["id"]).status_code, 400)  # one level only
        data = self.client.get(f"/api/v2/monday-minute/{self.m.pk}/comments").json()
        self.assertEqual(len(data["comments"]), 1)
        self.assertEqual(data["comments"][0]["replies"][0]["body"], "Same here.")
        self.assertEqual(data["comments"][0]["display_name"], "Dock lead")
        self.assertTrue(data["rules"])
        self.assertNotIn("install", json.dumps(data))

    def test_comment_rules_links_and_rejection(self):
        self.assertEqual(self.comment(accepted_rules=False).status_code, 400)
        self.assertEqual(self.comment("call me at 702-555-0100").json()["status"], "rejected")
        self.assertEqual(self.comment("see www.spam.com now").json()["status"], "rejected")
        with patch("monday.moderation.ai_check", return_value=(False, "Please leave out names.")):
            r = self.comment("Bob got hurt badly").json()
        self.assertEqual((r["status"], r["message"]), ("rejected", "Please leave out names."))
        self.assertFalse(MondayComment.objects.exists())

    def test_moderation_down_holds_comment(self):
        with patch("monday.moderation.ai_check", side_effect=RuntimeError("down")):
            self.assertEqual(self.comment().json()["status"], "pending")
        self.assertEqual(self.client.get(f"/api/v2/monday-minute/{self.m.pk}/comments").json()["comments"], [])
        from .api import screen_pending
        with patch("monday.moderation.ai_check", return_value=(True, "")):
            self.assertEqual(screen_pending(), 1)
        self.assertEqual(MondayComment.objects.get().status, MondayComment.VISIBLE)

    def test_two_reports_hide_comment(self):
        with patch("monday.moderation.ai_check", return_value=(True, "")):
            cid = self.comment().json()["comment"]["id"]
        self.post(f"/comments/{cid}/report", {"install_id": INSTALL + "a"})
        self.post(f"/comments/{cid}/report", {"install_id": INSTALL + "a"})  # same phone twice counts once
        self.assertEqual(MondayComment.objects.get().status, MondayComment.VISIBLE)
        self.post(f"/comments/{cid}/report", {"install_id": INSTALL + "b"})
        self.assertEqual(MondayComment.objects.get().status, MondayComment.HIDDEN)

    def test_feedback_notes_feed_the_writer(self):
        for i in range(3):
            MondayFeedback.objects.create(minute=self.m, install_hash=f"h{i}", helpful=False, reasons=["too_long"])
        notes = " ".join(g.feedback_notes(self.t))
        self.assertIn("Too long", notes)
        self.assertIn("0 thumbs up and 3 thumbs down", notes)


class ClaudeCallTests(TestCase):
    """The real call path with the SDK client faked: fallback beta first, plain call if the beta is rejected, refusals raise."""

    def fake(self, stop="end_turn", text='{"a": 1}', beta_error=False):
        import anthropic
        import httpx2 as httpx
        from types import SimpleNamespace as NS

        res = NS(stop_reason=stop, model="claude-opus-5-5", content=[NS(type="text", text=text)])
        client = NS(beta=NS(messages=NS()), messages=NS())
        calls = []

        def beta_create(**kw):
            calls.append(("beta", kw))
            if beta_error:
                raise anthropic.BadRequestError("bad", response=httpx.Response(400, request=httpx.Request("POST", "https://x")), body=None)
            return res

        client.beta.messages.create = beta_create
        client.messages.create = lambda **kw: calls.append(("plain", kw)) or res
        return client, calls

    def test_structured_call_with_fallback(self):
        client, calls = self.fake()
        with patch.object(g, "_client", return_value=client):
            data, model = g.claude_json("sys", "user", {"type": "object"}, "high")
        self.assertEqual((data, model), ({"a": 1}, "claude-opus-5-5"))
        kind, kw = calls[0]
        self.assertEqual((kind, kw["fallbacks"], kw["model"]), ("beta", "default", "claude-opus-5-5"))
        self.assertEqual(kw["output_config"]["format"]["type"], "json_schema")

    def test_plain_call_when_beta_rejected(self):
        client, calls = self.fake(beta_error=True)
        with patch.object(g, "_client", return_value=client):
            g.claude_json("s", "u", {}, "low")
        self.assertEqual([c[0] for c in calls], ["beta", "plain"])
        self.assertNotIn("fallbacks", calls[1][1])

    def test_refusal_raises(self):
        client, _ = self.fake(stop="refusal")
        with patch.object(g, "_client", return_value=client), self.assertRaises(g.GenerationError):
            g.claude_json("s", "u", {}, "low")


class TopicBankTests(TestCase):
    """The CSP-reviewed bank loaded by migration 0002."""

    def test_all_104_topics_loaded_and_complete(self):
        bank = MondayTopic.objects.all()
        self.assertEqual(bank.count(), 104)
        for t in bank:
            self.assertTrue(t.hazard and t.story_seed, t.slug)
            self.assertTrue(4 <= len(t.key_points) <= 6, t.slug)
            self.assertTrue(1 <= len(t.must_say) <= 2, t.slug)
            self.assertEqual(len(t.crew_questions), 2, t.slug)
            for f in t.facts:
                self.assertRegex(f["cite"], r"^(29 CFR )?19(10|04)\.\d+", t.slug)
            for r in t.references:
                self.assertRegex(r, r"^19(10|04)\.\d+", t.slug)

    def test_reviewed_wording(self):
        get = lambda s: MondayTopic.objects.get(slug=s)
        self.assertIn("Stay out of the path. Things that move, fall, or snap do not go where you expect.", get("line-of-fire").must_say)
        self.assertTrue(any("lock it out" in m for m in get("jam-clearing").must_say))
        self.assertTrue(any("do not go in" in m.lower() for m in get("permit-spaces").must_say))
        self.assertFalse(any("minor servicing" in f["text"].lower() for f in get("jam-clearing").facts))

    def test_seasonal_choice_on_the_real_bank(self):
        summer = g.candidates(dt.date(2027, 7, 5))[0]
        winter = g.candidates(dt.date(2027, 1, 4))[0]
        self.assertIn(7, summer.months)
        self.assertIn(1, winter.months)

    def test_a_talk_built_from_a_real_brief_passes_hard_checks(self):
        t = MondayTopic.objects.get(slug="loto-six-steps")
        talk = {
            "title": "Lock it, then prove it", "intro": t.hazard + " " + " ".join(t.must_say),
            "points": t.key_points[:4], "story_title": "A close call", "story": t.story_seed + " " + t.hazard,
            "crew_question": t.crew_questions[0], "takeaway": t.must_say[0],
        }
        self.assertEqual(g.hard_checks(t, talk), [])
