"""Writes, checks and schedules the weekly Monday Minute. Runs from `python manage.py monday_minute` (the cron service).
The AI runs on your own server (AI_PROVIDER=local, Ollama) or on Claude (AI_PROVIDER=anthropic); see ai.py.

Safety design, because no person approves each talk:
1. The writer sees ONE topic brief from the CSP-reviewed topic bank and may use nothing else.
2. Hard checks run on every draft: required lines present word for word, no number that isn't in the brief, no links,
   one crew question, sane length.
3. A second AI call reviews the draft as a Certified Safety Professional against the brief and maps every point to a
   brief line. Any MUST FIX finding or ungrounded point fails the draft. In strict mode (the default with the local
   model), a second independent review must also pass, and both must be highly confident. The writer gets the findings and tries again, up to 3 times per topic, 2 topics per week.
4. If nothing passes, that week has no Monday Minute (the app keeps showing last week's). Nothing unchecked publishes.
   A talk that passes publishes on its own only if this AI setup has passed the safety test (gate.py); otherwise it
   waits in the admin for a person to approve it.
5. After publishing, crews' "isn't safe or isn't right" reports pull the talk and pause its topic (see api.py).
"""
import datetime as dt
import hashlib
import json
import logging
import re
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db.models import Count, Q
from django.utils import timezone

from .ai import AIUnavailable, GenerationError, ai_json, is_local
from .gate import status as gate_status
from .models import MondayFeedback, MondayMinute, MondayTopic

log = logging.getLogger(__name__)
PACIFIC = ZoneInfo("America/Los_Angeles")
PUBLISH_TIME = dt.time(5, 0)
WRITE_DAYS_AHEAD = 5          # start writing Wednesday for the next Monday
ATTEMPTS_PER_TOPIC = 3
TOPICS_PER_WEEK = 2
NO_REPEAT_WEEKS = 104


# ---- Schedule ---------------------------------------------------------------------------------------

def publish_time(week: dt.date) -> dt.datetime:
    return dt.datetime.combine(week, PUBLISH_TIME, PACIFIC).astimezone(dt.timezone.utc)


def next_week(now=None) -> dt.date:
    """The next Monday whose 5:00 AM Pacific publish time is still ahead."""
    now = now or timezone.now()
    day = now.astimezone(PACIFIC).date()
    monday = day + dt.timedelta(days=(7 - day.weekday()) % 7)
    if publish_time(monday) <= now:
        monday += dt.timedelta(days=7)
    return monday


def due_week(now=None):
    """The week to write now, or None when it's too early or that week is already done or given up on."""
    now = now or timezone.now()
    week = next_week(now)
    if now < publish_time(week) - dt.timedelta(days=WRITE_DAYS_AHEAD):
        return None
    rows = MondayMinute.objects.filter(week=week)
    if rows.exclude(status=MondayMinute.BLOCKED).exists() or rows.filter(status=MondayMinute.BLOCKED).count() >= TOPICS_PER_WEEK:
        return None
    return week


# ---- Topic choice -----------------------------------------------------------------------------------

def candidates(week: dt.date):
    """Active topics not used in the last two years, best first: in season, well rated, least used."""
    recent = MondayMinute.objects.filter(week__gt=week - dt.timedelta(weeks=NO_REPEAT_WEEKS)).exclude(status=MondayMinute.BLOCKED)
    tried_this_week = MondayMinute.objects.filter(week=week).values_list("topic_id", flat=True)
    pool = MondayTopic.objects.filter(active=True).exclude(pk__in=tried_this_week)
    fresh = pool.exclude(pk__in=recent.values_list("topic_id", flat=True))
    pool = fresh if fresh.exists() else pool  # bank used up: start over with the least recent
    pool = pool.annotate(
        ups=Count("talks__feedback", filter=Q(talks__feedback__helpful=True)),
        downs=Count("talks__feedback", filter=Q(talks__feedback__helpful=False)),
        uses=Count("talks", filter=~Q(talks__status=MondayMinute.BLOCKED)),
    )

    def score(t):
        season = 2 if week.month in (t.months or []) else (-1 if t.months else 0)
        rating = (t.ups - t.downs) / max(1, t.ups + t.downs)
        tiebreak = int(hashlib.sha256(f"{t.slug}{week}".encode()).hexdigest()[:6], 16) / 0xFFFFFF
        return season + rating - 0.5 * t.uses + tiebreak * 0.1

    return sorted(pool, key=score, reverse=True)


