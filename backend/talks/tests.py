from datetime import datetime, timedelta, timezone as dt_tz
from io import StringIO
from unittest.mock import patch

from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings
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
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(AppSignup.objects.get().email, "crew@example.com")
        bad = self.client.post("/api/signups/", {"email": "nope"}, content_type="application/json")
        self.assertEqual(bad.status_code, 400)

    def test_repeats_have_a_wide_limit_of_their_own(self):
        for _ in range(120):
            self.client.post("/api/signups/", {"email": "a@b.co"}, content_type="application/json")
        r = self.client.post("/api/signups/", {"email": "a@b.co"}, content_type="application/json")
        self.assertEqual(r.status_code, 429)


# ---- GHL pipeline, feed, Spanish and sign-in sheets ----------------------------------------------
import base64
import json as _json
from pathlib import Path

from .ghl_sync import send_time, sync_year
from .models import FeedItem, GhlSync, SigninSheet

ISSUE23 = (Path(__file__).parent / "test_data" / "issue23.html").read_text()
KEY = "test-ingest-key"


class GhlYearSyncTests(TestCase):
    def templates(self):
        return [
            {"id": "t23", "name": "Zero Harm Weekly #23 – Heat Stroke Is a 911 Call (June 7, 2027)", "previewUrl": "u23", "updatedAt": "2026-11-06"},
            {"id": "t01", "name": "Zero Harm Weekly #01 – New Year Kickoff (January 3, 2028)", "previewUrl": "u01", "updatedAt": "2026-11-06"},
            {"id": "x", "name": "Some other newsletter", "previewUrl": "ux"},
        ]

    def test_sync_updates_existing_issue_and_holds_flagged_text(self):
        log = sync_year(2027, fetch_html=lambda url: ISSUE23, templates=self.templates())
        talk = ToolboxTalk.objects.get(issue=23)
        self.assertIn("Spot the early signs", talk.body_md)
        self.assertTrue(talk.hero_url.endswith("issue-23.jpg"))
        self.assertTrue(talk.pdf_url.endswith(".pdf"))
        self.assertTrue(talk.needs_review)  # the OSHA section still has a [Check ...] flag
        self.assertIn("HELD", "\n".join(log))
        with patch("django.utils.timezone.now", return_value=talk.send_at + timedelta(minutes=1)):
            issues = [t["issue"] for t in self.client.get("/api/talks/").json()["talks"]]
        self.assertNotIn(23, issues)

    def test_new_year_gets_new_rows_and_sunday_send_time(self):
        sync_year(2028, fetch_html=lambda url: ISSUE23.replace("Heat Stroke Is a 911 Call", "New Year Kickoff"), templates=self.templates())
        talk = ToolboxTalk.objects.get(issue_date="2028-01-03")
        self.assertEqual(talk.issue, 53)
        self.assertEqual(talk.number, 1)
        self.assertEqual(talk.send_at, datetime(2028, 1, 2, 19, 59, tzinfo=dt_tz.utc))
        self.assertEqual(ToolboxTalk.objects.get(issue=1).title, "Prove the Power Is Off (LOTO try-out)")  # 2027 untouched

    def test_reads_every_name_format_in_use(self):
        from .talk_parse import parse_name
        from datetime import date
        self.assertEqual(parse_name("Zero Harm Weekly #01 – Prove the Power Is Off (Jan 4, 2027)"), (1, "Prove the Power Is Off", date(2027, 1, 4)))
        self.assertEqual(parse_name("Zero Harm Weekly #4 – See a Lock, Leave It Alone: What Everyone Else Does During Lockout (January 25, 2027)")[0], 4)
        self.assertIsNone(parse_name("Zero Harm Weekly – Welcome"))

    def test_send_time_handles_daylight_saving(self):
        from datetime import date
        self.assertEqual(send_time(date(2027, 7, 5)).hour, 18)
        self.assertEqual(send_time(date(2027, 1, 4)).hour, 19)


class SpanishTests(TestCase):
    def test_spanish_only_when_approved(self):
        talk = ToolboxTalk.objects.get(issue=1)
        talk.title_es, talk.body_md_es, talk.spanish_status = "Compruebe que no hay energía", "Texto", "draft"
        talk.save()
        self.assertIsNone(talk.as_api()["es"])
        talk.spanish_status = "approved"
        self.assertEqual(talk.as_api()["es"]["title"], "Compruebe que no hay energía")


@override_settings(INGEST_KEY=KEY)
class IngestAndFeedTests(TestCase):
    def post(self, body, key=KEY):
        return self.client.post("/api/ingest/", _json.dumps(body), content_type="application/json", HTTP_X_ZEROHARM_KEY=key)

    def test_rejects_wrong_key(self):
        self.assertEqual(self.post({"kind": "alert", "title": "x"}, key="nope").status_code, 401)

    def test_publish_update_and_schedule(self):
        r = self.post({"Kind": "Regulatory alert", "Title": "Nevada heat rule update", "Summary": "What changed.",
                       "Jurisdiction": "Nevada", "Publish At": "2026-12-01 08:00", "Send Push": "Yes",
                       "Link": "https://example.com/rule", "External ID": "ghl-123"})
        self.assertEqual(r.status_code, 201)
        item = FeedItem.objects.get()
        self.assertEqual(item.publish_at, datetime(2026, 12, 1, 16, 0, tzinfo=dt_tz.utc))  # 8 AM Pacific
        self.assertTrue(item.send_push)
        self.assertEqual(self.post({"kind": "alert", "title": "Nevada heat rule update (revised)", "external_id": "ghl-123"}).status_code, 200)
        self.assertEqual(FeedItem.objects.count(), 1)
        with patch("django.utils.timezone.now", return_value=datetime(2026, 11, 30, tzinfo=dt_tz.utc)):
            self.assertEqual(self.client.get("/api/feed/").json()["items"], [])

    def test_feed_links_carry_app_source(self):
        self.post({"kind": "course", "title": "OSHA 300 Log Crash Course", "link": "https://go.trainovate.ai/osha-300"})
        item = self.client.get("/api/feed/?kind=course").json()["items"][0]
        self.assertEqual(item["link_url"], "https://go.trainovate.ai/osha-300?src=zero-harm-app")

    def test_rejects_non_https_links_and_bad_kinds(self):
        self.assertEqual(self.post({"kind": "course", "title": "x", "link": "http://x.com"}).status_code, 400)
        self.assertEqual(self.post({"kind": "banner", "title": "x"}).status_code, 400)

    def test_sync_year_request_is_queued(self):
        self.assertEqual(self.post({"action": "sync_year", "year": 2028}).status_code, 202)
        self.assertEqual(GhlSync.objects.get().status, "pending")

    def test_alert_push_goes_once_to_alert_subscribers(self):
        self.post({"kind": "alert", "title": "Federal rule", "send_push": "yes", "publish_at": "2026-12-01 08:00"})
        due = datetime(2026, 12, 1, 16, 5, tzinfo=dt_tz.utc)
        with patch("django.utils.timezone.now", return_value=due), patch(
            "talks.integrations._post", return_value=(200, {"id": "p"})
        ) as post, self.settings(ONESIGNAL_APP_ID="app", ONESIGNAL_REST_API_KEY="key"), patch("talks.management.commands.cron.call_command"):
            call_command("cron", stdout=StringIO())
            call_command("cron", stdout=StringIO())
        self.assertEqual(post.call_count, 1)
        self.assertEqual(post.call_args[0][2]["filters"][0]["key"], "alerts")


