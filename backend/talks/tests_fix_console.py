"""Tests for the fixes to the content console (talks/console.py) and the Spanish draft (talks/translate.py)."""
import io
import json
import os
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone as dt_tz
from unittest.mock import patch

from django.db import connection
from django.test import override_settings
from django.utils import timezone

from . import translate
from .models import FeedItem, KbEntry, TalkSuggestion, ToolboxTalk
from .tests_console import KEY, ConsoleCase

BEFORE_ANY_TALK = datetime(2026, 11, 10, 12, 0, tzinfo=dt_tz.utc)  # issue 1 sends 2027-01-03 19:59 UTC
ISSUE_1_SENDS = datetime(2027, 1, 3, 19, 59, tzinfo=dt_tz.utc)
WITH_ANSWER = "## The talk\n\nMain text.\n\n## Last week’s answer\n\nThe answer was B.\n\n## Crew question\n\nWhat now?"


@contextmanager
def at(moment):
    """Runs the block as if it were this moment. Edits made inside get this time as their updated_at."""
    with patch("django.utils.timezone.now", return_value=moment):
        yield


class TalkEditorKeepsStoredTextTests(ConsoleCase):
    """The editor loads body_md and sends it back, so the console must hand out the stored text, not the shortened
    text phones get before a talk's send time."""

    def setUp(self):
        super().setUp()
        ToolboxTalk.objects.filter(issue=2).update(body_md=WITH_ANSWER)

    def test_talk_not_sent_yet_comes_back_with_last_weeks_answer(self):
        with at(BEFORE_ANY_TALK):
            got = self.call("get", "talks/2/").json()
            listed = next(t for t in self.call("get", "talks/").json()["talks"] if t["issue"] == 2)
        self.assertTrue(got["early"])
        self.assertEqual(got["body_md"], WITH_ANSWER)
        self.assertEqual(listed["body_md"], WITH_ANSWER)

    def test_fixing_one_word_keeps_last_weeks_answer(self):
        with at(BEFORE_ANY_TALK):
            loaded = self.call("get", "talks/2/").json()["body_md"]
            r = self.call("patch", "talks/2/", {"body_md": loaded.replace("Main text.", "Main text, typo fixed.")})
        self.assertEqual(r.status_code, 200)
        saved = ToolboxTalk.objects.get(issue=2).body_md
        self.assertIn("Main text, typo fixed.", saved)
        self.assertIn("The answer was B.", saved)
        self.assertEqual(r.json()["body_md"], saved)

    def test_phones_still_do_not_get_the_answer_early(self):
        with at(BEFORE_ANY_TALK):
            public = self.client.get("/api/talks/2/").json()
        self.assertTrue(public["early"])
        self.assertNotIn("answer was B", public["body_md"])
        self.assertIn("Main text.", public["body_md"])

    def test_talk_without_text_still_answers_null(self):
        self.assertIsNone(self.call("get", "talks/3/").json()["body_md"])  # same shape the console already reads


class ContentVersionCountsEarlyTalksTests(ConsoleCase):
    """The app lists talks opened early, so a change to one of those must change the version phones poll."""

    def version(self):
        return self.client.get("/api/content-version/").json()["version"]

    def listed(self):
        return [t["issue"] for t in self.client.get("/api/talks/").json()["talks"]]

    def test_edit_and_unpublish_of_an_early_talk_change_the_version(self):
        ToolboxTalk.objects.filter(issue=1).update(body_md="Text.")
        with at(BEFORE_ANY_TALK):
            self.assertEqual(self.listed(), [1])  # open early
            v1 = self.version()
            self.assertEqual(v1, self.version())
        with at(BEFORE_ANY_TALK + timedelta(minutes=1)):
            self.call("patch", "talks/1/", {"title": "Corrected title", "body_md": "CORRECTED safety step."})
            self.assertEqual(self.client.get("/api/talks/1/").json()["title"], "Corrected title")
            v2 = self.version()
        self.assertNotEqual(v1, v2)
        with at(BEFORE_ANY_TALK + timedelta(minutes=2)):
            self.call("patch", "talks/1/", {"published": False})
            self.assertEqual(self.listed(), [])
            self.assertNotEqual(v2, self.version())

    def test_a_talk_opening_early_changes_the_version(self):
        with at(BEFORE_ANY_TALK):
            v1 = self.version()
            ToolboxTalk.objects.filter(issue=1).update(body_md="Text.")  # now it has text, so it opens early
            self.assertEqual(self.listed(), [1])
            self.assertNotEqual(v1, self.version())

    def test_an_early_talk_reaching_its_send_time_still_changes_the_version(self):
        # The same talk stays listed, but phones now get last week's answer and lose the "early" mark.
        ToolboxTalk.objects.filter(issue=1).update(body_md=WITH_ANSWER)
        with at(ISSUE_1_SENDS - timedelta(minutes=1)):
            self.assertEqual(self.listed(), [1])
            before = self.version()
        with at(ISSUE_1_SENDS + timedelta(minutes=1)):
            self.assertEqual(self.listed(), [1])
            self.assertNotEqual(before, self.version())

    def test_edit_of_a_talk_phones_cannot_see_leaves_the_version_alone(self):
        with at(BEFORE_ANY_TALK):
            v1 = self.version()
        with at(BEFORE_ANY_TALK + timedelta(minutes=1)):
            self.call("patch", "talks/30/", {"title": "Not open yet"})
            self.assertEqual(v1, self.version())


