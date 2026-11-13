"""Who is calling. The one place that works out the caller's network address; everything that limits, locks out or
looks up a place by address goes through here, so they all agree.

    client_ip(request) -> str          the caller's address ("203.0.113.7", "2001:db8::1"), or "" when unknown
    network_key(request_or_ip) -> str  what to COUNT per caller: the address for IPv4, the /64 for IPv6
    ScopedThrottle(rate, scope=...)    a Django Ninja limit with its own counter per scope and no address in the cache

Where the address comes from, in order (settings.py has the two settings):
1. The header named by CLIENT_IP_HEADER, "X-Real-IP" by default. Railway's docs say its edge writes the caller's
   address there (docs.railway.com/networking/public-networking/specs-and-limits: "X-Real-IP for identifying
   client's remote IP"). Their help forum, not the docs, says the edge replaces one a caller sends; it also carries
   a report of the header holding an edge address on some routes. Neither has been seen on this service yet, which
   is what the check below is for. One thing the code does not leave to the edge: if the header arrives twice, the
   proxy's value is the last one and that is the one used.
2. X-Forwarded-For, counted from the right with NUM_PROXIES. On Railway the last entry is one of the edge's own
   addresses (it changes per request), which is why this is only the fallback: it cannot be forged, but it is shared.
3. REMOTE_ADDR, the other end of the connection itself.

Checking it on production. Nobody has yet seen what Railway really sends this service, and the default above is only
right if X-Real-IP holds the caller. So the first time each layout of these headers is seen, one "Caller address:"
line goes to the web log (at most 8 per process, so per deploy or restart). It names the address headers that were
present, how many entries X-Forwarded-For had, and whether X-Real-IP equals the first entry, the last entry or
neither. Addresses are masked, "174.75.x.x": enough to tell your own network from the host's, never a whole address.
Any app open writes the line, and so does
    curl -X POST https://<your domain>/admin/login/          (it answers 403; that is fine)

What each outcome means for the two settings, CLIENT_IP_HEADER and NUM_PROXIES:
A. "equals the FIRST entry" (INFO). X-Real-IP holds the caller. Change nothing: leave CLIENT_IP_HEADER (X-Real-IP)
   and NUM_PROXIES (1) unset. Then check once that the edge replaces an X-Real-IP a caller sends:
       curl -X POST -H "X-Real-IP: 203.0.113.99" https://<your domain>/admin/login/
   No new line: it was replaced, all is well. A new line saying X-Real-IP "arrived 2 times": the edge added its own
   after yours and its own is the one read, also fine. A new WARNING that names 203.0.x.x: it was passed through
   and a caller can pick their own address, see C.
B. "equals the LAST entry" (WARNING). X-Real-IP holds the proxy's own address, so every limit is counting the proxy
   and strangers share one allowance. Set CLIENT_IP_HEADER to blank and NUM_PROXIES to the caller's place in
   X-Forwarded-For counted from the right: 2 when the line shows "caller, proxy". Counting from the right is what
   makes this safe: proxies add on the right, so an entry a caller makes up can only land further left.
C. "is NOT in X-Forwarded-For", or "equals entry 2 of 3, neither first nor last" (WARNING). The header did not come
   from the same place as the chain. Either a caller sent it and the proxy let it through, in which case every limit
   can be dodged by changing it, or the proxy writes some other hop there. Do not trust it: set CLIENT_IP_HEADER to
   blank and NUM_PROXIES as in B. One harmless case: if A is what normal traffic shows and this line has one entry
   more on the left, a caller added that entry themselves and X-Real-IP still held the real caller. Change nothing.
D. "equals the ONLY entry" (INFO). One proxy, and header and chain agree. If the masked address is your own
   network's, it is the caller: change nothing. If it is the host's, the same for everyone, no header read here
   holds the caller: the line lists the other address headers that were present, and CLIENT_IP_HEADER can name one
   of those once you have seen that the proxy overwrites it. NUM_PROXIES stays as it is.
E. "X-Real-IP is missing" or "is not an address" (WARNING). The fallback is in use: the X-Forwarded-For entry
   NUM_PROXIES from the right, by default the last one, which on Railway is the edge. Leave CLIENT_IP_HEADER and set
   NUM_PROXIES to the caller's place from the right, as in B.
F. "There is no X-Forwarded-For" (INFO). The header is used with nothing to compare it to. Normal on your Mac and on
   a host whose proxy writes only this header; not expected through Railway's public domain. Change nothing.
G. "CLIENT_IP_HEADER is blank" (INFO). What you get after the change in B, C or E: the line shows which entry is now
   read and its masked address. Right if that is your own network when you call, wrong if it is the host's.
After changing either setting, redeploy and read the new line: it describes the settings as they are now.

Until that check is done, know what is at stake. Under B or E every per-network limit is counting a shared address,
the admin sign-in limit included: ten wrong admin sign-ins by anyone behind that address refuse the owner's too for
the hour. Under C a caller may be able to dodge the limits by changing the header. Under A the limits lean on the
edge replacing a caller's X-Real-IP, which only the curl check shows.

On another host: if nothing in front of the app fills in CLIENT_IP_HEADER, step 1 finds nothing and steps 2 and 3
answer, which a caller cannot forge as long as NUM_PROXIES is the real number of proxies. The one unsafe setup is a
proxy that passes a caller's own X-Real-IP through untouched: there, set CLIENT_IP_HEADER to the header that proxy
does write (or to blank), or a caller could pick a new address for every request and dodge every limit.
"""
import hashlib
import ipaddress
import logging

