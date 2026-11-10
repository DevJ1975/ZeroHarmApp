import json

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .integrations import sync_signup_to_ghl
from .models import AppSignup, ToolboxTalk


@require_GET
def health(request):
    return JsonResponse({"ok": True})


@require_GET
def talk_list(request):
    """Talks the app shows, newest first: released ones, plus (with TALKS_UNLOCK_EARLY) every reviewed talk with text."""
    talks = [t.as_api() for t in ToolboxTalk.objects.available()]
    return JsonResponse({"talks": talks})


@require_GET
def talk_detail(request, issue):
    talk = ToolboxTalk.objects.available().filter(issue=issue).first()
    if not talk:
        return JsonResponse({"error": "This talk isn’t available yet."}, status=404)
    return JsonResponse(talk.as_api())


def _client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return forwarded.split(",")[0].strip() or request.META.get("REMOTE_ADDR", "")


@csrf_exempt  # called by the mobile app, which has no browser session or CSRF cookie
@require_POST
def signup(request):
    key = f"signup-rate:{_client_ip(request)}"
    attempts = cache.get(key, 0)
    if attempts >= 5:
        return JsonResponse({"error": "Too many sign-ups from this network. Try again in an hour."}, status=429)
    cache.set(key, attempts + 1, 3600)

    try:
        data = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "Send JSON."}, status=400)

    email = str(data.get("email", "")).strip().lower()
    try:
        validate_email(email)
    except ValidationError:
        return JsonResponse({"error": "Enter a valid email address."}, status=400)

    record = AppSignup.objects.create(
        email=email,
        first_name=str(data.get("first_name") or "")[:80],
        company=str(data.get("company") or "")[:120],
        wants_offers=bool(data.get("wants_offers")),
    )
    sync_signup_to_ghl(record)  # failures are retried by the sync_signups command
    return JsonResponse({"ok": True}, status=201)


# ---- Feed: regulatory alerts and free resources -------------------------------------------------
import base64
import datetime as dt
import hmac
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils.dateparse import parse_date, parse_datetime

from .integrations import sync_sheet_to_ghl
from .models import FeedItem, GhlSync, SigninSheet

PACIFIC = ZoneInfo("America/Los_Angeles")


@require_GET
def feed_list(request):
    items = FeedItem.objects.released()
    kind = request.GET.get("kind")
    if kind:
        items = items.filter(kind__in=kind.split(","))
    return JsonResponse({"items": [i.as_api() for i in items[:100]]})


@require_GET
def feed_detail(request, pk):
    item = FeedItem.objects.released().filter(pk=pk).first()
    if not item:
        return JsonResponse({"error": "Not available."}, status=404)
    return JsonResponse(item.as_api())


def _when(value):
    """Accepts ISO date-times, plain dates and GHL's 'YYYY-MM-DD HH:MM'. Times without a zone are Pacific."""
    if not value:
        return dt.datetime.now(dt.timezone.utc)
    value = str(value).strip().replace("/", "-")
    moment = parse_datetime(value.replace(" ", "T")) if any(c in value for c in "T: ") else None
    if moment is None:
        day = parse_date(value[:10])
        if day is None:
            raise ValueError(f"Can't read the date '{value}'. Use YYYY-MM-DD HH:MM.")
        moment = dt.datetime.combine(day, dt.time(6, 0))
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=PACIFIC)
    return moment.astimezone(dt.timezone.utc)


def _truthy(v):
    return str(v).strip().lower() in ("1", "true", "yes", "y", "on", "send")


KIND_WORDS = {"alert": "alert", "regulatory alert": "alert", "course": "course", "free course": "course", "tool": "tool",
              "free tool": "tool", "video": "video", "newsletter": "newsletter", "newsletter issue": "newsletter"}
JURIS_WORDS = {"federal": "federal", "federal osha": "federal", "nevada": "nevada", "las vegas": "las_vegas", "las_vegas": "las_vegas", "": ""}


