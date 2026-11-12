"""Tests for the shared pieces in zeroharm/: who is calling (net.py), the cache that holds only counters, the one
LOGGING block, API errors as JSON and the admin sign-in limit (middleware.py)."""
import ast
import io
import json
import logging
import os
import runpy
import sys
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache, caches
from django.core.cache.backends.locmem import LocMemCache
from django.core.exceptions import ImproperlyConfigured, SuspiciousOperation
from django.db import connection
from django.http import HttpResponse, JsonResponse
from django.test import Client, RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import include, path
from django.utils.dateparse import parse_datetime
from django.utils.log import configure_logging
from ninja import NinjaAPI

from zeroharm import net
from zeroharm.middleware import ADMIN_LOGIN_MAX_FAILURES, ADMIN_LOGIN_REFUSED, ADMIN_LOGIN_WINDOW, AdminLoginLimitMiddleware
from zeroharm.net import ScopedThrottle, client_ip, network_key

CALLER = "174.75.44.22"   # the phone or laptop
EDGE = "84.17.44.228"     # one of Railway's edge addresses: last in X-Forwarded-For, different on each request
EDGE_2 = "84.17.44.225"


# ---- A URL set for these tests: the real one plus views that fail in the ways a view never should -----------------

def _boom(request):
    raise RuntimeError("kaboom in a view")


def _suspicious(request):
    raise SuspiciousOperation("no thanks")


def _needs_csrf(request):
    return JsonResponse({"ok": True})


def _plain_refusal(request):
    return HttpResponse("nope", status=418, content_type="text/plain")


test_api = NinjaAPI(urls_namespace="fix-core-test")


@test_api.post("/limited-a", throttle=[ScopedThrottle("2/h", scope="fix-core-a")])
def _limited_a(request):
    return {"ok": True}


@test_api.post("/limited-b", throttle=[ScopedThrottle("2/h", scope="fix-core-b")])
def _limited_b(request):
    return {"ok": True}


urlpatterns = [
    path("api/boom/", _boom),
    path("api/suspicious/", _suspicious),
    path("api/needs-csrf/", _needs_csrf),
    path("api/teapot/", _plain_refusal),
    path("api/fix-core/", test_api.urls),
    path("boom/", _boom),
    path("", include("zeroharm.urls")),
]
WITH_TEST_URLS = override_settings(ROOT_URLCONF="talks.tests_fix_core")


def _request(real_ip=None, forwarded=None, remote="10.250.0.9", **extra):
    """A request as the app receives it: REMOTE_ADDR is the proxy next to it, the headers are what the edge wrote."""
    if real_ip is not None:
        extra["HTTP_X_REAL_IP"] = real_ip
    if forwarded is not None:
        extra["HTTP_X_FORWARDED_FOR"] = forwarded
    return RequestFactory().get("/api/health/", REMOTE_ADDR=remote, **extra)


# ---- Who is calling ------------------------------------------------------------------------------------------------

class ClientIpTests(SimpleTestCase):
    def test_production_chain_returns_the_caller_not_the_edge(self):
        # What Railway sends: the caller in X-Real-IP, and "caller, edge" in X-Forwarded-For.
        self.assertEqual(client_ip(_request(CALLER, f"{CALLER}, {EDGE}")), CALLER)
        self.assertEqual(client_ip(_request(CALLER, f"{CALLER}, {EDGE_2}")), CALLER)  # the edge address changes, the answer does not

    def test_forged_forwarded_for_changes_nothing(self):
        honest = client_ip(_request(CALLER, f"{CALLER}, {EDGE}"))
        self.assertEqual(client_ip(_request(CALLER, f"203.0.113.7, {CALLER}, {EDGE}")), honest)
        self.assertEqual(client_ip(_request(CALLER, "203.0.113.7")), honest)
        self.assertEqual(client_ip(_request(CALLER, "not an address, 198.51.100.9")), honest)

    def test_header_sent_twice_uses_the_one_the_proxy_wrote(self):
        # A server joins a repeated header with commas; the proxy's own value is the last one.
        self.assertEqual(client_ip(_request(f"203.0.113.7, {CALLER}")), CALLER)

    def test_without_the_header_forwarded_for_is_counted_from_the_right(self):
        chain = f"203.0.113.7, {CALLER}, {EDGE}"
        with override_settings(NUM_PROXIES=1):
            self.assertEqual(client_ip(_request(None, chain)), EDGE)   # not forgeable: the proxy wrote it
        with override_settings(NUM_PROXIES=2):
            self.assertEqual(client_ip(_request(None, chain)), CALLER)
        with override_settings(NUM_PROXIES=9):
            self.assertEqual(client_ip(_request(None, chain)), "203.0.113.7")  # fewer hops than proxies: the first one
        with override_settings(NUM_PROXIES=0):
            self.assertEqual(client_ip(_request(None, chain)), "10.250.0.9")   # X-Forwarded-For ignored

    def test_without_any_header_it_is_the_connection(self):
        self.assertEqual(client_ip(_request()), "10.250.0.9")

    def test_junk_is_never_returned(self):
        self.assertEqual(client_ip(_request("<script>", f"{CALLER}, {EDGE}")), EDGE)       # bad header: next source
        self.assertEqual(client_ip(_request("999.1.1.1", "also, junk")), "10.250.0.9")       # bad chain: the connection
        self.assertEqual(client_ip(_request("", "", remote="unix:/tmp/sock")), "")           # nothing usable: blank
        self.assertEqual(client_ip(_request("x" * 5000, None, remote="")), "")

    def test_forms_a_proxy_may_write(self):
        self.assertEqual(client_ip(_request("203.0.113.7:51234")), "203.0.113.7")
        self.assertEqual(client_ip(_request("[2001:db8::1]:443")), "2001:db8::1")
        self.assertEqual(client_ip(_request("::ffff:203.0.113.7")), "203.0.113.7")
        self.assertEqual(client_ip(_request("2001:0DB8:0000:0000:0000:0000:0000:0001")), "2001:db8::1")
        self.assertEqual(client_ip(_request(None, None, remote="fe80::1%eth0")), "fe80::1")

    def test_the_header_name_is_a_setting(self):
        request = _request(EDGE, f"{CALLER}, {EDGE}", HTTP_CF_CONNECTING_IP="198.51.100.4")
        with override_settings(CLIENT_IP_HEADER="CF-Connecting-IP"):
            self.assertEqual(client_ip(request), "198.51.100.4")
        with override_settings(CLIENT_IP_HEADER="", NUM_PROXIES=2):  # blank: skip the header, count X-Forwarded-For
            self.assertEqual(client_ip(request), CALLER)

    def test_settings_defaults(self):
        self.assertEqual(settings.CLIENT_IP_HEADER, "X-Real-IP")
        self.assertEqual(settings.NINJA_NUM_PROXIES, settings.NUM_PROXIES)

    def test_a_header_that_holds_the_edge_address_is_reported_once(self):
        net._seen_shapes.clear()
        with self.assertLogs("zeroharm.net", "WARNING") as logs:
            client_ip(_request(EDGE, f"{CALLER}, {EDGE}"))
        self.assertIn("LAST", logs.output[0])
        self.assertNotIn(EDGE, logs.output[0])  # the note says where the address sat, not what it was
        with self.assertNoLogs("zeroharm.net", "INFO"):
            client_ip(_request(EDGE_2, f"{CALLER}, {EDGE_2}"))


