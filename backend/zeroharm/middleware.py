"""Two small guards that sit in front of every view (see MIDDLEWARE in settings.py)."""
import hashlib
import json
import logging
import threading
import time
import unicodedata

from django.conf import settings
from django.core.cache import caches
from django.http import HttpResponse
from django.urls import NoReverseMatch, reverse

from .net import client_ip, network_key

log = logging.getLogger(__name__)


# ---- API errors as JSON ----------------------------------------------------------------------------

API_PREFIX = "/api/"
API_ERRORS = {
    400: "Bad request.",
    403: "Not allowed.",
    404: "Not found.",
    405: "Method not allowed.",
    413: "That is too large to send.",
    500: "Something went wrong on the server.",
}


class ApiJsonErrorsMiddleware:
    """Under /api/, an error that is not already JSON goes out as {"error": "..."}, the shape the views use.

    The views shape their own errors, but some answers never reach a view: an unknown address (404), a wrong method
    (405), a refused CSRF check (403), a body Django rejects (400) and a crash (500). Django answers those with an
    HTML page or an empty body, which a client reading JSON cannot parse. Everything outside /api/ (the admin, the
    back office, the invite page) keeps Django's pages. The status code and the other headers (Allow, cookies) stay
    as they were, and a crash is still written to the log with its traceback before it gets here."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if (
            request.path.startswith(API_PREFIX)
            and response.status_code >= 400
            and not getattr(response, "streaming", False)
            and "json" not in response.get("Content-Type", "")
        ):
            message = API_ERRORS.get(response.status_code, "The request failed.")
            response.content = b"" if request.method == "HEAD" else json.dumps({"error": message}).encode()
            response["Content-Type"] = "application/json"
            # CommonMiddleware has already written the length of the HTML page; a stale one would cut the answer short
            response["Content-Length"] = str(len(response.content))
        return response


# ---- Admin sign-in limit ---------------------------------------------------------------------------

ADMIN_LOGIN_MAX_FAILURES = 10  # wrong sign-ins an hour from one network, or for one username, before the limit bites
ADMIN_LOGIN_TRIES_UNDER_ATTACK = 3  # wrong tries one network gets at a username that is already over its count
ADMIN_LOGIN_WINDOW = 3600
ADMIN_LOGIN_REFUSED = "Too many failed sign-ins. Try again in an hour."


class AdminLoginLimitMiddleware:
    """Stops password guessing on the admin sign-in page (/admin/login/), which is open to the internet.

    Failed sign-ins are counted for an hour in the shared database cache (one count for every worker, and it holds
    across a restart), under salted hashes, so no address or username sits in the cache table. The hour starts with
    the first failure and is not moved by later ones.

    - Per network: after 10 failures from one network, that network is refused for the rest of the hour, whatever
      username or password it sends.
    - Per username: after 10 failures for one username, from anywhere, the username is treated as under attack. That
      alone refuses no one: a count anyone can run up from anywhere must not lock the real owner out, so a network
      that has not failed at this username still has its password checked, and the right one signs in. What changes
      is that each network now gets 3 wrong tries at that username in the hour, not 10, before it is refused. A
      guesser spread over many networks is cut to 3 guesses each; the owner is refused only after their own 3 misses.

    A failure is a POST to the sign-in page that comes back as the form again (status 200); a success redirects. A
    successful sign-in does not clear the counts: they run out by themselves.

    A try is counted BEFORE its password is checked and taken off again if the sign-in works. Counting afterwards let
    a burst of guesses sent at the same moment all be checked before the first one was counted. The price: tries
    being checked at that moment count as failures until they turn out right, so the eleventh sign-in to arrive
    while ten from the same network are still being checked is refused even if all of them are right.
    The check and the count happen under one lock, which covers the threads of one process. That is what the
    Dockerfile runs. The lock does not reach across processes: before running more than one, move the count into
    the database (one statement, or a row lock), or a burst spread over the processes can overshoot the ten again.

    "Network" is whatever zeroharm/net.py reads as the caller. If production turns out to put a shared address
    there (see the "Caller address:" log line), ten wrong sign-ins by strangers on that address refuse the owner for
    the hour too, until the two settings named in net.py are changed."""

    def __init__(self, get_response):
        self.get_response = get_response
        self.limits = caches["shared"]
        self.login_path = None
        self.lock = threading.Lock()

    def __call__(self, request):
        if request.method != "POST" or request.path != self._login_path():
            return self.get_response(request)
        # The same tidying Django gives a username before looking it up (NFKC), then case and spaces. Without it a
        # look-alike spelling such as a full-width "ｏwner" reached the same account but had a count of its own.
        username = unicodedata.normalize("NFKC", str(request.POST.get("username", ""))).strip().casefold()[:150]
        network = network_key(request)
        net_key = self._key("net", network)
        user_key = self._key("user", username) if username else None
        pair_key = self._key("pair", f"{username}|{network}") if username else None

        with self.lock:
            if self._count(net_key) >= ADMIN_LOGIN_MAX_FAILURES or (
                user_key
                and self._count(user_key) >= ADMIN_LOGIN_MAX_FAILURES
                and self._count(pair_key) >= ADMIN_LOGIN_TRIES_UNDER_ATTACK
            ):
                return HttpResponse(ADMIN_LOGIN_REFUSED, status=429, content_type="text/plain; charset=utf-8")
            net_count = self._add(net_key, 1)
            user_count = self._add(user_key, 1) if username else 0
            if username:
                self._add(pair_key, 1)

        response = self.get_response(request)
        if response.status_code != 200:  # signed in (a redirect), or turned away before the password was looked at
            with self.lock:
                for key in filter(None, (net_key, user_key, pair_key)):
                    self._add(key, -1)
            return response
        # The form again: wrong username or password, and the try stays counted.
        if net_count == ADMIN_LOGIN_MAX_FAILURES:
            log.warning("Admin: %s failed sign-ins from %s in an hour, refusing that network until it passes",
                        ADMIN_LOGIN_MAX_FAILURES, client_ip(request) or "an unknown address")
        if user_count == ADMIN_LOGIN_MAX_FAILURES:
            log.warning("Admin: %s failed sign-ins for one username in an hour, each network now gets %s tries at it",
                        ADMIN_LOGIN_MAX_FAILURES, ADMIN_LOGIN_TRIES_UNDER_ATTACK)
        return response

    def _login_path(self):
        if self.login_path is None:  # looked up on first use: the URLs are not loaded yet when middleware starts
            try:
                self.login_path = reverse("admin:login")
            except NoReverseMatch:
                self.login_path = ""
        return self.login_path

    @staticmethod
    def _key(kind, value):
        return f"admin-login:{kind}:" + hashlib.sha256(f"{settings.SECRET_KEY}:admin-login:{kind}:{value}".encode()).hexdigest()[:32]

    def _stored(self, key, now):
        """(count, the time its hour ends). No count, or one whose hour is over, is 0 with a new hour from now."""
        stored = self.limits.get(key)
        if isinstance(stored, tuple) and len(stored) == 2 and stored[0] > 0 and stored[1] > now:
            return stored
        return 0, now + ADMIN_LOGIN_WINDOW

    def _count(self, key):
        return self._stored(key, time.time())[0]

    def _add(self, key, by):
        """Adds `by` to a count and returns the new count. Call it holding the lock.

        The count is stored together with the time its hour ends and is always written back with exactly the time
        that is left. The cache's own incr() cannot be used for this: Django's database cache saves the count again
        with its default lifetime of 5 minutes, so from the second failure on the "hour" lasted five minutes."""
        now = time.time()
        count, until = self._stored(key, now)
        count += by
        if count <= 0:
            self.limits.delete(key)  # nothing left to remember; the next failure starts its own hour
            return 0
        self.limits.set(key, (count, until), until - now)
        return count
