import hmac

from django.conf import settings
from django.http import Http404
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from .metrics import dashboard

RANGES = {"30": 30, "90": 90, "365": 365}


def _allowed(request) -> bool:
    """Signed-in admin staff, or the private key in the link GoHighLevel opens (frames can't rely on login cookies)."""
    if request.user.is_authenticated and request.user.is_staff:
        return True
    key = settings.BACKOFFICE_KEY
    return bool(key) and hmac.compare_digest(request.GET.get("key", ""), key)


@never_cache
@require_GET
def analytics(request):
    if not _allowed(request):
        raise Http404  # don't reveal that the page exists
    days = RANGES.get(request.GET.get("days", "30"), 30)
    context = dashboard(days)
    context.update(key=request.GET.get("key", ""), ranges=[(k, {"30": "30 days", "90": "90 days", "365": "12 months"}[k], v == days) for k, v in RANGES.items()],
                   admin_url=request.build_absolute_uri("/admin/"), embed_admin=settings.GHL_EMBED_ADMIN)
    response = render(request, "backoffice/dashboard.html", context)
    response["Referrer-Policy"] = "no-referrer"  # the key is in the address; never pass it on to other sites
    response["X-Robots-Tag"] = "noindex"
    return response