class CallerAddressReportTests(SimpleTestCase):
    """The one-off "Caller address:" log lines: what the first deploy is read from. Each must say which headers
    came, how many X-Forwarded-For entries there were and where X-Real-IP sits among them, with every address masked."""

    V6 = "2600:1700:abcd:1234:5678:9abc:def0:1234"
    FULL = (CALLER, EDGE, EDGE_2, "203.0.113.99", "198.51.100.4", V6, "2600:1700:abcd", "abcd:1234")

    def setUp(self):
        net._seen_shapes.clear()
        self.addCleanup(net._seen_shapes.clear)

    def report(self, *args, level="INFO", **kwargs):
        """The one line written for this request, after checking that no whole address is in it."""
        with self.assertLogs("zeroharm.net", level) as logs:
            client_ip(_request(*args, **kwargs))
        self.assertEqual(len(logs.output), 1, logs.output)
        for whole in self.FULL:
            self.assertNotIn(whole, logs.output[0])
        self.assertIn("Caller address: headers present: ", logs.output[0])
        return logs.output[0]

    def test_addresses_are_masked(self):
        self.assertEqual(net._mask(CALLER), "174.75.x.x")
        self.assertEqual(net._mask(f"{CALLER}:51234"), "174.75.x.x")
        self.assertEqual(net._mask(self.V6), "2600:1700:x:x:x:x:x:x")
        self.assertEqual(net._mask("::ffff:174.75.44.22"), "174.75.x.x")
        # Text that is not an address is described, never repeated: a header is something a caller can type.
        for junk in ("<script>alert(1)</script>", "password=hunter2", "", "999.1.1.1", "x" * 500):
            self.assertEqual(net._mask(junk), "not an address")

    def test_first_entry_is_the_healthy_report(self):
        line = self.report(CALLER, f"{CALLER}, {EDGE}")
        self.assertTrue(line.startswith("INFO:"), line)
        self.assertIn("headers present: X-Real-IP, X-Forwarded-For.", line)
        self.assertIn("X-Forwarded-For has 2 entries (174.75.x.x, 84.17.x.x).", line)
        self.assertIn("X-Real-IP (174.75.x.x) equals the FIRST entry", line)
        self.assertIn("Outcome A", line)

    def test_last_entry_is_a_warning(self):
        line = self.report(EDGE, f"{CALLER}, {EDGE}", level="WARNING")
        self.assertTrue(line.startswith("WARNING:"), line)
        self.assertIn("X-Forwarded-For has 2 entries (174.75.x.x, 84.17.x.x).", line)
        self.assertIn("X-Real-IP (84.17.x.x) equals the LAST entry", line)
        self.assertIn("Outcome B", line)

    def test_a_header_that_is_not_in_the_chain_is_a_warning(self):
        # What the owner's own check looks like if the edge lets a caller's X-Real-IP through.
        line = self.report("203.0.113.99", f"{CALLER}, {EDGE}", level="WARNING")
        self.assertTrue(line.startswith("WARNING:"), line)
        self.assertIn("X-Real-IP (203.0.x.x) is NOT in X-Forwarded-For", line)
        self.assertIn("Outcome C", line)

    def test_neither_first_nor_last_says_which_entry(self):
        line = self.report(CALLER, f"203.0.113.99, {CALLER}, {EDGE}", level="WARNING")
        self.assertIn("X-Forwarded-For has 3 entries (203.0.x.x, 174.75.x.x, 84.17.x.x).", line)
        self.assertIn("equals entry 2 of 3, neither first nor last (2 from the right)", line)
        self.assertIn("Outcome C", line)

    def test_one_entry_missing_header_and_no_chain(self):
        line = self.report(CALLER, CALLER)
        self.assertIn("X-Forwarded-For has 1 entry (174.75.x.x).", line)
        self.assertIn("equals the ONLY entry. Outcome D", line)
        line = self.report(None, f"{CALLER}, {EDGE}", level="WARNING")
        self.assertIn("headers present: X-Forwarded-For.", line)
        self.assertIn("X-Real-IP is missing, so the caller is read from X-Forwarded-For, entry 1 from the right (NUM_PROXIES=1): 84.17.x.x", line)
        self.assertIn("Outcome E", line)
        line = self.report("<b>junk</b>", f"{CALLER}, {EDGE}, {EDGE_2}", level="WARNING")
        self.assertIn("X-Real-IP is not an address", line)
        self.assertNotIn("junk", line)
        line = self.report(CALLER)
        self.assertIn("headers present: X-Real-IP. There is no X-Forwarded-For.", line)
        self.assertIn("Outcome F", line)

    def test_ipv6_and_a_header_sent_twice(self):
        line = self.report(f"203.0.113.99, {self.V6}", f"{self.V6}, {EDGE}")
        self.assertIn("X-Forwarded-For has 2 entries (2600:1700:x:x:x:x:x:x, 84.17.x.x).", line)
        self.assertIn("X-Real-IP arrived 2 times; the last value", line)
        self.assertIn("X-Real-IP (2600:1700:x:x:x:x:x:x) equals the FIRST entry", line)

    def test_other_address_headers_are_named_but_their_values_are_not_shown(self):
        line = self.report(EDGE, EDGE, HTTP_CF_CONNECTING_IP=CALLER, HTTP_X_RAILWAY_EDGE="railway/us-west2", HTTP_USER_AGENT="curl/8")
        self.assertIn("headers present: X-Real-IP, X-Forwarded-For, CF-Connecting-IP, X-Railway-Edge.", line)
        self.assertNotIn("us-west2", line)
        self.assertNotIn("curl", line)

    def test_after_the_settings_change_the_report_shows_what_is_read_now(self):
        with override_settings(CLIENT_IP_HEADER="", NUM_PROXIES=2):
            line = self.report(EDGE, f"{CALLER}, {EDGE}")
        self.assertIn("headers present: X-Real-IP, X-Forwarded-For.", line)
        self.assertIn("CLIENT_IP_HEADER is blank, so the caller is read from X-Forwarded-For, entry 2 from the right (NUM_PROXIES=2): 174.75.x.x", line)
        self.assertIn("Outcome G", line)

    def test_each_layout_is_reported_once(self):
        self.report(CALLER, f"{CALLER}, {EDGE}")
        with self.assertNoLogs("zeroharm.net", "INFO"):
            client_ip(_request("198.51.100.4", f"198.51.100.4, {EDGE_2}"))  # another caller, the same layout
            client_ip(_request())                                           # no proxy headers at all: nothing to say
        self.report(EDGE, f"{CALLER}, {EDGE}", level="WARNING")              # a new layout is still reported

    def test_no_more_than_a_handful_of_lines_per_process(self):
        chains = [", ".join([CALLER] * n) for n in range(1, 9)]
        with self.assertLogs("zeroharm.net", "INFO") as logs:
            for real_ip in (CALLER, EDGE, "203.0.113.99", "junk", f"{EDGE}, {CALLER}", None):
                for chain in chains + [None]:
                    client_ip(_request(real_ip, chain))
        self.assertEqual(len(logs.output), net.MAX_REPORTS)
        self.assertLessEqual(net.MAX_REPORTS, 8)
        self.assertIn("no more are written until the next restart", logs.output[-1])
        for line in logs.output:
            for whole in self.FULL:
                self.assertNotIn(whole, line)

    def test_a_long_chain_cannot_use_up_the_reports(self):
        with self.assertLogs("zeroharm.net", "INFO") as logs:
            for n in range(4, 40):  # 36 different lengths count as one layout
                client_ip(_request(CALLER, ", ".join([CALLER] + ["203.0.113.99"] * n + [EDGE])))
        self.assertEqual(len(logs.output), 1)
        self.assertIn("X-Forwarded-For has 6 entries (174.75.x.x, 203.0.x.x, 203.0.x.x, 203.0.x.x, 203.0.x.x, 84.17.x.x)", logs.output[0])
        net._seen_shapes.clear()
        with self.assertLogs("zeroharm.net", "INFO") as logs:
            client_ip(_request(CALLER, ", ".join([CALLER] + ["203.0.113.99"] * 20 + [EDGE])))
        self.assertIn("X-Forwarded-For has 22 entries (174.75.x.x, 203.0.x.x, 203.0.x.x, 203.0.x.x, 203.0.x.x, 203.0.x.x and 16 more)", logs.output[0])

    def test_the_file_explains_every_outcome_the_line_can_name(self):
        text = Path(net.__file__).read_text()
        for letter in "ABCDEFG":
            self.assertIn(f"Outcome {letter}", text)   # the line names it
            self.assertIn(f"\n{letter}. ", text)       # and the top of the file says what to set for it
        self.assertIn("CLIENT_IP_HEADER to blank and NUM_PROXIES", text)


