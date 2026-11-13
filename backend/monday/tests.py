import datetime as dt
import json
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from . import ai, generate as g
from .models import MondayComment, MondayCommentBan, MondayFeedback, MondayLock, MondayMinute, MondayTopic

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


GROUNDED = [{"point": 0, "brief_key_point": 0}, {"point": 1, "brief_key_point": 1}, {"point": 2, "brief_key_point": 2}]
PASS = {"verdict": "pass", "findings": [], "grounding": GROUNDED, "confidence": "high"}
FAIL = {"verdict": "fail", "findings": [{"severity": "must_fix", "where": "point 2", "issue": "Unsafe.", "fix": "Say X."}], "grounding": GROUNDED, "confidence": "high"}


class ScheduleTests(TestCase):
    def test_publishes_monday_5am_pacific(self):
        self.assertEqual(g.publish_time(dt.date(2027, 1, 4)), dt.datetime(2027, 1, 4, 13, 0, tzinfo=UTC))   # PST
        self.assertEqual(g.publish_time(dt.date(2027, 7, 5)), dt.datetime(2027, 7, 5, 12, 0, tzinfo=UTC))   # PDT

    def test_next_week_and_write_window(self):
        tue = dt.datetime(2026, 11, 10, 18, 0, tzinfo=UTC)
        self.assertEqual(g.next_week(tue), dt.date(2026, 11, 16))
        # Next Monday's window opens Wednesday. Until then this week's talk is still owed if it was never written.
        self.assertEqual(g.due_week(tue), dt.date(2026, 11, 9))
        MondayMinute.objects.create(week=dt.date(2026, 11, 9), publish_at=g.publish_time(dt.date(2026, 11, 9)), topic=topic("written"), status=MondayMinute.READY)
        self.assertIsNone(g.due_week(tue))
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


@override_settings(MONDAY_GATE=False)  # these test the review pipeline; GateTests covers the gate
class PipelineTests(TestCase):
    def setUp(self):
        MondayTopic.objects.all().delete()  # these tests use their own small bank
        self.t = topic()
        self.week = dt.date(2026, 11, 16)

    def test_passes_first_try_and_publishes(self):
        m = g.generate_week(self.week, write_fn=lambda t, f: (talk(), "claude-opus-5-5"), review_fn=lambda t, d, **kw: (PASS, "x"))
        self.assertEqual((m.status, m.attempts, m.topic, m.publish_at), (MondayMinute.READY, 1, self.t, g.publish_time(self.week)))
        self.assertIsNone(g.generate_week(self.week))  # already done for the week

    def test_rewrites_with_findings_then_passes(self):
        seen = []
        reviews = iter([(FAIL, "x"), (PASS, "x")])

        def write(t, findings):
            seen.append(list(findings))
            return talk(), "m"

        m = g.generate_week(self.week, write_fn=write, review_fn=lambda t, d, **kw: next(reviews), strict=False)
        self.assertEqual((m.status, m.attempts), (MondayMinute.READY, 2))
        self.assertEqual(seen[0], [])
        self.assertIn("point 2: Unsafe. Use: Say X.", seen[1][0])

    def test_blocks_when_nothing_passes_and_tries_second_topic(self):
        topic("ladders", title="Ladders")
        m = g.generate_week(self.week, write_fn=lambda t, f: (talk(), "m"), review_fn=lambda t, d, **kw: (FAIL, "x"))
        self.assertEqual(m.status, MondayMinute.BLOCKED)
        self.assertEqual(MondayMinute.objects.filter(week=self.week, status=MondayMinute.BLOCKED).count(), 2)
        self.assertFalse(MondayMinute.objects.released().exists())
        self.assertIsNone(g.due_week(dt.datetime(2026, 11, 12, tzinfo=UTC)))  # gives up for the week

    def test_hard_check_failure_never_reaches_review(self):
        reviewed = []
        m = g.generate_week(self.week, write_fn=lambda t, f: (talk(points=["Lock it."]), "m"),
                            review_fn=lambda t, d, **kw: reviewed.append(1) or (PASS, "x"))
        self.assertEqual(m.status, MondayMinute.BLOCKED)
        self.assertEqual(reviewed, [])

    def test_refusal_counts_as_failed_attempt(self):
        def write(t, f):
            raise g.GenerationError("The model declined this request.")
        m = g.generate_week(self.week, write_fn=write, review_fn=lambda t, d, **kw: (PASS, "x"))
        self.assertEqual(m.status, MondayMinute.BLOCKED)
        self.assertIn("declined", m.check_log)

    def test_outage_does_not_use_up_the_week(self):
        def down(t, f):
            raise ai.AIUnavailable("Local AI server unavailable")
        with self.assertRaises(ai.AIUnavailable):
            g.generate_week(self.week, write_fn=down, review_fn=lambda t, d, **kw: (PASS, "x"))
        self.assertFalse(MondayMinute.objects.filter(week=self.week).exists())  # nothing recorded, so the next run retries
        m = g.generate_week(self.week, write_fn=lambda t, f: (talk(), "m"), review_fn=lambda t, d, **kw: (PASS, "x"), strict=False)
        self.assertEqual(m.status, MondayMinute.READY)

    def test_no_repeat_and_season(self):
        heat = topic("heat", title="Heat", months=[11])
        self.assertEqual(g.candidates(self.week)[0], heat)  # in season first
        MondayMinute.objects.create(week=self.week - dt.timedelta(weeks=1), publish_at=timezone.now(), topic=heat, status=MondayMinute.READY)
        self.assertNotIn(heat, g.candidates(self.week))
        self.t.active = False
        self.t.save()
        self.assertEqual(g.candidates(self.week), [heat])  # bank used up: least recent comes back, paused never does


