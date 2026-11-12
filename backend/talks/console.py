"""The local content console's API. Every endpoint needs "Authorization: Bearer <CONSOLE_KEY>".

The console runs on your Mac and its dev server adds the key, so the key never reaches a browser.
Nothing here hard-deletes: "delete" unpublishes, so a mistake is one click to undo.
"""
import functools
import hashlib
import hmac
import json
import logging
import os
import re
import uuid

from django.conf import settings
from django.core.cache import caches
from django.core.exceptions import RequestDataTooBig
from django.db.models import Count, Max
from django.http import JsonResponse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET

from zeroharm.net import client_ip, network_key

from . import translate
from .integrations import send_broadcast, send_episode_push, send_feed_push, send_talk_push
from .models import Episode, FeedItem, KbEntry, SigninSheet, TalkSuggestion, ToolboxTalk
from .views import _when

log = logging.getLogger(__name__)
WHO = "console"
MAX_FAILURES = 10  # wrong keys per network before wrong keys stop being looked at
FAIL_WINDOW = 3600  # seconds the count is kept after the latest wrong key: the "hour" in the 429 message
MAX_WHOLE_NUMBER = 2147483647  # the largest number the database's integer columns hold
MIN_KEY_LENGTH = 32  # a short key could be guessed; the console stays off until it is long enough
UPSTREAM_FAILED = 424  # Claude said no. A 4xx, so the console doesn't mistake it for a lost connection.
limits = caches["shared"]  # one count for every worker, not one per process


class Bad(Exception):
    """A request we refuse. The message is shown to you in the console."""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def _err(message, status):
    return JsonResponse({"error": message}, status=status)


# ---- Auth ------------------------------------------------------------------------------------------

def _real_ip(request):
    """The caller's address, worked out in the one place that knows how (zeroharm/net.py), or "" when unknown."""
    return client_ip(request)


def _fail_key(request):
    """Where this caller's wrong keys are counted. Per network, not per address: an IPv6 caller owns a whole /64 and
    could otherwise use a new address for every try. Hashed, so no readable address sits in the cache table."""
    network = hashlib.sha256(f"{settings.SECRET_KEY}:console-fail:{network_key(request)}".encode()).hexdigest()[:32]
    return f"console-fail:{network}"


def _count_failure(fail_key):
    """Adds one wrong key to this network's count and keeps the count for an hour from now.
    Shared by every gunicorn worker (database cache)."""
    if not limits.add(fail_key, 1, FAIL_WINDOW):
        try:
            limits.incr(fail_key)
            # incr() saves the count again with the cache's default lifetime (5 minutes), which used to end the
            # "hour" early. Put the hour back.
            limits.touch(fail_key, FAIL_WINDOW)
        except ValueError:  # the entry expired between add and incr
            limits.add(fail_key, 1, FAIL_WINDOW)


def _check_key(request):
    """Returns an error response, or None when the key is right."""
    key = settings.CONSOLE_KEY
    if not key:
        return _err("The content console is off. Set CONSOLE_KEY on the web service.", 503)
    if len(key) < MIN_KEY_LENGTH:
        log.error("Console: CONSOLE_KEY is shorter than %s characters, so the console stays off", MIN_KEY_LENGTH)
        return _err(f"The content console is off. CONSOLE_KEY must be at least {MIN_KEY_LENGTH} characters (try openssl rand -hex 32).", 503)
    header = request.headers.get("Authorization", "")
    sent = header[7:] if header.startswith("Bearer ") else ""
    # The key is checked first, so the right key always gets in. Otherwise anyone counted as the same network
    # (or anyone at all, when the address can't be read) could lock you out of your own console with ten wrong keys.
    # The key is at least 32 characters, so letting it through costs nothing: it can't be found by guessing.
    if hmac.compare_digest(sent.encode(), key.encode()):
        return None
    fail_key = _fail_key(request)
    if limits.get(fail_key, 0) >= MAX_FAILURES:
        return _err("Too many wrong keys from this network. Wrong keys get this answer for an hour; the right key still works.", 429)
    _count_failure(fail_key)
    log.warning("Console: wrong key from %s", _real_ip(request) or "an unknown address")
    return _err("Not authorized.", 401)


