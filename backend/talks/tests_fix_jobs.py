"""Tests for the background jobs: the 15-minute cron, calls out to OneSignal and GoHighLevel, and the retries.

Nothing here leaves the machine: OneSignal and GoHighLevel are replaced by stand-ins (one of them a small server on
this machine's own loopback address, for the test that needs a really slow answer), or urllib itself is made to fail
the way a dropped connection does."""
import datetime as dt
import http.client
import http.server
import json
import ssl
import threading
import time
import uuid
from io import StringIO
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.core.cache import cache, caches
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db.models import F, QuerySet
from django.test import TestCase, override_settings
from django.utils import timezone

from monday.models import MondayEvalRun, MondayLock
from regs.models import RegChange, RegSection
from talks import ghl, integrations, owner_alerts, zero_hour
from talks.ghl import GhlError
from talks.management.commands import cron
from talks.models import AppSignup, Episode, FeedItem, GhlSync, SigninSheet, TalkSuggestion, ToolboxTalk

GHL_ON = dict(SECRET_KEY="test", GHL_PRIVATE_TOKEN="token", GHL_LOCATION_ID="loc", OWNER_ALERT_EMAIL="")
PUSH_ON = dict(ONESIGNAL_APP_ID="app", ONESIGNAL_REST_API_KEY="key")
INSTALL = "7c1f3a52-0d7e-4a6b-9a3c-5e2f1b8d4c90"
CRON = "talks.management.commands.cron"


class Reply:
    """What urllib hands back for an answer that did arrive."""

    def __init__(self, body=b"{}", status=200):
        self.body, self.status = body, status

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def half_read():
    reply = Reply()
    reply.read = lambda: (_ for _ in ()).throw(http.client.IncompleteRead(b"{\"id\": ", 90))
    return reply


# The ways an answer can go wrong after the request has left: none of them is a URLError.
BROKEN = {
    "closed without answering": dict(side_effect=http.client.RemoteDisconnected("Remote end closed connection without response")),
    "connection reset": dict(side_effect=ConnectionResetError(54, "Connection reset by peer")),
    "TLS failure": dict(side_effect=ssl.SSLError("record layer failure")),
    "bad status line": dict(side_effect=http.client.BadStatusLine("garbage")),
    "cut short": dict(return_value=half_read()),
    "an HTML page with status 200": dict(return_value=Reply(b"<html>Just a moment...</html>")),
    "JSON that is not an object": dict(return_value=Reply(b"[1, 2]")),
    "not text": dict(return_value=Reply(b"\xff\xfe\x00")),
}


class FakeGhl:
    """A stand-in GoHighLevel that remembers contacts, their tags, notes and uploads, so a test can look at what a
    contact ends up with. `fail` holds (method, end of path, status) entries; each makes the next matching call fail once."""

    def __init__(self):
        self.calls, self.contacts, self.notes, self.fail, self.uploads, self.hook = [], {}, [], [], 0, None

    def contact(self, email, tags=()):
        return self.contacts.setdefault(email, {"id": f"c{len(self.contacts) + 1}", "tags": list(tags)})

    def tags(self, email):
        return sorted(self.contacts[email]["tags"])

    def _by_id(self, contact_id):
        return next(c for c in self.contacts.values() if c["id"] == contact_id)

    def to(self, end, method="POST"):
        return [c for c in self.calls if c[0] == method and c[1].endswith(end)]

    def handle(self, method, path, data, timeout):
        self.calls.append((method, path, data, timeout))
        if self.hook:
            self.hook(method, path)
        for i, (m, end, status) in enumerate(self.fail):
            if m == method and path.endswith(end):
                del self.fail[i]
                raise GhlError(f"{method} {path} -> {status}", status=status, body="stand-in failure")
        if path == "/contacts/upsert":
            c = self.contact(data["email"])
            return {"contact": {"id": c["id"], "tags": list(c["tags"])}}
        if path == "/medias/upload-file":
            self.uploads += 1
            return {"url": f"https://files.example/sheet-{self.uploads}.pdf"}
        if method == "GET" and path == "/contacts/search/duplicate":
            c = self.contacts.get(data["email"])
            return {"contact": {"id": c["id"], "tags": list(c["tags"])} if c else None}
        if path.startswith("/contacts/"):
            c = self._by_id(path.split("/")[2])
            if path.endswith("/tags") and method == "POST":
                c["tags"] += [t for t in data["tags"] if t not in c["tags"]]
            elif path.endswith("/tags") and method == "DELETE":
                c["tags"] = [t for t in c["tags"] if t not in data["tags"]]
            elif path.endswith("/notes") and method == "GET":
                return {"notes": [{"id": f"n{i}", "body": body, "contactId": cid} for i, (cid, body) in enumerate(self.notes) if cid == c["id"]]}
            elif path.endswith("/notes"):
                self.notes.append((c["id"], data["body"]))
            elif method == "GET":
                return {"contact": {"id": c["id"], "tags": list(c["tags"])}}
        return {}

    def post(self, url, headers, payload, timeout=10):  # stands in for integrations._post
        try:
            return 200, self.handle("POST", url.replace(integrations.GHL_API, ""), payload, timeout)
        except GhlError as err:
            return err.status, {"error": str(err)}

    def request(self, method, path, query=None, body=None, raw=None, content_type="application/json", timeout=30):  # ghl.request
        return self.handle(method, path, body if body is not None else (query or raw), timeout)


class GhlCase(TestCase):
    def setUp(self):
        cache.clear()
        caches["shared"].clear()
        self.ghl = FakeGhl()
        for target, fake in (("talks.integrations._post", self.ghl.post), ("talks.ghl.request", self.ghl.request)):
            patcher = patch(target, side_effect=fake)
            patcher.start()
            self.addCleanup(patcher.stop)

    def signup(self, **body):
        return self.client.post("/api/signups/", {"email": "race@example.com", "install_id": INSTALL, **body}, content_type="application/json")


def aged(row, **ago):
    """Moves a row's created_at back, past the cron's grace period for brand-new rows."""
    type(row).objects.filter(pk=row.pk).update(created_at=timezone.now() - dt.timedelta(**ago))
    return row


# ---- Calls out: every network and parsing failure is a handled failure --------------------------------------

class OutsideCallTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_post_answers_status_0_for_every_way_a_connection_can_break(self):
        for name, how in BROKEN.items():
            with self.subTest(name), patch("urllib.request.urlopen", **how):
                status, body = integrations._post("https://api.onesignal.com/notifications", {}, {"a": 1})
                self.assertEqual(status, 0)
                self.assertIn("error", body)

    @override_settings(**GHL_ON)
    def test_ghl_request_raises_its_own_error_for_every_way_a_connection_can_break(self):
        for name, how in BROKEN.items():
            with self.subTest(name), patch("urllib.request.urlopen", **how):
                with self.assertRaises(GhlError) as caught:
                    ghl.request("POST", "/contacts/upsert", body={"email": "a@b.co"})
                self.assertEqual(caught.exception.status, 0)

    @override_settings(**GHL_ON)
    def test_an_error_answer_whose_body_cannot_be_read_is_still_a_handled_failure(self):
        import urllib.error

        class Gone:
            def read(self):
                raise ConnectionResetError(54, "Connection reset by peer")

            def close(self):
                pass

        err = urllib.error.HTTPError("https://x", 502, "Bad Gateway", {}, Gone())
        with patch("urllib.request.urlopen", side_effect=err):
            self.assertEqual(integrations._post("https://x", {}, {})[0], 502)
            with self.assertRaises(GhlError) as caught:
                ghl.request("GET", "/contacts/abc")
        self.assertEqual(caught.exception.status, 502)

    @override_settings(**GHL_ON)
    def test_signup_answers_200_and_keeps_the_row_when_gohighlevel_drops_the_connection(self):
        for name in ("closed without answering", "an HTML page with status 200"):
            with self.subTest(name), patch("urllib.request.urlopen", **BROKEN[name]):
                email = f"{name.split()[0]}@example.com"
                r = self.client.post("/api/signups/", {"email": email}, content_type="application/json")
                self.assertEqual(r.status_code, 200)
                self.assertIsNone(AppSignup.objects.get(email=email).ghl_synced_at)
                call_command("sync_signups", stdout=StringIO())  # the retry does not blow up either

    @override_settings(**GHL_ON, **PUSH_ON)
    def test_a_dropped_onesignal_connection_does_not_stop_the_cron_run(self):
        talk = ToolboxTalk.objects.order_by("issue").first()
        ToolboxTalk.objects.filter(pk=talk.pk).update(send_at=timezone.now() - dt.timedelta(hours=1), published=True, needs_review=False, push_sent_at=None)
        aged(AppSignup.objects.create(email="waiting@example.com"), minutes=10)
        ran = []

        def commands(name, *args, **kwargs):  # the real push and sign-up steps; the ones that would call out further are only noted
            ran.append(name)
            if name in ("send_talk_push", "sync_signups", "owner_digest"):
                call_command(name, *args, **{"stdout": StringIO(), **kwargs})

        with patch("urllib.request.urlopen", **BROKEN["closed without answering"]), patch(f"{CRON}.call_command", side_effect=commands):
            call_command("cron", stdout=StringIO())  # no exception: a failed push is a handled failure, tried again next run
        self.assertEqual(ran[0], "send_talk_push")
        self.assertIn("monday_minute", ran)
        self.assertIsNone(ToolboxTalk.objects.get(pk=talk.pk).push_sent_at)


