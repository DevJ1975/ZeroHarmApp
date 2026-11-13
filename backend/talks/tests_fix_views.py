"""Tests for the fixes in the "views" group: the invite link, the public endpoints in talks/views.py, the usage count
and the back office key. Each test failed before its fix and passes with it. Nothing here touches the network."""
import base64
import datetime as dt
import hashlib
import http.client
import importlib
import json
from io import StringIO
from unittest import mock

from django.core.cache import cache, caches
from django.core.management import call_command
from django.db import connection
from django.test import RequestFactory, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from invite import tagging
from invite import views as invite_views
from invite.models import InviteClick

from . import console, owner_alerts, views, weather
from .models import AppSignup, FeedItem, GhlSync, OtisFeedback, OtisModelRelease, OtisRollout, SigninSheet, SignupPhone, SignupRemoval, TalkSuggestion
from .tests import CONSENT, GHL_ON, INSTALL, KEY, OTHER, GhlTestCase

GHL = override_settings(GHL_PRIVATE_TOKEN="t", GHL_LOCATION_ID="loc")
PDF = base64.b64encode(b"%PDF-1.7 test").decode()
# A real-looking address that Django's email check accepts but that is longer than the 254 characters the columns hold.
LONG_EMAIL = "a" * 60 + "@" + ".".join(["b" * 60] * 4) + ".com"


def post(client, path, body, **extra):
    """Sends `body` as JSON. A str is sent as it is, so a test can send JSON that json.dumps would not write."""
    return client.post(path, body if isinstance(body, str) else json.dumps(body), content_type="application/json", **extra)


class Clock:
    """Stands in for time.time, which the in-memory cache uses to end a rate-limit hour."""

    def __init__(self):
        self.now = 1_800_000_000.0

    def __call__(self):
        return self.now

    def forward(self, minutes):
        self.now += minutes * 60


# ---- Invite link ------------------------------------------------------------------------------------------------

def _ghl_like_the_real_one(method, path, **kwargs):
    """What talks.ghl.request does with a contact id that holds a control character: Python's HTTP client refuses
    the address with InvalidURL, which is not a GhlError."""
    if any(ord(ch) < 33 for ch in path):
        raise http.client.InvalidURL(f"URL can't contain control characters. {path!r}")
    return {}


@GHL
class InviteLinkTests(TestCase):
    def setUp(self):
        cache.clear()

    def get(self, query):
        return self.client.get("/get/?" + query, HTTP_USER_AGENT="Mozilla/5.0 (Windows NT 10.0)", REMOTE_ADDR="203.0.113.7")

    def test_a_contact_id_ending_in_a_newline_is_not_stored_or_sent(self):
        with mock.patch("talks.ghl.request", side_effect=_ghl_like_the_real_one) as req:
            res = self.get("c=NewlineContact00001%0A")
            longest = self.get("c=" + "B" * 40 + "%0A")  # 41 characters: too long for the column on PostgreSQL
        self.assertEqual((res.status_code, longest.status_code), (200, 200))
        self.assertEqual(InviteClick.objects.count(), 0)
        req.assert_not_called()
        for junk in ("abcdefghij\n", "abcdefghij\r", "\nabcdefghij", "abcde fghij", "abcdefghij\x00"):
            self.assertIsNone(invite_views.CONTACT_ID.fullmatch(junk), repr(junk))
        self.assertIsNotNone(invite_views.CONTACT_ID.fullmatch("aBcD1234eFgH5678iJkL"))

    def test_a_bad_row_already_in_the_table_is_closed_and_the_others_are_still_tagged(self):
        bad = InviteClick.objects.create(contact_id="NewlineContact00001\n", platform="other")
        good = InviteClick.objects.create(contact_id="GoodContact000000001", platform="ios")
        with mock.patch("talks.ghl.request", side_effect=_ghl_like_the_real_one) as req:
            self.assertEqual(tagging.retry_tags(), 2)  # both need nothing more
            self.assertEqual(tagging.retry_tags(), 0)  # and neither is tried again
        self.assertEqual(req.call_count, 1)
        self.assertEqual(req.call_args.args[1], "/contacts/GoodContact000000001/tags")
        bad.refresh_from_db()
        good.refresh_from_db()
        self.assertTrue(bad.contact_missing)
        self.assertIsNotNone(bad.tagged_at)
        self.assertIsNotNone(good.tagged_at)
        self.assertFalse(good.contact_missing)

    def test_an_error_nobody_expected_reaches_neither_the_visitor_nor_the_cron(self):
        with mock.patch("talks.ghl.request", side_effect=RuntimeError("boom")):
            res = self.get("c=aBcD1234eFgH5678iJkL")
            self.assertEqual(res.status_code, 200)
            self.assertEqual(tagging.retry_tags(), 0)  # still waiting, and nothing was raised
        self.assertIsNone(InviteClick.objects.get().tagged_at)
        with mock.patch("talks.ghl.request", return_value={}):
            self.assertEqual(tagging.retry_tags(), 1)

    def test_one_row_that_cannot_be_saved_does_not_stop_the_rows_after_it(self):
        first = InviteClick.objects.create(contact_id="FirstContact00000001", platform="ios")
        second = InviteClick.objects.create(contact_id="SecondContact0000001", platform="ios")
        InviteClick.objects.filter(pk=first.pk).update(created_at=timezone.now() - dt.timedelta(hours=1))
        real = tagging.tag_click

        def fails_on_the_first(click, timeout=10):
            if click.pk == first.pk:
                raise RuntimeError("the database hiccuped")
            return real(click, timeout=timeout)

        with mock.patch("talks.ghl.request", return_value={}), mock.patch("invite.tagging.tag_click", side_effect=fails_on_the_first):
            self.assertEqual(tagging.retry_tags(), 1)
        second.refresh_from_db()
        self.assertIsNotNone(second.tagged_at)

    def test_the_cron_reaches_the_steps_after_the_invite_retry(self):
        InviteClick.objects.create(contact_id="NewlineContact00001\n", platform="other")
        with mock.patch("talks.management.commands.cron.call_command") as later, \
             mock.patch("talks.ghl.request", side_effect=_ghl_like_the_real_one), \
             mock.patch("talks.owner_alerts.retry_signup_alerts", return_value=0), mock.patch("talks.owner_alerts.retry_removals", return_value=0), \
             mock.patch("talks.management.commands.cron.sync_episodes", return_value=[]):
            call_command("cron", stdout=StringIO())
        ran = [c.args[0] for c in later.call_args_list]
        for step in ("owner_digest", "regs_sync", "monday_minute"):
            self.assertIn(step, ran)

    @override_settings(GHL_PRIVATE_TOKEN="", GHL_LOCATION_ID="")
    def test_the_limit_counts_the_caller_not_the_edge(self):
        """On Railway the caller is in X-Real-IP and the last X-Forwarded-For entry is an edge address that changes."""
        for i in range(invite_views.NEW_CLICKS_PER_HOUR + 5):
            self.client.get("/get/", {"c": f"contact{i:06d}"}, HTTP_X_REAL_IP="198.51.100.9",
                            HTTP_X_FORWARDED_FOR=f"198.51.100.9, 100.64.0.{i + 1}", REMOTE_ADDR="10.0.0.1")
        self.assertEqual(InviteClick.objects.count(), invite_views.NEW_CLICKS_PER_HOUR)
        self.client.get("/get/", {"c": "othercaller0001"}, HTTP_X_REAL_IP="198.51.100.10",
                        HTTP_X_FORWARDED_FOR="198.51.100.10, 100.64.0.1", REMOTE_ADDR="10.0.0.1")  # same edge hop, another caller
        self.assertTrue(InviteClick.objects.filter(contact_id="othercaller0001").exists())


# ---- Who is calling, and the hourly limits ----------------------------------------------------------------------

class CallerTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_client_ip_is_the_shared_helper(self):
        rf = RequestFactory()
        on_railway = rf.get("/", HTTP_X_REAL_IP="203.0.113.7", HTTP_X_FORWARDED_FOR="203.0.113.7, 100.64.0.9", REMOTE_ADDR="10.0.0.5")
        self.assertEqual(views._client_ip(on_railway), "203.0.113.7")
        self.assertEqual(views._client_ip(rf.get("/", HTTP_X_FORWARDED_FOR="junk")), "127.0.0.1")  # never junk
        self.assertEqual(views._network(rf.get("/", HTTP_X_REAL_IP="2001:db8:1:2::1")), views._network(rf.get("/", HTTP_X_REAL_IP="2001:db8:1:2::ffff")))
        self.assertNotEqual(views._network(rf.get("/", HTTP_X_REAL_IP="2001:db8:1:2::1")), views._network(rf.get("/", HTTP_X_REAL_IP="2001:db8:1:3::1")))

    def remove(self, **extra):
        return post(self.client, "/api/signups/remove/", {"install_id": "zh-test-phone-000001"}, **extra).status_code

    def test_removals_are_counted_per_caller_when_the_edge_hop_changes(self):
        codes = [self.remove(HTTP_X_REAL_IP="203.0.113.7", HTTP_X_FORWARDED_FOR=f"203.0.113.7, 100.64.0.{i + 1}") for i in range(6)]
        self.assertEqual(codes, [200] * 5 + [429])
        # Another caller arriving through the very same edge address has its own count.
        self.assertEqual(self.remove(HTTP_X_REAL_IP="203.0.113.8", HTTP_X_FORWARDED_FOR="203.0.113.8, 100.64.0.1"), 200)

    def test_the_hour_ends_an_hour_after_its_first_try(self):
        clock = Clock()
        with mock.patch("time.time", clock):
            codes = []
            for _ in range(8):  # one removal every 50 minutes: never more than 2 in any hour, limit 5
                codes.append(self.remove())
                clock.forward(50)
        self.assertEqual(codes, [200] * 8)

    def test_a_burst_is_still_refused_and_clears_after_the_hour(self):
        clock = Clock()
        with mock.patch("time.time", clock):
            self.assertEqual([self.remove() for _ in range(7)], [200] * 5 + [429, 429])
            clock.forward(59)
            self.assertEqual(self.remove(), 429)  # refused tries do not push the end of the hour back
            clock.forward(2)
            self.assertEqual(self.remove(), 200)

    def suggest(self, **extra):
        self.ideas = getattr(self, "ideas", 0) + 1  # a new idea each time: the same one twice is taken for a resend
        return post(self.client, "/api/suggestions/", {"topic": f"Battery charging stations, part {self.ideas}"}, **extra).status_code

    def sheet(self, **extra):
        body = {"pdf_base64": base64.b64encode(b"%PDF-1.7 " + str(extra).encode()).decode(), "supervisor_email": "lead@plant.com", "held_on": "2027-06-07"}
        return post(self.client, "/api/signin-sheets/", body, **extra).status_code

    def test_a_slow_trickle_of_suggestions_and_sheets_is_never_refused(self):
        clock = Clock()
        with mock.patch("time.time", clock), mock.patch("talks.views.sync_suggestion_to_ghl"), mock.patch("talks.views.sync_sheet_to_ghl", return_value=False):
            ideas, sheets = [], []
            for i in range(32):
                if i < 12:
                    ideas.append(self.suggest())
                sheets.append(self.sheet(HTTP_X_REAL_IP="203.0.113.9", HTTP_X_FORWARDED_FOR=f"203.0.113.9, 100.64.1.{i + 1}"))
                clock.forward(50)
        self.assertEqual(ideas, [201] * 12)   # limit 10 an hour
        self.assertEqual(sheets, [201] * 32)  # limit 30 an hour

    def test_one_ipv6_network_cannot_dodge_the_sheet_and_suggestion_limits(self):
        with mock.patch("talks.views.sync_suggestion_to_ghl"), mock.patch("talks.views.sync_sheet_to_ghl", return_value=False):
            sheets = [self.sheet(HTTP_X_FORWARDED_FOR=f"2001:db8:5:5::{i + 1:x}") for i in range(40)]
            ideas = [self.suggest(HTTP_X_FORWARDED_FOR=f"2001:db8:5:5::{i + 1:x}") for i in range(25)]
            other = self.suggest(HTTP_X_FORWARDED_FOR="2001:db8:5:6::1")
        self.assertEqual((sheets.count(201), sheets.count(429)), (30, 10))
        self.assertEqual((ideas.count(201), ideas.count(429)), (10, 15))
        self.assertEqual(other, 201)

    def test_no_readable_address_is_kept_in_the_cache(self):
        with mock.patch("talks.views.sync_suggestion_to_ghl"), mock.patch("talks.views.sync_sheet_to_ghl", return_value=False):
            self.sheet(HTTP_X_FORWARDED_FOR="203.0.113.77")
            self.suggest(HTTP_X_FORWARDED_FOR="203.0.113.77")
        keys = " ".join(str(k) for store in (cache, caches["limits"]) for k in store._cache.keys())
        self.assertIn("sheet-rate:", keys)
        self.assertNotIn("203.0.113.77", keys)


class UsageCallerTests(TestCase):
    def setUp(self):
        cache.clear()

    def open(self, install, **extra):
        return post(self.client, "/api/v2/app/open", {"install_id": install, "platform": "ios"}, **extra)

    def test_the_place_is_looked_up_for_the_caller_not_the_edge(self):
        with mock.patch("usage.geo.lookup", return_value={"country": "US", "region": "Texas", "city": "Houston"}) as lookup:
            self.open("zh-usage-0001", HTTP_X_REAL_IP="203.0.113.9", HTTP_X_FORWARDED_FOR="203.0.113.9, 100.64.0.1")
        lookup.assert_called_once_with("203.0.113.9")

    def test_the_limit_counts_the_caller_and_has_its_own_counter(self):
        codes = [self.open(f"zh-usage-{i:05d}", HTTP_X_REAL_IP="203.0.113.9", HTTP_X_FORWARDED_FOR=f"203.0.113.9, 100.64.0.{i + 1}").status_code
                 for i in range(65)]
        self.assertEqual((codes.count(200), codes.count(429)), (60, 5))
        keys = [str(k) for k in caches["limits"]._cache.keys()]
        self.assertTrue(any("throttle:app-open:" in k for k in keys), keys)
        self.assertNotIn("203.0.113.9", " ".join(keys))


# ---- Weather ----------------------------------------------------------------------------------------------------

class WeatherLimitTests(TestCase):
    def setUp(self):
        cache.clear()
        self.outside, self.timeouts, self.down = [], [], False
        patcher = mock.patch("talks.weather._get", side_effect=self.fake_weather_service)
        patcher.start()
        self.addCleanup(patcher.stop)

    def fake_weather_service(self, url, timeout=None):
        self.outside.append(url)
        self.timeouts.append(timeout)
        if self.down:
            raise TimeoutError("timed out")
        if "/points/" in url:
            return {"properties": {"forecastHourly": "https://api.weather.gov/hourly", "relativeLocation": {"properties": {"city": "Midland", "state": "TX"}}}}
        if url.endswith("/hourly"):
            return {"properties": {"periods": [{"temperature": 70, "temperatureUnit": "F", "relativeHumidity": {"value": 40},
                                                "shortForecast": "Sunny", "windSpeed": "5 mph"}]}}
        return {"features": []}

    def weather(self, lat, lon=-100.0, **extra):
        return self.client.get(f"/api/weather/?lat={lat:.2f}&lon={lon:.2f}", **extra).status_code

    def test_lookups_are_limited_per_network(self):
        limit = views.WEATHER_LOOKUPS_PER_HOUR
        codes = [self.weather(30 + i / 100) for i in range(limit + 10)]
        self.assertEqual((codes.count(200), codes.count(429)), (limit, 10))
        self.assertEqual(len(self.outside), 3 * limit)  # a refused call makes no outside request
        self.assertEqual(self.weather(40.0, REMOTE_ADDR="198.51.100.4"), 200)  # another network has its own count

    def test_a_point_already_looked_up_is_free(self):
        """A whole crew on one plant Wi-Fi asks for the same point: that costs one lookup, so nobody is refused."""
        tries = views.WEATHER_LOOKUPS_PER_HOUR + 20
        self.assertEqual([self.weather(31.99) for _ in range(tries)], [200] * tries)
        self.assertEqual(len(self.outside), 3)

    def test_points_outside_the_us_and_bad_input_are_not_counted(self):
        self.assertEqual({self.weather(10, -100 - i) for i in range(150)}, {404})
        self.assertEqual(self.client.get("/api/weather/?lat=x&lon=y").status_code, 400)
        self.assertEqual({self.client.get(f"/api/weather/?lat={lat}&lon=-100").status_code for lat in ("nan", "inf", "-inf", "1e999")}, {404})
        self.assertEqual(self.weather(30.0), 200)
        self.assertEqual(len(self.outside), 3)

    def test_changing_address_inside_one_ipv6_network_does_not_dodge_it(self):
        codes = [self.weather(30 + i / 100, HTTP_X_FORWARDED_FOR=f"2001:db8:9:9::{i + 1:x}") for i in range(views.WEATHER_LOOKUPS_PER_HOUR + 5)]
        self.assertEqual(codes.count(429), 5)

    def test_weather_from_many_networks_cannot_push_the_other_limits_out(self):
        """The counters shared a 300-entry cache with the weather answers. One weather call from each of 330 networks,
        or two from each of the 256 networks of one home connection, emptied it and every used-up limit was new again."""
        remove = lambda: post(self.client, "/api/signups/remove/", {"install_id": "zh-test-phone-000001"}).status_code
        self.assertEqual([remove() for _ in range(6)], [200] * 5 + [429])
        codes = {self.weather(30 + i / 100, HTTP_X_FORWARDED_FOR=f"2001:db8:{i:x}:1::1") for i in range(330)}
        codes |= {self.weather(35 + i / 100 + j / 10, HTTP_X_FORWARDED_FOR=f"2001:db8:aa00:{i:x}::1") for i in range(256) for j in range(2)}
        self.assertEqual(codes, {200})
        self.assertEqual(remove(), 429)  # the removal limit is still in force
        self.assertFalse(any("-rate:" in str(k) for k in cache._cache))  # no counter sits with the weather answers

    def test_fifty_phones_behind_one_address_can_each_refresh_every_ten_minutes(self):
        """A phone carrier puts many phones behind one address. Each phone is at its own site and asks again when its
        ten minutes are up. With 60 lookups an hour, 12 such phones were all refused in the sixth round."""
        for minutes in (10, 10.5):
            cache.clear()
            caches["limits"].clear()
            clock, codes = Clock(), []
            with mock.patch("time.time", clock):
                for _ in range(19):  # a little over three hours
                    codes += [self.weather(30 + phone / 10, HTTP_X_REAL_IP="198.51.100.20") for phone in range(50)]
                    clock.forward(minutes)
            self.assertEqual((codes.count(200), len(codes)), (950, 950), minutes)

    def test_an_outage_does_not_use_up_the_allowance_and_is_not_hammered(self):
        clock = Clock()
        with mock.patch("time.time", clock):
            self.down = True
            self.assertEqual({self.weather(31.0) for _ in range(70)}, {503})
            self.assertEqual(len(self.outside), 1)  # asked once; the other 69 were answered from the memory of that failure
            self.down = False
            self.assertEqual(self.weather(31.0), 503)  # still inside the two minutes
            clock.forward(2.1)
            self.assertEqual(self.weather(31.0), 200)  # the service is back, and so is this network
            # The failed try cost nothing: the whole hour's allowance, less the one lookup that worked, is still there.
            rest = [self.weather(32 + i / 100) for i in range(views.WEATHER_LOOKUPS_PER_HOUR)]
            self.assertEqual((rest.count(200), rest.count(429)), (views.WEATHER_LOOKUPS_PER_HOUR - 1, 1))

    def test_one_network_cannot_hammer_a_failing_service_with_new_points(self):
        clock = Clock()
        with mock.patch("time.time", clock):
            self.down = True
            self.assertEqual({self.weather(30 + i / 100) for i in range(40)}, {503})
            self.assertEqual(len(self.outside), views.WEATHER_FAILURES)  # then it stops asking for this network
            self.assertEqual(self.weather(45.0, REMOTE_ADDR="198.51.100.4"), 503)
            self.assertEqual(len(self.outside), views.WEATHER_FAILURES + 1)  # another network still gets its own try
            clock.forward(views.WEATHER_FAILURE_SECONDS / 60 + 0.1)
            self.down = False
            self.assertEqual(self.weather(30.0), 200)  # two minutes later it asks again, and the answer is there

    def test_the_three_outside_requests_share_nine_seconds(self):
        """Each request used to get 10 seconds, 30 in all, with the phone gone after 10 and a server thread held."""
        now = [1000.0]

        def slow_but_answering(url, timeout=None):
            now[0] += timeout  # every request takes all the time it is given
            return self.fake_weather_service(url, timeout)

        with mock.patch("talks.weather._get", side_effect=slow_but_answering), mock.patch("talks.weather.time.monotonic", lambda: now[0]):
            self.assertEqual(self.weather(33.0), 200)
        self.assertEqual(len(self.timeouts), 3)
        self.assertLessEqual(max(self.timeouts), weather.CALL_SECONDS)
        self.assertLessEqual(sum(self.timeouts), weather.LOOKUP_SECONDS)
        self.assertLess(weather.LOOKUP_SECONDS, 10)  # the app stops waiting after 10 seconds


