"""Monday Minute endpoints on API v2 (/api/v2/monday-minute/...). Separate from Zero Harm Weekly's /api/talks/."""
import hashlib
from typing import Literal

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import F
from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from ninja import Router, Schema
from ninja.throttling import AnonRateThrottle
from pydantic import Field

from . import ai, moderation
from .models import (HIDE_AT_COMMENT_REPORTS, PULL_AT_UNSAFE_REPORTS, MondayComment, MondayCommentReport,
                     MondayFeedback, MondayMinute)

router = Router(tags=["Monday Minute"])
InstallId = Field(min_length=16, max_length=64, pattern=r"^[A-Za-z0-9-]+$", description="Random id the app makes once per install")
Reason = Literal["unsafe", "not_my_site", "confusing", "too_long", "too_basic"]


def _hash(install_id: str) -> str:
    return hashlib.sha256(f"{settings.SECRET_KEY}:{install_id}".encode()).hexdigest()


def _author_key(install_hash: str) -> str:
    """Stable per-phone key the app uses to block a commenter. Reveals nothing about the phone."""
    return hashlib.sha256(f"author:{install_hash}".encode()).hexdigest()[:16]


def _released(pk: int) -> MondayMinute:
    return get_object_or_404(MondayMinute.objects.released(), pk=pk)


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


class CommentResult(Schema):
    status: Literal["visible", "pending", "rejected"]
    message: str
    comment: CommentOut | None = None


class ReportIn(Schema):
    install_id: str = InstallId
    reason: str = Field(default="", max_length=40)


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
    return {"minutes": [m.as_api() for m in MondayMinute.objects.released().select_related("topic")[:30]]}


@router.get("/{minute_id}", response=MinuteOut)
def get_minute(request: HttpRequest, minute_id: int):
    return _released(minute_id).as_api()


@router.post("/{minute_id}/feedback", response=FeedbackOut, summary="Thumbs up or down, one per phone (a new vote replaces the old)",
             throttle=[AnonRateThrottle("60/h")])
def rate(request: HttpRequest, minute_id: int, body: FeedbackIn):
    minute = _released(minute_id)
    MondayFeedback.objects.update_or_create(
        minute=minute, install_hash=_hash(body.install_id),
        defaults={"helpful": body.helpful, "reasons": [] if body.helpful else sorted(set(body.reasons)),
                  "note": "" if body.helpful else body.note.strip(), "platform": body.platform},
    )
    unsafe = sum(1 for r in minute.feedback.filter(helpful=False).values_list("reasons", flat=True) if "unsafe" in (r or []))
    if unsafe >= PULL_AT_UNSAFE_REPORTS:
        # Fully automatic means crews are the after-the-fact check: pull the talk and stop using its topic.
        MondayMinute.objects.filter(pk=minute.pk).update(status=MondayMinute.PULLED)
        topic = minute.topic
        topic.active = False
        topic.paused_reason = f"Paused: {unsafe} crew reports that the {minute.week:%b %-d} talk isn't safe or isn't right."
        topic.save(update_fields=["active", "paused_reason", "updated_at"])
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


@router.post("/{minute_id}/comments", response={201: CommentResult, 400: Error}, throttle=[AnonRateThrottle("10/h")],
             summary="Post a comment or reply. Screened before anyone sees it.")
def post_comment(request: HttpRequest, minute_id: int, body: CommentIn):
    minute = _released(minute_id)
    if not body.accepted_rules:
        return 400, {"error": "Please agree to the community rules first."}
    parent = None
    if body.parent_id:
        parent = minute.comments.filter(pk=body.parent_id, status=MondayComment.VISIBLE, parent__isnull=True).first()
        if not parent:
            return 400, {"error": "That comment isn't available to reply to."}
    name = " ".join(body.display_name.split())[:40] or "Crew member"
    text = body.body.strip()
    reason = moderation.quick_check(text, name)
    if reason:
        return 201, {"status": "rejected", "message": reason}
    comment = MondayComment(minute=minute, parent=parent, display_name=name, body=text, install_hash=_hash(body.install_id))
    if ai.is_local():
        # A CPU model can take a while: save it as waiting and screen it in the background, so posting never hangs.
        comment.status = MondayComment.PENDING
        comment.save()
        _screen_soon(comment.pk)
        return 201, {"status": "pending", "message": "Thanks! Checking your comment. It will show in a minute."}
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


@router.post("/comments/{comment_id}/report", response=Ok, throttle=[AnonRateThrottle("30/h")], summary="Report a comment")
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
    return {"ok": True}


def screen_one(comment_id: int) -> bool:
    """Screens one waiting comment. True if it was decided; False if the AI couldn't run (it stays waiting)."""
    c = MondayComment.objects.select_related("minute__topic").filter(pk=comment_id, status=MondayComment.PENDING).first()
    if not c:
        return True
    try:
        allow, why = moderation.ai_check(c.body, c.display_name, c.minute.topic.title)
    except Exception:
        return False
    c.status = MondayComment.VISIBLE if allow else MondayComment.HIDDEN
    c.moderation = "" if allow else why
    c.save(update_fields=["status", "moderation"])
    return True


def _screen_soon(comment_id: int):
    """Background screening for the local model. If it fails, the cron's screen_pending picks it up."""
    import threading

    from django.db import connection

    def run():
        try:
            screen_one(comment_id)
        finally:
            connection.close()

    threading.Thread(target=run, daemon=True).start()


def screen_pending(limit=20):
    """Cron: screens comments that were held because moderation was down. Returns how many were decided."""
    done = 0
    for pk in MondayComment.objects.filter(status=MondayComment.PENDING).values_list("pk", flat=True)[:limit]:
        if not screen_one(pk):
            break
        done += 1
    return done