# ---- The cron: every step runs, a failure is logged and shows in the exit code -------------------------------

class CronStepTests(TestCase):
    def setUp(self):
        cache.clear()

    def run_cron(self, **patches):
        """Runs the cron with the sub-commands replaced by a recorder. Returns (commands run, output, error or None)."""
        ran, out = [], StringIO()
        fail = patches.pop("fail", ())

        def commands(name, *args, **kwargs):
            ran.append(name)
            if name in fail:
                raise RuntimeError(f"{name} blew up")

        error = None
        with patch(f"{CRON}.call_command", side_effect=commands), patch(f"{CRON}.sync_episodes", return_value=[]):
            try:
                call_command("cron", stdout=out)
            except CommandError as err:
                error = err
        return ran, out.getvalue(), error

    def test_one_failing_step_does_not_stop_the_others_and_the_run_exits_non_zero(self):
        with self.assertLogs(CRON, level="ERROR") as logs:
            ran, out, error = self.run_cron(fail=("send_talk_push", "sync_signups"))
        for later in ("sync_signups", "owner_digest", "regs_sync", "monday_minute"):
            self.assertIn(later, ran)
        self.assertIsNotNone(error)  # manage.py turns this into exit code 1
        self.assertIn("send_talk_push", str(error))
        self.assertIn("sync_signups", str(error))
        self.assertIn("Traceback", logs.output[0])  # the traceback is in the log
        self.assertIn("send_talk_push blew up", logs.output[0])

    def test_a_clean_run_exits_zero(self):
        ran, out, error = self.run_cron()
        self.assertIsNone(error)
        self.assertEqual(ran[0], "send_talk_push")

    def test_a_failing_owner_alert_or_invite_step_does_not_stop_the_monday_minute_step(self):
        with patch("talks.owner_alerts.retry_signup_alerts", side_effect=RuntimeError("alerts")), \
             patch(f"{CRON}.retry_invite_tags", side_effect=RuntimeError("invite")), self.assertLogs(CRON, level="ERROR"):
            ran, out, error = self.run_cron()
        self.assertIn("monday_minute", ran)
        self.assertIn("owner_digest", ran)
        self.assertIsNotNone(error)

    @override_settings(**PUSH_ON)
    def test_one_feed_push_that_raises_does_not_stop_the_next_item_or_the_episodes(self):
        now = timezone.now()
        for n in (1, 2):
            FeedItem.objects.create(external_id=f"f{n}", kind=FeedItem.ALERT, title=f"Rule {n}", send_push=True, publish_at=now - dt.timedelta(hours=n))
        Episode.objects.all().delete()
        Episode.objects.create(number=90, title="Ep", hazard="h", story="s", release_at=now - dt.timedelta(hours=1))
        sent = []

        def feed(item):
            sent.append(item.title)
            raise RuntimeError("boom")

        with patch(f"{CRON}.send_feed_push", side_effect=feed), patch(f"{CRON}.send_episode_push", return_value=(True, {})) as episode, \
             self.assertLogs(CRON, level="ERROR"):
            ran, out, error = self.run_cron()
        self.assertEqual(sorted(sent), ["Rule 1", "Rule 2"])
        episode.assert_called_once()
        self.assertIsNotNone(error)

    def test_pushes_keep_going_out_while_a_slow_step_is_still_running(self):
        passes, slow_done = [], threading.Event()

        def commands(name, *args, **kwargs):
            if name == "monday_minute":  # a long write: stay in it until two more push passes have happened
                slow_done.wait(5)

        def pushes(self_, zero_hour=False):
            passes.append(1)
            if len(passes) >= 3:
                slow_done.set()

        with patch(f"{CRON}.PUSH_EVERY", 0.01), patch.object(cron.Command, "pushes", pushes), \
             patch(f"{CRON}.call_command", side_effect=commands), patch(f"{CRON}.sync_episodes", return_value=[]):
            call_command("cron", stdout=StringIO())
        self.assertGreaterEqual(len(passes), 3)  # once at the start, then again while the slow step ran

    def test_a_quick_run_sends_pushes_once(self):
        passes = []
        with patch.object(cron.Command, "pushes", lambda self_, zero_hour=False: passes.append(1)), patch(f"{CRON}.call_command"), \
             patch(f"{CRON}.sync_episodes", return_value=[]):
            call_command("cron", stdout=StringIO())
        self.assertEqual(len(passes), 1)


# ---- A push OneSignal accepted is never sent twice ---------------------------------------------------------------

