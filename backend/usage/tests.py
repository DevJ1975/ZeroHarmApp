import datetime as dt
import gzip
import io
import json
import tempfile
from pathlib import Path
from unittest import mock

from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from monday.api import _hash

from . import geo
from .management.commands import geo_update
from .models import AppOpen, first_opens

INSTALL = "3f6c1c1e-8a55-4a0e-9d7b-1c2d3e4f5a6b"
ADDRESS = "203.0.113.77"
HOUSTON = {"country": "US", "region": "Texas", "city": "Houston"}
NOWHERE = {"country": "", "region": "", "city": ""}


class FakeReader:
    """Stands in for an open city database."""
    def __init__(self, records):
        self.records = records

    def get(self, ip):
        return self.records.get(ip)

    def close(self):
        pass


@override_settings(SECRET_KEY="test", USAGE_ENABLED=True, GEOIP_DB_PATH="/nonexistent/city.mmdb")
class OpenTests(TestCase):
    def setUp(self):
        cache.clear()
        geo.reset()
        self.addCleanup(geo.reset)

    def post(self, body=None, ip=ADDRESS, **extra):
        body = {"install_id": INSTALL, "platform": "ios", "app_version": "1.4.0", **(body or {}), **extra}
        return self.client.post("/api/v2/app/open", json.dumps(body), content_type="application/json", HTTP_X_FORWARDED_FOR=ip)

    def test_one_row_per_phone_per_day_with_only_the_hash(self):
        with mock.patch.object(geo, "lookup", return_value=dict(HOUSTON)) as lookup:
            first = self.post()
            self.post()
            self.post(install_id="another-phone-0001", platform="android")
        self.assertEqual((first.status_code, first.json()), (200, {"ok": True}))
        lookup.assert_any_call(ADDRESS)
        self.assertEqual(AppOpen.objects.count(), 2)
        row = AppOpen.objects.get(install_hash=_hash(INSTALL))
        self.assertEqual((row.day, row.platform, row.app_version), (timezone.localdate(), "ios", "1.4.0"))
        self.assertEqual((row.city, row.region, row.country, row.source), ("Houston", "Texas", "US", "network"))
        self.assertNotIn(INSTALL, json.dumps(list(AppOpen.objects.values()), default=str))

    def test_a_new_day_is_a_new_row(self):
        self.post()
        with mock.patch("usage.api.timezone.localdate", return_value=timezone.localdate() + dt.timedelta(days=1)):
            self.post()
        self.assertEqual(AppOpen.objects.filter(install_hash=_hash(INSTALL)).count(), 2)

    def test_the_network_address_is_never_stored(self):
        with mock.patch.object(geo, "lookup", return_value=dict(HOUSTON)):
            self.post()
            self.post(ip=f"6.6.6.6, {ADDRESS}")
        self.assertFalse(any("address" in f.name or "ip" == f.name or "network" in f.name for f in AppOpen._meta.get_fields()))
        for row in AppOpen.objects.values():
            for value in row.values():
                self.assertNotIn(ADDRESS, str(value))
                self.assertNotIn(_hash(f"net:{ADDRESS}"), str(value))

    def test_only_the_proxys_hop_is_looked_up(self):
        with mock.patch.object(geo, "lookup", return_value=dict(NOWHERE)) as lookup:
            self.post(ip=f"8.8.8.8, {ADDRESS}")
        lookup.assert_called_once_with(ADDRESS)

    def test_no_database_means_a_blank_place(self):
        self.assertEqual(self.post().status_code, 200)
        row = AppOpen.objects.get()
        self.assertEqual((row.city, row.region, row.country, row.source), ("", "", "", ""))

    def test_the_phones_own_place_wins_and_states_are_spelled_out(self):
        with mock.patch.object(geo, "lookup", return_value=dict(HOUSTON)) as lookup:
            self.post(place={"city": "Bakersfield", "region": "ca", "country": "us"})
        lookup.assert_not_called()
        row = AppOpen.objects.get()
        self.assertEqual((row.city, row.region, row.country, row.source), ("Bakersfield", "California", "US", "phone"))

    def test_a_later_open_can_only_improve_the_place(self):
        self.post()  # no database: unknown
        with mock.patch.object(geo, "lookup", return_value=dict(HOUSTON)):
            self.post()  # blank filled in from the network
        row = AppOpen.objects.get()
        self.assertEqual((row.city, row.source), ("Houston", "network"))
        self.post(place={"city": "Austin", "region": "TX", "country": "US"})  # network upgraded to the phone's place
        row.refresh_from_db()
        self.assertEqual((row.city, row.region, row.source), ("Austin", "Texas", "phone"))
        with mock.patch.object(geo, "lookup", return_value={"country": "US", "region": "Ohio", "city": "Dayton"}):
            self.post()  # a network lookup never replaces the phone's place
            self.post(place={"city": "Dallas", "region": "TX", "country": "US"})  # and the first phone place of the day stays
        row.refresh_from_db()
        self.assertEqual((row.city, row.source), ("Austin", "phone"))
        self.assertEqual(AppOpen.objects.count(), 1)

    def test_an_empty_place_falls_back_to_the_network(self):
        with mock.patch.object(geo, "lookup", return_value=dict(HOUSTON)):
            self.post(place={"city": "", "region": "", "country": ""})
        self.assertEqual(AppOpen.objects.get().source, "network")

    def test_validation(self):
        bad = [
            {"install_id": "short"},
            {"install_id": "x" * 81},
            {"platform": "windows"},
            {"app_version": "1" * 21},
            {"place": {"city": "c" * 81, "region": "TX", "country": "US"}},
            {"place": {"city": "Austin", "region": "r" * 81, "country": "US"}},
            {"place": {"city": "Austin", "region": "TX", "country": "USA"}},
            {"place": {"city": "Austin", "region": "TX", "country": "U1"}},
            {"place": "Austin, TX"},
            {"place": ["Austin", "TX", "US"]},
            {"place": {"city": 7, "region": "TX", "country": "US"}},
        ]
        for body in bad:
            self.assertEqual(self.post(body).status_code, 422, body)
        self.assertEqual(self.client.post("/api/v2/app/open", json.dumps({"platform": "ios"}), content_type="application/json").status_code, 422)
        self.assertEqual(AppOpen.objects.count(), 0)

    def test_control_characters_are_stripped(self):
        self.post(app_version="1.4\x00\n.0", place={"city": "Baton​\x07 Rouge\n", "region": " LA ", "country": "us"})
        row = AppOpen.objects.get()
        self.assertEqual((row.app_version, row.city, row.region, row.country), ("1.4 .0", "Baton Rouge", "Louisiana", "US"))

    def test_one_network_cannot_flood_rows(self):
        codes = [self.post(install_id=f"made-up-phone-{i:04d}").status_code for i in range(62)]
        self.assertEqual((codes[:60], codes[60:]), ([200] * 60, [429, 429]))
        self.assertEqual(AppOpen.objects.count(), 60)
        self.assertEqual(self.post(install_id="phone-on-another-network", ip="198.51.100.4").status_code, 200)
        self.assertEqual(self.post(install_id="forged-first-hop-0001", ip=f"1.2.3.4, {ADDRESS}").status_code, 429)

    @override_settings(USAGE_ENABLED=False)
    def test_switched_off_answers_ok_and_stores_nothing(self):
        with mock.patch.object(geo, "lookup") as lookup:
            res = self.post(place={"city": "Austin", "region": "TX", "country": "US"})
        self.assertEqual((res.status_code, res.json()), (200, {"ok": True}))
        lookup.assert_not_called()
        self.assertEqual(AppOpen.objects.count(), 0)


