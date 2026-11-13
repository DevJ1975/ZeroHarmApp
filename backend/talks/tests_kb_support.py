"""App help in the OTIS knowledge base: the `kind` field, what phones are sent, the seeded support entries, and the
console and admin side.

A support entry is shown on the phone word for word, so most of this file checks the words themselves: that each
entry is one short fix, names buttons that really exist in the app, carries no OSHA section number, and can be found
with the words people type.

What this file does NOT check: when the phone shows app help at all. The search tests below run a Python copy of the
phone's search over the support entries only, so they show how the entries rank against each other for a question,
nothing more. Whether OTIS answers a question with app help, the safety answer or the 911 banner (the order in
ask(): the 911 rail first, then the rule that the message names the app, then a strong support match with no hazard
words) is decided in lib/otis and is tested by the app's own tests (__tests__/), not here."""
import gzip
import importlib
import math
import pathlib
import re
import unicodedata

from django.apps import apps as live_apps
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import connection
from django.test import TestCase, override_settings

from regs.retrieve import cited
from regs.sync import cited_sections

from .models import KbEntry
from .tests_console import ConsoleCase

seed = importlib.import_module("talks.migrations.0021_seed_support_kb")

NEW_TITLES = [title for title, _, _ in seed.ENTRIES]


def payload(client, path="/api/otis/kb/"):
    return client.get(path).json()["items"]


def entry_items(items):
    """The knowledge base entries in a payload (ids k<pk>), without talk sections, huddle cards and OSHA text."""
    return {i["id"]: i for i in items if re.fullmatch(r"k\d+", i["id"])}


# ---- What phones are sent ------------------------------------------------------------------------------------------

class KindInPayloadTests(TestCase):
    def setUp(self):
        cache.clear()

    def check(self, path):
        items = payload(self.client, path)
        sent = entry_items(items)
        support = KbEntry.objects.filter(published=True, kind=KbEntry.SUPPORT)
        safety = KbEntry.objects.filter(published=True, kind=KbEntry.SAFETY)
        self.assertTrue(support.exists() and safety.exists())
        for e in support:
            self.assertEqual(sent[f"k{e.pk}"].get("kind"), "support", e.title)
        for e in safety:  # a safety entry is sent exactly as it was before the field existed
            self.assertEqual(set(sent[f"k{e.pk}"]), {"id", "title", "text", "source", "lang", "tags", "issue"}, e.title)
        # Talk sections, huddle cards and regulation text are never support.
        self.assertFalse([i["id"] for i in items if i["id"] not in sent and "kind" in i])

    def test_v1_payload_marks_support_entries_only(self):
        self.check("/api/otis/kb/")

    def test_v2_payload_marks_support_entries_only(self):
        self.check("/api/v2/otis/kb")

    def test_unpublished_support_entry_is_not_sent(self):
        e = KbEntry.objects.get(title="Who to contact for help")
        e.published = False
        e.save()
        self.assertNotIn(f"k{e.pk}", entry_items(payload(self.client)))

    def test_changing_kind_changes_the_kb_version(self):
        before = self.client.get("/api/v2/otis/kb").json()["version"]
        e = KbEntry.objects.get(title="Zero Harm Weekly")
        e.kind = KbEntry.SAFETY
        e.save()
        cache.clear()
        self.assertNotEqual(self.client.get("/api/v2/otis/kb").json()["version"], before)

    def test_a_new_entry_is_a_safety_entry_unless_told_otherwise(self):
        self.assertEqual(KbEntry.objects.create(title="Forklift horns", body="Sound the horn at corners.").kind, "safety")
        # A row written without the column at all, the way the old container writes during a deploy.
        with connection.cursor() as cur:
            cur.execute("INSERT INTO talks_kbentry (title, body, source, tags, published, paused_reason, updated_at) "
                        "VALUES ('Old container row', 'Body.', '', '', %s, '', CURRENT_TIMESTAMP)", [True])
        self.assertEqual(KbEntry.objects.get(title="Old container row").kind, "safety")

    def test_api_docs_describe_kind(self):
        self.client.force_login(get_user_model().objects.create_user("staff", password="x", is_staff=True))
        schema = self.client.get("/api/v2/openapi.json").json()["components"]["schemas"]["KbItem"]
        self.assertIn("kind", schema["properties"])
        self.assertNotIn("kind", schema.get("required", []))


# ---- The seeded entries --------------------------------------------------------------------------------------------

def steps(body):
    return re.findall(r"^(\d+)\. \S", body, flags=re.M)


