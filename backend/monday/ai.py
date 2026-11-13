"""Where Monday Minute's AI runs: your own Ollama server (AI_PROVIDER=local) or Claude (AI_PROVIDER=anthropic).

Every call asks for JSON that matches a schema and returns (data, model). Refusals, cut-off answers and bad JSON raise
GenerationError, so the caller fails safe (a draft fails, a comment waits) instead of guessing.

Local runs on CPU (Railway has no GPUs), so it's slow: minutes per talk, seconds to a minute per comment. The talk
pipeline runs from the cron and comments are screened in the background, so nobody waits on it.

Two limits keep a slow or stuck AI server from holding everything else up. A comment check has its own short timeout
(LOCAL_AI_FAST_TIMEOUT) instead of the long one a talk needs. And a caller can put a ceiling on everything it does
with `with time_budget(seconds):` (the cron step does, see MONDAY_STEP_BUDGET): calls inside share one deadline.
"""
import json
import logging
import threading
import time
import urllib.error
import urllib.request
from contextlib import contextmanager

from django.conf import settings

log = logging.getLogger(__name__)


class GenerationError(Exception):
    pass


class AIUnavailable(GenerationError):
    """The AI server or API can't be reached right now. Not the draft's fault: try again later, don't count it as a failed attempt."""


_budget = threading.local()  # .deadline: when this thread's time for AI calls runs out (time.monotonic), if it has one


@contextmanager
def time_budget(seconds):
    """Everything inside shares one deadline: each AI call may wait only for what is left of it, and once it has
    passed, calls fail at once with AIUnavailable (so nothing is recorded and the next run tries again). One stuck
    call used to cost its full timeout, 30 minutes with the local model, and a run made up to 18 of them, while
    Railway skipped every other scheduled run. 0 or None means no limit."""
    earlier = getattr(_budget, "deadline", None)
    if seconds:
        mine = time.monotonic() + seconds
        _budget.deadline = mine if earlier is None else min(earlier, mine)
    try:
        yield
    finally:
        _budget.deadline = earlier


def _time_for(timeout: float) -> float:
    """How long one call may wait: its own timeout, or what is left of the time budget if that is less."""
    deadline = getattr(_budget, "deadline", None)
    if deadline is None:
        return timeout
    left = deadline - time.monotonic()
    if left <= 0:
        raise AIUnavailable("This run has used up its time for AI calls. The next run carries on.")
    return min(timeout, left)


def provider() -> str:
    return settings.AI_PROVIDER


def is_local() -> bool:
    return provider() == "local"


def available() -> bool:
    """Whether the configured provider is set up at all (the server or the key)."""
    return bool((settings.LOCAL_AI_URL or "").strip()) if is_local() else bool(settings.ANTHROPIC_API_KEY)


# What each job needs. Smaller context and output caps mean less memory and time on CPU; the reviewer gets the most
# room because it reads the brief, the talk, the regulation text and past findings. Temperature 0 keeps checks repeatable.
ROLES = {
    #            context  max output  temperature  Claude effort
    "write":    (8192,    1500,       0.4,         "medium"),
    "review":   (16384,   2000,       0.0,         "high"),
    "moderate": (4096,    200,        0.0,         "low"),
}


def ai_json(system: str, user: str, schema: dict, role: str = "review", think: bool = True, fast: bool = False, seed: int | None = None):
    """One structured call on the configured provider, tuned for its role (see ROLES).
    `think` lets the local model reason first (slower, better). `fast` is for comment checks, which are small and must
    not tie anything up: a short timeout on either provider (and one retry on Claude). `seed` makes a second local
    review differ from the first."""
    if is_local():
        return ollama_json(system, user, schema, role=role, think=think, seed=seed, fast=fast)
    return claude_json(system, user, schema, ROLES[role][3], fast=fast)


def local_model(role: str) -> str:
    """The reviewer can run on a bigger model than the writer (LOCAL_AI_REVIEW_MODEL); it runs once a week, so slower is fine."""
    return (settings.LOCAL_AI_REVIEW_MODEL or settings.LOCAL_AI_MODEL) if role == "review" else settings.LOCAL_AI_MODEL


# ---- Local: Ollama ----------------------------------------------------------------------------------

NO_LOCAL_URL = "The AI server address is not set (LOCAL_AI_URL)."
BAD_LOCAL_URL = ("The AI server address (LOCAL_AI_URL) is not a web address. It must start with http:// or https://, "
                 "for example http://ollama.railway.internal:11434.")


