import html
import re
from pathlib import Path

from django.test import SimpleTestCase

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