def console_view(*methods):
    """Key check, allowed methods, and turning Bad into a JSON error, for every console endpoint."""
    def wrap(fn):
        @csrf_exempt  # called by the console's server with a bearer key, never with a browser session
        @functools.wraps(fn)
        def view(request, *args, **kwargs):
            denied = _check_key(request)
            if denied:
                return denied
            if request.method not in methods:
                return _err("Method not allowed.", 405)
            try:
                return fn(request, *args, **kwargs)
            except Bad as err:
                return _err(str(err), err.status)
            except Exception:  # keep every answer JSON, and keep the traceback in the logs
                log.exception("Console: %s %s failed", request.method, request.path)
                return _err("Something went wrong on the server. Check the web service logs.", 500)
        return view
    return wrap


def _body(request):
    try:
        raw = request.body
    except RequestDataTooBig:
        raise Bad("That is too large to send.", 413)
    try:
        data = json.loads(raw or b"{}")
    except (ValueError, RecursionError):  # not JSON, not UTF-8, a number too long to read, or nested too deep
        raise Bad("Send JSON.")
    if not isinstance(data, dict):
        raise Bad("Send a JSON object.")
    return data


def _done(action, what, **extra):
    log.info("Console: %s %s by %s %s", action, what, WHO, extra or "")


def _iso(value):
    return value.isoformat() if value else None


# ---- Field checks ----------------------------------------------------------------------------------
# Each check takes (field name, value) and returns the value to save, or raises Bad.

# A NUL character, or half of an emoji (JSON can carry half of a surrogate pair). PostgreSQL refuses the first in
# any text column, and the second can't be written as UTF-8 at all, so both are turned away here by name.
_CANT_STORE = re.compile(r"[\x00\ud800-\udfff]")


def _storable(name, v):
    if _CANT_STORE.search(v):
        raise Bad(f"{name} has a character that can't be saved (a NUL or a broken emoji). Delete it and type that part again.")
    return v


def text(limit=None, required=False):
    def check(name, v):
        if v is None:
            v = ""
        if not isinstance(v, str):
            raise Bad(f"{name} must be text.")
        v = _storable(name, v).strip()
        if required and not v:
            raise Bad(f"{name} can't be blank.")
        if limit and len(v) > limit:
            raise Bad(f"{name} is too long (max {limit} characters).")
        return v
    return check


def url(limit=200):
    def check(name, v):
        v = text(limit)(name, v)
        if v and not v.startswith("https://"):
            raise Bad(f"{name} must start with https://")
        return v
    return check


def flag(name, v):
    if not isinstance(v, bool):
        raise Bad(f"{name} must be true or false.")
    return v


def choice(options):
    def check(name, v):
        if v is None:
            v = ""
        if v not in options:
            raise Bad(f"{name} must be one of: {', '.join(o or '(blank)' for o in options)}.")
        return v
    return check


def when(required=True):
    """ISO date-time. A time without a zone is Pacific (America/Los_Angeles)."""
    def check(name, v):
        if v in (None, ""):
            if required:
                raise Bad(f"{name} can't be blank.")
            return None
        if not isinstance(v, str):
            raise Bad(f"{name} must be a date-time like 2027-01-03T11:59.")
        try:
            return _when(v)
        except (ValueError, OverflowError):  # OverflowError: year 1 or 9999, pushed out of range by its time zone
            raise Bad(f"Can't read {name} '{v}'. Use a date-time like 2027-01-03T11:59.")
    return check


def day(name, v):
    if v in (None, ""):
        return None
    try:
        parsed = parse_date(v[:10]) if isinstance(v, str) else None
    except ValueError:  # looks like a date but isn't one, like 2027-02-30
        parsed = None
    if parsed is None:
        raise Bad(f"{name} must be a date like 2027-01-03.")
    return parsed


def lines(name, v):
    if not isinstance(v, list) or not all(isinstance(i, str) for i in v):
        raise Bad(f"{name} must be a list of text.")
    return [_storable(name, i).strip() for i in v if i.strip()]


def whole_number(name, v):
    if v in (None, ""):
        return None
    if isinstance(v, bool) or not isinstance(v, int) or v < 1:
        raise Bad(f"{name} must be a whole number.")
    if v > MAX_WHOLE_NUMBER:
        raise Bad(f"{name} is too large (max {MAX_WHOLE_NUMBER}).")
    return v


