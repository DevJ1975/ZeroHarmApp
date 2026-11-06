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
