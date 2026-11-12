"""What phones send to the support system, on API v2 (/api/v2/support/...).

    POST /report   a person reports a problem (from OTIS or the form), or flags one OTIS answer
    POST /crash    the app reports an error by itself, with no personal data and nothing that links it to a person
    POST /mine     this phone's own reports, with their status and the owner's reply

All three are open to any phone, so each has its own limit per network, every field is cleaned and cut to size, and
a body over 32 KB is turned away before it is read. What is kept and what is never kept is at the top of models.py.
"""
import datetime as dt
import functools
import hashlib
import logging
import re
from typing import Literal

from django.conf import settings
from django.core.cache import caches
from django.db import IntegrityError, transaction
from django.db.models import F
from django.http import HttpRequest, JsonResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from ninja import Router, Schema
from ninja.decorators import decorate_view
from pydantic import Field, field_validator, model_validator

from monday.api import InstallId, _hash  # one rule and one salt for install ids across the whole backend
from zeroharm.net import ScopedThrottle, network_key

from . import alerts
from . import text as clean  # not "text": the report schema has a field of that name
from .models import CrashKey, CrashReport, Ticket

log = logging.getLogger(__name__)
router = Router(tags=["Support"])

MAX_BODY = 32 * 1024     # bytes. The largest honest body (a 6,000 character stack trace, or a 4,000 character report) is well under it.
CRASH_ROWS_KEPT = 50     # crash reports kept per ticket for the detail view; the ticket's count still counts every one
MINE_LIMIT = 30
FLAGGED_ANSWER = "Flagged OTIS answer"  # the text of an answer report when the person added no note of their own
EMAIL_SHAPE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
OLDEST_CRASH = dt.timedelta(days=30)  # a crash time further back than this is a wrong clock on the phone, not news
TRY_LATER = 3600  # seconds, the Retry-After sent with a crash turned away for now; the phone keeps it either way


def crash_hash(install_id):
    """The install id hashed for crash reports only. The same salt as every other install hash, with its own label,
    so a crash report can tell a repeat from a new one but cannot be matched to the sign-up or the problem reports
    from the same phone (those carry _hash(install_id))."""
    return _hash(f"crash:{install_id}")


def small_body(view):
    """Turns a body over MAX_BODY away with a 413 before anything reads it. Django only ever reads as many bytes as
    Content-Length says, so checking that number is the whole check."""
    @functools.wraps(view)
    def checked(request, *args, **kwargs):
        try:
            size = int(request.META.get("CONTENT_LENGTH") or 0)
        except ValueError:
            size = 0
        if size > MAX_BODY:
            return JsonResponse({"error": "That is too large to send."}, status=413)
        return view(request, *args, **kwargs)
    return checked


# ---- What a phone may send ---------------------------------------------------------------------------
# The few things that decide which row this is (the keys, the kind, the person's own text) are checked strictly: a
# wrong one is a 422 and nothing is saved. The details around them (phone model, version, screen) are cleaned and
# cut to size but never a reason to refuse: a report must not be lost because a phone model has a long name.

def _cut(limit, tidy=clean.line):
    return lambda value: tidy(value, limit)


def _key(value):
    """A phone-made key with anything invisible taken out, so it can always be saved and looked up again."""
    return clean.line(value).replace(" ", "") if isinstance(value, str) else value


def _yes_or_no(value):
    return False if value is None else value


class DeviceFields(Schema):
    """What the phone is, sent with a report and with a crash. Never a name, a place or an id of the device."""
    app_version: str = ""
    platform: Literal["ios", "android", ""] = ""
    os_version: str = ""
    device: str = Field(default="", description="Phone model, like Pixel 8")
    screen: str = Field(default="", description="The route it happened on, like /talk/12")

    _versions = field_validator("app_version", "os_version", mode="before")(_cut(20))
    _device = field_validator("device", mode="before")(_cut(60))
    _screen = field_validator("screen", mode="before")(clean.route)
    _platform = field_validator("platform", mode="before")(lambda v: "" if v is None else v)


