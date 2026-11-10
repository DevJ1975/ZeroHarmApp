from django.utils import timezone

from . import safety_eval as ev
from .ai import ensure_model, is_local
from .models import MondayEvalRun


def run_eval(topics, compare=True) -> MondayEvalRun:
    """Runs the safety test with RAG (and without, to compare) and saves the results. Can take hours on CPU."""
    topics = list(topics)
    run = MondayEvalRun.objects.create(model=ev.model_name(), topics=[t.slug for t in topics])
    per_mode = sum(1 + sum(1 for k in ev.PLANTS if ev.planted(t, k)) for t in topics)
    total, done = per_mode * (2 if compare else 1), [0]

    def tick():
        done[0] += 1
        MondayEvalRun.objects.filter(pk=run.pk).update(progress=f"{done[0]} of {total} talks")

    try:
        if is_local():
            ensure_model()
        results = {"rag_on": ev.run(topics, rag=True, progress=tick)}
        if compare:
            results["rag_off"] = ev.run(topics, rag=False, progress=tick)
        run.results = results
        run.summary = "\n\n".join(ev.summarize(r) for r in results.values())
        run.status = "done"
    except Exception as err:
        run.status, run.summary = "failed", str(err)[:2000]
    run.finished_at = timezone.now()
    run.progress = f"{done[0]} of {total} talks"
    run.save()
    return run
