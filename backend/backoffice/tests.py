import datetime as dt
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from monday.models import MondayComment, MondayFeedback, MondayMinute, MondayTopic
from talks.models import AppSignup, SigninSheet
from usage import geo
from usage.models import AppOpen

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

    def test_signups_tile_splits_welcome_and_settings(self):
        AppSignup.objects.create(email="w1@b.com", source="welcome")
        AppSignup.objects.create(email="w2@b.com", source="welcome")
        old = AppSignup.objects.create(email="old@b.com", source="welcome")
        AppSignup.objects.filter(pk=old.pk).update(created_at=timezone.now() - dt.timedelta(days=60))
        tile = {t["label"]: t for t in metrics.dashboard(30, today=self.today)["tiles"]}["Email sign-ups"]
        self.assertEqual((tile["value"], tile["note"]), (3, "2 welcome screen · 1 Settings · 4 in total"))

    def test_empty_weeks_draw_nothing_and_page_renders(self):
        chart = metrics.bars([(dt.date(2026, 11, 2), 0), (dt.date(2026, 11, 9), 4)])
        self.assertEqual(chart["bars"][0]["path"], "")
        self.assertTrue(chart["bars"][1]["path"].startswith("M"))
        with self.settings(BACKOFFICE_KEY="k"):
            html = self.client.get("/backoffice/?key=k&days=90").content.decode()
        self.assertIn("Crew members signed in per week", html)
        self.assertIn("Show as a table", html)
        self.assertIn('href="?days=30&amp;key=k"', html)


class UsageTests(TestCase):
    """Where the app is used: distinct phones, each counted once, in its most recent known place."""
    today = dt.date(2026, 11, 12)

    def seen(self, phone, days_ago, platform="ios", city="", region="", country="", source=None):
        AppOpen.objects.create(day=self.today - dt.timedelta(days=days_ago), install_hash=phone, platform=platform, city=city, region=region,
                               country=country, source=("network" if city or region or country else "") if source is None else source)

    def setUp(self):
        houston, dayton = dict(city="Houston", region="Texas", country="US"), dict(city="Dayton", region="Ohio", country="US")
        for days_ago in (20, 3, 0):
            self.seen("a", days_ago, **houston)               # one phone, three days: counted once
        self.seen("b", 25, **houston)
        self.seen("b", 2, source="phone", **dayton)            # moved: counts in Dayton, the most recent place
        self.seen("c", 10, platform="android", **houston)
        self.seen("c", 1, platform="android")                  # latest open has no place: the last known one is kept
        self.seen("d", 29, platform="android", city="Toronto", region="Ontario", country="CA")
        self.seen("e", 6, platform="android", country="MX")    # country only
        self.seen("f", 8)                                      # never placed
        self.seen("g", 30, **houston)                          # one day too old for 30 days
        self.seen("h", -1, **houston)                          # a row dated tomorrow is ignored

    def test_distinct_phones_by_period_platform_and_place(self):
        u = metrics.usage(30, today=self.today)
        self.assertEqual((u["phones"], u["phones_week"]), (6, 4))  # a, b, c and e were seen in the last 7 days
        self.assertEqual((u["ios"], u["android"]), (3, 3))
        self.assertEqual((u["from_phone"], u["from_network"], u["unknown"]), (1, 4, 1))
        self.assertEqual(u["countries"], [
            {"name": "United States", "within": "", "phones": 3}, {"name": "Canada", "within": "", "phones": 1},
            {"name": "Mexico", "within": "", "phones": 1}, {"name": "Unknown", "within": "", "phones": 1}])
        self.assertEqual(u["regions"], [
            {"name": "Texas", "within": "United States", "phones": 2}, {"name": "Ohio", "within": "United States", "phones": 1},
            {"name": "Ontario", "within": "Canada", "phones": 1}, {"name": "Unknown", "within": "", "phones": 2}])
        self.assertEqual(u["cities"], [
            {"name": "Houston", "within": "Texas, United States", "phones": 2}, {"name": "Dayton", "within": "Ohio, United States", "phones": 1},
            {"name": "Toronto", "within": "Ontario, Canada", "phones": 1}, {"name": "Unknown", "within": "", "phones": 2}])
        self.assertEqual(sum(r["phones"] for r in u["cities"]), u["phones"])
        self.assertEqual(metrics.usage(90, today=self.today)["phones"], 7)

    def test_new_phones_are_first_ever_opens_in_the_period(self):
        self.assertEqual(metrics.usage(30, today=self.today)["new_phones"], 6)  # g was first seen a day before the period
        self.seen("z", 200)
        self.seen("z", 1)  # active again in the period, but not new
        u = metrics.usage(30, today=self.today)
        self.assertEqual((u["phones"], u["new_phones"]), (7, 6))
        self.assertEqual(metrics.usage(365, today=self.today)["new_phones"], 8)

    def test_only_the_top_ten_places_are_listed(self):
        AppOpen.objects.all().delete()
        for i in range(13):
            for phone in range(2 if i < 3 else 1):
                self.seen(f"p{i}-{phone}", 1, city=f"City {i:02d}", region="Texas", country="US")
        cities = metrics.usage(30, today=self.today)["cities"]
        self.assertEqual(len(cities), 11)
        self.assertEqual(cities[0], {"name": "City 00", "within": "Texas, United States", "phones": 2})
        self.assertEqual(cities[-1], {"name": "All other places", "within": "", "phones": 3})

    @override_settings(BACKOFFICE_KEY="k")
    def test_page_shows_the_section_and_credits_db_ip_only_when_in_use(self):
        with mock.patch.object(metrics.timezone, "localdate", return_value=self.today), mock.patch.object(geo, "available", return_value=True):
            html = self.client.get("/backoffice/?key=k").content.decode()
        for text in ("Where the app is used", "Phones active, last 7 days", "Phones active, last 30 days", "New phones, last 30 days", "3 iPhone · 3 Android",
                     "Places are approximate", "company VPN or a cellular network", "States and regions", "<td>Houston</td><td>Texas, United States</td>",
                     '<a href="https://db-ip.com" target="_blank" rel="noopener">IP geolocation by DB-IP</a>'):
            self.assertIn(text, html)
        self.assertNotIn("—", html)
        # The credit stays while places that came from the database are on the page, even if the file is gone now.
        with mock.patch.object(geo, "available", return_value=False):
            self.assertIn("DB-IP", self.client.get("/backoffice/?key=k").content.decode())
            AppOpen.objects.filter(source=AppOpen.NETWORK).delete()
            self.assertNotIn("DB-IP", self.client.get("/backoffice/?key=k").content.decode())

    @override_settings(BACKOFFICE_KEY="k")
    def test_empty_state(self):
        AppOpen.objects.all().delete()
        html = self.client.get("/backoffice/?key=k").content.decode()
        self.assertIn("No app opens counted in the last 30 days", html)
        self.assertNotIn("<h2>Cities</h2>", html)
        with self.settings(USAGE_ENABLED=False):
            self.assertIn("switched off on the server", self.client.get("/backoffice/?key=k").content.decode())