class ReportIn(DeviceFields):
    client_key: str = Field(min_length=8, max_length=64, description="Made by the phone; the same key again returns the same ticket")
    install_id: str = InstallId
    source: Literal["otis", "form", "otis_answer"]
    text: str = Field(default="", max_length=4000, description="What the person wrote: 5 characters or more, or for otis_answer an optional note")
    email: str = ""
    name: str = ""
    may_contact: bool = False
    lang: Literal["en", "es", ""] = ""
    question: str = Field(default="", description="otis_answer only: the question the person asked OTIS")
    answer: str = Field(default="", description="otis_answer only: what OTIS answered")
    model_key: str = Field(default="", description="otis_answer only: which model wrote the answer")

    _tidy_key = field_validator("client_key", mode="before")(_key)
    _tidy_text = field_validator("text", mode="before")(clean.block)
    _tidy_email = field_validator("email", mode="before")(_cut(254))
    _tidy_name = field_validator("name", mode="before")(_cut(120))
    _tidy_question = field_validator("question", mode="before")(_cut(500, clean.block))
    _tidy_answer = field_validator("answer", mode="before")(_cut(2000, clean.block))
    _tidy_model = field_validator("model_key", mode="before")(_cut(60))
    _tidy_flag = field_validator("may_contact", mode="before")(_yes_or_no)
    _tidy_lang = field_validator("lang", mode="before")(lambda v: "" if v is None else v)

    @model_validator(mode="after")
    def _enough_to_go_on(self):
        if self.source == "otis_answer":
            self.text = self.text or FLAGGED_ANSWER
        elif len(self.text) < 5:
            raise ValueError("Say what happened in a few words (at least 5 characters).")
        return self


class ReportOut(Schema):
    number: str
    status: str


class CrashIn(DeviceFields):
    client_key: str = Field(min_length=8, max_length=64, description="Made by the phone; the same key again changes nothing")
    install_id: str = InstallId
    name: str = Field(description="The error's name, like TypeError")
    message: str = ""
    stack: str = ""
    fatal: bool = False
    at: dt.datetime | None = Field(default=None, description="When it happened, ISO date-time")

    _tidy_key = field_validator("client_key", mode="before")(_key)
    _tidy_name = field_validator("name", mode="before")(lambda v: clean.line(clean.scrub(clean.line(v)), 120))
    _tidy_message = field_validator("message", mode="before")(lambda v: clean.line(clean.scrub(clean.line(v)), 500))
    _tidy_stack = field_validator("stack", mode="before")(lambda v: clean.block(clean.scrub(clean.block(v)), 6000))
    _tidy_flag = field_validator("fatal", mode="before")(_yes_or_no)

    @field_validator("at", mode="before")
    @classmethod
    def _a_time_or_nothing(cls, value):
        """A time that cannot be read is left out, not refused: the report matters more than its clock."""
        if not isinstance(value, str):
            return None
        try:
            moment = parse_datetime(value.strip())
        except ValueError:
            return None
        if moment is not None and timezone.is_naive(moment):
            moment = moment.replace(tzinfo=dt.timezone.utc)
        return moment


class CrashOut(Schema):
    ok: bool
    number: str


class MineIn(Schema):
    install_id: str = InstallId


class MineTicket(Schema):
    number: str
    status: str
    title: str
    created_at: str
    updated_at: str
    reply: str


class MineOut(Schema):
    tickets: list[MineTicket]


def _device(body):
    return {"app_version": body.app_version, "platform": body.platform, "os_version": body.os_version,
            "device": body.device, "screen": body.screen}


# ---- A person reports a problem, or flags an OTIS answer ---------------------------------------------

# Why these limits: a person files a report by hand, so a whole site on one Wi-Fi has no reason to send more than a
# few an hour; 30 leaves room and caps what a script can add. Each endpoint counts by itself (its own scope), per
# network, and no readable address is kept in the count (zeroharm/net.py).
@router.post("/report", response=ReportOut, throttle=[ScopedThrottle("30/h", scope="support-report")],
             summary="A person reports a problem with the app, or flags one OTIS answer")
