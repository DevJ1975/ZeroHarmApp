"""Monday Minute endpoints on API v2 (/api/v2/monday-minute/...). Separate from Zero Harm Weekly's /api/talks/."""
import hashlib
import logging
import threading
import unicodedata
from typing import Literal

from django.conf import settings
from django.db import IntegrityError, connection, transaction
from django.db.models import F
from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from ninja import Router, Schema
from pydantic import Field, field_validator

from zeroharm.net import UNKNOWN, ScopedThrottle, network_key

from . import ai, gate, moderation
from .models import (HIDE_AT_COMMENT_REPORTS, PULL_AT_UNSAFE_REPORTS, MondayComment, MondayCommentBan, MondayCommentReport,
                     MondayFeedback, MondayMinute)

log = logging.getLogger(__name__)
router = Router(tags=["Monday Minute"])
InstallId = Field(min_length=16, max_length=64, pattern=r"^[A-Za-z0-9-]+$", description="Random id the app makes once per install")
Reason = Literal["unsafe", "not_my_site", "confusing", "too_long", "too_basic"]
SCREEN_TRIES = 3  # times the AI check may fail on one comment before the comment is hidden for a person to look at


def _hash(install_id: str) -> str:
    return hashlib.sha256(f"{settings.SECRET_KEY}:{install_id}".encode()).hexdigest()


def _author_key(install_hash: str) -> str:
    """Stable per-phone key the app uses to block a commenter. Reveals nothing about the phone."""
    return hashlib.sha256(f"author:{install_hash}".encode()).hexdigest()[:16]


def _text(value):
    """Free text from a phone, made safe to store: control characters (a NUL makes PostgreSQL refuse the whole save,
    which the phone saw as a server error) and broken halves of emoji are dropped, then the ends are trimmed. Line
    breaks and tabs stay. Runs before the length checks, so text made only of spaces counts as empty."""
    if not isinstance(value, str):
        return value
    return "".join(ch for ch in value if ch in "\n\t" or unicodedata.category(ch) not in ("Cc", "Cs")).strip()


def _waiting_on_gate(m: MondayMinute) -> bool:
    return m.gate_pending and not m.approved_by_person


def _released(pk: int) -> MondayMinute:
    minute = get_object_or_404(MondayMinute.objects.due().select_related("topic"), pk=pk)
    if _waiting_on_gate(minute):
        # First request since its publish time: the safety gate has its last word now, then the talk is out or held.
        gate.release_due()
        minute = get_object_or_404(MondayMinute.objects.released().select_related("topic"), pk=pk)
    return minute


# ---- Schemas ----------------------------------------------------------------------------------------

class MinuteOut(Schema):
    id: int
    week: str
    published_at: str
    topic: str
    category: str
    title: str
    intro: str
    points: list[str]
    story_title: str
    story: str
    crew_question: str
    takeaway: str
    references: list[str]
    thumbs_up: int
    thumbs_down: int
    comment_count: int


class MinuteList(Schema):
    minutes: list[MinuteOut]


class FeedbackIn(Schema):
    install_id: str = InstallId
    helpful: bool
    reasons: list[Reason] = Field(default_factory=list, max_length=5)
    note: str = Field(default="", max_length=300)
    platform: Literal["ios", "android", ""] = ""

    _tidy = field_validator("note", mode="before")(_text)


class FeedbackOut(Schema):
    thumbs_up: int
    thumbs_down: int


class CommentOut(Schema):
    id: int
    display_name: str
    body: str
    created_at: str
    author_key: str
    replies: list["CommentOut"] = []


class CommentList(Schema):
    comments: list[CommentOut]
    rules: list[str]


class CommentIn(Schema):
    install_id: str = InstallId
    body: str = Field(min_length=2, max_length=500)
    display_name: str = Field(default="", max_length=40)
    parent_id: int | None = None
    accepted_rules: bool

    _tidy = field_validator("body", "display_name", mode="before")(_text)


class CommentResult(Schema):
    status: Literal["visible", "pending", "rejected"]
    message: str
    comment: CommentOut | None = None


class ReportIn(Schema):
    install_id: str = InstallId
    reason: str = Field(default="", max_length=40)

    _tidy = field_validator("reason", mode="before")(_text)


class Ok(Schema):
    ok: bool


class Error(Schema):
    error: str


def _comment_out(c: MondayComment, replies=None) -> dict:
    return {"id": c.pk, "display_name": c.display_name, "body": c.body, "created_at": c.created_at.isoformat(),
            "author_key": _author_key(c.install_hash), "replies": replies or []}


# ---- Talks and ratings ------------------------------------------------------------------------------

@router.get("", response=MinuteList, summary="Published Monday Minutes, newest first")
def list_minutes(request: HttpRequest):
    def newest():
        return list(MondayMinute.objects.due().select_related("topic").with_counts().order_by("-week")[:30])

    minutes = newest()
    if any(_waiting_on_gate(m) for m in minutes):
        # A talk has reached its publish time since anyone last asked: the safety gate has its last word now.
        gate.release_due()
        minutes = [m for m in newest() if not _waiting_on_gate(m)]
    return {"minutes": [m.as_api() for m in minutes]}