def feedback_notes(topic: MondayTopic) -> list[str]:
    """What crews said about earlier talks, as style notes for the writer. Never instructions, only counts."""
    notes = []
    labels = dict(MondayFeedback.REASONS)
    since = timezone.now() - dt.timedelta(weeks=12)
    recent = MondayFeedback.objects.filter(helpful=False, created_at__gte=since)
    for key in ("too_long", "confusing", "too_basic"):
        n = sum(1 for f in recent.only("reasons") if key in (f.reasons or []))
        if n >= 3:
            notes.append(f"Crews rated {n} recent talks '{labels[key]}'. Adjust for that.")
    mine = MondayFeedback.objects.filter(minute__topic=topic)
    if mine.exists():
        up, down = mine.filter(helpful=True).count(), mine.filter(helpful=False).count()
        notes.append(f"Earlier talks on this topic got {up} thumbs up and {down} thumbs down.")
    return notes


# ---- Claude calls -----------------------------------------------------------------------------------

TALK_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "Up to 8 words"},
        "intro": {"type": "string", "description": "2 or 3 sentences: why this matters on the floor today"},
        "points": {"type": "array", "items": {"type": "string"}, "description": "3 to 5 numbered actions, 1 or 2 sentences each"},
        "story_title": {"type": "string", "description": "Up to 6 words"},
        "story": {"type": "string", "description": "3 to 5 sentences: an anonymous close call built from the story seed"},
        "crew_question": {"type": "string", "description": "One open question about the crew's own site, ending with ?"},
        "takeaway": {"type": "string", "description": "One sentence to remember"},
    },
    "required": ["title", "intro", "points", "story_title", "story", "crew_question", "takeaway"],
    "additionalProperties": False,
}

REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["pass", "fail"]},
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "severity": {"type": "string", "enum": ["must_fix", "should_fix"]},
                    "where": {"type": "string"},
                    "issue": {"type": "string"},
                    "fix": {"type": "string", "description": "Replacement wording"},
                },
                "required": ["severity", "where", "issue", "fix"],
                "additionalProperties": False,
            },
        },
        "grounding": {
            "type": "array",
            "description": "One entry per talk point, in order. point is 0-based; brief_key_point is the 0-based index into the brief key_points it comes from, or -1 if none",
            "items": {
                "type": "object",
                "properties": {"point": {"type": "integer"}, "brief_key_point": {"type": "integer"}},
                "required": ["point", "brief_key_point"],
                "additionalProperties": False,
            },
        },
        "confidence": {"type": "string", "enum": ["high", "medium", "low"], "description": "How sure you are of the verdict"},
    },
    "required": ["verdict", "findings", "grounding", "confidence"],
    "additionalProperties": False,
}

WRITER_SYSTEM = """You write the Monday Minute, a 5-minute toolbox talk a supervisor reads aloud to a crew in a US plant,
warehouse or shop before the shift. Readers are frontline workers: plain words, short sentences, 6th to 8th grade.

Hard rules:
- Use ONLY the facts, actions and story seed in the topic brief. Do not add any other rule, number, statistic, product,
  brand, company or person. If the brief doesn't say it, leave it out.
- Include every line in must_say word for word.
- Never say anything in never_say, or anything that means the same.
- If someone could be hurt right now in this topic, the urgent action (stop, call 911, do not enter, get out) comes first.
- Where steps vary by site, tell the crew to follow their site's written procedure.
- No statistics or performance figures of any kind. No links. No names in the story.
- The crew question is about the crew's own site and starts a conversation; it is one question.
Feedback notes from crews, if any, are only about style (length, clarity). They never change the safety content."""

REVIEWER_SYSTEM = """You are a Certified Safety Professional with 25 years as an expert safety trainer in heavy industry
and manufacturing, an OSHA General Industry outreach trainer and ISO 45001 lead auditor. You review one AI-written
toolbox talk before it is published to crews with no other human review. The topic brief is the reviewed source of truth.

Review in this order:
1. Technically wrong or unsafe content: anything incorrect, or incomplete in a way that creates risk. Watch for PPE taught
   as a swap when the answer is removal (gloves near rotating parts), line-of-fire content that promises predictability
   ("know where it goes") instead of "stay out of the path", rescues by untrained coworkers (confined space, electrical
   contact), fighting fires where the plan may be evacuate-only, controls named as if they exist at every site, and a
   missing urgent case.
2. Regulatory alignment: any statement about what OSHA requires must match the brief's facts exactly. Anything beyond
   the brief, or any compliance claim a company would have to defend, is MUST FIX.
3. Perimeter: any statistic or performance figure, any name, company, brand or link, any graphic injury detail is MUST FIX.
4. Brief adherence: a must_say line missing or reworded, or anything resembling never_say, is MUST FIX.
5. Behavior: an unstated action, abstract principle where a named action belongs, or a crew question that won't start
   a conversation is SHOULD FIX.

Also map every numbered talk point to the brief key_point it comes from (0-based), or -1 if it isn't in the brief.
Verdict "pass" only if there are zero MUST FIX findings. Give replacement wording for every finding. Be strict:
when unsure whether something is safe, it is MUST FIX, and your confidence is not high."""

