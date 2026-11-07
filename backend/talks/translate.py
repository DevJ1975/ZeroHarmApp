"""Drafts a Spanish version of a talk with the Claude API. A draft is never shown in the app until approved in the admin."""
import json
import os
import urllib.error
import urllib.request

PROMPT = """Translate this workplace safety toolbox talk into clear, plain Spanish for frontline workers in US plants and warehouses (neutral Latin American Spanish, "usted").
Keep the meaning exact. Do not add or remove safety steps. Keep OSHA citations like 1910.147 and numbers unchanged. Keep "## " heading markers and blank lines between paragraphs.
Return only JSON with these keys: title, story_title, crew_question, body_md.

"""


def draft_spanish(talk):
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        raise RuntimeError("Set ANTHROPIC_API_KEY on the Railway web service to draft translations.")
    source = {"title": talk.title, "story_title": talk.story_title, "crew_question": talk.crew_question, "body_md": talk.body_md}
    payload = {
        "model": os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5-5"),
        "max_tokens": 4000,
        "messages": [{"role": "user", "content": PROMPT + json.dumps(source, ensure_ascii=False)}],
    }
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(payload).encode(),
        headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as res:
            data = json.loads(res.read())
    except urllib.error.HTTPError as err:
        raise RuntimeError(f"Claude API {err.code}: {err.read().decode(errors='replace')[:200]}") from err
    text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text").strip()
    text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    out = json.loads(text)
    talk.title_es = out["title"][:200]
    talk.story_title_es = out["story_title"][:200]
    talk.crew_question_es = out["crew_question"]
    talk.body_md_es = out["body_md"]
    talk.spanish_status = talk.ES_DRAFT
    talk.save()