def _apply(obj, data, checks):
    """Sets every known field present in data. Fields the console doesn't edit (like id) are ignored."""
    changed = []
    for name, check in checks.items():
        if name in data:
            setattr(obj, name, check(name, data[name]))
            changed.append(name)
    return changed


# ---- Content version (public) ----------------------------------------------------------------------

def content_version():
    """A short hash that changes whenever anything the app shows changes: an edit, a release, an unpublish.
    The ids of what's live are part of it, so one alert ending as another starts still counts as a change.
    Talks go in twice. available() is what the app lists: released talks plus the next few opened early, so a
    correction to an early talk reaches open phones. released() stays because a talk reaching its send time changes
    what phones show (last week's answer appears, the "early" mark goes) while the same talks stay listed."""
    parts = []
    for qs in (ToolboxTalk.objects.available(), ToolboxTalk.objects.released(), FeedItem.objects.released(),
               Episode.objects.released(), KbEntry.objects.filter(published=True)):
        agg = qs.order_by().aggregate(n=Count("pk"), latest=Max("updated_at"))
        ids = ",".join(str(pk) for pk in qs.order_by("pk").values_list("pk", flat=True))
        parts.append(f"{agg['n']}:{_iso(agg['latest'])}:{ids}")
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:12]


@require_GET
def public_content_version(request):
    res = JsonResponse({"version": content_version()})
    res["Cache-Control"] = "no-store"
    return res


# ---- Overview --------------------------------------------------------------------------------------

@console_view("GET")
def overview(request):
    now = timezone.now()
    upcoming = [{"type": "talk", "id": t.issue, "title": t.title, "at": _iso(t.send_at), "push": t.push_sent_at is None and not t.needs_review}
                for t in ToolboxTalk.objects.filter(published=True, send_at__gt=now).order_by("send_at")[:10]]
    upcoming += [{"type": "feed", "id": i.pk, "title": i.title, "at": _iso(i.publish_at), "push": i.send_push and i.push_sent_at is None}
                 for i in FeedItem.objects.filter(published=True, publish_at__gt=now).order_by("publish_at")[:10]]
    # "push" uses the same rule as the cron: an episode still needing details doesn't release, so it doesn't push.
    upcoming += [{"type": "episode", "id": e.number, "title": e.title, "at": _iso(e.release_at),
                  "push": e.send_push and not e.needs_details and e.push_sent_at is None}
                 for e in Episode.objects.filter(published=True, release_at__gt=now).order_by("release_at")[:10]]
    pushes = [{"type": "talk", "id": t.issue, "title": t.title, "at": t.push_sent_at}
              for t in ToolboxTalk.objects.filter(push_sent_at__isnull=False).order_by("-push_sent_at")[:10]]
    pushes += [{"type": "feed", "id": i.pk, "title": i.title, "at": i.push_sent_at}
               for i in FeedItem.objects.filter(push_sent_at__isnull=False).order_by("-push_sent_at")[:10]]
    pushes += [{"type": "episode", "id": e.number, "title": e.title, "at": e.push_sent_at}
               for e in Episode.objects.filter(push_sent_at__isnull=False).order_by("-push_sent_at")[:10]]
    pushes = sorted(pushes, key=lambda p: p["at"], reverse=True)[:10]
    return JsonResponse({
        "counts": {
            "talks": ToolboxTalk.objects.count(),
            "talks_released": ToolboxTalk.objects.released().count(),
            "talks_needing_review": ToolboxTalk.objects.filter(needs_review=True).count(),
            "feed_live": FeedItem.objects.released().count(),
            "episodes_released": Episode.objects.released().count(),
            "kb_entries": KbEntry.objects.filter(published=True).count(),
            "suggestions_new": TalkSuggestion.objects.filter(status="new").count(),
            "sheets_failed": SigninSheet.objects.filter(status="failed").count(),
        },
        "upcoming": sorted(upcoming, key=lambda u: u["at"])[:10],
        "recent_pushes": [{**p, "at": _iso(p["at"])} for p in pushes],
        "onesignal_configured": bool(settings.ONESIGNAL_APP_ID and settings.ONESIGNAL_REST_API_KEY),
        "anthropic_configured": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "content_version": content_version(),
    })