@override_settings(**PUSH_ON, SECRET_KEY="test")
class PushOnceTests(TestCase):
    def setUp(self):
        cache.clear()
        caches["shared"].clear()
        self.talk = ToolboxTalk.objects.order_by("issue").first()
        ToolboxTalk.objects.filter(pk=self.talk.pk).update(push_sent_at=None)
        self.talk.refresh_from_db()

    def keys(self, send, answers):
        """Calls send() once per answer and returns the idempotency key each request carried."""
        sent = []
        for answer in answers:
            with patch("talks.integrations._post", return_value=answer) as post:
                send()
            sent.append(post.call_args[0][2].get("idempotency_key"))
        return sent

    def test_a_retry_after_an_unreadable_answer_carries_the_same_key(self):
        first, second = self.keys(lambda: integrations.send_talk_push(self.talk), [(0, {"error": "timed out"}), (200, {"id": "n1"})])
        self.assertEqual(str(uuid.UUID(first)), first)  # OneSignal wants a UUID
        self.assertEqual(first, second)  # so OneSignal drops the repeat if it had accepted the first one
        self.assertIsNotNone(ToolboxTalk.objects.get(pk=self.talk.pk).push_sent_at)

    def test_each_item_has_its_own_key_and_feed_and_episode_pushes_carry_one_too(self):
        now = timezone.now()
        item = FeedItem.objects.create(external_id="k1", kind=FeedItem.ALERT, title="Rule", send_push=True, publish_at=now)
        other = FeedItem.objects.create(external_id="k2", kind=FeedItem.ALERT, title="Rule 2", send_push=True, publish_at=now)
        ep = Episode.objects.create(number=91, title="Ep", hazard="h", story="s", release_at=now)
        lost = (0, {"error": "timed out"})
        a = self.keys(lambda: integrations.send_feed_push(item), [lost, lost])
        b = self.keys(lambda: integrations.send_feed_push(other), [lost])
        c = self.keys(lambda: integrations.send_episode_push(ep), [lost, lost])
        t = self.keys(lambda: integrations.send_talk_push(self.talk), [lost])
        self.assertEqual(a[0], a[1])
        self.assertEqual(c[0], c[1])
        self.assertEqual(len({a[0], b[0], c[0], t[0]}), 4)
        self.assertTrue(all(a + b + c + t))

    def test_sending_again_on_purpose_is_not_dropped_as_a_repeat(self):
        ok = (200, {"id": "n1"})
        first, again = self.keys(lambda: integrations.send_talk_push(self.talk), [ok, ok])  # e.g. send_talk_push --issue, or the admin action
        self.assertNotEqual(first, again)

    def test_a_push_refused_outright_is_tried_again_with_a_fresh_key(self):
        for status in (400, 401, 403):
            with self.subTest(status):
                caches["shared"].clear()
                refused, retry = self.keys(lambda: integrations.send_talk_push(self.talk), [(status, {"errors": ["no"]}), (0, {"error": "timed out"})])
                self.assertNotEqual(refused, retry)  # OneSignal said no, so nothing went out: a replayed "no" must not block the retry

    def test_a_try_again_later_answer_keeps_the_key(self):
        # OneSignal: after 429 or 5xx "the request may still be processing", retry with the same key.
        for status in (429, 500, 502, 503):
            with self.subTest(status):
                caches["shared"].clear()
                busy, retry = self.keys(lambda: integrations.send_talk_push(self.talk), [(status, {"errors": ["later"]}), (0, {"error": "timed out"})])
                self.assertEqual(busy, retry)

    def test_a_push_that_went_out_behind_a_500_is_not_delivered_again(self):
        """A stand-in OneSignal that keeps its word on keys: one delivery per key, however often it is asked."""
        delivered, answers = [], [500, 0, 200]  # took it and answered 500; took the repeat and the answer was lost; healthy

        def onesignal(url, headers, payload, timeout=10):
            if payload["idempotency_key"] not in delivered:
                delivered.append(payload["idempotency_key"])
            status = answers.pop(0)
            return status, ({"id": "n1"} if status == 200 else {"error": "x"})

        with patch("talks.integrations._post", side_effect=onesignal), self.assertLogs("talks.integrations", level="ERROR"):
            for _ in range(3):  # three cron runs
                call_command("send_talk_push", issue=self.talk.issue, stdout=StringIO())
                if ToolboxTalk.objects.get(pk=self.talk.pk).push_sent_at:
                    break
        self.assertEqual(answers, [])
        self.assertEqual(len(delivered), 1)

    def test_a_key_that_keeps_getting_try_again_later_is_given_up_after_three(self):
        busy = (503, {"errors": ["later"]})
        keys = self.keys(lambda: integrations.send_talk_push(self.talk), [busy, busy, busy, busy, busy])
        self.assertEqual(len(set(keys[:3])), 1)
        self.assertNotEqual(keys[3], keys[0])  # so a push can never sit for good behind one key
        self.assertEqual(keys[3], keys[4])     # and the new key gets its own three tries

    def test_what_onesignal_answered_is_still_known_at_the_next_cron_run_and_weeks_later(self):
        """The count used to be kept with the database cache's incr(), which saves it again for 5 minutes only: by the
        next cron run, 15 minutes later, the push was back on its first key."""
        first, = self.keys(lambda: integrations.send_talk_push(self.talk), [(400, {"errors": ["no"]})])
        for later in (dt.timedelta(minutes=16), dt.timedelta(days=29)):
            with self.subTest(later), patch("django.core.cache.backends.db.tz_now", return_value=timezone.now() + later):
                self.assertNotEqual(integrations.push_key("talk", self.talk.issue), first)

    def test_the_monday_minute_push_can_come_through_the_same_door(self):
        # monday/push.py calls post_push(payload, "monday", minute.pk, minute.push_sent_at): same key rules, own keys.
        with patch("talks.integrations._post", return_value=(0, {"error": "timed out"})) as post:
            integrations.post_push({"app_id": "app"}, "monday", 7, None)
            integrations.post_push({"app_id": "app"}, "monday", 7, None)
            integrations.post_push({"app_id": "app"}, "monday", 8, None)
        a, b, c = [call[0][2]["idempotency_key"] for call in post.call_args_list]
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)
        self.assertEqual(post.call_args[0][0], integrations.ONESIGNAL_PUSH)

    def test_an_early_push_from_the_console_carries_no_key(self):
        early, release = self.keys(lambda: integrations.send_talk_push(self.talk, mark_sent=False), [(200, {"id": "n1"})]) + \
            self.keys(lambda: integrations.send_talk_push(self.talk), [(200, {"id": "n2"})])
        self.assertIsNone(early)  # it must not use up the key of the release push that follows
        self.assertTrue(release)

    def test_dry_run_payloads_are_unchanged(self):
        ok, payload = integrations.send_talk_push(self.talk, dry_run=True)
        self.assertNotIn("idempotency_key", payload)


# ---- Sign-in sheets: a retry never uploads the PDF again -------------------------------------------------------------

