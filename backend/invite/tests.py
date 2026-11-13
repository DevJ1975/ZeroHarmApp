import datetime as dt
from unittest import mock

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from backoffice import metrics
from talks.ghl import GhlError

from . import tagging, views
from .models import InviteClick

IPHONE = "Mozilla/5.0 (iPhone; CPU iPhone OS 19_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148"
IPAD = "Mozilla/5.0 (iPad; CPU OS 19_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148"
ANDROID = "Mozilla/5.0 (Linux; Android 16; Pixel 9) AppleWebKit/537.36 Chrome/140.0 Mobile Safari/537.36"
DESKTOP = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140.0 Safari/537.36"
APPLE, GOOGLE = "https://apps.apple.com/app/id123", "https://play.google.com/store/apps/details?id=com.example.zeroharm"
CONTACT = "aBcD1234eFgH5678iJkL"
NO_GHL = override_settings(GHL_PRIVATE_TOKEN="", GHL_LOCATION_ID="")
GHL = override_settings(GHL_PRIVATE_TOKEN="t", GHL_LOCATION_ID="loc")


class Base(TestCase):
    def setUp(self):
        cache.clear()

    def get(self, ua=DESKTOP, c=CONTACT, path="/get/", ip="203.0.113.7"):
        query = {"c": c} if c is not None else {}
        return self.client.get(path, query, HTTP_USER_AGENT=ua, REMOTE_ADDR=ip)


@NO_GHL
class PageTests(Base):
    @override_settings(APP_STORE_URL=APPLE, PLAY_STORE_URL=GOOGLE)
    def test_phones_go_to_their_store(self):
        for ua, url in ((IPHONE, APPLE), (IPAD, APPLE), (ANDROID, GOOGLE)):
            res = self.get(ua, c=None)
            self.assertEqual(res.status_code, 302, ua)
            self.assertEqual(res["Location"], url)
            self.assertEqual(res["Referrer-Policy"], "no-referrer")  # the contact id stays with us

    @override_settings(APP_STORE_URL=APPLE, PLAY_STORE_URL="")
    def test_a_store_not_live_yet_shows_the_page(self):
        self.assertEqual(self.get(IPHONE)["Location"], APPLE)
        res = self.get(ANDROID)
        self.assertEqual(res.status_code, 200)
        body = res.content.decode()
        self.assertIn("Download on the App Store", body)
        self.assertNotIn("Get it on Google Play", body)
        self.assertNotIn("Coming soon", body)

    @override_settings(APP_STORE_URL=APPLE, PLAY_STORE_URL=GOOGLE)
    def test_a_computer_gets_both_buttons(self):
        res = self.get(DESKTOP)
        self.assertEqual(res.status_code, 200)
        body = res.content.decode()
        self.assertIn(f'href="{APPLE}"', body)
        self.assertIn("Get it on Google Play", body)

    @override_settings(APP_STORE_URL="", PLAY_STORE_URL="")
    def test_coming_soon_when_no_store_is_set(self):
        for ua in (IPHONE, ANDROID, DESKTOP):
            res = self.get(ua)
            self.assertEqual(res.status_code, 200)
            body = res.content.decode()
            self.assertIn("Coming soon to the App Store and Google Play. We'll email you when it's ready.", body)
            self.assertIn("Free for every crew", body)
            self.assertIn("Zero Harm", body)
            self.assertNotIn("<script", body)
            self.assertNotIn("—", body)
            self.assertIn('name="robots" content="noindex', body)
            self.assertEqual(res["X-Robots-Tag"], "noindex")
            self.assertIn("default-src 'none'", res["Content-Security-Policy"])

    @override_settings(APP_STORE_URL="http://not-secure.example", PLAY_STORE_URL="")
    def test_only_https_store_addresses_are_used(self):
        self.assertEqual(self.get(IPHONE).status_code, 200)

    def test_with_and_without_the_slash(self):
        self.assertEqual(self.get(path="/get").status_code, 200)
        self.assertEqual(self.get(path="/get/").status_code, 200)
        self.assertEqual(InviteClick.objects.count(), 1)