@override_settings(SECRET_KEY="test", AI_PROVIDER="anthropic")
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

    def test_list_uses_a_fixed_number_of_queries(self):
        for i in range(5):
            m = MondayMinute.objects.create(week=dt.date(2026, 10, 5) - dt.timedelta(weeks=i), publish_at=timezone.now() - dt.timedelta(days=30 + i),
                                            topic=self.t, status=MondayMinute.READY, **talk())
            MondayFeedback.objects.create(minute=m, install_hash=f"a{i}", helpful=True)
            MondayComment.objects.create(minute=m, body="hi", install_hash="x", status=MondayComment.VISIBLE)
        with self.assertNumQueries(1):
            data = self.client.get("/api/v2/monday-minute").json()["minutes"]
        self.assertEqual(len(data), 6)
        self.assertEqual((data[1]["thumbs_up"], data[1]["comment_count"]), (1, 1))
        weeks = [m["week"] for m in data]
        self.assertEqual(weeks, sorted(weeks, reverse=True))  # newest first: the app shows the first one as this week's

    def test_thumbs_one_vote_per_phone(self):
        r = self.post(f"/{self.m.pk}/feedback", {"install_id": INSTALL, "helpful": True}).json()
        self.assertEqual(r, {"thumbs_up": 1, "thumbs_down": 0})
        r = self.post(f"/{self.m.pk}/feedback", {"install_id": INSTALL, "helpful": False, "reasons": ["too_long"]}).json()
        self.assertEqual(r, {"thumbs_up": 0, "thumbs_down": 1})
        self.assertEqual(self.post(f"/{self.m.pk}/feedback", {"install_id": "bad id!", "helpful": True}).status_code, 422)

    def test_unsafe_reports_pull_talk_and_pause_topic(self):
        def report(i, ip):
            return self.client.post(f"/api/v2/monday-minute/{self.m.pk}/feedback", json.dumps(
                {"install_id": f"{INSTALL}{i}", "helpful": False, "reasons": ["unsafe"]}),
                content_type="application/json", HTTP_X_FORWARDED_FOR=ip)

        for i in range(5):  # five made-up phones on one connection can't pull a talk
            report(i, "203.0.113.9")
        self.m.refresh_from_db()
        self.assertEqual(self.m.status, MondayMinute.READY)
        report(10, "198.51.100.1")
        report(11, "6.6.6.6, 198.51.100.2")  # a forged first hop is ignored; the proxy's hop counts
        self.m.refresh_from_db()
        self.t.refresh_from_db()
        self.assertEqual(self.m.status, MondayMinute.PULLED)
        self.assertFalse(self.t.active)
        self.assertIn("reports from 3 sites", self.t.paused_reason)
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

    def test_banned_phone_cannot_comment_and_admin_ban_hides_everything(self):
        from django.contrib.admin.sites import site
        from django.test import RequestFactory

        from .api import _hash
        with patch("monday.moderation.ai_check", return_value=(True, "")):
            self.comment()
            self.comment(body="Second one from the same phone.")
        admin = site._registry[MondayComment]
        req = RequestFactory().post("/")
        with patch.object(admin, "message_user"):
            admin.hide_and_ban(req, MondayComment.objects.filter(pk=MondayComment.objects.first().pk))
        self.assertTrue(MondayCommentBan.objects.filter(install_hash=_hash(INSTALL)).exists())
        self.assertFalse(MondayComment.objects.filter(status=MondayComment.VISIBLE).exists())
        res = self.comment(body="Back again.")
        self.assertEqual((res.status_code, res.json()["error"]), (403, "You can no longer comment."))
        self.assertEqual(MondayComment.objects.count(), 2)

    @override_settings(OWNER_ALERT_EMAIL="owner@example.com", GHL_PRIVATE_TOKEN="t", GHL_LOCATION_ID="loc")
    def test_first_report_emails_the_owner_once(self):
        with patch("monday.moderation.ai_check", return_value=(True, "")):
            cid = self.comment().json()["comment"]["id"]
        with patch("talks.owner_alerts.ghl.configured", return_value=True), \
                patch("talks.owner_alerts._owner_contact", return_value="c1"), \
                patch("talks.owner_alerts.ghl.send_email") as send:
            self.post(f"/comments/{cid}/report", {"install_id": INSTALL + "a", "reason": "rude"})
            self.post(f"/comments/{cid}/report", {"install_id": INSTALL + "b"})
        self.assertEqual(send.call_count, 1)
        self.assertIn("reported", send.call_args.args[1])
        self.assertIn("within 24 hours", send.call_args.args[2])
        self.assertIsNotNone(MondayComment.objects.get().report_alerted_at)

    def test_report_alert_waits_for_the_cron_when_alerts_are_off(self):
        from talks import owner_alerts
        with patch("monday.moderation.ai_check", return_value=(True, "")):
            cid = self.comment().json()["comment"]["id"]
        self.post(f"/comments/{cid}/report", {"install_id": INSTALL + "a"})
        self.assertIsNone(MondayComment.objects.get().report_alerted_at)
        later = timezone.now() + dt.timedelta(minutes=5)
        with patch("talks.owner_alerts.enabled", return_value=True), patch("talks.owner_alerts.send", return_value=True):
            self.assertEqual(owner_alerts.retry_report_alerts(now=later), 1)
        self.assertIsNotNone(MondayComment.objects.get().report_alerted_at)

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
        with patch.object(ai, "_client", return_value=client):
            data, model = ai.claude_json("sys", "user", {"type": "object"}, "high")
        self.assertEqual((data, model), ({"a": 1}, "claude-opus-5-5"))
        kind, kw = calls[0]
        self.assertEqual((kind, kw["fallbacks"], kw["model"]), ("beta", "default", "claude-opus-5-5"))
        self.assertEqual(kw["output_config"]["format"]["type"], "json_schema")

    def test_plain_call_when_beta_rejected(self):
        client, calls = self.fake(beta_error=True)
        with patch.object(ai, "_client", return_value=client):
            ai.claude_json("s", "u", {}, "low")
        self.assertEqual([c[0] for c in calls], ["beta", "plain"])
        self.assertNotIn("fallbacks", calls[1][1])

    def test_refusal_raises(self):
        client, _ = self.fake(stop="refusal")
        with patch.object(ai, "_client", return_value=client), self.assertRaises(ai.GenerationError):
            ai.claude_json("s", "u", {}, "low")


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