@override_settings(**GHL_ON)
class SheetRetryTests(GhlCase):
    def sheet(self, n=1, **ago):
        sheet = SigninSheet.objects.create(talk_title=f"Talk {n}", supervisor_name="Ana Ruiz", supervisor_email=f"lead{n}@plant.com",
                                           held_on=dt.date(2027, 6, 7), attendee_count=9, pdf=b"%PDF-1.7 test")
        return aged(sheet, **(ago or {"minutes": 10}))

    def test_a_sheet_whose_note_fails_is_not_uploaded_again(self):
        sheet = self.sheet()
        self.ghl.fail = [("POST", "/notes", 500)] * 3
        for _ in range(3):
            self.assertFalse(integrations.sync_sheet_to_ghl(SigninSheet.objects.get(pk=sheet.pk)))
        row = SigninSheet.objects.get(pk=sheet.pk)
        self.assertEqual((row.status, self.ghl.uploads), ("failed", 1))
        self.assertEqual(row.ghl_media_url, "https://files.example/sheet-1.pdf")  # written down as soon as the upload worked
        self.assertTrue(bytes(row.pdf).startswith(b"%PDF"))  # kept until everything is done
        self.assertTrue(integrations.sync_sheet_to_ghl(SigninSheet.objects.get(pk=sheet.pk)))
        row = SigninSheet.objects.get(pk=sheet.pk)
        self.assertEqual((row.status, self.ghl.uploads, bytes(row.pdf)), ("synced", 1, b""))
        self.assertEqual(len(self.ghl.notes), 1)
        self.assertIn("https://files.example/sheet-1.pdf", self.ghl.notes[0][1])

    def test_the_cron_leaves_a_sheet_alone_while_the_app_may_still_be_uploading_it(self):
        self.sheet(1, seconds=30)
        with patch(f"{CRON}.call_command"), patch(f"{CRON}.sync_episodes", return_value=[]):
            call_command("cron", stdout=StringIO())
        self.assertEqual(self.ghl.uploads, 0)
        SigninSheet.objects.update(created_at=timezone.now() - dt.timedelta(minutes=10))
        with patch(f"{CRON}.call_command"), patch(f"{CRON}.sync_episodes", return_value=[]):
            call_command("cron", stdout=StringIO())
        self.assertEqual(self.ghl.uploads, 1)

    def test_sheets_that_keep_failing_cannot_hold_back_the_others(self):
        for n in range(25):  # the newest 20 used to be the only ones ever tried
            self.sheet(n, hours=30 - n)
        tried = set()
        start = timezone.now().replace(minute=5, second=0, microsecond=0)
        with patch(f"{CRON}.sync_sheet_to_ghl", side_effect=lambda s: tried.add(s.pk) and False), \
             patch(f"{CRON}.call_command"), patch(f"{CRON}.sync_episodes", return_value=[]):
            for run in range(2):
                with patch("django.utils.timezone.now", return_value=start + dt.timedelta(minutes=15 * run)):
                    call_command("cron", stdout=StringIO())
        self.assertEqual(len(tried), 25)

    def test_every_try_is_counted_on_the_sheet(self):
        sheet = self.sheet()
        self.ghl.fail = [("POST", "/notes", 500)] * 3
        for _ in range(3):
            integrations.sync_sheet_to_ghl(SigninSheet.objects.get(pk=sheet.pk))
        self.assertEqual(SigninSheet.objects.get(pk=sheet.pk).attempts, 3)
        self.assertTrue(integrations.sync_sheet_to_ghl(SigninSheet.objects.get(pk=sheet.pk)))
        row = SigninSheet.objects.get(pk=sheet.pk)
        self.assertEqual((row.attempts, row.status), (4, "synced"))  # the last save does not put the count back
        with override_settings(GHL_PRIVATE_TOKEN=""):  # nothing was tried, so nothing is counted
            other = self.sheet(2)
            integrations.sync_sheet_to_ghl(other)
        self.assertEqual(SigninSheet.objects.get(pk=other.pk).attempts, 0)

    def test_a_sheets_note_gohighlevel_stored_without_answering_is_not_written_again(self):
        sheet = self.sheet()

        def lost(method, path):  # GoHighLevel stores the note; the answer never arrives
            if method == "POST" and path.endswith("/notes"):
                self.ghl.notes.append((path.split("/")[2], f"Zero Harm crew sign-in sheet\nRef: {integrations.note_mark('sheet', sheet.pk)}"))
                raise GhlError(f"POST {path} -> TimeoutError: timed out")

        self.ghl.hook = lost
        self.assertFalse(integrations.sync_sheet_to_ghl(SigninSheet.objects.get(pk=sheet.pk)))
        self.ghl.hook = None
        self.assertTrue(integrations.sync_sheet_to_ghl(SigninSheet.objects.get(pk=sheet.pk)))
        self.assertEqual((len(self.ghl.notes), self.ghl.uploads), (1, 1))
        self.assertEqual(SigninSheet.objects.get(pk=sheet.pk).status, "synced")

    def test_a_supervisors_second_sheet_still_gets_its_own_note_and_the_first_try_does_not_look(self):
        first, second = self.sheet(1), self.sheet(1)  # same supervisor, so the same contact
        self.assertTrue(integrations.sync_sheet_to_ghl(first))
        self.assertEqual(self.ghl.to("/notes", "GET"), [])  # nothing to look for on a first try
        self.ghl.fail = [("POST", "/contacts/upsert", 500)]
        self.assertFalse(integrations.sync_sheet_to_ghl(SigninSheet.objects.get(pk=second.pk)))
        self.assertTrue(integrations.sync_sheet_to_ghl(SigninSheet.objects.get(pk=second.pk)))
        self.assertEqual(len(self.ghl.to("/notes", "GET")), 1)
        self.assertEqual(len(self.ghl.notes), 2)
        self.assertTrue(self.ghl.notes[1][1].endswith(f"Ref: {integrations.note_mark('sheet', second.pk)}"))

    def cron_runs(self, runs, start=None):
        """Runs the cron `runs` times, 15 minutes apart, with the sheet step's call to GoHighLevel replaced by a
        recorder that fails. Returns the sheet ids each run tried."""
        tried = []
        start = start or timezone.now().replace(minute=5, second=0, microsecond=0)
        with patch(f"{CRON}.sync_sheet_to_ghl", side_effect=lambda s: tried[-1].append(s.pk) and False), \
             patch(f"{CRON}.call_command"), patch(f"{CRON}.sync_episodes", return_value=[]):
            for run in range(runs):
                tried.append([])
                with patch("django.utils.timezone.now", return_value=start + dt.timedelta(minutes=15 * run)):
                    call_command("cron", stdout=StringIO())
        return tried

    def test_a_sheet_that_keeps_failing_is_tried_less_often_but_never_given_up(self):
        fresh, stuck = self.sheet(1, hours=3), self.sheet(2, hours=3)  # hours old: the runs below start up to an hour back
        SigninSheet.objects.filter(pk=fresh.pk).update(attempts=cron.SHEET_FAST_TRIES - 1)
        SigninSheet.objects.filter(pk=stuck.pk).update(attempts=cron.SHEET_FAST_TRIES)
        tried = self.cron_runs(cron.SHEET_SLOW_EVERY * 2)  # eight hours of runs
        self.assertTrue(all(fresh.pk in run for run in tried))        # still in its first tries: every run
        self.assertEqual(sum(stuck.pk in run for run in tried), 2)    # past them: once every four hours

    def test_stuck_sheets_do_not_all_come_up_in_the_same_run(self):
        sheets = [self.sheet(n, hours=3) for n in range(cron.SHEET_SLOW_EVERY)]
        SigninSheet.objects.update(attempts=50)
        tried = self.cron_runs(cron.SHEET_SLOW_EVERY)
        self.assertEqual(sorted(len(run) for run in tried), [1] * cron.SHEET_SLOW_EVERY)
        self.assertEqual(sorted(pk for run in tried for pk in run), sorted(s.pk for s in sheets))

    def test_a_stuck_sheet_still_goes_through_by_itself_once_gohighlevel_takes_it(self):
        sheet = self.sheet()
        SigninSheet.objects.filter(pk=sheet.pk).update(attempts=40, status="failed", error="POST /contacts/upsert -> 401")
        with patch(f"{CRON}.call_command"), patch(f"{CRON}.sync_episodes", return_value=[]):
            for run in range(cron.SHEET_SLOW_EVERY):
                with patch("django.utils.timezone.now", return_value=timezone.now() + dt.timedelta(minutes=15 * run)):
                    call_command("cron", stdout=StringIO())
        row = SigninSheet.objects.get(pk=sheet.pk)
        self.assertEqual((row.status, row.attempts, self.ghl.uploads), ("synced", 41, 1))

    @override_settings(OWNER_ALERT_EMAIL="owner@example.com")
    def test_the_owner_is_told_once_about_a_sheet_that_will_not_go_through(self):
        sheet = self.sheet()
        self.ghl.fail = [("POST", "/notes", 422)] * 20
        command = cron.Command(stdout=StringIO())
        command.failed = []
        mails = lambda: [c[2] for c in self.ghl.to("/conversations/messages")]
        with self.assertLogs("talks.integrations", level="ERROR"):
            for n in range(cron.SHEET_FAST_TRIES - 1):
                command.sheet(SigninSheet.objects.get(pk=sheet.pk))
            self.assertEqual(mails(), [])  # a few failed tries are ordinary: GoHighLevel has bad hours
            command.sheet(SigninSheet.objects.get(pk=sheet.pk))
            mail, = mails()
            self.assertIn("Talk 1", mail["subject"])
            for part in (f"Sign-in sheet {sheet.pk}", "lead1@plant.com", f"after {cron.SHEET_FAST_TRIES} tries", "/notes -&gt; 422", "Retry saving to GoHighLevel"):
                self.assertIn(part, mail["html"])
            command.sheet(SigninSheet.objects.get(pk=sheet.pk))
        self.assertEqual(len(mails()), 1)  # once per sheet, however long it stays stuck
        self.assertEqual(command.failed, [])

    @override_settings(OWNER_ALERT_EMAIL="owner@example.com")
    def test_a_sheet_that_goes_through_late_sends_no_email(self):
        sheet = self.sheet()
        SigninSheet.objects.filter(pk=sheet.pk).update(attempts=cron.SHEET_FAST_TRIES + 3)
        command = cron.Command(stdout=StringIO())
        command.failed = []
        command.sheet(SigninSheet.objects.get(pk=sheet.pk))
        self.assertEqual(SigninSheet.objects.get(pk=sheet.pk).status, "synced")
        self.assertEqual(self.ghl.to("/conversations/messages"), [])


# ---- Sign-ups: what the contact "already had" is decided from the row as it is now ---------------------------------

