import html
import json
import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase, override_settings

from monday.moderation import COMMUNITY_RULES

from .views import CONTACT_EMAIL, EFFECTIVE_DATE

# Every outside party the data inventory names. The privacy page has to say each one and what it gets.
THIRD_PARTIES = [
    "GoHighLevel",
    "OneSignal",
    "Railway",
    "Anthropic",
    "National Weather Service",
    "Hugging Face",
    "DB-IP",
    "Apple",
    "Google",
]


class LegalPageTests(SimpleTestCase):
    def page(self, path):
        res = self.client.get(path)
        self.assertEqual(res.status_code, 200, path)
        return res, res.content.decode()

    def visible(self, body):
        """The text a reader sees: no HTML comments, tags or entities."""
        body = re.sub(r"<!--.*?-->", "", body, flags=re.S)
        body = re.sub(r"<style.*?</style>", "", body, flags=re.S)
        return html.unescape(re.sub(r"<[^>]+>", " ", body))

    def test_both_pages_with_and_without_the_slash(self):
        for path in ("/privacy/", "/privacy", "/terms/", "/terms"):
            res, body = self.page(path)
            self.assertIn(CONTACT_EMAIL, body)
            self.assertIn(f"Effective date:</strong> {EFFECTIVE_DATE}", body)
            self.assertIn("Last updated:", body)
            self.assertIn("public", res["Cache-Control"])
            self.assertIn("max-age=3600", res["Cache-Control"])
            self.assertNotIn("noindex", body)
            self.assertNotIn("noindex", res.get("X-Robots-Tag", ""))

    def test_no_scripts_or_outside_resources(self):
        for path in ("/privacy/", "/terms/"):
            res, body = self.page(path)
            self.assertNotRegex(body, r"(?i)<script")
            self.assertNotRegex(body, r'(?i)<(link|img|iframe)[^>]+(src|href)="https?://')
            self.assertIn("default-src 'none'", res["Content-Security-Policy"])

    def test_only_get(self):
        self.assertEqual(self.client.post("/privacy/").status_code, 405)

    def test_privacy_names_every_third_party(self):
        _, body = self.page("/privacy/")
        text = self.visible(body)
        for name in THIRD_PARTIES:
            self.assertIn(name, text, name)
        self.assertIn("No data is sent to DB-IP", text)
        self.assertIn("do not sell personal information", text)

    def test_privacy_covers_the_required_points(self):
        text = self.visible(self.page("/privacy/")[1])
        for phrase in ("Remove my info", "within 30 days", "under 16", "unsubscribe", "400 days", "hashed",
                       "signature", "photo", "stay on the phone", "California"):
            self.assertIn(phrase, text, phrase)

    def test_dates_and_support_email_are_the_ones_published(self):
        self.assertEqual(EFFECTIVE_DATE, "November 13, 2026")
        self.assertEqual(CONTACT_EMAIL, "jamil@trainovations.com")
        # The store build's support email (Settings > Contact support, Delete my data) must be the one the pages name.
        eas = Path(__file__).resolve().parents[2] / "eas.json"
        if eas.exists():  # not in the backend's Docker image
            build = json.loads(eas.read_text())["build"]["production"]["env"]
            self.assertEqual(build["EXPO_PUBLIC_SUPPORT_EMAIL"], CONTACT_EMAIL)
        for path in ("/privacy/", "/terms/"):
            text = self.visible(self.page(path)[1])
            self.assertIn(f"mailto:{CONTACT_EMAIL}", self.page(path)[1])
            self.assertIn(f"Effective date: {EFFECTIVE_DATE}", " ".join(text.split()))

    def test_privacy_covers_support_tickets_crash_reports_and_removal(self):
        text = " ".join(self.visible(self.page("/privacy/")[1]).split())
        for phrase in ("Report a problem", "My reports", "Report this answer", "error screen", "Crash reports",
                       "phone model", "system version", "app version", "install id", "OK to reply to me",
                       "not sent to an AI", "cannot connect a crash report to you", "We got your request",
                       "phone that made your sign-up", "Reporting a problem with the app to OTIS", "Include my question"):
            self.assertIn(phrase, text, phrase)
        self.assertIn(f"after {settings.SUPPORT_CRASH_KEEP_DAYS} days", text)
        # The old promise with no exceptions must not come back.
        self.assertNotIn("are not sent to us or anyone else", text)
        self.assertNotIn("last phone linked", text)

    @override_settings(SUPPORT_CRASH_KEEP_DAYS=30)
    def test_crash_retention_follows_the_setting(self):
        self.assertIn("after 30 days", " ".join(self.visible(self.page("/privacy/")[1]).split()))

    def test_terms_say_reports_do_not_go_to_the_employer(self):
        text = " ".join(self.visible(self.page("/terms/")[1]).split())
        self.assertIn("They do not go to your employer", text)
        self.assertIn("problem reports", text)

    def test_terms_carry_the_community_rules_and_key_lines(self):
        text = self.visible(self.page("/terms/")[1])
        for rule in COMMUNITY_RULES:
            self.assertIn(rule, text)
        for phrase in ("Zero tolerance", "within 24 hours", "call 911", "not affiliated with", "Nevada", "can be wrong"):
            self.assertIn(phrase, text, phrase)

    def test_plain_punctuation_and_hidden_review_notes(self):
        for name in ("privacy", "terms"):
            body = self.page(f"/{name}/")[1]
            self.assertNotIn("—", body)  # no em dashes
            # The review notes are template comments: they stay in the repo and never reach a browser, not even in view-source.
            self.assertNotIn("LAWYER REVIEW", body)
            source = (Path(__file__).parent / "templates" / "legal" / f"{name}.html").read_text()
            self.assertIn("{# [LAWYER REVIEW]", source)
            self.assertNotIn("<!--", source)