class SpanishDraftSavesOnlyItsOwnFieldsTests(ConsoleCase):
    """The Claude call can take two minutes. Whatever else was saved on the talk meanwhile must survive."""

    REPLY = {"content": [{"type": "text", "text": json.dumps(
        {"title": "Título", "story_title": "Historia", "crew_question": "¿Y ahora?", "body_md": "Texto."})}]}

    def test_push_mark_and_edits_made_during_the_call_are_kept(self):
        talk = ToolboxTalk.objects.get(issue=1)  # the copy the console or admin loaded before the call
        sent = datetime(2027, 1, 3, 20, 0, tzinfo=dt_tz.utc)
        was_updated = talk.updated_at

        def claude(req, timeout=None):  # stands in for api.anthropic.com; nothing leaves this machine
            ToolboxTalk.objects.filter(issue=1).update(push_sent_at=sent, title="Edited meanwhile", ghl_template_id="t-9")
            return io.BytesIO(json.dumps(self.REPLY).encode())

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key-not-real"}), \
             patch("urllib.request.urlopen", side_effect=claude) as urlopen:
            translate.draft_spanish(talk)
        self.assertEqual(urlopen.call_count, 1)
        saved = ToolboxTalk.objects.get(issue=1)
        self.assertEqual(saved.push_sent_at, sent)  # or the Sunday push would go out a second time
        self.assertEqual(saved.title, "Edited meanwhile")
        self.assertEqual(saved.ghl_template_id, "t-9")
        self.assertEqual((saved.title_es, saved.story_title_es, saved.crew_question_es, saved.body_md_es, saved.spanish_status),
                         ("Título", "Historia", "¿Y ahora?", "Texto.", "draft"))
        self.assertGreater(saved.updated_at, was_updated)  # the draft still counts as an edit


