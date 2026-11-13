import datetime as dt
from django.test import TestCase

from monday.models import MondayTopic
from talks.models import KbEntry

from . import ecfr
from .models import RegChange, RegChunk, RegSection
from .retrieve import cited, for_otis, for_review
from .sync import sync


def xml(section="1910.999", d_text="Verify isolation before work starts.", extra=""):
    return f"""<ECFR><DIV8 N="{section}" TYPE="SECTION"><HEAD>§ {section} Test standard.</HEAD>
      <P>(a) Scope. This section covers test machines.</P>
      <P>(b)(1) Definitions. Energy isolating device means a disconnect.</P>
      <P>(c) Program. The employer shall establish a program.</P>
      <P>(d) Application of control. {d_text}</P>
      <P>(i) Training is required.</P>
      <TABLE><TR><TD>Duration</TD><TD>90</TD></TR></TABLE>{extra}
      <HD1>Appendix A to § {section}—Sample procedure</HD1><P>Try the start button.</P>
    </DIV8></ECFR>""".encode()


class ParseTests(TestCase):
    def test_paragraph_labels_tables_and_appendix(self):
        heading, full, chunks = ecfr.parse(xml(), "1910.999")
        self.assertEqual(heading, "Test standard.")
        labels = [(label, appx) for label, appx, _ in chunks]
        # (b)(1) starts paragraph (b); "(i) Training" after (d) is a roman sub-paragraph, not a new top level
        self.assertEqual(labels, [("(a)", False), ("(b)", False), ("(c)", False), ("(d)", False), ("Appendix A", True)])
        self.assertIn("Duration 90", chunks[3][2])
        self.assertEqual(ecfr.text_hash(full), ecfr.text_hash(" ".join(full.split())))

    def test_long_paragraphs_are_split(self):
        long = "Each step shall be done. " * 400
        _, _, chunks = ecfr.parse(xml(d_text=long), "1910.999")
        d = [t for label, _, t in chunks if label == "(d)"]
        self.assertGreater(len(d), 1)
        self.assertTrue(all(len(t) <= ecfr.MAX_CHUNK for t in d))

    def test_cited(self):
        self.assertEqual(cited("OSHA 29 CFR 1910.147(e) and (c)(6), 1904.39"), [("1910.147", "e"), ("1904.39", None)])


class SeedAndRetrievalTests(TestCase):
    """Runs on the reviewed regulation text loaded by migration regs/0002."""

    def test_seed_loaded(self):
        self.assertGreaterEqual(RegSection.objects.count(), 45)
        lockout = RegSection.objects.get(section="1910.147")
        self.assertEqual(lockout.as_of, dt.date(2026, 11, 6))
        self.assertTrue(lockout.chunks.filter(label="(d)").exists())
        self.assertTrue(lockout.chunks.filter(appendix=True).exists())

    def test_review_context_finds_the_cited_paragraphs(self):
        brief = {"facts": [{"text": "Lockout steps must be done in order: prepare, shut down, isolate, apply locks, release stored energy, verify.",
                            "cite": "1910.147"}], "references": ["1910.147"]}
        cites = [c for c, _ in for_review(brief, "Shut down, isolate, lock out and verify before you reach in.")]
        self.assertIn("29 CFR 1910.147(d)", cites)
        self.assertTrue(all(c.startswith("29 CFR 1910.147") for c in cites))

    def test_no_unrelated_rules_unless_the_talk_claims_one(self):
        self.assertEqual(for_review({"facts": [], "references": []}, "Drink water, rest in the shade."), [])
        self.assertTrue(for_review({"facts": [], "references": []}, "OSHA requires water every hour."))

    def test_otis_gets_a_phone_sized_slice(self):
        chunks = for_otis()
        self.assertTrue(chunks)
        self.assertLessEqual(sum(len(c.text) for c in chunks), 250_000)
        self.assertFalse(any(c.appendix for c in chunks))
        self.assertIn("1910.147", {c.section_id for c in chunks})


class SyncTests(TestCase):
    def setUp(self):
        RegSection.objects.all().delete()
        self.topic = MondayTopic.objects.create(slug="test-topic", title="Test", category="Machines", hazard="h",
                                                key_points=["a", "b", "c", "d"], must_say=["x"], facts=[{"text": "t", "cite": "1910.999"}],
                                                references=["1910.999"], crew_questions=["q?", "r?"])
        self.entry = KbEntry.objects.create(title="Test rule", body="Per 1910.999 do it.", source="OSHA 29 CFR 1910.999(d)")
        self.other = KbEntry.objects.create(title="Other", body="Unrelated.", source="OSHA 29 CFR 1910.22")

    def run_sync(self, body):
        return sync(sections=["1910.999"], fetch=lambda s, d: body, latest=lambda: "2027-01-15")

    def test_first_sync_loads_without_pausing(self):
        self.run_sync(xml())
        sec = RegSection.objects.get(section="1910.999")
        self.assertEqual((sec.as_of, sec.chunks.count()), (dt.date(2027, 1, 15), 5))
        self.assertFalse(RegChange.objects.exists())
        self.topic.refresh_from_db()
        self.assertTrue(self.topic.active)

    def test_amendment_pauses_topics_and_otis_entries(self):
        self.run_sync(xml())
        log = self.run_sync(xml(d_text="Verify isolation and test for voltage before work starts."))
        change = RegChange.objects.get()
        self.assertIn("CHANGED", " ".join(log))
        self.topic.refresh_from_db()
        self.entry.refresh_from_db()
        self.other.refresh_from_db()
        self.assertFalse(self.topic.active)
        self.assertIn("OSHA changed 29 CFR 1910.999", self.topic.paused_reason)
        self.assertFalse(self.entry.published)
        self.assertTrue(self.other.published)
        self.assertIn("Monday Minute topic: Test", change.paused)
        self.assertIn("OTIS entry: Test rule", change.paused)
        self.assertIn("test for voltage", " ".join(RegChunk.objects.values_list("text", flat=True)))

    def test_unchanged_text_changes_nothing(self):
        self.run_sync(xml())
        self.run_sync(xml())
        self.assertFalse(RegChange.objects.exists())

    def test_fetch_failure_is_logged_not_raised(self):
        def boom(s, d):
            raise OSError("eCFR down")
        log = sync(sections=["1910.999"], fetch=boom, latest=lambda: "2027-01-15")
        self.assertIn("could not fetch", " ".join(log))