class SupportSeedTests(TestCase):
    def test_20_to_28_new_entries_all_there_as_support(self):
        self.assertTrue(20 <= len(seed.ENTRIES) <= 28, len(seed.ENTRIES))
        self.assertEqual(len(set(NEW_TITLES)), len(NEW_TITLES))
        for title, body, tags in seed.ENTRIES:
            e = KbEntry.objects.get(title=title)
            self.assertEqual((e.kind, e.source, e.published), ("support", "Zero Harm app help", True), title)
            self.assertEqual((e.body, e.tags), (body, tags), title)

    def test_old_app_help_became_support_and_safety_content_did_not(self):
        for title in seed.EXISTING:
            self.assertEqual(KbEntry.objects.get(title=title).kind, "support", title)
        self.assertEqual(KbEntry.objects.filter(kind="support").count(), len(seed.ENTRIES) + len(seed.EXISTING))
        # The scope note for the OSHA entries shares the label but has to stay where safety questions find it.
        for title in (seed.STAYS_SAFETY, "Someone is hurt or in danger right now", "Not sure it is safe", "Lockout/tagout: the steps"):
            self.assertEqual(KbEntry.objects.get(title=title).kind, "safety", title)
        self.assertFalse(KbEntry.objects.filter(source__startswith="OSHA 29 CFR", kind="support").exists())

    def test_every_new_entry_is_one_short_numbered_fix(self):
        rows = list(seed.ENTRIES) + [(title, new, new_tags) for title, (_, _, new, new_tags) in seed.REWRITES.items()]
        for title, body, tags in rows:
            self.assertLessEqual(len(title), 60, title)
            self.assertLess(len(body), 700, title)
            found = steps(body)
            self.assertTrue(2 <= len(found) <= 6, f"{title}: {len(found)} steps")
            self.assertEqual(found, [str(n) for n in range(1, len(found) + 1)], title)
            self.assertNotRegex(body, r"[–—]", title)  # no dashes used as punctuation, like the rest of the app
            self.assertNotIn("  ", body, title)
            for line in body.split("\n"):
                self.assertTrue(line == line.strip() and line, f"{title}: stray space or blank line")

    def test_tags_fit_and_are_plain_lower_case(self):
        for e in KbEntry.objects.filter(kind="support"):
            self.assertLessEqual(len(e.tags), 200, e.title)  # the column holds 200; PostgreSQL refuses more
            self.assertEqual(e.tags, e.tags.lower(), e.title)
            self.assertTrue(e.tags.isascii(), f"{e.title}: Spanish tags are written without accents")
        for title, _, tags in seed.ENTRIES:
            self.assertGreaterEqual(len([t for t in tags.split(",") if t.strip()]), 8, title)

    def test_no_support_entry_names_an_osha_section(self):
        with_support = cited_sections()
        for e in KbEntry.objects.filter(kind="support"):
            self.assertEqual(cited(f"{e.title} {e.source} {e.body} {e.tags}"), [], e.title)
        KbEntry.objects.filter(kind="support").delete()
        self.assertEqual(cited_sections(), with_support)  # the OSHA sync watches nothing on their account

    def test_topics_the_owner_asked_for_are_each_covered(self):
        wanted = {
            "the app closed or froze": "The app closed, crashed or froze",
            "OTIS will not download / stuck": "OTIS will not download or the download is stuck",
            "short on space": "Not enough space on the phone for OTIS",
            "OTIS slow or answers stop": "OTIS is slow or stops in the middle of an answer",
            "OTIS needs an update": "OTIS says it needs an update",
            "OTIS switched off": "OTIS is switched off or taking a break",
            "OTIS cannot answer": "OTIS says it does not have that",
            "notifications": "Notifications are not arriving",
            "no Monday Minute": "No Monday Minute is showing",
            "talk locked": "A talk is locked or not there yet",
            "Spanish": "Spanish is not offered",
            "weather and heat": "The weather and heat card is missing",
            "sheet will not save or send": "A sign-in sheet will not save or send",
            "signatures": "A signature will not save",
            "photo": "Trouble taking the group photo",
            "print and share": "The PDF will not print or share",
            "save to my records": "What Save sheet to my records does",
            "signing in": "Signing in with your email",
            "changing details": "Changing your name or email",
            "removing your info": "Removing your info",
            "holiday look": "The app looks different: the holiday look",
            "old content": "The app shows old content or will not update",
            "report a problem": "How to report a problem and see the reply",
            "flag an answer": "How to flag a wrong OTIS answer",
            "crash reports": "What a crash report sends and how to turn it off",
            "deleting data": "Deleting your data",
            "who to contact": "Who to contact for help",
        }
        for topic, title in wanted.items():
            self.assertIn(title, NEW_TITLES, topic)

    def test_the_facts_that_must_not_drift(self):
        body = lambda title: KbEntry.objects.get(title=title).body
        self.assertIn("Monday at 5:00 AM Pacific", body("Notifications are not arriving"))
        self.assertIn("Open phone settings", body("Notifications are not arriving"))
        self.assertIn("5:00 AM Pacific", body("No Monday Minute is showing"))
        self.assertIn("only in the United States", body("The weather and heat card is missing"))
        self.assertIn("You cannot unlock it from the phone", body("A talk is locked or not there yet"))
        self.assertIn("You cannot turn it on from the phone", body("Spanish is not offered"))
        self.assertIn("You cannot turn OTIS back on from the phone", body("OTIS is switched off or taking a break"))
        self.assertIn("cannot be opened again", body("I left crew sign-in before saving the sheet"))
        # The real rule for sign-ups: the first phone owns it, any other phone only asks.
        self.assertIn("Only the phone that first signed up", body("Changing your name or email"))
        self.assertIn("a person removes your info", body("Removing your info"))
        # What a crash report is said to carry has to match what the phone sends.
        crash = body("What a crash report sends and how to turn it off")
        self.assertIn("It does not send your name, your email or your OTIS chat", crash)
        self.assertIn("turn off Crash reports", crash)
        # Reporting, under the names the app's screens use.
        report = body("How to report a problem and see the reply")
        self.assertIn("tap Report a problem", report)
        self.assertIn("tap My reports", report)
        self.assertIn("Tap Report this answer", body("How to flag a wrong OTIS answer"))
        # Never a way round an emergency.
        self.assertTrue(body("Who to contact for help").startswith("1. Someone hurt or in danger: call 911 first."))

    def test_three_stale_entries_were_corrected(self):
        for title, (_, _, now, now_tags) in seed.REWRITES.items():
            e = KbEntry.objects.get(title=title)
            self.assertEqual((e.body, e.tags), (now, now_tags), title)
        self.assertNotIn("Share the PDF.", KbEntry.objects.get(title="How to run a toolbox talk in the app").body)
        self.assertNotIn("Learn tab", KbEntry.objects.get(title="Suggesting a toolbox talk topic").body)

    def test_what_otis_is_keeps_its_wording_and_says_what_can_leave_the_phone(self):
        e = KbEntry.objects.get(title="What OTIS is")
        self.assertIn("OSHA General Industry", e.body)
        self.assertIn("OTIS can be wrong.", e.body)
        self.assertIn("works with no signal. Your questions stay on the phone unless you choose to report a problem or report an answer.", e.body)
        self.assertEqual(e.body.count(seed.WHAT_OTIS_IS_ADDED), 1)

    def test_two_old_entries_got_spanish_tags_unless_the_owner_changed_them(self):
        for title, (was, now) in seed.SPANISH_TAGS.items():
            self.assertEqual(KbEntry.objects.get(title=title).tags, now, title)
            self.assertLessEqual({t.strip() for t in was.split(",")}, {t.strip() for t in now.split(",")}, title)  # the English words stay
        e = KbEntry.objects.get(title="Regulatory alerts")
        e.kind, e.tags = "safety", "my own tags"
        e.save()
        seed.seed(live_apps, None)
        self.assertEqual(KbEntry.objects.get(title="Regulatory alerts").tags, "my own tags")

    def test_the_size_guard_still_has_room(self):
        # The same limit as ConfigTests in tests.py: phones on a weak signal download this in one go.
        res = self.client.get("/api/otis/kb/", HTTP_ACCEPT_ENCODING="gzip")
        self.assertEqual(res["Content-Encoding"], "gzip")
        self.assertLess(len(res.content), 120_000)
        support = [i for i in payload(self.client) if i.get("kind") == "support"]
        self.assertLess(len(gzip.compress(repr(support).encode())), 15_000)  # app help is a small share of it