@override_settings(**GHL_ON)
class SignupSyncTests(GhlCase):
    def test_a_sync_holding_a_stale_copy_does_not_record_the_apps_own_tags_as_already_there(self):
        self.assertEqual(self.signup().status_code, 200)
        row = AppSignup.objects.get()
        self.assertEqual(row.ghl_had_tags, [])
        # The copy the cron loaded while the sign-up request was still talking to GoHighLevel:
        stale = AppSignup.objects.get(pk=row.pk)
        stale.ghl_contact_id, stale.ghl_had_tags, stale.ghl_synced_at = "", None, None
        self.assertTrue(integrations.sync_signup_to_ghl(stale))
        self.assertEqual(AppSignup.objects.get().ghl_had_tags, [])
        self.client.post("/api/signups/remove/", {"install_id": INSTALL}, content_type="application/json")
        self.assertFalse(AppSignup.objects.exists())
        self.assertEqual(self.ghl.tags("race@example.com"), ["zero-harm-app", "zero-harm-removed"])  # off the newsletter list

    def test_a_stale_copy_does_not_take_the_offers_tag_back_off(self):
        self.signup(wants_offers=True)
        stale = AppSignup.objects.get()
        stale.wants_offers = False  # loaded before they ticked the box
        self.assertTrue(integrations.sync_signup_to_ghl(stale))
        self.assertIn("zero-harm-offers-optin", self.ghl.tags("race@example.com"))

    def test_tags_the_contact_really_had_are_still_noted_and_left_on_at_removal(self):
        self.ghl.contact("race@example.com", tags=["zero-harm-weekly", "customer"])
        self.signup()
        self.assertEqual(AppSignup.objects.get().ghl_had_tags, ["zero-harm-weekly"])
        self.client.post("/api/signups/remove/", {"install_id": INSTALL}, content_type="application/json")
        self.assertEqual(self.ghl.tags("race@example.com"), ["customer", "zero-harm-app", "zero-harm-removed", "zero-harm-weekly"])

    def test_the_removed_tag_comes_off_even_when_the_first_try_half_failed(self):
        self.ghl.contact("race@example.com", tags=["zero-harm-removed", "zero-harm-app"])  # they removed an earlier sign-up
        self.ghl.fail = [("POST", "/tags", 500)]
        self.assertEqual(self.signup().status_code, 200)
        row = AppSignup.objects.get()
        self.assertTrue(row.ghl_contact_id)  # the contact was saved,
        self.assertIsNone(row.ghl_synced_at)  # but the tags did not go on
        call_command("sync_signups", stdout=StringIO())
        self.assertIsNotNone(AppSignup.objects.get().ghl_synced_at)
        self.assertEqual(self.ghl.tags("race@example.com"), ["zero-harm-app", "zero-harm-app-signup", "zero-harm-weekly"])

    def test_the_cron_leaves_a_brand_new_signup_to_its_own_request(self):
        new = AppSignup.objects.create(email="new@example.com")
        old = aged(AppSignup.objects.create(email="old@example.com"), minutes=10)
        with patch(f"{CRON}.sync_episodes", return_value=[]), \
             patch(f"{CRON}.call_command", side_effect=lambda name, *a, **k: name == "sync_signups" and call_command(name, *a, **{"stdout": StringIO(), **k})):
            call_command("cron", stdout=StringIO())
        self.assertIsNotNone(AppSignup.objects.get(pk=old.pk).ghl_synced_at)
        self.assertIsNone(AppSignup.objects.get(pk=new.pk).ghl_synced_at)
        call_command("sync_signups", stdout=StringIO())  # run by hand, it takes everything that is waiting
        self.assertIsNotNone(AppSignup.objects.get(pk=new.pk).ghl_synced_at)

    def test_one_signup_that_raises_does_not_stop_the_rest(self):
        for n in range(3):
            AppSignup.objects.create(email=f"p{n}@example.com")
        real = integrations.sync_signup_to_ghl

        def flaky(signup, **kwargs):
            if signup.email == "p1@example.com":
                raise RuntimeError("database hiccup")
            return real(signup, **kwargs)

        out = StringIO()
        with patch("talks.management.commands.sync_signups.sync_signup_to_ghl", side_effect=flaky), \
             self.assertLogs("talks.management.commands.sync_signups", level="ERROR"):
            call_command("sync_signups", stdout=out)
        self.assertEqual(AppSignup.objects.filter(ghl_synced_at__isnull=False).count(), 2)
        self.assertIn("Synced 2 of 3", out.getvalue())


# ---- Suggest a topic: quick while the phone waits, retried by the cron ----------------------------------------------

@override_settings(**GHL_ON)
class SuggestionSyncTests(GhlCase):
    def suggest(self, **extra):
        return self.client.post("/api/suggestions/", json.dumps({"topic": "Forklift blind corners", "email": "lead@plant.com", **extra}),
                                content_type="application/json")

    def test_gohighlevel_gets_short_limits_while_the_phone_waits(self):
        self.assertEqual(self.suggest().status_code, 201)
        self.assertTrue(self.ghl.calls)
        self.assertTrue(all(c[3] <= integrations.QUICK for c in self.ghl.calls), [c[3] for c in self.ghl.calls])
        self.assertTrue(TalkSuggestion.objects.get().ghl_contact_id)

    def test_a_slow_gohighlevel_cannot_keep_the_phone_past_its_own_limit(self):
        clock = [1000.0]
        self.ghl.hook = lambda method, path: clock.__setitem__(0, clock[0] + 4)  # every call takes its full 4 seconds
        with patch("talks.integrations.time.monotonic", side_effect=lambda: clock[0]):
            self.assertEqual(self.suggest().status_code, 201)
        self.assertLessEqual(clock[0] - 1000.0, 9)  # the app gives up after 10
        s = TalkSuggestion.objects.get()
        self.assertEqual(s.ghl_contact_id, "")  # not finished: left for the cron
        self.assertEqual(self.ghl.notes, [])

    def test_the_cron_finishes_what_the_request_could_not(self):
        self.ghl.fail = [("POST", "/contacts/upsert", 0)]
        self.assertEqual(self.suggest().status_code, 201)
        s = TalkSuggestion.objects.get()
        self.assertEqual(s.ghl_contact_id, "")
        self.assertEqual(integrations.retry_suggestions(), 0)  # seconds old: its own request may still be at it
        aged(s, minutes=10)
        TalkSuggestion.objects.create(topic="Anonymous idea")  # no email: stays in the admin, never sent
        with patch(f"{CRON}.call_command"), patch(f"{CRON}.sync_episodes", return_value=[]):
            call_command("cron", stdout=StringIO())
        self.assertTrue(TalkSuggestion.objects.get(pk=s.pk).ghl_contact_id)
        self.assertEqual(len(self.ghl.notes), 1)
        self.assertIn("zero-harm-talk-suggestion", self.ghl.tags("lead@plant.com"))
        self.assertTrue(all(c[3] > integrations.QUICK for c in self.ghl.calls[1:]))  # no phone is waiting now
        self.assertEqual(integrations.retry_suggestions(), 0)  # done: no second note
        self.assertEqual(len(self.ghl.notes), 1)

    def test_old_suggestions_are_not_retried_for_ever(self):
        s = aged(TalkSuggestion.objects.create(topic="Old idea", email="lead@plant.com"), days=20)
        self.assertEqual(integrations.retry_suggestions(), 0)
        self.assertEqual(self.ghl.calls, [])
        self.assertEqual(TalkSuggestion.objects.get(pk=s.pk).ghl_contact_id, "")

    def lost_answer(self):
        """GoHighLevel stores the note, but the answer never arrives (status 0, as after a timeout)."""
        def hook(method, path):
            if method == "POST" and path.endswith("/notes"):
                self.ghl.notes.append((path.split("/")[2], f"stored, answer lost\nRef: {integrations.note_mark('idea', TalkSuggestion.objects.get().pk)}"))
                raise GhlError(f"POST {path} -> TimeoutError: timed out")
        return hook

    def test_a_note_gohighlevel_stored_without_answering_is_not_written_again(self):
        self.ghl.hook = self.lost_answer()
        self.assertEqual(self.suggest().status_code, 201)
        s = TalkSuggestion.objects.get()
        self.assertEqual((s.ghl_contact_id, len(self.ghl.notes)), ("", 1))  # stored, but the app does not know
        self.ghl.hook = None
        aged(s, minutes=10)
        self.assertEqual(integrations.retry_suggestions(), 1)
        self.assertEqual(len(self.ghl.notes), 1)  # the cron found the note and did not add a second
        self.assertTrue(TalkSuggestion.objects.get().ghl_contact_id)
        self.assertEqual(len(self.ghl.to("/notes")), 1)

    def test_the_same_holds_when_the_answer_is_lost_in_the_cron(self):
        self.ghl.fail = [("POST", "/contacts/upsert", 0)]
        self.suggest()
        s = aged(TalkSuggestion.objects.get(), minutes=10)
        self.ghl.hook = self.lost_answer()
        self.assertEqual(integrations.retry_suggestions(), 0)
        self.ghl.hook = None
        self.assertEqual(integrations.retry_suggestions(), 1)
        self.assertEqual(len(self.ghl.notes), 1)

    def test_a_second_idea_from_the_same_person_still_gets_its_own_note(self):
        self.suggest()
        self.ghl.fail = [("POST", "/contacts/upsert", 0)]
        self.suggest(topic="Ladder inspections")
        first, second = TalkSuggestion.objects.order_by("pk")
        self.assertNotEqual(integrations.note_mark("idea", first.pk), integrations.note_mark("idea", second.pk))
        aged(second, minutes=10)
        self.assertEqual(integrations.retry_suggestions(), 1)
        self.assertEqual(len(self.ghl.notes), 2)  # the first idea's note is not mistaken for the second's
        self.assertIn("Ladder inspections", self.ghl.notes[1][1])
        self.assertTrue(self.ghl.notes[1][1].endswith(f"Ref: {integrations.note_mark('idea', second.pk)}"))

    def test_when_the_notes_cannot_be_read_just_now_the_cron_waits_instead_of_risking_a_second_note(self):
        self.ghl.fail = [("POST", "/contacts/upsert", 0)]
        self.suggest()
        s = aged(TalkSuggestion.objects.get(), minutes=10)
        for status in (0, 429, 503):
            with self.subTest(status):
                self.ghl.fail = [("GET", "/notes", status)]
                self.assertEqual(integrations.retry_suggestions(), 0)
                self.assertEqual(self.ghl.notes, [])
                self.assertEqual(TalkSuggestion.objects.get().ghl_contact_id, "")
        self.assertEqual(integrations.retry_suggestions(), 1)  # GoHighLevel answers again
        self.assertEqual(len(self.ghl.notes), 1)

    def test_when_gohighlevel_will_not_list_notes_at_all_the_note_is_still_written(self):
        self.ghl.fail = [("POST", "/contacts/upsert", 0)]
        self.suggest()
        aged(TalkSuggestion.objects.get(), minutes=10)
        self.ghl.fail = [("GET", "/notes", 403)]  # the token is not allowed to read notes
        with self.assertLogs("talks.integrations", level="WARNING") as logs:
            self.assertEqual(integrations.retry_suggestions(), 1)
        self.assertEqual(len(self.ghl.notes), 1)  # an idea with no note would be worse than a rare second note
        self.assertIn("would not list the notes", logs.output[0])


