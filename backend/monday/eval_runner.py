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
        run.passed, run.verdict = gate.judge(configured)
        run.catch_rate, run.false_block_rate = scores["catch_rate"], scores["false_block_rate"]
        run.results = results
        run.summary = (("PASSED: " if run.passed else "NOT PASSED: ") + run.verdict + "\n\n"
                       + "\n\n".join(ev.summarize(r) for r in results.values()))
        run.status = "done"
    except Exception as err:
        run.status, run.summary = "failed", str(err)[:2000]
    run.finished_at = timezone.now()
    run.progress = f"{done[0]} of {total} talks"
    run.save()
    return run
