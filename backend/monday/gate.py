"""The safety gate: a Monday Minute only publishes on its own if the AI setup writing and reviewing it has passed the
safety test (catches planted mistakes, leaves good talks alone). Otherwise the talk is still written and checked, then
waits in the admin for a person to approve it.

"The AI setup" is the reviewer model plus whether RAG and the strict double review are on: change any of them and the
setup has to pass the test again. The bar is in settings (MONDAY_GATE_*).
"""
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from .ai import is_local
from .models import MondayEvalRun


@dataclass
class Gate:
    ok: bool
    reason: str
    run: MondayEvalRun | None = None


def reviewer_model() -> str:
    return f"local:{settings.LOCAL_AI_REVIEW_MODEL or settings.LOCAL_AI_MODEL}" if is_local() else settings.MONDAY_MODEL


def setup() -> dict:
    """What the pass applies to."""
    return {"model": reviewer_model(), "rag": settings.MONDAY_RAG, "strict": is_local()}


def score(result: dict) -> dict:
    """Catch rate, wrong-block rate and failed calls from one safety_eval.run() result."""
    planted = sum(p["n"] for p in result.get("plants", {}).values())
    caught = sum(p["caught"] for p in result.get("plants", {}).values())
    good = result.get("good", {})
    cases = planted + good.get("n", 0)
    errors = result.get("errors", 0)
    return {
        "planted": planted,
        "catch_rate": caught / planted if planted else None,
        "false_block_rate": good.get("blocked", 0) / good["n"] if good.get("n") else None,
        "error_rate": errors / (cases + errors) if cases + errors else None,
    }


def judge(result: dict) -> tuple[bool, str]:
    """(passed, why) for one run of the configured mode, against the bar in settings."""
    s = score(result)
    if s["planted"] < settings.MONDAY_GATE_MIN_CASES:
        return False, f"only {s['planted']} planted mistakes were tested; {settings.MONDAY_GATE_MIN_CASES} needed"
    if s["error_rate"] is not None and s["error_rate"] > settings.MONDAY_GATE_MAX_ERRORS:
        return False, f"{s['error_rate']:.0%} of calls failed, so the result isn't reliable"
    if s["catch_rate"] < settings.MONDAY_GATE_MIN_CATCH:
        return False, f"caught {s['catch_rate']:.0%} of planted mistakes; {settings.MONDAY_GATE_MIN_CATCH:.0%} needed"
    if s["false_block_rate"] is None:
        return False, "no good talks were tested"
    if s["false_block_rate"] > settings.MONDAY_GATE_MAX_FALSE_BLOCK:
        return False, f"wrongly blocked {s['false_block_rate']:.0%} of good talks; at most {settings.MONDAY_GATE_MAX_FALSE_BLOCK:.0%} allowed"
    return True, f"caught {s['catch_rate']:.0%} of planted mistakes and wrongly blocked {s['false_block_rate']:.0%} of good talks"


def status() -> Gate:
    """Whether the current AI setup may publish on its own. The latest finished test of this exact setup decides."""
    if not settings.MONDAY_GATE:
        return Gate(True, "the safety gate is off (MONDAY_GATE=0)")
    want = setup()
    since = timezone.now() - timedelta(days=settings.MONDAY_GATE_MAX_AGE_DAYS)
    run = (MondayEvalRun.objects.filter(status="done", model=want["model"], rag=want["rag"], strict=want["strict"], finished_at__gte=since)
           .order_by("-finished_at").first())
    if run is None:
        return Gate(False, f"{want['model']} hasn't passed the safety test with this setup in the last {settings.MONDAY_GATE_MAX_AGE_DAYS} days")
    if not run.passed:
        return Gate(False, f"{want['model']} failed its latest safety test: {run.verdict}", run)
    return Gate(True, f"{want['model']} passed the safety test on {run.finished_at:%b %-d}: {run.verdict}", run)