from django.conf import settings
from django.core.cache import caches
from django.core.exceptions import ImproperlyConfigured
from ninja.throttling import AnonRateThrottle

log = logging.getLogger(__name__)
UNKNOWN = "unknown"  # network_key's answer when there is no usable address: all such callers share one count
MAX_REPORTS = 8  # "Caller address:" lines one process may write: a caller sending odd headers cannot fill the log
_seen_shapes = set()  # header layouts already written to the log, so each is reported once per process
# Other headers a proxy or CDN may put the caller's address in. Only their names are ever logged, to show what
# CLIENT_IP_HEADER could be pointed at; X-Railway-Edge holds no address, it shows the request came through the edge.
OTHER_ADDRESS_HEADERS = ("Forwarded", "CF-Connecting-IP", "True-Client-IP", "Fastly-Client-IP", "X-Client-IP",
                         "X-Envoy-External-Address", "X-Railway-Edge")


def _clean(value):
    """One address as plain text, or "" when the text is not an address. Accepts the forms proxies write:
    "203.0.113.7", "203.0.113.7:51234", "[2001:db8::1]:443", "fe80::1%eth0"."""
    text = str(value or "").strip().strip('"')
    if text.startswith("["):
        text = text[1:].split("]", 1)[0]
    elif text.count(":") == 1:  # IPv4 with a port; an IPv6 address has more than one colon
        text = text.split(":", 1)[0]
    try:
        address = ipaddress.ip_address(text.split("%", 1)[0])
    except ValueError:
        return ""
    if address.version == 6 and address.ipv4_mapped:  # "::ffff:203.0.113.7" is the IPv4 caller 203.0.113.7
        address = address.ipv4_mapped
    return str(address)


def _mask(value):
    """An address with its second half blanked, for the log: "174.75.x.x", "2001:db8:x:x:x:x:x:x". Enough to tell
    your own network from the host's, not enough to point at one connection. Text that is not an address is never
    echoed, so nothing a caller types into a header can reach the log through here."""
    ip = _clean(value)
    if not ip:
        return "not an address"
    address = ipaddress.ip_address(ip)
    if address.version == 4:
        first, second = ip.split(".")[:2]
        return f"{first}.{second}.x.x"
    first, second = address.exploded.split(":")[:2]
    return f"{int(first, 16):x}:{int(second, 16):x}:x:x:x:x:x:x"


def _note_shape(request, header, values, hops):
    """Writes once per process, for each layout of the address headers, what arrived and where the caller's header
    sits in the X-Forwarded-For chain, so the first deploy shows whether the header holds the caller. The letters
    are the outcomes at the top of this file, which say what to set for each. Addresses only ever go out masked."""
    if len(_seen_shapes) >= MAX_REPORTS or not (values or hops):
        return  # said enough already, or nothing went through a proxy (local runs, Railway's health check)
    found = _clean(values[-1]) if values else ""
    chain = [_clean(h) for h in hops]
    if not header:
        where = "off"
    elif not found:
        where = "unusable" if values else "missing"
    elif not chain:
        where = "alone"
    elif len(chain) == 1:
        where = "only" if found == chain[0] else "neither"
    elif found == chain[0]:
        where = "first"
    elif found == chain[-1]:
        where = "last"
    else:
        where = "middle" if found in chain else "neither"
    # Long chains and repeated headers are grouped, so a caller cannot use up the reports by sending 5, 6, 7 entries.
    shape = (where, min(len(chain), 4), min(len(values), 2))
    if shape in _seen_shapes:
        return
    _seen_shapes.add(shape)

    names = dict.fromkeys(filter(None, (header, "X-Real-IP", "X-Forwarded-For") + OTHER_ADDRESS_HEADERS))  # no doubles
    present = [name for name in names if request.headers.get(name)]
    shown = ", ".join(_mask(h) for h in chain[:6]) + (f" and {len(chain) - 6} more" if len(chain) > 6 else "")
    said = _mask(found)
    line = f"Caller address: headers present: {', '.join(present)}. "
    line += f"X-Forwarded-For has {len(chain)} {'entry' if len(chain) == 1 else 'entries'} ({shown}). " if chain else "There is no X-Forwarded-For. "
    if len(values) > 1:
        line += f"{header} arrived {len(values)} times; the last value, the one written nearest the app, is read. "
    # What the fallback reads when the header is not used: the same entry client_ip picks further down.
    proxies = getattr(settings, "NUM_PROXIES", 1)
    if proxies > 0 and chain:
        fallback = f"X-Forwarded-For, entry {min(proxies, len(chain))} from the right (NUM_PROXIES={proxies}): {_mask(chain[-min(proxies, len(chain))])}"
    else:
        fallback = "the connection itself, not from any header (NUM_PROXIES=0)"
    warn = True
    if where == "first":
        warn = False
        line += f"{header} ({said}) equals the FIRST entry: it holds the caller. Outcome A: nothing to change."
    elif where == "last":
        line += (f"{header} ({said}) equals the LAST entry, which is the proxy's own address, not the caller: limits are "
                 f"counting the proxy. Outcome B: set CLIENT_IP_HEADER to blank and NUM_PROXIES to the caller's place from the right.")
    elif where == "middle":
        place = chain.index(found) + 1
        line += (f"{header} ({said}) equals entry {place} of {len(chain)}, neither first nor last "
                 f"({len(chain) - place + 1} from the right). Outcome C: read it before changing anything.")
    elif where == "neither":
        line += (f"{header} ({said}) is NOT in X-Forwarded-For: it may be a value the caller sent, or another hop. "
                 f"Outcome C: do not trust it until checked.")
    elif where == "only":
        warn = False
        line += f"{header} ({said}) equals the ONLY entry. Outcome D: right if that is the caller's network, not the host's."
    elif where == "alone":
        warn = False
        line += f"{header} ({said}) is used with nothing to compare it to. Outcome F."
    elif where == "off":
        warn = False
        line += f"CLIENT_IP_HEADER is blank, so the caller is read from {fallback}. Outcome G: right if that is the caller's network, not the host's."
    else:
        line += f"{header} is {'not an address' if values else 'missing'}, so the caller is read from {fallback}. Outcome E."
    line += " See the top of zeroharm/net.py."
    if len(_seen_shapes) >= MAX_REPORTS:
        line += f" This is report {MAX_REPORTS} of {MAX_REPORTS}: no more are written until the next restart."
    log.log(logging.WARNING if warn else logging.INFO, "%s", line)