class WeatherTimeoutTests(TestCase):
    def test_no_request_to_the_weather_service_waits_ten_seconds(self):
        cache.clear()
        waits = []

        class Answer:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def read(self):
                return json.dumps({"properties": {"forecastHourly": "https://api.weather.gov/hourly", "periods": [{"temperature": 70, "temperatureUnit": "F"}]},
                                   "features": []}).encode()

        def urlopen(request, timeout=None):
            waits.append(timeout)
            return Answer()

        with mock.patch("urllib.request.urlopen", side_effect=urlopen):
            self.assertEqual(weather.conditions(30.0, -100.0)["temp_f"], 70)
        self.assertEqual(len(waits), 3)
        self.assertTrue(all(w is not None and w <= 4 for w in waits), waits)

# ---- Feed and ingest --------------------------------------------------------------------------------------------

@override_settings(INGEST_KEY=KEY)
class FeedAndIngestTests(TestCase):
    def ingest(self, body, key=KEY):
        return post(self.client, "/api/ingest/", body, HTTP_X_ZEROHARM_KEY=key)

    def test_an_unknown_kind_never_reaches_the_database(self):
        self.ingest({"kind": "course", "title": "A course"})
        self.ingest({"kind": "alert", "title": "An alert"})
        for query in ("%00", "alert%00", "bogus", ",,,"):
            with self.assertNumQueries(0):
                res = self.client.get("/api/feed/?kind=" + query)
            self.assertEqual((res.status_code, res.json()), (200, {"items": []}), query)
        mixed = self.client.get("/api/feed/?kind=course,%00alert").json()["items"]
        self.assertEqual([i["kind"] for i in mixed], ["course"])
        self.assertEqual(len(self.client.get("/api/feed/").json()["items"]), 2)

    def test_a_key_with_other_letters_is_just_a_wrong_key(self):
        res = self.client.post("/api/ingest/", "{}", content_type="application/json", headers={"X-ZeroHarm-Key": "clé"})
        self.assertEqual(res.status_code, 401)

    def test_a_body_that_is_not_an_object_is_refused(self):
        for body in ("[]", "[1]", '"x"', "123", "null"):
            res = self.ingest(body)
            self.assertEqual((res.status_code, res.json()), (400, {"error": "Send JSON."}), body)

    def test_sync_year_needs_a_sensible_year(self):
        for year in (-5, 0, 1999, 99999999999999999999, "soon", None, 1e999, [2028]):
            res = self.ingest('{"action": "sync_year", "year": 1e999}' if year == 1e999 else {"action": "sync_year", "year": year})
            self.assertEqual(res.status_code, 400, year)
        self.assertFalse(GhlSync.objects.exists())
        self.assertEqual(self.ingest({"action": "sync_year", "year": "2028"}).status_code, 202)
        self.assertEqual(GhlSync.objects.get().year, 2028)

    def test_a_date_too_far_off_is_refused_not_a_crash(self):
        for field in ("publish_at", "expires_at"):
            res = self.ingest({"kind": "tool", "title": "Date test", field: "9999-12-31 23:59"})
            self.assertEqual(res.status_code, 400, field)
            self.assertIn(field, res.json()["error"])
        self.assertFalse(FeedItem.objects.exists())

    def test_an_effective_date_that_cannot_be_read_is_refused(self):
        for value in ("garbage", "January 3, 2027", "2027-02-30"):
            res = self.ingest({"kind": "alert", "title": "Rule", "effective_date": value, "external_id": "rule-1"})
            self.assertEqual(res.status_code, 400, value)
        self.assertIn("effective_date", self.ingest({"kind": "alert", "title": "Rule", "effective_date": "garbage"}).json()["error"])
        self.assertFalse(FeedItem.objects.exists())
        self.assertEqual(self.ingest({"kind": "alert", "title": "Rule", "effective_date": "2027-01-03", "external_id": "rule-1"}).status_code, 201)
        # An update with a date that cannot be read must not wipe the date that is there.
        self.assertEqual(self.ingest({"kind": "alert", "title": "Rule", "effective_date": "soon", "external_id": "rule-1"}).status_code, 400)
        self.assertEqual(FeedItem.objects.get().effective_date, dt.date(2027, 1, 3))

    def test_an_effective_date_of_null_means_no_date(self):
        """GoHighLevel sends null for an empty field. For a while that was refused and the item was not published."""
        res = self.ingest({"kind": "alert", "title": "Rule", "effective_date": None, "external_id": "rule-2"})
        self.assertEqual(res.status_code, 201)
        self.assertIsNone(FeedItem.objects.get().effective_date)
        self.assertEqual(self.ingest({"kind": "alert", "title": "Rule", "effective_date": "2027-01-03", "external_id": "rule-2"}).status_code, 200)
        self.assertEqual(FeedItem.objects.get().effective_date, dt.date(2027, 1, 3))
        self.ingest({"kind": "alert", "title": "Rule", "effective_date": "", "external_id": "rule-2"})  # blank: leave it as it is
        self.ingest({"kind": "alert", "title": "Rule", "external_id": "rule-2"})                        # not sent: the same
        self.assertEqual(FeedItem.objects.get().effective_date, dt.date(2027, 1, 3))
        self.assertEqual(self.ingest({"kind": "alert", "title": "Rule", "effective_date": None, "external_id": "rule-2"}).status_code, 200)
        self.assertIsNone(FeedItem.objects.get().effective_date)  # null on an update clears it

    def test_an_effective_date_is_read_in_every_spelling_publish_at_takes(self):
        for i, (sent, day) in enumerate((("2027/01/03", (2027, 1, 3)), ("2027-01-04 08:30", (2027, 1, 4)), ("2027/01/05 08:30", (2027, 1, 5)),
                                         ("2027-01-06T23:30:00-08:00", (2027, 1, 6)), (" 2027-01-07 ", (2027, 1, 7)))):
            res = self.ingest({"kind": "alert", "title": f"Rule {i}", "effective_date": sent, "publish_at": sent})
            self.assertEqual(res.status_code, 201, sent)
            self.assertEqual(FeedItem.objects.get(title=f"Rule {i}").effective_date, dt.date(*day), sent)  # the day as written
        for junk in ("2027-01-03 soon", "2027-01-03x", ["2027-01-03"], {"d": 1}, "\ud800"):
            body = json.dumps({"kind": "alert", "title": "Junk", "effective_date": junk})
            self.assertEqual(self.ingest(body).status_code, 400, junk)
        self.assertFalse(FeedItem.objects.filter(title="Junk").exists())

    def test_an_expiry_of_null_means_it_does_not_expire(self):
        """null was read as "now": the item was published and left the app in the same moment."""
        self.assertEqual(self.ingest({"kind": "tool", "title": "Ladder checklist", "expires_at": None}).status_code, 201)
        self.assertIsNone(FeedItem.objects.get().expires_at)
        self.assertEqual(len(self.client.get("/api/feed/").json()["items"]), 1)
        self.ingest({"kind": "tool", "title": "Ladder checklist", "expires_at": "2031-01-01 08:00"})
        self.assertIsNotNone(FeedItem.objects.get().expires_at)
        self.ingest({"kind": "tool", "title": "Ladder checklist", "expires_at": None})
        self.assertIsNone(FeedItem.objects.get().expires_at)

    def test_lists_objects_and_broken_characters_where_text_belongs(self):
        for field in ("title", "kind", "jurisdiction"):
            for junk in ([], ["a"], {}, {"a": 1}):
                res = self.ingest({"kind": "tool", "title": "Typed", field: junk})
                self.assertEqual(res.status_code, 400, (field, junk))
        res = self.ingest({"kind": "tool", "title": "Typed", "summary": ["a"], "body": {"a": 1}, "link": [], "image": {}, "external_id": ["x"],
                           "send_push": [], "featured": {}, "publish_at": None})
        self.assertEqual(res.status_code, 201)
        item = FeedItem.objects.get()
        self.assertEqual((item.summary, item.body_md, item.link_url, item.image_url, item.external_id), ("", "", "", "", "tool:typed"))
        for field in ("publish_at", "expires_at"):
            self.assertEqual(self.ingest({"kind": "tool", "title": "Typed", field: ["2027-01-01"]}).status_code, 400, field)
        # Half a surrogate pair is valid JSON and cannot be written as UTF-8.
        res = self.ingest('{"kind": "tool", "title": "Half \\ud83d an emoji", "summary": "\\ud800", "body": "x\\udfff", "external_id": "id-\\ud800"}')
        self.assertEqual(res.status_code, 201)
        item = FeedItem.objects.get(external_id="id-")
        self.assertEqual((item.title, item.summary, item.body_md), ("Half  an emoji", "", "x"))
        res = self.ingest('{"kind": "tool", "title": "\\ud800"}')
        self.assertEqual(res.status_code, 400)  # nothing is left of the title

    def test_a_link_longer_than_the_column_is_refused_with_a_reason(self):
        room = FeedItem._meta.get_field("link_url").max_length
        self.assertEqual(room, 500)  # was 200, which signed and tracking links run past
        start = "https://example.com/"
        for field in ("link", "image"):
            res = self.ingest({"kind": "tool", "title": "Long", field: start + "a" * (620 - len(start)), "external_id": f"long-{field}"})
            self.assertEqual(res.status_code, 400, field)
            self.assertIn(str(room), res.json()["error"])
            self.assertIn("620", res.json()["error"])
        self.assertFalse(FeedItem.objects.exists())  # nothing half-saved, nothing cut short
        fits = start + "a" * (room - len(start))
        self.assertEqual(self.ingest({"kind": "tool", "title": "Fits", "link": fits, "image": fits}).status_code, 201)
        self.assertEqual(FeedItem.objects.get().link_url, fits)

    def test_nul_characters_are_dropped_from_text(self):
        res = self.ingest({"kind": "tool", "title": "nul \u0000 title", "summary": "a\u0000b", "body": "c\u0000d", "external_id": "nul\u0000-1"})
        self.assertEqual(res.status_code, 201)
        item = FeedItem.objects.get()
        self.assertEqual((item.title, item.summary, item.body_md, item.external_id), ("nul  title", "ab", "cd", "nul-1"))