class GeoTests(TestCase):
    def setUp(self):
        geo.reset()
        self.addCleanup(geo.reset)

    def test_blank_and_quiet_without_a_database(self):
        with self.settings(GEOIP_DB_PATH="/nonexistent/city.mmdb"):
            self.assertEqual(geo.lookup("8.8.8.8"), NOWHERE)
            self.assertFalse(geo.available())
        with self.settings(GEOIP_DB_PATH=""):
            self.assertEqual(geo.lookup("8.8.8.8"), NOWHERE)

    def test_a_damaged_file_or_missing_package_is_blank_too(self):
        with tempfile.NamedTemporaryFile(suffix=".mmdb") as f, self.settings(GEOIP_DB_PATH=f.name):
            f.write(b"not a database")
            f.flush()
            self.assertEqual(geo.lookup("8.8.8.8"), NOWHERE)
            geo.reset()
            with mock.patch.object(geo, "_open", side_effect=ImportError("no maxminddb")):
                self.assertEqual(geo.lookup("8.8.8.8"), NOWHERE)
                self.assertFalse(geo.available())

    def test_reads_city_state_and_country_and_opens_the_file_once(self):
        record = {"country": {"iso_code": "US", "names": {"en": "United States"}},
                  "subdivisions": [{"names": {"en": "Texas"}}], "city": {"names": {"en": "Houston", "es": "Houston"}}}
        reader = FakeReader({"8.8.8.8": record, "9.9.9.9": {"country": {"iso_code": "CA"}}, "2001:4860:4860::8888": record})
        with tempfile.NamedTemporaryFile(suffix=".mmdb") as f, self.settings(GEOIP_DB_PATH=f.name), \
                mock.patch.object(geo, "_open", return_value=reader) as opened:
            self.assertEqual(geo.lookup("8.8.8.8"), HOUSTON)
            self.assertEqual(geo.lookup("2001:4860:4860::8888"), HOUSTON)
            self.assertEqual(geo.lookup("9.9.9.9"), {"country": "CA", "region": "", "city": ""})
            self.assertEqual(geo.lookup("1.1.1.1"), NOWHERE)  # not in the database
            self.assertTrue(geo.available())
            self.assertEqual(opened.call_count, 1)

    def test_private_and_malformed_addresses_are_not_looked_up(self):
        reader = mock.Mock()
        with tempfile.NamedTemporaryFile(suffix=".mmdb") as f, self.settings(GEOIP_DB_PATH=f.name), mock.patch.object(geo, "_open", return_value=reader):
            for address in ("10.0.0.5", "192.168.1.20", "127.0.0.1", "::1", "fe80::1", "", None, "not an address", "999.1.1.1", "8.8.8.8, 1.1.1.1"):
                self.assertEqual(geo.lookup(address), NOWHERE, address)
            reader.get.assert_not_called()
            reader.get.side_effect = RuntimeError("database closed")
            self.assertEqual(geo.lookup("8.8.8.8"), NOWHERE)