class SigninSheetTests(TestCase):
    def setUp(self):
        cache.clear()

    def send(self, pdf=b"%PDF-1.7 test", **extra):
        return self.client.post("/api/signin-sheets/", _json.dumps({
            "pdf_base64": base64.b64encode(pdf).decode(), "supervisor_email": "Lead@Plant.com", "supervisor_name": "Ana Ruiz",
            "talk_title": "Heat Stroke Is a 911 Call", "held_on": "2027-06-07", "attendee_count": 9, "has_group_photo": True, **extra,
        }), content_type="application/json")

    def test_monday_minute_sheet_is_labeled_and_tagged(self):
        with patch("talks.ghl.configured", return_value=True), patch("talks.ghl.upload_media", return_value="https://files.example/s.pdf"), \
             patch("talks.ghl.upsert_contact", return_value="c1") as contact, patch("talks.ghl.add_note") as note:
            self.send(program="monday-minute", issue=7)
        sheet = SigninSheet.objects.get()
        self.assertEqual((sheet.program, sheet.issue), ("monday-minute", 7))
        self.assertIn("monday-minute", contact.call_args.args[3])
        self.assertIn("Program: Monday Minute", note.call_args.args[1])
        self.send(program="something-else")
        self.assertEqual(SigninSheet.objects.latest("pk").program, "zero-harm-weekly")

    def test_sheet_goes_to_ghl_and_local_copy_is_cleared(self):
        with patch("talks.ghl.configured", return_value=True), patch("talks.ghl.upload_media", return_value="https://files.example/sheet.pdf"), \
             patch("talks.ghl.upsert_contact", return_value="c1"), patch("talks.ghl.add_note") as note:
            r = self.send()
        self.assertTrue(r.json()["saved_to_ghl"])
        sheet = SigninSheet.objects.get()
        self.assertEqual(sheet.status, "synced")
        self.assertEqual(bytes(sheet.pdf), b"")
        self.assertIn("https://files.example/sheet.pdf", note.call_args[0][1])
        self.assertIn("Group photo included", note.call_args[0][1])

    def test_sheet_is_kept_for_retry_when_ghl_fails(self):
        from talks.ghl import GhlError
        with patch("talks.ghl.configured", return_value=True), patch("talks.ghl.upload_media", side_effect=GhlError("down")):
            self.send()
        sheet = SigninSheet.objects.get()
        self.assertEqual(sheet.status, "failed")
        self.assertTrue(bytes(sheet.pdf).startswith(b"%PDF"))

    def test_rejects_non_pdf(self):
        self.assertEqual(self.send(pdf=b"GIF89a").status_code, 400)


# ---- OTIS knowledge base, weather, suggestions ---------------------------------------------------
from .models import KbEntry, TalkSuggestion
from .weather import heat_index_f


class OtisKbTests(TestCase):
    def test_kb_has_entries_and_only_released_talks(self):
        talk = ToolboxTalk.objects.get(issue=1)
        talk.body_md = "Intro text.\n\n## Talk it through with your crew\n\n1. Clear the area."
        talk.save()
        with patch("django.utils.timezone.now", return_value=talk.send_at + timedelta(minutes=1)):
            items = self.client.get("/api/otis/kb/").json()["items"]
        self.assertTrue(any(i["title"] == "Someone is hurt or in danger right now" for i in items))
        talk_items = [i for i in items if i["issue"]]
        self.assertEqual({i["issue"] for i in talk_items}, {1})
        self.assertTrue(any("Clear the area" in i["text"] and "Talk it through" in i["title"] for i in talk_items))

    def test_config(self):
        self.assertEqual(self.client.get("/api/otis/config/").json()["model"], "QWEN3_1_7B")


class WeatherTests(TestCase):
    def test_heat_index_matches_nws_table(self):
        self.assertEqual(heat_index_f(90, 60), 100)  # NWS chart: 90°F at 60% RH is about 100°F
        self.assertEqual(heat_index_f(96, 40), 101)

    def test_rounds_location_and_rejects_non_us(self):
        self.assertEqual(self.client.get("/api/weather/?lat=51.5&lon=-0.12").status_code, 404)
        with patch("talks.weather.conditions", return_value={"temp_f": 70}) as c:
            self.client.get("/api/weather/?lat=36.1699412&lon=-115.1398296")
        self.assertEqual(c.call_args[0], (36.17, -115.14))


class SuggestionTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_suggestion_saved_and_validated(self):
        ok = self.client.post("/api/suggestions/", _json.dumps({"topic": "Battery charging stations", "email": "", "may_contact": True}),
                              content_type="application/json")
        self.assertEqual(ok.status_code, 201)
        self.assertFalse(TalkSuggestion.objects.get().may_contact)  # no email, so no contact
        self.assertEqual(self.client.post("/api/suggestions/", _json.dumps({"topic": "x"}), content_type="application/json").status_code, 400)


# ---- Zero Hour --------------------------------------------------------------------------------------
from .models import Episode
from zoneinfo import ZoneInfo

from .zero_hour import next_thursday_5am, sync_episodes

PACIFIC_TZ = ZoneInfo("America/Los_Angeles")


class ZeroHourTests(TestCase):
    def test_four_episodes_loaded_and_released_on_schedule(self):
        self.assertEqual(Episode.objects.count(), 4)
        at = datetime(2026, 11, 7, tzinfo=dt_tz.utc)
        with patch("django.utils.timezone.now", return_value=at):
            eps = self.client.get("/api/episodes/").json()["episodes"]
        self.assertEqual([e["number"] for e in eps], [3, 2, 1])  # EP 04 releases Nov 12
        self.assertEqual(eps[-1]["chain"][0], "An E-stop stops the motion. It does not lock out the energy.")
        self.assertTrue(eps[-1]["video_url"].endswith("_720p.mp4"))

    def test_sync_links_new_episode_on_hold_and_prefers_newest_version(self):
        files = [
            {"name": "ZH_E05_LinkedIn_1x1_v1.mp4", "contentType": "video/mp4", "url": "https://x/v1.mp4", "encodedFormats": ["cts-aaa_720p.mp4"]},
            {"name": "ZH_E05_LinkedIn_1x1_v2.mp4", "contentType": "video/mp4", "url": "https://x/v2.mp4", "encodedFormats": ["cts-bbb_720p.mp4"],
             "thumbnail": {"url": "https://x/t.jpg"}},
            {"name": "ZH_E05_Huddle_Card.pdf", "contentType": "application/pdf", "url": "https://x/card.pdf"},
            {"name": "ZHA_OSHA300_L01_FINAL.mp4", "contentType": "video/mp4", "url": "https://x/other.mp4"},
        ]
        log = sync_episodes(files)
        ep = Episode.objects.get(number=5)
        self.assertTrue(ep.needs_details)
        self.assertIn("cts-bbb_720p", ep.video_url)
        self.assertEqual(ep.card_pdf_url, "https://x/card.pdf")
        self.assertIn("on hold", log[0])
        self.assertEqual(ep.release_at.astimezone(PACIFIC_TZ).weekday(), 3)

    def test_next_thursday(self):
        t = next_thursday_5am(datetime(2026, 11, 6, 20, tzinfo=dt_tz.utc))  # a Friday
        self.assertEqual(t, datetime(2026, 11, 12, 13, 0, tzinfo=dt_tz.utc))

    def test_huddle_cards_feed_otis(self):
        with patch("django.utils.timezone.now", return_value=datetime(2026, 11, 7, tzinfo=dt_tz.utc)):
            items = self.client.get("/api/otis/kb/").json()["items"]
        self.assertTrue(any("E-stop" in i["text"] and i.get("episode") == 1 for i in items))


# ---- API v2 (Django Ninja): OTIS on-device manifest, KB sync, feedback -----------------------------
import json as _json

from .models import OtisFeedback, OtisModelRelease, OtisRollout


def _release(**kw):
    base = dict(key="qwen3-1.7b-mlx", label="OTIS standard", platform="ios", backend="mlx", min_memory_gb=6,
                model_url="https://cdn.example.com/m.pte", tokenizer_url="https://cdn.example.com/t.json",
                tokenizer_config_url="https://cdn.example.com/tc.json", size_mb=1100, active=True)
    base.update(kw)
    return OtisModelRelease.objects.create(**base)


