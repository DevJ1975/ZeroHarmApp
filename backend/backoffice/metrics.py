"""Numbers for the back-office dashboard. Everything comes from what the server already stores. The only thing the app
reports about itself is the anonymous once-a-day usage count (usage/), which people can switch off."""
import datetime as dt
from collections import Counter, defaultdict

from django.conf import settings

from django.db.models import Count, Q, Sum
from django.utils import timezone

from monday.gate import status as gate_status
from monday.models import MondayComment, MondayFeedback, MondayMinute, MondayTopic
from regs.models import RegChange
from talks.models import AppSignup, KbEntry, OtisFeedback, SigninSheet, TalkSuggestion, ToolboxTalk
from usage import geo
from usage.models import AppOpen

WEEKS = 12
TOP_PLACES = 10
# Names for the countries most likely to show up. Any other country is shown by its two-letter code.
COUNTRIES = {"US": "United States", "CA": "Canada", "MX": "Mexico", "PR": "Puerto Rico", "GB": "United Kingdom", "IE": "Ireland",
             "AU": "Australia", "NZ": "New Zealand", "DE": "Germany", "FR": "France", "ES": "Spain", "IN": "India", "PH": "Philippines",
             "BR": "Brazil", "CO": "Colombia"}


def _monday(d: dt.date) -> dt.date:
    return d - dt.timedelta(days=d.weekday())


def _pct(part, whole):
    return round(100 * part / whole) if whole else None


def weekly(rows, value=lambda r: 1, weeks=WEEKS, today=None):
    """[(week start, total)] for the last `weeks` weeks, oldest first, with empty weeks as 0."""
    this_week = _monday(today or timezone.localdate())
    totals = defaultdict(int)
    for day, row in rows:
        totals[_monday(day)] += value(row)
    return [(this_week - dt.timedelta(weeks=i), totals[this_week - dt.timedelta(weeks=i)]) for i in range(weeks - 1, -1, -1)]


def bars(series, width=640, height=180, pad=24):
    """Bar geometry for an inline SVG chart: thin bars, rounded tops, square at the baseline."""
    peak = max((v for _, v in series), default=0) or 1
    slot = (width - 2 * pad) / max(1, len(series))
    bar_w = min(28, slot - 6)
    out = []
    for i, (week, value) in enumerate(series):
        h = round((height - 2 * pad) * value / peak, 1)
        x = round(pad + i * slot + (slot - bar_w) / 2, 1)
        y = height - pad - h
        r = min(4, h / 2)
        path = f"M{x},{height - pad} V{y + r} Q{x},{y} {x + r},{y} H{x + bar_w - r} Q{x + bar_w},{y} {x + bar_w},{y + r} V{height - pad} Z" if h else ""
        out.append({"week": week, "value": value, "path": path, "cx": round(x + bar_w / 2, 1), "y": y,
                    "label": value == peak and value > 0 or (i == len(series) - 1 and value > 0), "tick": i % 2 == (len(series) - 1) % 2})
    return {"bars": out, "width": width, "height": height, "baseline": height - pad, "pad": pad, "peak": peak}


def _top(counts, row, top=TOP_PLACES):
    """Table rows for the busiest places, then "All other places" and "Unknown" so every phone is in the table once."""
    unknown = counts.pop(None, 0)
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    rows = [{**row(key), "phones": n} for key, n in ranked[:top]]
    other = sum(n for _, n in ranked[top:])
    if other:
        rows.append({"name": "All other places", "within": "", "phones": other})
    if unknown:
        rows.append({"name": "Unknown", "within": "", "phones": unknown})
    return rows


