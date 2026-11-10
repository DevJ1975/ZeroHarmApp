"""Zero Harm API v2 (Django Ninja): what the phones need to run OTIS on the device.

OTIS's model runs on the phone (ExecuTorch: MLX or Core ML on iPhone, XNNPACK or Vulkan on Android). This API never runs
the model. It tells each phone which model files to download, whether OTIS is switched on for its platform, when the
knowledge base changed, and takes opt-in "Was this helpful?" ratings. Schema and docs: /api/v2/docs.
"""
import hashlib
import json
from decimal import Decimal
from typing import Literal

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.core.cache import cache
from django.http import HttpRequest, HttpResponse
from ninja import NinjaAPI, Schema
from ninja.throttling import AnonRateThrottle
from pydantic import Field

from .models import OtisFeedback, OtisModelRelease, OtisRollout

# The interactive docs describe every endpoint; keep them for people signed in to the admin.
api = NinjaAPI(title="Zero Harm API", version="2.0.0", urls_namespace="api-v2", docs_url="/docs",
               docs_decorator=staff_member_required)


def _mount_routers():
    from monday.api import router as monday_router
    from usage.api import router as usage_router

    api.add_router("/monday-minute", monday_router)
    api.add_router("/app", usage_router)

BUILTIN_SIZE_MB = {"QWEN3_1_7B": 1300, "QWEN3_0_6B": 510}
MIN_MEMORY_GB_FOR_BIG_MODEL = 6
KB_CACHE_KEY = "otis-kb-v2"
KB_CACHE_SECONDS = 60
Platform = Literal["ios", "android"]


# ---- Schemas ----------------------------------------------------------------------------------------

class DeviceIn(Schema):
    platform: Platform
    memory_gb: float = Field(ge=0, le=64, description="Total device memory")
    app_version: str = Field(default="", max_length=20)
    os_version: str = Field(default="", max_length=20)
    backends: list[str] = Field(default_factory=list, max_length=8, description="ExecuTorch backends this app build links, e.g. ['mlx', 'xnnpack']")
    kb_version: str = Field(default="", max_length=64, description="Knowledge base version already on the phone")


class ModelFiles(Schema):
    model_url: str
    tokenizer_url: str
    tokenizer_config_url: str


class ModelOut(Schema):
    key: str = Field(description="Changes when the phone should download a new model")
    label: str
    size_mb: int
    builtin: str | None = Field(description="react-native-executorch model name when no pinned release applies")
    files: ModelFiles | None = Field(description="Pinned files to download instead of the built-in model")


class KbStatus(Schema):
    version: str
    changed: bool


class ManifestOut(Schema):
    enabled: bool
    message: str = ""
    update_required: bool = False
    model: ModelOut | None
    kb: KbStatus
    feedback_enabled: bool


class KbItem(Schema):
    id: str
    title: str
    text: str
    source: str
    lang: str
    issue: int | None = None
    episode: int | None = None
    tags: str | None = None


class KbOut(Schema):
    version: str
    items: list[KbItem]


class FeedbackIn(Schema):
    helpful: bool
    source_ids: list[str] = Field(default_factory=list, max_length=8)
    question: str = Field(default="", max_length=500, description="Only when the person chose to share it")
    model_key: str = Field(default="", max_length=60)
    platform: Platform | Literal[""] = ""
    app_version: str = Field(default="", max_length=20)
    lang: Literal["en", "es"] = "en"


class Ok(Schema):
    ok: bool


class Error(Schema):
    error: str


# ---- Helpers ----------------------------------------------------------------------------------------

def _version_tuple(v: str):
    parts = []
    for p in v.split("."):
        digits = "".join(ch for ch in p if ch.isdigit())
        parts.append(int(digits or 0))
    return tuple(parts)