class ApiV2ManifestTests(TestCase):
    def setUp(self):
        cache.clear()

    def manifest(self, **device):
        body = {"platform": "ios", "memory_gb": 8, "app_version": "1.0.0", "backends": ["mlx", "xnnpack"]}
        body.update(device)
        return self.client.post("/api/v2/otis/manifest", _json.dumps(body), content_type="application/json")

    def test_builtin_model_by_memory(self):
        big = self.manifest(memory_gb=8).json()
        self.assertTrue(big["enabled"])
        self.assertEqual(big["model"]["builtin"], "QWEN3_1_7B")
        self.assertIsNone(big["model"]["files"])
        small = self.manifest(platform="android", memory_gb=4, backends=["xnnpack"]).json()
        self.assertEqual(small["model"]["builtin"], "QWEN3_0_6B")

    def test_pinned_release_matches_platform_backend_and_memory(self):
        _release()
        _release(key="qwen3-0.6b-mlx", min_memory_gb=0, size_mb=450, label="OTIS compact")
        _release(key="qwen3-1.7b-android", platform="android", backend="xnnpack")
        self.assertEqual(self.manifest(memory_gb=8).json()["model"]["key"], "qwen3-1.7b-mlx")
        self.assertEqual(self.manifest(memory_gb=4).json()["model"]["key"], "qwen3-0.6b-mlx")
        # An app build without MLX never gets the MLX file; it falls back to the built-in model.
        self.assertEqual(self.manifest(backends=["xnnpack"]).json()["model"]["builtin"], "QWEN3_1_7B")
        android = self.manifest(platform="android", backends=["vulkan", "xnnpack"]).json()["model"]
        self.assertEqual((android["key"], android["files"]["model_url"]), ("qwen3-1.7b-android", "https://cdn.example.com/m.pte"))

    def test_inactive_release_ignored(self):
        _release(active=False)
        self.assertEqual(self.manifest().json()["model"]["builtin"], "QWEN3_1_7B")

    def test_platform_switch_and_min_version(self):
        OtisRollout.objects.create(android_enabled=False, min_app_version="1.2.0", message="Back Monday.")
        off = self.manifest(platform="android", backends=["xnnpack"]).json()
        self.assertEqual((off["enabled"], off["message"], off["model"]), (False, "Back Monday.", None))
        old = self.manifest(app_version="1.1.9").json()
        self.assertEqual((old["enabled"], old["update_required"]), (False, True))
        self.assertTrue(self.manifest(app_version="1.10.0").json()["enabled"])

    def test_rejects_bad_platform(self):
        self.assertEqual(self.manifest(platform="windows").status_code, 422)

    def test_app_config_theme_switch(self):
        self.assertEqual(self.client.get("/api/v2/app/config").json(), {"theme": "auto"})
        with self.settings(APP_THEME="default"):
            self.assertEqual(self.client.get("/api/v2/app/config").json(), {"theme": "default"})
        with self.settings(APP_THEME="christmas"):  # a typo must not break the app
            self.assertEqual(self.client.get("/api/v2/app/config").json(), {"theme": "auto"})

    def test_kb_version_and_304(self):
        man = self.manifest(kb_version="").json()["kb"]
        self.assertTrue(man["changed"])
        res = self.client.get("/api/v2/otis/kb")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["version"], man["version"])
        self.assertEqual(res["ETag"], f'"{man["version"]}"')
        self.assertEqual(self.client.get("/api/v2/otis/kb", HTTP_IF_NONE_MATCH=res["ETag"]).status_code, 304)
        self.assertFalse(self.manifest(kb_version=man["version"]).json()["kb"]["changed"])
        KbEntry.objects.create(title="New entry", body="Something new.")
        cache.clear()
        self.assertEqual(self.client.get("/api/v2/otis/kb", HTTP_IF_NONE_MATCH=res["ETag"]).status_code, 200)

    def test_feedback_saved_and_switch(self):
        post = lambda body: self.client.post("/api/v2/otis/feedback", _json.dumps(body), content_type="application/json")
        self.assertEqual(post({"helpful": True, "source_ids": ["k1", "t3-1"], "platform": "ios", "lang": "es"}).status_code, 201)
        fb = OtisFeedback.objects.get()
        self.assertEqual((fb.helpful, fb.source_ids, fb.question, fb.lang), (True, ["k1", "t3-1"], "", "es"))
        self.assertEqual(post({"helpful": False, "question": "x" * 501}).status_code, 422)
        OtisRollout.objects.create(feedback_enabled=False)
        self.assertEqual(post({"helpful": False}).status_code, 403)

    def test_openapi_schema(self):
        from django.contrib.auth import get_user_model
        self.assertEqual(self.client.get("/api/v2/openapi.json").status_code, 302)  # docs are for signed-in staff
        self.client.force_login(get_user_model().objects.create_user("staff", password="x", is_staff=True))
        paths = self.client.get("/api/v2/openapi.json").json()["paths"]
        self.assertTrue({"/api/v2/otis/manifest", "/api/v2/otis/kb", "/api/v2/otis/feedback"} <= set(paths))


class OshaKbTests(TestCase):
    def test_general_industry_entries_seeded_and_cited(self):
        osha = KbEntry.objects.filter(source__startswith="OSHA 29 CFR")
        self.assertGreaterEqual(osha.count(), 39)
        for e in osha:
            self.assertRegex(e.source, r"^OSHA 29 CFR 19(10|04)\.", e.title)
            self.assertLessEqual(len(e.body.split()), 130, f"{e.title} is too long for OTIS to quote")

    def test_safety_critical_wording(self):
        body = lambda t: KbEntry.objects.get(title=t).body
        self.assertIn("Verify isolation", body("Lockout/tagout: the steps"))
        self.assertIn("removed by the person who put it on", body("Lockout/tagout: whose lock comes off"))
        self.assertIn("do not go in after them", body("Permit-required confined spaces"))
        self.assertIn("no gloves", body("Gloves, and when not to wear them"))
        self.assertTrue(body("Reporting a death or serious injury to OSHA").startswith("If someone is hurt, call 911 first."))
        self.assertIn("OSHA General Industry", body("What OTIS is"))

    def test_otis_finds_osha_answers(self):
        items = self.client.get("/api/otis/kb/").json()["items"]
        self.assertTrue(any(i["source"] == "OSHA 29 CFR 1910.147(d)" for i in items))


class EarlyUnlockTests(TestCase):
    """Only the next few talks open early, and never with last week's answer."""

    BODY = "Intro.\n\n## Talk it through with your crew\n\n1. Do the thing.\n\n## Last week’s answer\n\nThe answer is X.\n\n## What OSHA says\n\nRule."

    def setUp(self):
        cache.clear()
        self.now = datetime(2026, 11, 10, 12, 0, tzinfo=dt_tz.utc)  # before issue #1's Jan 3, 2027 send
        ToolboxTalk.objects.filter(issue__in=[1, 2, 3, 10]).update(body_md=self.BODY)

    def listed(self):
        with patch("django.utils.timezone.now", return_value=self.now):
            return self.client.get("/api/talks/").json()["talks"]

    def test_only_the_next_two_open_early(self):
        talks = self.listed()
        self.assertEqual(sorted(t["issue"] for t in talks), [1, 2])
        self.assertTrue(all(t["early"] for t in talks))
        with patch("django.utils.timezone.now", return_value=self.now):
            self.assertEqual(self.client.get("/api/talks/2/").status_code, 200)
            self.assertEqual(self.client.get("/api/talks/3/").status_code, 404)
            self.assertEqual(self.client.get("/api/talks/10/").status_code, 404)

    def test_early_talks_hide_last_weeks_answer_until_their_send(self):
        talk = self.listed()[0]
        self.assertNotIn("Last week", talk["body_md"])
        self.assertNotIn("The answer is X", talk["body_md"])
        self.assertIn("## What OSHA says", talk["body_md"])
        self.now = ToolboxTalk.objects.get(issue=1).send_at + timedelta(minutes=1)
        released = next(t for t in self.listed() if t["issue"] == 1)
        self.assertFalse(released["early"])
        self.assertIn("The answer is X", released["body_md"])

    def test_spanish_and_otis_hide_it_too(self):
        ToolboxTalk.objects.filter(issue=1).update(
            spanish_status="approved", title_es="T", crew_question_es="¿Q?",
            body_md_es="Intro.\n\n## Respuesta de la semana pasada\n\nLa respuesta es X.\n\n## Lo que dice OSHA\n\nRegla.")
        talk = next(t for t in self.listed() if t["issue"] == 1)
        self.assertNotIn("La respuesta es X", talk["es"]["body_md"])
        self.assertIn("Lo que dice OSHA", talk["es"]["body_md"])
        with patch("django.utils.timezone.now", return_value=self.now):
            items = self.client.get("/api/otis/kb/").json()["items"]
        text = " ".join(i["title"] + " " + i["text"] for i in items if i.get("issue"))
        self.assertNotIn("The answer is X", text)
        self.assertNotIn("La respuesta es X", text)
        self.assertIn("Do the thing", text)

    def test_held_or_unpublished_talks_dont_use_up_a_slot(self):
        ToolboxTalk.objects.filter(issue=1).update(needs_review=True)
        self.assertEqual(sorted(t["issue"] for t in self.listed()), [2, 3])

    @override_settings(TALKS_EARLY_COUNT=0)
    def test_count_zero_waits_for_sunday(self):
        self.assertEqual(self.listed(), [])

    @override_settings(TALKS_UNLOCK_EARLY=False)
    def test_switch_off_waits_for_sunday(self):
        self.assertEqual(self.listed(), [])

    def test_early_talk_does_not_push_early(self):
        out = StringIO()
        with patch("django.utils.timezone.now", return_value=self.now):
            call_command("send_talk_push", "--dry-run", stdout=out)
        self.assertIn("No talk is due", out.getvalue())

    def test_answer_section_parser(self):
        from .models import without_last_weeks_answer
        self.assertEqual(without_last_weeks_answer("## Last week's answer\n\nX\n\n## Next\n\nY"), "## Next\n\nY")
        self.assertEqual(without_last_weeks_answer("Intro only."), "Intro only.")
        self.assertEqual(without_last_weeks_answer(""), "")
        self.assertEqual(without_last_weeks_answer("A\n\n## La respuesta de la semana anterior\n\nZ"), "A")
        # Headings a translator or a hand edit could plausibly produce must be caught too.
        for heading in ("## La respuesta de la última semana", "### Last week's answer", "##Last week’s answer", "**Last week's answer**"):
            self.assertEqual(without_last_weeks_answer(f"A\n\n{heading}\n\nSECRET\n\n## Next\n\nY"), "A\n\n## Next\n\nY", heading)
        self.assertEqual(without_last_weeks_answer(f"A\n## Last week's answer\nSECRET"), "A")

    def test_an_empty_talk_does_not_use_up_an_early_slot(self):
        upcoming = list(ToolboxTalk.objects.filter(send_at__gt=timezone.now()).order_by("send_at")[:3])
        self.assertEqual(len(upcoming), 3)
        ToolboxTalk.objects.filter(pk=upcoming[0].pk).update(body_md="")
        early = sorted(t.pk for t in ToolboxTalk.objects.available() if t.early)
        self.assertEqual(early, sorted([upcoming[1].pk, upcoming[2].pk]))