class BadInputIsRefusedClearlyTests(ConsoleCase):
    """Input the database or Python can't take gets a 400 that names the field, not the catch-all 500."""

    def refused(self, r, word, status=400):
        self.assertEqual(r.status_code, status, r.content[:200])
        self.assertIn(word, r.json()["error"])

    def test_dates_too_far_out_to_convert(self):
        for value in ("9999-12-31T23:59", "0001-01-01T00:00+14:00"):
            self.refused(self.call("patch", "talks/2/", {"send_at": value}), "send_at")
            self.refused(self.call("patch", "episodes/1/", {"release_at": value}), "release_at")
            self.refused(self.call("post", "feed/", {"kind": "alert", "title": "T", "publish_at": value}), "publish_at")
            self.refused(self.call("post", "feed/", {"kind": "alert", "title": "T", "expires_at": value}), "expires_at")
        self.assertEqual(FeedItem.objects.count(), 0)

    def test_text_the_database_cannot_store(self):
        before = KbEntry.objects.count()
        self.refused(self.call("patch", "talks/2/", {"body_md": "abc \u0000 def"}), "body_md")
        self.refused(self.call("patch", "talks/2/", {"title": "bad \ud83e surrogate"}), "title")
        self.refused(self.call("post", "kb/", {"title": "nul \u0000", "body": "b"}), "title")
        self.refused(self.call("patch", "episodes/1/", {"checks": ["Lock it", "Try \u0000 it"]}), "checks")
        self.refused(self.call("patch", "episodes/1/", {"questions": ["half \udc00 emoji"]}), "questions")
        self.assertEqual(KbEntry.objects.count(), before)
        self.assertEqual(ToolboxTalk.objects.get(issue=2).body_md, "")
        # A whole emoji and accented text are ordinary text and still save.
        ok = self.call("patch", "talks/2/", {"title": "Cuidado ⚠️ 🧤 señal"})
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ToolboxTalk.objects.get(issue=2).title, "Cuidado ⚠️ 🧤 señal")

    def test_issue_number_larger_than_the_database_holds(self):
        s = TalkSuggestion.objects.create(topic="Battery charging")
        self.refused(self.call("patch", f"suggestions/{s.pk}/", {"used_in_issue": 3000000000}), "used_in_issue")
        self.refused(self.call("patch", f"suggestions/{s.pk}/", {"used_in_issue": 99999999999999999999999}), "used_in_issue")
        self.assertIsNone(TalkSuggestion.objects.get(pk=s.pk).used_in_issue)
        self.assertEqual(self.call("patch", f"suggestions/{s.pk}/", {"used_in_issue": 2147483647}).status_code, 200)

    def raw(self, text):
        return self.client.patch("/api/console/talks/2/", data=text, content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {KEY}")

    def test_json_python_cannot_read(self):
        self.refused(self.raw("[" * 200000), "JSON")  # nested too deep
        self.refused(self.raw('{"title": %s}' % ("9" * 5000)), "JSON")  # a number with more digits than Python reads

    @override_settings(DATA_UPLOAD_MAX_MEMORY_SIZE=2000)
    def test_body_over_the_upload_limit(self):
        self.refused(self.call("patch", "talks/2/", {"body_md": "x" * 5000}), "too large", status=413)
        self.assertEqual(ToolboxTalk.objects.get(issue=2).body_md, "")


class LockoutTests(ConsoleCase):
    def wrong(self, **headers):
        return self.call("get", "talks/", key="guess", **headers).status_code

    def test_lock_lasts_the_hour_the_message_says(self):
        for _ in range(10):
            self.assertEqual(self.wrong(), 401)
        now = timezone.now()
        with patch("django.core.cache.backends.db.tz_now", return_value=now + timedelta(minutes=30)):
            r = self.call("get", "talks/", key="guess")
            self.assertEqual(r.status_code, 429)  # the count used to be gone 5 minutes after the last wrong key
            self.assertIn("hour", r.json()["error"])
        with patch("django.core.cache.backends.db.tz_now", return_value=now + timedelta(minutes=61)):
            self.assertEqual(self.wrong(), 401)

    def test_a_slow_guesser_is_still_counted(self):
        # Nine wrong keys, then a tenth 20 minutes later: all inside one hour, so the eleventh is refused.
        for _ in range(9):
            self.assertEqual(self.wrong(), 401)
        now = timezone.now()
        with patch("django.core.cache.backends.db.tz_now", return_value=now + timedelta(minutes=20)):
            self.assertEqual(self.wrong(), 401)
            self.assertEqual(self.wrong(), 429)

    def test_right_key_is_never_locked_out_by_wrong_ones(self):
        for _ in range(10):
            self.assertEqual(self.wrong(), 401)
        self.assertEqual(self.wrong(), 429)
        self.assertEqual(self.call("get", "talks/").status_code, 200)
        self.assertEqual(self.wrong(), 429)  # and using the right key does not reset the count for wrong ones

    def test_counts_the_caller_railway_names_not_the_edge_hop(self):
        # Production shape: the edge writes the caller in X-Real-IP and appends its own, changing, address last.
        for i in range(10):
            self.assertEqual(self.wrong(HTTP_X_REAL_IP="203.0.113.7", HTTP_X_FORWARDED_FOR=f"203.0.113.7, 10.250.0.{i}"), 401)
        self.assertEqual(self.wrong(HTTP_X_REAL_IP="203.0.113.7", HTTP_X_FORWARDED_FOR="203.0.113.7, 10.250.0.99"), 429)
        # Another caller who happens to come through the same edge hop is not locked.
        self.assertEqual(self.wrong(HTTP_X_REAL_IP="198.51.100.2", HTTP_X_FORWARDED_FOR="198.51.100.2, 10.250.0.99"), 401)

    def test_ipv6_caller_cannot_dodge_by_changing_address_inside_their_64(self):
        for i in range(1, 11):
            self.assertEqual(self.wrong(HTTP_X_FORWARDED_FOR=f"2001:db8:1:1::{i:x}"), 401)
        self.assertEqual(self.wrong(HTTP_X_FORWARDED_FOR="2001:db8:1:1:aaaa:bbbb:cccc:dddd"), 429)
        self.assertEqual(self.wrong(HTTP_X_REAL_IP="2001:db8:1:1::77", HTTP_X_FORWARDED_FOR="2001:db8:1:1::77, 10.250.0.1"), 429)
        self.assertEqual(self.wrong(HTTP_X_FORWARDED_FOR="2001:db8:1:2::1"), 401)  # the neighbouring /64 is someone else

    def test_no_readable_address_in_the_cache(self):
        self.assertEqual(self.wrong(HTTP_X_FORWARDED_FOR="203.0.113.7"), 401)
        with connection.cursor() as cursor:
            cursor.execute("SELECT cache_key FROM zeroharm_cache")
            keys = [row[0] for row in cursor.fetchall()]
        self.assertTrue(any("console-fail:" in k for k in keys), keys)
        self.assertFalse(any("203.0.113.7" in k for k in keys), keys)

    def test_wrong_key_is_logged_with_the_callers_address(self):
        with self.assertLogs("talks.console", "WARNING") as logs:
            self.wrong(HTTP_X_REAL_IP="203.0.113.7", HTTP_X_FORWARDED_FOR="203.0.113.7, 10.250.0.1")
        self.assertIn("203.0.113.7", logs.output[0])
        self.assertNotIn("10.250.0.1", logs.output[0])


class BroadcastRouteTests(ConsoleCase):
    def send(self, route):
        return self.call("post", "broadcast/", {"audience": "offers", "heading": "H", "message": "M", "route": route, "dry_run": True})

    def test_route_number_must_be_plain_digits(self):
        for route in ("/talk/٣", "/monday/７", "/alert/१२"):  # digits from other scripts: no screen matches them
            self.assertEqual(self.send(route).status_code, 400, route)
        r = self.send("/monday/7")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["detail"]["data"]["route"], "/monday/7")
