"""Reads a Zero Harm Weekly email template (HTML) into the parts the app shows."""
import html
import re
from datetime import date, datetime
from html.parser import HTMLParser

NAME_RE = re.compile(r"^Zero Harm Weekly #(\d+)\s*[–—-]\s*(.+?)\s*\(([A-Z][a-z]+ \d{1,2}, \d{4})\)\s*$")
FLAG_RE = re.compile(r"\[[^\]]{3,}\]")
BLOCK_TAGS = {"p", "div", "td", "tr", "li", "h1", "h2", "h3", "h4", "table", "br"}


def parse_name(name):
    """'Zero Harm Weekly #23 – Heat Stroke Is a 911 Call (June 7, 2027)' -> (23, title, date) or None."""
    m = NAME_RE.match((name or "").strip())
    if not m:
        return None
    for fmt in ("%B %d, %Y", "%b %d, %Y"):  # "January 4, 2027" or "Jan 4, 2027"
        try:
            return int(m.group(1)), m.group(2).strip(), datetime.strptime(m.group(3), fmt).date()
        except ValueError:
            continue
    return None


class _Lines(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.lines, self.buf, self.links, self.images, self.skip = [], [], [], [], 0

    def _flush(self):
        text = re.sub(r"\s+", " ", "".join(self.buf)).strip()
        if text:
            self.lines.append(text)
        self.buf = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in ("style", "script", "head"):
            self.skip += 1
        if tag == "a" and a.get("href"):
            self.links.append(a["href"])
        if tag == "img" and a.get("src"):
            self.images.append(a["src"])
        if tag in BLOCK_TAGS:
            self._flush()

    def handle_endtag(self, tag):
        if tag in ("style", "script", "head"):
            self.skip = max(0, self.skip - 1)
        if tag in BLOCK_TAGS:
            self._flush()

    def handle_data(self, data):
        if not self.skip:
            self.buf.append(data)


def _between(lines, start, stops):
    """Lines after the first line starting with `start`, up to the first line starting with any of `stops`."""
    up = [s.upper() for s in stops]
    try:
        i = next(k for k, l in enumerate(lines) if l.upper().startswith(start.upper()))
    except StopIteration:
        return []
    out = []
    for l in lines[i + 1:]:
        if any(l.upper().startswith(s) for s in up):
            break
        out.append(l)
    return out


def parse_issue(html_text, title):
    p = _Lines()
    p.feed(html_text)
    p._flush()
    lines = [html.unescape(l) for l in p.lines]

    # The month kicker ("JUNE · HEAT · WEEK 1 OF 4") sits above the headline in every issue; the intro follows the headline.
    kicker, intro, start = "", [], None
    for k, l in enumerate(lines):
        if re.match(r"^[A-Z]+ · [A-Z&/ ]+ · WEEK", l):
            kicker, start = l, k + 2  # skip the headline line
            if l.endswith(title) or not re.search(r"OF \d+$", l):
                start = k + 1  # headline glued onto the kicker line
            break
    if start is None:  # fall back to finding the headline by the template's title
        start = next((k + 1 for k, l in enumerate(lines) if k > 2 and title in l), None)
    if start is not None:
        for nxt in lines[start:]:
            if nxt.lower().startswith(("free this week", "download pdf", "talk it through")):
                break
            intro.append(nxt)

    points = _between(lines, "Talk it through", ["THE FIX", "CLOSE CALL", "WHAT OSHA"])
    story = _between(lines, "CLOSE CALL", ["WHAT OSHA", "LAST WEEK", "CREW CHECK"])
    osha = _between(lines, "WHAT OSHA SAYS", ["LAST WEEK", "CREW CHECK"])
    last = _between(lines, "LAST WEEK", ["CREW CHECK"])
    crew = _between(lines, "CREW CHECK", ["Reply with your answer", "See Soteria", "Book a"])

    story_title, story_text = (story[0], story[1:]) if story else ("", [])
    sections = []
    if intro:
        sections.append("\n\n".join(intro))
    if points:
        sections.append("## Talk it through with your crew\n\n" + "\n\n".join(points))
    if story_text:
        sections.append(f"## Close call: {story_title}\n\n" + "\n\n".join(story_text))
    if osha:
        sections.append("## What OSHA says\n\n" + "\n\n".join(osha))
    if last:
        sections.append("## Last week’s answer\n\n" + "\n\n".join(last))
    body = "\n\n".join(sections)

    pdf = next((u for u in p.links if u.lower().split("?")[0].endswith(".pdf")), "")
    hero = next((u for u in p.images if "/img/" in u or "hero" in u.lower()), "")
    theme = kicker.split("·")[1].strip().title() if kicker.count("·") >= 1 else ""
    theme = re.sub(r"Week \d.*$", "", theme).strip()
    shown = " ".join([body, story_title, crew[0] if crew else ""])
    flags = sorted(set(FLAG_RE.findall(shown)))
    problems = []
    if not points or not crew:
        problems.append("Could not find the talking points or the crew question in this template.")
    return {
        "body_md": body,
        "story_title": story_title,
        "crew_question": crew[0] if crew else "",
        "pdf_url": pdf,
        "hero_url": hero,
        "month_theme": theme,
        "flags": flags + problems,
    }