@csrf_exempt  # called by the GoHighLevel workflow, authenticated by the shared key instead
@require_POST
def ingest(request):
    """Publish from GoHighLevel. Header X-ZeroHarm-Key must match INGEST_KEY.
    Body: {"action": "publish" | "sync_year", ...}. Publishing the same external_id again updates the item."""
    key = settings.INGEST_KEY
    sent = request.headers.get("X-ZeroHarm-Key", "")
    if not key or not hmac.compare_digest(sent, key):
        return JsonResponse({"error": "Not authorized."}, status=401)
    try:
        data = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "Send JSON."}, status=400)
    data = {str(k).strip().lower().replace(" ", "_"): v for k, v in data.items()}

    if data.get("action") == "sync_zero_hour":
        from .zero_hour import sync_episodes
        return JsonResponse({"ok": True, "log": sync_episodes()})

    if data.get("action") == "sync_year":
        try:
            year = int(data.get("year"))
        except (TypeError, ValueError):
            return JsonResponse({"error": "Give the year, like 2028."}, status=400)
        job = GhlSync.objects.create(year=year, requested_by="ghl")
        return JsonResponse({"ok": True, "queued": f"{year} sync", "id": job.pk}, status=202)

    kind = KIND_WORDS.get(str(data.get("kind", data.get("type", ""))).strip().lower())
    title = str(data.get("title", "")).strip()
    if not kind or not title:
        return JsonResponse({"error": "kind (alert, course, tool, video, newsletter) and title are required."}, status=400)
    juris = JURIS_WORDS.get(str(data.get("jurisdiction", "")).strip().lower())
    if juris is None:
        return JsonResponse({"error": "jurisdiction must be Federal, Nevada or Las Vegas."}, status=400)
    present = lambda *names: next((n for n in names if n in data and str(data[n]).strip() != ""), None)
    fields = {"kind": kind, "title": title[:200]}
    try:
        if present("publish_at"):
            fields["publish_at"] = _when(data["publish_at"])
        if present("expires_at"):
            fields["expires_at"] = _when(data["expires_at"])
        if present("effective_date"):
            fields["effective_date"] = parse_date(str(data["effective_date"])[:10])
    except ValueError as err:
        return JsonResponse({"error": str(err)}, status=400)
    if present("jurisdiction"):
        fields["jurisdiction"] = juris
    for target, names, limit in (("summary", ("summary",), 2000), ("body_md", ("body", "body_md"), 20000),
                                 ("link_url", ("link", "link_url"), 500), ("image_url", ("image", "image_url"), 500)):
        name = present(*names)
        if name:
            fields[target] = str(data[name]).strip()[:limit]
    for flag in ("send_push", "featured"):
        if present(flag):
            fields[flag] = _truthy(data[flag])
    if present("unpublish"):
        fields["published"] = not _truthy(data["unpublish"])
    for f in ("link_url", "image_url"):
        if fields.get(f) and not fields[f].startswith("https://"):
            return JsonResponse({"error": f"{f} must start with https://"}, status=400)
    external_id = str(data.get("external_id") or f"{kind}:{title.lower()}")[:120]
    item = FeedItem.objects.filter(external_id=external_id).first()
    created = item is None
    if created:
        fields.setdefault("publish_at", _when(None))
        item = FeedItem(external_id=external_id)
    for k, v in fields.items():
        setattr(item, k, v)
    item.save()
    return JsonResponse({"ok": True, "id": item.pk, "created": created, "publish_at": item.publish_at.isoformat()}, status=201 if created else 200)