class SlowGhl(http.server.BaseHTTPRequestHandler):
    """A GoHighLevel stand-in on this machine that is really slow: it stores a note at once and answers after
    `delay` seconds. Only the calls a talk suggestion makes."""
    notes, delay = [], 0.0

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path.endswith("/notes"):
            type(self).notes.append(body["body"])
            time.sleep(type(self).delay)
        self.answer({"contact": {"id": "slow1", "tags": []}} if self.path == "/contacts/upsert" else {})

    def do_GET(self):
        self.answer({"notes": [{"id": str(i), "body": b} for i, b in enumerate(type(self).notes)]})

    def answer(self, data):
        raw = json.dumps(data).encode()
        try:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        except OSError:  # the caller gave up waiting and hung up, which is the point of the test
            pass

    def log_message(self, *args):
        pass


@override_settings(**GHL_ON)
class SlowGoHighLevelTests(TestCase):
    """The case the second checker found: GoHighLevel takes longer over the note than the phone's time allows."""

    def setUp(self):
        cache.clear()
        SlowGhl.notes, SlowGhl.delay = [], 0.6
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), SlowGhl)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        patcher = patch("talks.ghl.BASE", f"http://127.0.0.1:{self.server.server_address[1]}")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_note_cut_off_by_the_phones_time_limit_is_on_the_contact_once_after_the_cron(self):
        with patch("talks.integrations.QUICK", 0.2), self.assertLogs("talks.integrations", level="ERROR"):  # 4 s in real life
            r = self.client.post("/api/suggestions/", json.dumps({"topic": "Forklift blind corners", "email": "lead@plant.com"}),
                                 content_type="application/json")
        self.assertEqual(r.status_code, 201)
        s = TalkSuggestion.objects.get()
        self.assertEqual(s.ghl_contact_id, "")       # the app was cut off waiting for the answer...
        self.assertEqual(len(SlowGhl.notes), 1)      # ...but GoHighLevel had already stored the note
        aged(s, minutes=10)
        self.assertEqual(integrations.retry_suggestions(), 1)   # still slow, but the cron has time
        self.assertEqual(len(SlowGhl.notes), 1)      # one idea, one note
        self.assertEqual(TalkSuggestion.objects.get().ghl_contact_id, "slow1")
        self.assertEqual(integrations.retry_suggestions(), 0)
        self.assertEqual(len(SlowGhl.notes), 1)


# ---- One-off notices to the owner ---------------------------------------------------------------------------------------

OWNER_ON = dict(GHL_ON, OWNER_ALERT_EMAIL="owner@example.com")


@override_settings(**OWNER_ON)
class OwnerNoticeTests(GhlCase):
    def emails(self):
        return [c[2] for c in self.ghl.to("/conversations/messages")]

    def test_a_notice_goes_out_once_for_its_key(self):
        self.assertIs(owner_alerts.notify("No talk went out this week", ["Week of Nov 9.", "Look at the cron log <now>."], "monday-missed:2026-11-09"), True)
        self.assertIs(owner_alerts.notify("No talk went out this week", ["Week of Nov 9."], "monday-missed:2026-11-09"), False)
        mail, = self.emails()
        self.assertEqual((mail["type"], mail["subject"]), ("Email", "No talk went out this week"))
        self.assertEqual(mail["contactId"], self.ghl.contact("owner@example.com")["id"])
        self.assertIn("<p style=\"margin:0 0 8px\">Week of Nov 9.</p>", mail["html"])
        self.assertIn("Look at the cron log &lt;now&gt;.", mail["html"])  # plain text in, nothing read as HTML
        self.assertIs(owner_alerts.notify("Another week", ["Week of Nov 16."], "monday-missed:2026-11-16"), True)  # its own key
        self.assertEqual(len(self.emails()), 2)

    def test_the_key_is_remembered_by_the_web_server_and_the_cron_alike_for_14_days(self):
        self.assertTrue(owner_alerts.notify("Once", ["line"], "k1"))
        cache.clear()             # a cron run is a new process: nothing in memory carries over
        caches["limits"].clear()
        self.assertFalse(owner_alerts.notify("Once", ["line"], "k1"))
        with patch("django.core.cache.backends.db.tz_now", return_value=timezone.now() + dt.timedelta(days=13)):
            self.assertFalse(owner_alerts.notify("Once", ["line"], "k1"))
        with patch("django.core.cache.backends.db.tz_now", return_value=timezone.now() + dt.timedelta(days=15)):
            self.assertTrue(owner_alerts.notify("Once", ["line"], "k1"))

    def test_nothing_is_sent_while_owner_alerts_are_off_and_the_key_is_not_used_up(self):
        for off in (dict(OWNER_ALERT_EMAIL=""), dict(GHL_PRIVATE_TOKEN=""), dict(GHL_LOCATION_ID="")):
            with self.subTest(off), override_settings(**off):
                for _ in range(10):  # asked again on every cron run; none of it counts toward the hourly cap either
                    self.assertIs(owner_alerts.notify("Subject", ["line"], "k-off"), False)
        self.assertEqual(self.ghl.calls, [])
        self.assertTrue(owner_alerts.notify("Subject", ["line"], "k-off"))  # switched on later: it goes out then

    def test_a_notice_gohighlevel_did_not_take_can_be_sent_again_later(self):
        self.ghl.fail = [("POST", "/conversations/messages", 503)]
        with self.assertLogs("talks.owner_alerts", level="ERROR"):
            self.assertIs(owner_alerts.notify("Subject", ["line"], "k-retry"), False)
        self.assertIs(owner_alerts.notify("Subject", ["line"], "k-retry"), True)  # the next cron run
        self.assertIs(owner_alerts.notify("Subject", ["line"], "k-retry"), False)
        self.assertEqual(len(self.emails()), 2)  # the try GoHighLevel turned away, and the one that went out

    def test_it_never_raises(self):
        broken_cache = patch.object(caches["shared"], "add", side_effect=RuntimeError("no cache table"))
        broken_send = patch.object(owner_alerts, "send", side_effect=RuntimeError("boom"))
        with self.assertLogs("talks.owner_alerts", level="ERROR"):
            with broken_cache:
                self.assertIs(owner_alerts.notify("Subject", ["line"], "k-raise"), False)
            with broken_send:
                self.assertIs(owner_alerts.notify("Subject", ["line"], "k-raise"), False)
            self.assertIs(owner_alerts.notify("Subject", None, "k-raise"), False)   # lines that are not lines
        self.assertEqual(self.emails(), [])
        self.assertIs(owner_alerts.notify("Subject", "one line as plain text", "k-raise"), True)  # none of that used the key up
        self.assertIs(owner_alerts.notify(None, [None, 5], None), True)  # odd values are written out, not an error

    def test_a_missing_cache_table_means_no_email_rather_than_one_every_run(self):
        with patch.object(caches["shared"], "add", return_value=False):  # what Django's database cache answers when the table is gone
            self.assertIs(owner_alerts.notify("Subject", ["line"], "k-table"), False)
        self.assertEqual(self.emails(), [])

    def test_notices_count_toward_the_hourly_cap_on_owner_emails(self):
        cap = owner_alerts.ALERTS_PER_HOUR
        self.assertEqual(sum(owner_alerts.notify("Subject", ["line"], f"k{i}") for i in range(cap)), cap)
        with self.assertLogs("talks.owner_alerts", level="WARNING") as logs:
            self.assertIs(owner_alerts.notify("One too many", ["line"], "k-over"), False)
        self.assertIn("One too many", logs.output[0])
        self.assertEqual(len(self.emails()), cap)
        # Sign-up alerts share the count: this one is left for the daily summary.
        signup = AppSignup.objects.create(email="late@plant.com")
        self.assertTrue(owner_alerts.alert_signup(signup))
        self.assertEqual(len(self.emails()), cap)
        # The notice past the cap was not used up: in the next hour it goes out.
        caches["limits"].clear()
        self.assertIs(owner_alerts.notify("One too many", ["line"], "k-over"), True)

    def test_signup_alerts_use_up_the_same_cap(self):
        for i in range(owner_alerts.ALERTS_PER_HOUR):
            owner_alerts.alert_signup(AppSignup.objects.create(email=f"p{i}@plant.com"))
        self.assertEqual(len(self.emails()), owner_alerts.ALERTS_PER_HOUR)
        with self.assertLogs("talks.owner_alerts", level="WARNING"):
            self.assertIs(owner_alerts.notify("Subject", ["line"], "k-after-signups"), False)

    def test_a_count_that_runs_out_mid_step_does_not_break_the_sign_up(self):
        signup = AppSignup.objects.create(email="edge@plant.com")
        with patch.object(caches["limits"], "incr", side_effect=ValueError("Key not found")):  # what incr says about a count that just ran out
            self.assertTrue(owner_alerts.alert_signup(signup))
        self.assertEqual(len(self.emails()), 1)

    def test_other_cached_content_cannot_push_the_hourly_count_out(self):
        for i in range(owner_alerts.ALERTS_PER_HOUR):
            owner_alerts.alert_signup(AppSignup.objects.create(email=f"p{i}@plant.com"))
        for i in range(400):  # weather points and the like: the default cache holds 300 entries
            cache.set(f"wx:{i}", {"temp": i}, 600)
        sent = len(self.emails())
        owner_alerts.alert_signup(AppSignup.objects.create(email="one-more@plant.com"))
        self.assertEqual(len(self.emails()), sent)  # still capped