def usage(days=30, today=None):
    """Where the app is used: distinct phones in the last 7 and the last `days` days, by platform and by place.

    A phone counts once however many days it opened the app. If it was seen in several places, it counts in the most
    recent place that is known.
    """
    today = today or timezone.localdate()
    since, week = today - dt.timedelta(days=days - 1), today - dt.timedelta(days=6)
    phones = {}  # install hash -> [platform, last day seen, (country, region, city), where that place came from]
    rows = (AppOpen.objects.filter(day__gte=since, day__lte=today).order_by("day", "id")
            .values_list("install_hash", "day", "platform", "country", "region", "city", "source"))
    for install, day, platform, country, region, city, source in rows.iterator(chunk_size=5000):
        phone = phones.setdefault(install, [platform, day, ("", "", ""), ""])
        phone[0], phone[1] = platform, day  # rows arrive oldest first, so the newest wins
        if country or region or city:
            phone[2], phone[3] = (country, region, city), source

    countries, regions, cities, platforms, sources = Counter(), Counter(), Counter(), Counter(), Counter()
    for platform, _, (country, region, city), source in phones.values():
        platforms[platform] += 1
        sources[source] += 1
        countries[country or None] += 1
        regions[(region, country) if region else None] += 1
        cities[(city, region, country) if city else None] += 1

    def country_name(code):
        return COUNTRIES.get(code, code)

    return {
        "enabled": settings.USAGE_ENABLED,
        "days": days,
        "phones": len(phones),
        "phones_week": sum(1 for p in phones.values() if p[1] >= week) if days >= 7 else len(phones),
        "ios": platforms["ios"], "android": platforms["android"],
        "from_phone": sources[AppOpen.PHONE], "from_network": sources[AppOpen.NETWORK], "unknown": sources[""],
        "countries": _top(countries, lambda c: {"name": country_name(c), "within": ""}),
        "regions": _top(regions, lambda k: {"name": k[0], "within": country_name(k[1])}),
        "cities": _top(cities, lambda k: {"name": k[0], "within": ", ".join(x for x in (k[1], country_name(k[2])) if x)}),
        "credit": geo.available() or sources[AppOpen.NETWORK] > 0,  # DB-IP's licence (CC BY 4.0) asks for a credit line wherever its data is used
    }