class NetworkKeyTests(SimpleTestCase):
    def test_ipv4_is_the_address(self):
        self.assertEqual(network_key("203.0.113.7"), "203.0.113.7")
        self.assertNotEqual(network_key("203.0.113.7"), network_key("203.0.113.8"))

    def test_ipv6_is_grouped_by_its_64(self):
        one = network_key("2001:db8:aa:bb:1111:2222:3333:4444")
        self.assertEqual(one, "2001:db8:aa:bb::/64")
        self.assertEqual(network_key("2001:db8:aa:bb::9"), one)                 # same connection, another address
        self.assertEqual(network_key("2001:DB8:00AA:00BB:ffff:ffff:ffff:ffff"), one)
        self.assertNotEqual(network_key("2001:db8:aa:bc::9"), one)              # the next /64 is someone else

    def test_takes_a_request_or_an_address(self):
        self.assertEqual(network_key(_request(CALLER, f"{CALLER}, {EDGE}")), CALLER)
        self.assertEqual(network_key(_request("2001:db8:aa:bb::5", f"2001:db8:aa:bb::5, {EDGE}")), "2001:db8:aa:bb::/64")
        self.assertEqual(network_key("::ffff:203.0.113.7"), "203.0.113.7")

    def test_no_address_is_one_shared_key(self):
        self.assertEqual(network_key("garbage"), "unknown")
        self.assertEqual(network_key(""), "unknown")
        self.assertEqual(network_key(_request("", "", remote="")), "unknown")