# ---- The cron: interrupted safety tests, and Zero Hour files before Zero Hour pushes --------------------------------------

class CronHousekeepingTests(TestCase):
    def setUp(self):
        cache.clear()

    def run_cron(self, minute=20, **patches):
        """A cron run at `minute` past the hour, with the sub-commands replaced. Returns (output, error or None)."""
        out, error = StringIO(), None
        clock = Mock(now=lambda: timezone.now().replace(minute=minute))
        with patch(f"{CRON}.call_command"), patch(f"{CRON}.timezone", clock):
            try:
                call_command("cron", stdout=out)
            except CommandError as err:
                error = err
        return out.getvalue(), error

    def test_a_safety_test_killed_by_a_deploy_is_marked_failed_without_anyone_opening_the_admin(self):
        run = MondayEvalRun.objects.create(model="test-model", status="running", progress="3 of 12")
        with patch(f"{CRON}.sync_episodes", return_value=[]):
            out, error = self.run_cron()
        run.refresh_from_db()
        self.assertEqual(run.status, "failed")
        self.assertIsNotNone(run.finished_at)
        self.assertIn("Interrupted", run.summary)
        self.assertIn("1 safety test run(s) marked as failed", out)
        self.assertIsNone(error)

    def test_a_safety_test_that_is_still_alive_is_left_alone(self):
        run = MondayEvalRun.objects.create(model="test-model", status="running")
        MondayLock.objects.create(name="eval", locked_at=timezone.now())  # its sign of life, refreshed every minute
        with patch(f"{CRON}.sync_episodes", return_value=[]):
            out, error = self.run_cron()
        run.refresh_from_db()
        self.assertEqual(run.status, "running")
        self.assertNotIn("safety test", out)

    def test_a_fault_in_the_safety_test_check_is_one_failed_step_not_the_end_of_the_run(self):
        ran = []
        with patch("monday.eval_runner.close_stale_runs", side_effect=RuntimeError("boom")), self.assertLogs(CRON, level="ERROR"), \
             patch(f"{CRON}.sync_episodes", return_value=[]), patch(f"{CRON}.retry_suggestions", side_effect=lambda: ran.append("suggestions") or 0):
            out, error = self.run_cron()
        self.assertEqual(ran, ["suggestions"])
        self.assertIn("Safety test runs", str(error))

    def test_the_monday_minute_push_goes_out_with_the_other_pushes_ahead_of_the_slow_steps(self):
        order = []
        with patch("monday.push.send_due", side_effect=lambda: order.append("monday push") or ["Monday Minute push 2026-11-09: OK"]), \
             patch(f"{CRON}.sync_episodes", return_value=[]), patch(f"{CRON}.retry_suggestions", side_effect=lambda: order.append("slow steps") or 0):
            out, error = self.run_cron()
        self.assertEqual(order, ["monday push", "slow steps"])
        self.assertIn("Monday Minute push 2026-11-09: OK", out)
        self.assertIsNone(error)

    def test_every_push_pass_includes_the_monday_minute_push(self):
        command, calls = cron.Command(stdout=StringIO()), []
        command.failed = []
        with patch("monday.push.send_due", side_effect=lambda: calls.append(1) or []), patch(f"{CRON}.call_command"):
            command.pushes()  # what the in-run pass calls every 15 minutes while a slow step is still going
        self.assertEqual(calls, [1])

    def test_a_fault_in_the_monday_minute_push_is_one_failed_step(self):
        ep = self.episode_due()
        with patch("monday.push.send_due", side_effect=RuntimeError("boom")), self.assertLogs(CRON, level="ERROR"), \
             patch(f"{CRON}.sync_episodes", return_value=[]), patch(f"{CRON}.send_episode_push", return_value=(True, {})) as push:
            out, error = self.run_cron()
        push.assert_called_once()  # the pushes behind it still went
        self.assertIn("Monday Minute pushes", str(error))

    def test_the_monday_minute_door_is_where_the_cron_expects_it(self):
        from monday.models import MondayMinute
        from monday.push import send_due

        MondayMinute.objects.all().delete()
        self.assertEqual(send_due(), [])  # no arguments, a list of lines back: the shape the cron calls it in

    def test_removal_requests_the_owner_was_not_told_about_are_sent_again(self):
        ran = []
        with patch("talks.views.retry_removal_request_notices", side_effect=lambda: ran.append("notices") or 0), \
             patch(f"{CRON}.sync_episodes", return_value=[]):
            out, error = self.run_cron()
        self.assertEqual(ran, ["notices"])
        self.assertIsNone(error)
        with patch("talks.views.retry_removal_request_notices", side_effect=RuntimeError("boom")), self.assertLogs(CRON, level="ERROR"), \
             patch(f"{CRON}.sync_episodes", return_value=[]), patch(f"{CRON}.retry_invite_tags", side_effect=lambda: ran.append("later step") or 0):
            out, error = self.run_cron()
        self.assertEqual(ran, ["notices", "later step"])  # a fault there is one failed step
        self.assertIn("Removal request notices", str(error))

    def episode_due(self):
        Episode.objects.all().delete()
        return Episode.objects.create(number=92, title="Ep", hazard="h", story="s", send_push=True, release_at=timezone.now() - dt.timedelta(hours=2))

    def test_the_hourly_look_for_zero_hour_files_comes_before_the_episode_push(self):
        ep, seen = self.episode_due(), []

        def look(**kwargs):  # the hourly look finds the episode's video in GoHighLevel
            Episode.objects.filter(pk=ep.pk).update(video_url="https://cdn.example/ZH_E92_720p.mp4")
            return ["EP 92: linked"]

        def push(episode):  # phones refetch the moment this lands
            seen.append(Episode.objects.get(pk=episode.pk).video_url)
            return True, {}

        with patch(f"{CRON}.sync_episodes", side_effect=look) as sync, patch(f"{CRON}.send_episode_push", side_effect=push):
            out, error = self.run_cron(minute=5)
        self.assertEqual(seen, ["https://cdn.example/ZH_E92_720p.mp4"])  # the video was on the episode when the push went
        sync.assert_called_once_with(timeout=cron.ZERO_HOUR_LOOK)  # once a run, and with a short limit: a push waits behind it
        self.assertLess(cron.ZERO_HOUR_LOOK, 30)
        self.assertIsNone(error)

    def test_a_failed_look_does_not_hold_the_episode_push_back(self):
        self.episode_due()
        with patch(f"{CRON}.sync_episodes", side_effect=GhlError("GET /medias/files -> TimeoutError: timed out")), \
             patch(f"{CRON}.send_episode_push", return_value=(True, {})) as push:
            out, error = self.run_cron(minute=5)
        push.assert_called_once()
        self.assertIn("Zero Hour sync failed", out)

    def test_outside_the_first_quarter_hour_there_is_no_look_and_the_push_still_goes(self):
        self.episode_due()
        with patch(f"{CRON}.sync_episodes", return_value=[]) as sync, patch(f"{CRON}.send_episode_push", return_value=(True, {})) as push:
            self.run_cron(minute=20)
        sync.assert_not_called()
        push.assert_called_once()

    @override_settings(**GHL_ON)
    def test_the_time_limit_reaches_the_listing_call(self):
        with patch("talks.ghl.request", return_value={"files": []}) as request:
            zero_hour.sync_episodes(timeout=7)
        self.assertEqual(request.call_args.kwargs["timeout"], 7)


