from datetime import datetime, timedelta, timezone as dt_tz
from io import StringIO
from unittest.mock import patch

from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from .models import AppSignup, ToolboxTalk


class TalkReleaseTests(TestCase):
    def test_all_52_issues_loaded_with_pacific_send_times(self):
        self.assertEqual(ToolboxTalk.objects.count(), 52)
        first = ToolboxTalk.objects.get(issue=1)
        self.assertEqual(first.send_at, datetime(2027, 1, 3, 19, 59, tzinfo=dt_tz.utc))  # 11:59 AM PST
        summer = ToolboxTalk.objects.get(issue=27)
        self.assertEqual(summer.send_at, datetime(2027, 7, 4, 18, 59, tzinfo=dt_tz.utc))  # 11:59 AM PDT

    def test_api_hides_talks_before_send_time(self):
        before = datetime(2027, 1, 3, 19, 58, tzinfo=dt_tz.utc)
        with patch("django.utils.timezone.now", return_value=before):
            self.assertEqual(self.client.get("/api/talks/").json()["talks"], [])
            self.assertEqual(self.client.get("/api/talks/1/").status_code, 404)
        after = before + timedelta(minutes=2)
        with patch("django.utils.timezone.now", return_value=after):
            talks = self.client.get("/api/talks/").json()["talks"]
            self.assertEqual([t["issue"] for t in talks], [1])
            self.assertEqual(self.client.get("/api/talks/1/").json()["title"], "Prove the Power Is Off (LOTO try-out)")

    def test_push_sends_once_when_due(self):
        due = datetime(2027, 1, 3, 19, 59, 5, tzinfo=dt_tz.utc)
        with patch("django.utils.timezone.now", return_value=due), patch(
            "talks.integrations._post", return_value=(200, {"id": "abc"})
        ) as post, self.settings(ONESIGNAL_APP_ID="app", ONESIGNAL_REST_API_KEY="key"):
            call_command("send_talk_push", stdout=StringIO())
            call_command("send_talk_push", stdout=StringIO())  # second run must not resend
        self.assertEqual(post.call_count, 1)
        self.assertEqual(post.call_args[0][2]["data"], {"issue": 1})
        self.assertIsNotNone(ToolboxTalk.objects.get(issue=1).push_sent_at)


class SignupTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_signup_saves_and_validates(self):
        ok = self.client.post("/api/signups/", {"email": " Crew@Example.com ", "wants_offers": True}, content_type="application/json")
        self.assertEqual(ok.status_code, 201)
        self.assertEqual(AppSignup.objects.get().email, "crew@example.com")
        bad = self.client.post("/api/signups/", {"email": "nope"}, content_type="application/json")
        self.assertEqual(bad.status_code, 400)

    def test_signup_rate_limit(self):
        for _ in range(5):
            self.client.post("/api/signups/", {"email": "a@b.co"}, content_type="application/json")
        r = self.client.post("/api/signups/", {"email": "a@b.co"}, content_type="application/json")
        self.assertEqual(r.status_code, 429)