class ScopedThrottleTests(SimpleTestCase):
    def setUp(self):
        caches["limits"].clear()

    def test_two_scopes_do_not_share_a_counter(self):
        a, b = ScopedThrottle("2/h", scope="feedback"), ScopedThrottle("2/h", scope="comments")
        request = _request(CALLER, f"{CALLER}, {EDGE}")
        self.assertEqual([a.allow_request(request) for _ in range(3)], [True, True, False])
        self.assertEqual([b.allow_request(request) for _ in range(3)], [True, True, False])  # untouched by a's calls
        self.assertNotEqual(a.get_cache_key(request), b.get_cache_key(request))

    def test_counts_the_caller_not_the_edge_hop(self):
        limit = ScopedThrottle("2/h", scope="one")
        # One caller arriving through three edge addresses is still one caller.
        seen = [limit.allow_request(_request(CALLER, f"{CALLER}, 84.17.44.{n}")) for n in (225, 226, 227)]
        self.assertEqual(seen, [True, True, False])
        # Another caller behind the very same edge address has their own allowance.
        self.assertTrue(limit.allow_request(_request("198.51.100.4", "198.51.100.4, 84.17.44.225")))

    def test_ipv6_addresses_in_one_64_share_the_allowance(self):
        limit = ScopedThrottle("2/h", scope="v6")
        seen = [limit.allow_request(_request(f"2001:db8:aa:bb::{n}")) for n in (1, 2, 3)]
        self.assertEqual(seen, [True, True, False])
        self.assertTrue(limit.allow_request(_request("2001:db8:aa:cc::1")))

    def test_cache_key_holds_no_address(self):
        for ip, parts in ((CALLER, [CALLER, "174.75"]), ("2001:db8:aa:bb::1", ["2001", "db8:aa"])):
            key = ScopedThrottle("2/h", scope="feedback").get_cache_key(_request(ip, f"{ip}, {EDGE}"))
            self.assertTrue(key.startswith("throttle:feedback:"), key)
            for part in parts + [EDGE, "/64"]:
                self.assertNotIn(part, key)
        # Stable: the same network gives the same key, so the count holds from one request to the next.
        self.assertEqual(ScopedThrottle("2/h", scope="s").get_cache_key(_request(CALLER)),
                         ScopedThrottle("9/m", scope="s").get_cache_key(_request(CALLER)))

    def test_scope_is_required(self):
        with self.assertRaises(TypeError):
            ScopedThrottle("2/h")
        for bad in ("", "  ", None):
            with self.assertRaises(ImproperlyConfigured):
                ScopedThrottle("2/h", scope=bad)

    @WITH_TEST_URLS
    def test_on_real_endpoints(self):
        post = lambda path, ip: self.client.post(path, HTTP_X_REAL_IP=ip, HTTP_X_FORWARDED_FOR=f"{ip}, {EDGE}").status_code
        self.assertEqual([post("/api/fix-core/limited-a", CALLER) for _ in range(3)], [200, 200, 429])
        self.assertEqual(post("/api/fix-core/limited-b", CALLER), 200)          # the other endpoint's own counter
        self.assertEqual(post("/api/fix-core/limited-a", "198.51.100.4"), 200)  # another caller, same edge address


# ---- The cache that holds only counters ----------------------------------------------------------------------------

class LimitsCacheTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        caches["limits"].clear()

    def test_it_is_its_own_store_with_room_for_100_000_counters(self):
        self.assertIsInstance(caches["limits"], LocMemCache)
        self.assertGreaterEqual(caches["limits"]._max_entries, 100_000)
        caches["limits"].set("only-in-limits", 1, 60)
        cache.set("only-in-default", 1, 60)
        self.assertIsNone(cache.get("only-in-limits"))
        self.assertIsNone(caches["limits"].get("only-in-default"))
        cache.clear()  # emptying the content cache leaves the counters alone
        self.assertEqual(caches["limits"].get("only-in-limits"), 1)

    def test_throttle_counts_are_kept_there(self):
        limit, request = ScopedThrottle("2/h", scope="where"), _request(CALLER, f"{CALLER}, {EDGE}")
        self.assertTrue(limit.allow_request(request))
        key = limit.get_cache_key(request)
        self.assertEqual(len(caches["limits"].get(key)), 1)
        self.assertIsNone(cache.get(key))

    def test_filling_the_content_cache_does_not_start_a_limit_again(self):
        # The weather finding: 300 cached lookups pushed the counters out, and a used-up limit was fresh again.
        limit, request = ScopedThrottle("2/h", scope="evict"), _request(CALLER, f"{CALLER}, {EDGE}")
        self.assertEqual([limit.allow_request(request) for _ in range(3)], [True, True, False])
        for n in range(1000):
            cache.set(f"wx:{n}", {"temp": n}, 600)
        self.assertFalse(limit.allow_request(request))

    def test_thousands_of_other_callers_do_not_start_a_limit_again(self):
        # The second checker's way round: one call each from many networks. 330 were enough before.
        limit, request = ScopedThrottle("2/h", scope="crowd"), _request(CALLER, f"{CALLER}, {EDGE}")
        self.assertEqual([limit.allow_request(request) for _ in range(3)], [True, True, False])
        for n in range(3000):
            self.assertTrue(limit.allow_request(_request(f"2001:db8:{n:x}:1::7")))
        self.assertFalse(limit.allow_request(request))

    def test_the_shared_cache_has_room_too(self):
        self.assertGreaterEqual(caches["shared"]._max_entries, 100_000)


class CountersDoNotLeakBetweenTestsTests(SimpleTestCase):
    """Neither test empties a cache: the test runner (zeroharm/testing.py) empties the counters before each one.
    Both use up the same limit, so whichever runs second fails if the first one's count is still there."""

    def use_up_the_limit(self):
        limit, request = ScopedThrottle("1/h", scope="leak"), _request(CALLER, f"{CALLER}, {EDGE}")
        self.assertEqual([limit.allow_request(request) for _ in range(2)], [True, False])

    test_one = use_up_the_limit
    test_two = use_up_the_limit

    def test_the_runner_is_the_one_in_settings(self):
        self.assertEqual(settings.TEST_RUNNER, "zeroharm.testing.Runner")


class MondayTimingSettingsTests(SimpleTestCase):
    """MONDAY_STEP_BUDGET and LOCAL_AI_FAST_TIMEOUT were read by the monday code but were not settings, so setting
    them on Railway changed nothing."""

    def load_settings(self, **environment):
        """settings.py run afresh with these environment variables, as a new process would read it."""
        clean = {k: v for k, v in os.environ.items() if k not in ("MONDAY_STEP_BUDGET", "LOCAL_AI_FAST_TIMEOUT")}
        with mock.patch.dict(os.environ, {**clean, "DJANGO_DEBUG": "1", **environment}, clear=True):
            return runpy.run_path(str(Path(settings.BASE_DIR, "zeroharm", "settings.py")))

    def test_defaults(self):
        fresh = self.load_settings()
        self.assertEqual((fresh["MONDAY_STEP_BUDGET"], fresh["LOCAL_AI_FAST_TIMEOUT"]), (1800.0, 180.0))
        self.assertIsInstance(settings.MONDAY_STEP_BUDGET, float)   # real settings: no getattr with a default needed
        self.assertIsInstance(settings.LOCAL_AI_FAST_TIMEOUT, float)

    def test_both_are_read_from_the_environment(self):
        fresh = self.load_settings(MONDAY_STEP_BUDGET="7", LOCAL_AI_FAST_TIMEOUT="9.5")
        self.assertEqual((fresh["MONDAY_STEP_BUDGET"], fresh["LOCAL_AI_FAST_TIMEOUT"]), (7.0, 9.5))

    def test_both_are_listed_in_the_example_file(self):
        example = Path(settings.BASE_DIR, ".env.example").read_text()
        self.assertIn("\nMONDAY_STEP_BUDGET=1800\n", example)
        self.assertIn("\nLOCAL_AI_FAST_TIMEOUT=180\n", example)


