"""Fetches and splits OSHA sections from the eCFR API (the official, current Code of Federal Regulations)."""
import gzip
import hashlib
import json
import re
import urllib.request
import xml.etree.ElementTree as ET

API = "https://www.ecfr.gov/api/versioner/v1"
SECTION = re.compile(r"\b(19(?:10|04)\.\d+)")
APPENDIX = re.compile(r"^Appendix [A-Z0-9]+ to (§|Section|Part)", re.I)
TOP = re.compile(r"^\(([a-z])\)(?=\s|\()")
BLOCKS = ("P", "FP", "HD", "TABLE", "GPOTABLE")  # tag prefixes read as one block each (P-2, FP-DASH, HD1...)
MAX_CHUNK = 2500  # characters; long paragraphs are split so retrieval stays focused


def _get(url: str, timeout=60) -> bytes:
    req = urllib.request.Request(url, headers={"Accept-Encoding": "gzip", "User-Agent": "zero-harm-regs/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as res:
        body = res.read()
        return gzip.decompress(body) if res.headers.get("Content-Encoding") == "gzip" else body


def latest_date() -> str:
    """The date Title 29 is current to on the eCFR."""
    titles = json.loads(_get(f"{API}/titles.json"))["titles"]
    return next(t for t in titles if t["number"] == 29)["up_to_date_as_of"]


def fetch_xml(section: str, date: str) -> bytes:
    return _get(f"{API}/full/{date}/title-29.xml?section={section}", timeout=120)


def _flat(el, sep="") -> str:
    """Whitespace-normalized text. The full-section hash uses sep="" to match the reviewed baseline; table cells in
    chunks use sep=" " so values don't run together."""
    return " ".join(sep.join(el.itertext()).split())


def text_hash(full_text: str) -> str:
    return hashlib.sha256(full_text.encode()).hexdigest()


def parse(xml: bytes, section: str):
    """(heading, full_text, chunks). full_text is normalized the same way the reviewed baseline was."""
    root = ET.fromstring(xml)
    div = next((d for d in root.iter("DIV8") if d.get("N") == section), None)
    if div is None:
        raise ValueError(f"Section {section} not found in the eCFR response")
    head = div.find("HEAD")
    heading = _flat(head) if head is not None else ""
    heading = re.sub(rf"^§\s*{re.escape(section)}\s*", "", heading)
    full_text = _flat(div)
    return heading, full_text, chunk(div)


def _blocks(el):
    """Paragraph-level elements in document order. A table is one block, so its cells stay together."""
    for child in el:
        if child.tag.startswith(BLOCKS):
            yield child
        elif child.tag not in ("HEAD", "CITA", "SOURCE", "AUTH"):
            yield from _blocks(child)


def chunk(div):
    """Groups paragraphs under their top-level letter, (a), (b)..., then appendices. Splits long groups."""
    groups, label, appendix, buf = [], "(intro)", False, []

    def flush():
        if buf:
            groups.append((label, appendix, " ".join(buf)))

    for el in _blocks(div):
        t = _flat(el, " " if el.tag.endswith("TABLE") else "")
        if not t:
            continue
        if APPENDIX.match(t):
            flush()
            buf, appendix = [t], True
            label = " ".join(t.split()[:2])  # "Appendix A"
            continue
        m = TOP.match(t)
        if m and not appendix:
            letter = m.group(1)
            current = label[1] if label.startswith("(") and len(label) == 3 else None
            if (current is None and letter == "a") or (current and ord(letter) == ord(current) + 1):
                flush()
                buf, label = [], f"({letter})"
        buf.append(t)
    flush()
    out = []
    for label, appx, text in groups:
        while len(text) > MAX_CHUNK:
            cut = text.rfind(". ", 0, MAX_CHUNK) + 1 or MAX_CHUNK
            out.append((label, appx, text[:cut].strip()))
            text = text[cut:].strip()
        if text:
            out.append((label, appx, text))
    return out
