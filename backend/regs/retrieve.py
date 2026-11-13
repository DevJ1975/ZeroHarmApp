"""BM25 search over the regulation paragraphs. Plain Python: no extra service, fast enough for a few thousand chunks."""
import math
import re
from collections import Counter

from .models import RegChunk, RegSection

WORD = re.compile(r"[a-z0-9]+(?:\.[0-9]+)?")
CITE = re.compile(r"\b(19(?:10|04)\.\d+)(?:\s*\(([a-z])\))?")
STOP = set("a an and are as at be but by can do does for from has have how if in is it its may must not of on or shall "
           "should so such than that the their them then there these they this to under was were what when where which "
           "who will with you your any all each other employee employees employer".split())
_cache = {"key": None, "index": None}


def words(text: str):
    return [w for w in WORD.findall(text.lower()) if w not in STOP and len(w) > 1]


class Index:
    def __init__(self, chunks):
        self.chunks = chunks
        self.toks = [Counter(words(c.text)) for c in chunks]
        self.lens = [sum(t.values()) for t in self.toks]
        self.avg = sum(self.lens) / max(1, len(self.lens))
        self.df = Counter(w for t in self.toks for w in t)
        self.n = len(chunks)

    def search(self, query: str, k=3, where=None):
        q = set(words(query))
        scored = []
        for i, c in enumerate(self.chunks):
            if where and not where(c):
                continue
            t, s = self.toks[i], 0.0
            for w in q:
                tf = t.get(w)
                if tf:
                    idf = math.log(1 + (self.n - self.df[w] + 0.5) / (self.df[w] + 0.5))
                    s += idf * tf * 2.2 / (tf + 1.2 * (0.25 + 0.75 * self.lens[i] / self.avg))
            if s > 0:
                scored.append((s, i))
        return [self.chunks[i] for s, i in sorted(scored, reverse=True)[:k]]


def index() -> Index:
    """Cached until the library changes (a sync or an admin edit)."""
    key = (RegChunk.objects.count(), RegSection.objects.order_by("-fetched_at").values_list("fetched_at", flat=True).first())
    if _cache["key"] != key:
        _cache["key"], _cache["index"] = key, Index(list(RegChunk.objects.select_related("section").order_by("section_id", "order")))
    return _cache["index"]


def cited(text: str):
    """[(section, top-level letter or None)] cited in text, e.g. '1910.147(d)(6)' -> ('1910.147', 'd')."""
    return [(s, letter or None) for s, letter in CITE.findall(text or "")]


def for_review(brief: dict, talk_text: str, budget=12000):
    """Regulation paragraphs a safety reviewer needs for this talk: each fact's cited paragraph, then the closest
    paragraphs of the brief's referenced sections to the talk, then the closest anywhere. Returns [(citation, text)]."""
    ix = index()
    picked, out, used = set(), [], 0

    def add(chunk):
        nonlocal used
        if chunk.pk in picked or used + len(chunk.text) > budget:
            return
        picked.add(chunk.pk)
        out.append((chunk.citation, chunk.text))
        used += len(chunk.text)

    for fact in brief.get("facts", []):
        wants_appendix = any(w in fact["text"].lower() for w in ("appendix", "sample", "non-mandatory"))
        for section, letter in cited(fact.get("cite", "")):
            where = (lambda c, s=section, l=letter, a=wants_appendix:
                     c.section_id == s and (not l or c.label == f"({l})") and (a or not c.appendix))
            for c in ix.search(fact["text"], k=2, where=where):
                add(c)
    sections = {s for ref in brief.get("references", []) for s, _ in cited(ref)}
    for section in sorted(sections):
        for c in ix.search(talk_text, k=2, where=lambda c, s=section: c.section_id == s and not c.appendix):
            add(c)
    # Search everything only when the talk itself makes a regulatory claim; otherwise unrelated rules just add noise.
    if re.search(r"\bOSHA\b|\brequire|\bregulation|\brule\b|\blaw\b|\bstandard\b", talk_text, re.I):
        for c in ix.search(talk_text, k=2, where=lambda c: not c.appendix):
            add(c)
    return out


def for_otis(budget=250_000):
    """The regulation paragraphs to put on phones for OTIS: the ones its own OSHA entries and the Monday Minute facts
    point to (a cited paragraph, or the best matches for the entry), main text only. Kept small enough for a phone."""
    from monday.models import MondayTopic
    from talks.models import KbEntry

    ix = index()
    wanted = []  # (query text, section, letter)
    for e in KbEntry.objects.filter(published=True):
        for section, letter in cited(f"{e.source} {e.body}"):
            wanted.append((f"{e.title} {e.body}", section, letter))
    for t in MondayTopic.objects.filter(active=True):
        for f in t.facts:
            for section, letter in cited(f.get("cite", "")):
                wanted.append((f["text"], section, letter))
    picked, out, used = set(), [], 0
    for query, section, letter in wanted:
        where = (lambda c, s=section, l=letter: c.section_id == s and not c.appendix and (not l or c.label == f"({l})"))
        for c in ix.search(query, k=2 if not letter else 3, where=where):
            if c.pk in picked or used + len(c.text) > budget:
                continue
            picked.add(c.pk)
            out.append(c)
            used += len(c.text)
    return sorted(out, key=lambda c: (c.section_id, c.order))