@override_settings(BACKOFFICE_KEY="s3cret-key")
class BackOfficeKeyTests(TestCase):
    def test_a_key_with_other_letters_gets_the_same_404_as_any_wrong_key(self):
        self.assertEqual(self.client.get("/backoffice/?key=cl%C3%A9").status_code, 404)
        self.assertEqual(self.client.get("/backoffice/?key=wrong").status_code, 404)
        self.assertEqual(self.client.get("/backoffice/?key=s3cret-key").status_code, 200)


class BodyTests(TestCase):
    """Bodies json.loads refuses in ways the views did not expect: bytes that are not UTF-8 raise UnicodeDecodeError
    and very deep nesting raises RecursionError, neither of which is a JSONDecodeError."""

    def setUp(self):
        cache.clear()

    @override_settings(INGEST_KEY=KEY)
    def test_bytes_that_are_not_utf8_and_very_deep_nesting_get_the_usual_answer(self):
        for body in (b"\xc3\x28", b"[" * 100000):
            answers = {path: self.client.post(path, body, content_type="application/json", HTTP_X_ZEROHARM_KEY=KEY).status_code
                       for path in ("/api/signups/", "/api/signups/remove/", "/api/signin-sheets/", "/api/suggestions/", "/api/ingest/")}
            self.assertEqual(answers, {"/api/signups/": 400, "/api/signups/remove/": 200, "/api/signin-sheets/": 400,
                                       "/api/suggestions/": 400, "/api/ingest/": 400}, body[:4])


# ---- Sign-in sheets and suggestions -----------------------------------------------------------------------------

class SheetInputTests(TestCase):
    def setUp(self):
        cache.clear()
        patcher = mock.patch("talks.views.sync_sheet_to_ghl", return_value=False)
        self.sync = patcher.start()
        self.addCleanup(patcher.stop)

    def send(self, **extra):
        body = {"pdf_base64": PDF, "supervisor_email": "lead@plant.com", "supervisor_name": "Ana Ruiz", "held_on": "2027-06-07",
                "talk_title": "Heat Stroke Is a 911 Call", "attendee_count": 9, **extra}
        return post(self.client, "/api/signin-sheets/", body)

    def test_bodies_that_are_not_what_the_app_sends_get_a_400(self):
        for body in ("[]", "[1]", "null", '"sheet"', "12"):
            self.assertEqual(post(self.client, "/api/signin-sheets/", body).status_code, 400, body)
        for extra in ({"pdf_base64": 123}, {"pdf_base64": None}, {"pdf_base64": ["x"]}, {"attendee_count": "twelve"}, {"attendee_count": [1]},
                      {"attendee_count": {"n": 1}}, {"attendee_count": 3000000000}, {"supervisor_email": LONG_EMAIL}):
            self.assertEqual(self.send(**extra).status_code, 400, extra)
        huge = json.dumps({"pdf_base64": PDF, "supervisor_email": "lead@plant.com", "held_on": "2027-06-07"})[:-1] + ', "attendee_count": 1e999}'
        self.assertEqual(post(self.client, "/api/signin-sheets/", huge).status_code, 400)
        self.assertFalse(SigninSheet.objects.exists())

    def test_what_the_app_sends_is_still_saved(self):
        self.assertEqual(self.send(attendee_count="12", issue=7).status_code, 201)
        self.assertEqual(self.send(pdf_base64=base64.b64encode(b"%PDF-1.7 two").decode(), attendee_count=-3).status_code, 201)
        self.assertEqual(self.send(pdf_base64=base64.b64encode(b"%PDF-1.7 three").decode(), attendee_count=None).status_code, 201)
        self.assertEqual(sorted(SigninSheet.objects.values_list("attendee_count", "issue"), key=str), [(0, None), (0, None), (12, 7)])

    def test_an_issue_number_the_column_cannot_hold_is_left_blank(self):
        for i, issue in enumerate((-5, 3000000000, "7", 1.5)):
            res = self.send(issue=issue, pdf_base64=base64.b64encode(b"%PDF-1.7 " + bytes([65 + i])).decode())
            self.assertEqual(res.status_code, 201, issue)
        self.assertEqual(set(SigninSheet.objects.values_list("issue", flat=True)), {None})

    def test_nul_characters_and_nulls_are_dropped_from_text(self):
        self.assertEqual(self.send(talk_title="Heat\u0000 talk", supervisor_name="Ana\u0000 Ruiz", company=None, location="Dock\u00003").status_code, 201)
        sheet = SigninSheet.objects.get()
        self.assertEqual((sheet.talk_title, sheet.supervisor_name, sheet.company, sheet.location), ("Heat talk", "Ana Ruiz", "", "Dock3"))

    def test_a_sheet_sent_again_is_not_stored_or_forwarded_twice(self):
        first = self.send()
        again = self.send()  # the phone timed out waiting and sent the same sheet from its outbox
        self.assertEqual((first.status_code, again.status_code), (201, 200))
        self.assertEqual(again.json()["id"], first.json()["id"])
        self.assertEqual(SigninSheet.objects.count(), 1)
        self.assertEqual(self.sync.call_count, 1)
        # A different sheet for the same talk and supervisor (a second crew) is a new sheet.
        other = self.send(pdf_base64=base64.b64encode(b"%PDF-1.7 second crew").decode())
        self.assertEqual(other.status_code, 201)
        self.assertEqual(SigninSheet.objects.count(), 2)

    def test_a_resend_is_recognised_from_the_database_after_a_restart(self):
        """The memory of what was taken is gone after a restart; a sheet still waiting for GoHighLevel has its PDF."""
        first = self.send()
        other_crew = self.send(pdf_base64=base64.b64encode(b"%PDF-1.7 second crew").decode())
        cache.clear()
        again = self.send()
        self.assertEqual((again.status_code, again.json()["id"]), (200, first.json()["id"]))
        self.assertEqual((other_crew.status_code, SigninSheet.objects.count()), (201, 2))
        self.assertEqual(self.sync.call_count, 2)

    def test_a_resend_of_a_sheet_already_forwarded_is_recognised_after_a_restart(self):
        """The case that was left: GoHighLevel has the PDF, the copy here is emptied, and the server has restarted.
        The fingerprint on the row is what is left to know the sheet by; it used to be stored and forwarded twice."""
        first = self.send()
        sheet = SigninSheet.objects.get()
        self.assertEqual(sheet.pdf_sha256, hashlib.sha256(b"%PDF-1.7 test").hexdigest())
        self.assertEqual(sheet.attempts, 0)
        SigninSheet.objects.update(status="synced", pdf=b"")  # forwarded
        cache.clear()
        caches["limits"].clear()                              # restarted
        again = self.send()
        self.assertEqual((again.status_code, again.json()), (200, {"ok": True, "id": first.json()["id"], "saved_to_ghl": True}))
        self.assertEqual(SigninSheet.objects.count(), 1)
        self.assertEqual(self.sync.call_count, 1)
        # The same PDF filed under other details is another sheet (a corrected supervisor email, say), and so is
        # another PDF with the same details.
        self.assertEqual(self.send(supervisor_email="other.lead@plant.com").status_code, 201)
        self.assertEqual(self.send(pdf_base64=base64.b64encode(b"%PDF-1.7 second crew").decode()).status_code, 201)
        self.assertEqual(SigninSheet.objects.count(), 3)

    def test_sheets_waiting_before_the_fingerprint_existed_get_one_from_the_migration(self):
        migration = importlib.import_module("talks.migrations.0019_signup_owner_sheet_fingerprint_longer_links")
        details = dict(supervisor_name="Ana Ruiz", supervisor_email="lead@plant.com", held_on=dt.date(2027, 6, 7), talk_title="Heat Stroke Is a 911 Call",
                       attendee_count=9)
        waiting = SigninSheet.objects.create(pdf=base64.b64decode(PDF), **details)                  # taken before this change
        forwarded = SigninSheet.objects.create(pdf=b"", status="synced", **{**details, "talk_title": "Older"})  # nothing left to fingerprint
        self.assertEqual(migration.fingerprint_waiting_sheets(SigninSheet), 1)
        self.assertEqual(migration.fingerprint_waiting_sheets(SigninSheet), 0)  # safe to run again
        waiting.refresh_from_db()
        forwarded.refresh_from_db()
        self.assertEqual((waiting.pdf_sha256, forwarded.pdf_sha256), (hashlib.sha256(base64.b64decode(PDF)).hexdigest(), ""))
        again = self.send()  # the phone sends that waiting sheet again after the deploy
        self.assertEqual((again.status_code, again.json()["id"]), (200, waiting.pk))

    def test_a_list_or_an_object_where_text_belongs_is_not_a_crash(self):
        for i, junk in enumerate(([], ["monday-minute"], {}, {"a": 1}, 7, True, None)):
            res = self.send(program=junk, pdf_base64=base64.b64encode(b"%PDF-1.7 program " + bytes([65 + i])).decode())
            self.assertEqual(res.status_code, 201, junk)  # "program": [] was a 500: a list cannot be looked up
        self.assertEqual(set(SigninSheet.objects.values_list("program", flat=True)), {"zero-harm-weekly"})
        SigninSheet.objects.all().delete()
        res = self.send(talk_title=["a", "b"], supervisor_name={"n": 1}, company=[], location={}, held_on=[], has_group_photo=[], issue=[7])
        self.assertEqual(res.status_code, 201)
        sheet = SigninSheet.objects.get()
        self.assertEqual((sheet.talk_title, sheet.supervisor_name, sheet.company, sheet.location, sheet.issue, sheet.has_group_photo),
                         ("", "Supervisor", "", "", None, False))
        for extra in ({"supervisor_email": ["lead@plant.com"]}, {"supervisor_email": {}}, {"pdf_base64": {}}, {"pdf_base64": True}):
            self.assertEqual(self.send(**extra).status_code, 400, extra)

    def test_half_a_surrogate_pair_is_dropped_from_text(self):
        """Valid JSON such as "\\ud800" becomes text that cannot be written as UTF-8: saving it was a 500."""
        body = json.dumps({"pdf_base64": PDF, "supervisor_email": "lead@plant.com", "held_on": "2027-06-07"})[:-1]
        body += ', "talk_title": "Heat \\ud800talk", "supervisor_name": "\\udfffAna", "company": "\\ud800", "location": "Dock \\ud83d"}'
        res = post(self.client, "/api/signin-sheets/", body)
        self.assertEqual(res.status_code, 201)
        sheet = SigninSheet.objects.get()
        self.assertEqual((sheet.talk_title, sheet.supervisor_name, sheet.company, sheet.location), ("Heat talk", "Ana", "", "Dock "))
        for field in ("supervisor_email", "pdf_base64", "held_on"):
            bad = json.dumps({"pdf_base64": PDF, "supervisor_email": "lead@plant.com", "held_on": "2027-06-07", field: "@@"}).replace("@@", "\\ud800")
            self.assertIn(post(self.client, "/api/signin-sheets/", bad).status_code, (201, 400), field)
        emoji = self.send(talk_title="Heat \U0001f525 talk", pdf_base64=base64.b64encode(b"%PDF-1.7 emoji").decode())  # a whole pair is kept
        self.assertEqual(SigninSheet.objects.get(pk=emoji.json()["id"]).talk_title, "Heat \U0001f525 talk")

    def test_a_resend_says_whether_the_first_copy_reached_gohighlevel(self):
        self.send()
        self.assertFalse(self.send().json()["saved_to_ghl"])
        SigninSheet.objects.update(status="synced")
        self.assertTrue(self.send().json()["saved_to_ghl"])

    def test_a_resend_after_the_stored_copy_was_cleared_is_still_recognised(self):
        """Once GoHighLevel has the PDF the copy here is emptied, so the match cannot rely on the stored bytes."""
        first = self.send()
        SigninSheet.objects.update(status="synced", pdf=b"")
        again = self.send()
        self.assertEqual((again.status_code, again.json()["id"]), (200, first.json()["id"]))
        self.assertEqual(SigninSheet.objects.count(), 1)