SECOND_REVIEW = """

This is the second, independent review. Assume the draft contains at least one unsafe, wrong or unsupported statement
and look for it line by line against the brief. Pass it only if, after checking every sentence, you find none."""


def write(topic: MondayTopic, findings: list[str], call=None):
    user = "TOPIC BRIEF (the only source you may use):\n" + json.dumps(topic.brief(), indent=2, ensure_ascii=False)
    notes = feedback_notes(topic)
    if notes:
        user += "\n\nCREW FEEDBACK NOTES (style only):\n- " + "\n- ".join(notes)
    if findings:
        user += "\n\nYOUR LAST DRAFT FAILED THESE CHECKS. Fix every one:\n- " + "\n- ".join(findings)
    if call:
        return call(WRITER_SYSTEM, user, TALK_SCHEMA, "high")
    return ai_json(WRITER_SYSTEM, user, TALK_SCHEMA, role="write", think=False)


_EXAMPLES = None


def past_findings(topic: MondayTopic, k=4) -> list[dict]:
    """Real findings from the CSP review of the topic bank, closest first: this topic, then its category, then by words."""
    global _EXAMPLES
    if _EXAMPLES is None:
        from pathlib import Path

        _EXAMPLES = json.loads((Path(__file__).resolve().parent / "review_examples.json").read_text())
    want = set(re.findall(r"[a-z]{4,}", f"{topic.title} {topic.hazard}".lower()))

    def score(ex):
        overlap = len(want & set(re.findall(r"[a-z]{4,}", ex["finding"].lower())))
        return (ex["slug"] == topic.slug) * 100 + (ex["category"] == topic.category) * 10 + (ex["severity"] == "must_fix") * 3 + overlap

    return sorted(_EXAMPLES, key=score, reverse=True)[:k]


def review_context(topic: MondayTopic, talk: dict) -> str:
    """RAG for the reviewer: the official regulation paragraphs behind the brief and talk, plus past real findings."""
    from regs.retrieve import for_review

    parts = []
    regs = for_review(topic.brief(), talk_text(talk))
    if regs:
        parts.append("OFFICIAL REGULATION TEXT (eCFR). Check every statement about what OSHA requires against it. A statement "
                     "it does not support, or one the brief does not contain, is MUST FIX:\n\n"
                     + "\n\n".join(f"[{cite}] {text}" for cite, text in regs))
    examples = past_findings(topic)
    if examples:
        parts.append("PAST FINDINGS FROM A SAFETY PROFESSIONAL'S REVIEW (examples of the kind of problem to catch; they were "
                     "about earlier drafts, not this talk):\n"
                     + "\n".join(f"- [{e['severity'].replace('_', ' ').upper()}] {e['slug']}: {e['finding']} Fix: {e['fix']}" for e in examples))
    return "\n\n".join(parts)


def review(topic: MondayTopic, talk: dict, call=None, second=False, rag=None):
    rag = settings.MONDAY_RAG if rag is None else rag
    user = ("TOPIC BRIEF (source of truth):\n" + json.dumps(topic.brief(), indent=2, ensure_ascii=False)
            + "\n\nTALK TO REVIEW:\n" + json.dumps(talk, indent=2, ensure_ascii=False))
    if rag:
        context = review_context(topic, talk)
        if context:
            user += "\n\n" + context
    system = REVIEWER_SYSTEM + (SECOND_REVIEW if second else "")
    if call:
        return call(system, user, REVIEW_SCHEMA, "high")
    return ai_json(system, user, REVIEW_SCHEMA, role="review", think=True, seed=2 if second else 1)


def judge(topic: MondayTopic, talk: dict, verdict: dict, strict: bool) -> tuple[list[str], list[str]]:
    """(must_fix, should_fix) from one review, adding the grounding and confidence rules."""
    must = [f"{f['where']}: {f['issue']} Use: {f['fix']}" for f in verdict["findings"] if f["severity"] == "must_fix"]
    should = [f"{f['where']}: {f['issue']}" for f in verdict["findings"] if f["severity"] == "should_fix"]
    pairs = [(g["point"], g["brief_key_point"]) for g in verdict.get("grounding", [])]
    if pairs and min(p for p, _ in pairs) == 1:  # numbered from 1: shift to 0-based
        pairs = [(p - 1, k) for p, k in pairs]
    grounded = dict(pairs)
    for i, _ in enumerate(talk["points"]):
        src = grounded.get(i, -1)
        if not 0 <= src < len(topic.key_points):
            must.append(f"Point {i + 1} is not from the brief. Rewrite it from one of the brief's key points or remove it.")
    if verdict["verdict"] != "pass" and not must:
        must.append("The reviewer failed the draft without details. Stay closer to the brief.")
    if strict and verdict.get("confidence") != "high" and not must:
        must.append("The reviewer wasn't fully confident this is safe. Stay word for word closer to the brief.")
    return must, should