class OtisRegulationTests(TestCase):
    def test_kb_includes_official_regulation_text(self):
        items = self.client.get("/api/otis/kb/").json()["items"]
        regs = [i for i in items if i["id"].startswith("r")]
        self.assertTrue(regs)
        self.assertTrue(all(i["source"].startswith("29 CFR 19") for i in regs))
        self.assertTrue(any(i["source"].startswith("29 CFR 1910.147(") for i in regs))
        self.assertLessEqual(sum(len(i["text"]) for i in regs), 250_000)

    def test_paused_entry_leaves_otis(self):
        entry = KbEntry.objects.filter(source__startswith="OSHA 29 CFR 1910.147").first()
        entry.published, entry.paused_reason = False, "OSHA changed 29 CFR 1910.147"
        entry.save()
        titles = {i["title"] for i in self.client.get("/api/otis/kb/").json()["items"]}
        self.assertNotIn(entry.title, titles)


class ConfigTests(TestCase):
    def test_railway_healthcheck_host_is_allowed(self):
        from django.conf import settings
        self.assertIn("healthcheck.railway.app", settings.ALLOWED_HOSTS)
        self.assertEqual(self.client.get("/api/health/", HTTP_HOST="healthcheck.railway.app").status_code, 200)

    def test_client_ip_trusts_only_the_proxy_hop(self):
        from django.test import RequestFactory
        from .views import _client_ip
        rf = RequestFactory()
        self.assertEqual(_client_ip(rf.get("/", HTTP_X_FORWARDED_FOR="1.1.1.1, 203.0.113.7")), "203.0.113.7")
        self.assertEqual(_client_ip(rf.get("/", REMOTE_ADDR="10.0.0.5")), "10.0.0.5")

    def test_big_responses_are_gzipped_and_revalidate(self):
        res = self.client.get("/api/otis/kb/", HTTP_ACCEPT_ENCODING="gzip")
        self.assertEqual(res["Content-Encoding"], "gzip")
        self.assertLess(len(res.content), 120_000)
        plain = self.client.get("/api/talks/")
        self.assertEqual(self.client.get("/api/talks/", HTTP_IF_NONE_MATCH=plain["ETag"]).status_code, 304)


# ---- Welcome sign-in: one row per email, GoHighLevel lead, owner alerts, removal ------------------
import datetime as dt
import importlib

from usage.models import AppOpen

from . import owner_alerts
from .ghl import GhlError
from .integrations import sync_signup_to_ghl
from .models import OwnerDigest, SignupPhone, SignupRemoval, split_name

INSTALL = "3f6c1c1e-8a55-4a0e-9d7b-1c2d3e4f5a6b"
CONSENT = "You'll get Zero Harm Weekly by email each week. Unsubscribe anytime."
GHL_ON = dict(SECRET_KEY="test", GHL_PRIVATE_TOKEN="token", GHL_LOCATION_ID="loc", OWNER_ALERT_EMAIL="owner@example.com")


class FakeGhl:
    """Stands in for GoHighLevel. Records every call made through integrations._post and ghl.request; `down` makes
    both fail the way a dead network does. Nothing here touches the network."""

    def __init__(self):
        self.down, self.calls = False, []
        self.tags = []          # the tags on contact lead1 before the app touches it
        self.upsert_tags = None  # set to a list to send the tags back in the upsert answer instead
        self.known = set()       # emails that have a contact (made by an upsert, or set by a test)
        self.fail = {}           # (method, path) -> (status, body): GoHighLevel answers that call with an error
        self.hook = None         # called before each tag call; lets a test act while the sync is running

    def post(self, url, headers, payload, timeout=10):
        path = url.replace("https://services.leadconnectorhq.com", "")
        self.calls.append(("POST", path, payload, timeout))
        if self.down:
            return 0, {"error": "timed out"}
        if path == "/contacts/upsert":
            self.known.add(payload["email"])
            contact = {"id": "lead1", **({"tags": self.upsert_tags} if self.upsert_tags is not None else {})}
            return 200, {"contact": contact}
        if self.hook:
            self.hook()
        return 200, {}

    def request(self, method, path, query=None, body=None, raw=None, content_type="application/json", timeout=30):
        self.calls.append((method, path, body or query, timeout))
        if self.down:
            raise GhlError(f"{method} {path} -> timed out")
        if (method, path) in self.fail:
            status, text = self.fail[(method, path)]
            raise GhlError(f"{method} {path} -> {status}: {text}", status=status, body=text)
        if path == "/contacts/upsert":
            return {"contact": {"id": "owner1"}}
        if method == "GET" and path == "/contacts/search/duplicate":
            return {"contact": {"id": "lead1", "tags": list(self.tags)} if query["email"] in self.known else None}
        if method == "GET" and path.startswith("/contacts/"):
            return {"contact": {"id": path.split("/")[2], "tags": list(self.tags)}}
        return {}

    def to(self, path, method="POST"):
        return [c for c in self.calls if c[1] == path and c[0] == method]

    @property
    def emails(self):
        return [c[2] for c in self.to("/conversations/messages")]


class GhlTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.ghl = FakeGhl()
        for target, fake in (("talks.integrations._post", self.ghl.post), ("talks.ghl.request", self.ghl.request)):
            patcher = patch(target, side_effect=fake)
            patcher.start()
            self.addCleanup(patcher.stop)

    def signup(self, **body):
        return self.client.post("/api/signups/", {"email": "jane@plant.com", **body}, content_type="application/json")

    def remove(self, install_id=INSTALL):
        return self.client.post("/api/signups/remove/", {"install_id": install_id}, content_type="application/json")


