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


def provider() -> str:
    return settings.AI_PROVIDER


def is_local() -> bool:
    return provider() == "local"


def available() -> bool:
    """Whether the configured provider is set up at all (the server or the key)."""
    return bool(settings.LOCAL_AI_URL) if is_local() else bool(settings.ANTHROPIC_API_KEY)


def ai_json(system: str, user: str, schema: dict, effort: str = "high", think: bool = True):
    """One structured call on the configured provider. `think` lets the local model reason first (slower, better)."""
    if is_local():
        return ollama_json(system, user, schema, think=think)
    return claude_json(system, user, schema, effort)


# ---- Local: Ollama ----------------------------------------------------------------------------------

def _ollama(path: str, payload: dict | None, timeout: float):
    url = settings.LOCAL_AI_URL.rstrip("/") + path
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST" if data else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return json.loads(res.read().decode() or "{}")
    except (urllib.error.URLError, TimeoutError, OSError) as err:
        raise GenerationError(f"Local AI server unavailable: {err}") from err


def ensure_model() -> bool:
    """Downloads the model onto the AI server's volume the first time (several GB, can take a while). True when ready."""
    tags = _ollama("/api/tags", None, timeout=30)
    names = {m.get("name") for m in tags.get("models", [])} | {m.get("model") for m in tags.get("models", [])}
    if settings.LOCAL_AI_MODEL in names:
        return True
    log.warning("Pulling %s onto the local AI server", settings.LOCAL_AI_MODEL)
    res = _ollama("/api/pull", {"model": settings.LOCAL_AI_MODEL, "stream": False}, timeout=3600)
    return res.get("status") == "success"


def ollama_json(system: str, user: str, schema: dict, think: bool = True):
    res = _ollama("/api/chat", {
        "model": settings.LOCAL_AI_MODEL,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "format": schema,                       # Ollama constrains the output to this JSON schema
        "think": think,
        "stream": False,
        "keep_alive": "10m",                    # unload after 10 idle minutes, so memory (and the bill) drops between runs
        "options": {"temperature": 0.2, "num_ctx": 16384},
    }, timeout=settings.LOCAL_AI_TIMEOUT)
    if res.get("done_reason") == "length":
        raise GenerationError("The local model ran out of room before finishing.")
    text = (res.get("message") or {}).get("content", "")
    try:
        return json.loads(text), f"local:{res.get('model', settings.LOCAL_AI_MODEL)}"
    except json.JSONDecodeError as err:
        raise GenerationError(f"Local model returned invalid JSON: {err}") from err


# ---- Claude -----------------------------------------------------------------------------------------

def _client():
    import anthropic

    return anthropic.Anthropic(timeout=180.0, max_retries=3)


def claude_json(system: str, user: str, schema: dict, effort: str = "high"):
    import anthropic

    client = _client()
    kwargs = dict(
        model=settings.MONDAY_MODEL,
        max_tokens=16000,
        system=system,
        messages=[{"role": "user", "content": user}],
        output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
    )
    try:  # server-side fallback re-runs a declined request on another model inside the same call
        res = client.beta.messages.create(betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs)
    except anthropic.BadRequestError:
        res = client.messages.create(**kwargs)
    if res.stop_reason == "refusal":
        raise GenerationError("The model declined this request.")
    if res.stop_reason == "max_tokens":
        raise GenerationError("The response was cut off.")
    text = next((b.text for b in res.content if b.type == "text"), "")
    try:
        return json.loads(text), res.model
    except json.JSONDecodeError as err:
        raise GenerationError(f"Not valid JSON: {err}") from err
