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
        self.assertEqual(ok.status_code, 201)
        self.assertEqual(AppSignup.objects.get().email, "crew@example.com")
        bad = self.client.post("/api/signups/", {"email": "nope"}, content_type="application/json")
        self.assertEqual(bad.status_code, 400)

    def test_signup_rate_limit(self):
        for _ in range(5):
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

    def send(self, pdf=b"%PDF-1.7 test"):
        return self.client.post("/api/signin-sheets/", _json.dumps({
            "pdf_base64": base64.b64encode(pdf).decode(), "supervisor_email": "Lead@Plant.com", "supervisor_name": "Ana Ruiz",
            "talk_title": "Heat Stroke Is a 911 Call", "held_on": "2027-06-07", "attendee_count": 9, "has_group_photo": True,
        }), content_type="application/json")

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
    """Talks with their text open in the app before their Sunday newsletter, with sign-in; others wait."""

    def setUp(self):
        cache.clear()
        self.now = datetime(2026, 11, 10, 12, 0, tzinfo=dt_tz.utc)  # before issue #1's Jan 3, 2027 send
        talk = ToolboxTalk.objects.get(issue=10)
        talk.body_md = "Intro.\n\n## Talk it through with your crew\n\n1. Do the thing."
        talk.save()

    def listed(self):
        with patch("django.utils.timezone.now", return_value=self.now):
            return self.client.get("/api/talks/").json()["talks"]

    def test_talk_with_text_is_available_early(self):
        talks = self.listed()
        self.assertEqual([t["issue"] for t in talks], [10])
        self.assertTrue(talks[0]["early"])
        self.assertEqual(talks[0]["send_at"], ToolboxTalk.objects.get(issue=10).send_at.isoformat())
        with patch("django.utils.timezone.now", return_value=self.now):
            self.assertEqual(self.client.get("/api/talks/10/").status_code, 200)
            self.assertEqual(self.client.get("/api/talks/11/").status_code, 404)  # no text yet

    def test_held_for_review_stays_hidden(self):
        ToolboxTalk.objects.filter(issue=10).update(needs_review=True)
        self.assertEqual(self.listed(), [])

    @override_settings(TALKS_UNLOCK_EARLY=False)
    def test_switch_off_waits_for_sunday(self):
        self.assertEqual(self.listed(), [])

    def test_released_talk_is_not_early(self):
        self.now = ToolboxTalk.objects.get(issue=10).send_at + timedelta(minutes=1)
        self.assertFalse(self.listed()[0]["early"])

    def test_early_talk_does_not_push_early(self):
        out = StringIO()
        with patch("django.utils.timezone.now", return_value=self.now):
            call_command("send_talk_push", "--dry-run", stdout=out)
        self.assertIn("No talk is due", out.getvalue())