# ---- Admin: OSHA sections and amendments come from the sync, so there is nothing to add by hand -----------------------------

@override_settings(STORAGES={"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
                             "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
class RegsAdminTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client.force_login(get_user_model().objects.create_superuser("owner", "owner@example.com", "a-long-test-password"))
        RegSection.objects.all().delete()
        self.section = RegSection.objects.create(section="1910.147", heading="The control of hazardous energy")
        self.change = RegChange.objects.create(section=self.section, new_hash="b" * 64)

    def test_the_add_pages_answer_403_instead_of_a_server_error(self):
        for model, rows in (("regsection", RegSection), ("regchange", RegChange)):
            with self.subTest(model):
                before = rows.objects.count()
                with self.assertLogs("django.request", level="WARNING"):  # Django notes each 403 it answers
                    self.assertEqual(self.client.get(f"/admin/regs/{model}/add/").status_code, 403)
                    self.assertEqual(self.client.post(f"/admin/regs/{model}/add/", {"_save": "Save"}).status_code, 403)
                self.assertEqual(rows.objects.count(), before)

    def test_the_lists_show_no_add_link_and_the_rows_still_open(self):
        for model, pk in (("regsection", self.section.pk), ("regchange", self.change.pk)):
            with self.subTest(model):
                page = self.client.get(f"/admin/regs/{model}/")
                self.assertEqual(page.status_code, 200)
                self.assertNotContains(page, f"/admin/regs/{model}/add/")
                self.assertEqual(self.client.get(f"/admin/regs/{model}/{pk}/change/").status_code, 200)
        self.assertNotContains(self.client.get("/admin/"), "/admin/regs/regsection/add/")
        # Ticking "reviewed" on an amendment is the one thing done by hand, and it still saves.
        r = self.client.post(f"/admin/regs/regchange/{self.change.pk}/change/", {"reviewed": "on", "_save": "Save"})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(RegChange.objects.get(pk=self.change.pk).reviewed)


# ---- A year sync that could not run is not "done" -------------------------------------------------------------------------

class YearSyncNotConfiguredTests(TestCase):
    @override_settings(GHL_PRIVATE_TOKEN="", GHL_LOCATION_ID="")
    def test_the_job_waits_instead_of_being_marked_done(self):
        job = GhlSync.objects.create(year=2028, requested_by="ghl")
        out = StringIO()
        with patch(f"{CRON}.call_command"), patch(f"{CRON}.sync_episodes", return_value=[]):
            call_command("cron", stdout=out)  # and the run itself is not a failure
        job.refresh_from_db()
        self.assertEqual(job.status, "pending")
        self.assertIsNone(job.finished_at)
        self.assertIn("not configured", job.log)
        self.assertIn("2028", out.getvalue())

    @override_settings(GHL_PRIVATE_TOKEN="token", GHL_LOCATION_ID="loc")
    def test_it_runs_once_the_settings_are_back_and_real_failures_are_still_marked_failed(self):
        job = GhlSync.objects.create(year=2028)
        with patch("talks.ghl.request", return_value={"builders": []}), patch(f"{CRON}.call_command"), patch(f"{CRON}.sync_episodes", return_value=[]):
            call_command("cron", stdout=StringIO())
        job.refresh_from_db()
        self.assertEqual(job.status, "done")
        job2 = GhlSync.objects.create(year=2029)
        with patch("talks.ghl.request", side_effect=GhlError("GET /emails/builder -> 500", status=500)), \
             patch(f"{CRON}.call_command"), patch(f"{CRON}.sync_episodes", return_value=[]):
            call_command("cron", stdout=StringIO())
        job2.refresh_from_db()
        self.assertEqual(job2.status, "failed")


# ---- The weekly regulation sync stays weekly --------------------------------------------------------------------------

def postgres_order(real=QuerySet.order_by):
    """PostgreSQL puts empty values FIRST when sorting newest-first; SQLite (used by this test suite) puts them last.
    This makes order_by behave the PostgreSQL way, so the bug shows here too."""
    def order_by(qs, *fields):
        return real(qs, *[F(f[1:]).desc(nulls_first=True) if isinstance(f, str) and f.startswith("-") else f for f in fields])
    return patch.object(QuerySet, "order_by", order_by)


class RegsSyncGuardTests(TestCase):
    def setUp(self):
        RegSection.objects.all().delete()
        now = timezone.now()
        for n in range(4):
            RegSection.objects.create(section=f"1910.{100 + n}", fetched_at=now - dt.timedelta(hours=1))

    def runs(self, **options):
        with patch("regs.management.commands.regs_sync.sync", return_value=["ok"]) as sync, postgres_order():
            call_command("regs_sync", stdout=StringIO(), **options)
        return sync.call_count

    def test_a_section_that_was_never_fetched_does_not_make_every_run_sync(self):
        RegSection.objects.create(section="1910.999")  # never fetched: it failed to download
        self.assertEqual(self.runs(), 0)
        self.assertEqual(self.runs(force=True), 1)

    def test_it_syncs_weekly_and_a_missing_section_is_tried_again_after_a_day(self):
        self.assertEqual(self.runs(), 0)
        RegSection.objects.update(fetched_at=timezone.now() - dt.timedelta(days=2))
        self.assertEqual(self.runs(), 0)  # everything is there: wait for the week
        RegSection.objects.create(section="1910.999")
        self.assertEqual(self.runs(), 1)  # one is missing: do not wait a whole week for it
        RegSection.objects.filter(fetched_at__isnull=False).update(fetched_at=timezone.now() - dt.timedelta(days=8))
        RegSection.objects.filter(section="1910.999").delete()
        self.assertEqual(self.runs(), 1)

    def test_an_empty_library_syncs(self):
        RegSection.objects.all().delete()
        self.assertEqual(self.runs(), 1)
