import logging
import threading
from datetime import timedelta

from django.conf import settings
from django.db import connection
from django.utils import timezone

from . import gate
from . import safety_eval as ev
from .ai import ensure_model, is_local
from .models import MondayEvalRun, MondayLock

log = logging.getLogger(__name__)

# One safety test at a time: two at once on a CPU-only AI server each take twice as long and time out more.
# The run holds this lock and refreshes it every minute while its process is alive. A deploy, restart or crash
# stops the refreshing, and that silence is how an interrupted run is told from one that is only slow.
LOCK = "eval"
BEAT_EVERY = 60                      # seconds between refreshes
STALE_AFTER = timedelta(minutes=10)  # no refresh for this long means the process behind the run is gone
INTERRUPTED = ("Interrupted: the server process running this test stopped (a deploy, a restart or a crash) before it "
               "finished, so there is no result. Start it again from the topics list.")


class AlreadyRunning(Exception):
    """A safety test is still going. Wait for it, or for it to be marked failed if its process died."""


def close_stale_runs(now=None) -> int:
    """Marks runs that still say "running" but have no live process behind them as failed. Returns how many.
    Called before a new run starts, when the runs are opened in the admin, and safe to call from the cron."""
    now = now or timezone.now()
    if MondayLock.objects.filter(name=LOCK, locked_at__gt=now - STALE_AFTER).exists():
        return 0  # a run is alive, and it is the one that says "running"
    closed = 0
    for run in MondayEvalRun.objects.filter(status="running"):
        run.status, run.finished_at = "failed", now
        run.summary = INTERRUPTED + (f" It had done {run.progress}." if run.progress else "")
        run.save(update_fields=["status", "finished_at", "summary"])
        closed += 1
    return closed


def claim() -> bool:
    """Takes the one safety-test slot. False when a run is already going. Whoever gets True must call run_eval
    (claimed=True) or release()."""
    close_stale_runs()
    return MondayLock.acquire(LOCK, ttl=STALE_AFTER)


def release():
    MondayLock.release(LOCK)


def _keep_alive(stop):
    """Refreshes the lock for as long as the run works, however long that is. Progress alone is too quiet for this:
    one model call can take half an hour, and a full test many hours."""
    try:
        while not stop.wait(BEAT_EVERY):
            try:
                MondayLock.objects.filter(name=LOCK).update(locked_at=timezone.now())
            except Exception:  # a database blip must not end the sign of life; the next beat tries again
                log.exception("Safety test: could not refresh its lock")
    finally:
        connection.close()


def run_eval(topics, compare=True, claimed=False) -> MondayEvalRun:
    """Runs the safety test for the current AI setup (and the other RAG mode, to compare), saves the results and
    whether the setup passed the gate's bar. Can take hours on CPU.
    Only one runs at a time: raises AlreadyRunning if another is going. Pass claimed=True when claim() was already
    called (the admin does, so it can tell the owner before starting the background work)."""
    if not claimed and not claim():
        raise AlreadyRunning("A safety test is already running. Wait for it to finish.")
    stop = threading.Event()
    try:
        threading.Thread(target=_keep_alive, args=(stop,), daemon=True).start()
        return _run(list(topics), compare)
    finally:
        stop.set()
        release()


def _run(topics, compare) -> MondayEvalRun:
    want = gate.setup()
    run = MondayEvalRun.objects.create(model=want["model"], rag=want["rag"], strict=want["strict"], topics=[t.slug for t in topics])
    per_mode = sum(1 + sum(1 for k in ev.PLANTS if ev.planted(t, k)) for t in topics)
    total, done = per_mode * (2 if compare else 1), [0]

    def tick():
        done[0] += 1
        MondayEvalRun.objects.filter(pk=run.pk).update(progress=f"{done[0]} of {total} talks")

    key = lambda rag: "rag_on" if rag else "rag_off"
    try:
        if is_local():
            ensure_model()
        results = {key(want["rag"]): ev.run(topics, rag=want["rag"], strict=want["strict"], progress=tick)}
        if compare:
            results[key(not want["rag"])] = ev.run(topics, rag=not want["rag"], strict=want["strict"], progress=tick)
        configured = results[key(want["rag"])]
        scores = gate.score(configured)
        run.conclusive, why = gate.conclusive(configured, run.topics)
        if run.conclusive:
            run.passed, run.verdict = gate.judge(configured)
            label = "PASSED: " if run.passed else "NOT PASSED: "
        else:
            run.passed, run.verdict = False, f"exploratory run, does not count toward the safety gate: {why}"[:300]
            label = "EXPLORATORY: "
        run.catch_rate, run.false_block_rate = scores["catch_rate"], scores["false_block_rate"]
        run.results = results
        run.summary = (label + run.verdict + "\n\n"
                       + "\n\n".join(ev.summarize(r) for r in results.values()))
        run.status = "done"
    except Exception as err:
        run.status, run.summary = "failed", str(err)[:2000]
    run.finished_at = timezone.now()
    run.progress = f"{done[0]} of {total} talks"
    run.save()
    # A talk written while an earlier pass stood must not publish on its own after this run says otherwise.
    held = gate.hold_unpublished()
    if held:
        run.summary += f"\n\n{held} talk(s) that had not published yet were moved back to waiting for approval."
        run.save(update_fields=["summary"])
    return run