@override_settings(**GHL_ON)
class WelcomeSignupTests(GhlTestCase):
    def test_new_and_repeat_emails_get_the_same_answer_with_one_row(self):
        first = self.signup(name="Jane van Doe", source="welcome", install_id=INSTALL, consent=CONSENT)
        self.assertEqual((first.status_code, first.json()), (200, {"ok": True}))
        row = AppSignup.objects.get()
        self.assertEqual((row.first_name, row.last_name, row.source, row.consent_text), ("Jane", "van Doe", "welcome", CONSENT))
        self.assertIsNotNone(row.consent_at)
        self.assertEqual([len(h) for h in row.phones.values_list("install_hash", flat=True)], [64])
        created = row.created_at

        again = self.signup(email=" JANE@Plant.com ", name="Jane Doe", company="Acme Foods", wants_offers=True, source="settings", install_id=INSTALL)
        self.assertEqual((again.status_code, again.json()), (200, {"ok": True}))
        row = AppSignup.objects.get()  # still one row
        self.assertEqual((row.email, row.last_name, row.company, row.wants_offers), ("jane@plant.com", "Doe", "Acme Foods", True))
        self.assertEqual((row.source, row.created_at), ("welcome", created))  # where and when they first signed up stay
        self.assertEqual(row.phones.count(), 1)

    def test_database_refuses_a_second_row_for_the_same_email(self):
        from django.db import IntegrityError, transaction
        AppSignup.objects.create(email="jane@plant.com")
        with self.assertRaises(IntegrityError), transaction.atomic():
            AppSignup.objects.create(email="Jane@Plant.com")

    def test_name_split_and_old_clients(self):
        self.assertEqual(split_name("Jane"), ("Jane", ""))
        self.assertEqual(split_name("  Jane   van  Doe "), ("Jane", "van Doe"))
        self.assertEqual(split_name(""), ("", ""))
        self.signup(first_name="Bo", company="Dock Co")  # an app version from before the welcome screen
        row = AppSignup.objects.get()
        self.assertEqual((row.first_name, row.last_name, row.source, row.phones.count(), row.consent_at), ("Bo", "", "settings", 0, None))

    def test_bad_input(self):
        self.assertEqual(self.signup(email="nope").status_code, 400)
        self.assertEqual(self.client.post("/api/signups/", "[1]", content_type="application/json").status_code, 400)
        self.signup(install_id="short", source="somewhere", name="x" * 300)  # ignored or cut, never an error
        row = AppSignup.objects.get()
        self.assertEqual((row.phones.count(), row.source, len(row.first_name)), (0, "settings", 80))

    def test_lead_goes_to_ghl_with_last_name_and_tags(self):
        self.signup(name="Jane van Doe", company="Acme", wants_offers=True, source="welcome")
        upsert = self.ghl.to("/contacts/upsert")[0][2]
        self.assertEqual(upsert, {"locationId": "loc", "email": "jane@plant.com", "source": "Zero Harm app",
                                  "firstName": "Jane", "lastName": "van Doe", "companyName": "Acme"})
        self.assertNotIn("tags", upsert)  # tags sent with the upsert would replace the contact's other tags
        tags = self.ghl.to("/contacts/lead1/tags")[0][2]["tags"]
        self.assertEqual(tags, ["zero-harm-app", "zero-harm-weekly", "zero-harm-app-signup", "zero-harm-offers-optin"])
        row = AppSignup.objects.get()
        self.assertEqual(row.ghl_contact_id, "lead1")
        self.assertIsNotNone(row.ghl_synced_at)

    def test_offers_tag_only_when_opted_in_and_taken_off_on_a_repeat_without_it(self):
        self.signup(name="Jane Doe", wants_offers=True, install_id=INSTALL)
        self.signup(name="Jane Doe", wants_offers=False, install_id=INSTALL)
        self.assertEqual(self.ghl.to("/contacts/lead1/tags")[-1][2]["tags"], ["zero-harm-app", "zero-harm-weekly", "zero-harm-app-signup"])
        self.assertEqual(self.ghl.to("/contacts/lead1/tags", "DELETE")[0][2], {"tags": ["zero-harm-offers-optin"]})

    def test_owner_alert_once_for_a_new_email_never_for_repeats(self):
        self.signup(name="Jane Doe", company="Acme Foods", source="welcome")
        self.signup(name="Jane Doe")
        self.signup(name="Jane D")
        self.assertEqual(len(self.ghl.emails), 1)
        mail = self.ghl.emails[0]
        self.assertEqual((mail["type"], mail["contactId"], mail["subject"]), ("Email", "owner1", "New Zero Harm sign-up: Jane Doe"))
        for text in ("jane@plant.com", "Acme Foods", "the welcome screen", "Pacific", "<b>Sign-ups so far:</b> 1", "zero-harm-weekly"):
            self.assertIn(text, mail["html"])
        self.assertIsNotNone(AppSignup.objects.get().owner_alerted_at)
        # The owner's own contact: made once, tagged in a separate call, never marked as an app lead.
        owner = [c for c in self.ghl.calls if c[0] == "POST" and c[1] == "/contacts/upsert" and c[2].get("email") == "owner@example.com"]
        self.assertEqual([c[2] for c in owner], [{"locationId": "loc", "email": "owner@example.com"}])
        self.assertEqual(self.ghl.to("/contacts/owner1/tags")[0][2], {"tags": ["zero-harm-owner"]})
        self.assertEqual(owner_alerts.retry_signup_alerts(now=timezone.now() + timedelta(hours=1)), 0)
        self.assertEqual(len(self.ghl.emails), 1)

    def test_alert_escapes_what_the_person_typed(self):
        self.signup(name="<script>alert(1)</script> O'Neil", company="<img src=x onerror=1>&Co")
        html = self.ghl.emails[0]["html"]
        self.assertNotIn("<script>", html)
        self.assertNotIn("<img", html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt; O&#x27;Neil", html)
        self.assertIn("&lt;img src=x onerror=1&gt;&amp;Co", html)

    def test_signup_succeeds_when_ghl_is_down_and_the_cron_sends_the_alert_later(self):
        self.ghl.down = True
        self.assertEqual(self.signup(name="Jane Doe").status_code, 200)
        row = AppSignup.objects.get()
        self.assertEqual((row.ghl_synced_at, row.owner_alerted_at), (None, None))
        self.assertTrue(all(c[3] <= 5 for c in self.ghl.calls))  # short timeouts while the phone waits
        self.assertEqual(len(self.ghl.calls), 1)  # one try, then it gives up until the cron

        later = timezone.now() + timedelta(minutes=20)
        self.assertEqual(owner_alerts.retry_signup_alerts(now=later), 0)  # still down
        self.ghl.down = False
        self.assertEqual(owner_alerts.retry_signup_alerts(now=later), 1)
        self.assertEqual(owner_alerts.retry_signup_alerts(now=later), 0)
        self.assertEqual([m["subject"] for m in self.ghl.emails], ["New Zero Harm sign-up: Jane Doe"])
        call_command("sync_signups", stdout=StringIO())
        self.assertEqual(AppSignup.objects.get().ghl_contact_id, "lead1")

    def test_the_cron_itself_sends_what_was_missed(self):
        self.ghl.down = True
        self.signup(name="Jane Doe", install_id=INSTALL)
        self.ghl.down = False
        with patch("django.utils.timezone.now", return_value=timezone.now() + timedelta(minutes=20)), \
                patch("talks.management.commands.cron.call_command") as commands:
            out = StringIO()
            call_command("cron", stdout=out)
        self.assertIn("Owner alerts: 1 sign-up alerts sent late, 0 removals finished", out.getvalue())
        self.assertIn("owner_digest", [c[0][0] for c in commands.call_args_list])
        self.assertEqual(len(self.ghl.emails), 1)

    def test_cron_retry_leaves_old_and_brand_new_rows_alone(self):
        old = AppSignup.objects.create(email="old@plant.com")
        AppSignup.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=3))
        AppSignup.objects.create(email="new@plant.com")  # seconds old: the sign-up request may still be sending it
        self.assertEqual(owner_alerts.retry_signup_alerts(), 0)
        self.assertEqual(self.ghl.emails, [])

    def test_no_alerts_without_an_owner_address(self):
        with self.settings(OWNER_ALERT_EMAIL=""):
            self.assertEqual(self.signup(name="Jane Doe").status_code, 200)
            self.assertEqual(owner_alerts.retry_signup_alerts(now=timezone.now() + timedelta(hours=1)), 0)
            self.assertEqual(owner_alerts.send_due_digests(), [])
        self.assertEqual(self.ghl.emails, [])
        self.assertEqual(len(self.ghl.to("/contacts/upsert")), 1)  # the lead still went to GoHighLevel

    def test_nothing_is_sent_without_ghl_settings(self):
        with self.settings(GHL_PRIVATE_TOKEN=""):
            self.assertEqual(self.signup(name="Jane Doe").status_code, 200)
            self.assertFalse(sync_signup_to_ghl(AppSignup.objects.get()))
        self.assertEqual(self.ghl.calls, [])

    def test_a_crew_can_sign_in_together_on_one_network(self):
        with patch("talks.views.sync_signup_to_ghl", return_value=False):
            for i in range(30):
                self.assertEqual(self.signup(email=f"crew{i}@plant.com").status_code, 200)
            for _ in range(10):  # repeats of an email already here don't use up the limit
                self.assertEqual(self.signup(email="crew0@plant.com").status_code, 200)
            self.assertEqual(self.signup(email="one-too-many@plant.com").status_code, 429)
            self.assertEqual(self.signup(email="crew1@plant.com").status_code, 200)
        self.assertEqual(AppSignup.objects.count(), 30)


class MergeDuplicateSignupsTests(TestCase):
    def test_merge_keeps_the_earliest_row_and_the_ghl_id(self):
        merge = importlib.import_module("talks.migrations.0013_merge_duplicate_signups").merge_duplicate_signups
        from django.db import connection
        # The rule that stops duplicates came after the merge. Drop its index to make some; the test's rollback puts it back.
        with connection.cursor() as cursor:
            cursor.execute("DROP INDEX one_signup_per_email")
        synced = timezone.now()
        rows = [
            AppSignup.objects.create(email="Jane@Plant.com", source="zero-harm-app"),
            AppSignup.objects.create(email="jane@plant.com", first_name="Jane", company="Acme", ghl_contact_id="g1", ghl_synced_at=synced),
            AppSignup.objects.create(email="JANE@plant.com ", first_name="Janet", wants_offers=True, ghl_contact_id="g2"),
            AppSignup.objects.create(email="bo@dock.com", first_name="Bo", source="zero-harm-app"),
        ]
        for i, row in enumerate(rows):
            AppSignup.objects.filter(pk=row.pk).update(created_at=datetime(2026, 5, 1 + i, tzinfo=dt_tz.utc))
        self.assertEqual(merge(AppSignup), 2)
        self.assertEqual(merge(AppSignup), 0)  # safe to run again
        self.assertEqual(AppSignup.objects.count(), 2)
        jane = AppSignup.objects.get(email="jane@plant.com")
        self.assertEqual(jane.pk, rows[0].pk)
        self.assertEqual(jane.created_at, datetime(2026, 5, 1, tzinfo=dt_tz.utc))
        self.assertEqual((jane.first_name, jane.company, jane.ghl_contact_id, jane.ghl_synced_at, jane.wants_offers, jane.source),
                         ("Jane", "Acme", "g1", synced, True, "settings"))
        self.assertEqual(AppSignup.objects.get(email="bo@dock.com").source, "settings")