class SuggestionInputTests(TestCase):
    def setUp(self):
        cache.clear()
        patcher = mock.patch("talks.views.sync_suggestion_to_ghl")
        self.sync = patcher.start()
        self.addCleanup(patcher.stop)

    def test_the_same_idea_sent_again_within_ten_minutes_is_not_stored_twice(self):
        """The app gives up after 10 seconds and sends it again; each copy became a row and a note in GoHighLevel."""
        idea = {"topic": "Forklift batteries", "details": "Charging area has no eyewash", "name": "Bo", "email": "bo@dock.com", "may_contact": True}
        first = post(self.client, "/api/suggestions/", idea)
        again = post(self.client, "/api/suggestions/", idea)
        self.assertEqual((first.status_code, again.status_code), (201, 200))
        self.assertEqual(again.json(), {"ok": True, "id": first.json()["id"]})
        self.assertEqual((TalkSuggestion.objects.count(), self.sync.call_count), (1, 1))
        # Anything different is another idea, also from the same person.
        for change in ({"topic": "Forklift batteries again"}, {"details": "And no spill kit"}, {"email": "bo.other@dock.com"}, {"may_contact": False}):
            self.assertEqual(post(self.client, "/api/suggestions/", {**idea, **change}).status_code, 201, change)
        self.assertEqual(TalkSuggestion.objects.count(), 5)
        # And after the ten minutes the same words are a new idea again.
        TalkSuggestion.objects.filter(pk=first.json()["id"]).update(created_at=timezone.now() - dt.timedelta(minutes=views.SUGGESTION_RESEND_MINUTES + 1))
        later = post(self.client, "/api/suggestions/", idea)
        self.assertEqual(later.status_code, 201)
        self.assertNotEqual(later.json()["id"], first.json()["id"])

    def test_a_list_or_an_object_where_text_belongs_is_not_stored_as_its_python_spelling(self):
        for junk in ([], ["Forklift batteries"], {}, {"t": "Forklift batteries"}, True):
            self.assertEqual(post(self.client, "/api/suggestions/", {"topic": junk}).status_code, 400, junk)
        res = post(self.client, "/api/suggestions/", {"topic": "Forklift batteries", "details": ["a"], "name": {"n": 1}, "company": [], "month_theme": {},
                                                      "email": [], "may_contact": {"yes": 1}})
        self.assertEqual(res.status_code, 201)
        s = TalkSuggestion.objects.get()
        self.assertEqual((s.details, s.name, s.company, s.month_theme, s.email, s.may_contact), ("", "", "", "", "", False))

    def test_half_a_surrogate_pair_is_dropped_from_text(self):
        res = post(self.client, "/api/suggestions/", '{"topic": "Fork\\ud800lifts", "details": "\\udfff", "name": "Bo\\ud83d", "company": "\\ud800Dock", '
                                                     '"month_theme": "\\ud800"}')
        self.assertEqual(res.status_code, 201)
        s = TalkSuggestion.objects.get()
        self.assertEqual((s.topic, s.details, s.name, s.company, s.month_theme), ("Forklifts", "", "Bo", "Dock", ""))
        self.assertEqual(post(self.client, "/api/suggestions/", '{"topic": "\\ud800\\ud800\\ud800\\ud800"}').status_code, 400)  # nothing is left of it
        self.assertEqual(post(self.client, "/api/suggestions/", '{"topic": "Dock plates", "email": "bo\\ud800@dock.com"}').status_code, 201)

    def test_bodies_that_are_not_an_object_get_a_400(self):
        for body in ("[]", "[1]", "null", '"topic"', "7"):
            self.assertEqual(post(self.client, "/api/suggestions/", body).status_code, 400, body)
        self.assertEqual(post(self.client, "/api/suggestions/", {"topic": None}).status_code, 400)  # was stored as the word None
        self.assertEqual(post(self.client, "/api/suggestions/", {"topic": "Forklift batteries", "email": LONG_EMAIL}).status_code, 400)
        self.assertFalse(TalkSuggestion.objects.exists())

    def test_nul_characters_and_nulls_are_dropped_from_text(self):
        res = post(self.client, "/api/suggestions/", {"topic": "Fork\u0000lifts", "details": None, "name": "Bo\u0000", "company": "Dock\u0000 Co", "month_theme": None})
        self.assertEqual(res.status_code, 201)
        s = TalkSuggestion.objects.get()
        self.assertEqual((s.topic, s.details, s.name, s.company, s.month_theme), ("Forklifts", "", "Bo", "Dock Co", ""))


# ---- Sign-ups ---------------------------------------------------------------------------------------------------