class PruneTests(TestCase):
    @override_settings(USAGE_KEEP_DAYS=400)
    def test_deletes_only_rows_past_the_keep_period(self):
        today = timezone.localdate()
        for days_ago in (0, 399, 400, 401, 900):
            AppOpen.objects.create(day=today - dt.timedelta(days=days_ago), install_hash=f"h{days_ago}", platform="ios")
        out = io.StringIO()
        call_command("usage_prune", stdout=out)
        self.assertEqual(sorted((today - d).days for d in AppOpen.objects.values_list("day", flat=True)), [0, 399, 400])
        self.assertIn("deleted 2 app-open rows", out.getvalue())
        out = io.StringIO()
        call_command("usage_prune", stdout=out)
        self.assertEqual(out.getvalue(), "")


class GeoUpdateTests(TestCase):
    def setUp(self):
        geo.reset()
        self.addCleanup(geo.reset)
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.target = Path(self.dir.name) / "geo" / "city.mmdb"
        self.database = b"\x00fake city database\x00" * 60_000  # a little over the 1 MB floor

    def run_command(self, fetch):
        out = io.StringIO()
        with self.settings(GEOIP_DB_PATH=str(self.target)), mock.patch.object(geo_update, "fetch", side_effect=fetch) as fetched, \
                mock.patch("usage.management.commands.geo_update.timezone.localdate", return_value=dt.date(2027, 1, 3)):
            call_command("geo_update", stdout=out)  # must not raise: the Docker build runs this
        return out.getvalue(), [c.args[0] for c in fetched.call_args_list]

    def test_downloads_and_unzips_this_months_file(self):
        out, urls = self.run_command(lambda url: io.BytesIO(gzip.compress(self.database)))
        self.assertEqual(urls, ["https://download.db-ip.com/free/dbip-city-lite-2027-01.mmdb.gz"])
        self.assertEqual(self.target.read_bytes(), self.database)
        self.assertIn("1.2 MB", out)
        self.assertEqual([p.name for p in self.target.parent.iterdir()], ["city.mmdb"])  # no temporary files left behind

    def test_falls_back_to_last_month(self):
        def fetch(url):
            if "2027-01" in url:
                raise OSError("HTTP Error 404: Not Found")
            return io.BytesIO(gzip.compress(self.database))

        out, urls = self.run_command(fetch)
        self.assertEqual([u[-18:-8] for u in urls], ["te-2027-01", "te-2026-12"])
        self.assertEqual(self.target.read_bytes(), self.database)
        self.assertIn("2026-12", out)

    def test_a_failed_download_is_reported_and_keeps_the_old_file(self):
        out, urls = self.run_command(lambda url: (_ for _ in ()).throw(OSError("network is unreachable")))
        self.assertEqual(len(urls), 2)
        self.assertIn("could not download", out)
        self.assertIn("blank until it works", out)
        self.assertFalse(self.target.exists())

        self.target.parent.mkdir(parents=True, exist_ok=True)
        self.target.write_bytes(b"last month's database")
        for bad in (b"<html>Not a gzip file</html>", gzip.compress(b"too small to be a database")):
            out, _ = self.run_command(lambda url, bad=bad: io.BytesIO(bad))
            self.assertIn("stays in use", out)
            self.assertEqual(self.target.read_bytes(), b"last month's database")
            self.assertEqual([p.name for p in self.target.parent.iterdir()], ["city.mmdb"])


