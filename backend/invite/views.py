"""The invite link the owner sends from GoHighLevel: https://YOUR-SERVER/get/?c={{contact.id}}

A phone goes straight to its app store when that store's address is set (APP_STORE_URL, PLAY_STORE_URL). Anything else
(a computer, or a store that isn't live yet) gets a small page with whichever store buttons exist, or "coming soon".
A tap from a GHL contact is counted once a day and tags the contact zero-harm-invite-clicked for a follow-up."""
import hashlib
import re

from django.conf import settings
from django.core.cache import caches
from django.db import IntegrityError
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET

from zeroharm.net import network_key

from .models import InviteClick
from .tagging import CONTACT_ID, tag_click  # CONTACT_ID: 10 to 40 letters and digits, checked with fullmatch

# New rows one network may add an hour. A crew forwarding the link around one plant Wi-Fi stays well under it; a script
# inventing contact ids does not get to fill the table.
NEW_CLICKS_PER_HOUR = 30
TAG_WAIT = 3  # seconds the visitor may wait for GoHighLevel; the cron tags it later if this runs out


def _platform(request):
    agent = request.META.get("HTTP_USER_AGENT", "")
    if re.search(r"iPhone|iPad|iPod", agent):
        return InviteClick.IOS
    if "Android" in agent:
        return InviteClick.ANDROID
    return InviteClick.OTHER


def _store_url(name):
    """The store address from settings, when it is a real https address."""
    url = (getattr(settings, name, "") or "").strip()
    return url if url.startswith("https://") else ""


def _network_key(request):
    """Counts per network, the same way as every other limit (zeroharm/net.py): a whole IPv6 /64 is one network, and
    the cache key is a salted hash, so no readable address is kept anywhere."""
    return "invite-rate:" + hashlib.sha256(f"{settings.SECRET_KEY}:invite-throttle:{network_key(request)}".encode()).hexdigest()


def _over_limit(request):
    # The count lives in the "limits" cache (settings.CACHES), which holds nothing but counters. In the default cache
    # weather and other content could push it out, and the hour's limit started again from zero.
    counters, key = caches["limits"], _network_key(request)
    if counters.add(key, 1, 3600):
        return False
    try:
        count = counters.incr(key)
    except ValueError:  # the entry ran out between the two calls
        counters.set(key, 1, 3600)
        return False
    return count > NEW_CLICKS_PER_HOUR


def _record(request, contact_id, platform):
    """One row per contact per day. Reloads and repeat taps change nothing and don't count toward the limit."""
    today = timezone.localdate()
    if InviteClick.objects.filter(contact_id=contact_id, day=today).exists() or _over_limit(request):
        return
    try:
        click = InviteClick.objects.create(contact_id=contact_id, day=today, platform=platform)
    except IntegrityError:  # two taps at the same moment
        return
    tag_click(click, timeout=TAG_WAIT)


def _no_tracking(response):
    response["Cache-Control"] = "no-store"
    response["X-Robots-Tag"] = "noindex"
    response["Referrer-Policy"] = "no-referrer"  # the contact id is in the address; don't hand it on to the store
    return response


@require_GET
def get_app(request):
    platform = _platform(request)
    contact_id = request.GET.get("c", "")
    # fullmatch, not match: with match and "$" an id ending in a line break got through, was stored, and could not
    # be put into a GoHighLevel address afterwards (see tagging.py for what that did to the cron).
    if CONTACT_ID.fullmatch(contact_id):
        _record(request, contact_id, platform)

    app_store, play_store = _store_url("APP_STORE_URL"), _store_url("PLAY_STORE_URL")
    if platform == InviteClick.IOS and app_store:
        return _no_tracking(HttpResponseRedirect(app_store))
    if platform == InviteClick.ANDROID and play_store:
        return _no_tracking(HttpResponseRedirect(play_store))

    response = render(request, "invite/get.html", {"app_store": app_store, "play_store": play_store})
    response["Content-Security-Policy"] = "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
    return _no_tracking(response)