# ---- The words on the app's screens ------------------------------------------------------------------------------

# Buttons, switches, screen names and messages the entries tell people to look for, exactly as the app shows them.
ON_SCREEN = [
    # tabs and Today
    "Ask OTIS", "Open the talk", "Open the archive", "Suggest a talk", "Suggest a toolbox talk", "Search toolbox talks", "Send my idea",
    "Show local weather and heat alerts", "Ready early", "This week's talk isn't out yet", "This talk isn't available yet",
    "No signal. Showing the copy saved on this phone.", "Past Monday Minutes", "English", "Español",
    # OTIS
    "Set up OTIS", "Setting up OTIS", "Starting OTIS", "OTIS could not finish setting up", "New chat",
    "Sorry, OTIS could not answer just now", "Update Zero Harm from the App Store or Google Play", "OTIS has an update", "Update OTIS",
    "Not now, keep using OTIS as it is", "OTIS is taking a short break",
    # Settings
    "Your account", "Your name", "Email", "Sign in", "Check the email address", "Remove my info", "Notifications",
    "Monday Minute", "Weekly toolbox talk", "Zero Hour episodes", "Notifications are blocked for Zero Harm on this phone",
    "Open phone settings", "My sign-in sheets", "Daily usage count", "Contact support", "Delete my data", "We got your request",
    # the Report a problem form
    "Send report",
    # crew sign-in
    "Start crew sign-in", "Crew member name", "Add your name", "Save signature", "Clear", "Take a group photo",
    "How many people are in the photo?", "Retake", "Remove", "Save the sheet", "Your email", "Save sheet to my records",
    "Saved on this phone", "Saved to your Zero Harm records", "Could not build the sheet", "Print the sheet", "Email or share the PDF",
    "Email or share", "Could not make the PDF",
]
# The screens the support work adds. Their names are fixed by the design, so the entries may use them; they are
# checked against the app once those screens are in the tree.
BEING_ADDED = ["Report a problem", "My reports", "Crash reports", "Report this answer", "Try again"]

