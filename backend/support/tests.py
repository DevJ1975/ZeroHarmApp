"""Tests for support tickets: the three phone endpoints, crash grouping, the owner's emails, the reporter's contact
in GoHighLevel, the cron step, the console endpoints, the admin and the clean-up."""
import datetime as dt
import importlib
import io
import json
import os
import pathlib
import random
import re
import subprocess
import sys
import threading
import uuid
from unittest import mock, skipUnless

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.core.cache import cache, caches
from django.core.management import call_command
from django.db import connection
from django.test import Client, SimpleTestCase, TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from backoffice import metrics
from monday.api import _hash
from talks import owner_alerts
from talks.ghl import GhlError
from talks.integrations import note_mark

from . import alerts, api, text
from .models import CrashKey, CrashReport, Ticket

INSTALL = "zh-m1abcd-0123456789abcdef01234567"
OTHER_PHONE = "zh-m1wxyz-76543210fedcba9876543210"
ADDRESS = "203.0.113.77"
OWNER = "owner@example.com"
KEY = "console-test-key-long-and-random"
GHL_ON = dict(GHL_PRIVATE_TOKEN="token", GHL_LOCATION_ID="loc", OWNER_ALERT_EMAIL=OWNER)
PLAIN_STATIC = {"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
                "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}}

REPORT = {"client_key": "rep-0001-abcdef", "install_id": INSTALL, "source": "form",
          "text": "The talk list will not load.\nIt spins forever.", "app_version": "1.0.0", "platform": "android",
          "os_version": "14", "device": "Pixel 8", "screen": "/talks", "lang": "en"}
CRASH = {"client_key": "crash-0001-abcdef", "install_id": INSTALL, "name": "TypeError", "message": "undefined is not a function",
         "stack": "TypeError: undefined is not a function\n    at render (index.android.bundle:1:234567)\n    at anonymous (index.android.bundle:1:99)",
         "fatal": True, "screen": "/otis", "app_version": "1.0.0", "platform": "android", "os_version": "14", "device": "Pixel 8"}


class FakeGhl:
    """Stands in for GoHighLevel. Records every call made through talks.ghl.request; nothing touches the network."""

    def __init__(self):
        self.down, self.calls = False, []
        self.fail = {}                 # (method, path) -> (status, body): GoHighLevel answers that call with an error
        self.notes = {}                # contact id -> the notes on it
        self.lose_note_answer = False  # the note is stored, but its answer never comes back

    def request(self, method, path, query=None, body=None, raw=None, content_type="application/json", timeout=30):
        self.calls.append((method, path, body or query, timeout))
        if self.down:
            raise GhlError(f"{method} {path} -> timed out")
        if (method, path) in self.fail:
            status, said = self.fail[(method, path)]
            raise GhlError(f"{method} {path} -> {status}: {said}", status=status, body=said)
        if path == "/contacts/upsert":
            return {"contact": {"id": "owner1" if body["email"] == OWNER else "reporter1"}}
        if path.endswith("/notes"):
            contact = path.split("/")[2]
            if method == "GET":
                return {"notes": [{"body": note} for note in self.notes.get(contact, [])]}
            self.notes.setdefault(contact, []).append(body["body"])
            if self.lose_note_answer:
                raise GhlError(f"{method} {path} -> timed out")
        return {}

    def to(self, path, method="POST"):
        return [c for c in self.calls if c[1] == path and c[0] == method]

    @property
    def emails(self):
        return [c[2] for c in self.to("/conversations/messages")]


@override_settings(SECRET_KEY="test", SUPPORT_ENABLED=True, PUBLIC_URL="", CONSOLE_KEY=KEY)
class SupportCase(TestCase):
    def setUp(self):
        cache.clear()
        caches["shared"].clear()
        self.ghl = FakeGhl()
        patcher = mock.patch("talks.ghl.request", side_effect=self.ghl.request)
        patcher.start()
        self.addCleanup(patcher.stop)

    def post(self, path, body, ip=ADDRESS, **extra):
        data = body if isinstance(body, str) else json.dumps(body)
        return self.client.post(f"/api/v2/support/{path}", data, content_type="application/json", HTTP_X_FORWARDED_FOR=ip, **extra)

    def report(self, ip=ADDRESS, **changes):
        return self.post("report", {**REPORT, **changes}, ip=ip)

    def crash(self, ip=ADDRESS, **changes):
        return self.post("crash", {**CRASH, **changes}, ip=ip)

    def later(self, minutes=5):
        return timezone.now() + dt.timedelta(minutes=minutes)


# ---- A person reports a problem ----------------------------------------------------------------------

class ReportTests(SupportCase):
    def test_a_report_becomes_a_ticket_with_a_number(self):
        r = self.report(email="Jane@Plant.com", name="Jane Doe", may_contact=True)
        t = Ticket.objects.get()
        self.assertEqual((r.status_code, r.json()), (200, {"number": f"ZH-{t.pk}", "status": "new"}))
        self.assertEqual((t.kind, t.source, t.status, t.count), ("problem", "form", "new", 1))
        self.assertEqual((t.title, t.text), ("The talk list will not load.", "The talk list will not load.\nIt spins forever."))
        self.assertEqual((t.app_version, t.platform, t.os_version, t.device, t.screen, t.lang), ("1.0.0", "android", "14", "Pixel 8", "/talks", "en"))
        self.assertEqual((t.name, t.email, t.may_contact, t.client_key), ("Jane Doe", "Jane@Plant.com", True, "rep-0001-abcdef"))
        self.assertEqual((t.fingerprint, t.reply, t.owner_note, t.question, t.answer), ("", "", "", "", ""))

    def test_only_the_hash_of_the_install_id_is_kept_and_never_the_address(self):
        self.report(ip=f"6.6.6.6, {ADDRESS}")
        self.crash(ip=f"6.6.6.6, {ADDRESS}")
        self.assertEqual(Ticket.objects.get(install_hash=_hash(INSTALL)).kind, "problem")  # a crash is kept under another hash
        self.assertEqual(CrashReport.objects.get().install_hash, api.crash_hash(INSTALL))
        for model in (Ticket, CrashReport):
            self.assertFalse(any("address" in f.name or f.name in ("ip", "network") for f in model._meta.get_fields()))
            stored = json.dumps(list(model.objects.values()), default=str)
            for secret in (INSTALL, ADDRESS, "6.6.6.6", _hash(f"net:{ADDRESS}")):
                self.assertNotIn(secret, stored)
        keys = " ".join(str(k) for k in list(caches["limits"]._cache) + list(cache._cache))
        self.assertNotIn(ADDRESS, keys)
        self.assertIn("throttle:support-report:", keys)

    def test_the_same_client_key_again_returns_the_same_ticket_and_makes_nothing(self):
        first = self.report()
        again = self.report(text="Sent again with other words, which changes nothing.")
        self.assertEqual(again.json(), first.json())
        self.assertEqual(Ticket.objects.count(), 1)
        self.assertEqual(Ticket.objects.get().text, REPORT["text"])
        # The status in the answer is the ticket's status now, not what it was when it was first sent.
        Ticket.objects.update(status=Ticket.FIXED)
        self.assertEqual(self.report().json()["status"], "fixed")

    def test_two_phones_may_use_the_same_client_key(self):
        a, b = self.report().json(), self.report(install_id=OTHER_PHONE).json()
        self.assertNotEqual(a["number"], b["number"])
        self.assertEqual(Ticket.objects.count(), 2)

    def test_bodies_that_do_not_fit_the_contract_are_refused_and_nothing_is_kept(self):
        bad = [
            {"client_key": "short"}, {"client_key": "k" * 65}, {"client_key": None},
            {"install_id": "short"}, {"install_id": "has spaces in it, no good"}, {"install_id": "x" * 65},
            {"text": "hey"}, {"text": "     \n  "}, {"text": "x" * 4001}, {"text": ["a", "list"]},
            {"source": "crash"}, {"source": ""}, {"platform": "windows"}, {"lang": "fr"}, {"may_contact": "perhaps"},
        ]
        for change in bad:
            with self.subTest(change=str(change)[:60]):
                self.assertEqual(self.report(**change).status_code, 422)
        for key in ("client_key", "install_id", "source", "text"):
            with self.subTest(missing=key):
                self.assertEqual(self.post("report", {k: v for k, v in REPORT.items() if k != key}).status_code, 422)
        for body in ("[1, 2]", '"text"', "not json", "[" * 5000):
            with self.subTest(body=body[:20]):
                self.assertIn(self.post("report", body).status_code, (400, 422))
        self.assertEqual(Ticket.objects.count(), 0)

    def test_text_at_the_limits_is_taken(self):
        self.assertEqual(self.report(text="12345").status_code, 200)
        self.assertEqual(self.report(client_key="rep-0002-abcdef", text="x" * 4000).status_code, 200)
        self.assertEqual(self.report(client_key="k" * 8).status_code, 200)
        self.assertEqual(self.report(client_key="k" * 64).status_code, 200)
        self.assertEqual(Ticket.objects.count(), 4)

    def test_details_about_the_phone_are_cut_to_size_never_a_reason_to_refuse(self):
        r = self.report(device="D" * 300, os_version=34, app_version="1.0.0-" + "b" * 50, screen="/talk/12?ref=jane@plant.com#top",
                        name="N" * 300, email=None, lang=None, platform=None, may_contact=None)
        self.assertEqual(r.status_code, 200)
        t = Ticket.objects.get()
        self.assertEqual((len(t.device), t.os_version, len(t.app_version), t.screen, len(t.name)), (60, "34", 20, "/talk/12", 120))
        self.assertEqual((t.email, t.lang, t.platform, t.may_contact), ("", "", "", False))

    def test_an_email_that_could_never_work_is_dropped_and_the_report_is_kept(self):
        for n, email in enumerate(["not an email", "jane@", "@plant.com", "jane@plant", "a b@plant.com"]):
            self.report(client_key=f"rep-bad-email-{n}", email=email, may_contact=True)
        self.assertEqual(Ticket.objects.count(), 5)
        self.assertEqual(set(Ticket.objects.values_list("email", "may_contact")), {("", False)})

    def test_ok_to_reply_means_nothing_without_an_email(self):
        self.report(may_contact=True)
        self.assertFalse(Ticket.objects.get().may_contact)

    def test_characters_the_database_cannot_hold_are_taken_out(self):
        # Sent as raw JSON: a NUL (PostgreSQL refuses it) and half of an emoji (it cannot be written as UTF-8).
        body = json.dumps({**REPORT, "text": "TEXT", "name": "NAME", "device": "DEVICE"})
        body = body.replace("TEXT", "It broke\\u0000 here \\ud83d and\\r\\nagain").replace("NAME", "Ja\\u0000ne\\ud800").replace("DEVICE", "Pix\\u0000el")
        self.assertEqual(self.post("report", body).status_code, 200)
        t = Ticket.objects.get()
        self.assertEqual((t.text, t.name, t.device), ("It broke here  and\nagain", "Ja ne", "Pix el"))
        t.text.encode("utf-8")

    def test_a_flagged_otis_answer_keeps_the_question_and_the_answer(self):
        r = self.report(source="otis_answer", text="", question="How deep can a trench be before it needs shoring?",
                        answer="Five feet.\nAsk your competent person.", model_key="QWEN3_1_7B", lang="es")
        t = Ticket.objects.get()
        self.assertEqual((r.status_code, r.json()["number"]), (200, t.number))
        self.assertEqual((t.kind, t.source, t.text, t.title), ("answer", "otis_answer", "Flagged OTIS answer", "Flagged OTIS answer"))
        self.assertEqual((t.question, t.answer, t.model_key), ("How deep can a trench be before it needs shoring?", "Five feet.\nAsk your competent person.", "QWEN3_1_7B"))
        # A short note of their own is allowed for this kind, and long fields are cut, not refused.
        self.report(client_key="rep-0002-abcdef", source="otis_answer", text="No", question="q" * 900, answer="a" * 5000, model_key="m" * 99)
        t = Ticket.objects.get(client_key="rep-0002-abcdef")
        self.assertEqual((t.text, len(t.question), len(t.answer), len(t.model_key)), ("No", 500, 2000, 60))

    def test_a_problem_report_never_carries_the_chat(self):
        self.report(source="otis", question="What I asked OTIS", answer="What OTIS said", model_key="QWEN3_1_7B")
        t = Ticket.objects.get()
        self.assertEqual((t.kind, t.source, t.question, t.answer, t.model_key), ("problem", "otis", "", "", ""))

    def test_a_body_over_32_kb_is_turned_away_before_it_is_read(self):
        r = self.report(text="x" * 3000, question="q" * 40000)
        self.assertEqual((r.status_code, r.json()), (413, {"error": "That is too large to send."}))
        self.assertEqual(self.post("crash", {**CRASH, "stack": "s" * 40000}).status_code, 413)
        self.assertEqual(self.post("mine", {"install_id": INSTALL, "padding": "p" * 40000}).status_code, 413)
        self.assertEqual((Ticket.objects.count(), CrashReport.objects.count()), (0, 0))
        # Just under the limit is read as usual.
        self.assertEqual(self.post("crash", {**CRASH, "stack": "s" * 30000}).status_code, 200)

    @override_settings(SUPPORT_ENABLED=False)
    def test_switched_off_answers_kindly_and_keeps_nothing(self):
        self.assertEqual(self.report().json(), {"number": "", "status": "off"})
        self.assertEqual(self.crash().json(), {"ok": True, "number": ""})
        self.assertEqual(self.post("mine", {"install_id": INSTALL}).json(), {"tickets": []})
        self.assertEqual((Ticket.objects.count(), CrashReport.objects.count()), (0, 0))

    def test_one_network_gets_thirty_reports_an_hour(self):
        codes = [self.report(client_key=f"rep-flood-{n:04d}").status_code for n in range(32)]
        self.assertEqual(codes, [200] * 30 + [429, 429])
        self.assertEqual(Ticket.objects.count(), 30)
        # A made-up first hop does not buy a new allowance; another network has its own.
        self.assertEqual(self.report(client_key="rep-forged-0001", ip=f"9.9.9.9, {ADDRESS}").status_code, 429)
        self.assertEqual(self.report(client_key="rep-other-0001", ip="198.51.100.4").status_code, 200)

    def test_each_endpoint_has_its_own_allowance(self):
        for n in range(31):
            self.report(client_key=f"rep-flood-{n:04d}")
        self.assertEqual(self.report(client_key="rep-one-too-many").status_code, 429)
        # Reports used up: crash reports, "My reports" and the rest of the app still work from the same network.
        self.assertEqual(self.crash().status_code, 200)
        self.assertEqual(self.post("mine", {"install_id": INSTALL}).status_code, 200)
        opened = self.client.post("/api/v2/app/open", json.dumps({"install_id": INSTALL, "platform": "ios"}),
                                  content_type="application/json", HTTP_X_FORWARDED_FOR=ADDRESS)
        self.assertEqual(opened.status_code, 200)

    def test_crash_and_mine_get_sixty_an_hour(self):
        codes = [self.crash(client_key=f"crash-flood-{n:04d}").status_code for n in range(62)]
        self.assertEqual(codes, [200] * 60 + [429, 429])
        codes = [self.post("mine", {"install_id": INSTALL}).status_code for n in range(62)]
        self.assertEqual(codes, [200] * 60 + [429, 429])

    def test_the_phone_gets_its_answer_when_gohighlevel_is_not_set_up(self):
        self.assertEqual(self.report().status_code, 200)
        self.assertEqual(self.ghl.calls, [])
        self.assertIsNone(Ticket.objects.get().owner_alerted_at)


# ---- The app reports a crash by itself ----------------------------------------------------------------

class CrashTests(SupportCase):
    def test_a_crash_becomes_a_ticket_and_a_report_row(self):
        r = self.crash()
        t, row = Ticket.objects.get(), CrashReport.objects.get()
        self.assertEqual((r.status_code, r.json()), (200, {"ok": True, "number": f"ZH-{t.pk}"}))
        self.assertEqual((t.kind, t.source, t.status, t.count, t.alerted_count), ("crash", "crash", "new", 1, 0))
        self.assertEqual((t.title, t.text, t.client_key), ("TypeError: undefined is not a function", "undefined is not a function", ""))
        self.assertEqual((t.app_version, t.platform, t.os_version, t.device, t.screen), ("1.0.0", "android", "14", "Pixel 8", "/otis"))
        self.assertEqual(len(t.fingerprint), 64)
        self.assertEqual((row.ticket, row.name, row.message, row.fatal, row.client_key), (t, "TypeError", "undefined is not a function", True, "crash-0001-abcdef"))
        self.assertEqual(row.stack.splitlines()[1], "    at render (index.android.bundle:1:234567)")  # line breaks and the place in the code are kept
        self.assertEqual((row.app_version, row.platform, row.os_version, row.device, row.screen), ("1.0.0", "android", "14", "Pixel 8", "/otis"))

    def test_the_same_error_on_the_same_version_and_platform_is_one_ticket_with_a_count(self):
        first = self.crash(message="Item 12 not found in list 0x7ffe12ab").json()
        second = self.crash(client_key="crash-0002-abcdef", install_id=OTHER_PHONE, message="Item 97 not found in list 0x1c", device="iPhone 15").json()
        third = self.crash(client_key="crash-0003-abcdef", message="Item 5 not found in list 0xdeadbeef", stack="").json()
        self.assertEqual(first["number"], second["number"])
        self.assertEqual(first["number"], third["number"])
        t = Ticket.objects.get()
        self.assertEqual((t.count, t.crashes.count(), t.status), (3, 3, "new"))
        self.assertEqual(t.device, "Pixel 8")  # the ticket keeps the first report's details; each row keeps its own
        self.assertGreaterEqual(t.last_seen, t.first_seen)

    def test_another_version_platform_name_or_message_is_another_ticket(self):
        self.crash()
        for n, change in enumerate([{"app_version": "1.0.1"}, {"platform": "ios"}, {"name": "RangeError"}, {"message": "null is not an object"}]):
            self.crash(client_key=f"crash-other-{n:04d}", **change)
        self.assertEqual(Ticket.objects.count(), 5)
        self.assertEqual(set(Ticket.objects.values_list("count", flat=True)), {1})

    def test_the_same_client_key_again_changes_nothing(self):
        first = self.crash()
        again = self.crash()
        self.assertEqual(again.json(), first.json())
        self.assertEqual((Ticket.objects.get().count, CrashReport.objects.count()), (1, 1))

    def test_a_closed_crash_that_comes_back_opens_again_as_new(self):
        self.crash()
        Ticket.objects.update(status=Ticket.CLOSED, closed_at=timezone.now(), alerted_count=1)
        self.crash(client_key="crash-0002-abcdef")
        t = Ticket.objects.get()
        self.assertEqual((t.status, t.closed_at, t.count, t.alerted_count), ("new", None, 2, 0))

    def test_a_fixed_crash_keeps_counting_quietly(self):
        # Fixed means fixed in a newer version: phones still on the old one go on sending it, and that is not news.
        self.crash()
        closed = timezone.now()
        Ticket.objects.update(status=Ticket.FIXED, closed_at=closed, alerted_count=1)
        self.crash(client_key="crash-0002-abcdef")
        t = Ticket.objects.get()
        self.assertEqual((t.status, t.closed_at, t.count, t.alerted_count), ("fixed", closed, 2, 1))
        self.assertEqual(alerts.crashes_to_report().count(), 0)

    def test_only_the_newest_reports_are_kept_and_all_are_counted(self):
        with mock.patch.object(api, "CRASH_ROWS_KEPT", 3):
            for n in range(8):
                self.crash(client_key=f"crash-many-{n:04d}")
        t = Ticket.objects.get()
        self.assertEqual(t.count, 8)
        self.assertEqual(sorted(t.crashes.values_list("client_key", flat=True)), ["crash-many-0005", "crash-many-0006", "crash-many-0007"])

    def test_made_up_crashes_are_turned_away_past_the_daily_limit_and_known_ones_still_count(self):
        with mock.patch.object(alerts, "NEW_CRASHES_PER_DAY", 3):
            answers = [self.crash(ip=f"198.51.100.{n}", client_key=f"crash-junk-{n:04d}", name=f"Junk{'ABCDE'[n]}") for n in range(5)]
            # Never a 200 for one that was not saved: the phone deletes a report once it has a 200, and keeps it otherwise.
            self.assertEqual([r.status_code for r in answers], [200, 200, 200, 503, 503])
            self.assertEqual(answers[3]["Retry-After"], str(api.TRY_LATER))
            self.assertEqual((Ticket.objects.count(), CrashReport.objects.count()), (3, 3))
            # A crash already known is still counted, and yesterday's new ones no longer count against today.
            self.assertEqual(self.crash(client_key="crash-junk-again", name="JunkA").json()["number"], answers[0].json()["number"])
            self.assertEqual(Ticket.objects.get(title="JunkA: undefined is not a function").count, 2)
            Ticket.objects.filter(title__startswith="JunkB").update(created_at=timezone.now() - dt.timedelta(hours=25))
            # The phone sends the one it kept again, and now it is saved.
            self.assertTrue(self.crash(ip="198.51.100.3", client_key="crash-junk-0003", name="JunkD").json()["number"])

    def test_one_network_cannot_use_up_the_room_for_new_crashes_that_everyone_shares(self):
        with mock.patch.object(alerts, "NEW_CRASHES_PER_NETWORK", 3):
            codes = [self.crash(client_key=f"crash-flood-{n:04d}", name=f"Flood{'ABCDE'[n]}").status_code for n in range(5)]
            self.assertEqual(codes, [200, 200, 200, 429, 429])
            # A crash already known from that network still counts, and another network can still report a new one.
            self.assertEqual(self.crash(client_key="crash-flood-again", name="FloodA").status_code, 200)
            self.assertEqual(self.crash(ip="198.51.100.9", client_key="crash-other-net", name="RealError").status_code, 200)
            self.assertEqual(Ticket.objects.count(), 4)
            # The next day the network has its room back.
            with mock.patch("support.api.timezone.now", return_value=timezone.now() + dt.timedelta(days=1)):
                self.assertEqual(self.crash(client_key="crash-flood-0004", name="FloodE").status_code, 200)

    def test_personal_details_are_taken_out_of_crash_text_before_it_is_saved(self):
        self.crash(
            name="Error for bob@example.com",
            message="Could not load https://api.example.com/v1/me?token=SECRETTOKEN&user=bob for bob.smith@example.com, call 555-123-4567, card 4111111111111111",
            stack="Error: failed\n    at load (https://cdn.example.com/app.js?session=SECRETSESSION:12:34)\n    at open (/data/user/0/app/x.js?key=SECRETKEY:3:4)\n"
                  "    at go (index.android.bundle:1:234567) from 10.20.30.40",
            screen="/talk/12?email=bob@example.com",
        )
        t, row = Ticket.objects.get(), CrashReport.objects.get()
        stored = json.dumps(list(Ticket.objects.values()) + list(CrashReport.objects.values()), default=str)
        for secret in ("bob@example.com", "bob.smith", "SECRETTOKEN", "SECRETSESSION", "SECRETKEY", "555-123-4567", "4111111111111111", "10.20.30.40", "user=bob"):
            self.assertNotIn(secret, stored)
        self.assertEqual(row.name, "Error for [email]")
        self.assertEqual(row.message, "Could not load https://api.example.com/v1/me for [email], call [phone], card [number]")
        self.assertEqual(row.stack.splitlines()[1:], ["    at load (https://cdn.example.com/app.js:12:34)", "    at open (/data/user/0/app/x.js:3:4)",
                                                      "    at go (index.android.bundle:1:234567) from [address]"])
        self.assertEqual((row.screen, t.screen), ("/talk/12", "/talk/12"))

    def test_two_crashes_that_differ_only_in_a_personal_detail_are_one_ticket(self):
        self.crash(message="Sign-in failed for bob@example.com")
        self.crash(client_key="crash-0002-abcdef", message="Sign-in failed for jane@plant.com")
        self.assertEqual(Ticket.objects.get().count, 2)

    def test_long_crash_text_is_cut_not_refused(self):
        r = self.crash(name="N" * 300, message="m" * 2000, stack="at line\n" * 2000)
        self.assertEqual(r.status_code, 200)
        row = CrashReport.objects.get()
        self.assertEqual((len(row.name), len(row.message)), (120, 500))
        self.assertLessEqual(len(row.stack), 6000)
        self.assertLessEqual(len(Ticket.objects.get().title), 120)

    def test_a_crash_with_no_name_or_message_is_still_counted(self):
        self.assertEqual(self.crash(name="", message=None, stack=None, fatal=None).status_code, 200)
        t = Ticket.objects.get()
        self.assertEqual((t.title, t.text, t.crashes.get().fatal), ("Error", "Error", False))

    def test_bad_crash_bodies_are_refused(self):
        for change in ({"client_key": "short"}, {"install_id": "short"}, {"platform": "windows"}, {"name": ["a"]}, {"fatal": "maybe"}, {"stack": {"a": 1}}):
            with self.subTest(change=str(change)):
                self.assertEqual(self.crash(**change).status_code, 422)
        self.assertEqual(self.post("crash", {k: v for k, v in CRASH.items() if k != "name"}).status_code, 422)
        self.assertEqual((Ticket.objects.count(), CrashReport.objects.count()), (0, 0))

    def test_the_time_from_the_phone_is_used_only_when_it_makes_sense(self):
        hour_ago = timezone.now() - dt.timedelta(hours=1)
        self.crash(at=hour_ago.isoformat())
        self.assertEqual(CrashReport.objects.get().created_at, hour_ago)
        before = timezone.now()
        for n, at in enumerate(["yesterday-ish", 12345, "2099-01-01T00:00:00Z", "2001-01-01T00:00:00Z", "2026-13-45T99:00:00Z", None]):
            self.assertEqual(self.crash(client_key=f"crash-clock-{n:04d}", at=at).status_code, 200)
        self.assertEqual(CrashReport.objects.filter(created_at__gte=before).count(), 6)

    @override_settings(**GHL_ON)
    def test_a_crash_never_emails_anyone_from_the_request(self):
        for n in range(5):
            self.crash(client_key=f"crash-quiet-{n:04d}", email="jane@plant.com", may_contact=True, text="typed words")
        self.assertEqual(self.ghl.calls, [])
        t = Ticket.objects.get()
        self.assertEqual((t.email, t.name, t.may_contact), ("", "", False))  # a crash carries nothing a person typed


@skipUnless(connection.vendor == "postgresql", "Needs a database that lets several requests write at once (PostgreSQL).")
@override_settings(SECRET_KEY="test", SUPPORT_ENABLED=True)
class ManyAtOnceTests(TransactionTestCase):
    """Real requests landing at the same moment, each on its own database connection, the way gunicorn's threads
    serve them. This is what a crash loop on many phones looks like to the server."""

    def at_once(self, bodies, path):
        answers, go = [], threading.Barrier(len(bodies))

        def send(n, body):
            try:
                go.wait(timeout=10)
                r = Client().post(f"/api/v2/support/{path}", json.dumps(body), content_type="application/json", HTTP_X_FORWARDED_FOR=f"198.51.{n % 200}.{n // 200 + 1}")
                answers.append((r.status_code, r.json()))
            finally:
                connection.close()  # this thread's own connection

        threads = [threading.Thread(target=send, args=(n, body)) for n, body in enumerate(bodies)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        return answers

    def test_the_same_new_crash_from_many_phones_at_once_is_one_ticket_with_every_report_counted(self):
        bodies = [{**CRASH, "client_key": f"crash-race-{n:05d}", "install_id": f"zh-race-{n:024d}", "message": f"Cannot read item {n} of undefined"} for n in range(24)]
        answers = self.at_once(bodies, "crash")
        self.assertEqual({code for code, _ in answers}, {200})
        t = Ticket.objects.get()
        self.assertEqual({a["number"] for _, a in answers}, {t.number})
        self.assertEqual((t.count, t.crashes.count()), (24, 24))
        # And again while the ticket is closed: it opens once, and every report is still counted.
        Ticket.objects.update(status=Ticket.CLOSED, alerted_count=24)
        self.at_once([{**b, "client_key": b["client_key"] + "-again"} for b in bodies], "crash")
        t = Ticket.objects.get()
        self.assertEqual((t.count, t.status, t.alerted_count), (48, "new", 0))

    def test_one_crash_report_sent_many_times_at_once_is_counted_once(self):
        answers = self.at_once([CRASH] * 12, "crash")
        self.assertEqual({code for code, _ in answers}, {200})
        self.assertEqual(len({a["number"] for _, a in answers}), 1)
        self.assertEqual((Ticket.objects.get().count, CrashReport.objects.count()), (1, 1))

    def test_one_report_sent_many_times_at_once_is_one_ticket(self):
        answers = self.at_once([REPORT] * 12, "report")
        self.assertEqual({code for code, _ in answers}, {200})
        self.assertEqual(len({a["number"] for _, a in answers}), 1)
        self.assertEqual(Ticket.objects.count(), 1)


# ---- This phone's own reports -------------------------------------------------------------------------

class MineTests(SupportCase):
    def test_it_lists_this_phones_reports_newest_first_with_status_and_reply(self):
        self.report()
        self.report(client_key="rep-0002-abcdef", text="OTIS will not download.")
        self.report(client_key="rep-0003-abcdef", source="otis_answer", text="", question="Q", answer="A")
        self.report(client_key="rep-0004-abcdef", install_id=OTHER_PHONE, text="Somebody else's report.")
        self.crash()
        first = Ticket.objects.get(client_key="rep-0001-abcdef")
        first.set_status(Ticket.FIXED)
        first.reply, first.owner_note = "Fixed in version 1.0.1. Thanks.", "PRIVATE: same as ZH-3"
        first.save()
        r = self.post("mine", {"install_id": INSTALL})
        self.assertEqual(r.status_code, 200)
        tickets = r.json()["tickets"]
        # Not the answer they flagged, not the other phone's report, not the crash.
        self.assertEqual([t["title"] for t in tickets], ["OTIS will not download.", "The talk list will not load."])
        self.assertEqual(set(tickets[1]), {"number", "status", "title", "created_at", "updated_at", "reply"})
        self.assertEqual((tickets[1]["number"], tickets[1]["status"], tickets[1]["reply"]), (first.number, "fixed", "Fixed in version 1.0.1. Thanks."))
        self.assertEqual((tickets[1]["created_at"], tickets[0]["reply"]), (first.created_at.isoformat(), ""))
        self.assertNotIn("PRIVATE", r.content.decode())

    def test_at_most_thirty(self):
        Ticket.objects.bulk_create(Ticket(kind=Ticket.PROBLEM, title=f"t{n}", text="text", install_hash=_hash(INSTALL), client_key=f"key-{n:05d}") for n in range(35))
        self.assertEqual(len(self.post("mine", {"install_id": INSTALL}).json()["tickets"]), 30)

    def test_a_phone_with_no_reports_and_a_bad_install_id(self):
        self.assertEqual(self.post("mine", {"install_id": OTHER_PHONE}).json(), {"tickets": []})
        self.assertEqual(self.post("mine", {"install_id": "short"}).status_code, 422)
        self.assertEqual(self.post("mine", {}).status_code, 422)
        self.assertEqual(self.client.get("/api/v2/support/mine").status_code, 405)


# ---- Emails to the owner ------------------------------------------------------------------------------

@override_settings(**GHL_ON)
class OwnerEmailTests(SupportCase):
    def test_a_report_emails_the_owner_at_once_with_the_short_timeout(self):
        self.report(text="The <b>talk</b> list & feed will not load.\nIt spins forever.", email="jane@plant.com", name="Jane Doe", may_contact=True)
        t = Ticket.objects.get()
        self.assertIsNotNone(t.owner_alerted_at)
        self.assertEqual({c[3] for c in self.ghl.calls}, {owner_alerts.QUICK})
        (email,) = self.ghl.emails
        self.assertEqual((email["contactId"], email["type"]), ("owner1", "Email"))
        self.assertEqual(email["subject"], f"Zero Harm problem report {t.number}: The <b>talk</b> list & feed will not load.")
        html = email["html"]
        for part in (f"Ticket {t.number}: a problem report, sent from the Report a problem form.",
                     "<p style=\"margin:0 0 8px\">The &lt;b&gt;talk&lt;/b&gt; list &amp; feed will not load.</p>", "<p style=\"margin:0 0 8px\">It spins forever.</p>",
                     "App version: 1.0.0. Phone: Pixel 8, Android 14. Screen: /talks. Language: en.",
                     f"When: {owner_alerts._when(t.created_at)}. Times reported: 1.", "Pacific",
                     "Reply to: jane@plant.com (Jane Doe). They said it is OK to reply."):
            self.assertIn(part, html)
        self.assertNotIn("<b>talk</b>", html)
        self.assertNotIn("Open it:", html)  # PUBLIC_URL is blank: no link
        # The reporter's own contact is not touched while the phone waits; the cron does that.
        self.assertEqual([c[2]["email"] for c in self.ghl.to("/contacts/upsert")], [OWNER])

    @override_settings(PUBLIC_URL="https://api.example.com")
    def test_the_email_links_to_the_admin_when_the_public_address_is_set(self):
        self.report()
        t = Ticket.objects.get()
        self.assertIn(f"Open it: https://api.example.com/admin/support/ticket/{t.pk}/change/", self.ghl.emails[0]["html"])

    def test_a_flagged_answer_email_shows_the_question_and_the_answer(self):
        self.report(source="otis_answer", text="This is wrong for my state.", question="How deep before shoring?", answer="Five feet.\nAsk your competent person.", model_key="QWEN3_1_7B")
        t = Ticket.objects.get()
        (email,) = self.ghl.emails
        self.assertEqual(email["subject"], f"Zero Harm OTIS answer flagged {t.number}: This is wrong for my state.")
        for part in ("a flagged OTIS answer, sent with Report this answer", "How deep before shoring?", "Five feet.", "Ask your competent person.",
                     "This is wrong for my state.", "OTIS model: QWEN3_1_7B", "No name or email given."):
            self.assertIn(part, email["html"])

    def test_gohighlevel_down_the_phone_still_gets_its_number_and_the_cron_sends_the_email_once(self):
        self.ghl.down = True
        r = self.report()
        t = Ticket.objects.get()
        self.assertEqual(r.json(), {"number": t.number, "status": "new"})
        self.assertIsNone(t.owner_alerted_at)
        self.ghl.down = False
        self.assertEqual(alerts.run(timezone.now())["reports"], 0)  # too fresh: its own request may still be sending
        self.assertEqual(self.ghl.emails, [])
        said = []
        self.assertEqual(alerts.run(self.later(), say=said.append), {"reports": 1, "crashes": 0, "contacts": 0})
        self.assertEqual(said, ["Support: 1 reports emailed to the owner late"])
        self.assertEqual(len(self.ghl.emails), 1)
        self.assertIsNotNone(Ticket.objects.get().owner_alerted_at)
        # Every later run finds nothing left to do.
        for minutes in (20, 35, 3000):
            self.assertEqual(alerts.run(self.later(minutes)), {"reports": 0, "crashes": 0, "contacts": 0})
        self.assertEqual(len(self.ghl.emails), 1)

    def test_while_gohighlevel_is_not_answering_later_phones_do_not_wait_for_it(self):
        self.ghl.down = True
        self.report()
        tried = len(self.ghl.calls)
        self.report(client_key="rep-0002-abcdef")
        self.assertEqual(len(self.ghl.calls), tried)  # the second request did not try GoHighLevel at all
        self.ghl.down = False
        self.assertEqual(alerts.run(self.later())["reports"], 2)
        self.assertEqual(len(self.ghl.emails), 2)

    def test_the_same_report_sent_twice_is_one_email(self):
        self.report()
        self.report()
        self.assertEqual(alerts.run(self.later())["reports"], 0)
        self.assertEqual(len(self.ghl.emails), 1)

    @override_settings(OWNER_ALERT_EMAIL="")
    def test_no_alert_address_means_no_email_and_the_ticket_waits(self):
        self.report()
        self.assertEqual(alerts.run(self.later()), {"reports": 0, "crashes": 0, "contacts": 0})
        self.assertEqual(self.ghl.calls, [])
        with self.settings(OWNER_ALERT_EMAIL=OWNER):  # the address is set later: nothing was lost
            self.assertEqual(alerts.run(self.later())["reports"], 1)
        self.assertEqual(len(self.ghl.emails), 1)

    def test_a_ticket_the_owner_already_picked_up_needs_no_email(self):
        self.ghl.down = True
        self.report()
        self.ghl.down = False
        Ticket.objects.update(status=Ticket.IN_PROGRESS)
        self.assertEqual(alerts.run(self.later())["reports"], 0)
        self.assertEqual(self.ghl.emails, [])

    def _already_emailed(self, n, minutes_ago=10):
        """n tickets the owner was emailed about one by one a little while ago."""
        base = timezone.now() - dt.timedelta(minutes=minutes_ago)
        Ticket.objects.bulk_create(Ticket(kind=Ticket.PROBLEM, title=f"earlier {i}", text="text", install_hash="h", client_key=f"earlier-{i:04d}",
                                          owner_alerted_at=base + dt.timedelta(seconds=i)) for i in range(n))

    def test_the_hourly_cap_is_counted_from_the_database_and_nothing_is_dropped(self):
        self._already_emailed(alerts.INSTANT_PER_HOUR)
        self.report()
        self.assertEqual(self.ghl.emails, [])  # the hour's single emails are used up
        # Not a count in anyone's memory: with every cache emptied (a restart, or the cron's own process) it still holds.
        cache.clear()
        caches["limits"].clear()
        caches["shared"].clear()
        self.report(client_key="rep-0002-abcdef", text="Second one over the cap.")
        self.assertEqual(self.ghl.emails, [])
        self.assertEqual(Ticket.objects.filter(owner_alerted_at__isnull=True).count(), 2)
        # The cron sends both in ONE list email and stamps them.
        self.assertEqual(alerts.run(self.later())["reports"], 2)
        (email,) = self.ghl.emails
        self.assertEqual(email["subject"], "Zero Harm: 2 reports waiting")
        waiting = Ticket.objects.filter(client_key__startswith="rep-")
        for t in waiting:
            self.assertIn(f"{t.number}, problem report from", email["html"])
        self.assertIn("Second one over the cap.", email["html"])
        self.assertEqual(waiting.filter(owner_alerted_at__isnull=True).count(), 0)
        self.assertEqual(alerts.run(self.later(20))["reports"], 0)
        self.assertEqual(len(self.ghl.emails), 1)

    def test_a_list_email_counts_as_the_one_email_it_was(self):
        self._already_emailed(alerts.INSTANT_PER_HOUR - 2)
        stamp = timezone.now() - dt.timedelta(minutes=5)
        Ticket.objects.bulk_create(Ticket(kind=Ticket.CRASH, title=f"crash {i}", text="text", install_hash="h", fingerprint=f"fp{i}",
                                          alerted_count=1, owner_alerted_at=stamp) for i in range(25))
        self.assertEqual(alerts.emails_last_hour(), alerts.INSTANT_PER_HOUR - 1)
        self.report()
        self.assertEqual(len(self.ghl.emails), 1)

    def test_the_cap_frees_up_after_an_hour(self):
        self._already_emailed(alerts.INSTANT_PER_HOUR, minutes_ago=90)
        self.report()
        self.assertEqual(len(self.ghl.emails), 1)

    def test_many_waiting_reports_go_out_as_lists_oldest_first_until_none_are_left(self):
        self.ghl.down = True
        with mock.patch.object(alerts, "LISTED_PER_EMAIL", 4):
            for n in range(9):
                self.report(client_key=f"rep-many-{n:04d}", text=f"Problem number {n} with the app.", ip=f"198.51.100.{n}")
            self.ghl.down = False
            self.assertEqual(alerts.run(self.later(5))["reports"], 4)
            self.assertEqual(alerts.run(self.later(20))["reports"], 4)
            self.assertEqual(alerts.run(self.later(35))["reports"], 1)
            self.assertEqual(alerts.run(self.later(50))["reports"], 0)
        first, second, third = self.ghl.emails
        self.assertEqual((first["subject"], second["subject"], third["subject"]),
                         ("Zero Harm: 9 reports waiting", "Zero Harm: 5 reports waiting", f"Zero Harm problem report {Ticket.objects.get(client_key='rep-many-0008').number}: Problem number 8 with the app."))
        self.assertIn("Problem number 0 with the app.", first["html"])
        self.assertIn("5 more are waiting.", first["html"])
        self.assertNotIn("Problem number 4 with the app.", first["html"])
        self.assertIn("Problem number 4 with the app.", second["html"])
        self.assertEqual(Ticket.objects.filter(owner_alerted_at__isnull=True).count(), 0)

    def test_a_list_that_gohighlevel_did_not_take_is_sent_on_the_next_run(self):
        self.ghl.down = True
        for n in range(5):
            self.report(client_key=f"rep-many-{n:04d}", ip=f"198.51.100.{n}")
        self.assertEqual(alerts.run(self.later(5))["reports"], 0)
        self.assertEqual(Ticket.objects.filter(owner_alerted_at__isnull=True).count(), 5)
        self.ghl.down = False
        self.assertEqual(alerts.run(self.later(20))["reports"], 5)
        self.assertEqual(len(self.ghl.emails), 1)


@override_settings(**GHL_ON)
class CrashEmailTests(SupportCase):
    def grow(self, count):
        Ticket.objects.filter(kind=Ticket.CRASH).update(count=count)

    def test_new_crashes_go_out_in_one_email_per_run(self):
        self.crash()
        self.crash(client_key="crash-0002-abcdef", name="RangeError", message="Maximum call stack size exceeded", app_version="1.0.1", platform="ios", device="iPhone 15", os_version="18.1")
        self.crash(client_key="crash-0003-abcdef")
        said = []
        self.assertEqual(alerts.run(timezone.now(), say=said.append), {"reports": 0, "crashes": 2, "contacts": 0})
        self.assertEqual(said, ["Support: the owner was emailed about 2 crashes"])
        (email,) = self.ghl.emails
        self.assertEqual(email["subject"], "Zero Harm crashes: 2 new")
        first, second = Ticket.objects.order_by("pk")
        for part in (f"{first.number}, new: TypeError: undefined is not a function. Reported 2 times, app 1.0.0 on Pixel 8, Android 14, first on the screen /otis.",
                     f"{second.number}, new: RangeError: Maximum call stack size exceeded. Reported 1 time, app 1.0.1 on iPhone 15, iOS 18.1",
                     f"last seen {owner_alerts._when(first.last_seen)}", "They hold no names, emails or anything a person typed, and nothing that links them to a person.",
                     "A reply you write on a crash ticket is a private note: nobody sees it."):
            self.assertIn(part, email["html"])
        self.assertEqual([(t.alerted_count, t.owner_alerted_at is not None) for t in (first, second)], [(2, True), (1, True)])
        self.assertEqual(alerts.run(self.later(15))["crashes"], 0)
        self.assertEqual(len(self.ghl.emails), 1)

    @override_settings(PUBLIC_URL="https://api.example.com")
    def test_each_crash_in_the_email_links_to_its_admin_page(self):
        self.crash()
        alerts.run()
        self.assertIn(f"Open it: https://api.example.com/admin/support/ticket/{Ticket.objects.get().pk}/change/", self.ghl.emails[0]["html"])

    def test_the_owner_hears_again_only_at_10_100_and_1000_reports(self):
        self.crash()
        emails = []
        for count in (1, 2, 9, 10, 11, 99, 100, 101, 999, 1000, 1001, 5000, 100000):
            self.grow(count)
            alerts.run(self.later(count))
            emails.append(len(self.ghl.emails))
        #                      1  2  9  10 11 99 100 101 999 1000 1001 5000 100000
        self.assertEqual(emails, [1, 1, 1, 2, 2, 2, 3, 3, 3, 4, 4, 4, 4])
        self.assertEqual(self.ghl.emails[1]["subject"], "Zero Harm crashes: 1 growing")
        self.assertIn("now 10 reports, up from 1 when you were last told", self.ghl.emails[1]["html"])

    def test_a_crash_first_seen_already_in_the_thousands_is_one_email(self):
        self.crash()
        self.grow(7000)
        alerts.run()
        self.grow(90000)
        alerts.run(self.later(15))
        self.assertEqual(len(self.ghl.emails), 1)
        self.assertEqual(Ticket.objects.get().alerted_count, 7000)

    def test_a_crash_loop_on_many_phones_is_one_ticket_and_one_email(self):
        for n in range(200):
            r = self.crash(client_key=f"crash-loop-{n:05d}", install_id=f"zh-loop-{n:024d}", message=f"Cannot read item {n} of undefined", ip=f"198.51.100.{n % 5}")
            self.assertEqual(r.status_code, 200)
        t = Ticket.objects.get()
        self.assertEqual((t.count, t.crashes.count()), (200, api.CRASH_ROWS_KEPT))
        self.assertEqual(self.ghl.calls, [])
        for minutes in (0, 15, 30, 45):
            alerts.run(self.later(minutes))
        self.assertEqual(len(self.ghl.emails), 1)
        self.assertIn("Reported 200 times", self.ghl.emails[0]["html"])

    def test_a_closed_crash_that_comes_back_is_told_again_and_a_fixed_one_is_not(self):
        self.crash()
        self.crash(client_key="crash-0002-abcdef", name="RangeError")
        alerts.run()
        typeerror, rangeerror = Ticket.objects.order_by("pk")
        Ticket.objects.filter(pk=typeerror.pk).update(status=Ticket.CLOSED)
        Ticket.objects.filter(pk=rangeerror.pk).update(status=Ticket.FIXED)
        self.assertEqual(alerts.run(self.later(15))["crashes"], 0)
        self.crash(client_key="crash-0003-abcdef")
        self.crash(client_key="crash-0004-abcdef", name="RangeError")
        self.assertEqual(alerts.run(self.later(30))["crashes"], 1)
        self.assertEqual(len(self.ghl.emails), 2)
        self.assertIn(f"{typeerror.number}, new:", self.ghl.emails[1]["html"])
        self.assertNotIn(rangeerror.number + ",", self.ghl.emails[1]["html"])

    def test_an_email_gohighlevel_did_not_take_is_sent_on_the_next_run_and_nothing_is_stamped_early(self):
        self.crash()
        self.ghl.down = True
        self.assertEqual(alerts.run()["crashes"], 0)
        t = Ticket.objects.get()
        self.assertEqual((t.alerted_count, t.owner_alerted_at), (0, None))
        self.ghl.down = False
        self.assertEqual(alerts.run(self.later(15))["crashes"], 1)
        self.assertEqual(len(self.ghl.emails), 1)

    def test_more_crashes_than_fit_wait_for_the_next_email(self):
        with mock.patch.object(alerts, "LISTED_PER_EMAIL", 2):
            for n in range(3):
                self.crash(client_key=f"crash-kind-{n:04d}", name=f"Error{'ABC'[n]}")
            self.assertEqual(alerts.run()["crashes"], 2)
            self.assertIn("1 more crashes are waiting.", self.ghl.emails[0]["html"])
            self.assertEqual(alerts.run(self.later(15))["crashes"], 1)
            self.assertEqual(alerts.run(self.later(30))["crashes"], 0)
        self.assertEqual(len(self.ghl.emails), 2)

    def test_the_email_says_so_when_the_daily_limit_on_new_crashes_was_reached(self):
        with mock.patch.object(alerts, "NEW_CRASHES_PER_DAY", 2):
            for n in range(4):
                self.crash(ip=f"198.51.100.{n}", client_key=f"crash-junk-{n:04d}", name=f"Junk{'ABCD'[n]}")
            self.assertEqual(alerts.run()["crashes"], 2)
        notice, rollup = self.ghl.emails
        self.assertEqual(notice["subject"], "Zero Harm: new crash reports are being turned away")
        self.assertIn("2 different crashes have come in over the last day.", rollup["html"])
        self.crash(client_key="crash-junk-0009", name="JunkZ")
        alerts.run(self.later(15))
        self.assertNotIn("different crashes have come in", self.ghl.emails[2]["html"])  # under the usual limit of 200 again
        self.assertEqual(len(self.ghl.emails), 3)

    def test_while_a_limit_turns_crashes_away_the_owner_hears_once_a_day_even_with_no_crash_to_list(self):
        with mock.patch.object(alerts, "NEW_CRASHES_PER_DAY", 2):
            for n in range(3):
                self.crash(ip=f"198.51.100.{n}", client_key=f"crash-junk-{n:04d}", name=f"Junk{'ABC'[n]}")
            alerts.run()  # the notice and the list of the two made-up crashes
            self.assertEqual(len(self.ghl.emails), 2)
            for minutes in (15, 30, 45):  # nothing left to list, the limit still holds: no more email that day
                self.assertEqual(alerts.run(self.later(minutes))["crashes"], 0)
            self.assertEqual(len(self.ghl.emails), 2)
            # The next day it still holds (they were made up a minute before midnight, say): one more notice, alone.
            Ticket.objects.update(created_at=timezone.now() + dt.timedelta(hours=23))
            alerts.run(timezone.now() + dt.timedelta(days=1))
        self.assertEqual([e["subject"] for e in self.ghl.emails[1:]], ["Zero Harm crashes: 2 new", "Zero Harm: new crash reports are being turned away"])

    def test_a_network_that_used_up_its_room_is_told_to_the_owner(self):
        with mock.patch.object(alerts, "NEW_CRASHES_PER_NETWORK", 1):
            self.crash(client_key="crash-flood-0001", name="FloodA")
            self.assertEqual(self.crash(client_key="crash-flood-0002", name="FloodB").status_code, 429)
            alerts.run()
            notice = self.ghl.emails[0]
            self.assertEqual(notice["subject"], "Zero Harm: new crash reports are being turned away")
            self.assertIn("One network sent more than 1 new kinds of crash today.", notice["html"])
            alerts.run(self.later(15))
        self.assertEqual(len(self.ghl.emails), 2)  # the notice and the list of FloodA, and no second notice

    @override_settings(OWNER_ALERT_EMAIL="")
    def test_no_alert_address_means_no_crash_email_and_nothing_is_marked_as_told(self):
        self.crash()
        self.assertEqual(alerts.run()["crashes"], 0)
        self.assertEqual((self.ghl.calls, Ticket.objects.get().alerted_count), ([], 0))


# ---- The reporter's contact in GoHighLevel -------------------------------------------------------------

@override_settings(**GHL_ON)
class ReporterContactTests(SupportCase):
    def reporter_calls(self):
        """Calls about the reporter's contact, leaving out the owner's own (the email to the owner)."""
        return [(c[0], c[1]) for c in self.ghl.calls if "reporter1" in c[1] or (c[1] == "/contacts/upsert" and c[2]["email"] != OWNER)]

    def test_a_reporter_who_said_ok_to_reply_is_tagged_and_noted_once(self):
        self.report(email="jane@plant.com", name="Jane van Doe", may_contact=True)
        t = Ticket.objects.get()
        self.assertEqual(self.reporter_calls(), [])
        self.assertEqual(alerts.run(self.later()), {"reports": 0, "crashes": 0, "contacts": 1})
        self.assertEqual(self.reporter_calls(), [("POST", "/contacts/upsert"), ("DELETE", "/contacts/reporter1/tags"), ("POST", "/contacts/reporter1/tags"),
                                                 ("GET", "/contacts/reporter1/notes"), ("POST", "/contacts/reporter1/notes")])
        upsert = [c[2] for c in self.ghl.to("/contacts/upsert") if c[2]["email"] != OWNER][0]
        self.assertEqual((upsert["email"], upsert["firstName"], upsert["lastName"]), ("jane@plant.com", "Jane", "van Doe"))
        self.assertNotIn("tags", upsert)  # tags sent with the upsert would replace every tag the contact has
        # Taken off, then put back on: a "tag added" workflow fires for this ticket even if they reported before.
        self.assertEqual(self.ghl.to("/contacts/reporter1/tags", "DELETE")[0][2], {"tags": ["zero-harm-support-ticket"]})
        self.assertEqual(self.ghl.to("/contacts/reporter1/tags")[0][2], {"tags": ["zero-harm-support-ticket"]})
        (note,) = self.ghl.notes["reporter1"]
        for part in (f"Zero Harm support ticket {t.number}", "What they wrote: The talk list will not load.\nIt spins forever.", "App: 1.0.0 on Pixel 8, Android 14",
                     "OK to reply: yes", f"Ref: {note_mark('ticket', t.pk)}"):
            self.assertIn(part, note)
        t.refresh_from_db()
        self.assertEqual((t.ghl_contact_id, t.ghl_tagged_at is not None, t.ghl_noted_at is not None), ("reporter1", True, True))
        # Every later run leaves the contact alone.
        calls = len(self.ghl.calls)
        for minutes in (20, 35, 50):
            self.assertEqual(alerts.run(self.later(minutes))["contacts"], 0)
        self.assertEqual(len(self.ghl.calls), calls)
        self.assertEqual(len(self.ghl.notes["reporter1"]), 1)

    def test_a_second_ticket_from_the_same_person_fires_the_tag_again(self):
        self.report(email="jane@plant.com", may_contact=True)
        self.report(client_key="rep-0002-abcdef", email="jane@plant.com", may_contact=True, text="Another problem, a day later.")
        self.assertEqual(alerts.run(self.later())["contacts"], 2)
        self.assertEqual(len(self.ghl.to("/contacts/reporter1/tags", "DELETE")), 2)
        self.assertEqual(len(self.ghl.to("/contacts/reporter1/tags")), 2)
        self.assertEqual(len(self.ghl.notes["reporter1"]), 2)

    def test_a_retry_starts_where_the_last_try_stopped(self):
        self.report(email="jane@plant.com", may_contact=True)
        self.ghl.fail[("POST", "/contacts/reporter1/tags")] = (500, "try later")
        self.assertEqual(alerts.run(self.later(5))["contacts"], 0)
        t = Ticket.objects.get()
        self.assertEqual((t.ghl_contact_id, t.ghl_tagged_at, t.ghl_noted_at), ("reporter1", None, None))
        self.ghl.fail = {("POST", "/contacts/reporter1/notes"): (500, "try later")}
        self.assertEqual(alerts.run(self.later(20))["contacts"], 0)
        t.refresh_from_db()
        self.assertEqual((t.ghl_tagged_at is not None, t.ghl_noted_at), (True, None))
        self.ghl.fail = {}
        self.assertEqual(alerts.run(self.later(35))["contacts"], 1)
        calls = self.reporter_calls()
        self.assertEqual(calls.count(("POST", "/contacts/upsert")), 1)        # the contact was made once
        self.assertEqual(calls.count(("POST", "/contacts/reporter1/tags")), 2)  # the failed try, then the one that worked
        self.assertEqual(calls.count(("DELETE", "/contacts/reporter1/tags")), 2)
        self.assertEqual(len(self.ghl.notes["reporter1"]), 1)
        self.assertEqual(len(self.ghl.emails), 1)  # and the owner's email was not sent again along the way

    def test_a_note_whose_answer_was_lost_is_not_added_twice(self):
        self.report(email="jane@plant.com", may_contact=True)
        self.ghl.lose_note_answer = True
        self.assertEqual(alerts.run(self.later(5))["contacts"], 0)
        self.assertIsNone(Ticket.objects.get().ghl_noted_at)
        self.ghl.lose_note_answer = False
        self.assertEqual(alerts.run(self.later(20))["contacts"], 1)
        self.assertEqual(len(self.ghl.notes["reporter1"]), 1)
        self.assertIsNotNone(Ticket.objects.get().ghl_noted_at)

    def test_a_tag_that_is_not_there_to_take_off_does_not_stop_the_rest(self):
        self.report(email="jane@plant.com", may_contact=True)
        self.ghl.fail[("DELETE", "/contacts/reporter1/tags")] = (400, "tag not found")
        self.assertEqual(alerts.run(self.later())["contacts"], 1)
        self.assertEqual(len(self.ghl.notes["reporter1"]), 1)
        # A sign-in or rate-limit answer is a real failure: the step is tried again, the tag is not put on blind.
        self.report(client_key="rep-0002-abcdef", email="jane@plant.com", may_contact=True)
        self.ghl.fail[("DELETE", "/contacts/reporter1/tags")] = (429, "slow down")
        self.assertEqual(alerts.run(self.later(20))["contacts"], 0)
        self.assertIsNone(Ticket.objects.get(client_key="rep-0002-abcdef").ghl_tagged_at)

    def test_nobody_is_added_without_an_email_and_ok_to_reply(self):
        self.report()
        self.report(client_key="rep-0002-abcdef", email="jane@plant.com", may_contact=False)
        self.report(client_key="rep-0003-abcdef", may_contact=True)
        self.crash()
        self.assertEqual(alerts.run(self.later())["contacts"], 0)
        self.assertEqual(self.reporter_calls(), [])
        self.assertFalse(alerts.sync_contact(Ticket.objects.get(client_key="rep-0002-abcdef")))
        self.assertEqual(self.reporter_calls(), [])

    def test_a_flagged_answer_from_someone_who_said_ok_to_reply_is_noted_with_the_answer(self):
        self.report(source="otis_answer", text="Wrong for California.", question="How deep before shoring?", answer="Five feet.", email="jane@plant.com", may_contact=True)
        self.assertEqual(alerts.run(self.later())["contacts"], 1)
        (note,) = self.ghl.notes["reporter1"]
        for part in ("flagged OTIS answer", "Question to OTIS: How deep before shoring?", "OTIS answered: Five feet.", "Their note: Wrong for California."):
            self.assertIn(part, note)

    def test_the_cron_gives_up_on_a_contact_after_two_days(self):
        self.ghl.down = True
        self.report(email="jane@plant.com", may_contact=True)
        self.assertEqual(alerts.sync_waiting_contacts(self.later(60)), 0)
        tried = len(self.ghl.calls)
        self.assertGreater(tried, 0)
        self.ghl.down = False
        self.assertEqual(alerts.sync_waiting_contacts(self.later(60 * 24 * 2 + 5)), 0)
        self.assertEqual(self.reporter_calls().count(("POST", "/contacts/upsert")), 1)  # only the try from before the two days were up
        self.assertEqual(alerts.sync_waiting_contacts(self.later(60 * 24 * 2 - 5)), 1)

    def test_at_most_fifty_a_run_and_stuck_ones_do_not_block_the_rest(self):
        Ticket.objects.bulk_create(Ticket(kind=Ticket.PROBLEM, title=f"t{n}", text="text", install_hash="h", client_key=f"key-{n:05d}",
                                          email=f"p{n}@plant.com", may_contact=True) for n in range(120))
        self.ghl.down = True
        tried = set()
        for run in range(3):
            before = len(self.ghl.calls)
            with self.assertLogs("support.alerts", level="ERROR"):
                alerts.sync_waiting_contacts(timezone.now() + dt.timedelta(minutes=15 * run + 1))
            calls = self.ghl.calls[before:]
            self.assertEqual(len(calls), alerts.CONTACTS_PER_RUN)
            tried |= {c[2]["email"] for c in calls}
        self.assertEqual(len(tried), 120)  # three runs reached every one of them

    @override_settings(OWNER_ALERT_EMAIL="")
    def test_reporters_are_added_even_when_owner_emails_are_off(self):
        self.report(email="jane@plant.com", may_contact=True)
        self.assertEqual(alerts.run(self.later()), {"reports": 0, "crashes": 0, "contacts": 1})

    @override_settings(GHL_PRIVATE_TOKEN="")
    def test_nothing_is_tried_when_gohighlevel_is_not_set_up(self):
        self.report(email="jane@plant.com", may_contact=True)
        self.assertEqual(alerts.run(self.later()), {"reports": 0, "crashes": 0, "contacts": 0})
        self.assertEqual(self.ghl.calls, [])


# ---- The cron -----------------------------------------------------------------------------------------

@override_settings(**GHL_ON)
class CronTests(SupportCase):
    def test_one_failing_part_does_not_stop_the_others_and_the_step_is_shown_as_failed(self):
        self.crash()
        self.report(email="jane@plant.com", may_contact=True)
        said = []
        with mock.patch.object(alerts, "send_crash_rollup", side_effect=ValueError("boom")), self.assertLogs("support.alerts", level="ERROR"):
            with self.assertRaisesMessage(RuntimeError, "Support: crashes failed"):
                alerts.run(self.later(), say=said.append)
        self.assertEqual(said, ["Support: 1 reporters added to GoHighLevel"])
        self.assertIsNotNone(Ticket.objects.get(kind=Ticket.PROBLEM).ghl_noted_at)

    def test_the_cron_itself_runs_the_support_step_and_the_hourly_clean_up(self):
        self.ghl.down = True
        self.report(email="jane@plant.com", may_contact=True)
        self.ghl.down = False
        self.crash()
        top_of_hour = (timezone.now() + dt.timedelta(hours=1)).replace(minute=5, second=0, microsecond=0)
        with mock.patch("django.utils.timezone.now", return_value=top_of_hour), mock.patch("talks.management.commands.cron.call_command") as commands:
            out = io.StringIO()
            call_command("cron", stdout=out)
        for line in ("Support: 1 reports emailed to the owner late", "Support: the owner was emailed about 1 crashes", "Support: 1 reporters added to GoHighLevel"):
            self.assertIn(line, out.getvalue())
        self.assertIn("support_prune", [c[0][0] for c in commands.call_args_list])
        self.assertEqual(len(self.ghl.emails), 2)
        half_past = top_of_hour.replace(minute=35)
        with mock.patch("django.utils.timezone.now", return_value=half_past), mock.patch("talks.management.commands.cron.call_command") as commands:
            out = io.StringIO()
            call_command("cron", stdout=out)
        self.assertNotIn("support_prune", [c[0][0] for c in commands.call_args_list])  # the clean-up is hourly
        self.assertNotIn("Support:", out.getvalue())
        self.assertEqual(len(self.ghl.emails), 2)

    def test_a_support_step_that_fails_is_reported_and_the_cron_carries_on(self):
        from django.core.management.base import CommandError

        with mock.patch.object(alerts, "send_waiting_reports", side_effect=ValueError("boom")), self.assertLogs(level="ERROR"), \
                mock.patch("talks.management.commands.cron.call_command") as commands:
            out = io.StringIO()
            with self.assertRaises(CommandError):
                call_command("cron", stdout=out)
        self.assertIn("Support tickets: FAILED", out.getvalue())
        self.assertIn("monday_minute", [c[0][0] for c in commands.call_args_list])  # the steps after it still ran


class PruneTests(SupportCase):
    @override_settings(SUPPORT_CRASH_KEEP_DAYS=90)
    def test_old_crash_reports_go_and_tickets_stay(self):
        self.crash()
        t = Ticket.objects.get()
        now = timezone.now()
        for n, days in enumerate([91, 90, 89, 400]):
            CrashReport.objects.create(ticket=t, client_key=f"old-{n}", install_hash="h", name="TypeError",
                                       created_at=now - dt.timedelta(days=days) + dt.timedelta(minutes=1 if days == 90 else 0))
        Ticket.objects.filter(pk=t.pk).update(count=5, created_at=now - dt.timedelta(days=400), last_seen=now - dt.timedelta(days=400))
        out = io.StringIO()
        call_command("support_prune", stdout=out)
        self.assertIn("Support: deleted 2 crash reports", out.getvalue())
        self.assertEqual(sorted(CrashReport.objects.values_list("client_key", flat=True)), ["crash-0001-abcdef", "old-1", "old-2"])
        self.assertEqual(Ticket.objects.get().count, 5)  # the ticket and its count are never pruned
        out = io.StringIO()
        call_command("support_prune", stdout=out)
        self.assertEqual(out.getvalue(), "")  # nothing to say when nothing was deleted


# ---- The content console ------------------------------------------------------------------------------

class ConsoleTests(SupportCase):
    def call(self, method, path, body=None, key=KEY):
        headers = {"HTTP_AUTHORIZATION": f"Bearer {key}"} if key is not None else {}
        data = json.dumps(body) if body is not None else ""
        return getattr(self.client, method)(f"/api/console/{path}", data=data, content_type="application/json", **headers)

    def seed(self):
        self.report(email="jane@plant.com", name="Jane Doe", may_contact=True)
        self.report(client_key="rep-0002-abcdef", source="otis_answer", text="Wrong.", question="Q?", answer="A.", model_key="QWEN3_1_7B")
        self.crash()
        self.crash(client_key="crash-0002-abcdef")
        self.crash(client_key="crash-0003-abcdef", name="RangeError")
        problem, answer = Ticket.objects.get(kind="problem"), Ticket.objects.get(kind="answer")
        typeerror, rangeerror = Ticket.objects.filter(kind="crash").order_by("pk")
        return problem, answer, typeerror, rangeerror

    def test_every_endpoint_needs_the_key(self):
        problem = self.seed()[0]
        for method, path, body in (("get", "tickets/", None), ("get", f"tickets/{problem.pk}/", None), ("patch", f"tickets/{problem.pk}/", {"status": "closed"})):
            with self.subTest(path=path, method=method):
                self.assertEqual(self.call(method, path, body, key=None).status_code, 401)
                self.assertEqual(self.call(method, path, body, key="wrong-key").json(), {"error": "Not authorized."})
                with self.settings(CONSOLE_KEY=""):
                    self.assertEqual(self.call(method, path, body).status_code, 503)
                self.assertEqual(self.call(method, path, body).status_code, 200)  # and the right key gets in
        self.assertEqual(Ticket.objects.get(pk=problem.pk).status, "closed")  # only the call with the right key changed it
        self.assertEqual(self.call("post", "tickets/").status_code, 405)
        self.assertEqual(self.call("delete", f"tickets/{problem.pk}/").status_code, 405)

    def test_the_list_shows_open_tickets_unless_asked_otherwise(self):
        problem, answer, typeerror, rangeerror = self.seed()
        Ticket.objects.filter(pk=rangeerror.pk).update(status=Ticket.FIXED)
        Ticket.objects.filter(pk=answer.pk).update(status=Ticket.IN_PROGRESS)

        def ids(query=""):
            r = self.call("get", f"tickets/{query}")
            self.assertEqual(r.status_code, 200)
            return {t["id"] for t in r.json()["tickets"]}

        self.assertEqual(ids(), {problem.pk, answer.pk, typeerror.pk})
        self.assertEqual(ids("?status=open"), {problem.pk, answer.pk, typeerror.pk})
        self.assertEqual(ids("?status=new"), {problem.pk, typeerror.pk})
        self.assertEqual(ids("?status=in_progress"), {answer.pk})
        self.assertEqual(ids("?status=fixed"), {rangeerror.pk})
        self.assertEqual(ids("?status=closed"), set())
        self.assertEqual(ids("?status=all"), {problem.pk, answer.pk, typeerror.pk, rangeerror.pk})
        self.assertEqual(ids("?status=all&kind=crash"), {typeerror.pk, rangeerror.pk})
        self.assertEqual(ids("?kind=problem"), {problem.pk})
        self.assertEqual(ids("?kind=answer"), {answer.pk})
        self.assertEqual(ids("?kind=all&status=new"), {problem.pk, typeerror.pk})
        for query in ("?status=nope", "?kind=nope"):
            r = self.call("get", f"tickets/{query}")
            self.assertEqual(r.status_code, 400)
            self.assertIn("must be one of", r.json()["error"])

    def test_a_ticket_in_the_list_has_every_field_the_console_shows(self):
        problem, answer, typeerror, _ = self.seed()
        rows = {t["id"]: t for t in self.call("get", "tickets/").json()["tickets"]}
        row = rows[problem.pk]
        self.assertEqual(set(row), {"id", "number", "kind", "status", "source", "title", "text", "reply", "owner_note", "count", "app_version", "platform",
                                    "os_version", "device", "screen", "lang", "name", "email", "may_contact", "created_at", "updated_at", "last_seen",
                                    "question", "answer", "model_key"})
        self.assertEqual((row["number"], row["kind"], row["status"], row["source"], row["count"]), (problem.number, "problem", "new", "form", 1))
        self.assertEqual((row["name"], row["email"], row["may_contact"], row["device"]), ("Jane Doe", "jane@plant.com", True, "Pixel 8"))
        self.assertEqual(row["created_at"], problem.created_at.isoformat())
        self.assertEqual((rows[typeerror.pk]["count"], rows[typeerror.pk]["kind"]), (2, "crash"))
        self.assertEqual((rows[answer.pk]["question"], rows[answer.pk]["answer"], rows[answer.pk]["model_key"]), ("Q?", "A.", "QWEN3_1_7B"))
        self.assertNotIn("install_hash", json.dumps(rows))

    def test_one_ticket_comes_with_its_crash_reports(self):
        problem, _, typeerror, _ = self.seed()
        r = self.call("get", f"tickets/{typeerror.pk}/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["ticket"]["number"], typeerror.number)
        crashes = r.json()["crashes"]
        self.assertEqual(len(crashes), 2)
        self.assertEqual(set(crashes[0]), {"created_at", "fatal", "name", "message", "stack", "screen", "app_version", "platform", "os_version", "device"})
        self.assertEqual((crashes[0]["name"], crashes[0]["fatal"], crashes[0]["stack"]), ("TypeError", True, CRASH["stack"]))
        self.assertEqual(self.call("get", f"tickets/{problem.pk}/").json()["crashes"], [])
        missing = self.call("get", "tickets/999999/")
        self.assertEqual((missing.status_code, missing.json()), (404, {"error": "No ticket with that number."}))
        self.assertEqual(self.call("patch", "tickets/999999/", {"status": "closed"}).status_code, 404)

    def test_the_owner_changes_status_reply_and_note_and_the_phone_sees_status_and_reply(self):
        problem = self.seed()[0]
        r = self.call("patch", f"tickets/{problem.pk}/", {"status": "fixed", "reply": " Fixed in 1.0.1. ", "owner_note": "Same as the feed bug.",
                                                          "email": "changed@evil.com", "count": 99, "kind": "crash"})
        self.assertEqual(r.status_code, 200)
        ticket = r.json()["ticket"]
        self.assertEqual((ticket["status"], ticket["reply"], ticket["owner_note"]), ("fixed", "Fixed in 1.0.1.", "Same as the feed bug."))
        problem.refresh_from_db()
        self.assertEqual((problem.email, problem.count, problem.kind), ("jane@plant.com", 1, "problem"))  # only the three fields can be changed
        self.assertIsNotNone(problem.closed_at)
        mine = self.post("mine", {"install_id": INSTALL}).json()["tickets"]
        self.assertEqual([(t["status"], t["reply"]) for t in mine if t["number"] == problem.number], [("fixed", "Fixed in 1.0.1.")])
        self.assertNotIn("Same as the feed bug.", json.dumps(mine))

    def test_closed_at_follows_the_status(self):
        problem = self.seed()[0]
        self.call("patch", f"tickets/{problem.pk}/", {"status": "in_progress"})
        self.assertIsNone(Ticket.objects.get(pk=problem.pk).closed_at)
        self.call("patch", f"tickets/{problem.pk}/", {"status": "closed"})
        closed = Ticket.objects.get(pk=problem.pk).closed_at
        self.assertIsNotNone(closed)
        self.call("patch", f"tickets/{problem.pk}/", {"status": "fixed"})   # still done: the first moment stays
        self.call("patch", f"tickets/{problem.pk}/", {"reply": "Thanks."})  # a change that is not the status
        self.assertEqual(Ticket.objects.get(pk=problem.pk).closed_at, closed)
        self.call("patch", f"tickets/{problem.pk}/", {"status": "new"})
        self.assertIsNone(Ticket.objects.get(pk=problem.pk).closed_at)

    def test_field_problems_answer_400_and_change_nothing(self):
        problem = self.seed()[0]
        for body in ({"status": "done"}, {"status": None}, {"status": 3}, {"reply": "r" * 2001}, {"owner_note": "n" * 2001}, {"reply": ["a"]},
                     {"reply": "broken \x00 character"}, {"status": "fixed", "reply": "r" * 2001}):
            with self.subTest(body=str(body)[:40]):
                r = self.call("patch", f"tickets/{problem.pk}/", body)
                self.assertEqual(r.status_code, 400)
                self.assertIn("error", r.json())
        for raw in ("not json", "[1]"):
            r = self.client.patch(f"/api/console/tickets/{problem.pk}/", data=raw, content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {KEY}")
            self.assertEqual(r.status_code, 400)
        problem.refresh_from_db()
        self.assertEqual((problem.status, problem.reply, problem.owner_note, problem.closed_at), ("new", "", "", None))
        self.assertEqual(self.call("patch", f"tickets/{problem.pk}/", {}).status_code, 200)  # nothing to change is not a problem

    def test_the_overview_counts_open_tickets(self):
        _, answer, typeerror, _ = self.seed()
        self.assertEqual(self.call("get", "overview/").json()["counts"]["tickets_open"], 4)
        Ticket.objects.filter(pk=answer.pk).update(status=Ticket.IN_PROGRESS)
        Ticket.objects.filter(pk=typeerror.pk).update(status=Ticket.CLOSED)
        self.assertEqual(self.call("get", "overview/").json()["counts"]["tickets_open"], 3)


# ---- The admin and the back office --------------------------------------------------------------------

@override_settings(STORAGES=PLAIN_STATIC)  # admin pages link their stylesheets; tests have no collected static files
class AdminTests(SupportCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(get_user_model().objects.create_superuser("owner", "owner@example.com", "a-long-test-password"))
        self.report(email="jane@plant.com", name="Jane Doe", may_contact=True)
        self.crash()
        self.problem, self.crashed = Ticket.objects.get(kind="problem"), Ticket.objects.get(kind="crash")

    def test_the_list_and_both_kinds_of_ticket_open(self):
        page = self.client.get("/admin/support/ticket/")
        self.assertContains(page, self.problem.number)
        self.assertContains(page, "TypeError: undefined is not a function")
        self.assertContains(self.client.get(f"/admin/support/ticket/{self.problem.pk}/change/"), "The talk list will not load.")
        self.assertContains(self.client.get(f"/admin/support/ticket/{self.crashed.pk}/change/"), "index.android.bundle:1:234567")
        self.assertEqual(self.client.get("/admin/support/ticket/add/").status_code, 403)  # tickets only come from phones

    def test_a_ticket_is_found_by_its_number(self):
        for term in (self.problem.number, self.problem.number.lower(), f"#{self.problem.pk}", str(self.problem.pk)):
            page = self.client.get("/admin/support/ticket/", {"q": term})
            self.assertContains(page, "The talk list will not load.")
            self.assertNotContains(page, "TypeError: undefined")
        self.assertContains(self.client.get("/admin/support/ticket/", {"q": "undefined is not"}), "TypeError: undefined")

    def test_the_actions_change_the_status_and_stamp_closed_at(self):
        def act(action, *tickets):
            return self.client.post("/admin/support/ticket/", {"action": action, "_selected_action": [t.pk for t in tickets]}, follow=True)

        self.assertContains(act("mark_in_progress", self.problem, self.crashed), "2 marked in progress.")
        self.assertEqual(set(Ticket.objects.values_list("status", "closed_at")), {("in_progress", None)})
        self.assertContains(act("mark_fixed", self.crashed), "1 marked fixed.")
        self.assertContains(act("mark_closed", self.problem), "1 marked closed.")
        self.problem.refresh_from_db()
        self.crashed.refresh_from_db()
        self.assertEqual((self.problem.status, self.crashed.status), ("closed", "fixed"))
        self.assertIsNotNone(self.problem.closed_at)
        self.assertIsNotNone(self.crashed.closed_at)
        self.assertContains(act("mark_closed", self.problem), "Those were already closed.")

    def test_saving_the_form_changes_only_what_the_owner_works_with(self):
        form = {"status": "fixed", "reply": "Fixed in 1.0.1.", "owner_note": "private", "title": "HACKED", "email": "changed@evil.com", "count": "99",
                "crashes-TOTAL_FORMS": "0", "crashes-INITIAL_FORMS": "0", "crashes-MIN_NUM_FORMS": "0", "crashes-MAX_NUM_FORMS": "0"}
        r = self.client.post(f"/admin/support/ticket/{self.problem.pk}/change/", form)
        self.assertEqual(r.status_code, 302)
        self.problem.refresh_from_db()
        self.assertEqual((self.problem.status, self.problem.reply, self.problem.owner_note), ("fixed", "Fixed in 1.0.1.", "private"))
        self.assertEqual((self.problem.title, self.problem.email, self.problem.count), ("The talk list will not load.", "jane@plant.com", 1))
        self.assertIsNotNone(self.problem.closed_at)
        self.client.post(f"/admin/support/ticket/{self.problem.pk}/change/", {**form, "status": "new"})
        self.problem.refresh_from_db()
        self.assertEqual((self.problem.status, self.problem.closed_at), ("new", None))

    @override_settings(**GHL_ON)
    def test_the_gohighlevel_action_adds_the_reporter_and_says_so(self):
        r = self.client.post("/admin/support/ticket/", {"action": "send_to_ghl", "_selected_action": [self.problem.pk, self.crashed.pk]}, follow=True)
        self.assertContains(r, "1 in GoHighLevel, tagged zero-harm-support-ticket with a note.")
        self.assertEqual(len(self.ghl.notes["reporter1"]), 1)
        r = self.client.post("/admin/support/ticket/", {"action": "send_to_ghl", "_selected_action": [self.crashed.pk]}, follow=True)
        self.assertContains(r, "nobody to add to GoHighLevel")

    def test_the_back_office_flags_new_tickets(self):
        flags = {a["url"]: a for a in metrics.dashboard(30)["attention"]}
        self.assertEqual(flags["/admin/support/ticket/?status__exact=new"]["text"], "support tickets waiting for you")
        self.assertEqual(flags["/admin/support/ticket/?status__exact=new"]["count"], 2)
        Ticket.objects.filter(pk=self.crashed.pk).update(status=Ticket.IN_PROGRESS)
        self.assertEqual({a["url"]: a for a in metrics.dashboard(30)["attention"]}["/admin/support/ticket/?status__exact=new"]["text"], "support ticket waiting for you")
        Ticket.objects.update(status=Ticket.CLOSED)
        self.assertNotIn("/admin/support/ticket/?status__exact=new", {a["url"] for a in metrics.dashboard(30)["attention"]})
        self.assertEqual(self.client.get("/admin/support/ticket/?status__exact=new").status_code, 200)


# ---- Cleaning text ------------------------------------------------------------------------------------

class TextTests(SimpleTestCase):
    def test_scrub_takes_out_what_could_point_at_a_person_and_keeps_where_it_broke(self):
        cases = {
            "mail bob.smith+x@example.co.uk now": "mail [email] now",
            "GET https://api.example.com/v1/x?token=abc&u=5 failed": "GET https://api.example.com/v1/x failed",
            "at f (https://x.example/app.js?v=1:10:22)": "at f (https://x.example/app.js:10:22)",
            "open zeroharm://report?email=a#frag": "open zeroharm://report",
            "at g (/var/app/x.js?key=1:3:4)": "at g (/var/app/x.js:3:4)",
            "call 555-123-4567 or (555) 123 4567 or +1 555.123.4567": "call [phone] or [phone] or [phone]",
            "card 4111111111111111 and id 123456789": "card [number] and id [number]",
            "from 10.0.0.5:8080": "from [address]:8080",
            # What must survive: places in the code, versions, questions, and the app's own picture names.
            "at h (index.android.bundle:1:2345678)": "at h (index.android.bundle:1:2345678)",
            "at h (index.bundle:123:4567890)": "at h (index.bundle:123:4567890)",
            "version 1.2.3 on Android 14": "version 1.2.3 on Android 14",
            "What is this? and/or that?": "What is this? and/or that?",
            "could not load icon@2x.png": "could not load icon@2x.png",
            "Cannot read property 'x' of undefined": "Cannot read property 'x' of undefined",
        }
        for raw, wanted in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(text.scrub(raw), wanted)

    def test_line_and_block(self):
        self.assertEqual(text.line(" a\x00b​  c\n d "), "a b c d")
        self.assertEqual(text.line("x" * 50, 20), "x" * 20)
        self.assertEqual((text.line(None), text.line(34), text.line(True), text.line(["a"])), ("", "34", True, ["a"]))
        self.assertEqual(text.block(" one\r\ntwo\x00\ud800\tthree \n"), "one\ntwo\tthree")
        self.assertEqual((text.block(None), text.block(7), text.block("x" * 50, 20)), ("", 7, "x" * 20))
        self.assertEqual(text.route("/talk/12?ref=1#top"), "/talk/12")
        self.assertEqual(text.first_line("\n\n  It   broke \nmore"), "It broke")

    def test_fingerprint_groups_by_error_version_and_platform(self):
        same = text.fingerprint("TypeError", "Item 12 not found in 0xABCDEF12 for 3f6c1c1e-8a55-4a0e-9d7b-1c2d3e4f5a6b", "1.0.0", "ios")
        self.assertEqual(same, text.fingerprint("TypeError", "item 97  not found in 0x12 for deadbeef01", "1.0.0", "ios"))
        for other in (("RangeError", "Item 12 not found in 0x1 for a1b2c3d4e5", "1.0.0", "ios"), ("TypeError", "Item 12 was not found", "1.0.0", "ios"),
                      ("TypeError", "Item 12 not found in 0x1 for a1b2c3d4e5", "1.0.1", "ios"), ("TypeError", "Item 12 not found in 0x1 for a1b2c3d4e5", "1.0.0", "android")):
            self.assertNotEqual(same, text.fingerprint(*other))


# ---- Review fixes: one crash is one ticket, whatever a scrub did to an id in it ------------------------

# A Python copy of the phone's scrub (lib/support/crash.ts, scrub(), as of 2026-11-11), so a report can be put through
# what a phone does before it is sent. PHONE_SCRUB is the current one, which turns a whole id into "[id]".
# PHONE_SCRUB_BEFORE_IDS is the earlier one, which cut digit runs out of the middle of ids; phones may still run it.
# JavaScript's \w and \d are ASCII only, hence re.ASCII.
_JS = re.ASCII
PHONE_NUMBER_RULES = [
    (re.compile(r"(\S)\?[\w%.~+-]*=[^\s\"'<>)\]]*", _JS), r"\1?"),
    (re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+", _JS), "[email]"),
    (re.compile(r"\+?\d[\d\s().-]{7,}\d", _JS), "[number]"),
    (re.compile(r"\d{6,}", _JS), "[number]"),
    (re.compile(r"-?\d{1,3}\.\d{4,}", _JS), "[number]"),
]
PHONE_ID_RULES = [
    (re.compile(r"\b([a-z][a-z0-9+.-]*://[^\s?#\"'<>)\]]*)[?#][^\s\"'<>)\]]*", _JS | re.I), r"\1"),
    (re.compile(r"(\S)\?[\w%.~+-]*=[^\s\"'<>)\]]*", _JS), r"\1?"),
    (re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", _JS | re.I), "[id]"),
    (re.compile(r"\b(?:0x)?[0-9a-f]{16,}\b", _JS | re.I), "[id]"),
    (re.compile(r"\b(?=[0-9a-f]*[a-f])(?=[0-9a-f]*\d{6})[0-9a-f]{8,}\b", _JS | re.I), "[id]"),
]


def _run(rules, value):
    for pattern, put in rules:
        value = pattern.sub(put, value)
    return " ".join(value.split())  # describeError: runs of space become one


def PHONE_SCRUB(value):
    return _run(PHONE_ID_RULES + PHONE_NUMBER_RULES[1:], value)


def PHONE_SCRUB_BEFORE_IDS(value):
    return _run(PHONE_NUMBER_RULES, value)


def server_fingerprint(message, name="Error", version="1.0.0", platform="ios"):
    """The fingerprint the crash endpoint makes: the message cleaned by the endpoint's own schema first."""
    body = api.CrashIn(client_key="crash-fp-0001", install_id=INSTALL, name=name, message=message, app_version=version, platform=platform)
    return text.fingerprint(body.name, body.message, body.app_version, body.platform)


class OneCrashOneTicketTests(SupportCase):
    SHAPES = (
        lambda u: f"File '/var/mobile/Containers/Data/Application/{u.upper()}/Library/Caches/otis/model.pte' is not readable",
        lambda u: f"File '/var/mobile/Containers/Data/Application/{u}/Library/Caches/otis/model.pte' is not readable",
        lambda u: f"No device with id {u.replace('-', '')[:16]} (code 7)",
        lambda u: f"Lookup failed for {u[:24]}{int(u.replace('-', ''), 16) % 10**12:012d}",
    )

    def test_a_thousand_phones_with_their_own_app_folder_id_make_one_ticket(self):
        rnd = random.Random(20261111)
        for scrub_name, phone_scrub in (("no phone scrub", lambda m: m), ("phone scrub", PHONE_SCRUB), ("older phone scrub", PHONE_SCRUB_BEFORE_IDS)):
            for n, shape in enumerate(self.SHAPES):
                with self.subTest(scrub=scrub_name, shape=n):
                    ids = [str(uuid.UUID(int=rnd.getrandbits(128), version=4)) for _ in range(1000)]
                    found = {server_fingerprint(phone_scrub(shape(u))) for u in ids}
                    self.assertEqual(len(found), 1, sorted({phone_scrub(shape(u)) for u in ids})[:3])

    def test_what_a_scrub_leaves_of_an_id_counts_as_one_id(self):
        same = server_fingerprint("Open /Application/[id]/Library failed")
        for left in ("Open /Application/E91AC587-2E[number]EFD537C5BF/Library failed", "Open /Application/e91ac587-2e[number]/Library failed",
                     "Open /Application/3f2a9c1e-1111-2222-3333-[number]/Library failed", "Open /Application/[number]-ab12/Library failed"):
            self.assertEqual(server_fingerprint(left), same, left)
        self.assertNotEqual(server_fingerprint("Open /Application/[id]/Caches failed"), same)  # the words around it still count

    def test_crash_reports_from_many_phones_through_the_endpoint_are_one_ticket(self):
        rnd = random.Random(7)
        for n in range(40):
            u = str(uuid.UUID(int=rnd.getrandbits(128), version=4))
            message = PHONE_SCRUB_BEFORE_IDS(self.SHAPES[0](u))
            r = self.crash(ip=f"198.51.{n // 200}.{n % 200}", client_key=f"crash-many-{n:04d}", install_id=f"zh-m1abcd-{n:032x}", message=message)
            self.assertEqual(r.status_code, 200)
        t = Ticket.objects.get()
        self.assertEqual(t.count, 40)


# ---- Review fixes: what is taken out of crash text ---------------------------------------------------

class ScrubReviewTests(SimpleTestCase):
    def test_a_query_string_goes_whole_whatever_is_in_it(self):
        cases = {
            "https://api.example.com/v2/x?email=jane@example.com&token=SECRET5": "https://api.example.com/v2/x",
            "https://api.example.com/cb?email=jane@example.com#access_token=SECRET8": "https://api.example.com/cb",
            "https://api.example.com/v2/x?ids[]=5&token=SECRET1": "https://api.example.com/v2/x",
            "https://api.example.com/v2/x?q=jane doe&token=SECRET3 failed": "https://api.example.com/v2/x  failed",
            "zeroharm://invite?name=Jane Doe&code=SECRET10": "zeroharm://invite ",
            "https://u:p@host.example.com/x?ids[]=5&token=SECRET1": "https://host.example.com/x",
            "open invite?code=SECRET99 failed": "open invite failed",
            # A stack frame keeps where it broke and its closing parenthesis.
            "at f (https://x.example/app.js?v=1&t=SECRET2:10:22)": "at f (https://x.example/app.js:10:22)",
            "at g (/var/app/x.js?key=SECRET4#top:3:4)": "at g (/var/app/x.js:3:4)",
        }
        for raw, wanted in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(text.scrub(raw), wanted)
                self.assertNotIn("SECRET", text.scrub(raw))

    def test_phone_card_and_social_security_numbers_and_ipv6_addresses_go(self):
        cases = {
            "call 702-555-1234 / 702.555.1234 / (702)555-1234 / 7025551234": "call [phone] / [phone] / [phone] / [number]",
            "+52 55 1234 5678 or +44 20 7946 0958": "[number] or [number]",
            "card 4111 1111 1111 1111 or 4111-1111-1111-1111": "card [number] or [number]",
            "ssn 123-45-6789": "ssn [number]",
            "from 2001:db8::8a2e:370:7334 and ::1": "from [address] and [address]",
            # What must survive: places in the code, versions, dates and times, short numbers.
            "at h (index.android.bundle:1:2345678)": "at h (index.android.bundle:1:2345678)",
            "version 1.2.3 on Android 14, status 404": "version 1.2.3 on Android 14, status 404",
            "on 2026-11-11T10:20:30Z at 10:20:30": "on 2026-11-11T10:20:30Z at 10:20:30",
            "std::vector failed at abc:12:34": "std::vector failed at abc:12:34",
        }
        for raw, wanted in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(text.scrub(raw), wanted)

    def test_an_id_is_taken_out_whole(self):
        self.assertEqual(text.scrub("/Application/E91AC587-2E39-4A1B-9123-456789012345/Library"), "/Application/[id]/Library")
        self.assertEqual(text.scrub("token a1b2c3d4e5f60718293a4b5c"), "token [id]")


# ---- Review fixes: a crash cannot be matched to a person ------------------------------------------------

class CrashPrivacyTests(SupportCase):
    def test_a_crash_is_kept_under_its_own_hash_and_the_ticket_keeps_none(self):
        self.report(email="quiet@example.com")
        self.crash()
        problem, crash = Ticket.objects.get(kind="problem"), Ticket.objects.get(kind="crash")
        row = CrashReport.objects.get()
        self.assertEqual(problem.install_hash, _hash(INSTALL))  # a person's report stays tied to the phone, on purpose
        self.assertEqual(crash.install_hash, "")
        self.assertEqual(row.install_hash, api.crash_hash(INSTALL))
        self.assertNotEqual(row.install_hash, _hash(INSTALL))
        # Nothing joins: no ticket or sign-up hash matches a crash row's hash.
        self.assertFalse(Ticket.objects.filter(install_hash=row.install_hash).exists())
        self.assertFalse(CrashReport.objects.filter(install_hash__in=Ticket.objects.exclude(install_hash="").values("install_hash")).exists())
        # A repeat is still told apart from a new report.
        self.crash()
        self.assertEqual(Ticket.objects.get(kind="crash").count, 1)
        self.crash(client_key="crash-0002-abcdef")
        self.assertEqual(Ticket.objects.get(kind="crash").count, 2)

    @override_settings(SUPPORT_CRASH_KEEP_DAYS=90)
    def test_the_first_phones_details_go_from_the_ticket_with_the_reports(self):
        self.crash()
        Ticket.objects.update(first_seen=timezone.now() - dt.timedelta(days=89))
        call_command("support_prune", stdout=io.StringIO())
        self.assertEqual(Ticket.objects.values_list("device", "os_version", "screen").get(), ("Pixel 8", "14", "/otis"))
        Ticket.objects.update(first_seen=timezone.now() - dt.timedelta(days=91))
        CrashReport.objects.update(created_at=timezone.now() - dt.timedelta(days=91))
        out = io.StringIO()
        call_command("support_prune", stdout=out)
        self.assertIn("cleared the phone details on 1 crash tickets", out.getvalue())
        t = Ticket.objects.get()
        self.assertEqual((t.device, t.os_version, t.screen, t.install_hash), ("", "", "", ""))
        self.assertEqual((t.title, t.app_version, t.platform, t.count), ("TypeError: undefined is not a function", "1.0.0", "android", 1))
        self.assertFalse(CrashReport.objects.exists())

    def test_the_migration_unlinks_crash_rows_saved_before_it(self):
        migration = importlib.import_module("support.migrations.0002_crash_privacy_and_counting")
        self.report()
        self.crash()
        Ticket.objects.filter(kind="crash").update(install_hash=_hash(INSTALL))
        CrashReport.objects.update(install_hash=_hash(INSTALL))  # as the first version stored them
        migration.unlink_old_crash_rows(django_apps, None)
        self.assertEqual(Ticket.objects.get(kind="crash").install_hash, "")
        self.assertEqual(Ticket.objects.get(kind="problem").install_hash, _hash(INSTALL))
        self.assertTrue(CrashReport.objects.get().install_hash.startswith("unlinked:"))


# ---- Review fixes: counting, saving and emailing once ----------------------------------------------------

class CountedOnceTests(SupportCase):
    def test_a_report_sent_again_after_its_row_was_trimmed_is_not_counted_again(self):
        with mock.patch.object(api, "CRASH_ROWS_KEPT", 3):
            for n in range(6):
                self.crash(client_key=f"crash-many-{n:04d}")
            self.assertFalse(CrashReport.objects.filter(client_key="crash-many-0000").exists())
            again = self.crash(client_key="crash-many-0000")
        t = Ticket.objects.get()
        self.assertEqual((again.status_code, again.json()["number"], t.count), (200, t.number, 6))

    @override_settings(SUPPORT_CRASH_KEEP_DAYS=90)
    def test_a_report_sent_again_after_the_clean_up_is_not_counted_again_within_a_week(self):
        self.crash()
        CrashReport.objects.update(created_at=timezone.now() - dt.timedelta(days=91))
        call_command("support_prune", stdout=io.StringIO())
        self.assertFalse(CrashReport.objects.exists())
        self.crash()
        self.assertEqual(Ticket.objects.get().count, 1)
        # After a week the reminder goes too; a phone never waits that long to send one again.
        CrashKey.objects.update(created_at=timezone.now() - dt.timedelta(days=8))
        call_command("support_prune", stdout=io.StringIO())
        self.assertFalse(CrashKey.objects.exists())

    def test_a_report_turned_away_by_a_limit_is_counted_when_it_comes_back(self):
        with mock.patch.object(alerts, "NEW_CRASHES_PER_DAY", 0):
            self.assertEqual(self.crash().status_code, 503)
        self.assertFalse(CrashKey.objects.exists())
        self.assertEqual(self.crash().status_code, 200)
        self.assertEqual(Ticket.objects.get().count, 1)


@override_settings(SUPPORT_CRASH_KEEP_DAYS=0)
class PruneSettingTests(SupportCase):
    def test_the_clean_up_refuses_a_keep_time_under_one_day(self):
        from django.core.management.base import CommandError

        self.crash()
        with self.assertRaises(CommandError):
            call_command("support_prune", stdout=io.StringIO())
        self.assertEqual(CrashReport.objects.count(), 1)

    def test_a_blank_or_mistyped_keep_time_does_not_stop_the_server(self):
        script = "from django.conf import settings; print(settings.SUPPORT_CRASH_KEEP_DAYS)"
        for value, wanted in (("", "90"), ("ninety", "90"), ("0", "1"), ("-5", "1"), (" 30 ", "30")):
            with self.subTest(value=value):
                env = {**os.environ, "DJANGO_SETTINGS_MODULE": "zeroharm.settings", "DJANGO_SECRET_KEY": "test", "SUPPORT_CRASH_KEEP_DAYS": value}
                out = subprocess.run([sys.executable, "-c", f"import django; django.setup(); {script}"], env=env, capture_output=True,
                                     text=True, cwd=pathlib.Path(__file__).resolve().parents[1], timeout=60)
                self.assertEqual((out.returncode, out.stdout.strip()), (0, wanted), out.stderr[-500:])


class OwnerEditsTests(SupportCase):
    def call(self, method, path, body=None):
        return getattr(self.client, method)(f"/api/console/{path}", data=json.dumps(body) if body is not None else "",
                                            content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {KEY}")

    def _meanwhile(self, pk, now):
        """What the crash endpoint and the cron write while the owner's save is on its way."""
        Ticket.objects.filter(pk=pk).update(count=107, last_seen=now, alerted_count=100, owner_alerted_at=now)

    def test_a_console_edit_does_not_undo_counts_and_stamps_written_meanwhile(self):
        self.crash()
        t, now = Ticket.objects.get(), timezone.now()
        from . import console as console_module

        real = console_module._apply

        def apply_after_others_wrote(obj, data, checks):
            self._meanwhile(obj.pk, now)
            return real(obj, data, checks)

        with mock.patch.object(console_module, "_apply", side_effect=apply_after_others_wrote):
            r = self.call("patch", f"tickets/{t.pk}/", {"status": "in_progress", "owner_note": "looking"})
        self.assertEqual(r.status_code, 200)
        t.refresh_from_db()
        self.assertEqual((t.status, t.owner_note, t.count, t.alerted_count, t.owner_alerted_at), ("in_progress", "looking", 107, 100, now))

    @override_settings(STORAGES=PLAIN_STATIC)
    def test_an_admin_save_does_not_undo_counts_and_stamps_written_meanwhile(self):
        from .admin import TicketAdmin

        self.client.force_login(get_user_model().objects.create_superuser("owner", "owner@example.com", "a-long-test-password"))
        self.crash()
        t, now = Ticket.objects.get(), timezone.now()
        real = TicketAdmin.save_form

        def save_form_after_others_wrote(admin_self, request, form, change):
            self._meanwhile(t.pk, now)
            return real(admin_self, request, form, change)

        form = {"status": "fixed", "reply": "", "owner_note": "fixed in 1.0.1", "crashes-TOTAL_FORMS": "0", "crashes-INITIAL_FORMS": "0",
                "crashes-MIN_NUM_FORMS": "0", "crashes-MAX_NUM_FORMS": "0"}
        with mock.patch.object(TicketAdmin, "save_form", save_form_after_others_wrote):
            self.assertEqual(self.client.post(f"/admin/support/ticket/{t.pk}/change/", form).status_code, 302)
        t.refresh_from_db()
        self.assertEqual((t.status, t.owner_note, t.count, t.alerted_count, t.owner_alerted_at), ("fixed", "fixed in 1.0.1", 107, 100, now))
        self.assertIsNotNone(t.closed_at)

    @override_settings(STORAGES=PLAIN_STATIC)
    def test_the_admin_reply_box_says_who_sees_it(self):
        self.client.force_login(get_user_model().objects.create_superuser("owner", "owner@example.com", "a-long-test-password"))
        self.report()
        self.report(client_key="rep-0002-abcdef", source="otis_answer", text="Wrong.")
        self.crash()
        for kind, words in (("problem", "The person sees this in the app under My reports."),
                            ("answer", "Private note. The person never sees a reply on a flagged OTIS answer or a crash."),
                            ("crash", "Private note. The person never sees a reply on a flagged OTIS answer or a crash.")):
            with self.subTest(kind=kind):
                self.assertContains(self.client.get(f"/admin/support/ticket/{Ticket.objects.get(kind=kind).pk}/change/"), words)


@override_settings(**GHL_ON)
class OwnerEmailReviewTests(SupportCase):
    def test_only_a_problem_report_email_says_the_person_sees_the_reply(self):
        self.report()
        self.report(client_key="rep-0002-abcdef", source="otis_answer", text="Wrong.", question="Q?", answer="A.")
        problem, answer = self.ghl.emails
        self.assertIn("The person sees the status and your reply in the app, under My reports.", problem["html"])
        self.assertNotIn("under My reports", answer["html"])
        self.assertIn("A reply you write on it is a private note they never see.", answer["html"])

    def test_an_email_gohighlevel_took_but_answered_too_late_for_is_not_sent_again_as_its_own(self):
        slow = {"on": True}
        real = self.ghl.request

        def took_it_then_timed_out(method, path, *args, **kwargs):
            answer = real(method, path, *args, **kwargs)  # recorded: GoHighLevel has the email
            if slow["on"] and path == "/conversations/messages":
                raise GhlError(f"{method} {path} -> TimeoutError: timed out")
            return answer

        clock = iter([100.0, 100.0 + owner_alerts.QUICK])
        with mock.patch("talks.ghl.request", side_effect=took_it_then_timed_out), mock.patch.object(alerts.time, "monotonic", lambda: next(clock)):
            self.report()
        t = Ticket.objects.get()
        self.assertEqual(len(self.ghl.emails), 1)
        self.assertIsNone(t.owner_alerted_at)
        self.assertIsNotNone(t.owner_alert_unsure_at)
        slow["on"] = False
        self.assertEqual(alerts.run(self.later(5))["reports"], 0)  # too soon: it may well have arrived
        self.assertEqual(len(self.ghl.emails), 1)
        self.assertEqual(alerts.run(self.later(20))["reports"], 1)
        (_, listed) = self.ghl.emails
        self.assertEqual(listed["subject"], "Zero Harm: 1 report waiting")
        self.assertIn("This one may have reached you already", listed["html"])
        for minutes in (35, 50, 3000):
            self.assertEqual(alerts.run(self.later(minutes))["reports"], 0)
        self.assertEqual(len(self.ghl.emails), 2)

    def test_a_refusal_is_not_taken_for_a_slow_answer(self):
        self.ghl.down = True  # answers at once with an error
        self.report()
        self.assertIsNone(Ticket.objects.get().owner_alert_unsure_at)
        self.ghl.down = False
        self.assertEqual(alerts.run(self.later())["reports"], 1)
        self.assertNotIn("may have reached you", self.ghl.emails[0]["html"])


# ---- Second review: what the checker still found ---------------------------------------------------------

class UuidNextToAWordTests(SupportCase):
    """A UUID right after "_" or a letter, or right before "_", has no word edge. It must still be taken out whole and
    still even out in the fingerprint, or every phone's crash is its own ticket with its own id in the title."""
    SHAPES = (
        lambda u: f"File '/var/mobile/Containers/Data/Application/ImagePicker/photo_{u}.jpg' not found",
        lambda u: f"File '/x/{u}_thumb.jpg' missing",
        lambda u: f"Cannot open cacheV{u}",
        lambda u: f"Cannot open cache_{u.upper()}_v2",
    )

    def test_one_fingerprint_for_every_shape_with_or_without_the_phones_scrub(self):
        rnd = random.Random(20261112)
        for scrub_name, phone_scrub in (("no phone scrub", lambda m: m), ("phone scrub", PHONE_SCRUB), ("older phone scrub", PHONE_SCRUB_BEFORE_IDS)):
            for n, shape in enumerate(self.SHAPES):
                with self.subTest(scrub=scrub_name, shape=n):
                    ids = [str(uuid.UUID(int=rnd.getrandbits(128), version=4)) for _ in range(500)]
                    found = {server_fingerprint(phone_scrub(shape(u))) for u in ids}
                    self.assertEqual(len(found), 1, sorted({phone_scrub(shape(u)) for u in ids})[:3])
                    for u in ids[:20]:
                        self.assertNotIn(u.lower(), text.scrub(phone_scrub(shape(u))).lower())

    def test_thirty_phones_through_the_endpoint_make_one_ticket_with_no_id_in_its_title(self):
        rnd = random.Random(30)
        ids = [str(uuid.UUID(int=rnd.getrandbits(128), version=4)) for _ in range(30)]
        for n, u in enumerate(ids):
            r = self.crash(ip=f"198.51.100.{n}", client_key=f"crash-photo-{n:04d}", install_id=f"zh-m1abcd-{n:032x}", message=self.SHAPES[0](u))
            self.assertEqual(r.status_code, 200)
        t = Ticket.objects.get()
        self.assertEqual(t.count, 30)
        self.assertIn("photo_[id].jpg", t.title)
        for u in ids:
            self.assertNotIn(u, t.title)
            self.assertFalse(CrashReport.objects.filter(message__icontains=u).exists())


class ScrubSecondReviewTests(SimpleTestCase):
    def test_a_number_after_a_label_and_a_colon_goes(self):
        cases = {
            "card:4111-1111-1111-1111": "card:[number]",
            "card:4111 1111 1111 1111": "card:[number]",
            "SSN:123-45-6789": "SSN:[number]",
            "Invalid phone:702-555-1234": "Invalid phone:[phone]",
            "tel:702.555.1234": "tel:[phone]",
            "call 555-1234 now": "call [phone] now",
            "lat 36.169941, lng -115.139832": "lat [number], lng [number]",
            # A place in the code is "digit:" and stays, and so do dates and times.
            "at index.bundle:1:234 567": "at index.bundle:1:234 567",
            "x.js:12:34 - 56": "x.js:12:34 - 56",
            "index.android.bundle:1:2345678": "index.android.bundle:1:2345678",
            "row saved at 2026-11-12 14:05:00": "row saved at 2026-11-12 14:05:00",
            "on 2026-11-11T10:20:30Z at 10:20:30": "on 2026-11-11T10:20:30Z at 10:20:30",
            "version 1.2.3 on Android 14, status 404": "version 1.2.3 on Android 14, status 404",
        }
        for raw, wanted in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(text.scrub(raw), wanted)

    def test_a_fragment_or_a_quoted_query_goes_whole(self):
        cases = {
            "route /reset#token=SECRET21": "route /reset",
            "open invite#code=SECRET22 failed": "open invite failed",
            'fetch https://h.example.com/a?data={"token":"SECRET23"}': "fetch https://h.example.com/a",
            "fetch https://h.example.com/a?q=\"SECRET24\" failed": "fetch https://h.example.com/a failed",
            "at g (/var/app/x.js?d={\"k\":\"SECRET25\"}:3:4)": "at g (/var/app/x.js:3:4)",
            # What stays: a quote that closes the address, and a "#" with no "=" after a path.
            'fetch "https://h.example.com/a?b=SECRET26" failed': 'fetch "https://h.example.com/a" failed',
            "go to /settings#top": "go to /settings#top",
        }
        for raw, wanted in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(text.scrub(raw), wanted)

    def test_a_search_with_spaces_and_no_ampersand_keeps_its_later_words(self):
        # A known gap, kept on record: with no "&" there is nothing to tell the rest of the search from the rest of
        # the message, so only the first word goes.
        self.assertEqual(text.scrub("GET https://h.example.com/a?q=jane doe smith"), "GET https://h.example.com/a doe smith")

    def test_a_javascriptcore_stack_frame_is_not_an_email(self):
        for frame in ("f@index.bundle:12:34", "render@index.android.bundle:1:2345", "anonymous@main.jsbundle.bundle:3:4"):
            with self.subTest(frame=frame):
                self.assertEqual(text.scrub(frame), frame)
        self.assertEqual(text.scrub("mail jane@mail.bundle.com now"), "mail [email] now")
        self.assertEqual(text.scrub("mail jane@example.com now"), "mail [email] now")


class OwnerEditRaceTests(SupportCase):
    """A note written on a closed crash ticket must not close it again when a new report opened it meanwhile."""

    def call(self, method, path, body=None):
        return getattr(self.client, method)(f"/api/console/{path}", data=json.dumps(body) if body is not None else "",
                                            content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {KEY}")

    def _closed_crash(self):
        self.crash()
        closed = timezone.now() - dt.timedelta(days=3)
        Ticket.objects.update(status=Ticket.CLOSED, closed_at=closed, alerted_count=1)
        return Ticket.objects.get()

    def _reopened_meanwhile(self, pk):
        Ticket.objects.filter(pk=pk).update(status=Ticket.NEW, closed_at=None, count=2, alerted_count=0)

    def test_a_console_note_does_not_close_a_ticket_opened_again_meanwhile(self):
        from . import console as console_module

        t = self._closed_crash()
        real = console_module._apply

        def apply_after_reopen(obj, data, checks):
            self._reopened_meanwhile(obj.pk)
            return real(obj, data, checks)

        for body in ({"owner_note": "x"}, {"owner_note": "y", "status": "closed"}):  # the status sent as it was is no change
            with self.subTest(body=body):
                Ticket.objects.filter(pk=t.pk).update(status=Ticket.CLOSED, closed_at=timezone.now(), alerted_count=1)
                with mock.patch.object(console_module, "_apply", side_effect=apply_after_reopen):
                    r = self.call("patch", f"tickets/{t.pk}/", body)
                self.assertEqual(r.status_code, 200)
                t.refresh_from_db()
                self.assertEqual((t.status, t.closed_at, t.owner_note, t.count), ("new", None, body["owner_note"], 2))

    def test_a_console_status_change_still_stamps_closed_at(self):
        self.crash()
        t = Ticket.objects.get()
        self.assertEqual(self.call("patch", f"tickets/{t.pk}/", {"status": "closed"}).status_code, 200)
        t.refresh_from_db()
        self.assertEqual(t.status, "closed")
        self.assertIsNotNone(t.closed_at)
        self.call("patch", f"tickets/{t.pk}/", {"status": "in_progress"})
        t.refresh_from_db()
        self.assertEqual((t.status, t.closed_at), ("in_progress", None))

    @override_settings(STORAGES=PLAIN_STATIC)
    def test_an_admin_note_does_not_close_a_ticket_opened_again_meanwhile(self):
        from .admin import TicketAdmin

        self.client.force_login(get_user_model().objects.create_superuser("owner", "owner@example.com", "a-long-test-password"))
        t = self._closed_crash()
        real = TicketAdmin.save_form

        def save_form_after_reopen(admin_self, request, form, change):
            self._reopened_meanwhile(t.pk)
            return real(admin_self, request, form, change)

        form = {"status": "closed", "reply": "", "owner_note": "seen it", "crashes-TOTAL_FORMS": "0", "crashes-INITIAL_FORMS": "0",
                "crashes-MIN_NUM_FORMS": "0", "crashes-MAX_NUM_FORMS": "0"}
        with mock.patch.object(TicketAdmin, "save_form", save_form_after_reopen):
            self.assertEqual(self.client.post(f"/admin/support/ticket/{t.pk}/change/", form).status_code, 302)
        t.refresh_from_db()
        self.assertEqual((t.status, t.closed_at, t.owner_note, t.count), ("new", None, "seen it", 2))


@override_settings(**GHL_ON)
class SlowListEmailTests(SupportCase):
    """GoHighLevel takes a list email but answers after the wait is up. The next cron run must not send the same list
    again as if it were new: it waits UNSURE_WAIT, then lists them once, marked as possibly a repeat."""

    def setUp(self):
        super().setUp()
        caches["limits"].clear()
        self.slow = False
        real = self.ghl.request

        def took_it_then_timed_out(method, path, *args, **kwargs):
            answer = real(method, path, *args, **kwargs)  # recorded: GoHighLevel has the email
            if self.slow and path == "/conversations/messages":
                raise GhlError(f"{method} {path} -> TimeoutError: timed out")
            return answer

        patcher = mock.patch("talks.ghl.request", side_effect=took_it_then_timed_out)
        patcher.start()
        self.addCleanup(patcher.stop)

    def slow_clock(self):
        ticks = iter(range(0, 10**6, alerts.LIST_TIMEOUT + 1))
        return mock.patch.object(alerts.time, "monotonic", lambda: next(ticks))

    def test_a_waiting_reports_list_answered_too_late_is_not_sent_again_as_new(self):
        self.ghl.down = True  # refused at once while the phones wait: the reports wait for the cron
        for n in range(alerts.INSTANT_PER_RUN + 1):
            self.report(client_key=f"rep-slow-{n:04d}")
        self.ghl.down, self.slow = False, True
        with self.slow_clock():
            self.assertEqual(alerts.run(self.later(5))["reports"], 0)
        self.assertEqual(len(self.ghl.emails), 1)
        self.assertEqual(Ticket.objects.filter(owner_alert_unsure_at__isnull=False).count(), alerts.INSTANT_PER_RUN + 1)
        self.slow = False
        self.assertEqual(alerts.run(self.later(10))["reports"], 0)  # too soon: it may well have arrived
        self.assertEqual(len(self.ghl.emails), 1)
        self.assertEqual(alerts.run(self.later(25))["reports"], alerts.INSTANT_PER_RUN + 1)
        listed = self.ghl.emails[1]
        self.assertEqual(listed["html"].count("This one may have reached you already"), alerts.INSTANT_PER_RUN + 1)
        for minutes in (40, 55, 3000):
            self.assertEqual(alerts.run(self.later(minutes))["reports"], 0)
        self.assertEqual(len(self.ghl.emails), 2)

    def test_a_crash_email_answered_too_late_is_not_sent_again_as_new(self):
        self.crash()
        self.slow = True
        with self.slow_clock():
            self.assertEqual(alerts.run(self.later(1))["crashes"], 0)
        t = Ticket.objects.get()
        self.assertEqual((len(self.ghl.emails), t.alerted_count), (1, 0))
        self.assertIsNotNone(t.owner_alert_unsure_at)
        self.slow = False
        self.assertEqual(alerts.run(self.later(10))["crashes"], 0)
        self.assertEqual(len(self.ghl.emails), 1)
        self.assertEqual(alerts.run(self.later(25))["crashes"], 1)
        self.assertIn("This one may have reached you already", self.ghl.emails[1]["html"])
        t.refresh_from_db()
        self.assertEqual((t.alerted_count, t.owner_alert_unsure_at), (1, None))
        for minutes in (40, 3000):
            self.assertEqual(alerts.run(self.later(minutes))["crashes"], 0)
        self.assertEqual(len(self.ghl.emails), 2)
        # The next step is a plain email again, not marked.
        Ticket.objects.update(count=10)
        self.assertEqual(alerts.run(self.later(3015))["crashes"], 1)
        self.assertNotIn("may have reached you", self.ghl.emails[2]["html"])

    def test_a_refused_list_email_marks_nothing(self):
        self.crash()
        self.ghl.down = True
        self.assertEqual(alerts.run(self.later(1))["crashes"], 0)
        self.assertIsNone(Ticket.objects.get().owner_alert_unsure_at)
        self.ghl.down = False
        self.assertEqual(alerts.run(self.later(2))["crashes"], 1)
        self.assertNotIn("may have reached you", self.ghl.emails[0]["html"])