@override_settings(**GHL_ON)
class SignupRemoveTests(GhlTestCase):
    def test_remove_deletes_the_row_and_untags_the_contact(self):
        self.signup(name="Jane Doe", install_id=INSTALL, wants_offers=True)
        self.signup(email="bo@dock.com", name="Bo", install_id="another-phone-id")
        self.ghl.calls.clear()
        res = self.remove()
        self.assertEqual((res.status_code, res.json()), (200, {"ok": True}))
        self.assertEqual(list(AppSignup.objects.values_list("email", flat=True)), ["bo@dock.com"])
        self.assertEqual(self.ghl.to("/contacts/lead1/tags", "DELETE")[0][2],
                         {"tags": ["zero-harm-weekly", "zero-harm-offers-optin", "zero-harm-app-signup"]})
        self.assertEqual(self.ghl.to("/contacts/lead1/tags")[0][2], {"tags": ["zero-harm-removed"]})
        note = self.ghl.to("/contacts/lead1/notes")[0][2]["body"]
        self.assertIn("Removed their sign-up in the Zero Harm app on", note)
        self.assertIn(str(timezone.localdate().year), note)
        self.assertEqual([m["subject"] for m in self.ghl.emails], ["Zero Harm removal request: jane@plant.com"])
        self.assertFalse(SignupRemoval.objects.exists())  # nothing left to do, so nothing is kept

    def test_remove_always_answers_200(self):
        self.signup(name="Jane Doe", install_id=INSTALL)
        self.ghl.calls.clear()
        for body in ({"install_id": "some-other-phone"}, {"install_id": "x"}, {}, {"install_id": 12345678}):
            res = self.client.post("/api/signups/remove/", body, content_type="application/json")
            self.assertEqual((res.status_code, res.json()), (200, {"ok": True}))
        self.assertEqual(self.client.post("/api/signups/remove/", "not json", content_type="application/json").status_code, 200)
        self.assertEqual(AppSignup.objects.count(), 1)
        self.assertEqual(self.ghl.calls, [])

    def test_remove_is_kept_and_retried_when_ghl_is_down(self):
        self.signup(name="Jane Doe", install_id=INSTALL)
        self.ghl.calls.clear()
        self.ghl.down = True
        self.assertEqual(self.remove().status_code, 200)
        self.assertFalse(AppSignup.objects.exists())  # their data is gone from the app's server right away
        pending = SignupRemoval.objects.get()
        self.assertEqual((pending.email, pending.ghl_contact_id, pending.ghl_done_at), ("jane@plant.com", "lead1", None))
        self.assertTrue(all(c[3] <= 5 for c in self.ghl.calls))

        later = timezone.now() + timedelta(minutes=20)
        self.assertEqual(owner_alerts.retry_removals(now=later), 0)
        self.assertTrue(SignupRemoval.objects.exists())
        self.ghl.down = False
        self.ghl.calls.clear()
        self.assertEqual(owner_alerts.retry_removals(now=later), 1)
        self.assertFalse(SignupRemoval.objects.exists())
        self.assertEqual(len(self.ghl.to("/contacts/lead1/tags", "DELETE")), 1)
        self.assertEqual(len(self.ghl.emails), 1)

    def test_remove_before_the_lead_reached_ghl_only_tells_the_owner(self):
        self.ghl.down = True
        self.signup(name="Jane Doe", install_id=INSTALL)
        self.ghl.down = False
        self.ghl.calls.clear()
        self.remove()
        self.assertFalse(AppSignup.objects.exists())
        self.assertFalse(SignupRemoval.objects.exists())
        self.assertEqual(self.ghl.to("/contacts/lead1/tags", "DELETE"), [])
        self.assertIn("had not reached GoHighLevel", self.ghl.emails[0]["html"])
        call_command("sync_signups", stdout=StringIO())  # the deleted sign-up is never sent to GoHighLevel afterwards
        self.assertEqual([c for c in self.ghl.to("/contacts/upsert") if c[2]["email"] == "jane@plant.com"], [])

    def test_remove_rate_limit(self):
        for _ in range(5):
            self.assertEqual(self.remove().status_code, 200)
        self.assertEqual(self.remove().status_code, 429)


OTHER = "9b1d7c2e-0f44-4c6a-8e1f-aa00bb11cc22"  # another phone


@override_settings(**GHL_ON)
class SignupPhoneTests(GhlTestCase):
    """Every phone that signs up with an email is linked to it, and a phone can only remove itself."""

    def test_a_repeat_from_another_phone_links_it_and_changes_nothing_else(self):
        self.signup(name="Jane Doe", install_id=INSTALL, consent=CONSENT)
        consent_at = AppSignup.objects.get().consent_at
        again = self.signup(name="Mallory Evil", company="Evil Co", wants_offers=True, consent="something else", install_id=OTHER)
        self.assertEqual((again.status_code, again.json()), (200, {"ok": True}))
        row = AppSignup.objects.get()
        self.assertEqual((row.first_name, row.last_name, row.consent_text, row.consent_at, row.wants_offers),
                         ("Jane", "Doe", CONSENT, consent_at, False))
        self.assertEqual(row.company, "Evil Co")  # it was blank, so it is filled in
        self.assertEqual(row.phones.count(), 2)
        self.signup(company="Other Co", install_id=OTHER)  # once linked, the second phone counts as theirs too
        self.signup(name="Someone Else", company="Old App Co")  # an old app version that sends no phone id: blanks only
        row = AppSignup.objects.get()
        self.assertEqual((row.first_name, row.company, row.phones.count()), ("Jane", "Other Co", 2))

    def test_another_phone_can_only_remove_itself(self):
        self.signup(name="Jane Doe", install_id=INSTALL)
        self.signup(name="Mallory", install_id=OTHER)
        self.ghl.calls.clear()
        res = self.remove(OTHER)
        self.assertEqual((res.status_code, res.json()), (200, {"ok": True}))
        row = AppSignup.objects.get()  # Jane is still signed up
        self.assertEqual(row.phones.count(), 1)
        self.assertEqual((self.ghl.calls, SignupRemoval.objects.count()), ([], 0))  # GoHighLevel untouched, no alert
        self.assertEqual(self.remove(OTHER).json(), {"ok": True})  # again: nothing left for that phone
        self.assertTrue(AppSignup.objects.exists())

        self.remove(INSTALL)  # her own (last) phone removes the sign-up
        self.assertFalse(AppSignup.objects.exists())
        self.assertEqual(len(self.ghl.to("/contacts/lead1/tags", "DELETE")), 1)
        self.assertEqual([m["subject"] for m in self.ghl.emails], ["Zero Harm removal request: jane@plant.com"])

    def test_old_single_phone_column_is_copied_into_the_links(self):
        copy_phones = importlib.import_module("talks.migrations.0016_copy_signup_phones").copy_phones
        jane, bo = AppSignup.objects.create(email="jane@plant.com"), AppSignup.objects.create(email="bo@dock.com")
        old_rows = [(jane.pk, "h" * 64, jane.created_at), (bo.pk, "g" * 64, bo.created_at)]

        class OldAppSignup:  # the sign-up model as it was before 0017, with its install_hash column
            class objects:
                @staticmethod
                def exclude(**kw):
                    return type("Q", (), {"values_list": staticmethod(lambda *a: old_rows)})()

        self.assertEqual(copy_phones(OldAppSignup, SignupPhone), 2)
        self.assertEqual(copy_phones(OldAppSignup, SignupPhone), 0)  # safe to run again
        self.assertEqual(list(jane.phones.values_list("install_hash", flat=True)), ["h" * 64])
        self.assertEqual(jane.phones.get().created_at, jane.created_at)


