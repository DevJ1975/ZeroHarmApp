"""Pulls a year of Zero Harm Weekly issues out of GoHighLevel and schedules them in the app."""
import datetime as dt
from zoneinfo import ZoneInfo

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from . import ghl
from .models import ToolboxTalk
from .talk_parse import parse_issue, parse_name

PACIFIC = ZoneInfo("America/Los_Angeles")


def send_time(issue_date):
    """Sunday 11:59 AM Pacific, the day before the Monday issue date (daylight saving handled)."""
    sunday = issue_date - dt.timedelta(days=1)
    return dt.datetime.combine(sunday, dt.time(11, 59), PACIFIC).astimezone(dt.timezone.utc)


def sync_year(year, fetch_html=ghl.fetch_text, templates=None):
    """Creates or updates every issue dated in `year`. Returns a list of log lines.

    Matching is by issue date, so a new year never overwrites an old one. Text edits made in
    GHL carry over; a talk whose push already went out keeps its push record and is never re-sent.
    Any issue whose app-facing text still holds a [bracketed] pre-send flag is held for review.
    """
    if templates is None:
        if not ghl.configured():
            return ["GoHighLevel is not configured (GHL_PRIVATE_TOKEN / GHL_LOCATION_ID)."]
        templates = ghl.list_templates("Zero Harm Weekly")
    picked = {}
    for t in templates:
        parsed = parse_name(t.get("name", ""))
        if parsed and parsed[2].year == year:
            number, title, issue_date = parsed
            prev = picked.get(issue_date)
            if not prev or (t.get("updatedAt", "") > prev[0].get("updatedAt", "")):
                picked[issue_date] = (t, number, title)
    log = [f"Found {len(picked)} issue(s) dated {year}."]
    if not picked:
        return log
    for issue_date in sorted(picked):
        t, number, title = picked[issue_date]
        if issue_date.weekday() != 0:
            log.append(f"#{number:02d} skipped: {issue_date} is not a Monday. Fix the date in the template name.")
            continue
        try:
            parts = parse_issue(fetch_html(t["previewUrl"]), title)
        except Exception as err:  # network or template problem: skip this one, keep going
            log.append(f"#{number:02d} skipped: could not read the template ({err}).")
            continue
        with transaction.atomic():
            talk = ToolboxTalk.objects.select_for_update().filter(issue_date=issue_date).first()
            if talk is None:
                next_id = (ToolboxTalk.objects.aggregate(m=Max("issue"))["m"] or 0) + 1
                talk = ToolboxTalk(issue=next_id, issue_date=issue_date)
            talk.number = number
            talk.title = title
            talk.send_at = send_time(issue_date)
            talk.ghl_template_id = t.get("id", "")[:40]
            talk.story_title = parts["story_title"] or talk.story_title or ""
            talk.crew_question = parts["crew_question"] or talk.crew_question or ""
            talk.month_theme = parts["month_theme"] or talk.month_theme or ""
            talk.body_md = parts["body_md"]
            talk.pdf_url = parts["pdf_url"] or talk.pdf_url
            talk.hero_url = parts["hero_url"] or talk.hero_url
            talk.review_flags = "\n".join(parts["flags"])
            talk.needs_review = bool(parts["flags"])
            if talk.needs_review and talk.spanish_status == ToolboxTalk.ES_APPROVED:
                talk.spanish_status = ToolboxTalk.ES_DRAFT  # English changed, so Spanish needs another look
            talk.ghl_synced_at = timezone.now()
            talk.save()
        state = "HELD for review: " + "; ".join(parts["flags"]) if talk.needs_review else "ready"
        log.append(f"#{number:02d} {issue_date:%b %d} {title}: {state}")
    return log
