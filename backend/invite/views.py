"""The invite link the owner sends from GoHighLevel: https://YOUR-SERVER/get/?c={{contact.id}}

A phone goes straight to its app store when that store's address is set (APP_STORE_URL, PLAY_STORE_URL). Anything else
(a computer, or a store that isn't live yet) gets a small page with whichever store buttons exist, or "coming soon".
A tap from a GHL contact is counted once a day and tags the contact zero-harm-invite-clicked for a follow-up."""
import hashlib
import ipaddress
import re

from django.conf import settings
from django.core.cache import cache
from django.db import IntegrityError
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET

from talks.views import _client_ip

from .models import InviteClick
from .tagging import tag_click

# GoHighLevel contact ids are 20 letters and digits today. Allow some room, and nothing else, so junk never gets stored.
CONTACT_ID = re.compile(r"^[A-Za-z0-9]{10,40}$")
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
    """Counts per network, the same way as the usage count's limit: a whole IPv6 /64 is one network, and the cache key is
    a salted hash, so no readable address is kept anywhere."""
    ident = _client_ip(request)
    try:
        address = ipaddress.ip_address(ident)
        if address.version == 6:
            ident = str(ipaddress.ip_network(f"{address}/64", strict=False).network_address)
    except ValueError:
        pass
    return "invite-rate:" + hashlib.sha256(f"{settings.SECRET_KEY}:invite-throttle:{ident}".encode()).hexdigest()


def _over_limit(request):
    key = _network_key(request)
    if cache.add(key, 1, 3600):
        return False
    try:
        count = cache.incr(key)
    except ValueError:  # the entry ran out between the two calls
        cache.set(key, 1, 3600)
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
    if CONTACT_ID.match(contact_id):
        _record(request, contact_id, platform)

    app_store, play_store = _store_url("APP_STORE_URL"), _store_url("PLAY_STORE_URL")
    if platform == InviteClick.IOS and app_store:
        return _no_tracking(HttpResponseRedirect(app_store))
    if platform == InviteClick.ANDROID and play_store:
        return _no_tracking(HttpResponseRedirect(play_store))

    response = render(request, "invite/get.html", {"app_store": app_store, "play_store": play_store})
    response["Content-Security-Policy"] = "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
    return _no_tracking(response)