APP_ROOT = pathlib.Path(__file__).resolve().parents[2]
straight = lambda text: text.replace("’", "'").replace("‘", "'")


def app_source():
    """Every screen, component and helper of the phone app as one string, with the comments taken out so a name that is
    only talked about does not count as shown. "" where only the backend is checked out."""
    files = [p for folder in ("app", "components", "lib") for p in (APP_ROOT / folder).rglob("*.ts*")] if (APP_ROOT / "app").is_dir() else []
    code = "\n".join(p.read_text(encoding="utf-8") for p in files)
    code = re.sub(r"/\*.*?\*/", "", code, flags=re.S)        # block comments
    code = re.sub(r"(^|\s)//[^\n]*", r"\1", code)             # line comments (not the // in a web address)
    return straight(code)


class OnScreenWordsTests(TestCase):
    def test_every_listed_word_is_used_by_an_entry(self):
        text = "\n".join(KbEntry.objects.filter(kind="support").values_list("body", flat=True))
        for words in ON_SCREEN + BEING_ADDED:
            self.assertIn(words, text, f"no app help entry mentions {words!r}: drop it from the list")

    def test_the_app_really_shows_those_words(self):
        source = app_source()
        if not source:
            self.skipTest("the phone app's source is not here (backend-only checkout)")
        for words in ON_SCREEN:
            self.assertIn(words, source, f"an app help entry says {words!r}, but no screen in the app shows it")

    def test_the_new_screens_use_the_names_the_entries_use(self):
        if not ((APP_ROOT / "app" / "report.tsx").exists() and (APP_ROOT / "app" / "my-reports.tsx").exists()):
            self.skipTest("the report screens are not in this checkout")
        source = app_source()
        for words in BEING_ADDED:
            self.assertIn(words, source, f"an app help entry says {words!r}, but no screen in the app shows it")


# ---- The seed is careful with what is already there ---------------------------------------------------------------