@NO_GHL
class CountTests(Base):
    def test_contact_id_must_be_10_to_40_letters_or_digits(self):
        for bad in ("short", "a" * 41, "abc-def-ghi-jkl", "{{contact.id}}", "abcdefghij<script>", "abcdefghij klm", ""):
            res = self.get(c=bad)
            self.assertEqual(res.status_code, 200)  # the page still works, the id is just ignored
        self.assertFalse(InviteClick.objects.exists())
        self.get(c="a" * 10)
        self.get(c="Z9" * 20)
        self.assertEqual(InviteClick.objects.count(), 2)

    def test_one_row_per_contact_per_day(self):
        for _ in range(5):
            self.get(IPHONE)
        self.get(ANDROID)
        self.assertEqual(InviteClick.objects.count(), 1)
        click = InviteClick.objects.get()
        self.assertEqual((click.contact_id, click.platform, click.day), (CONTACT, InviteClick.IOS, timezone.localdate()))
        later = timezone.now() + dt.timedelta(days=1)
        with mock.patch("django.utils.timezone.now", return_value=later):
            self.get(ANDROID)
        self.assertEqual(InviteClick.objects.count(), 2)

    def test_platforms(self):
        self.get(IPHONE, c="a" * 12)
        self.get(ANDROID, c="b" * 12)
        self.get(DESKTOP, c="c" * 12)
        self.assertEqual(dict(InviteClick.objects.values_list("contact_id", "platform")),
                         {"a" * 12: "ios", "b" * 12: "android", "c" * 12: "other"})

    def test_no_network_address_or_browser_kept(self):
        self.get(IPHONE, ip="198.51.100.23")
        fields = {f.name for f in InviteClick._meta.get_fields()}
        self.assertEqual(fields, {"id", "contact_id", "day", "platform", "created_at", "tagged_at", "contact_missing"})
        row = InviteClick.objects.values().get()
        self.assertNotIn("198.51.100.23", str(row))
        self.assertNotIn("iPhone OS", str(row))

    def test_rate_limit_per_network(self):
        for i in range(views.NEW_CLICKS_PER_HOUR + 10):
            res = self.get(c=f"contact{i:06d}")
            self.assertEqual(res.status_code, 200)  # over the limit the page still shows; nothing is stored
        self.assertEqual(InviteClick.objects.count(), views.NEW_CLICKS_PER_HOUR)
        self.get(c="othernetwork01", ip="192.0.2.50")  # another network has its own limit
        self.assertTrue(InviteClick.objects.filter(contact_id="othernetwork01").exists())

    def test_ipv6_network_counts_as_one(self):
        for i in range(views.NEW_CLICKS_PER_HOUR + 5):
            self.get(c=f"contact{i:06d}", ip=f"2001:db8:1:2::{i + 1:x}")
        self.assertEqual(InviteClick.objects.count(), views.NEW_CLICKS_PER_HOUR)

    def test_reloads_dont_use_up_the_limit(self):
        for _ in range(views.NEW_CLICKS_PER_HOUR + 5):
            self.get()
        self.get(c="anothercontact1")
        self.assertEqual(InviteClick.objects.count(), 2)


