"""Where Monday Minute's AI runs: your own Ollama server (AI_PROVIDER=local) or Claude (AI_PROVIDER=anthropic).

Every call asks for JSON that matches a schema and returns (data, model). Refusals, cut-off answers and bad JSON raise
GenerationError, so the caller fails safe (a draft fails, a comment waits) instead of guessing.

Local runs on CPU (Railway has no GPUs), so it's slow: minutes per talk, seconds to a minute per comment. The talk
pipeline runs from the cron and comments are screened in the background, so nobody waits on it.
"""
import json
import logging
import urllib.error
import urllib.request

from django.conf import settings

log = logging.getLogger(__name__)


class GenerationError(Exception):
    pass


class AIUnavailable(GenerationError):
    """The AI server or API can't be reached right now. Not the draft's fault: try again later, don't count it as a failed attempt."""


def provider() -> str:
    return settings.AI_PROVIDER


def is_local() -> bool:
    return provider() == "local"


def available() -> bool:
    """Whether the configured provider is set up at all (the server or the key)."""
    return bool(settings.LOCAL_AI_URL) if is_local() else bool(settings.ANTHROPIC_API_KEY)


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
    `think` lets the local model reason first (slower, better). `fast` is for calls made while a person waits (comment
    checks on Claude): short timeout, one retry. `seed` makes a second local review differ from the first."""
    if is_local():
        return ollama_json(system, user, schema, role=role, think=think, seed=seed)
    return claude_json(system, user, schema, ROLES[role][3], fast=fast)


def local_model(role: str) -> str:
    """The reviewer can run on a bigger model than the writer (LOCAL_AI_REVIEW_MODEL); it runs once a week, so slower is fine."""
    return (settings.LOCAL_AI_REVIEW_MODEL or settings.LOCAL_AI_MODEL) if role == "review" else settings.LOCAL_AI_MODEL


# ---- Local: Ollama ----------------------------------------------------------------------------------

def _ollama(path: str, payload: dict | None, timeout: float):
    url = settings.LOCAL_AI_URL.rstrip("/") + path
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST" if data else "GET")
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


def ollama_json(system: str, user: str, schema: dict, role: str = "review", think: bool = True, seed: int | None = None):
    context, max_out, temperature, _ = ROLES[role]
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
    }, timeout=settings.LOCAL_AI_TIMEOUT)
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
