"""Writes, checks and schedules the weekly Monday Minute. Runs from `python manage.py monday_minute` (the cron service).

Safety design, because no person approves each talk:
1. The writer sees ONE topic brief from the CSP-reviewed topic bank and may use nothing else.
2. Hard checks run on every draft: required lines present word for word, no number that isn't in the brief, no links,
   one crew question, sane length.
3. A second Claude call reviews the draft as a Certified Safety Professional against the brief. Any MUST FIX finding
   fails the draft. The writer gets the findings and tries again, up to 3 times per topic, 2 topics per week.
4. If nothing passes, that week has no Monday Minute (the app keeps showing last week's). Nothing unchecked publishes.
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

from .models import MondayFeedback, MondayMinute, MondayTopic

log = logging.getLogger(__name__)
PACIFIC = ZoneInfo("America/Los_Angeles")
PUBLISH_TIME = dt.time(5, 0)
WRITE_DAYS_AHEAD = 5          # start writing Wednesday for the next Monday
ATTEMPTS_PER_TOPIC = 3
TOPICS_PER_WEEK = 2
NO_REPEAT_WEEKS = 104


class GenerationError(Exception):
    pass


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
    },
    "required": ["verdict", "findings"],
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

Verdict "pass" only if there are zero MUST FIX findings. Give replacement wording for every finding. Be strict:
when unsure whether something is safe, it is MUST FIX."""


def _client():
    import anthropic

    return anthropic.Anthropic(timeout=180.0, max_retries=3)


def claude_json(system: str, user: str, schema: dict, effort: str = "high"):
    """One structured-output call. Returns (data, model). Refusals and truncation raise GenerationError."""
    import anthropic

    client = _client()
    kwargs = dict(
        model=settings.MONDAY_MODEL,
        max_tokens=16000,
        system=system,
        messages=[{"role": "user", "content": user}],
        output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
    )
    try:  # server-side fallback re-runs a declined request on another model inside the same call
        res = client.beta.messages.create(betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs)
    except anthropic.BadRequestError:
        res = client.messages.create(**kwargs)
    if res.stop_reason == "refusal":
        raise GenerationError("The model declined this request.")
    if res.stop_reason == "max_tokens":
        raise GenerationError("The response was cut off.")
    text = next((b.text for b in res.content if b.type == "text"), "")
    try:
        return json.loads(text), res.model
    except json.JSONDecodeError as err:
        raise GenerationError(f"Not valid JSON: {err}") from err


def write(topic: MondayTopic, findings: list[str], call=claude_json):
    user = "TOPIC BRIEF (the only source you may use):\n" + json.dumps(topic.brief(), indent=2, ensure_ascii=False)
    notes = feedback_notes(topic)
    if notes:
        user += "\n\nCREW FEEDBACK NOTES (style only):\n- " + "\n- ".join(notes)
    if findings:
        user += "\n\nYOUR LAST DRAFT FAILED THESE CHECKS. Fix every one:\n- " + "\n- ".join(findings)
    return call(WRITER_SYSTEM, user, TALK_SCHEMA, "high")


def review(topic: MondayTopic, talk: dict, call=claude_json):
    user = ("TOPIC BRIEF (source of truth):\n" + json.dumps(topic.brief(), indent=2, ensure_ascii=False)
            + "\n\nTALK TO REVIEW:\n" + json.dumps(talk, indent=2, ensure_ascii=False))
    return call(REVIEWER_SYSTEM, user, REVIEW_SCHEMA, "high")


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

def generate_week(week: dt.date, write_fn=write, review_fn=review):
    """Writes the Monday Minute for `week`. Returns the saved MondayMinute (READY or BLOCKED) or None if nothing to do."""
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
            except GenerationError as err:
                lines.append(f"Attempt {attempt}: {err}")
                findings = []
                continue
            must = [f"{f['where']}: {f['issue']} Use: {f['fix']}" for f in verdict["findings"] if f["severity"] == "must_fix"]
            should = [f"{f['where']}: {f['issue']}" for f in verdict["findings"] if f["severity"] == "should_fix"]
            if verdict["verdict"] == "pass" and not must:
                lines.append(f"Attempt {attempt}: passed the CSP review." + (" Should fix (logged only): " + "; ".join(should) if should else ""))
                return MondayMinute.objects.create(
                    week=week, publish_at=publish_time(week), topic=topic, status=MondayMinute.READY, attempts=attempt,
                    model=model, check_log="\n".join(lines), title=talk["title"][:120], intro=talk["intro"],
                    points=talk["points"], story_title=talk["story_title"][:120], story=talk["story"],
                    crew_question=talk["crew_question"], takeaway=talk["takeaway"],
                )
            findings = must or ["The reviewer failed the draft without details. Stay closer to the brief."]
            lines.append(f"Attempt {attempt}: CSP review failed:\n  " + "\n  ".join(findings))
        result = MondayMinute.objects.create(
            week=week, publish_at=publish_time(week), topic=topic, status=MondayMinute.BLOCKED,
            attempts=ATTEMPTS_PER_TOPIC, model=model, check_log="\n".join(lines),
        )
        log.warning("Monday Minute %s: topic %s blocked after %s attempts", week, topic.slug, ATTEMPTS_PER_TOPIC)
    return result