def client_ip(request):
    """The caller's address as text, or "" when none of the sources holds a real address. Never anything else:
    every value is checked with the ipaddress module, so junk in a header cannot end up in a key, a log or a lookup."""
    hops = [h for h in request.META.get("HTTP_X_FORWARDED_FOR", "").split(",") if h.strip()]
    header = getattr(settings, "CLIENT_IP_HEADER", "X-Real-IP")
    # If the header arrives more than once the values are joined with commas; the last one is the one written
    # closest to us, by the proxy, so a value a caller sent first is never the one used.
    values = [v for v in request.headers.get(header, "").split(",") if v.strip()] if header else []
    _note_shape(request, header, values, hops)
    found = _clean(values[-1]) if values else ""
    if found:
        return found
    proxies = getattr(settings, "NUM_PROXIES", 1)
    if proxies > 0 and hops:
        found = _clean(hops[-min(proxies, len(hops))])
        if found:
            return found
    return _clean(request.META.get("REMOTE_ADDR", ""))


def network_key(request_or_ip):
    """What rate limits, lockouts and "different networks" rules count, as a short stable string. Takes a request or
    an address. IPv4: the address ("203.0.113.7"). IPv6: its /64 ("2001:db8:1:2::/64"), because one home or phone
    connection owns a whole /64 and could otherwise switch addresses to look like someone new. No address: "unknown".
    This is readable, so hash it before using it in a cache key or storing it (ScopedThrottle does)."""
    ip = _clean(request_or_ip) if isinstance(request_or_ip, str) else client_ip(request_or_ip)
    if not ip:
        return UNKNOWN
    address = ipaddress.ip_address(ip)
    if address.version == 6:
        return f"{ipaddress.ip_network(f'{address}/64', strict=False).network_address}/64"
    return ip


class ScopedThrottle(AnonRateThrottle):
    """A per-network limit for one Django Ninja endpoint: ScopedThrottle("60/h", scope="monday-feedback").

    Like Ninja's AnonRateThrottle, with two differences. The scope is required and is part of the cache key, so every
    endpoint has its own counter (the stock class puts every endpoint in one "anon" counter, so a busy endpoint used
    up the allowance of the others). And the caller comes from network_key above, salted and hashed, so the count is
    per network and no readable address sits in the cache.

    The counts are kept in the "limits" cache (settings.CACHES), which holds nothing but counters. The stock class
    uses the default cache, where weather and other content took the room and pushed the counts out."""

    def __init__(self, rate, scope):
        if not isinstance(scope, str) or not scope.strip():
            raise ImproperlyConfigured('ScopedThrottle needs a scope name, e.g. ScopedThrottle("60/h", scope="monday-feedback").')
        super().__init__(rate)
        self.scope = scope.strip()

    @property
    def cache(self):
        return caches["limits"]  # looked up on each use, so it is always the cache the settings name now

    def get_ident(self, request):
        return hashlib.sha256(f"{settings.SECRET_KEY}:throttle:{network_key(request)}".encode()).hexdigest()[:32]

    def get_cache_key(self, request):
        return f"throttle:{self.scope}:{self.get_ident(request)}"
