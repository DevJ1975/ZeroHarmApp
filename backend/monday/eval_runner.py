from django.conf import settings
from django.utils import timezone

from . import gate
from . import safety_eval as ev
from .ai import ensure_model, is_local
from .models import MondayEvalRun


def run_eval(topics, compare=True) -> MondayEvalRun:
    """Runs the safety test for the current AI setup (and the other RAG mode, to compare), saves the results and
    whether the setup passed the gate's bar. Can take hours on CPU."""
    topics = list(topics)
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