# ---- Logging -------------------------------------------------------------------------------------------------------

@contextmanager
def _written_by(logger_name):
    """Everything the configured handlers would write for a record logged on `logger_name`, as one string buffer."""
    handlers, logger = [], logging.getLogger(logger_name)
    while logger:
        handlers += [h for h in logger.handlers if isinstance(h, logging.StreamHandler)]
        logger = logger.parent if logger.propagate else None
    out = io.StringIO()
    before = [h.setStream(out) for h in handlers]
    try:
        yield out
    finally:
        for handler, stream in zip(handlers, before):
            handler.setStream(stream)


class LoggingTests(SimpleTestCase):
    def test_settings_define_logging_once(self):
        tree = ast.parse(Path(settings.BASE_DIR, "zeroharm", "settings.py").read_text())
        assigned = [n for n in ast.walk(tree) if isinstance(n, ast.Assign) and any(getattr(t, "id", "") == "LOGGING" for t in n.targets)]
        self.assertEqual(len(assigned), 1, "a second LOGGING block replaces the first")
        self.assertIs(settings.LOGGING["disable_existing_loggers"], False)
        self.assertEqual(settings.LOGGING["root"]["level"], "INFO")

    def test_djangos_own_loggers_are_left_on(self):
        for name in ("django", "django.request", "django.server", "django.security"):
            self.assertFalse(logging.getLogger(name).disabled, name)

    @WITH_TEST_URLS
    def test_unhandled_error_in_a_view_is_logged_with_its_traceback(self):
        with _written_by("django.request") as out:
            response = Client(raise_request_exception=False).get("/api/boom/")
        self.assertEqual(response.status_code, 500)
        written = out.getvalue()
        self.assertIn("ERROR django.request: Internal Server Error: /api/boom/", written)  # level and logger name
        self.assertIn("Traceback (most recent call last)", written)
        self.assertIn("RuntimeError: kaboom in a view", written)
        self.assertEqual(written.count("Internal Server Error"), 1)  # once, not once per handler

    def test_app_loggers_write_at_info_with_level_and_name(self):
        with _written_by("talks.console") as out:
            logging.getLogger("talks.console").info("Console: saved %s", "talk 3")
        self.assertEqual(out.getvalue(), "INFO talks.console: Console: saved talk 3\n")

    def test_gunicorns_loggers_survive_django_starting(self):
        # gunicorn makes its two loggers, with their handlers, before the worker loads Django. Do the same, then
        # configure logging the way django.setup() does.
        error_log, access_log = logging.getLogger("gunicorn.error"), logging.getLogger("gunicorn.access")
        error_out = io.StringIO()
        error_handler = logging.StreamHandler(error_out)
        for logger in (error_log, access_log):
            logger.propagate = False
            logger.setLevel(logging.INFO)
        error_log.addHandler(error_handler)
        self.addCleanup(error_log.removeHandler, error_handler)
        access_log.addHandler(logging.StreamHandler(sys.stdout))

        configure_logging(settings.LOGGING_CONFIG, settings.LOGGING)

        self.assertFalse(error_log.disabled)
        self.assertFalse(access_log.disabled)
        error_log.info("Booting worker with pid: 7")
        self.assertIn("Booting worker with pid: 7", error_out.getvalue())  # gunicorn's own handler still attached
        self.assertEqual(len(access_log.handlers), 1)

    def test_access_log_lines_come_out_without_the_query_string(self):
        from gunicorn.glogging import SafeAtoms  # what gunicorn passes to its access logger

        atoms = SafeAtoms({"h": "10.250.0.9", "l": "-", "u": "-", "t": "[12/Nov/2026:01:27:08 +0000]", "s": 200, "b": 512,
                           "r": "GET /backoffice/?key=the-back-office-key&tab=2 HTTP/1.1", "q": "key=the-back-office-key&tab=2",
                           "f": "https://example.test/backoffice/?key=the-back-office-key", "a": "Mozilla/5.0"})
        with _written_by("gunicorn.access") as out:
            logging.getLogger("gunicorn.access").info('%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(q)s', atoms)
        self.assertEqual(out.getvalue(), '10.250.0.9 - - [12/Nov/2026:01:27:08 +0000] "GET /backoffice/ HTTP/1.1" 200 512 '
                                         '"https://example.test/backoffice/" "Mozilla/5.0" -\n')
        with _written_by("gunicorn.access") as out:  # a line with no query string is written as it is
            logging.getLogger("gunicorn.access").info('"%(r)s" %(s)s', SafeAtoms({"r": "GET /api/health/ HTTP/1.1", "s": 200}))
        self.assertEqual(out.getvalue(), '"GET /api/health/ HTTP/1.1" 200\n')

    def test_a_referer_with_a_space_in_its_query_string_is_cut_whole(self):
        from gunicorn.glogging import SafeAtoms

        atoms = SafeAtoms({"r": "GET /backoffice/?key=the-back-office-key HTTP/1.1", "s": 200,
                           "f": "http://x.test/?a=1 key=THE-VALUE and more", "{referer}i": "http://x.test/?a=1 key=THE-VALUE and more"})
        with _written_by("gunicorn.access") as out:
            logging.getLogger("gunicorn.access").info('"%(r)s" %(s)s "%(f)s" "%({referer}i)s"', atoms)
        self.assertEqual(out.getvalue(), '"GET /backoffice/ HTTP/1.1" 200 "http://x.test/" "http://x.test/"\n')
        # A request line keeps only its last word after the query string, even with a space in between.
        atoms = SafeAtoms({"r": "GET /get/?c=contact-id&x=1 y=SECRET HTTP/1.1"})
        with _written_by("gunicorn.access") as out:
            logging.getLogger("gunicorn.access").info('"%(r)s"', atoms)
        self.assertEqual(out.getvalue(), '"GET /get/ HTTP/1.1"\n')


# ---- API errors as JSON --------------------------------------------------------------------------------------------