@override_settings(**GHL_ON)
class SignupFixTests(GhlTestCase):
    def setUp(self):
        super().setUp()
        # The owner's notice is sent by owner_alerts.notify (another group's). It is stood in for here, as agreed.
        self.stand_in = mock.patch.object(owner_alerts, "notify", create=True, return_value=True)
        self.notify = self.stand_in.start()
        self.addCleanup(self.stand_in.stop)

    def test_text_with_nul_characters_and_an_email_too_long_for_the_column(self):
        self.assertEqual(self.signup(email=LONG_EMAIL, name="Jane Doe").status_code, 400)
        self.assertEqual(self.signup(name="Ja\u0000ne D\u0000oe", company="Ac\u0000me", consent="I \u0000agree", install_id=INSTALL).status_code, 200)
        row = AppSignup.objects.get()
        self.assertEqual((row.first_name, row.last_name, row.company, row.consent_text), ("Jane", "Doe", "Acme", "I agree"))

    def test_another_phone_changes_nothing_however_often_it_asks_and_is_told_so(self):
        self.signup(name="Vera Victim", install_id=INSTALL, consent=CONSENT)  # no company given: a blank a stranger could have filled
        before = AppSignup.objects.values().get()
        self.ghl.calls.clear()
        for _ in range(3):
            res = self.signup(name="Mallory Attacker", company="EvilCo", wants_offers=True, consent="forged consent", install_id=OTHER)
            self.assertEqual((res.status_code, res.json()), (200, {"ok": True, "changed": False}))
        self.assertEqual(AppSignup.objects.values().get(), before)  # every column, the blank company included
        self.assertEqual(self.ghl.calls, [])  # and GoHighLevel hears nothing of it
        self.assertEqual(AppSignup.objects.get().phones.count(), 2)  # the phone is linked, so the app works on it

    def test_the_phone_that_signed_up_can_still_change_its_own_sign_up(self):
        self.signup(name="Vera Victim", company="HonestCo", install_id=INSTALL, consent=CONSENT)
        self.signup(name="Mallory", install_id=OTHER)  # another phone is linked in between
        res = self.signup(name="Vera Valdez", company="NewCo", wants_offers=True, install_id=INSTALL)
        self.assertEqual(res.json(), {"ok": True})  # no "changed": false for the owner phone
        row = AppSignup.objects.get()
        self.assertEqual((row.last_name, row.company, row.wants_offers), ("Valdez", "NewCo", True))

    def test_another_phone_can_switch_the_offers_choice_neither_on_nor_off(self):
        """It could switch it off for a while. A stranger linked to the email could do that too, with two requests."""
        self.signup(name="Vera Victim", wants_offers=True, install_id=INSTALL)
        for wants in (False, False, True):
            self.assertEqual(self.signup(name="Vera Victim", wants_offers=wants, install_id=OTHER).json(), {"ok": True, "changed": False})
            self.assertTrue(AppSignup.objects.get().wants_offers)
        self.signup(name="Vera Victim", wants_offers=False, install_id=INSTALL)
        self.assertFalse(AppSignup.objects.get().wants_offers)
        self.signup(name="Vera Victim", wants_offers=True, install_id=OTHER)
        self.assertFalse(AppSignup.objects.get().wants_offers)

    def test_a_request_with_no_phone_id_changes_nothing_and_learns_nothing(self):
        """An old app version, or a script. Its answer is the same for a new email and a known one."""
        self.signup(name="Vera Victim", install_id=INSTALL)
        before = AppSignup.objects.values().get()
        known = self.signup(name="Someone", company="Other Co", wants_offers=True)
        new = self.signup(email="new@plant.com", name="Someone")
        self.assertEqual((known.status_code, known.content), (new.status_code, new.content))
        self.assertEqual(AppSignup.objects.values().get(email="jane@plant.com"), before)
        # A sign-up that never had a phone has no owner: nobody can claim it, and nobody can change it from the app.
        res = self.signup(email="new@plant.com", name="Mallory", company="EvilCo", install_id=OTHER)
        self.assertEqual(res.json(), {"ok": True, "changed": False})
        row = AppSignup.objects.get(email="new@plant.com")
        self.assertEqual((row.first_name, row.company, row.phones.count()), ("Someone", "", 0))

    def test_a_repeat_writes_only_the_columns_it_changes(self):
        """Two requests for one email can overlap. The repeat saved its whole copy of the row, loaded earlier, and so
        put the old ghl_contact_id and ghl_had_tags back over what the other request had just stored."""
        self.signup(name="Vera Victim", install_id=INSTALL)
        with mock.patch("talks.views.sync_signup_to_ghl", return_value=False), CaptureQueriesContext(connection) as queries:
            self.signup(name="Vera Valdez", company="NewCo", install_id=INSTALL)
        updates = [q["sql"] for q in queries if q["sql"].startswith("UPDATE") and "talks_appsignup" in q["sql"]]
        self.assertEqual(len(updates), 1, updates)
        for column in ("last_name", "company", "ghl_synced_at"):
            self.assertIn(f'"{column}" =', updates[0])
        for column in ("ghl_contact_id", "ghl_had_tags", "owner_alerted_at", "email", "source", "wants_offers"):
            self.assertNotIn(f'"{column}" =', updates[0])
        row = AppSignup.objects.get()
        self.assertEqual((row.last_name, row.company, row.ghl_contact_id), ("Valdez", "NewCo", "lead1"))

    def test_a_repeat_from_the_owner_phone_at_the_moment_of_its_removal_does_not_put_the_row_back(self):
        """A plain save() of the copy loaded a moment earlier inserted the removed sign-up again."""
        self.signup(name="Vera Victim", install_id=INSTALL)

        class RemovedMeanwhile(dict):
            def __contains__(self, key):  # the view asks '"wants_offers" in data' after it has loaded the row
                AppSignup.objects.all().delete()
                return super().__contains__(key)

        with mock.patch("talks.views._json_body", return_value=RemovedMeanwhile(email="jane@plant.com", name="Vera Valdez", install_id=INSTALL)):
            res = self.signup()
        self.assertEqual((res.status_code, res.json()), (200, {"ok": True}))
        self.assertFalse(AppSignup.objects.exists())

    # ---- "Remove my info" ----------------------------------------------------------------------------------------

    def test_the_owner_phone_removes_the_sign_up_as_before(self):
        self.signup(name="Maria Lopez", install_id=INSTALL)
        self.signup(name="Somebody Else", install_id=OTHER)  # a stranger linked to the email cannot keep her on the list
        self.ghl.calls.clear()
        res = self.remove(INSTALL)
        self.assertEqual((res.status_code, res.json()), (200, {"ok": True}))
        self.assertFalse(AppSignup.objects.exists())
        self.assertFalse(SignupPhone.objects.exists())
        self.assertFalse(SignupRemoval.objects.exists())  # finished: tags off, owner told
        self.assertEqual(len(self.ghl.to("/contacts/lead1/tags", "DELETE")), 1)
        self.assertEqual([m["subject"] for m in self.ghl.emails], ["Zero Harm removal request: jane@plant.com"])
        self.notify.assert_not_called()

    def test_a_removal_from_another_phone_deletes_nothing_and_goes_to_the_owner_to_decide(self):
        """Her new phone, a reinstall, or a stranger who typed her email: the server cannot tell which."""
        self.signup(name="Maria Lopez", company="Dock Co", wants_offers=True, install_id=INSTALL)
        self.signup(name="Maria Lopez", install_id=OTHER)
        before = AppSignup.objects.values().get()
        self.ghl.calls.clear()
        res = self.remove(OTHER)
        self.assertEqual((res.status_code, res.json()), (200, {"ok": True, "pending": True}))
        row = AppSignup.objects.get()
        self.assertIsNotNone(row.removal_requested_at)
        self.assertEqual({**AppSignup.objects.values().get(), "removal_requested_at": None}, before)  # nothing else moved
        self.assertEqual(row.phones.count(), 1)  # the asking phone is unlinked, the owner phone is not
        self.assertEqual(self.ghl.calls, [])  # no tag came off, no "removed" note
        self.assertFalse(SignupRemoval.objects.exists())
        subject, lines = self.notify.call_args.args
        self.assertEqual(self.notify.call_count, 1)
        self.assertIn("jane@plant.com", subject)
        self.assertIn("Maria Lopez", " ".join(lines))
        self.assertEqual(self.notify.call_args.kwargs, {"key": f"signup-removal-request:{row.pk}"})

        # Asking again (after linking again) neither moves the date nor deletes anything; the key keeps it to one email.
        first_asked = row.removal_requested_at
        self.signup(name="Maria Lopez", install_id=OTHER)
        self.assertEqual(self.remove(OTHER).json(), {"ok": True, "pending": True})
        self.assertEqual(AppSignup.objects.get().removal_requested_at, first_asked)
        self.assertEqual({c.kwargs["key"] for c in self.notify.call_args_list}, {f"signup-removal-request:{row.pk}"})
        # A phone with nothing linked gets the plain answer, as before.
        self.assertEqual(self.remove(OTHER).json(), {"ok": True})

    def test_the_three_request_takeover_leaves_the_victims_sign_up_unchanged(self):
        """What the second check showed: a stranger links a phone to the email, removes the sign-up, signs the email up
        again as their own. It ended with 'Mallory Attacker | EvilCo | offers on | forged consent' in the database and
        in GoHighLevel."""
        self.signup(name="Vera Victim", company="HonestCo", install_id=INSTALL, consent=CONSENT)
        before = AppSignup.objects.values().get()
        self.ghl.calls.clear()
        stranger = dict(name="Mallory Attacker", company="EvilCo", wants_offers=True, consent="forged consent", install_id=OTHER)

        self.assertEqual(self.signup(**stranger).json(), {"ok": True, "changed": False})   # 1. link
        self.assertEqual(self.remove(OTHER).json(), {"ok": True, "pending": True})         # 2. remove
        self.assertEqual(self.signup(**stranger).json(), {"ok": True, "changed": False})   # 3. sign up again

        after = AppSignup.objects.values().get()
        self.assertIsNotNone(after.pop("removal_requested_at"))  # the one trace: a request for the owner to look at
        before.pop("removal_requested_at")
        self.assertEqual(after, before)  # same row, same name, company, offers choice, consent and consent time
        self.assertEqual(self.ghl.calls, [])  # GoHighLevel was sent no rename, no offers tag, no removal
        self.assertEqual(self.notify.call_count, 1)
        # The victim's own phone still owns the sign-up: it can correct it and remove it.
        self.signup(name="Vera Valdez", install_id=INSTALL)
        self.assertEqual(AppSignup.objects.get().last_name, "Valdez")
        self.assertEqual(self.remove(INSTALL).json(), {"ok": True})
        self.assertFalse(AppSignup.objects.exists())

    def test_a_shared_phone_removes_only_the_sign_ups_it_made(self):
        """One tablet linked to several sign-ups used to delete all of them, the ones other phones made too."""
        self.signup(email="mine@plant.com", name="Tablet Owner", install_id=OTHER)
        self.signup(email="hers@plant.com", name="Maria Lopez", install_id=INSTALL)
        self.signup(email="hers@plant.com", name="Maria Lopez", install_id=OTHER)
        self.assertEqual(self.remove(OTHER).json(), {"ok": True, "pending": True})
        self.assertEqual(list(AppSignup.objects.values_list("email", flat=True)), ["hers@plant.com"])
        self.assertIsNotNone(AppSignup.objects.get().removal_requested_at)
        self.assertEqual(self.notify.call_count, 1)

    def test_the_request_stands_when_the_owner_cannot_be_told(self):
        self.signup(name="Maria Lopez", install_id=INSTALL)
        self.signup(name="Maria Lopez", install_id=OTHER)
        self.notify.side_effect = RuntimeError("no such thing should happen, but")
        with self.assertLogs("talks.views", level="ERROR"):
            res = self.remove(OTHER)
        self.assertEqual((res.status_code, res.json()), (200, {"ok": True, "pending": True}))
        self.assertIsNotNone(AppSignup.objects.get().removal_requested_at)
        # The cron can ask again: only requests of the last week, and the key keeps a sent one from going twice.
        self.notify.side_effect = None
        self.notify.reset_mock()
        AppSignup.objects.create(email="old@plant.com", removal_requested_at=timezone.now() - dt.timedelta(days=30))
        AppSignup.objects.create(email="none@plant.com")
        self.assertEqual(views.retry_removal_request_notices(), 1)
        self.assertEqual(self.notify.call_args.kwargs["key"], f"signup-removal-request:{AppSignup.objects.get(email='jane@plant.com').pk}")

    def test_the_notice_is_one_the_real_sender_accepts(self):
        """owner_alerts.notify itself, not the stand-in: the subject, lines and key go through it to GoHighLevel once."""
        if not hasattr(owner_alerts, "notify"):
            self.skipTest("owner_alerts.notify is not there yet")
        self.stand_in.stop()
        self.signup(name="Maria Lopez", install_id=INSTALL)
        self.signup(name="Maria Lopez", install_id=OTHER)
        self.ghl.calls.clear()
        self.remove(OTHER)
        self.signup(name="Maria Lopez", install_id=OTHER)
        self.remove(OTHER)
        self.assertEqual([m["subject"] for m in self.ghl.emails], ["Zero Harm removal request to check: jane@plant.com"])
        self.assertIn("Nothing was deleted", self.ghl.emails[0]["html"])

    def test_a_phone_that_was_never_linked_removes_nothing(self):
        self.signup(name="Maria Lopez", install_id=INSTALL)
        self.signup(email="old@plant.com", name="Old App")  # no phone id: nobody can link to it, so nobody can remove it
        self.signup(email="old@plant.com", name="Mallory", install_id=OTHER)
        self.ghl.calls.clear()
        self.assertEqual(self.remove(OTHER).json(), {"ok": True})
        self.assertEqual(self.remove("some-phone-nobody-knows").json(), {"ok": True})
        self.assertEqual(AppSignup.objects.count(), 2)
        self.assertEqual(AppSignup.objects.exclude(removal_requested_at=None).count(), 0)
        self.assertEqual(self.ghl.calls, [])
        self.notify.assert_not_called()

    def test_once_the_new_sign_up_limit_is_reached_known_and_unknown_emails_get_the_same_answer(self):
        with mock.patch("talks.views.sync_signup_to_ghl", return_value=False):
            for i in range(views.NEW_SIGNUPS_PER_HOUR):
                self.assertEqual(self.signup(email=f"crew{i}@plant.com").status_code, 200)
            answers = {email: self.signup(email=email).status_code
                       for email in ("crew0@plant.com", "CREW1@plant.com", "nobody-here@plant.com", "also-not-here@plant.com")}
        self.assertEqual(set(answers.values()), {429}, answers)
        self.assertEqual(AppSignup.objects.count(), views.NEW_SIGNUPS_PER_HOUR)

    def test_before_the_limit_is_reached_repeats_are_free(self):
        with mock.patch("talks.views.sync_signup_to_ghl", return_value=False):
            for i in range(views.NEW_SIGNUPS_PER_HOUR - 1):
                self.assertEqual(self.signup(email=f"crew{i}@plant.com").status_code, 200)
            for _ in range(10):
                self.assertEqual(self.signup(email="crew0@plant.com").status_code, 200)
            self.assertEqual(self.signup(email="the-last-one@plant.com").status_code, 200)
        self.assertEqual(AppSignup.objects.count(), views.NEW_SIGNUPS_PER_HOUR)