@decorate_view(small_body)
def report(request: HttpRequest, body: ReportIn):
    """Sent when a person taps Send on a problem report, or confirms "Report this answer". It carries only what
    they were shown and agreed to send."""
    if not settings.SUPPORT_ENABLED:
        return {"number": "", "status": "off"}  # switched off on the server: answer kindly, keep nothing
    install_hash = _hash(body.install_id)
    same = {"install_hash": install_hash, "client_key": body.client_key}
    ticket = Ticket.objects.filter(**same).first()
    if ticket:
        return {"number": ticket.number, "status": ticket.status}  # the phone sent it again: nothing new is made
    flagged = body.source == "otis_answer"
    # An address that could never work is dropped, not refused: the report still matters, and nobody can be
    # written to at an address like that anyway.
    email = body.email if EMAIL_SHAPE.fullmatch(body.email) else ""
    fields = {
        "kind": Ticket.ANSWER if flagged else Ticket.PROBLEM, "source": body.source,
        "title": clean.first_line(body.text) or FLAGGED_ANSWER, "text": body.text, "lang": body.lang,
        "name": body.name, "email": email, "may_contact": bool(body.may_contact and email),
        # The question and answer are kept only for a flagged answer. A problem report never carries the chat,
        # whatever a phone puts in these fields.
        "question": body.question if flagged else "", "answer": body.answer if flagged else "",
        "model_key": body.model_key if flagged else "", **_device(body),
    }
    try:
        with transaction.atomic():
            ticket = Ticket.objects.create(**same, **fields)
    except IntegrityError:  # the same report arrived twice at the same moment: the other one made the ticket
        ticket = Ticket.objects.get(**same)
        return {"number": ticket.number, "status": ticket.status}
    # The owner hears about it now if GoHighLevel answers within a few seconds. If not, the cron sends it; the
    # phone gets its answer either way.
    alerts.alert_ticket(ticket, timeout=alerts.QUICK)
    return {"number": ticket.number, "status": ticket.status}


# ---- The app reports a crash by itself ----------------------------------------------------------------

def _trim_crash_rows(ticket_id):
    """Keeps the newest CRASH_ROWS_KEPT reports of one ticket. A crash loop on thousands of phones must not fill
    the table; the count on the ticket is what says how often it happens."""
    extra = list(CrashReport.objects.filter(ticket_id=ticket_id).order_by("-pk").values_list("pk", flat=True)[CRASH_ROWS_KEPT:CRASH_ROWS_KEPT + 200])
    if extra:
        CrashReport.objects.filter(pk__in=extra).delete()


# 60 an hour per network: a phone sends each different error once and at most 20 from its queue, so a site's Wi-Fi
# stays under this unless something is looping, and a loop is exactly what should be cut short.
@router.post("/crash", response=CrashOut, throttle=[ScopedThrottle("60/h", scope="support-crash")],
             summary="An automatic crash report. No personal data.")
@decorate_view(small_body)
def crash(request: HttpRequest, body: CrashIn):
    """Sent by the app when its code hits an error, only while the person has "Crash reports" switched on. The same
    crash on the same app version and platform is counted on one ticket. Nobody is emailed from here: the cron
    tells the owner about new and growing crashes in one email."""
    if not settings.SUPPORT_ENABLED:
        return {"ok": True, "number": ""}
    install_hash = crash_hash(body.install_id)
    same = {"install_hash": install_hash, "client_key": body.client_key}
    seen = _counted(same)
    if seen:
        return {"ok": True, "number": seen.number}  # the phone sent it again: it is counted once
    now = timezone.now()
    name = body.name or "Error"
    happened = body.at if body.at and now - OLDEST_CRASH <= body.at <= now else now
    title = f"{name}: {body.message}" if body.message else name
    fingerprint = clean.fingerprint(name, body.message, body.app_version, body.platform)
    ticket, created = Ticket.objects.filter(fingerprint=fingerprint).first(), False
    if ticket is None:
        turned_away = _new_crash_turned_away(request, now)
        if turned_away:
            return turned_away
    try:
        with transaction.atomic():
            if ticket is None:  # get_or_create: two phones may report a brand-new crash at the same moment
                # No install hash on the ticket: it stands for every phone that has the crash. The first report's
                # phone model, system and screen are kept on it until support_prune clears them with the reports.
                ticket, created = Ticket.objects.get_or_create(
                    fingerprint=fingerprint,
                    defaults={"kind": Ticket.CRASH, "source": Ticket.FROM_CRASH, "title": title[:120], "text": body.message or name,
                              "install_hash": "", "first_seen": now, "last_seen": now, **_device(body)})
            CrashKey.objects.create(ticket=ticket, **same)
            CrashReport.objects.create(ticket=ticket, created_at=happened, fatal=body.fatal, name=name, message=body.message,
                                       stack=body.stack, **same, **_device(body))
            if not created:
                # Counted in the database, so reports landing together all count.
                Ticket.objects.filter(pk=ticket.pk).update(count=F("count") + 1, last_seen=now)
                if ticket.status == Ticket.CLOSED:
                    # The crash came back: the ticket opens again as new, and the owner is told again.
                    Ticket.objects.filter(pk=ticket.pk, status=Ticket.CLOSED).update(status=Ticket.NEW, closed_at=None, alerted_count=0, updated_at=now)
    except IntegrityError:  # the same report arrived twice at the same moment: the other one is the one counted
        seen = _counted(same)
        if not seen:
            raise
        return {"ok": True, "number": seen.number}
    if created:
        _count_new_crash(request, now)
    else:
        _trim_crash_rows(ticket.pk)
    return {"ok": True, "number": ticket.number}