def _push_reply(ok, detail):
    """{"ok", "detail"} either way, as the contract says. A refusal is still a 200: the request worked,
    OneSignal said no, and detail carries its reason (for example, no subscribed devices)."""
    return JsonResponse({"ok": ok, "detail": detail})


def _wants_force(data):
    return data.get("force") is True


# ---- Talks -----------------------------------------------------------------------------------------

TALK_CHECKS = {
    "title": text(200, required=True), "story_title": text(200), "crew_question": text(), "body_md": text(),
    "month_theme": text(80), "hero_url": url(500), "pdf_url": url(500), "send_at": when(), "published": flag, "needs_review": flag,
    "title_es": text(200), "story_title_es": text(200), "crew_question_es": text(), "body_md_es": text(),
    "spanish_status": choice([ToolboxTalk.ES_NONE, ToolboxTalk.ES_DRAFT, ToolboxTalk.ES_APPROVED]),
}


def talk_released(t):
    return t.published and not t.needs_review and t.send_at <= timezone.now()


def talk_admin(t):
    return {
        **t.as_api(),
        # The stored text, not the shortened text phones get before send time (as_api drops "Last week's answer"
        # until then). The editor sends back what it loaded, so the shortened text would overwrite the real one.
        "body_md": t.body_md or None,
        "send_at": _iso(t.send_at), "published": t.published, "needs_review": t.needs_review, "review_flags": t.review_flags,
        "spanish_status": t.spanish_status, "title_es": t.title_es, "story_title_es": t.story_title_es,
        "crew_question_es": t.crew_question_es, "body_md_es": t.body_md_es, "push_sent_at": _iso(t.push_sent_at),
        "released": talk_released(t), "updated_at": _iso(t.updated_at),
    }


def _talk(issue):
    talk = ToolboxTalk.objects.filter(issue=issue).first()
    if not talk:
        raise Bad("No talk with that issue number.", 404)
    return talk


@console_view("GET")
def talks(request):
    return JsonResponse({"talks": [talk_admin(t) for t in ToolboxTalk.objects.order_by("-issue")]})


@console_view("GET", "PATCH")
def talk(request, issue):
    t = _talk(issue)
    if request.method == "PATCH":
        changed = _apply(t, _body(request), TALK_CHECKS)
        if t.spanish_status == ToolboxTalk.ES_APPROVED and not (t.title_es and t.body_md_es):
            raise Bad("Add the Spanish title and talk text before approving the Spanish version.")
        t.save()
        _done("edited talk", t.issue, fields=changed)
    return JsonResponse(talk_admin(t))


@console_view("POST")
def talk_push(request, issue):
    t = _talk(issue)
    data = _body(request)
    released = talk_released(t)
    if not released and not _wants_force(data):
        raise Bad("This talk isn't live in the app yet, so the push would open an empty screen. Send force to push anyway.", 409)
    # An early, forced push doesn't count as the release push, so the scheduled one still goes out.
    ok, detail = send_talk_push(t, dry_run=data.get("dry_run") is True, mark_sent=released)
    _done("pushed talk", t.issue, ok=ok)
    return _push_reply(ok, detail)


@console_view("POST")
def talk_spanish_draft(request, issue):
    t = _talk(issue)
    try:
        translate.draft_spanish(t)
    except Exception as err:  # missing key, Claude API error, or a reply that wasn't the JSON we asked for
        log.error("Console: Spanish draft for talk %s failed: %s", t.issue, err)
        return _err(f"Couldn't draft the Spanish version: {err}", UPSTREAM_FAILED)
    _done("drafted Spanish for talk", t.issue)
    t.refresh_from_db()
    return JsonResponse(talk_admin(t))


# ---- Feed: alerts and free resources ---------------------------------------------------------------

FEED_CHECKS = {
    "kind": choice([k for k, _ in FeedItem.KINDS]), "title": text(200, required=True), "summary": text(2000),
    "body_md": text(20000), "link_url": url(500), "image_url": url(500), "jurisdiction": choice([j for j, _ in FeedItem.JURISDICTIONS]),
    "effective_date": day, "publish_at": when(), "expires_at": when(required=False),
    "send_push": flag, "featured": flag, "published": flag,
}