# ---- Round two: text that is valid JSON and still not text ----------------------------------------------------------

@override_settings(**GHL_ON)
class SignupOddInputTests(GhlTestCase):
    def test_a_list_or_an_object_where_text_belongs(self):
        for junk in ([], ["jane@plant.com"], {}, {"e": "jane@plant.com"}, True, 7):
            self.assertEqual(self.signup(email=junk).status_code, 400, junk)
        res = self.signup(name=["Jane", "Doe"], first_name={"n": "Jane"}, company=["Acme"], consent={"text": "yes"}, source=["welcome"],
                          install_id=["3f6c1c1e-8a55-4a0e-9d7b-1c2d3e4f5a6b"], wants_offers=[])
        self.assertEqual(res.status_code, 200)
        row = AppSignup.objects.get()
        self.assertEqual((row.first_name, row.last_name, row.company, row.consent_text, row.source, row.wants_offers, row.phones.count()),
                         ("", "", "", "", "settings", False, 0))
        self.assertEqual(post(self.client, "/api/signups/remove/", {"install_id": ["x" * 20]}).json(), {"ok": True})
        self.assertEqual(post(self.client, "/api/signups/remove/", {"install_id": {"id": "x" * 20}}).json(), {"ok": True})

    def test_half_a_surrogate_pair_in_a_name_or_a_phone_id(self):
        """"\\ud800" is valid JSON. The name could not be saved and the phone id could not be hashed: both a 500."""
        res = post(self.client, "/api/signups/", '{"email": "jane@plant.com", "name": "Ja\\ud800ne D\\udfffoe", "company": "\\ud800Acme", '
                                                 '"consent": "I agree\\ud83d", "install_id": "zh-phone-\\ud800-0001"}')
        self.assertEqual(res.status_code, 200)
        row = AppSignup.objects.get()
        self.assertEqual((row.first_name, row.last_name, row.company, row.consent_text), ("Jane", "Doe", "Acme", "I agree"))
        self.assertEqual(row.phones.count(), 0)  # such an id is no phone's id: treated like none
        self.assertEqual(post(self.client, "/api/signups/", '{"email": "bo\\ud800@dock.com"}').status_code, 200)  # the address without it
        self.assertEqual(post(self.client, "/api/signups/", '{"email": "\\ud800"}').status_code, 400)
        res = post(self.client, "/api/signups/remove/", '{"install_id": "zh-phone-\\ud800-0001"}')
        self.assertEqual((res.status_code, res.json()), (200, {"ok": True}))
        self.assertEqual(sorted(AppSignup.objects.values_list("email", flat=True)), ["bo@dock.com", "jane@plant.com"])


class OtisOddInputTests(TestCase):
    """The OTIS endpoints (talks/api_v2.py), which round one could not touch."""

    def setUp(self):
        cache.clear()

    def manifest(self, **extra):
        return post(self.client, "/api/v2/otis/manifest", {"platform": "ios", "memory_gb": 8, **extra})

    def feedback(self, body):
        return post(self.client, "/api/v2/otis/feedback", body)

    def test_an_app_version_with_a_digit_that_is_not_0_to_9(self):
        """'²'.isdigit() is true and int('²') is an error: with a minimum version set, "1.²" was a 500."""
        OtisRollout.objects.create(min_app_version="1.2.0")
        for version, too_old in (("1.²", True), ("1.³.9", True), ("²", True), ("1.٣", True), ("1.2.0", False), ("2.0", False), ("1.10", False), ("v1.2.1-beta", False)):
            res = self.manifest(app_version=version)
            self.assertEqual(res.status_code, 200, version)
            self.assertEqual(res.json()["update_required"], too_old, version)

    def test_a_nul_character_in_a_rating_is_dropped_not_a_server_error(self):
        res = self.feedback({"helpful": True, "question": "Why lock\u0000out?\nReally", "source_ids": ["k1\u0000", "\u0000"], "model_key": "qwen\u0000-1",
                             "app_version": "1.2\u0000", "platform": "ios"})
        self.assertEqual(res.status_code, 201)
        row = OtisFeedback.objects.get()
        self.assertEqual((row.question, row.source_ids, row.model_key, row.app_version), ("Why lockout?\nReally", ["k1", ""], "qwen-1", "1.2"))

    def test_half_a_surrogate_pair_in_a_rating(self):
        res = self.feedback('{"helpful": false, "question": "Why\\ud800 not", "source_ids": ["k\\udfff2"], "model_key": "m\\ud83d", "app_version": "\\ud800"}')
        self.assertEqual(res.status_code, 201)
        row = OtisFeedback.objects.get()
        self.assertEqual((row.question, row.source_ids, row.model_key, row.app_version), ("Why not", ["k2"], "m", ""))

    def test_wrong_types_in_a_rating_are_refused_not_a_crash(self):
        for body in ({"helpful": True, "question": ["a"]}, {"helpful": True, "source_ids": "k1"}, {"helpful": True, "model_key": {}},
                     {"helpful": True, "source_ids": [["k1"]]}, {"helpful": True, "app_version": 12}, [], '"x"'):
            self.assertEqual(self.feedback(body).status_code, 422, body)
        self.assertFalse(OtisFeedback.objects.exists())

    def test_the_phones_own_text_never_goes_into_the_release_lookup(self):
        """backends is the one piece of the phone's text that reached a query: a NUL in it was a 500 on PostgreSQL."""
        OtisModelRelease.objects.create(key="pinned-mlx", label="OTIS standard", platform="ios", backend="mlx", model_url="https://x.example/m.pte",
                                        tokenizer_url="https://x.example/t.json", tokenizer_config_url="https://x.example/c.json", size_mb=900, active=True)
        with CaptureQueriesContext(connection) as queries:
            res = self.manifest(backends=["mlx\u0000", "\u0000", "no-such-backend"], app_version="1\u0000.0", os_version="\u0000", kb_version="\u0000")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["model"]["key"], "pinned-mlx")  # "mlx" with the NUL dropped is still mlx
        self.assertFalse(any("no-such-backend" in q["sql"] for q in queries))
        res = post(self.client, "/api/v2/otis/manifest", '{"platform": "ios", "memory_gb": 8, "backends": ["\\ud800", "MLX"], "kb_version": "\\ud800", "os_version": "\\ud800"}')
        self.assertEqual((res.status_code, res.json()["model"]["key"]), (200, "pinned-mlx"))
        self.assertEqual(self.manifest(backends=["no-such-backend"]).json()["model"]["builtin"], "QWEN3_1_7B")  # as before: no pinned release, the built-in one
        self.assertEqual(self.manifest().json()["model"]["builtin"], "QWEN3_1_7B")  # no backends named: XNNPACK, for which nothing is pinned