@WITH_TEST_URLS
class ApiErrorTests(TestCase):
    def setUp(self):
        self.client = Client(raise_request_exception=False)

    def assertJsonError(self, response, status, message):
        self.assertEqual(response.status_code, status)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertEqual(response.json(), {"error": message})
        self.assertEqual(int(response["Content-Length"]), len(response.content))

    def test_unknown_address_is_json_404(self):
        self.assertJsonError(self.client.get("/api/no-such-thing/"), 404, "Not found.")
        self.assertJsonError(self.client.get("/api/talks/abc/"), 404, "Not found.")
        self.assertJsonError(self.client.get("/api/v2/no-such-thing"), 404, "Not found.")

    def test_wrong_method_is_json_405_and_keeps_allow(self):
        response = self.client.get("/api/signups/")
        self.assertJsonError(response, 405, "Method not allowed.")
        self.assertEqual(response["Allow"], "POST")
        self.assertJsonError(self.client.get("/api/fix-core/limited-a"), 405, "Method not allowed.")  # Django Ninja's

    def test_crash_is_json_500_and_still_logged(self):
        with self.assertLogs("django.request", "ERROR") as logs:
            self.assertJsonError(self.client.get("/api/boom/"), 500, "Something went wrong on the server.")
        self.assertIn("kaboom", logs.output[0])  # the traceback is in the log, not in the answer

    def test_refused_csrf_check_is_json_403(self):
        strict = Client(enforce_csrf_checks=True)
        with self.assertLogs("django.security.csrf", "WARNING"):
            self.assertJsonError(strict.post("/api/needs-csrf/", {"a": 1}), 403, "Not allowed.")

    def test_bad_request_is_json_400(self):
        with self.assertLogs("django.security.SuspiciousOperation", "ERROR"):
            self.assertJsonError(self.client.get("/api/suspicious/"), 400, "Bad request.")

    def test_other_non_json_errors_get_the_shape_too(self):
        self.assertJsonError(self.client.get("/api/teapot/"), 418, "The request failed.")

    def test_head_gets_no_body(self):
        response = self.client.head("/api/no-such-thing/")
        self.assertEqual((response.status_code, response.content, response["Content-Length"]), (404, b"", "0"))

    def test_errors_the_views_shape_themselves_are_left_alone(self):
        response = self.client.get("/api/talks/987654/")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"error": "This talk isn’t available yet."})

    def test_working_answers_are_left_alone(self):
        self.assertEqual(self.client.get("/api/health/").json(), {"ok": True})

    def test_pages_outside_the_api_keep_djangos_html(self):
        response = self.client.get("/no-such-page/")
        self.assertEqual(response.status_code, 404)
        self.assertTrue(response["Content-Type"].startswith("text/html"))
        self.assertIn(b"Not Found", response.content)
        with self.assertLogs("django.request", "ERROR"):
            response = self.client.get("/boom/")
        self.assertEqual(response.status_code, 500)
        self.assertTrue(response["Content-Type"].startswith("text/html"))
        strict = Client(enforce_csrf_checks=True)
        with self.assertLogs("django.security.csrf", "WARNING"):
            response = strict.post("/admin/login/", {"username": "a", "password": "b"})
        self.assertEqual(response.status_code, 403)
        self.assertTrue(response["Content-Type"].startswith("text/html"))


# ---- Admin sign-in limit -------------------------------------------------------------------------------------------

PASSWORD = "correct horse battery staple"


class SlowCache(LocMemCache):
    """An in-memory cache whose reads take a moment, as a database's do, so threads really do get in between one
    request's read of a count and its write. Threads cannot use the real one: it is inside the test's transaction."""

    def get(self, *args, **kwargs):
        time.sleep(0.001)
        return super().get(*args, **kwargs)