@router.get("/{minute_id}", response=MinuteOut)
def get_minute(request: HttpRequest, minute_id: int):
    return _released(minute_id).as_api()


# Each limit below has its own counter per network (ScopedThrottle). They used to share one counter per address, so
# ten thumbs from a crew on one plant Wi-Fi used up that site's comments for the hour.
@router.post("/{minute_id}/feedback", response=FeedbackOut, summary="Thumbs up or down, one per phone (a new vote replaces the old)",
             throttle=[ScopedThrottle("60/h", scope="monday-feedback")])
def rate(request: HttpRequest, minute_id: int, body: FeedbackIn):
    minute = _released(minute_id)
    MondayFeedback.objects.update_or_create(
        minute=minute, install_hash=_hash(body.install_id),
        defaults={"helpful": body.helpful, "reasons": [] if body.helpful else sorted(set(body.reasons)),
                  "note": "" if body.helpful else body.note.strip(), "platform": body.platform,
                  # network_key, not the bare address: an IPv6 home or phone connection owns a whole /64 and could
                  # otherwise report from three addresses in it and look like three sites.
                  "network_hash": _hash(f"net:{network_key(request)}")},
    )
    # Count networks, not phones: three made-up phone ids from one connection must not be able to pull a talk.
    # A report whose network could not be read is kept, but is not one of the three: nothing tells it apart from
    # a network already counted.
    unknown = _hash(f"net:{UNKNOWN}")
    unsafe = len({net for reasons, net in minute.feedback.filter(helpful=False).values_list("reasons", "network_hash")
                  if "unsafe" in (reasons or []) and net != unknown})
    if unsafe >= PULL_AT_UNSAFE_REPORTS:
        # Fully automatic means crews are the after-the-fact check: pull the talk and stop using its topic.
        MondayMinute.objects.filter(pk=minute.pk).update(status=MondayMinute.PULLED)
        topic = minute.topic
        topic.active = False
        topic.paused_reason = f"Paused: reports from {unsafe} sites that the {minute.week:%b %-d} talk isn't safe or isn't right."
        topic.save(update_fields=["active", "paused_reason", "updated_at"])
        log.warning("Monday Minute %s (%s) was pulled and its topic paused: reports from %s networks that it isn't safe or isn't right",
                    minute.week, topic.slug, unsafe)
    return {"thumbs_up": minute.feedback.filter(helpful=True).count(), "thumbs_down": minute.feedback.filter(helpful=False).count()}


# ---- Comments ---------------------------------------------------------------------------------------

@router.get("/{minute_id}/comments", response=CommentList)
def list_comments(request: HttpRequest, minute_id: int):
    minute = _released(minute_id)
    visible = list(minute.comments.filter(status=MondayComment.VISIBLE).order_by("created_at"))
    by_parent = {}
    for c in visible:
        by_parent.setdefault(c.parent_id, []).append(c)
    top = [_comment_out(c, [_comment_out(r) for r in by_parent.get(c.pk, [])]) for c in by_parent.get(None, [])]
    return {"comments": top, "rules": moderation.COMMUNITY_RULES}


BANNED = "You can no longer comment."


@router.post("/{minute_id}/comments", response={201: CommentResult, 400: Error, 403: Error}, throttle=[ScopedThrottle("10/h", scope="monday-comment")],
             summary="Post a comment or reply. Screened before anyone sees it.")
def post_comment(request: HttpRequest, minute_id: int, body: CommentIn):
    minute = _released(minute_id)
    if not body.accepted_rules:
        return 400, {"error": "Please agree to the community rules first."}
    install_hash = _hash(body.install_id)
    if MondayCommentBan.objects.filter(install_hash=install_hash).exists():
        return 403, {"error": BANNED}
    parent = None
    if body.parent_id:
        parent = minute.comments.filter(pk=body.parent_id, status=MondayComment.VISIBLE, parent__isnull=True).first()
        if not parent:
            return 400, {"error": "That comment isn't available to reply to."}
    name = " ".join(body.display_name.split())[:40] or "Crew member"
    text = body.body  # already trimmed and length-checked by the schema
    reason = moderation.quick_check(text, name)
    if reason:
        return 201, {"status": "rejected", "message": reason}
    comment = MondayComment(minute=minute, parent=parent, display_name=name, body=text, install_hash=install_hash)
    if ai.is_local():
        # A CPU model can take a while: save it as waiting and screen it in the background, so posting never hangs.
        comment.status = MondayComment.PENDING
        comment.save()
        _screen_soon(comment.pk)
        return 201, {"status": "pending", "message": "Thanks! Checking your comment. It will show in a minute."}
    _free_connection()
    try:
        allow, why = moderation.ai_check(text, name, minute.topic.title)
    except Exception:  # review unavailable: hold it, the cron screens it later
        comment.status = MondayComment.PENDING
        comment.save()
        return 201, {"status": "pending", "message": "Thanks! Your comment will show once it's been checked."}
    if not allow:
        return 201, {"status": "rejected", "message": why or "This comment doesn't follow the community rules."}
    comment.status = MondayComment.VISIBLE
    comment.save()
    return 201, {"status": "visible", "message": "Posted.", "comment": _comment_out(comment)}