def current_kb():
    """(version, JSON body) of the knowledge base, cached briefly. The version is a content hash: it changes whenever any passage does."""
    hit = cache.get(KB_CACHE_KEY)
    if hit:
        return hit
    from .views import kb_items

    items = kb_items()
    version = hashlib.sha256(json.dumps(items, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]
    # Keep the finished JSON too: serving it skips validating and re-encoding a few hundred passages per request.
    body = json.dumps({"version": version, "items": items}, ensure_ascii=False, separators=(",", ":")).encode()
    cache.set(KB_CACHE_KEY, (version, body), KB_CACHE_SECONDS)
    return version, body


def pick_model(device: DeviceIn) -> ModelOut:
    """A pinned release this phone can run (platform, backend, memory), else the library's built-in model by memory."""
    backends = {b.lower() for b in device.backends} or {"xnnpack"}  # unknown build: XNNPACK runs everywhere
    release = (
        OtisModelRelease.objects.filter(active=True, platform=device.platform, backend__in=backends,
                                        min_memory_gb__lte=Decimal(str(device.memory_gb)))
        .order_by("-min_memory_gb", "-updated_at")
        .first()
    )
    if release:
        return ModelOut(key=release.key, label=release.label, size_mb=release.size_mb, builtin=None,
                        files=ModelFiles(model_url=release.model_url, tokenizer_url=release.tokenizer_url,
                                         tokenizer_config_url=release.tokenizer_config_url))
    name = settings.OTIS_MODEL if device.memory_gb >= MIN_MEMORY_GB_FOR_BIG_MODEL else settings.OTIS_SMALL_MODEL
    return ModelOut(key=f"builtin-{name}", label="OTIS standard" if name == settings.OTIS_MODEL else "OTIS compact",
                    size_mb=BUILTIN_SIZE_MB.get(name, 0), builtin=name, files=None)


# ---- Endpoints --------------------------------------------------------------------------------------

class AppConfigOut(Schema):
    theme: Literal["auto", "default", "holiday"] = Field(
        description="auto: the phone follows the calendar (holiday look in December). default or holiday force it.")


@api.get("/app/config", response=AppConfigOut, tags=["App"], summary="Switches the app checks when it opens")
def app_config(request: HttpRequest):
    theme = settings.APP_THEME if settings.APP_THEME in ("auto", "default", "holiday") else "auto"
    return {"theme": theme}


@api.post("/otis/manifest", response=ManifestOut, tags=["OTIS"], summary="What this phone should run")
def manifest(request: HttpRequest, device: DeviceIn):
    rollout = OtisRollout.current()
    platform_on = rollout.ios_enabled if device.platform == "ios" else rollout.android_enabled
    enabled = settings.OTIS_ENABLED and platform_on
    too_old = bool(rollout.min_app_version and device.app_version
                   and _version_tuple(device.app_version) < _version_tuple(rollout.min_app_version))
    version, _ = current_kb()
    return ManifestOut(
        enabled=enabled and not too_old,
        message="" if enabled else (rollout.message or "OTIS is taking a short break. Check back soon."),
        update_required=too_old,
        model=pick_model(device) if enabled and not too_old else None,
        kb=KbStatus(version=version, changed=device.kb_version != version),
        feedback_enabled=rollout.feedback_enabled,
    )


@api.get("/otis/kb", response={200: KbOut, 304: None}, tags=["OTIS"], summary="Knowledge base, only when it changed")
def kb(request: HttpRequest):
    """Send `If-None-Match` with the version you have. A 304 means the copy on the phone is current."""
    version, body = current_kb()
    etag = f'"{version}"'
    sent = request.headers.get("If-None-Match", "").removeprefix("W/")
    res = HttpResponse(status=304) if sent in (etag, version) else HttpResponse(body, content_type="application/json")
    res["ETag"] = etag
    res["Cache-Control"] = "no-cache"
    return res


@api.post("/otis/feedback", response={201: Ok, 403: Error}, tags=["OTIS"], summary="Opt-in 'Was this helpful?' rating",
          throttle=[AnonRateThrottle("30/h")])
def feedback(request: HttpRequest, body: FeedbackIn):
    if not OtisRollout.current().feedback_enabled:
        return 403, {"error": "Feedback is turned off."}
    OtisFeedback.objects.create(
        helpful=body.helpful,
        question=body.question.strip(),
        source_ids=[s[:20] for s in body.source_ids],
        model_key=body.model_key,
        platform=body.platform,
        app_version=body.app_version,
        lang=body.lang,
    )
    return 201, {"ok": True}


_mount_routers()