class SeedIsCarefulTests(TestCase):
    def snapshot(self):
        return sorted(KbEntry.objects.values_list("title", "body", "source", "tags", "kind", "published"))

    def test_running_it_again_changes_nothing(self):
        before = self.snapshot()
        seed.seed(live_apps, None)
        self.assertEqual(self.snapshot(), before)

    def test_wording_the_owner_changed_is_kept(self):
        e = KbEntry.objects.get(title="Finding past talks")
        e.body, e.tags, e.kind = "Ask at the front office for old talks.", "office", "safety"
        e.save()
        new = KbEntry.objects.get(title="Who to contact for help")
        new.body = "Call the shop."
        new.save()
        seed.seed(live_apps, None)
        e.refresh_from_db()
        new.refresh_from_db()
        self.assertEqual((e.body, e.tags, e.kind), ("Ask at the front office for old talks.", "office", "support"))
        self.assertEqual(new.body, "Call the shop.")

    def test_an_entry_the_owner_added_under_the_app_help_label_becomes_support(self):
        mine = KbEntry.objects.create(title="Shop tablet", body="The shop tablet lives in the office.", source="Zero Harm app help")
        other = KbEntry.objects.create(title="Hot work", body="Get the permit first.", source="Site rule")
        seed.seed(live_apps, None)
        self.assertEqual(KbEntry.objects.get(pk=mine.pk).kind, "support")
        self.assertEqual(KbEntry.objects.get(pk=other.pk).kind, "safety")
        self.assertEqual(KbEntry.objects.get(title=seed.STAYS_SAFETY).kind, "safety")

    def test_marking_an_entry_moves_its_updated_at(self):
        # updated_at is part of the content version phones watch, so the change has to show there.
        e = KbEntry.objects.get(title="Regulatory alerts")
        KbEntry.objects.filter(pk=e.pk).update(kind="safety")
        seed.seed(live_apps, None)
        self.assertGreater(KbEntry.objects.get(pk=e.pk).updated_at, e.updated_at)

    def test_undo_puts_back_what_was_there_and_redo_matches(self):
        seeded = self.snapshot()
        seed.unseed(live_apps, None)
        self.assertFalse(KbEntry.objects.filter(kind="support").exists())
        self.assertFalse(KbEntry.objects.filter(title__in=NEW_TITLES).exists())
        for title, (was, was_tags, _, _) in seed.REWRITES.items():
            e = KbEntry.objects.get(title=title)
            self.assertEqual((e.body, e.tags), (was, was_tags), title)
        otis = KbEntry.objects.get(title="What OTIS is")
        self.assertNotIn("report a problem", otis.body)
        self.assertEqual(otis.tags, seed.WHAT_OTIS_IS_TAGS[0])
        seed.seed(live_apps, None)
        self.assertEqual(self.snapshot(), seeded)


# ---- Can people find them? ----------------------------------------------------------------------------------------

# A Python copy of the phone's search (lib/otis/kb.ts, as of 2026-11-11), so the words in the seed can be tried against
# the questions people type without leaving this test run. If the phone's rules change, change this copy with them.
STOP = set(("a an and are as at be but by can do does for from how i if in is it its me my of on or should so that the their them there they this "
            "to was we what when where which who why will with you your el la los las un una y o de del que en es por para con se su sus lo al como").split())
# Words that say something is wrong with the app but not what. searchSupport leaves them out of the question.
VAGUE = set(("app apps application aplicacion zero harm please help ayuda problem problems problema problemas issue issues not no wont won cant cannot "
             "doesnt doesn isnt isn didnt didn keep keeps kept just still really por favor").split())


def words(text):
    """The phone's tokenizer: lower case, accents off, split on anything that is not a letter or digit."""
    text = re.sub(r"[\u0300-\u036f]", "", unicodedata.normalize("NFD", text.lower()))
    text = re.sub(r"(^|\D)\.|\.(?!\d)", lambda m: (m.group(1) or "") + " ", text)
    return [w for w in re.split(r"[^a-z0-9.]+", text) if len(w) > 1 and w not in STOP]


def stem(word):
    """"crashing", "crashed" and "crashes" all become "crash". Support search only."""
    if len(word) < 4 or re.search(r"\d", word):
        return word
    cut = re.sub(r"(ing|ed|es|s|e)$", "", word)
    return cut if len(cut) >= 3 else word


def phone_search(items, question, k, support):
    """BM25 over the items given: the title counts twice, tags count, and a word over four letters also matches by its
    first letters. With support=True it is searchSupport: vague words dropped, words stemmed, and an entry must hold at
    least half of the words that are left. With support=False it is the plain safety search."""
    shape = (lambda ws: [stem(w) for w in ws]) if support else (lambda ws: ws)
    toks = [shape(words(f"{i['title']} {i['title']} {i.get('tags') or ''} {i['text']}")) for i in items]
    asked = list(dict.fromkeys(shape([w for w in words(question) if not (support and w in VAGUE)])))
    avg = sum(len(t) for t in toks) / max(1, len(toks))
    df = {}
    for t in toks:
        for w in set(t):
            df[w] = df.get(w, 0) + 1
    scored = []
    for item, t in zip(items, toks):
        score, hits = 0.0, 0
        for w in asked:
            first_letters = len(w) > 4 and not re.search(r"\d", w)
            tf = sum(1 for x in t if x == w or (first_letters and x.startswith(w[:-1])))
            if tf:
                hits += 1
                idf = math.log(1 + (len(items) - df.get(w, 0) + 0.5) / (df.get(w, 0) + 0.5))
                score += (idf * tf * 2.2) / (tf + 1.2 * (0.25 + 0.75 * (len(t) / avg)))
        if score > 0.5 and (not support or hits * 2 >= len(asked)):
            scored.append((score, item["title"]))
    return [title for _, title in sorted(scored, reverse=True)[:k]]