def feed_live(i):
    now = timezone.now()
    return i.published and i.publish_at <= now and (i.expires_at is None or i.expires_at > now)


def feed_admin(i):
    return {
        **i.as_api(), "external_id": i.external_id, "publish_at": _iso(i.publish_at), "expires_at": _iso(i.expires_at),
        "published": i.published, "send_push": i.send_push, "push_sent_at": _iso(i.push_sent_at), "live": feed_live(i),
        "link_url_raw": i.link_url,
    }


def _feed_item(pk):
    item = FeedItem.objects.filter(pk=pk).first()
    if not item:
        raise Bad("No feed item with that id.", 404)
    return item


def _save_feed(item, data):
    changed = _apply(item, data, FEED_CHECKS)
    if not item.kind or not item.title:
        raise Bad("kind (alert, course, tool, video, newsletter) and title are required.")
    if item.expires_at and item.expires_at <= item.publish_at:
        raise Bad("expires_at must be after publish_at.")
    item.save()
    return changed


@console_view("GET", "POST")
def feed(request):
    if request.method == "POST":
        data = _body(request)
        item = FeedItem(external_id=f"console:{uuid.uuid4().hex[:12]}", publish_at=timezone.now())
        _save_feed(item, {k: v for k, v in data.items() if not (k == "publish_at" and v in (None, ""))})
        _done("created feed item", item.pk, kind=item.kind)
        return JsonResponse(feed_admin(item), status=201)
    return JsonResponse({"items": [feed_admin(i) for i in FeedItem.objects.all()]})


@console_view("GET", "PATCH", "DELETE")
def feed_item(request, pk):
    item = _feed_item(pk)
    if request.method == "PATCH":
        _done("edited feed item", item.pk, fields=_save_feed(item, _body(request)))
    elif request.method == "DELETE":
        item.published = False
        item.save()
        _done("unpublished feed item", item.pk)
    return JsonResponse(feed_admin(item))


@console_view("POST")
def feed_push(request, pk):
    item = _feed_item(pk)
    data = _body(request)
    live = feed_live(item)
    if not live and not _wants_force(data):
        raise Bad("This item isn't live in the app yet, so the push would open an empty screen. Send force to push anyway.", 409)
    ok, detail = send_feed_push(item, dry_run=data.get("dry_run") is True, mark_sent=live)
    _done("pushed feed item", item.pk, ok=ok)
    return _push_reply(ok, detail)


# ---- Zero Hour episodes ----------------------------------------------------------------------------

EPISODE_CHECKS = {
    "title": text(120, required=True), "hazard": text(120), "story": text(), "zero_hour": text(20), "chain": lines,
    "checks_label": text(80), "checks": lines, "stop_when": text(), "emergency_label": text(80), "emergency": text(),
    "questions": lines, "references": lines, "video_url": url(500), "thumbnail_url": url(500), "card_pdf_url": url(500),
    "release_at": when(), "published": flag, "needs_details": flag, "send_push": flag,
}


def episode_released(e):
    return e.published and not e.needs_details and e.release_at <= timezone.now()


def episode_admin(e):
    return {
        **e.as_api(), "release_at": _iso(e.release_at), "published": e.published, "needs_details": e.needs_details,
        "send_push": e.send_push, "push_sent_at": _iso(e.push_sent_at), "released": episode_released(e), "updated_at": _iso(e.updated_at),
    }


def _episode(number):
    ep = Episode.objects.filter(number=number).first()
    if not ep:
        raise Bad("No episode with that number.", 404)
    return ep


@console_view("GET")
def episodes(request):
    return JsonResponse({"episodes": [episode_admin(e) for e in Episode.objects.order_by("-number")]})


@console_view("GET", "PATCH")
def episode(request, number):
    ep = _episode(number)
    if request.method == "PATCH":
        changed = _apply(ep, _body(request), EPISODE_CHECKS)
        ep.save()
        _done("edited episode", ep.number, fields=changed)
    return JsonResponse(episode_admin(ep))