def _counted(same):
    """The ticket a crash report was already counted on, or None. CrashKey remembers it for a week even after the
    report row itself was trimmed; the row is looked at too, for a report older than that."""
    key = CrashKey.objects.filter(**same).select_related("ticket").first()
    if key:
        return key.ticket
    row = CrashReport.objects.filter(**same).select_related("ticket").first()
    return row.ticket if row else None


def _network_budget_key(request, now):
    network = hashlib.sha256(f"{settings.SECRET_KEY}:support-new-crash:{network_key(request)}".encode()).hexdigest()[:32]
    return f"support-new-crashes:{now:%Y%m%d}:{network}"


def _new_crash_turned_away(request, now):
    """A 429 or 503 answer when a crash of a new kind cannot be saved now, or None when it can. An app has a few dozen
    different crashes at most, so hundreds of new kinds in a day is somebody making them up, and each would be a
    ticket and a line in the owner's email. Two limits: each network may add NEW_CRASHES_PER_NETWORK new kinds a day,
    so one caller cannot use up the room everyone shares, and all networks together NEW_CRASHES_PER_DAY in 24 hours.
    Crashes already known are always counted. The answer is never a 200: the phone keeps a report it was not given a
    200 for and sends it again later, so a real crash waits instead of being lost. The cron tells the owner, once a
    day, while either limit is turning reports away (alerts.send_crash_limit_notice)."""
    limits = caches["limits"]
    if limits.get(_network_budget_key(request, now), 0) >= alerts.NEW_CRASHES_PER_NETWORK:
        caches["shared"].add(alerts.network_limit_key(now), 1, 2 * 24 * 3600)
        answer = JsonResponse({"error": "Too many new kinds of error from this network today. Try again tomorrow."}, status=429)
    elif alerts.new_crashes_today(now) >= alerts.NEW_CRASHES_PER_DAY:
        answer = JsonResponse({"error": "New error reports are not being taken just now. Try again later."}, status=503)
    else:
        return None
    answer["Retry-After"] = str(TRY_LATER)
    return answer


def _count_new_crash(request, now):
    limits, key = caches["limits"], _network_budget_key(request, now)
    limits.add(key, 0, 2 * 24 * 3600)
    try:
        limits.incr(key)
    except ValueError:  # the count ran out between the two lines: this is the first of the day
        limits.set(key, 1, 2 * 24 * 3600)


# ---- This phone's own reports -------------------------------------------------------------------------

# A POST, not a GET, so the install id travels in the body and never shows in an address or a log line.
@router.post("/mine", response=MineOut, throttle=[ScopedThrottle("60/h", scope="support-mine")],
             summary="This phone's reports with their status and the owner's reply")
@decorate_view(small_body)
def mine(request: HttpRequest, body: MineIn):
    """Sent when a person opens "My reports". Only that phone's problem reports: an answer they flagged is not a
    conversation with the owner, and a crash ticket belongs to every phone that had the crash. The owner's private
    note is never part of the answer."""
    if not settings.SUPPORT_ENABLED:
        return {"tickets": []}
    rows = Ticket.objects.filter(install_hash=_hash(body.install_id), kind=Ticket.PROBLEM).order_by("-created_at", "-pk")[:MINE_LIMIT]
    return {"tickets": [{"number": t.number, "status": t.status, "title": t.title, "created_at": t.created_at.isoformat(),
                         "updated_at": t.updated_at.isoformat(), "reply": t.reply} for t in rows]}