# What a worker might type, and the entry the phone has to show first (it shows the best match word for word).
QUESTIONS_EN = [
    ("the app keeps crashing", "The app closed, crashed or froze"),
    ("app crashed", "The app closed, crashed or froze"),
    ("app is frozen", "The app closed, crashed or froze"),
    ("the app is stuck", "The app closed, crashed or froze"),
    ("app not working", "The app closed, crashed or froze"),
    ("otis won't download", "OTIS will not download or the download is stuck"),
    ("OTIS download is stuck at 40%", "OTIS will not download or the download is stuck"),
    ("otis stuck on setting up", "OTIS will not download or the download is stuck"),
    ("not enough storage for otis", "Not enough space on the phone for OTIS"),
    ("otis is really slow", "OTIS is slow or stops in the middle of an answer"),
    ("otis stopped answering", "OTIS is slow or stops in the middle of an answer"),
    ("otis says update the app", "OTIS says it needs an update"),
    ("otis is taking a short break", "OTIS is switched off or taking a break"),
    ("otis is turned off", "OTIS is switched off or taking a break"),
    ("otis says it doesn't have that in its knowledge base", "OTIS says it does not have that"),
    ("I am not getting notifications", "Notifications are not arriving"),
    ("notifications not working", "Notifications are not arriving"),
    ("didn't get the monday notification", "Notifications are not arriving"),
    ("what time does the notification come", "Notifications are not arriving"),
    ("monday minute is not showing", "No Monday Minute is showing"),
    ("there is no monday minute this week", "No Monday Minute is showing"),
    ("the talk is locked", "A talk is locked or not there yet"),
    ("talk isn't out yet", "A talk is locked or not there yet"),
    ("how do I change the language to spanish", "Spanish is not offered"),
    ("the weather is not showing", "The weather and heat card is missing"),
    ("heat card missing", "The weather and heat card is missing"),
    ("signature won't save", "A signature will not save"),
    ("camera won't open for the group photo", "Trouble taking the group photo"),
    ("sign-in sheet won't save", "A sign-in sheet will not save or send"),
    ("sign in sheet not sending", "A sign-in sheet will not save or send"),
    ("where does save sheet to my records go", "What Save sheet to my records does"),
    ("the pdf won't print", "The PDF will not print or share"),
    ("can't share the pdf", "The PDF will not print or share"),
    ("i lost my signatures", "I left crew sign-in before saving the sheet"),
    ("i went back and the sheet is gone", "I left crew sign-in before saving the sheet"),
    ("login not working", "Signing in with your email"),
    ("what is my password", "Signing in with your email"),
    ("how do I change my email", "Changing your name or email"),
    ("my name is wrong", "Changing your name or email"),
    ("remove my info", "Removing your info"),
    ("how do I unsubscribe", "Removing your info"),
    ("how do I delete my account", "Deleting your data"),
    ("why does the app look different", "The app looks different: the holiday look"),
    ("why are there christmas lights", "The app looks different: the holiday look"),
    ("the talks are not updating", "The app shows old content or will not update"),
    ("the content is old", "The app shows old content or will not update"),
    ("how do I report a problem", "How to report a problem and see the reply"),
    ("I want to report a bug", "How to report a problem and see the reply"),
    ("did you reply to my report", "How to report a problem and see the reply"),
    ("otis gave a wrong answer", "How to flag a wrong OTIS answer"),
    ("otis is wrong", "How to flag a wrong OTIS answer"),
    ("what does a crash report send", "What a crash report sends and how to turn it off"),
    ("turn off crash reports", "What a crash report sends and how to turn it off"),
    ("who do I contact", "Who to contact for help"),
    ("is there a phone number for support", "Who to contact for help"),
    ("how do I run a toolbox talk", "How to run a toolbox talk in the app"),
    ("where are the old talks", "Finding past talks"),
    ("how do I suggest a topic", "Suggesting a toolbox talk topic"),
    ("what is otis", "What OTIS is"),
    ("how do I get alerts about new osha rules", "Regulatory alerts"),
    ("how do I subscribe to the weekly newsletter", "Zero Harm Weekly"),
]
# The same problems as a Spanish speaker would type them. The entries are in English; these find them through the tags.
QUESTIONS_ES = [
    ("la app se cierra sola", "The app closed, crashed or froze"),
    ("la aplicacion no funciona", "The app closed, crashed or froze"),
    ("se traba la app", "The app closed, crashed or froze"),
    ("otis no descarga", "OTIS will not download or the download is stuck"),
    ("no tengo espacio para otis", "Not enough space on the phone for OTIS"),
    ("otis esta muy lento", "OTIS is slow or stops in the middle of an answer"),
    ("otis no responde", "OTIS is slow or stops in the middle of an answer"),
    ("otis pide actualizar", "OTIS says it needs an update"),
    ("otis no esta disponible", "OTIS is switched off or taking a break"),
    ("otis no sabe", "OTIS says it does not have that"),
    ("no me llegan las notificaciones", "Notifications are not arriving"),
    ("no aparece la charla del lunes", "No Monday Minute is showing"),
    ("la charla no esta disponible", "A talk is locked or not there yet"),
    ("no hay espanol", "Spanish is not offered"),
    ("quiero la app en español", "Spanish is not offered"),
    ("no aparece el clima", "The weather and heat card is missing"),
    ("la firma no se guarda", "A signature will not save"),
    ("la camara no abre", "Trouble taking the group photo"),
    ("no se guarda la hoja de asistencia", "A sign-in sheet will not save or send"),
    ("donde se guardan las hojas", "What Save sheet to my records does"),
    ("no puedo imprimir", "The PDF will not print or share"),
    ("se borraron las firmas", "I left crew sign-in before saving the sheet"),
    ("no puedo iniciar sesion", "Signing in with your email"),
    ("quiero cambiar mi correo", "Changing your name or email"),
    ("quiero darme de baja", "Removing your info"),
    ("borrar mis datos", "Deleting your data"),
    ("la app se ve diferente", "The app looks different: the holiday look"),
    ("no se actualiza", "The app shows old content or will not update"),
    ("quiero reportar un problema", "How to report a problem and see the reply"),
    ("la respuesta de otis esta mal", "How to flag a wrong OTIS answer"),
    ("como apago los reportes", "What a crash report sends and how to turn it off"),
    ("como contacto a soporte", "Who to contact for help"),
    ("alertas de reglas nuevas de osha", "Regulatory alerts"),
    ("como me suscribo al boletin semanal", "Zero Harm Weekly"),
]
QUESTIONS = QUESTIONS_EN + QUESTIONS_ES


