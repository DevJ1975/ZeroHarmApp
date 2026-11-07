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
    """Released talks, newest first. Next week's talk stays hidden until its Sunday send time."""
    talks = [t.as_api() for t in ToolboxTalk.objects.released()]
    return JsonResponse({"talks": talks})


@require_GET
def talk_detail(request, issue):
    talk = ToolboxTalk.objects.released().filter(issue=issue).first()
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
    sheet = SigninSheet.objects.create(
        issue=data.get("issue") if isinstance(data.get("issue"), int) else None,
        talk_title=str(data.get("talk_title", ""))[:200], supervisor_name=str(data.get("supervisor_name", ""))[:120] or "Supervisor",
        supervisor_email=email, company=str(data.get("company", ""))[:120], location=str(data.get("location", ""))[:120],
        held_on=held_on, attendee_count=max(0, int(data.get("attendee_count") or 0)), has_group_photo=bool(data.get("has_group_photo")), pdf=pdf,
    )
    synced = sync_sheet_to_ghl(sheet)  # if GHL is down, the cron retries
    return JsonResponse({"ok": True, "id": sheet.pk, "saved_to_ghl": synced}, status=201)