@override_settings(MONDAY_GATE=False)  # these test the review pipeline; GateTests covers the gate
class StrictLocalTests(TestCase):
    """With the local model: two independent reviews, both highly confident, and every point traced to the brief."""

    def setUp(self):
        MondayTopic.objects.all().delete()
        self.t = topic()
        self.week = dt.date(2026, 11, 16)

    def run_with(self, reviews, strict=True):
        it = iter(reviews)
        calls = []

        def review(t, d, second=False):
            calls.append(second)
            return next(it), "local:qwen3:8b"

        m = g.generate_week(self.week, write_fn=lambda t, f: (talk(), "local:qwen3:8b"), review_fn=review, strict=strict)
        return m, calls

    def test_needs_two_passing_reviews(self):
        m, calls = self.run_with([PASS, PASS])
        self.assertEqual((m.status, calls), (MondayMinute.READY, [False, True]))
        self.assertIn("both independent CSP reviews", m.check_log)

    def test_second_review_can_fail_it(self):
        m, calls = self.run_with([PASS, FAIL, PASS, PASS])
        self.assertEqual((m.status, m.attempts), (MondayMinute.READY, 2))
        self.assertIn("second review failed", m.check_log)

    def test_medium_confidence_is_not_enough(self):
        unsure = dict(PASS, confidence="medium")
        m, _ = self.run_with([unsure] * 3 + [unsure] * 3, strict=True)
        self.assertEqual(m.status, MondayMinute.BLOCKED)
        self.assertIn("wasn't fully confident", m.check_log)
        m2 = MondayMinute.objects.filter(week=self.week)
        self.assertTrue(m2.exists())

    def test_ungrounded_point_fails_even_when_not_strict(self):
        made_up = dict(PASS, grounding=[{"point": 0, "brief_key_point": 0}, {"point": 1, "brief_key_point": -1}, {"point": 2, "brief_key_point": 2}])
        must, _ = g.judge(self.t, talk(), made_up, strict=False)
        self.assertTrue(any("Point 2 is not from the brief" in x for x in must))
        one_based = dict(PASS, grounding=[{"point": 1, "brief_key_point": 0}, {"point": 2, "brief_key_point": 1}, {"point": 3, "brief_key_point": 2}])
        self.assertEqual(g.judge(self.t, talk(), one_based, strict=False)[0], [])
        missing_last = dict(PASS, grounding=[{"point": 1, "brief_key_point": 0}, {"point": 2, "brief_key_point": 1}])
        self.assertTrue(g.judge(self.t, talk(), missing_last, strict=False)[0])