@csrf_exempt  # called by the app
@require_POST
def signin_sheet(request):
    """Receives a finished crew sign-in sheet PDF from the app and forwards it to GoHighLevel."""
    ipkey = f"sheet-rate:{_client_ip(request)}"
    if cache.get(ipkey, 0) >= 30:
        return JsonResponse({"error": "Too many sheets from this network. Try again in an hour."}, status=429)
    cache.set(ipkey, cache.get(ipkey, 0) + 1, 3600)
    if len(request.body) > 20 * 1024 * 1024:
        return JsonResponse({"error": "That sheet is too large."}, status=413)
    try:
        data = json.loads(request.body)
        pdf = base64.b64decode(data.get("pdf_base64", ""), validate=True)
        email = str(data.get("supervisor_email", "")).strip().lower()
        validate_email(email)
        held_on = parse_date(str(data.get("held_on", ""))[:10]) or dt.date.today()
    except (json.JSONDecodeError, ValueError, ValidationError):
        return JsonResponse({"error": "Send the PDF, a valid supervisor email and the date."}, status=400)
    if not pdf.startswith(b"%PDF"):
        return JsonResponse({"error": "That file is not a PDF."}, status=400)
    program = data.get("program") if data.get("program") in dict(SigninSheet.PROGRAMS) else "zero-harm-weekly"
    sheet = SigninSheet.objects.create(
        program=program,
        issue=data.get("issue") if isinstance(data.get("issue"), int) else None,
        talk_title=str(data.get("talk_title", ""))[:200], supervisor_name=str(data.get("supervisor_name", ""))[:120] or "Supervisor",
        supervisor_email=email, company=str(data.get("company", ""))[:120], location=str(data.get("location", ""))[:120],
        held_on=held_on, attendee_count=max(0, int(data.get("attendee_count") or 0)), has_group_photo=bool(data.get("has_group_photo")), pdf=pdf,
    )
    synced = sync_sheet_to_ghl(sheet)  # if GHL is down, the cron retries
    return JsonResponse({"ok": True, "id": sheet.pk, "saved_to_ghl": synced}, status=201)


# ---- OTIS knowledge base, weather and talk suggestions ------------------------------------------
from . import weather as wx
from .integrations import sync_suggestion_to_ghl
from .models import KbEntry, TalkSuggestion, ToolboxTalk


def _talk_chunks(talk, lang="en"):
    """Splits a released talk into sections so OTIS can retrieve and cite just the relevant part."""
    if lang == "es":
        title, question, body = talk.title_es, talk.crew_question_es, talk.body_md_es
    else:
        title, question, body = talk.title, talk.crew_question, talk.body_md
    label = f"Zero Harm Weekly #{talk.number or talk.issue}: {title}"
    sections, head = [], "Overview"
    for block in (body or "").split("\n\n## "):
        block = block.strip().lstrip("#").strip()
        if not block:
            continue
        if sections or (body or "").startswith("## "):
            head, _, block = block.partition("\n\n")
        sections.append((head.strip(), block.strip()))
    out = [{"id": f"t{talk.issue}-{lang}-q", "title": label, "text": f"Crew question: {question}", "source": label, "lang": lang, "issue": talk.issue}]
    for i, (h, text) in enumerate(sections):
        if text:
            out.append({"id": f"t{talk.issue}-{lang}-{i}", "title": f"{label} · {h}", "text": text, "source": label, "lang": lang, "issue": talk.issue})
    return out


@require_GET
def otis_kb(request):
    """Everything OTIS may answer from (v1). The app now uses /api/v2/otis/kb, which only downloads when it changed."""
    items = kb_items()
    version = max([e.updated_at for e in KbEntry.objects.all()] + [t.updated_at for t in ToolboxTalk.objects.available()], default=None)
    return JsonResponse({"version": version.isoformat() if version else "0", "items": items})