class SupportSearchTests(TestCase):
    """Ranking only: which support entry a copy of the phone's support search puts first. See the top of this file
    for what it does not check."""

    def setUp(self):
        cache.clear()
        items = payload(self.client)
        self.support = [i for i in items if i.get("kind") == "support"]
        self.safety = [i for i in items if i.get("kind") != "support"]

    def test_typical_questions_show_the_right_entry_first(self):
        missed = []
        for question, want in QUESTIONS:
            got = phone_search(self.support, question, 2, support=True)
            if got[:1] != [want]:
                missed.append((question, want, got))
        self.assertEqual(missed, [])

    def test_a_question_with_nothing_to_go_on_shows_no_entry(self):
        # "A problem with the app" names nothing. The phone then offers to file a report instead of guessing an entry.
        for question in ("a problem with the app", "help", "necesito ayuda con la app", "zero harm no"):
            self.assertEqual(phone_search(self.support, question, 2, support=True), [], question)

    def test_every_new_entry_is_asked_for_in_english_and_in_spanish(self):
        # So the check above really covers each entry both ways, not just the easy ones.
        for label, questions in (("English", QUESTIONS_EN), ("Spanish", QUESTIONS_ES)):
            self.assertEqual(set(NEW_TITLES) - {want for _, want in questions}, set(), f"no {label} question for these")

    def test_the_two_pools_stay_apart(self):
        # The phone searches support items and safety items separately. Sorting by kind must leave nothing in both,
        # and the entry people need in an emergency must be on the safety side.
        self.assertFalse({i["id"] for i in self.support} & {i["id"] for i in self.safety})
        self.assertIn("Someone is hurt or in danger right now", phone_search(self.safety, "someone is hurt and bleeding", 4, support=False))
        self.assertNotIn("Someone is hurt or in danger right now", [i["title"] for i in self.support])


# ---- Console and admin --------------------------------------------------------------------------------------------

