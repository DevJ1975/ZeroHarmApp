"""The public privacy policy and terms of use that Apple and Google ask for, linked from the app and the store listings.

Plain pages with no scripts and nothing that tracks the reader. The dates live here so both pages and the tests agree."""
from django.conf import settings
from django.shortcuts import render
from django.views.decorators.http import require_GET

EFFECTIVE_DATE = "November 13, 2026"
LAST_UPDATED = "November 13, 2026"
CONTACT_EMAIL = "jamil@trainovations.com"
COMPANY = "Trainovate Technologies"
CSP = "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"


def _page(request, template):
    context = {
        "effective_date": EFFECTIVE_DATE,
        "last_updated": LAST_UPDATED,
        "contact_email": CONTACT_EMAIL,
        "company": COMPANY,
        "usage_keep_days": getattr(settings, "USAGE_KEEP_DAYS", 400),
        "crash_keep_days": getattr(settings, "SUPPORT_CRASH_KEEP_DAYS", 90),
    }
    response = render(request, template, context)
    response["Cache-Control"] = "public, max-age=3600"
    response["Content-Security-Policy"] = CSP
    return response


@require_GET
def privacy(request):
    return _page(request, "legal/privacy.html")


@require_GET
def terms(request):
    return _page(request, "legal/terms.html")