def kb_items():
    """Reviewed KB entries plus every released talk (English, and approved Spanish) and Zero Hour huddle card."""
    items = [{"id": f"k{e.pk}", "title": e.title, "text": e.body, "source": e.source or e.title, "lang": "en", "tags": e.tags, "issue": None}
             for e in KbEntry.objects.filter(published=True)]
    for talk in ToolboxTalk.objects.available():
        items += _talk_chunks(talk)
        if talk.spanish_status == ToolboxTalk.ES_APPROVED:
            items += _talk_chunks(talk, "es")
    for ep in Episode.objects.released():
        items += _episode_chunks(ep)
    return items


@require_GET
def otis_config(request):
    """Which on-device model the app downloads. Phones with less memory get the small one."""
    return JsonResponse({
        "enabled": settings.OTIS_ENABLED,
        "model": settings.OTIS_MODEL,
        "small_model": settings.OTIS_SMALL_MODEL,
        "min_memory_gb_for_model": 6,
    })


@require_GET
def weather(request):
    try:
        lat = round(float(request.GET["lat"]), 2)
        lon = round(float(request.GET["lon"]), 2)
    except (KeyError, ValueError):
        return JsonResponse({"error": "lat and lon are required."}, status=400)
    if not (18 <= lat <= 72 and -180 <= lon <= -64):
        return JsonResponse({"error": "Weather is available for US locations."}, status=404)
    try:
        return JsonResponse(wx.conditions(lat, lon))
    except Exception:
        return JsonResponse({"error": "Weather is unavailable right now."}, status=503)


@csrf_exempt  # called by the app
@require_POST
def suggestion(request):
    key = f"suggest-rate:{_client_ip(request)}"
    if cache.get(key, 0) >= 10:
        return JsonResponse({"error": "Thanks! That's a lot of ideas at once. Try again in an hour."}, status=429)
    cache.set(key, cache.get(key, 0) + 1, 3600)
    try:
        data = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "Send JSON."}, status=400)
    topic = str(data.get("topic", "")).strip()
    if len(topic) < 3:
        return JsonResponse({"error": "Tell us the topic in a few words."}, status=400)
    email = str(data.get("email", "")).strip().lower()
    if email:
        try:
            validate_email(email)
        except ValidationError:
            return JsonResponse({"error": "Check the email address, or leave it blank."}, status=400)
    s = TalkSuggestion.objects.create(
        topic=topic[:200], details=str(data.get("details", ""))[:4000], month_theme=str(data.get("month_theme", ""))[:80],
        name=str(data.get("name", ""))[:120], email=email, company=str(data.get("company", ""))[:120],
        may_contact=bool(data.get("may_contact")) and bool(email),
    )
    sync_suggestion_to_ghl(s)
    return JsonResponse({"ok": True, "id": s.pk}, status=201)


# ---- Zero Hour ------------------------------------------------------------------------------------
from .models import Episode


@require_GET
def episode_list(request):
    return JsonResponse({"episodes": [e.as_api() for e in Episode.objects.released()]})


@require_GET
def episode_detail(request, number):
    ep = Episode.objects.released().filter(number=number).first()
    if not ep:
        return JsonResponse({"error": "This episode isn't out yet."}, status=404)
    return JsonResponse(ep.as_api())


def _episode_chunks(ep):
    label = f"Zero Hour EP {ep.number:02d}: {ep.title} (huddle card)"
    base = {"lang": "en", "issue": None, "episode": ep.number, "source": label}
    return [
        {**base, "id": f"z{ep.number}-story", "title": f"{label} · The story", "text": f"{ep.hazard}. {ep.story}"},
        {**base, "id": f"z{ep.number}-chain", "title": f"{label} · Where the chain could have broken", "text": " ".join(ep.chain)},
        {**base, "id": f"z{ep.number}-checks", "title": f"{label} · {ep.checks_label}", "text": ". ".join(ep.checks) + "."},
        {**base, "id": f"z{ep.number}-stop", "title": f"{label} · Say stop when you see", "text": ep.stop_when},
        {**base, "id": f"z{ep.number}-emergency", "title": f"{label} · {ep.emergency_label}", "text": ep.emergency},
    ]