@router.post("/comments/{comment_id}/report", response=Ok, throttle=[ScopedThrottle("30/h", scope="monday-report")], summary="Report a comment")
def report_comment(request: HttpRequest, comment_id: int, body: ReportIn):
    comment = get_object_or_404(MondayComment, pk=comment_id, status=MondayComment.VISIBLE)
    try:
        with transaction.atomic():
            MondayCommentReport.objects.create(comment=comment, install_hash=_hash(body.install_id), reason=body.reason)
            MondayComment.objects.filter(pk=comment.pk).update(report_count=F("report_count") + 1)
    except IntegrityError:
        return {"ok": True}  # already reported from this phone
    comment.refresh_from_db()
    if comment.report_count >= HIDE_AT_COMMENT_REPORTS:
        comment.status, comment.moderation = MondayComment.HIDDEN, f"Hidden after {comment.report_count} reports. Review in the admin."
        comment.save(update_fields=["status", "moderation"])
    # The owner hears about the first report right away, so the 24-hour promise does not depend on checking the admin.
    # If GoHighLevel is slow or down, the cron sends it (owner_alerts.retry_report_alerts).
    from talks import owner_alerts
    owner_alerts.alert_report(comment, timeout=owner_alerts.QUICK)
    return {"ok": True}


def _free_connection():
    """Hands this thread's database connection back before a slow AI call, so a waiting comment check holds none (a
    busy AI server once meant one open connection per waiting comment, for up to 30 minutes each). The next query
    opens a new one. Inside a transaction the connection has to stay."""
    if not connection.in_atomic_block:
        connection.close()


def _screen(comment_id: int) -> str:
    """Screens one waiting comment. "decided": shown or hidden (or it was no longer waiting). "down": the AI can't be
    reached, it stays waiting. "failed": the AI answered but not usably for this comment; that is counted on the
    comment, and after SCREEN_TRIES it is hidden for a person to look at."""
    c = MondayComment.objects.select_related("minute__topic").filter(pk=comment_id, status=MondayComment.PENDING).first()
    if not c:
        return "decided"
    waiting = MondayComment.objects.filter(pk=c.pk, status=MondayComment.PENDING)  # only while nobody decided it meanwhile
    _free_connection()
    try:
        allow, why = moderation.ai_check(c.body, c.display_name, c.minute.topic.title)
    except ai.AIUnavailable:
        return "down"
    except (ai.GenerationError, KeyError, TypeError):  # refused, cut off, not valid JSON, or not the shape asked for
        waiting.update(screen_failures=F("screen_failures") + 1)
        waiting.filter(screen_failures__gte=SCREEN_TRIES).update(
            status=MondayComment.HIDDEN, moderation=f"The AI check could not give an answer for this comment in {SCREEN_TRIES} tries. Review in the admin.")
        return "failed"
    except Exception:  # anything unexpected is treated as an outage: the comment waits and nothing is counted against it
        log.exception("Monday Minute comment %s: the AI check failed in an unexpected way", comment_id)
        return "down"
    waiting.update(status=MondayComment.VISIBLE if allow else MondayComment.HIDDEN, moderation="" if allow else why)
    return "decided"


def screen_one(comment_id: int) -> bool:
    """Screens one waiting comment. True if it was decided; False if the AI couldn't run or couldn't answer (it stays waiting)."""
    return _screen(comment_id) == "decided"


_screening = threading.Lock()  # held while this process's one background screening worker is running


def _screen_soon(comment_id: int):
    """Background screening for the local model: ONE worker per process goes through the waiting comments, oldest
    first. A thread per comment, each waiting on the AI with its own database connection, could use up the
    database's connections when the AI server was slow. A comment that arrives while the worker is busy is picked up
    on its next pass, or by the cron's screen_pending if the worker has just finished or the AI is down.
    With no AI set up at all (LOCAL_AI_URL blank) no worker starts: the comment waits, as it does during an outage,
    and the cron screens it once there is an AI. Starting one anyway wrote a traceback to the log for every comment."""
    if not ai.available() or not _screening.acquire(blocking=False):
        return

    def run():
        try:
            while screen_pending():
                pass
        except Exception:
            log.exception("Monday Minute comments: background screening stopped")
        finally:
            connection.close()
            _screening.release()

    threading.Thread(target=run, name="monday-comment-screening", daemon=True).start()


def screen_pending(limit=20):
    """Screens waiting comments, oldest first (the cron, and the background worker with the local model). Returns how
    many were decided. Stops when the AI can't be reached. A comment the AI cannot answer for is skipped, so one such
    comment no longer keeps every comment behind it waiting."""
    done = 0
    for pk in list(MondayComment.objects.filter(status=MondayComment.PENDING).values_list("pk", flat=True)[:limit]):
        result = _screen(pk)
        if result == "down":
            break
        done += result == "decided"
    return done
