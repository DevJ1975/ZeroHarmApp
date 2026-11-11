"""Tests for the content console API (/api/console/) and the public content version."""
import json
from datetime import datetime, timedelta, timezone as dt_tz
from unittest.mock import patch

from django.core.cache import cache, caches
from django.test import TestCase, override_settings

from .models import Episode, FeedItem, KbEntry, TalkSuggestion, ToolboxTalk

KEY = "console-test-key-long-and-random"
AFTER_ISSUE_1 = datetime(2027, 1, 3, 20, 5, tzinfo=dt_tz.utc)  # issue 1 sends 2027-01-03 19:59 UTC


@override_settings(CONSOLE_KEY=KEY)
class ConsoleCase(TestCase):
    def setUp(self):
        cache.clear()
        caches["shared"].clear()

    def call(self, method, path, body=None, key=KEY, **extra):
        headers = {"HTTP_AUTHORIZATION": f"Bearer {key}", **extra} if key is not None else extra
        data = json.dumps(body) if body is not None else ""
        return getattr(self.client, method)(f"/api/console/{path}", data=data, content_type="application/json", **headers)


class AuthTests(ConsoleCase):
    @override_settings(CONSOLE_KEY="")
    def test_console_off_without_key(self):
        r = self.call("get", "overview/")
        self.assertEqual(r.status_code, 503)
        self.assertIn("CONSOLE_KEY", r.json()["error"])

    def test_wrong_or_missing_key(self):
        self.assertEqual(self.call("get", "overview/", key="nope").status_code, 401)
        self.assertEqual(self.call("get", "overview/", key=None).status_code, 401)
        r = self.client.get("/api/console/overview/", HTTP_AUTHORIZATION=KEY)  # no "Bearer "
        self.assertEqual(r.json(), {"error": "Not authorized."})

    def test_failed_attempts_rate_limited(self):
        for _ in range(10):
            self.assertEqual(self.call("get", "talks/", key="guess").status_code, 401)
        self.assertEqual(self.call("get", "talks/", key="guess").status_code, 429)
        self.assertEqual(self.call("get", "talks/").status_code, 429)  # even the right key, until the hour passes

    def test_rate_limit_uses_the_address_the_edge_added(self):
        # The caller controls everything before the last X-Forwarded-For entry, so rotating it buys nothing.
        for i in range(10):
            r = self.call("get", "talks/", key="guess", HTTP_X_FORWARDED_FOR=f"10.0.0.{i}, 203.0.113.7")
            self.assertEqual(r.status_code, 401)
        self.assertEqual(self.call("get", "talks/", key="guess", HTTP_X_FORWARDED_FOR="10.9.9.9, 203.0.113.7").status_code, 429)
        # Someone else, as the edge saw them, is not locked out, even if they claim the blocked address first.
        self.assertEqual(self.call("get", "talks/", HTTP_X_FORWARDED_FOR="203.0.113.7, 198.51.100.2").status_code, 200)

    @override_settings(CONSOLE_KEY="short-key")
    def test_short_key_keeps_console_off(self):
        with self.assertLogs("talks.console", "ERROR"):
            r = self.call("get", "overview/", key="short-key")
        self.assertEqual(r.status_code, 503)
        self.assertIn("32 characters", r.json()["error"])

    def test_unexpected_error_is_still_json(self):
        with patch("talks.console.talk_admin", side_effect=RuntimeError("boom")), self.assertLogs("talks.console", "ERROR"):
            r = self.call("get", "talks/1/")
        self.assertEqual(r.status_code, 500)
        self.assertIn("error", r.json())

    def test_right_key_and_method_check(self):
        r = self.call("get", "overview/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["counts"]["talks"], 52)
        self.assertEqual(self.call("delete", "overview/").status_code, 405)

    def test_overview_lists_upcoming_and_recent_pushes(self):
        ToolboxTalk.objects.filter(issue=2).update(push_sent_at=datetime(2026, 11, 1, tzinfo=dt_tz.utc))
        with patch("django.utils.timezone.now", return_value=datetime(2026, 11, 10, tzinfo=dt_tz.utc)):
            data = self.call("get", "overview/").json()
        self.assertEqual(data["upcoming"][0]["type"], "episode")  # EP 04, Nov 12
        self.assertTrue(data["upcoming"][0]["push"])
        Episode.objects.filter(number=4).update(needs_details=True)
        with patch("django.utils.timezone.now", return_value=datetime(2026, 11, 10, tzinfo=dt_tz.utc)):
            self.assertFalse(self.call("get", "overview/").json()["upcoming"][0]["push"])  # held, so the cron won't push it
        self.assertIn({"type": "talk", "id": 2, "title": ToolboxTalk.objects.get(issue=2).title,
                       "at": "2026-11-01T00:00:00+00:00"}, data["recent_pushes"])
        self.assertFalse(data["onesignal_configured"])


class TalkTests(ConsoleCase):
    def test_list_and_detail(self):
        talks = self.call("get", "talks/").json()["talks"]
        self.assertEqual(talks[0]["issue"], 52)
        self.assertIn("spanish_status", talks[0])
        self.assertEqual(self.call("get", "talks/999/").status_code, 404)

    def test_patch_saves_and_parses_send_at_as_pacific(self):
        r = self.call("patch", "talks/1/", {"title": "  New title ", "send_at": "2027-01-03T10:00", "issue": 77})
        self.assertEqual(r.status_code, 200)
        talk = ToolboxTalk.objects.get(issue=1)
        self.assertEqual(talk.title, "New title")
        self.assertEqual(talk.send_at, datetime(2027, 1, 3, 18, 0, tzinfo=dt_tz.utc))  # 10 AM PST
        self.assertEqual(r.json()["send_at"], "2027-01-03T18:00:00+00:00")
        self.call("patch", "talks/1/", {"send_at": "2027-07-04T11:59:00"})
        self.assertEqual(ToolboxTalk.objects.get(issue=1).send_at, datetime(2027, 7, 4, 18, 59, tzinfo=dt_tz.utc))  # PDT
        self.call("patch", "talks/1/", {"send_at": "2027-01-03T12:00:00Z"})
        self.assertEqual(ToolboxTalk.objects.get(issue=1).send_at, datetime(2027, 1, 3, 12, 0, tzinfo=dt_tz.utc))

    def test_patch_validation(self):
        for body in ({"hero_url": "http://x.com/a.jpg"}, {"title": ""}, {"published": "yes"}, {"send_at": "someday"},
                     {"spanish_status": "maybe"}, {"title": "x" * 201}, {"spanish_status": "approved"}):
            r = self.call("patch", "talks/1/", body)
            self.assertEqual(r.status_code, 400, body)
            self.assertIn("error", r.json())
        self.assertEqual(ToolboxTalk.objects.get(issue=1).spanish_status, "none")
        ok = self.call("patch", "talks/1/", {"title_es": "Compruebe", "body_md_es": "Texto", "spanish_status": "approved"})
        self.assertEqual(ok.json()["es"]["title"], "Compruebe")

    def test_push_refuses_unreleased_unless_forced(self):
        with patch("talks.integrations._post", return_value=(200, {"id": "n1"})) as post, \
             self.settings(ONESIGNAL_APP_ID="app", ONESIGNAL_REST_API_KEY="key"), \
             patch("django.utils.timezone.now", return_value=datetime(2026, 11, 10, tzinfo=dt_tz.utc)):
            self.assertEqual(self.call("post", "talks/1/push/").status_code, 409)
            self.assertEqual(post.call_count, 0)
            r = self.call("post", "talks/1/push/", {"force": True})
        self.assertEqual(r.json(), {"ok": True, "detail": {"id": "n1"}})
        payload = post.call_args[0][2]
        self.assertEqual(payload["data"], {"issue": 1, "refresh": True})
        self.assertEqual(payload["filters"][0]["key"], "weekly_talk")
        self.assertIsNone(ToolboxTalk.objects.get(issue=1).push_sent_at)  # early push: the Sunday push still goes out
        with patch("talks.integrations._post", return_value=(200, {"id": "n2"})), \
             self.settings(ONESIGNAL_APP_ID="app", ONESIGNAL_REST_API_KEY="key"), \
             patch("django.utils.timezone.now", return_value=AFTER_ISSUE_1):
            self.call("post", "talks/1/push/")
        self.assertIsNotNone(ToolboxTalk.objects.get(issue=1).push_sent_at)  # once live, it counts as the release push

    def test_push_released_talk_and_onesignal_failure(self):
        with patch("talks.integrations._post", return_value=(400, {"errors": ["bad"]})), \
             self.settings(ONESIGNAL_APP_ID="app", ONESIGNAL_REST_API_KEY="key"), \
             patch("django.utils.timezone.now", return_value=AFTER_ISSUE_1):
            r = self.call("post", "talks/1/push/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"ok": False, "detail": {"errors": ["bad"]}})  # OneSignal's reason reaches the console
        self.assertIsNone(ToolboxTalk.objects.get(issue=1).push_sent_at)

    def test_spanish_draft(self):
        def fake(talk):
            talk.title_es, talk.body_md_es, talk.spanish_status = "Título", "Texto", "draft"
            talk.save()
        with patch("talks.translate.draft_spanish", side_effect=fake):
            r = self.call("post", "talks/1/spanish-draft/")
        self.assertEqual(r.json()["spanish_status"], "draft")
        self.assertEqual(r.json()["title_es"], "Título")
        with patch("talks.translate.draft_spanish", side_effect=RuntimeError("Set ANTHROPIC_API_KEY")):
            r = self.call("post", "talks/1/spanish-draft/")
        self.assertEqual(r.status_code, 424)
        self.assertIn("ANTHROPIC_API_KEY", r.json()["error"])


class FeedTests(ConsoleCase):
    def create(self, **extra):
        return self.call("post", "feed/", {"kind": "alert", "title": "Nevada heat rule", "jurisdiction": "nevada",
                                           "publish_at": "2026-12-01T08:00", "link_url": "https://example.com/rule", **extra})

    def test_create_update_and_soft_delete(self):
        r = self.create(send_push=True)
        self.assertEqual(r.status_code, 201)
        item = r.json()
        self.assertTrue(item["external_id"].startswith("console:"))
        self.assertEqual(item["publish_at"], "2026-12-01T16:00:00+00:00")
        self.assertEqual(item["link_url"], "https://example.com/rule?src=zero-harm-app")
        self.assertEqual(item["link_url_raw"], "https://example.com/rule")
        self.assertFalse(item["live"])
        pk = item["id"]
        r = self.call("patch", f"feed/{pk}/", {"title": "Nevada heat rule (revised)", "featured": True, "publish_at": "2026-11-01T08:00"})
        self.assertEqual(r.json()["title"], "Nevada heat rule (revised)")
        self.assertTrue(r.json()["live"])
        r = self.call("delete", f"feed/{pk}/")
        self.assertFalse(r.json()["published"])
        self.assertTrue(FeedItem.objects.filter(pk=pk).exists())  # never hard-deleted
        self.assertEqual(self.client.get("/api/feed/").json()["items"], [])
        self.assertEqual(len(self.call("get", "feed/").json()["items"]), 1)

    def test_create_validation(self):
        self.assertEqual(self.call("post", "feed/", {"title": "No kind"}).status_code, 400)
        self.assertEqual(self.create(kind="banner").status_code, 400)
        self.assertEqual(self.create(link_url="http://x.com").status_code, 400)
        self.assertEqual(self.create(jurisdiction="texas").status_code, 400)
        self.assertEqual(self.create(expires_at="2026-11-01T08:00").status_code, 400)
        self.assertEqual(self.create(effective_date="soon").status_code, 400)
        self.assertEqual(self.create(effective_date="2027-02-30").status_code, 400)  # date-shaped but not a real day
        self.assertEqual(FeedItem.objects.count(), 0)
        self.assertEqual(self.call("patch", "feed/999/", {"title": "x"}).status_code, 404)

    def test_create_without_publish_at_goes_live_now(self):
        r = self.call("post", "feed/", {"kind": "course", "title": "OSHA 300 crash course"})
        self.assertTrue(r.json()["live"])

    def test_push(self):
        pk = self.create(publish_at="2026-11-01T08:00").json()["id"]
        with patch("talks.integrations._post", return_value=(200, {"id": "p"})) as post, \
             self.settings(ONESIGNAL_APP_ID="app", ONESIGNAL_REST_API_KEY="key"):
            r = self.call("post", f"feed/{pk}/push/")
        self.assertTrue(r.json()["ok"])
        self.assertEqual(post.call_args[0][2]["filters"][0]["key"], "alerts")
        self.assertEqual(post.call_args[0][2]["data"], {"feed_id": pk, "kind": "alert", "refresh": True})
        self.assertIsNotNone(FeedItem.objects.get(pk=pk).push_sent_at)
        future = self.create(title="Later", publish_at="2030-01-01T08:00").json()["id"]
        self.assertEqual(self.call("post", f"feed/{future}/push/").status_code, 409)
        with patch("talks.integrations._post", return_value=(200, {"id": "q"})), \
             self.settings(ONESIGNAL_APP_ID="app", ONESIGNAL_REST_API_KEY="key"):
            self.assertTrue(self.call("post", f"feed/{future}/push/", {"force": True}).json()["ok"])
        self.assertIsNone(FeedItem.objects.get(pk=future).push_sent_at)  # the release push still goes out


class EpisodeTests(ConsoleCase):
    def test_list_patch_and_push(self):
        eps = self.call("get", "episodes/").json()["episodes"]
        self.assertEqual([e["number"] for e in eps], [4, 3, 2, 1])
        r = self.call("patch", "episodes/1/", {"title": "Stored Energy", "checks": ["Lock it", " ", "Try it"], "release_at": "2026-11-05T05:00"})
        self.assertEqual(r.status_code, 200)
        ep = Episode.objects.get(number=1)
        self.assertEqual(ep.checks, ["Lock it", "Try it"])
        self.assertEqual(ep.release_at, datetime(2026, 11, 5, 13, 0, tzinfo=dt_tz.utc))
        self.assertEqual(self.call("patch", "episodes/1/", {"checks": "Lock it"}).status_code, 400)
        self.assertEqual(self.call("patch", "episodes/1/", {"video_url": "ftp://x"}).status_code, 400)
        with patch("talks.integrations._post", return_value=(200, {"id": "e"})) as post, \
             self.settings(ONESIGNAL_APP_ID="app", ONESIGNAL_REST_API_KEY="key"), \
             patch("django.utils.timezone.now", return_value=datetime(2026, 11, 10, tzinfo=dt_tz.utc)):
            self.assertEqual(self.call("post", "episodes/4/push/").status_code, 409)  # releases Nov 12
            self.assertTrue(self.call("post", "episodes/4/push/", {"force": True}).json()["ok"])
            self.assertIsNone(Episode.objects.get(number=4).push_sent_at)  # Thursday's release push still goes out
            r = self.call("post", "episodes/1/push/")
        self.assertTrue(r.json()["ok"])
        self.assertEqual(post.call_args[0][2]["data"], {"episode": 1, "refresh": True})
        self.assertEqual(post.call_args[0][2]["filters"][0]["key"], "zero_hour")


class KbAndSuggestionTests(ConsoleCase):
    def test_kb_crud(self):
        before = KbEntry.objects.filter(published=True).count()
        r = self.call("post", "kb/", {"title": "Forklift seat belts", "body": "Wear the belt.", "source": "OSHA 1910.178"})
        self.assertEqual(r.status_code, 201)
        pk = r.json()["id"]
        self.assertEqual(self.call("post", "kb/", {"title": "No body"}).status_code, 400)
        self.assertEqual(self.call("patch", f"kb/{pk}/", {"tags": "forklift, pit"}).json()["tags"], "forklift, pit")
        self.assertEqual(len(self.call("get", "kb/").json()["entries"]), before + 1)
        self.assertFalse(self.call("delete", f"kb/{pk}/").json()["published"])
        self.assertTrue(KbEntry.objects.filter(pk=pk).exists())
        self.assertFalse(any(i["id"] == f"k{pk}" for i in self.client.get("/api/otis/kb/").json()["items"]))

    def test_suggestions(self):
        s = TalkSuggestion.objects.create(topic="Battery charging")
        self.assertEqual(self.call("get", "suggestions/").json()["suggestions"][0]["topic"], "Battery charging")
        r = self.call("patch", f"suggestions/{s.pk}/", {"status": "used", "used_in_issue": 12})
        self.assertEqual((r.json()["status"], r.json()["used_in_issue"]), ("used", 12))
        self.assertEqual(self.call("patch", f"suggestions/{s.pk}/", {"status": "maybe"}).status_code, 400)
        self.assertEqual(self.call("patch", f"suggestions/{s.pk}/", {"used_in_issue": "twelve"}).status_code, 400)


class BroadcastTests(ConsoleCase):
    def send(self, **body):
        return self.call("post", "broadcast/", {"audience": "alerts", "heading": "Heat advisory", "message": "Water, rest, shade.", **body})

    def test_audience_and_field_validation(self):
        self.assertEqual(self.send(audience="everyone").status_code, 400)
        self.assertEqual(self.send(audience=None).status_code, 400)
        self.assertEqual(self.send(heading="x" * 61).status_code, 400)
        self.assertEqual(self.send(message="").status_code, 400)
        self.assertEqual(self.send(route="https://evil.example").status_code, 400)
        self.assertEqual(self.send(route="/talk/abc").status_code, 400)

    def test_dry_run_never_posts(self):
        with patch("talks.integrations._post") as post:
            r = self.send(dry_run=True, route="/alert/3", audience="offers")
        self.assertEqual(post.call_count, 0)
        detail = r.json()["detail"]
        self.assertEqual(detail["filters"], [{"field": "tag", "key": "offers", "relation": "=", "value": "on"}])
        self.assertEqual(detail["data"], {"route": "/alert/3", "refresh": True})
        self.assertNotIn("included_segments", detail)

    def test_send(self):
        with patch("talks.integrations._post", return_value=(200, {"id": "b"})) as post, \
             self.settings(ONESIGNAL_APP_ID="app", ONESIGNAL_REST_API_KEY="key"):
            r = self.send(route="/learn")
        self.assertEqual(r.json(), {"ok": True, "detail": {"id": "b"}})
        self.assertEqual(post.call_args[0][2]["headings"], {"en": "Heat advisory"})
        with self.settings(ONESIGNAL_APP_ID=""):
            r = self.send()
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()["ok"])
        self.assertIn("not configured", r.json()["detail"])


class ContentVersionTests(ConsoleCase):
    def version(self):
        r = self.client.get("/api/content-version/")
        self.assertEqual(r.status_code, 200)
        return r.json()["version"]

    def test_public_and_changes_after_edits(self):
        with patch("django.utils.timezone.now", return_value=AFTER_ISSUE_1):
            v1 = self.version()
            self.assertEqual(v1, self.version())  # stable when nothing changed
            self.call("patch", "talks/1/", {"title": "Edited"})
            v2 = self.version()
            self.assertNotEqual(v1, v2)
            self.call("post", "kb/", {"title": "New entry", "body": "Text."})
            v3 = self.version()
            self.assertNotEqual(v2, v3)
            self.call("patch", "talks/30/", {"title": "Not released yet"})  # unreleased edits don't change what the app sees
            self.assertEqual(v3, self.version())
        with patch("django.utils.timezone.now", return_value=AFTER_ISSUE_1 + timedelta(days=7)):
            self.assertNotEqual(v3, self.version())  # issue 2 released

    def test_changes_when_one_alert_ends_as_another_starts(self):
        swap = datetime(2026, 12, 1, 16, 0, tzinfo=dt_tz.utc)
        with patch("django.utils.timezone.now", return_value=swap - timedelta(days=30)):
            FeedItem.objects.create(external_id="a", kind="alert", title="Ends", publish_at=swap - timedelta(days=10), expires_at=swap)
            FeedItem.objects.create(external_id="b", kind="alert", title="Starts", publish_at=swap)
        FeedItem.objects.create(external_id="c", kind="alert", title="Newest edit", publish_at=swap - timedelta(days=10))
        with patch("django.utils.timezone.now", return_value=swap - timedelta(minutes=1)):
            before = self.version()
        with patch("django.utils.timezone.now", return_value=swap + timedelta(minutes=1)):
            self.assertNotEqual(before, self.version())  # same count and same latest edit, different items

    @override_settings(CONSOLE_KEY="")
    def test_works_without_console_key(self):
        self.assertTrue(self.version())