@override_settings(**GHL_ON)
class RemovalTagTests(GhlTestCase):
    def test_tags_the_contact_already_had_are_noted_and_left_on(self):
        self.ghl.tags = ["zero-harm-weekly", "customer"]
        self.signup(name="Jane Doe", install_id=INSTALL, wants_offers=True)
        self.assertEqual(self.ghl.to("/contacts/lead1", "GET")[0][1], "/contacts/lead1")  # the upsert answer had no tags
        self.assertEqual(AppSignup.objects.get().ghl_had_tags, ["zero-harm-weekly"])
        self.ghl.calls.clear()
        self.remove()
        self.assertEqual(self.ghl.to("/contacts/lead1/tags", "DELETE")[0][2], {"tags": ["zero-harm-offers-optin", "zero-harm-app-signup"]})
        self.assertIn("They had zero-harm-weekly before signing up in the app, so those were left on.", self.ghl.emails[0]["html"])

    def test_tags_in_the_upsert_answer_are_used_and_an_offers_tag_they_had_stays_on_a_repeat(self):
        self.ghl.upsert_tags = ["zero-harm-offers-optin"]
        self.signup(name="Jane Doe", install_id=INSTALL)
        self.assertEqual(self.ghl.to("/contacts/lead1", "GET"), [])
        self.assertEqual(AppSignup.objects.get().ghl_had_tags, ["zero-harm-offers-optin"])
        self.signup(name="Jane Doe", install_id=INSTALL, wants_offers=False)
        self.assertEqual(self.ghl.to("/contacts/lead1/tags", "DELETE"), [])  # their own offers tag is not the app's to take off
        self.remove()
        self.assertEqual(self.ghl.to("/contacts/lead1/tags", "DELETE")[0][2], {"tags": ["zero-harm-weekly", "zero-harm-app-signup"]})

    def test_signing_up_again_after_a_removal_takes_the_removed_tag_off(self):
        self.ghl.tags = ["zero-harm-removed"]
        self.signup(name="Jane Doe", install_id=INSTALL)
        tag_calls = [c for c in self.ghl.calls if c[1] == "/contacts/lead1/tags"]
        self.assertEqual([(c[0], c[2]["tags"][-1]) for c in tag_calls], [("POST", "zero-harm-app-signup"), ("DELETE", "zero-harm-removed")])
        self.assertIsNotNone(AppSignup.objects.get().ghl_synced_at)
        self.signup(name="Jane Doe", install_id=INSTALL)  # only checked on the first sync
        self.assertEqual([c[2] for c in self.ghl.to("/contacts/lead1/tags", "DELETE")].count({"tags": ["zero-harm-removed"]}), 1)


@override_settings(**GHL_ON)
class PendingRemovalTests(GhlTestCase):
    def test_signing_up_again_calls_off_a_removal_still_waiting_for_ghl(self):
        self.ghl.tags = ["zero-harm-weekly"]
        self.signup(name="Jane Doe", install_id=INSTALL)
        self.ghl.down = True
        self.remove()
        self.assertEqual(SignupRemoval.objects.get().ghl_had_tags, ["zero-harm-weekly"])
        self.ghl.down = False
        self.ghl.calls.clear()
        self.assertEqual(self.signup(name="Jane Doe", install_id=INSTALL).status_code, 200)
        self.assertFalse(SignupRemoval.objects.exists())
        self.assertEqual(owner_alerts.retry_removals(now=timezone.now() + timedelta(minutes=20)), 0)
        self.assertEqual(self.ghl.to("/contacts/lead1/tags", "DELETE"), [])
        self.assertEqual(AppSignup.objects.get().ghl_had_tags, ["zero-harm-weekly"])  # what it knew carries over

    def test_finish_removal_leaves_ghl_alone_when_the_email_is_signed_up_again(self):
        AppSignup.objects.create(email="jane@plant.com", ghl_contact_id="lead1")
        removal = SignupRemoval.objects.create(email="Jane@Plant.com", ghl_contact_id="lead1")
        self.assertTrue(owner_alerts.finish_removal(removal))
        self.assertEqual([c for c in self.ghl.calls if c[1].startswith("/contacts/lead1")], [])
        self.assertIn("have since signed up again", self.ghl.emails[0]["html"])
        self.assertFalse(SignupRemoval.objects.exists())


@override_settings(**GHL_ON)
class RemovalFailureTests(GhlTestCase):
    def pending(self, **kw):
        return SignupRemoval.objects.create(email="jane@plant.com", name="Jane Doe", ghl_contact_id="lead1", ghl_had_tags=[], **kw)

    def test_a_contact_ghl_no_longer_has_counts_as_done(self):
        for status, text in ((404, "Contact not found"), (400, "Contact with id lead1 not found"), (422, '{"message":"lead1 is not valid"}')):
            self.ghl.fail = {("DELETE", "/contacts/lead1/tags"): (status, text)}
            self.assertTrue(owner_alerts.finish_removal(self.pending()), status)
        self.assertFalse(SignupRemoval.objects.exists())
        self.ghl.fail = {("DELETE", "/contacts/lead1/tags"): (400, "Bad request")}  # a 400 that is not about the contact
        self.assertFalse(owner_alerts.finish_removal(self.pending()))
        self.assertEqual(SignupRemoval.objects.get().attempts, 1)

    def test_gives_up_after_7_days_and_asks_the_owner_to_finish_by_hand(self):
        self.ghl.fail = {("DELETE", "/contacts/lead1/tags"): (500, "Internal error")}
        removal = self.pending()
        self.assertEqual(owner_alerts.retry_removals(now=timezone.now() + timedelta(days=6)), 0)
        self.assertTrue(SignupRemoval.objects.exists())
        self.assertEqual(owner_alerts.retry_removals(now=timezone.now() + timedelta(days=7, minutes=1)), 1)
        self.assertFalse(SignupRemoval.objects.filter(pk=removal.pk).exists())  # their name and email are not kept
        mail, = self.ghl.emails
        self.assertEqual(mail["subject"], "Zero Harm removal needs finishing by hand: jane@plant.com")
        for text in ("lead1", "zero-harm-weekly, zero-harm-offers-optin, zero-harm-app-signup", "zero-harm-removed", "yourself"):
            self.assertIn(text, mail["html"])

    def test_stuck_removals_do_not_hold_up_newer_ones(self):
        self.ghl.fail = {("DELETE", "/contacts/stuck/tags"): (500, "Internal error")}
        now = timezone.now() + timedelta(minutes=30)
        for _ in range(25):
            SignupRemoval.objects.create(email="stuck@plant.com", ghl_contact_id="stuck", last_tried_at=now - timedelta(minutes=5))
        newer = SignupRemoval.objects.create(email="jane@plant.com", ghl_contact_id="lead1")
        self.assertEqual(owner_alerts.retry_removals(now=now), 1)
        self.assertFalse(SignupRemoval.objects.filter(pk=newer.pk).exists())
        self.assertEqual(SignupRemoval.objects.filter(attempts=1).count(), 19)  # it took one of the 20 places


@override_settings(**GHL_ON)
class RemovalDuringSyncTests(GhlTestCase):
    def test_a_removal_during_the_tagging_takes_the_new_tags_back_off(self):
        self.ghl.hook = lambda: AppSignup.objects.filter(email="jane@plant.com").delete()
        self.assertEqual(self.signup(name="Jane Doe", install_id=INSTALL).status_code, 200)  # no error for the phone
        self.ghl.hook = None
        self.assertEqual(self.ghl.to("/contacts/lead1/tags", "DELETE")[0][2], {"tags": ["zero-harm-weekly", "zero-harm-app-signup"]})
        self.assertEqual(self.ghl.emails, [])

    def test_a_row_removed_before_the_tagging_is_not_tagged(self):
        row = AppSignup.objects.create(email="jane@plant.com")
        AppSignup.objects.filter(pk=row.pk).delete()
        self.assertFalse(sync_signup_to_ghl(row))
        self.assertEqual(self.ghl.to("/contacts/lead1/tags"), [])

    def test_a_removal_with_no_contact_id_looks_the_email_up(self):
        self.ghl.known.add("jane@plant.com")
        self.ghl.tags = ["zero-harm-weekly"]
        removal = SignupRemoval.objects.create(email="jane@plant.com", name="Jane Doe")
        self.assertTrue(owner_alerts.finish_removal(removal))
        self.assertEqual(self.ghl.to("/contacts/search/duplicate", "GET")[0][2], {"locationId": "loc", "email": "jane@plant.com"})
        self.assertEqual([c for c in self.ghl.to("/contacts/upsert") if c[2]["email"] == "jane@plant.com"], [])  # looking never makes one
        self.assertEqual(self.ghl.to("/contacts/lead1/tags", "DELETE")[0][2], {"tags": ["zero-harm-offers-optin", "zero-harm-app-signup"]})
        self.assertEqual(self.ghl.to("/contacts/lead1/tags")[0][2], {"tags": ["zero-harm-removed"]})