@GHL
class TagTests(Base):
    def test_a_tap_tags_the_contact_quickly(self):
        with mock.patch("talks.ghl.request", return_value={}) as req:
            self.get(IPHONE)
            self.get(IPHONE)  # a reload doesn't tag again
        req.assert_called_once_with("POST", f"/contacts/{CONTACT}/tags", body={"tags": ["zero-harm-invite-clicked"]}, timeout=views.TAG_WAIT)
        self.assertLessEqual(views.TAG_WAIT, 3)
        click = InviteClick.objects.get()
        self.assertIsNotNone(click.tagged_at)
        self.assertFalse(click.contact_missing)

    def test_no_contact_id_means_no_call(self):
        with mock.patch("talks.ghl.request") as req:
            self.get(c=None)
            self.get(c="bad")
        req.assert_not_called()

    def test_ghl_down_then_the_cron_retries(self):
        with mock.patch("talks.ghl.request", side_effect=GhlError("down")):
            res = self.get(ANDROID)
        self.assertEqual(res.status_code, 200)  # the visitor never sees the failure
        self.assertIsNone(InviteClick.objects.get().tagged_at)
        with mock.patch("talks.ghl.request", side_effect=GhlError("still down", status=503)):
            self.assertEqual(tagging.retry_tags(), 0)
        with mock.patch("talks.ghl.request", side_effect=GhlError("no token", status=401)):
            self.assertEqual(tagging.retry_tags(), 0)
        with mock.patch("talks.ghl.request", return_value={}) as req:
            self.assertEqual(tagging.retry_tags(), 1)
            self.assertEqual(tagging.retry_tags(), 0)  # done, not tagged twice
        req.assert_called_once()
        self.assertIsNotNone(InviteClick.objects.get().tagged_at)

    def test_only_the_last_two_days_are_retried(self):
        with mock.patch("talks.ghl.request", side_effect=GhlError("down")):
            self.get()
        InviteClick.objects.update(created_at=timezone.now() - dt.timedelta(days=3))
        with mock.patch("talks.ghl.request") as req:
            self.assertEqual(tagging.retry_tags(), 0)
        req.assert_not_called()

    def test_contact_not_found_counts_as_done(self):
        for status in (400, 404, 422):
            InviteClick.objects.all().delete()
            with mock.patch("talks.ghl.request", side_effect=GhlError("Contact not found", status=status)):
                self.get()
            click = InviteClick.objects.get()
            self.assertIsNotNone(click.tagged_at, status)
            self.assertTrue(click.contact_missing)
            with mock.patch("talks.ghl.request") as req:
                self.assertEqual(tagging.retry_tags(), 0)
            req.assert_not_called()

    def test_cron_runs_the_retry(self):
        from django.core.management import call_command

        with mock.patch("talks.ghl.request", side_effect=GhlError("down")):
            self.get()
        with mock.patch("talks.management.commands.cron.call_command"), mock.patch("talks.ghl.request", return_value={}), \
             mock.patch("talks.owner_alerts.retry_signup_alerts", return_value=0), mock.patch("talks.owner_alerts.retry_removals", return_value=0), \
             mock.patch("talks.management.commands.cron.sync_episodes", return_value=[]):
            call_command("cron")
        self.assertIsNotNone(InviteClick.objects.get().tagged_at)

    @NO_GHL
    def test_nothing_is_sent_without_ghl_settings(self):
        with mock.patch("talks.ghl.request") as req:
            self.get()
            self.assertEqual(tagging.retry_tags(), 0)
        req.assert_not_called()
        self.assertIsNone(InviteClick.objects.get().tagged_at)


@NO_GHL
@override_settings(BACKOFFICE_KEY="k")
class BackOfficeTests(Base):
    def test_invite_taps_in_the_period(self):
        self.get(IPHONE, c="a" * 12)
        self.get(IPHONE, c="b" * 12)
        self.get(ANDROID, c="c" * 12)
        self.get(DESKTOP, c="d" * 12)
        old = InviteClick.objects.create(contact_id="e" * 12, platform="ios", day=timezone.localdate() - dt.timedelta(days=60))
        InviteClick.objects.filter(pk=old.pk).update(created_at=timezone.now() - dt.timedelta(days=60))
        tile = next(t for t in metrics.dashboard(30)["tiles"] if t["label"] == "Invite link taps")
        self.assertEqual(tile["value"], 4)
        self.assertEqual(tile["note"], "2 iPhone · 1 Android · 1 other")
        tile = next(t for t in metrics.dashboard(90)["tiles"] if t["label"] == "Invite link taps")
        self.assertEqual(tile["value"], 5)
        body = self.client.get("/backoffice/?key=k").content.decode()
        self.assertIn("Invite link taps", body)
        self.assertIn("2 iPhone · 1 Android · 1 other", body)