@override_settings(AI_PROVIDER="local", LOCAL_AI_URL="http://ollama.test:11434", LOCAL_AI_MODEL="qwen3:8b")
class OllamaTests(TestCase):
    def reply(self, body):
        from io import BytesIO
        from unittest.mock import MagicMock

        res = MagicMock()
        res.__enter__.return_value = BytesIO(json.dumps(body).encode())
        return res

    def test_chat_sends_schema_and_parses_json(self):
        sent = {}

        def fake(req, timeout):
            sent.update(json.loads(req.data), url=req.full_url, timeout=timeout)
            return self.reply({"model": "qwen3:8b", "done_reason": "stop", "message": {"content": '{"allow": true}'}})

        with patch("urllib.request.urlopen", fake):
            data, model = ai.ai_json("sys", "user", {"type": "object"}, think=False)
        self.assertEqual((data, model), ({"allow": True}, "local:qwen3:8b"))
        self.assertEqual(sent["url"], "http://ollama.test:11434/api/chat")
        self.assertEqual((sent["format"], sent["think"], sent["stream"]), ({"type": "object"}, False, False))
        self.assertEqual((sent["options"]["num_ctx"], sent["options"]["temperature"]), (16384, 0.0))  # review role
        self.assertEqual(sent["messages"][0]["role"], "system")

    @override_settings(LOCAL_AI_REVIEW_MODEL="qwen3:14b", LOCAL_AI_THREADS=8)
    def test_roles_tune_model_context_and_threads(self):
        sent = []

        def fake(req, timeout):
            sent.append(json.loads(req.data))
            return self.reply({"done_reason": "stop", "message": {"content": "{}"}})

        with patch("urllib.request.urlopen", fake):
            ai.ai_json("s", "u", {}, role="moderate", think=False)
            ai.ai_json("s", "u", {}, role="review", seed=2)
        mod, rev = sent
        self.assertEqual((mod["model"], mod["options"]["num_ctx"], mod["options"]["num_predict"]), ("qwen3:8b", 4096, 200))
        self.assertEqual((rev["model"], rev["options"]["seed"], rev["options"]["num_thread"]), ("qwen3:14b", 2, 8))

    def test_cut_off_and_down_raise(self):
        with patch("urllib.request.urlopen", lambda req, timeout: self.reply({"done_reason": "length", "message": {"content": "{"}})):
            with self.assertRaises(ai.GenerationError):
                ai.ai_json("s", "u", {})
        import urllib.error
        def down(req, timeout):
            raise urllib.error.URLError("refused")
        with patch("urllib.request.urlopen", down), self.assertRaises(ai.AIUnavailable):
            ai.ai_json("s", "u", {})

    def test_ensure_model_pulls_when_missing(self):
        paths = []

        def fake(req, timeout):
            paths.append(req.full_url.rsplit("/", 1)[-1])
            if req.full_url.endswith("/api/tags"):
                return self.reply({"models": [{"name": "llama3:8b"}]})
            return self.reply({"status": "success"})

        with patch("urllib.request.urlopen", fake):
            self.assertTrue(ai.ensure_model())
        self.assertEqual(paths, ["tags", "pull"])

    @override_settings(SECRET_KEY="test")
    def test_local_comments_wait_then_get_screened(self):
        t = topic()
        m = MondayMinute.objects.create(week=dt.date(2026, 11, 9), publish_at=timezone.now() - dt.timedelta(hours=1), topic=t,
                                        status=MondayMinute.READY, **talk())
        with patch("monday.api._screen_soon") as soon:
            r = self.client.post(f"/api/v2/monday-minute/{m.pk}/comments", json.dumps(
                {"install_id": INSTALL, "body": "We lock out at the panel.", "accepted_rules": True}), content_type="application/json").json()
        self.assertEqual(r["status"], "pending")
        cid = MondayComment.objects.get().pk
        soon.assert_called_once_with(cid)
        from .api import screen_one
        with patch("monday.moderation.ai_check", side_effect=ai.GenerationError("down")):
            self.assertFalse(screen_one(cid))
        with patch("monday.moderation.ai_check", return_value=(True, "")):
            self.assertTrue(screen_one(cid))
        self.assertEqual(MondayComment.objects.get().status, MondayComment.VISIBLE)


class LockTests(TestCase):
    def test_one_writer_at_a_time_and_stale_locks_expire(self):
        self.assertTrue(MondayLock.acquire("write"))
        self.assertFalse(MondayLock.acquire("write"))
        MondayLock.objects.filter(name="write").update(locked_at=timezone.now() - dt.timedelta(hours=5))
        self.assertTrue(MondayLock.acquire("write"))
        MondayLock.release("write")
        self.assertTrue(MondayLock.acquire("write"))