def dashboard(days=30, today=None):
    today = today or timezone.localdate()
    since = today - dt.timedelta(days=days)
    since_dt = timezone.now() - dt.timedelta(days=days)
    chart_from = _monday(today) - dt.timedelta(weeks=WEEKS - 1)

    sheets = SigninSheet.objects.filter(held_on__gte=since)
    sheet_totals = sheets.aggregate(n=Count("id"), people=Sum("attendee_count"), supervisors=Count("supervisor_email", distinct=True))
    by_program = {r["program"]: r["n"] for r in sheets.values("program").annotate(n=Count("id"))}
    chart_rows = list(SigninSheet.objects.filter(held_on__gte=chart_from).values_list("held_on", "attendee_count"))

    votes = MondayFeedback.objects.filter(created_at__gte=since_dt)
    up, down = votes.filter(helpful=True).count(), votes.filter(helpful=False).count()
    otis = OtisFeedback.objects.filter(created_at__gte=since_dt)
    otis_up, otis_all = otis.filter(helpful=True).count(), otis.count()

    minutes = (MondayMinute.objects.exclude(status=MondayMinute.BLOCKED).select_related("topic").with_counts().order_by("-week")[:10])
    top_talks = (sheets.exclude(talk_title="").values("talk_title", "program")
                 .annotate(n=Count("id"), people=Sum("attendee_count")).order_by("-people", "-n")[:8])
    programs = dict(SigninSheet.PROGRAMS)

    attention = []

    def flag(count, text, url, one=None):
        if count:
            attention.append({"count": count, "text": one if count == 1 and one else text, "url": url})

    flag(MondayMinute.objects.filter(status=MondayMinute.HELD).count(), "Monday Minute talks waiting for your approval",
         "/admin/monday/mondayminute/?status__exact=held", one="Monday Minute talk waiting for your approval")
    qualified = gate_status()
    if not qualified.ok:
        attention.append({"count": "", "text": f"Monday Minute can't publish on its own yet: {qualified.reason}. Run the safety test from Monday Minute topics.",
                          "url": "/admin/monday/mondayevalrun/"})
    flag(MondayMinute.objects.filter(status=MondayMinute.PULLED).count(), "Monday Minute talks pulled after crew reports", "/admin/monday/mondayminute/?status__exact=pulled", one="Monday Minute talk pulled after crew reports")
    flag(MondayTopic.objects.filter(active=False).count(), "Monday Minute topics paused", "/admin/monday/mondaytopic/?active__exact=0", one="Monday Minute topic paused")
    flag(MondayMinute.objects.filter(status=MondayMinute.BLOCKED, week__gte=today - dt.timedelta(days=14)).count(),
         "recent Monday Minute drafts blocked by the safety checks", "/admin/monday/mondayminute/?status__exact=blocked")
    flag(RegChange.objects.filter(reviewed=False).count(), "OSHA rule changes waiting for review", "/admin/regs/regchange/?reviewed__exact=0", one="OSHA rule change waiting for review")
    flag(KbEntry.objects.filter(published=False).exclude(paused_reason="").count(), "OTIS answers taken out until re-reviewed", "/admin/talks/kbentry/?published__exact=0", one="OTIS answer taken out until re-reviewed")
    flag(MondayComment.objects.filter(status=MondayComment.PENDING).count(), "comments waiting for a check", "/admin/monday/mondaycomment/?status__exact=pending", one="comment waiting for a check")
    flag(MondayComment.objects.filter(status=MondayComment.HIDDEN, report_count__gt=0).count(), "reported comments hidden", "/admin/monday/mondaycomment/?status__exact=hidden", one="reported comment hidden")
    flag(SigninSheet.objects.filter(status="failed").count(), "sign-in sheets that didn't reach GoHighLevel", "/admin/talks/signinsheet/?status__exact=failed", one="sign-in sheet that didn't reach GoHighLevel")
    flag(ToolboxTalk.objects.filter(needs_review=True).count(), "Zero Harm Weekly talks held for bracketed notes", "/admin/talks/toolboxtalk/?needs_review__exact=1", one="Zero Harm Weekly talk held for bracketed notes")
    flag(TalkSuggestion.objects.filter(status="new").count(), "new talk suggestions", "/admin/talks/talksuggestion/?status__exact=new", one="new talk suggestion")

    return {
        "days": days,
        "tiles": [
            {"label": "Sign-in sheets", "value": sheet_totals["n"] or 0,
             "note": f"{by_program.get('monday-minute', 0)} Monday Minute · {by_program.get('zero-harm-weekly', 0)} Zero Harm Weekly"},
            {"label": "Crew members signed in", "value": sheet_totals["people"] or 0, "note": f"{sheet_totals['supervisors'] or 0} supervisors ran a talk"},
            {"label": "Email sign-ups", "value": AppSignup.objects.filter(created_at__gte=since_dt).count(), "note": f"{AppSignup.objects.count()} in total"},
            {"label": "Monday Minute thumbs up", "value": f"{_pct(up, up + down)}%" if up + down else "–", "note": f"{up} up · {down} down"},
            {"label": "Comments posted", "value": MondayComment.objects.filter(created_at__gte=since_dt, status=MondayComment.VISIBLE).count(), "note": "shown to crews"},
            {"label": "OTIS answers rated helpful", "value": f"{_pct(otis_up, otis_all)}%" if otis_all else "–", "note": f"{otis_all} ratings (opt-in)"},
        ],
        "sheets_chart": bars(weekly(chart_rows, today=today)),
        "people_chart": bars(weekly(chart_rows, value=lambda n: n or 0, today=today)),
        "minutes": [{"week": m.week, "title": m.title or m.topic.title, "up": m._up, "down": m._down, "comments": m._comments,
                     "status": {"ready": "Published", "pulled": "Pulled", "held": "Waiting for approval"}.get(m.status, m.get_status_display()), "pulled": m.status == MondayMinute.PULLED, "id": m.pk} for m in minutes],
        "top_talks": [{"title": t["talk_title"], "program": programs.get(t["program"], t["program"]), "sheets": t["n"], "people": t["people"] or 0} for t in top_talks],
        "attention": attention,
        "usage": usage(days, today=today),
    }
