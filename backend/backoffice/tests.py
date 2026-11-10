import datetime as dt

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from monday.models import MondayComment, MondayFeedback, MondayMinute, MondayTopic
from talks.models import AppSignup, SigninSheet

from . import metrics


@override_settings(BACKOFFICE_KEY="s3cret-key")
class AccessTests(TestCase):
    def test_needs_the_key_or_a_staff_login(self):
        self.assertEqual(self.client.get("/backoffice/").status_code, 404)
        self.assertEqual(self.client.get("/backoffice/?key=wrong").status_code, 404)
        self.assertEqual(self.client.get("/backoffice/?key=s3cret-key").status_code, 200)
        self.client.force_login(get_user_model().objects.create_user("boss", password="x", is_staff=True))
        self.assertEqual(self.client.get("/backoffice/").status_code, 200)

    @override_settings(BACKOFFICE_KEY="")
    def test_no_key_set_means_no_key_access(self):
        self.assertEqual(self.client.get("/backoffice/?key=").status_code, 404)

    def test_only_gohighlevel_may_frame_it_and_the_key_is_not_leaked(self):
        res = self.client.get("/backoffice/?key=s3cret-key")
        self.assertIn("frame-ancestors https://app.gohighlevel.com", res["Content-Security-Policy"])
        self.assertNotIn("X-Frame-Options", res)
        self.assertEqual(res["Referrer-Policy"], "no-referrer")
        self.assertIn("no-store", res["Cache-Control"])
        self.assertIn('target="_blank"', res.content.decode())  # admin links open in a new tab by default

    def test_admin_stays_unframeable_unless_switched_on(self):
        res = self.client.get("/admin/")
        self.assertEqual(res["X-Frame-Options"], "DENY")
        with self.settings(GHL_EMBED_ADMIN=True):
            res = self.client.get("/admin/")
            self.assertNotIn("X-Frame-Options", res)
            self.assertIn("frame-ancestors", res["Content-Security-Policy"])
        self.assertEqual(self.client.get("/api/health/")["X-Frame-Options"], "DENY")


class MetricsTests(TestCase):
    def setUp(self):
        self.today = dt.date(2026, 11, 12)  # a Thursday
        sheet = dict(supervisor_name="Ana", supervisor_email="ana@plant.com", status="synced")
        SigninSheet.objects.create(program="monday-minute", talk_title="Lock it", held_on=dt.date(2026, 11, 9), attendee_count=12, **sheet)
        SigninSheet.objects.create(program="zero-harm-weekly", talk_title="Heat", held_on=dt.date(2026, 11, 3), attendee_count=8, **sheet)
        SigninSheet.objects.create(program="monday-minute", talk_title="Lock it", held_on=dt.date(2026, 11, 10), attendee_count=5,
                                   supervisor_name="Bo", supervisor_email="bo@dock.com", status="failed")
        SigninSheet.objects.create(talk_title="Old", held_on=dt.date(2026, 6, 1), attendee_count=99, **sheet)
        AppSignup.objects.create(email="a@b.com")
        topic = MondayTopic.objects.first()
        self.m = MondayMinute.objects.create(week=dt.date(2026, 11, 9), publish_at=timezone.now(), topic=topic, status=MondayMinute.READY, title="Lock it")
        for i, helpful in enumerate([True, True, True, False]):
            MondayFeedback.objects.create(minute=self.m, install_hash=f"h{i}", helpful=helpful)
        MondayComment.objects.create(minute=self.m, body="x", install_hash="h", status=MondayComment.PENDING)

    def test_tiles_charts_and_attention(self):
        d = metrics.dashboard(30, today=self.today)
        tiles = {t["label"]: t for t in d["tiles"]}
        self.assertEqual(tiles["Sign-in sheets"]["value"], 3)
        self.assertEqual(tiles["Sign-in sheets"]["note"], "2 Monday Minute · 1 Zero Harm Weekly")
        self.assertEqual(tiles["Crew members signed in"]["value"], 25)
        self.assertEqual(tiles["Crew members signed in"]["note"], "2 supervisors ran a talk")
        self.assertEqual(tiles["Monday Minute thumbs up"]["value"], "75%")
        self.assertEqual(tiles["OTIS answers rated helpful"]["value"], "–")
        bars = d["sheets_chart"]["bars"]
        self.assertEqual(len(bars), 12)
        self.assertEqual([(b["week"], b["value"]) for b in bars[-2:]], [(dt.date(2026, 11, 2), 1), (dt.date(2026, 11, 9), 2)])
        self.assertEqual(d["people_chart"]["bars"][-1]["value"], 17)
        self.assertEqual(d["top_talks"][0], {"title": "Lock it", "program": "Monday Minute", "sheets": 2, "people": 17})
        self.assertEqual(d["minutes"][0]["up"], 3)
        texts = " ".join(a["text"] for a in d["attention"])
        self.assertIn("comment waiting for a check", texts)
        self.assertIn("sign-in sheet that didn't reach GoHighLevel", texts)

    def test_empty_weeks_draw_nothing_and_page_renders(self):
        chart = metrics.bars([(dt.date(2026, 11, 2), 0), (dt.date(2026, 11, 9), 4)])
        self.assertEqual(chart["bars"][0]["path"], "")
        self.assertTrue(chart["bars"][1]["path"].startswith("M"))
        with self.settings(BACKOFFICE_KEY="k"):
            html = self.client.get("/backoffice/?key=k&days=90").content.decode()
        self.assertIn("Crew members signed in per week", html)
        self.assertIn("Show as a table", html)
        self.assertIn('href="?days=30&amp;key=k"', html)