class ConsoleKindTests(ConsoleCase):
    def test_console_shows_and_accepts_kind(self):
        r = self.call("post", "kb/", {"title": "Battery is draining", "body": "1. Close the app.\n2. Open it again.", "kind": "support"})
        self.assertEqual((r.status_code, r.json()["kind"]), (201, "support"))
        pk = r.json()["id"]
        self.assertEqual(entry_items(payload(self.client))[f"k{pk}"]["kind"], "support")
        listed = {e["id"]: e for e in self.call("get", "kb/").json()["entries"]}
        self.assertEqual(listed[pk]["kind"], "support")
        self.assertEqual(listed[KbEntry.objects.get(title="Lockout/tagout: the steps").pk]["kind"], "safety")
        self.assertEqual(self.call("patch", f"kb/{pk}/", {"kind": "safety"}).json()["kind"], "safety")
        cache.clear()
        self.assertNotIn("kind", entry_items(payload(self.client))[f"k{pk}"])

    def test_kind_defaults_to_safety_and_other_edits_leave_it_alone(self):
        r = self.call("post", "kb/", {"title": "Forklift seat belts", "body": "Wear the belt."})
        self.assertEqual(r.json()["kind"], "safety")
        help_pk = KbEntry.objects.get(title="Who to contact for help").pk
        self.assertEqual(self.call("patch", f"kb/{help_pk}/", {"tags": "contact, help"}).json()["kind"], "support")

    def test_unknown_kind_is_refused(self):
        for bad in ("help", "", None, 3):
            r = self.call("post", "kb/", {"title": "T", "body": "B", "kind": bad})
            self.assertEqual(r.status_code, 400, bad)
            self.assertIn("kind must be one of: safety, support", r.json()["error"])
        self.assertFalse(KbEntry.objects.filter(title="T").exists())

    def test_app_help_cannot_name_an_osha_section(self):
        r = self.call("post", "kb/", {"title": "Lockout help", "body": "See 1910.147 for the steps.", "kind": "support"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("App help can't name an OSHA section number", r.json()["error"])
        self.assertFalse(KbEntry.objects.filter(title="Lockout help").exists())
        # A safety entry may, and it cannot then be turned into app help without taking the number out.
        pk = self.call("post", "kb/", {"title": "Lockout help", "body": "See 1910.147 for the steps."}).json()["id"]
        self.assertEqual(self.call("patch", f"kb/{pk}/", {"kind": "support"}).status_code, 400)
        self.assertEqual(KbEntry.objects.get(pk=pk).kind, "safety")
        r = self.call("patch", f"kb/{pk}/", {"kind": "support", "body": "See your site's lockout steps."})
        self.assertEqual((r.status_code, r.json()["kind"]), (200, "support"))


PLAIN_STATIC = {"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
                "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}}


@override_settings(STORAGES=PLAIN_STATIC)  # admin pages link their stylesheets; tests have no collected static files
class AdminKindTests(TestCase):
    def setUp(self):
        self.client.force_login(get_user_model().objects.create_superuser("owner", "owner@example.com", "a-long-test-password"))

    def test_admin_lists_and_filters_by_kind(self):
        page = self.client.get("/admin/talks/kbentry/?kind__exact=support")
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Who to contact for help")
        self.assertContains(page, "App help")
        self.assertNotContains(page, "Lockout/tagout: the steps")
        self.assertContains(self.client.get("/admin/talks/kbentry/?kind__exact=safety"), "Lockout/tagout: the steps")

    def test_admin_form_has_kind_and_refuses_an_osha_number_in_app_help(self):
        self.assertContains(self.client.get("/admin/talks/kbentry/add/"), 'name="kind"')
        data = {"title": "Lockout help", "body": "See 1910.147 for the steps.", "source": "", "tags": "", "kind": "support", "published": "on", "paused_reason": ""}
        page = self.client.post("/admin/talks/kbentry/add/", data)
        self.assertContains(page, "App help can&#x27;t name an OSHA section number")
        self.assertFalse(KbEntry.objects.filter(title="Lockout help").exists())
        self.client.post("/admin/talks/kbentry/add/", {**data, "body": "See your site's lockout steps."})
        self.assertEqual(KbEntry.objects.get(title="Lockout help").kind, "support")

    def test_model_check_only_bites_app_help(self):
        KbEntry(title="A", body="See 1910.147.", kind="safety").clean()
        KbEntry(title="A", body="Open Settings.", source="Zero Harm app help", kind="support").clean()
        with self.assertRaises(ValidationError):
            KbEntry(title="A", body="Open Settings.", source="OSHA 29 CFR 1904.7", kind="support").clean()