def local_url() -> str:
    """Where the local AI server is. A blank or malformed address is said in one plain line (AIUnavailable, so nothing
    is recorded against a draft or a comment) instead of urllib's "unknown url type: '/api/tags'", which named neither
    the setting nor the fix and came with a traceback for every posted comment."""
    url = (settings.LOCAL_AI_URL or "").strip().rstrip("/")
    if not url:
        raise AIUnavailable(NO_LOCAL_URL)
    if not url.lower().startswith(("http://", "https://")):
        raise AIUnavailable(BAD_LOCAL_URL)
    return url


def _ollama(path: str, payload: dict | None, timeout: float):
    url = local_url() + path
    data = json.dumps(payload).encode() if payload is not None else None
    try:
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST" if data else "GET")
    except ValueError as err:  # an address urllib cannot read at all
        raise AIUnavailable(BAD_LOCAL_URL) from err
    timeout = _time_for(timeout)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return json.loads(res.read().decode() or "{}")
    except (urllib.error.URLError, TimeoutError, OSError) as err:
        raise AIUnavailable(f"Local AI server unavailable: {err}") from err


def ensure_model() -> bool:
    """Downloads the model(s) onto the AI server's volume the first time (several GB, can take a while). True when ready."""
    tags = _ollama("/api/tags", None, timeout=30)
    names = {m.get("name") for m in tags.get("models", [])} | {m.get("model") for m in tags.get("models", [])}
    ready = True
    for model in {local_model("write"), local_model("review")}:
        if model in names:
            continue
        log.warning("Pulling %s onto the local AI server", model)
        ready = _ollama("/api/pull", {"model": model, "stream": False}, timeout=3600).get("status") == "success" and ready
    return ready


def ollama_json(system: str, user: str, schema: dict, role: str = "review", think: bool = True, seed: int | None = None, fast: bool = False):
    context, max_out, temperature, _ = ROLES[role]
    # A comment check is a few hundred tokens: if it has no answer in a few minutes the server is busy or stuck, and
    # waiting the 30 minutes a talk is allowed would hold a cron run (or the web worker) for nothing.
    timeout = min(settings.LOCAL_AI_TIMEOUT, settings.LOCAL_AI_FAST_TIMEOUT) if fast else settings.LOCAL_AI_TIMEOUT
    options = {"temperature": temperature, "num_ctx": context, "num_predict": max_out + (2000 if think else 0)}
    if settings.LOCAL_AI_THREADS:
        options["num_thread"] = settings.LOCAL_AI_THREADS  # match the service's vCPU limit; Ollama otherwise counts the host's cores
    if seed is not None:
        options["seed"] = seed
    model = local_model(role)
    res = _ollama("/api/chat", {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "format": schema,                       # Ollama constrains the output to this JSON schema
        "think": think,
        "stream": False,
        "keep_alive": "10m",                    # unload after 10 idle minutes, so memory (and the bill) drops between runs
        "options": options,
    }, timeout=timeout)
    if res.get("done_reason") == "length":
        raise GenerationError("The local model ran out of room before finishing.")
    text = (res.get("message") or {}).get("content", "")
    try:
        return json.loads(text), f"local:{res.get('model', model)}"
    except json.JSONDecodeError as err:
        raise GenerationError(f"Local model returned invalid JSON: {err}") from err


# ---- Claude -----------------------------------------------------------------------------------------

def _client():
    import anthropic

    return anthropic.Anthropic(timeout=180.0, max_retries=3)


def claude_json(system: str, user: str, schema: dict, effort: str = "high", fast: bool = False):
    import anthropic

    client = _client()
    if fast:
        client = client.with_options(timeout=20.0, max_retries=1)
    if getattr(_budget, "deadline", None) is not None:  # inside a time budget: no call may wait past what is left of it
        client = client.with_options(timeout=_time_for(20.0 if fast else 180.0))
    kwargs = dict(
        model=settings.MONDAY_MODEL,
        max_tokens=1000 if effort == "low" else 16000,
        system=system,
        messages=[{"role": "user", "content": user}],
        output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
    )
    try:
        try:  # server-side fallback re-runs a declined request on another model inside the same call
            res = client.beta.messages.create(betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs)
        except anthropic.BadRequestError:
            res = client.messages.create(**kwargs)
    except (anthropic.APIConnectionError, anthropic.RateLimitError, anthropic.InternalServerError, anthropic.AuthenticationError) as err:
        raise AIUnavailable(f"Claude API unavailable: {err}") from err
    if res.stop_reason == "refusal":
        raise GenerationError("The model declined this request.")
    if res.stop_reason == "max_tokens":
        raise GenerationError("The response was cut off.")
    text = next((b.text for b in res.content if b.type == "text"), "")
    try:
        return json.loads(text), res.model
    except json.JSONDecodeError as err:
        raise GenerationError(f"Not valid JSON: {err}") from err