PLAIN_STATIC = {"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
                "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}}


# The sign-in page links its stylesheet and tests have no collected static files. The quick password hasher is only
# to keep the hundred-odd sign-ins below fast; what is tested is the counting, not the hashing.
@override_settings(STORAGES=PLAIN_STATIC, PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class AdminLoginLimitTests(TestCase):
    def setUp(self):
        caches["shared"].clear()
        get_user_model().objects.create_superuser("owner", "owner@example.test", PASSWORD)

    def sign_in(self, ip, password=PASSWORD, username="owner", edge=EDGE):
        """One POST to the sign-in page from `ip`, through a fresh browser. 302 = signed in, 200 = wrong, 429 = refused."""
        return Client().post("/admin/login/", {"username": username, "password": password, "next": "/admin/"},
                             HTTP_X_REAL_IP=ip, HTTP_X_FORWARDED_FOR=f"{ip}, {edge}")

    def seconds_left(self):
        """How long each sign-in count has left before it runs out, read from the cache table itself."""
        with connection.cursor() as cursor:
            cursor.execute("SELECT cache_key, expires FROM zeroharm_cache WHERE cache_key LIKE %s", ["%admin-login:%"])
            rows = cursor.fetchall()
        left = {}
        for key, expires in rows:
            if isinstance(expires, str):  # SQLite hands the column back as text
                expires = parse_datetime(expires)
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            left[key] = (expires - datetime.now(timezone.utc)).total_seconds()
        return left

    @contextmanager
    def later(self, seconds):
        """Runs the block with every clock the limit depends on moved on by `seconds`: Python's, and the one the
        database cache uses to decide whether a row has run out."""
        real_time, real_now = time.time, datetime.now
        with mock.patch("time.time", lambda: real_time() + seconds), \
                mock.patch("django.core.cache.backends.db.tz_now", lambda: real_now(timezone.utc) + timedelta(seconds=seconds)):
            yield

    def test_right_password_signs_in(self):
        self.assertEqual(self.sign_in(CALLER).status_code, 302)

    def test_counts_still_have_their_hour_after_several_failures(self):
        # Django's database cache saved a count again for 5 minutes each time it was added to, so from the second
        # failure on the "hour" was five minutes.
        for _ in range(4):
            self.assertEqual(self.sign_in(CALLER, "wrong").status_code, 200)
        left = self.seconds_left()
        self.assertEqual(len(left), 3)  # network, username, and the pair
        for key, seconds in left.items():
            self.assertGreater(seconds, ADMIN_LOGIN_WINDOW - 60, key)
            self.assertLessEqual(seconds, ADMIN_LOGIN_WINDOW, key)

    def test_the_hour_starts_with_the_first_failure_and_later_ones_do_not_move_it(self):
        self.sign_in(CALLER, "wrong")
        first = self.seconds_left()
        with self.later(1800):
            for _ in range(3):
                self.sign_in(CALLER, "wrong")
        after = self.seconds_left()
        self.assertEqual(first.keys(), after.keys())
        for key in first:  # the rows still run out an hour after the first failure, not later and not sooner
            self.assertAlmostEqual(first[key], after[key], delta=5)

    def test_a_refused_network_is_still_refused_six_minutes_later_and_free_after_the_hour(self):
        for n in range(10):
            self.assertEqual(self.sign_in(CALLER, "wrong", username=f"guess{n}").status_code, 200)
        self.assertEqual(self.sign_in(CALLER).status_code, 429)
        for minutes in (6, 30, 59):
            with self.later(minutes * 60):
                self.assertEqual(self.sign_in(CALLER).status_code, 429, f"{minutes} minutes on")
        with self.later(61 * 60):
            self.assertEqual(self.sign_in(CALLER, "wrong").status_code, 200)  # a new hour, counted from one again
            self.assertEqual(self.sign_in(CALLER).status_code, 302)

    def test_a_username_under_attack_is_still_guarded_six_minutes_later(self):
        for n in range(10):
            self.assertEqual(self.sign_in(f"203.0.113.{n + 1}", "wrong").status_code, 200)
        fresh = "198.51.100.77"
        self.assertEqual([self.sign_in(fresh, "wrong").status_code for _ in range(3)], [200, 200, 200])
        with self.later(6 * 60):
            self.assertEqual(self.sign_in(fresh).status_code, 429)

    def test_a_sign_in_that_works_is_not_left_counted(self):
        for _ in range(12):  # counted before the password is checked, and taken off again when it is right
            self.assertEqual(self.sign_in(CALLER).status_code, 302)
        self.assertEqual(self.seconds_left(), {})
        for n in range(9):
            self.assertEqual(self.sign_in(CALLER, "wrong", username=f"guess{n}").status_code, 200)
        self.assertEqual(self.sign_in(CALLER).status_code, 302)                        # the tenth try, and it is right
        self.assertEqual(self.sign_in(CALLER, "wrong", username="guess9").status_code, 200)  # so this is failure ten
        self.assertEqual(self.sign_in(CALLER).status_code, 429)

    def test_a_request_turned_away_before_the_password_is_looked_at_is_not_counted(self):
        strict = Client(enforce_csrf_checks=True)
        with self.assertLogs("django.security.csrf", "WARNING"):
            for _ in range(12):  # no CSRF token: 403 from Django, the password never checked
                self.assertEqual(strict.post("/admin/login/", {"username": "owner", "password": "wrong"}, HTTP_X_REAL_IP=CALLER).status_code, 403)
        self.assertEqual(self.seconds_left(), {})
        self.assertEqual(self.sign_in(CALLER).status_code, 302)

    def test_a_burst_of_guesses_at_the_same_moment_is_stopped_at_ten(self):
        # Counting only after the password check let every guess that arrived during the first checks through:
        # 23 of 40 on the real server. The fake check below waits long enough for all 40 to be inside at once.
        checked = []

        def check_password(request):
            checked.append(request)
            time.sleep(0.1)
            return HttpResponse("the form again", status=200)

        limit = AdminLoginLimitMiddleware(check_password)
        limit.limits = SlowCache("fix-core-burst", {})
        limit.limits.clear()
        answers = []

        def guess(n):
            request = RequestFactory().post("/admin/login/", {"username": f"guess{n}", "password": "wrong"},
                                            HTTP_X_REAL_IP=CALLER, HTTP_X_FORWARDED_FOR=f"{CALLER}, {EDGE}")
            answers.append(limit(request).status_code)

        threads = [threading.Thread(target=guess, args=(n,)) for n in range(40)]
        with self.assertLogs("zeroharm.middleware", "WARNING"):
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
        self.assertEqual(len(checked), ADMIN_LOGIN_MAX_FAILURES)
        self.assertEqual(sorted(answers), [200] * 10 + [429] * 30)

    def test_a_burst_of_right_passwords_leaves_nothing_counted(self):
        def signs_in(request):
            time.sleep(0.05)
            return HttpResponse(status=302)

        limit = AdminLoginLimitMiddleware(signs_in)
        limit.limits = SlowCache("fix-core-burst-ok", {})
        limit.limits.clear()
        post = lambda: limit(RequestFactory().post("/admin/login/", {"username": "owner", "password": PASSWORD}, HTTP_X_REAL_IP=CALLER))
        threads = [threading.Thread(target=post) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(limit._count(limit._key("net", CALLER)), 0)
        self.assertEqual(limit._count(limit._key("user", "owner")), 0)
        self.assertEqual(post().status_code, 302)

    def test_look_alike_spellings_of_a_username_share_its_count(self):
        # Django reads the full-width "ｏwner" as "owner" (NFKC) and signs that account in, so it is the same username.
        self.assertEqual(self.sign_in("198.51.100.9", username="ｏｗｎｅｒ").status_code, 302)
        for n in range(10):
            self.assertEqual(self.sign_in(f"203.0.113.{n + 1}", "wrong").status_code, 200)
        fresh = "198.51.100.77"
        self.assertEqual([self.sign_in(fresh, "wrong", username="ｏwner").status_code for _ in range(4)], [200, 200, 200, 429])
        self.assertEqual(self.sign_in(fresh, "wrong", username="ＯＷＮＥＲ").status_code, 429)

    def test_many_networks_guessing_do_not_push_counts_or_notes_out_of_the_shared_cache(self):
        # Django's database cache keeps 300 rows unless told otherwise; past that it deletes the lowest third by key,
        # run out or not. A wrong sign-in writes three rows, so 100 guessers emptied the network counts and anything
        # else that sorted first, such as the cron's "already sent" notes.
        caches["shared"].set("0-already-sent", "yes", 14 * 24 * 3600)
        limit = AdminLoginLimitMiddleware(lambda request: HttpResponse("the form again", status=200))
        for n in range(120):
            limit(RequestFactory().post("/admin/login/", {"username": f"guess{n}", "password": "wrong"}, HTTP_X_REAL_IP=f"203.0.113.{n + 1}"))
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM zeroharm_cache")
            self.assertEqual(cursor.fetchone()[0], 361)
        self.assertEqual(caches["shared"].get("0-already-sent"), "yes")
        self.assertEqual([limit._count(limit._key("net", f"203.0.113.{n + 1}")) for n in range(120)], [1] * 120)

    def test_a_count_left_in_the_old_form_is_read_as_no_count(self):
        # Before this fix a count was a bare number; one left in the table must not break the sign-in page.
        caches["shared"].set(AdminLoginLimitMiddleware._key("net", CALLER), 10, 300)
        self.assertEqual(self.sign_in(CALLER, "wrong").status_code, 200)
        self.assertEqual(self.sign_in(CALLER).status_code, 302)

    def test_ten_failures_from_one_network_refuse_that_network_for_the_hour(self):
        for n in range(10):  # ten different usernames, so only the network count is in play
            self.assertEqual(self.sign_in(CALLER, "wrong", username=f"guess{n}").status_code, 200)
        refused = self.sign_in(CALLER, "wrong", username="guess10")
        self.assertEqual(refused.status_code, 429)
        self.assertEqual(refused.content.decode(), ADMIN_LOGIN_REFUSED)
        self.assertTrue(refused["Content-Type"].startswith("text/plain"))
        self.assertEqual(self.sign_in(CALLER).status_code, 429)          # even the right password, from that network
        self.assertEqual(self.sign_in("198.51.100.4").status_code, 302)  # the owner, elsewhere, is not affected

    def test_the_network_is_the_caller_not_the_edge_address(self):
        for n in range(10):
            self.assertEqual(self.sign_in(CALLER, "wrong", username=f"guess{n}", edge=f"84.17.44.{225 + n % 5}").status_code, 200)
        self.assertEqual(self.sign_in(CALLER, edge="84.17.44.230").status_code, 429)  # a new edge address is no way out
        self.assertEqual(self.sign_in("198.51.100.4", edge=EDGE).status_code, 302)    # sharing an edge address is no lockout

    def test_ipv6_addresses_in_one_64_are_one_network(self):
        for n in range(10):
            self.assertEqual(self.sign_in(f"2001:db8:aa:bb::{n + 1}", "wrong", username=f"guess{n}").status_code, 200)
        self.assertEqual(self.sign_in("2001:db8:aa:bb:ffff::1").status_code, 429)
        self.assertEqual(self.sign_in("2001:db8:aa:cc::1").status_code, 302)

    def test_failures_on_a_username_never_lock_out_the_right_password_from_another_network(self):
        for n in range(25):  # someone guessing at "owner" from 25 networks, far past the username count of 10
            self.assertEqual(self.sign_in(f"203.0.113.{n + 1}", "wrong").status_code, 200)
        self.assertEqual(self.sign_in("198.51.100.4").status_code, 302)  # the owner, from a network that has not failed

    def test_a_username_under_attack_gives_each_network_three_wrong_tries(self):
        for n in range(10):
            self.assertEqual(self.sign_in(f"203.0.113.{n + 1}", "wrong").status_code, 200)
        fresh = "198.51.100.77"
        self.assertEqual([self.sign_in(fresh, "wrong").status_code for _ in range(4)], [200, 200, 200, 429])
        self.assertEqual(self.sign_in(fresh).status_code, 429)             # that network used up its own three tries
        self.assertEqual(self.sign_in("203.0.113.1", "wrong").status_code, 200)  # an attacking network: tries 2 and 3
        self.assertEqual(self.sign_in("203.0.113.1", "wrong").status_code, 200)
        self.assertEqual(self.sign_in("203.0.113.1", "wrong").status_code, 429)
        # A username nobody is attacking still gets the normal ten from that same fresh network... which the network
        # count then stops: it has 3 failures already, so 7 more are let through and the next is refused.
        seen = [self.sign_in(fresh, "wrong", username="someone-else").status_code for _ in range(8)]
        self.assertEqual(seen, [200] * 7 + [429])

    def test_username_count_ignores_case_and_spaces(self):
        for n in range(10):
            self.assertEqual(self.sign_in(f"203.0.113.{n + 1}", "wrong", username=" OWNER ").status_code, 200)
        fresh = "198.51.100.77"
        self.assertEqual([self.sign_in(fresh, "wrong").status_code for _ in range(4)], [200, 200, 200, 429])

    def test_opening_the_page_is_never_counted_or_refused(self):
        for _ in range(12):
            self.assertEqual(Client().get("/admin/login/", HTTP_X_REAL_IP=CALLER).status_code, 200)
        self.assertEqual(self.sign_in(CALLER).status_code, 302)
        for n in range(10):
            self.sign_in(CALLER, "wrong", username=f"guess{n}")
        self.assertEqual(Client().get("/admin/login/", HTTP_X_REAL_IP=CALLER).status_code, 200)  # the page still opens

    def test_counts_are_kept_in_the_shared_cache_without_addresses_or_usernames(self):
        for _ in range(3):
            self.sign_in(CALLER, "wrong")
        with connection.cursor() as cursor:
            cursor.execute("SELECT cache_key FROM zeroharm_cache")
            keys = [row[0] for row in cursor.fetchall()]
        self.assertEqual(len([k for k in keys if "admin-login:" in k]), 3)  # network, username, and the pair
        for key in keys:
            self.assertNotIn(CALLER, key)
            self.assertNotIn("owner", key)

    def test_the_command_in_the_instructions_writes_the_line(self):
        # net.py tells the owner to run: curl -X POST https://<domain>/admin/login/. That has no CSRF token, so it
        # answers 403, and it must still reach the code that reads the caller.
        net._seen_shapes.clear()
        self.addCleanup(net._seen_shapes.clear)
        with self.assertLogs("zeroharm.net", "INFO") as logs, self.assertLogs("django.security.csrf", "WARNING"):
            response = Client(enforce_csrf_checks=True).post("/admin/login/", HTTP_X_REAL_IP=CALLER, HTTP_X_FORWARDED_FOR=f"{CALLER}, {EDGE}")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(len(logs.output), 1)
        self.assertIn("equals the FIRST entry", logs.output[0])

    def test_reaching_the_limit_is_logged_once(self):
        with self.assertLogs("zeroharm.middleware", "WARNING") as logs:
            for n in range(12):
                self.sign_in(CALLER, "wrong", username=f"guess{n}")
        self.assertEqual(len(logs.output), 1)
        self.assertIn(CALLER, logs.output[0])