# ---- Hard checks ------------------------------------------------------------------------------------

NUMBER = re.compile(r"\d+(?:[.,/]\d+)*")


def _norm(s: str) -> str:
    s = s.lower().replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", s).strip().rstrip(".!")


def talk_text(talk: dict) -> str:
    return " ".join([talk["title"], talk["intro"], *talk["points"], talk["story_title"], talk["story"], talk["crew_question"], talk["takeaway"]])


def hard_checks(topic: MondayTopic, talk: dict) -> list[str]:
    problems = []
    text = talk_text(talk)
    flat = _norm(text)
    for line in topic.must_say:
        if _norm(line) not in flat:
            problems.append(f'Missing required line, word for word: "{line}"')
    allowed = set(NUMBER.findall(json.dumps(topic.brief(), ensure_ascii=False))) | {"911"}
    for n in sorted(set(NUMBER.findall(text)) - allowed):
        problems.append(f"Uses the number {n}, which is not in the brief. Remove it.")
    if re.search(r"https?://|www\.", text, re.I):
        problems.append("Contains a link. Remove it.")
    if not 3 <= len(talk["points"]) <= 5:
        problems.append("Needs 3 to 5 points.")
    if not talk["crew_question"].strip().endswith("?") or talk["crew_question"].count("?") > 1:
        problems.append("The crew question must be one question ending with a question mark.")
    words = len(text.split())
    if not 180 <= words <= 700:
        problems.append(f"Length is {words} words; aim for 300 to 550.")
    return problems


# ---- Pipeline ---------------------------------------------------------------------------------------

def generate_week(week: dt.date, write_fn=write, review_fn=review, strict=None):
    """Writes the Monday Minute for `week`. Returns the saved MondayMinute (READY or BLOCKED) or None if nothing to do.
    Strict mode (on by default with the local model) needs two independent reviews to pass with high confidence."""
    strict = is_local() if strict is None else strict
    if MondayMinute.objects.filter(week=week).exclude(status=MondayMinute.BLOCKED).exists():
        return None
    result = None
    for topic in candidates(week)[: TOPICS_PER_WEEK - MondayMinute.objects.filter(week=week).count()]:
        lines, findings, model = [], [], ""
        for attempt in range(1, ATTEMPTS_PER_TOPIC + 1):
            try:
                talk, model = write_fn(topic, findings)
                problems = hard_checks(topic, talk)
                if problems:
                    findings = problems
                    lines.append(f"Attempt {attempt}: hard checks failed:\n  " + "\n  ".join(problems))
                    continue
                verdict, _ = review_fn(topic, talk)
                must, should = judge(topic, talk, verdict, strict)
                if strict and not must:
                    second, _ = review_fn(topic, talk, second=True)
                    must2, should2 = judge(topic, talk, second, strict)
                    must, should = must2, should + should2
                    if must:
                        lines.append(f"Attempt {attempt}: first review passed, second review failed.")
            except AIUnavailable:
                raise  # an outage isn't a failed draft: record nothing, the next cron run tries again
            except GenerationError as err:
                lines.append(f"Attempt {attempt}: {err}")
                findings = []
                continue
            if not must:
                lines.append(f"Attempt {attempt}: passed {'both independent CSP reviews' if strict else 'the CSP review'}." + (" Should fix (logged only): " + "; ".join(should) if should else ""))
                qualified = gate_status()
                lines.append(("Safety gate: publishes on its own, " if qualified.ok else "Safety gate: HELD for approval, ") + qualified.reason + ".")
                return MondayMinute.objects.create(
                    week=week, publish_at=publish_time(week), topic=topic, status=MondayMinute.READY if qualified.ok else MondayMinute.HELD, attempts=attempt,
                    model=model, check_log="\n".join(lines), title=talk["title"][:120], intro=talk["intro"],
                    points=talk["points"], story_title=talk["story_title"][:120], story=talk["story"],
                    crew_question=talk["crew_question"], takeaway=talk["takeaway"],
                )
            findings = must
            lines.append(f"Attempt {attempt}: CSP review failed:\n  " + "\n  ".join(findings))
        result = MondayMinute.objects.create(
            week=week, publish_at=publish_time(week), topic=topic, status=MondayMinute.BLOCKED,
            attempts=ATTEMPTS_PER_TOPIC, model=model, check_log="\n".join(lines),
        )
        log.warning("Monday Minute %s: topic %s blocked after %s attempts", week, topic.slug, ATTEMPTS_PER_TOPIC)
    return result