@override_settings(**GHL_ON)
class OwnerDigestTests(GhlTestCase):
    DAY = dt.date(2026, 11, 9)
    MORNING = datetime(2026, 11, 10, 15, 5, tzinfo=dt_tz.utc)  # 7:05 AM Pacific on Nov 10

    def opened(self, phone, day, platform="ios", city="", region="", country=""):
        AppOpen.objects.create(install_hash=phone, day=day, platform=platform, city=city, region=region, country=country)

    def signed_up(self, email, when):
        AppSignup.objects.filter(pk=AppSignup.objects.create(email=email).pk).update(created_at=when)

    def a_busy_day(self):
        self.opened("old", dt.date(2026, 11, 1))
        self.opened("old", self.DAY)  # active that day, but not new
        self.opened("a", self.DAY, "ios", "Houston", "Texas", "US")
        self.opened("b", self.DAY, "android", "Houston", "Texas", "US")
        self.opened("c", self.DAY, "android", "", "Nevada", "US")
        self.opened("d", self.DAY, "ios")
        self.opened("a", dt.date(2026, 11, 10))  # a later open by the same phone is not a second download
        self.signed_up("in@plant.com", datetime(2026, 11, 9, 8, 30, tzinfo=dt_tz.utc))      # 12:30 AM Pacific on the 9th
        self.signed_up("late@plant.com", datetime(2026, 11, 10, 7, 30, tzinfo=dt_tz.utc))   # 11:30 PM Pacific on the 9th
        self.signed_up("before@plant.com", datetime(2026, 11, 9, 7, 30, tzinfo=dt_tz.utc))  # 11:30 PM Pacific on the 8th
        OwnerDigest.objects.create(day=dt.date(2026, 11, 7))
        OwnerDigest.objects.create(day=dt.date(2026, 11, 8))

    def test_numbers_for_one_pacific_day(self):
        self.a_busy_day()
        n = owner_alerts.digest_numbers(self.DAY)
        self.assertEqual((n["new_phones"], n["ios"], n["android"]), (4, 2, 2))
        self.assertEqual((n["places"], n["unknown_places"], n["other_places"]), ([("Houston, Texas", 2), ("Nevada", 1)], 1, 0))
        self.assertEqual((n["signups"], n["active"], n["total_phones"], n["total_signups"]), (2, 5, 5, 3))

    def test_at_most_8_places_then_the_rest_together(self):
        for i in range(11):
            self.opened(f"p{i}", self.DAY, city=f"Town {chr(65 + i)}", region="Ohio", country="US")
        n = owner_alerts.digest_numbers(self.DAY)
        self.assertEqual((len(n["places"]), n["other_places"]), (8, 3))

    def test_sent_once_a_day_after_7_pacific(self):
        self.a_busy_day()
        self.assertEqual(owner_alerts.send_due_digests(now=self.MORNING - timedelta(minutes=10)), [])  # 6:55 AM: too early
        self.assertEqual(self.ghl.emails, [])
        self.assertEqual(owner_alerts.send_due_digests(now=self.MORNING), ["Owner summary for 2026-11-09: sent"])
        self.assertEqual(owner_alerts.send_due_digests(now=self.MORNING + timedelta(minutes=15)), [])
        mail, = self.ghl.emails
        self.assertEqual(mail["subject"], "Zero Harm yesterday: 4 new phones, 2 sign-ups")
        for text in ("4 (2 iPhone, 2 Android)", "Houston, Texas (2), Nevada (1), unknown (1)", "<b>Phones active that day:</b> 5",
                     "<b>All sign-ups so far:</b> 3", "calendar day in Pacific time", "switched off the anonymous usage count are not included"):
            self.assertIn(text, mail["html"])
        row = OwnerDigest.objects.get(day=self.DAY)
        self.assertEqual((row.sent, row.new_phones, row.signups), (True, 4, 2))

    def test_nothing_is_sent_for_an_empty_day(self):
        self.opened("old", dt.date(2026, 11, 1))
        self.opened("old", self.DAY)  # an active phone, but no new phones and no sign-ups
        OwnerDigest.objects.create(day=dt.date(2026, 11, 7))
        OwnerDigest.objects.create(day=dt.date(2026, 11, 8))
        self.assertEqual(owner_alerts.send_due_digests(now=self.MORNING), ["Owner summary for 2026-11-09: nothing to report"])
        self.assertEqual(self.ghl.calls, [])
        self.assertFalse(OwnerDigest.objects.get(day=self.DAY).sent)
        self.assertEqual(owner_alerts.send_due_digests(now=self.MORNING), [])

    def test_catches_up_at_most_3_missed_days(self):
        for back in range(1, 8):  # a new phone on each of the last 7 days, and no summary sent for any of them
            self.opened(f"p{back}", dt.date(2026, 11, 10) - timedelta(days=back))
        owner_alerts.send_due_digests(now=self.MORNING)
        self.assertEqual([m["subject"] for m in self.ghl.emails],
                         ["Zero Harm Nov 7: 1 new phone, 0 sign-ups", "Zero Harm Nov 8: 1 new phone, 0 sign-ups", "Zero Harm yesterday: 1 new phone, 0 sign-ups"])
        self.assertEqual(OwnerDigest.objects.count(), 3)

    def test_a_failed_send_is_tried_again(self):
        self.a_busy_day()
        self.ghl.down = True
        self.assertEqual(owner_alerts.send_due_digests(now=self.MORNING), ["Owner summary for 2026-11-09: FAILED, will retry"])
        self.assertFalse(OwnerDigest.objects.filter(day=self.DAY).exists())
        self.ghl.down = False
        with patch("django.utils.timezone.now", return_value=self.MORNING + timedelta(minutes=15)):
            out = StringIO()
            call_command("owner_digest", stdout=out)
        self.assertIn("2026-11-09: sent", out.getvalue())
        self.assertEqual(len(self.ghl.emails), 1)


import json  # noqa: E402

from .models import SignupPhone, SignupRemoval  # noqa: E402


class ReviewRoundTwoTests(TestCase):
    """Second review: unclaimed rows, probing, address-hopping, alert floods, removal racing a sign-up."""

    def setUp(self):
        cache.clear()

    def post(self, path, body, **extra):
        return self.client.post(path, json.dumps(body), content_type="application/json", **extra)

    def test_a_row_with_no_phone_cannot_be_claimed_and_removed(self):
        AppSignup.objects.create(email="old@plant.com", first_name="Old")  # signed up before phones were recorded
        self.post("/api/signups/", {"email": "old@plant.com", "install_id": "attacker-phone-0001"})
        self.assertFalse(SignupPhone.objects.exists())
        self.post("/api/signups/remove/", {"install_id": "attacker-phone-0001"})
        self.assertTrue(AppSignup.objects.filter(email="old@plant.com").exists())

    def test_the_answer_does_not_say_whether_an_email_signed_up(self):
        first = self.post("/api/signups/", {"email": "a@plant.com"})
        again = self.post("/api/signups/", {"email": "a@plant.com"})
        self.assertEqual((first.status_code, first.content), (again.status_code, again.content))

    @override_settings(NUM_PROXIES=1)
    def test_hopping_addresses_in_one_ipv6_network_is_still_limited(self):
        codes = [self.post("/api/signups/remove/", {"install_id": "zh-phone-00001"}, HTTP_X_FORWARDED_FOR=f"2001:db8:1:1::{i:x}").status_code
                 for i in range(8)]
        self.assertEqual(codes.count(429), 3)
        self.assertFalse(any("2001:db8" in str(k) for k in cache._cache.keys()))

    @override_settings(OWNER_ALERT_EMAIL="owner@x.com")
    def test_instant_alerts_are_capped_each_hour(self):
        from . import owner_alerts
        with patch.object(owner_alerts, "send", return_value=True) as send:
            for i in range(owner_alerts.ALERTS_PER_HOUR + 5):
                owner_alerts.alert_signup(AppSignup.objects.create(email=f"p{i}@plant.com"))
        self.assertEqual(send.call_count, owner_alerts.ALERTS_PER_HOUR)
        self.assertFalse(AppSignup.objects.filter(owner_alerted_at__isnull=True).exists())  # the cron won't send them later

    def test_a_removal_called_off_meanwhile_does_nothing(self):
        from . import owner_alerts
        removal = SignupRemoval.objects.create(email="a@plant.com", ghl_contact_id="c1")
        SignupRemoval.objects.filter(pk=removal.pk).delete()
        with patch.object(owner_alerts, "_untag") as untag:
            self.assertTrue(owner_alerts.finish_removal(removal))
        untag.assert_not_called()