@console_view("POST")
def episode_push(request, number):
    ep = _episode(number)
    data = _body(request)
    released = episode_released(ep)
    if not released and not _wants_force(data):
        raise Bad("This episode isn't out yet, so the push would open an empty screen. Send force to push anyway.", 409)
    ok, detail = send_episode_push(ep, dry_run=data.get("dry_run") is True, mark_sent=released)
    _done("pushed episode", ep.number, ok=ok)
    return _push_reply(ok, detail)


# ---- OTIS knowledge base ---------------------------------------------------------------------------

KB_CHECKS = {"title": text(200, required=True), "body": text(required=True), "source": text(200), "tags": text(200), "published": flag}


def kb_admin(e):
    return {"id": e.pk, "title": e.title, "body": e.body, "source": e.source, "tags": e.tags, "published": e.published, "updated_at": _iso(e.updated_at)}


def _kb_entry(pk):
    entry = KbEntry.objects.filter(pk=pk).first()
    if not entry:
        raise Bad("No knowledge base entry with that id.", 404)
    return entry


@console_view("GET", "POST")
def kb(request):
    if request.method == "POST":
        data = _body(request)
        entry = KbEntry()
        _apply(entry, {"title": data.get("title"), "body": data.get("body"), **data}, KB_CHECKS)  # title and body always checked
        entry.save()
        _done("created KB entry", entry.pk)
        return JsonResponse(kb_admin(entry), status=201)
    return JsonResponse({"entries": [kb_admin(e) for e in KbEntry.objects.all()]})


@console_view("GET", "PATCH", "DELETE")
def kb_entry(request, pk):
    entry = _kb_entry(pk)
    if request.method == "PATCH":
        changed = _apply(entry, _body(request), KB_CHECKS)
        entry.save()
        _done("edited KB entry", entry.pk, fields=changed)
    elif request.method == "DELETE":
        entry.published = False
        entry.save()
        _done("unpublished KB entry", entry.pk)
    return JsonResponse(kb_admin(entry))


# ---- Talk suggestions ------------------------------------------------------------------------------

SUGGESTION_CHECKS = {"status": choice([s for s, _ in TalkSuggestion.STATUSES]), "used_in_issue": whole_number}


def suggestion_admin(s):
    return {
        "id": s.pk, "topic": s.topic, "details": s.details, "month_theme": s.month_theme, "name": s.name, "email": s.email,
        "company": s.company, "may_contact": s.may_contact, "status": s.status, "used_in_issue": s.used_in_issue,
        "created_at": _iso(s.created_at),
    }


@console_view("GET")
def suggestions(request):
    return JsonResponse({"suggestions": [suggestion_admin(s) for s in TalkSuggestion.objects.all()]})


@console_view("PATCH")
def suggestion(request, pk):
    s = TalkSuggestion.objects.filter(pk=pk).first()
    if not s:
        raise Bad("No suggestion with that id.", 404)
    changed = _apply(s, _body(request), SUGGESTION_CHECKS)
    s.save()
    _done("edited suggestion", s.pk, fields=changed)
    return JsonResponse(suggestion_admin(s))


# ---- Broadcast -------------------------------------------------------------------------------------
# One push to everyone who switched on ONE topic. Never to all devices. Promotional messages use "offers" only (Apple 4.5.4).

AUDIENCES = ("weekly_talk", "alerts", "zero_hour", "offers")
ROUTE = re.compile(r"^/(talk|alert|zero-hour|monday)/[0-9]+$|^/(learn|otis|archive)$")  # [0-9]: \d also matches digits from other scripts


@console_view("POST")
def broadcast(request):
    data = _body(request)
    audience = choice(AUDIENCES)("audience", data.get("audience"))
    heading = text(60, required=True)("heading", data.get("heading"))
    message = text(180, required=True)("message", data.get("message"))
    route = text(60)("route", data.get("route")) or None
    if route and not ROUTE.match(route):
        raise Bad("route must be /talk/<n>, /alert/<id>, /zero-hour/<n>, /monday/<id>, /learn, /otis or /archive.")
    dry_run = data.get("dry_run") is True
    ok, detail = send_broadcast(audience, heading, message, route=route, dry_run=dry_run)
    if not dry_run:
        _done("broadcast to", audience, heading=heading, route=route, ok=ok)
    return _push_reply(ok, detail)