class UsageOddInputTests(TestCase):
    def test_half_a_surrogate_pair_in_the_daily_count(self):
        for body in ('{"install_id": "zh-usage-\\ud800-01", "platform": "ios"}',
                     '{"install_id": "zh-usage-000001", "platform": "ios", "app_version": "1\\ud800"}',
                     '{"install_id": "zh-usage-000002", "platform": "ios", "place": {"city": "Hous\\ud800ton", "region": "\\ud800", "country": "US"}}',
                     '{"install_id": ["zh-usage-000003"], "platform": "ios"}'):
            with mock.patch("usage.geo.lookup", return_value={"country": "", "region": "", "city": ""}):
                self.assertIn(post(self.client, "/api/v2/app/open", body).status_code, (200, 422), body)

    def test_an_address_that_is_not_known_gives_a_blank_place(self):
        """zeroharm.net.client_ip answers "" when it cannot tell the caller; the place lookup must take that."""
        from usage import geo

        self.assertEqual(geo.lookup(""), {"country": "", "region": "", "city": ""})
        self.assertEqual(geo.lookup(None), {"country": "", "region": "", "city": ""})


# ---- Round two: the counters' own cache, and the longer address columns ---------------------------------------------

@override_settings(GHL_PRIVATE_TOKEN="", GHL_LOCATION_ID="")
class CountersCacheTests(TestCase):
    def test_the_invite_limit_survives_a_full_content_cache(self):
        cache.clear()
        get = lambda i: self.client.get("/get/", {"c": f"contact{i:06d}"}, REMOTE_ADDR="203.0.113.7")
        for i in range(invite_views.NEW_CLICKS_PER_HOUR):
            get(i)
        for i in range(400):  # more than the 300 entries the content cache holds
            cache.set(f"wx:{i}", {"temp_f": 70}, 600)
        get(9000)
        self.assertEqual(InviteClick.objects.count(), invite_views.NEW_CLICKS_PER_HOUR)
        self.assertTrue(any("invite-rate:" in str(k) for k in caches["limits"]._cache))
        self.assertFalse(any("invite-rate:" in str(k) for k in cache._cache))

    def test_every_counter_in_these_views_is_in_the_limits_cache(self):
        cache.clear()
        with mock.patch("talks.views.sync_suggestion_to_ghl"), mock.patch("talks.views.sync_sheet_to_ghl", return_value=False), \
             mock.patch("talks.weather._get", side_effect=TimeoutError("down")):
            post(self.client, "/api/signups/", {"email": "jane@plant.com"})
            post(self.client, "/api/signups/remove/", {"install_id": "zh-test-phone-000001"})
            post(self.client, "/api/suggestions/", {"topic": "Dock plates"})
            post(self.client, "/api/signin-sheets/", {"pdf_base64": PDF, "supervisor_email": "lead@plant.com", "held_on": "2027-06-07"})
            self.client.get("/api/weather/?lat=30&lon=-100")
        names = {str(k).split(":")[-2] for k in caches["limits"]._cache}
        self.assertEqual(names, {"signup-rate", "signup-new-rate", "signup-remove-rate", "suggest-rate", "sheet-rate", "weather-rate", "weather-failed-rate"})
        self.assertFalse(any("-rate:" in str(k) for k in cache._cache))


class LongerAddressTests(TestCase):
    def test_talk_and_feed_addresses_hold_500_characters_in_the_database_and_the_console(self):
        long = "https://files.example.com/" + "a" * 474
        self.assertEqual(len(long), 500)
        for model, names in ((FeedItem, ("link_url", "image_url")), (views.ToolboxTalk, ("hero_url", "pdf_url"))):
            for name in names:
                self.assertEqual(model._meta.get_field(name).max_length, 500, name)
        for checks, names in ((console.FEED_CHECKS, ("link_url", "image_url")), (console.TALK_CHECKS, ("hero_url", "pdf_url"))):
            for name in names:
                self.assertEqual(checks[name](name, long), long)
                with self.assertRaises(console.Bad):
                    checks[name](name, long + "a")
        item = FeedItem.objects.create(external_id="long-1", kind="tool", title="Long", link_url=long, image_url=long)
        item.full_clean()
        self.assertEqual(FeedItem.objects.get().as_api()["image_url"], long)


@override_settings(INGEST_KEY=KEY, GHL_PRIVATE_TOKEN="", GHL_LOCATION_ID="")
class NoServerErrorSweepTests(TestCase):
    """Every public endpoint in these files, each field in turn replaced by things that are valid JSON and not what
    the field expects. Whatever the answer is (saved, cleaned or 400/422), it is never a server error. The same sweep
    runs on PostgreSQL, which refuses what SQLite lets through (NUL characters, numbers too big for a column)."""

    JUNK = ([], ["a"], [[]], {}, {"a": {"b": []}}, None, True, False, 0, -1, 7, 1.5, 10 ** 30, -(10 ** 30), "", " ", "a\u0000b", "\u0000",
            "\ud800", "x\udfffy", "\U0001f525", "²", "1.²", "a" * 5000, "2027-02-30", "9999-12-31 23:59", "0001-01-01", "nan")
    BODIES = {
        "/api/signups/": {"email": "jane@plant.com", "name": "Jane Doe", "first_name": "Jane", "company": "Acme", "consent": CONSENT, "source": "welcome",
                          "wants_offers": True, "install_id": INSTALL},
        "/api/signups/remove/": {"install_id": INSTALL},
        "/api/signin-sheets/": {"pdf_base64": PDF, "supervisor_email": "lead@plant.com", "supervisor_name": "Ana Ruiz", "held_on": "2027-06-07",
                                "talk_title": "Heat", "attendee_count": 9, "issue": 7, "program": "monday-minute", "company": "Acme", "location": "Dock 3",
                                "has_group_photo": True},
        "/api/suggestions/": {"topic": "Forklift batteries", "details": "No eyewash", "month_theme": "Heat", "name": "Bo", "email": "bo@dock.com",
                              "company": "Dock Co", "may_contact": True},
        "/api/ingest/": {"action": "publish", "kind": "alert", "title": "Rule", "summary": "S", "body": "B", "link": "https://example.com/a",
                         "image": "https://example.com/a.png", "jurisdiction": "Nevada", "effective_date": "2027-01-03", "publish_at": "2027-01-01 08:00",
                         "expires_at": "2028-01-01", "send_push": "yes", "featured": "no", "unpublish": "no", "external_id": "rule-1", "year": 2028},
        "/api/v2/otis/manifest": {"platform": "ios", "memory_gb": 8, "app_version": "1.2.0", "os_version": "18.1", "backends": ["mlx"], "kb_version": "abc"},
        "/api/v2/otis/feedback": {"helpful": True, "source_ids": ["k1"], "question": "Why?", "model_key": "m", "platform": "ios", "app_version": "1.2.0",
                                  "lang": "en"},
        "/api/v2/app/open": {"install_id": INSTALL, "platform": "ios", "app_version": "1.2.0", "place": {"city": "Houston", "region": "TX", "country": "US"}},
    }

    def test_no_field_can_be_made_to_crash_an_endpoint(self):
        OtisRollout.objects.create(min_app_version="1.2.0")
        tried = 0
        with mock.patch("usage.geo.lookup", return_value={"country": "", "region": "", "city": ""}):
            for path, good in self.BODIES.items():
                for field in good:
                    for junk in self.JUNK:
                        caches["limits"].clear()  # so the hourly limits do not answer 429 before the field is read
                        body = json.dumps({**good, field: junk})
                        res = self.client.post(path, body, content_type="application/json", HTTP_X_ZEROHARM_KEY=KEY)
                        self.assertLess(res.status_code, 500, (path, field, junk if len(str(junk)) < 40 else str(junk)[:40]))
                        tried += 1
                # sync_year uses the same body with another action
                if path == "/api/ingest/":
                    for junk in self.JUNK:
                        res = self.client.post(path, json.dumps({"action": "sync_year", "year": junk}), content_type="application/json", HTTP_X_ZEROHARM_KEY=KEY)
                        self.assertLess(res.status_code, 500, ("sync_year", junk))
        self.assertGreater(tried, 1500)

    def test_addresses_and_ids_in_the_url(self):
        for path in ("/api/talks/99999999999999999999/", "/api/feed/99999999999999999999/", "/api/episodes/99999999999999999999/",
                     "/api/feed/?kind=%00", "/api/feed/?kind=%ED%A0%80", "/api/weather/?lat=%00&lon=1", "/api/weather/?lat=1e400&lon=-1e400",
                     "/get/?c=%00%00%00%00%00%00%00%00%00%00", "/get/?c=%ED%A0%80aaaaaaaaaaaa", "/backoffice/?key=%00", "/backoffice/?key=%ED%A0%80"):
            self.assertLess(self.client.get(path).status_code, 500, path)
