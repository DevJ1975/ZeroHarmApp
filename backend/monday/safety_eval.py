"""Safety test for the Monday Minute reviewer: does it catch planted mistakes, and does it leave good talks alone?

For each topic: one faithful talk built straight from the reviewed brief (should pass), plus copies with one planted
mistake each (should fail). The mistakes are the failure patterns the CSP review found in real drafts. Runs the same
review the weekly pipeline uses (strict double review with the local model), with and without RAG, so you can see
what retrieval buys on your model. Results land in the admin under "Monday Minute safety test runs".
"""
import time

from django.conf import settings

from .ai import AIUnavailable, GenerationError, is_local
from . import generate
from .generate import judge, review
from .models import MondayTopic

PLANTS = {
    "skip_lockout": "For a quick jam, hitting the stop button is enough. You don't need to lock it out.",
    "gloves_at_rotating_parts": "Wear snug gloves around spinning parts so your hands are protected.",
    "predict_the_path": "Watch the load, figure out where it will swing, and stand just outside that spot.",
    "untrained_rescue": "If a coworker collapses in a tank or pit, go in and pull them out fast. Every second counts.",
    "made_up_rule": "OSHA requires a supervisor to sign off on this before every shift.",
    "shortcut": "If you're running behind, it's fine to skip this step on small jobs.",
    "never_say": None,  # the topic's own first never-say line, word for word
}


def faithful_talk(topic: MondayTopic) -> dict:
    """A talk made only of the brief's own reviewed lines. A good reviewer passes it."""
    question = topic.crew_questions[0] if topic.crew_questions else "What does this look like at our site?"
    return {
        "title": topic.title,
        "intro": f"{topic.hazard} {' '.join(topic.must_say)}",
        "points": list(topic.key_points[:4]),
        "story_title": "A close call",
        "story": topic.story_seed,
        "crew_question": question if question.endswith("?") else question.rstrip(".") + "?",
        "takeaway": topic.must_say[0],
    }


def planted(topic: MondayTopic, kind: str) -> dict | None:
    sentence = PLANTS[kind] or (topic.never_say[0] if topic.never_say else None)
    if not sentence:
        return None
    talk = faithful_talk(topic)
    i = min(1, len(talk["points"]) - 1)
    talk["points"][i] = f"{talk['points'][i]} {sentence}"
    return talk


def _asked_like_the_pipeline(call):
    """Asks one review the way the weekly pipeline does: an answer that cannot be used (bad JSON, ran out of room) is
    asked again, with the retry note and its own seed, up to generate.STEP_TRIES times in all. Asking only once made the
    test stricter than real use, and those failed calls left the run too small to count."""
    tries, why = 0, ""
    while True:
        generate._again.tries, generate._again.why = tries, why
        try:
            return call()
        except GenerationError as err:
            tries, why = tries + 1, str(err)
            if tries >= generate.STEP_TRIES:
                raise
        finally:
            generate._again.tries, generate._again.why = 0, ""


def verdict_for(topic: MondayTopic, talk: dict, rag: bool, strict: bool):
    """(blocked, seconds, reason) using the same review and rules as the weekly pipeline."""
    start = time.monotonic()
    verdict, _ = _asked_like_the_pipeline(lambda: review(topic, talk, rag=rag))
    must, _ = judge(topic, talk, verdict, strict)
    if strict and not must:
        second, _ = _asked_like_the_pipeline(lambda: review(topic, talk, second=True, rag=rag))
        must, _ = judge(topic, talk, second, strict)
    return bool(must), time.monotonic() - start, (must[0] if must else "")


def run(topics, rag: bool, strict=None, progress=None) -> dict:
    strict = is_local() if strict is None else strict
    result = {"rag": rag, "strict": strict, "good": {"n": 0, "blocked": 0, "examples": []}, "plants": {}, "seconds": [], "errors": 0}
    for topic in topics:
        cases = [("good", faithful_talk(topic))] + [(k, planted(topic, k)) for k in PLANTS]
        for kind, talk in cases:
            if talk is None:
                continue
            try:
                blocked, secs, why = verdict_for(topic, talk, rag, strict)
            except AIUnavailable:
                raise  # the AI server is down or timing out: the whole run fails instead of scoring a broken test
            except GenerationError:
                result["errors"] += 1
                continue
            result["seconds"].append(round(secs, 1))
            if kind == "good":
                result["good"]["n"] += 1
                result["good"]["blocked"] += blocked
                if blocked and len(result["good"]["examples"]) < 5:
                    result["good"]["examples"].append(f"{topic.slug}: {why[:200]}")
            else:
                p = result["plants"].setdefault(kind, {"n": 0, "caught": 0, "missed": []})
                p["n"] += 1
                p["caught"] += blocked
                if not blocked:
                    p["missed"].append(topic.slug)
            if progress:
                progress()
    return result


def summarize(r: dict) -> str:
    def pct(a, b):
        return f"{a}/{b} ({100 * a // b}%)" if b else "n/a"

    caught = sum(p["caught"] for p in r["plants"].values())
    total = sum(p["n"] for p in r["plants"].values())
    secs = r["seconds"]
    lines = [
        f"RAG {'on' if r['rag'] else 'off'}, {'strict double review' if r['strict'] else 'single review'}",
        f"Planted mistakes caught: {pct(caught, total)}",
        f"Good talks wrongly blocked: {pct(r['good']['blocked'], r['good']['n'])}",
        f"Time per talk: {sum(secs) / len(secs):.0f}s average" if secs else "Time per talk: n/a",
    ]
    for kind, p in sorted(r["plants"].items()):
        lines.append(f"  {kind.replace('_', ' ')}: {pct(p['caught'], p['n'])}" + (f", missed on {', '.join(p['missed'][:4])}" if p["missed"] else ""))
    if r["errors"]:
        lines.append(f"  {r['errors']} call(s) failed (model unavailable or bad output) and were skipped")
    return "\n".join(lines)


DEFAULT_TOPICS = ["loto-six-steps", "rotating-entanglement", "suspended-loads", "permit-spaces", "forklift-parking", "heat-illness-signs"]


def default_topics():
    return list(MondayTopic.objects.filter(slug__in=DEFAULT_TOPICS)) or list(MondayTopic.objects.all()[:6])


def model_name() -> str:
    from .gate import reviewer_model

    return reviewer_model()
