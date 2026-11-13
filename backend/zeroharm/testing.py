"""How the test suite runs (TEST_RUNNER in settings.py). Only `manage.py test` loads this; the web server and the
cron never do."""
import unittest

from django.core.cache import caches
from django.test.runner import DiscoverRunner


class FreshCounters:
    """Empties the "limits" cache before every test.

    Rate-limit and lockout counters sit in memory, in a cache of their own. Django rolls the database back between
    tests but leaves caches as they are, so a limit one test used up would refuse the first request of the next
    test. The cache.clear() most test files call in setUp empties only the default cache, which was enough while the
    counters lived there. Doing it here keeps every test starting from zero without each file having to know."""

    def startTest(self, test):
        caches["limits"].clear()
        super().startTest(test)


class Runner(DiscoverRunner):
    def get_resultclass(self):
        # Django names a result class of its own for --debug-sql and --pdb; keep whichever it is and add the step.
        base = super().get_resultclass() or unittest.TextTestResult
        return type(f"FreshCounters{base.__name__}", (FreshCounters, base), {})