class ReviewRagTests(TestCase):
    """RAG for the reviewer: regulation paragraphs from the library, plus past CSP findings."""

    def test_review_prompt_includes_regulation_text_and_past_findings(self):
        t = MondayTopic.objects.get(slug="loto-six-steps")
        seen = {}

        def fake(system, user, schema, effort):
            seen["user"] = user
            return PASS, "m"

        g.review(t, talk(), call=fake, rag=True)
        self.assertIn("OFFICIAL REGULATION TEXT", seen["user"])
        self.assertIn("[29 CFR 1910.147(", seen["user"])
        self.assertIn("PAST FINDINGS FROM A SAFETY PROFESSIONAL'S REVIEW", seen["user"])
        g.review(t, talk(), call=fake, rag=False)
        self.assertNotIn("OFFICIAL REGULATION TEXT", seen["user"])

    def test_past_findings_prefer_the_same_topic_then_category(self):
        t = MondayTopic.objects.get(slug="jam-clearing")
        found = g.past_findings(t, k=4)
        self.assertEqual(found[0]["slug"], "jam-clearing")
        self.assertTrue(all(f["category"] == t.category or f["slug"] == t.slug for f in found[:2]))

    @override_settings(MONDAY_RAG=False)
    def test_rag_can_be_switched_off(self):
        t = MondayTopic.objects.get(slug="loto-six-steps")
        seen = {}
        g.review(t, talk(), call=lambda s, u, sc, e: (seen.update(u=u) or (PASS, "m")))
        self.assertNotIn("OFFICIAL REGULATION TEXT", seen["u"])


class SafetyEvalTests(TestCase):
    def test_faithful_talk_and_plants(self):
        from . import safety_eval as ev

        t = MondayTopic.objects.get(slug="loto-six-steps")
        good = ev.faithful_talk(t)
        self.assertTrue(good["crew_question"].endswith("?"))
        bad = ev.planted(t, "skip_lockout")
        self.assertIn(ev.PLANTS["skip_lockout"], bad["points"][1])
        self.assertIn(t.never_say[0], ev.planted(t, "never_say")["points"][1])
        self.assertNotEqual(good, bad)

    def test_scoring_with_a_reviewer_that_catches_some_plants(self):
        from . import safety_eval as ev

        topics = list(MondayTopic.objects.filter(slug__in=["loto-six-steps", "permit-spaces"]))
        grounded = {"verdict": "pass", "findings": [], "confidence": "high",
                    "grounding": [{"point": i, "brief_key_point": i} for i in range(4)]}
        unsafe = dict(grounded, verdict="fail", findings=[{"severity": "must_fix", "where": "p2", "issue": "unsafe", "fix": "x"}])
        caught = (ev.PLANTS["skip_lockout"], ev.PLANTS["untrained_rescue"])

        def fake_review(topic, talk_, second=False, rag=None, call=None):
            text = " ".join(talk_["points"])
            return (unsafe if any(c in text for c in caught) else grounded), "m"

        with patch.object(ev, "review", fake_review):
            r = ev.run(topics, rag=True, strict=True)
        self.assertEqual(r["good"], {"n": 2, "blocked": 0, "examples": []})
        self.assertEqual(r["plants"]["skip_lockout"]["caught"], 2)
        self.assertEqual(r["plants"]["made_up_rule"]["caught"], 0)
        self.assertEqual(sorted(r["plants"]["made_up_rule"]["missed"]), sorted(t.slug for t in topics))
        summary = ev.summarize(r)
        self.assertIn("Planted mistakes caught: 4/14", summary)
        self.assertIn("Good talks wrongly blocked: 0/2 (0%)", summary)

    def test_an_unreadable_review_is_asked_again_like_the_pipeline(self):
        """One bad answer is asked again with the retry note (as the weekly pipeline does), so it is not an error.
        Two bad answers in a row still count as one failed call."""
        from . import generate as g
        from . import safety_eval as ev
        from .ai import GenerationError

        topics = list(MondayTopic.objects.filter(slug="loto-six-steps"))
        grounded = {"verdict": "pass", "findings": [], "confidence": "high",
                    "grounding": [{"point": i, "brief_key_point": i} for i in range(4)]}
        seen = []

        def flaky(topic, talk_, second=False, rag=None, call=None):
            seen.append(g._asked_before())
            if len(seen) % 2 == 1:
                raise GenerationError("Local model returned invalid JSON: cut off")
            return grounded, "m"

        with patch.object(ev, "review", flaky):
            r = ev.run(topics, rag=True, strict=True)
        self.assertEqual(r["errors"], 0)
        self.assertEqual(r["good"]["n"], 1)
        self.assertEqual(seen[:2], [0, 1])  # the second ask knows it is a retry, so it gets the note and its own seed
        self.assertEqual(g._asked_before(), 0)  # nothing left behind for the next call

        def broken(*a, **k):
            raise GenerationError("Local model returned invalid JSON: cut off")

        with patch.object(ev, "review", broken):
            r = ev.run(topics, rag=True, strict=True)
        self.assertEqual(r["good"]["n"], 0)
        self.assertEqual(r["errors"], 1 + len(ev.PLANTS))

    def test_runner_saves_results(self):
        from . import safety_eval as ev
        from .eval_runner import run_eval
        from .models import MondayEvalRun

        topics = list(MondayTopic.objects.filter(slug="loto-six-steps"))
        passing = {"verdict": "pass", "findings": [], "confidence": "high",
                   "grounding": [{"point": i, "brief_key_point": i} for i in range(4)]}
        with patch.object(ev, "review", lambda *a, **k: (passing, "m")), override_settings(AI_PROVIDER="anthropic"):
            run = run_eval(topics, compare=True)
        self.assertEqual(run.status, "done")
        self.assertEqual(set(run.results), {"rag_on", "rag_off"})
        self.assertIn("RAG on", run.summary)
        self.assertEqual(run.progress, f"{2 * (1 + len(ev.PLANTS))} of {2 * (1 + len(ev.PLANTS))} talks")
        self.assertEqual(MondayEvalRun.objects.count(), 1)