class ReviewFixTests(TestCase):
    """Fixes from review: junk places, address-hopping, and readable addresses in the cache."""

    def setUp(self):
        cache.clear()

    def post(self, body, **extra):
        return self.client.post("/api/v2/app/open", json.dumps(body), content_type="application/json", **extra)

    def test_a_junk_phone_place_is_ignored_and_the_network_is_used(self):
        junk = [{"city": "36.1716,-115.1391 jane@x.com", "region": "NV", "country": "US"},
                {"city": "Reno", "region": "<b>zz</b>", "country": "US"},
                {"city": "Paris", "region": "IDF", "country": "FR"}]
        for i, place in enumerate(junk):
            with mock.patch("usage.geo.lookup", return_value={"country": "US", "region": "Nevada", "city": "Reno"}):
                self.assertEqual(self.post({"install_id": f"zh-junk-{i:04d}", "platform": "ios", "place": place}).status_code, 200)
        rows = list(AppOpen.objects.values_list("city", "region", "country", "source"))
        self.assertEqual(rows, [("Reno", "Nevada", "US", AppOpen.NETWORK)] * 3)

    def test_a_real_phone_place_is_kept(self):
        self.post({"install_id": "zh-good-0001", "platform": "ios", "place": {"city": "Coeur d'Alene", "region": "id", "country": "US"}})
        self.assertEqual(AppOpen.objects.values_list("city", "region", "source").get(), ("Coeur d'Alene", "Idaho", AppOpen.PHONE))

    @override_settings(NUM_PROXIES=1)
    def test_hopping_addresses_inside_one_ipv6_network_is_still_limited(self):
        codes = [self.post({"install_id": f"zh-hop-{i:05d}", "platform": "ios"}, HTTP_X_FORWARDED_FOR=f"2001:db8:1:1::{i:x}").status_code
                 for i in range(70)]
        self.assertEqual(codes.count(200), 60)
        self.assertEqual(codes.count(429), 10)

    @override_settings(NUM_PROXIES=1)
    def test_no_readable_address_is_kept_in_the_cache(self):
        self.post({"install_id": "zh-cache-0001", "platform": "ios"}, HTTP_X_FORWARDED_FOR="203.0.113.77")
        keys = " ".join(str(k) for k in cache._cache.keys())
        self.assertIn("throttle_usage_", keys)
        self.assertNotIn("203.0.113.77", keys)


class FirstOpenTests(TestCase):
    """A "download" is a phone's first-ever counted open."""

    def test_one_row_per_new_phone_on_its_first_day_only(self):
        def opened(phone, day, platform="ios"):
            AppOpen.objects.create(install_hash=phone, day=dt.date(2026, 11, day), platform=platform)
        opened("a", 1)
        opened("a", 5)
        opened("b", 5, "android")
        opened("c", 5)
        opened("c", 6)
        opened("d", 7)
        day5 = first_opens(dt.date(2026, 11, 5), dt.date(2026, 11, 5))
        self.assertEqual(sorted(day5.values_list("install_hash", "platform")), [("b", "android"), ("c", "ios")])
        self.assertEqual(first_opens(dt.date(2026, 11, 6), dt.date(2026, 11, 6)).count(), 0)
        self.assertEqual(first_opens(dt.date(2026, 11, 1), dt.date(2026, 11, 7)).count(), 4)