class GateTests(TestCase):
    """Talks publish on their own only after this AI setup passes the safety test; otherwise they wait for approval."""

    def setUp(self):
        from . import gate
        self.gate = gate
        MondayTopic.objects.all().delete()
        self.t = topic()
        self.week = dt.date(2026, 11, 16)

    def result(self, caught=40, planted=42, good=6, blocked=0, errors=0):
        return {"plants": {"x": {"n": planted, "caught": caught, "missed": []}}, "good": {"n": good, "blocked": blocked, "examples": []},
                "errors": errors, "seconds": []}

    def run_record(self, passed=True, **kw):
        from .models import MondayEvalRun
        want = self.gate.setup()
        defaults = dict(model=want["model"], rag=want["rag"], strict=want["strict"], status="done", passed=passed, conclusive=True,
                        verdict="caught 95%", finished_at=timezone.now())
        defaults.update(kw)
        return MondayEvalRun.objects.create(**defaults)

    def write(self):
        return g.generate_week(self.week, write_fn=lambda t, f: (talk(), "m"), review_fn=lambda t, d, **kw: (PASS, "x"), strict=False)

    def test_judge_applies_the_bar(self):
        self.assertTrue(self.gate.judge(self.result())[0])
        self.assertIn("caught 76%", self.gate.judge(self.result(caught=32))[1])
        self.assertIn("wrongly blocked 50%", self.gate.judge(self.result(blocked=3))[1])
        self.assertIn("only 10 planted", self.gate.judge(self.result(caught=10, planted=10))[1])
        self.assertIn("calls failed", self.gate.judge(self.result(errors=10))[1])
        self.assertFalse(self.gate.judge(self.result(good=0))[0])

    def test_no_test_on_record_holds_the_talk(self):
        m = self.write()
        self.assertEqual(m.status, MondayMinute.HELD)
        self.assertIn("HELD for approval", m.check_log)
        self.assertFalse(MondayMinute.objects.released().exists())
        self.assertIsNone(g.due_week(dt.datetime(2026, 11, 12, tzinfo=UTC)))  # held counts as written: no second talk

    def test_a_pass_for_this_setup_publishes(self):
        self.run_record()
        self.assertEqual(self.write().status, MondayMinute.READY)

    def test_the_latest_matching_run_decides(self):
        self.run_record(passed=True, finished_at=timezone.now() - dt.timedelta(days=2))
        self.run_record(passed=False, verdict="caught 60%")
        st = self.gate.status()
        self.assertFalse(st.ok)
        self.assertIn("caught 60%", st.reason)

    def test_a_pass_for_another_setup_or_too_old_does_not_count(self):
        self.run_record(model="local:some-other-model")
        self.run_record(rag=not self.gate.setup()["rag"])
        self.run_record(finished_at=timezone.now() - dt.timedelta(days=120))
        self.assertFalse(self.gate.status().ok)

    @override_settings(MONDAY_GATE=False)
    def test_gate_can_be_switched_off(self):
        self.assertEqual(self.write().status, MondayMinute.READY)

    def approve(self, queryset=None):
        from django.contrib.admin.sites import site
        from django.test import RequestFactory
        from .admin import MondayMinuteAdmin
        admin = MondayMinuteAdmin(MondayMinute, site)
        with patch.object(admin, "message_user") as said:
            admin.approve(RequestFactory().post("/"), queryset if queryset is not None else MondayMinute.objects.all())
        return said.call_args[0][1]

    def minute(self, week, status=MondayMinute.HELD, **kw):
        kw.setdefault("publish_at", g.publish_time(week))
        return MondayMinute.objects.create(week=week, topic=self.t, status=status, title="T", **kw)

    def test_approve_publishes_now_and_only_touches_held_talks(self):
        this_week = g.next_week() - dt.timedelta(days=7)
        held = self.minute(this_week, publish_at=timezone.now() - dt.timedelta(days=1))
        blocked = self.minute(this_week - dt.timedelta(days=7), status=MondayMinute.BLOCKED)
        said = self.approve()
        held.refresh_from_db()
        blocked.refresh_from_db()
        self.assertEqual((held.status, held.approved_by_person), (MondayMinute.READY, True))
        self.assertGreater(held.publish_at, timezone.now() - dt.timedelta(minutes=1))  # so the Monday push still goes out
        self.assertIsNone(held.push_sent_at)
        self.assertEqual(blocked.status, MondayMinute.BLOCKED)
        self.assertTrue(MondayMinute.objects.released().filter(pk=held.pk).exists())
        self.assertIn("Approved 1 talk(s). 1 will send a push", said)

    def test_approving_a_backlog_notifies_once(self):
        from django.core.management import call_command
        this_week = g.next_week() - dt.timedelta(days=7)
        recent = timezone.now() - dt.timedelta(hours=2)  # inside the cron's push window, so only the approve logic stops a push
        newest = self.minute(this_week, publish_at=recent)
        older = [self.minute(this_week - dt.timedelta(days=7 * i), publish_at=recent) for i in (1, 2)]
        said = self.approve()
        self.assertIn("Approved 3 talk(s). 1 will send a push", said)
        pushed = []
        with patch("monday.management.commands.monday_minute.send_minute_push", lambda m: (pushed.append(m.pk), (True, ""))[1]), \
                patch("monday.management.commands.monday_minute.due_week", lambda: None), \
                patch("monday.management.commands.monday_minute.ai.available", lambda: False):
            call_command("monday_minute")
        self.assertEqual(pushed, [newest.pk])
        for m in older:
            m.refresh_from_db()
            self.assertEqual(m.status, MondayMinute.READY)
            self.assertIsNotNone(m.push_sent_at)
            self.assertEqual(m.publish_at, recent)  # published quietly, in its own place

    def test_approving_only_old_talks_notifies_nobody(self):
        old = self.minute(g.next_week() - dt.timedelta(days=21))
        self.assertIn("0 will send a push", self.approve())
        old.refresh_from_db()
        self.assertEqual(old.publish_at, g.publish_time(old.week))
        self.assertIsNotNone(old.push_sent_at)
        self.assertTrue(MondayMinute.objects.released().filter(pk=old.pk).exists())

    # ---- The gate is checked again after the talk was written -------------------------------------------

    def test_a_later_failed_test_holds_a_talk_that_has_not_published(self):
        self.run_record(finished_at=timezone.now() - dt.timedelta(days=2))
        ahead = self.minute(g.next_week(), status=MondayMinute.READY, check_log="Attempt 1: passed.")
        out = self.minute(g.next_week() - dt.timedelta(days=7), status=MondayMinute.READY)
        approved = self.minute(g.next_week() + dt.timedelta(days=7), status=MondayMinute.READY, approved_by_person=True)
        self.assertEqual(self.gate.hold_unpublished(), 0)  # the pass still stands
        self.run_record(passed=False, verdict="caught 60%")
        self.assertEqual(self.gate.hold_unpublished(), 1)
        for m in (ahead, out, approved):
            m.refresh_from_db()
        self.assertEqual(ahead.status, MondayMinute.HELD)
        self.assertTrue(ahead.check_log.startswith("Attempt 1: passed.\nSafety gate ("))
        self.assertIn("caught 60%", ahead.check_log)
        self.assertEqual(out.status, MondayMinute.READY)       # already published
        self.assertEqual(approved.status, MondayMinute.READY)  # a person approved it

    def test_cron_rechecks_the_gate_before_releasing(self):
        from io import StringIO
        from django.core.management import call_command
        ahead = self.minute(g.next_week(), status=MondayMinute.READY)  # written while a pass stood; none on record now
        out = StringIO()
        with patch("monday.management.commands.monday_minute.due_week", lambda: None), \
                patch("monday.management.commands.monday_minute.ai.available", lambda: False):
            call_command("monday_minute", stdout=out)
        ahead.refresh_from_db()
        self.assertEqual(ahead.status, MondayMinute.HELD)
        self.assertIn("1 talk(s) moved back to waiting for approval", out.getvalue())
        with override_settings(MONDAY_GATE=False):
            ahead.status = MondayMinute.READY
            ahead.save()
            self.assertEqual(self.gate.hold_unpublished(), 0)

    def test_restore_marks_the_talk_as_approved_by_a_person(self):
        from django.contrib.admin.sites import site
        from django.test import RequestFactory
        from .admin import MondayMinuteAdmin
        # Restore only takes back a talk that has its text and a passed check on record (a blocked draft has neither).
        m = self.minute(g.next_week(), status=MondayMinute.PULLED, intro="Intro.", points=["One."], check_log="Attempt 1: passed the CSP review.")
        admin = MondayMinuteAdmin(MondayMinute, site)
        with patch.object(admin, "message_user"):
            admin.restore(RequestFactory().post("/"), MondayMinute.objects.all())
        self.assertEqual(self.gate.hold_unpublished(), 0)
        m.refresh_from_db()
        self.assertEqual((m.status, m.approved_by_person), (MondayMinute.READY, True))

    # ---- Which runs count -------------------------------------------------------------------------------

    def test_only_conclusive_runs_count(self):
        from . import safety_eval as ev
        slugs = ev.DEFAULT_TOPICS
        self.assertEqual(self.gate.conclusive(self.result(), slugs), (True, ""))
        self.assertIn("did not cover every default topic", self.gate.conclusive(self.result(), slugs[:-1])[1])
        self.assertIn("only 10 planted", self.gate.conclusive(self.result(caught=10, planted=10), slugs)[1])
        self.assertIn("only 5 good talks", self.gate.conclusive(self.result(good=5), slugs)[1])
        self.assertIn("calls failed", self.gate.conclusive(self.result(errors=10), slugs)[1])

    def test_an_exploratory_run_neither_opens_nor_closes_the_gate(self):
        self.run_record(passed=True, conclusive=False, verdict="exploratory run")
        self.assertFalse(self.gate.status().ok)  # a small passing run does not open it
        self.run_record(finished_at=timezone.now() - dt.timedelta(days=2))
        self.run_record(passed=False, conclusive=False, verdict="exploratory run")
        self.assertTrue(self.gate.status().ok)   # and an inconclusive one does not take a real pass away

    def test_rows_from_before_the_gate_are_skipped(self):
        self.run_record(finished_at=timezone.now() - dt.timedelta(days=2))
        self.run_record(passed=False, verdict="")  # no verdict: it was never judged
        self.assertTrue(self.gate.status().ok)

    def test_each_kind_of_planted_mistake_has_a_floor(self):
        plants = {k: {"n": 6, "caught": 6, "missed": []} for k in "abcdefg"}
        plants["g"] = {"n": 6, "caught": 3, "missed": ["x"] * 3}  # 39 of 42 overall, but one kind is half missed
        r = dict(self.result(), plants=plants)
        ok, why = self.gate.judge(r)
        self.assertFalse(ok)
        self.assertIn("caught only 3 of 6 'g' mistakes", why)
        plants["g"]["caught"] = 5
        self.assertTrue(self.gate.judge(r)[0])
        plants["g"]["caught"] = 3
        with override_settings(MONDAY_GATE_MIN_CATCH_PER_KIND=0.5):
            self.assertTrue(self.gate.judge(r)[0])

    @override_settings(AI_PROVIDER="anthropic")
    def test_ai_outage_fails_the_run_instead_of_counting_errors(self):
        from . import safety_eval as ev
        from .eval_runner import run_eval

        def down(*a, **k):
            raise ai.AIUnavailable("Local AI server unavailable: timed out")

        self.run_record(finished_at=timezone.now() - dt.timedelta(days=2))
        with patch.object(ev, "review", down):
            run = run_eval([self.t], compare=False)
        self.assertEqual((run.status, run.conclusive, run.passed), ("failed", False, False))
        self.assertIn("unavailable", run.summary)
        self.assertTrue(self.gate.status().ok)  # the earlier pass still stands

        def bad_output(*a, **k):
            raise ai.GenerationError("Not valid JSON")

        with patch.object(ev, "review", bad_output):
            self.assertEqual(ev.run([self.t], rag=True, strict=False)["errors"], 1 + len(ev.PLANTS))  # still counted per case

    @override_settings(AI_PROVIDER="anthropic")
    def test_a_conclusive_failed_run_holds_talks_when_it_finishes(self):
        from . import safety_eval as ev
        from .eval_runner import run_eval
        topics = [topic(slug=s) for s in ev.DEFAULT_TOPICS]
        self.run_record(finished_at=timezone.now() - dt.timedelta(days=2))
        ahead = self.minute(g.next_week(), status=MondayMinute.READY)
        passing = {"verdict": "pass", "findings": [], "confidence": "high", "grounding": [{"point": i, "brief_key_point": i} for i in range(4)]}
        with patch.object(ev, "review", lambda *a, **k: (passing, "m")):  # a reviewer that catches nothing
            run = run_eval(topics, compare=False)
        self.assertEqual((run.status, run.conclusive, run.passed), ("done", True, False))
        self.assertTrue(run.summary.startswith("NOT PASSED"))
        self.assertIn("1 talk(s) that had not published yet", run.summary)
        ahead.refresh_from_db()
        self.assertEqual(ahead.status, MondayMinute.HELD)

    @override_settings(AI_PROVIDER="anthropic")
    def test_runner_records_the_verdict_for_the_configured_setup(self):
        from . import safety_eval as ev
        from .eval_runner import run_eval
        topics = list(MondayTopic.objects.all())
        passing = {"verdict": "pass", "findings": [], "confidence": "high", "grounding": [{"point": i, "brief_key_point": i} for i in range(4)]}
        with patch.object(ev, "review", lambda *a, **k: (passing, "m")):
            run = run_eval(topics, compare=False)
        self.assertEqual((run.status, run.passed, run.conclusive), ("done", False, False))  # one hand-picked topic is exploratory
        self.assertIn("exploratory run", run.verdict)
        self.assertIn("did not cover every default topic", run.verdict)
        self.assertEqual((run.model, run.rag, run.strict), (self.gate.reviewer_model(), True, False))
        self.assertEqual(run.false_block_rate, 0.0)
        self.assertEqual(run.catch_rate, 0.0)
        self.assertTrue(run.summary.startswith("EXPLORATORY"))
        self.assertFalse(self.gate.status().ok)
