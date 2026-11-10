"""Zero Harm backend settings. Everything that differs between your Mac and Railway comes from environment variables."""
import os
from pathlib import Path

import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent

DEBUG = os.environ.get("DJANGO_DEBUG", "0") == "1"
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-not-secret" if DEBUG else "")
if not SECRET_KEY:
    raise RuntimeError("Set DJANGO_SECRET_KEY.")

# Railway sets RAILWAY_PUBLIC_DOMAIN automatically once the service has a domain.
_hosts = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
if os.environ.get("RAILWAY_PUBLIC_DOMAIN"):
    _hosts.append(os.environ["RAILWAY_PUBLIC_DOMAIN"])
_hosts.append("healthcheck.railway.app")  # Railway's health check calls with this hostname; without it deploys fail
ALLOWED_HOSTS = [h.strip() for h in _hosts if h.strip()]
CSRF_TRUSTED_ORIGINS = [f"https://{h}" for h in ALLOWED_HOSTS if h not in ("localhost", "127.0.0.1", "healthcheck.railway.app")]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "talks",
    "monday",
    "regs",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.gzip.GZipMiddleware",  # the OTIS knowledge base is ~320 KB of JSON; gzip cuts it about 4x
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.http.ConditionalGetMiddleware",  # ETags on GETs: unchanged talks and feeds answer 304
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "zeroharm.urls"
WSGI_APPLICATION = "zeroharm.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ]
        },
    }
]

# DATABASE_URL comes from Railway Postgres (or docker-compose locally); SQLite is the fallback.
DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}", conn_max_age=600, conn_health_checks=True
    )
}

CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "America/Los_Angeles"  # admin shows Pacific time; the database stores UTC
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Railway's edge appends the real client address to X-Forwarded-For. Trust only that last hop for rate limits, so a
# client can't dodge them by sending its own header.
NUM_PROXIES = int(os.environ.get("NUM_PROXIES", "1"))
NINJA_NUM_PROXIES = NUM_PROXIES

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"line": {"format": "{levelname} {name}: {message}", "style": "{"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "line"}},
    "root": {"handlers": ["console"], "level": "WARNING"},
    "loggers": {name: {"handlers": ["console"], "level": "INFO", "propagate": False} for name in ("talks", "monday", "regs")},
}

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_SSL_REDIRECT = True
    SECURE_REDIRECT_EXEMPT = [r"^api/health/$"]  # Railway's health check calls over plain HTTP
    SECURE_HSTS_SECONDS = 3600  # start small; raise once HTTPS is confirmed on the final domain

# Integrations (set in Railway; leave blank to skip)
ONESIGNAL_APP_ID = os.environ.get("ONESIGNAL_APP_ID", "")
ONESIGNAL_REST_API_KEY = os.environ.get("ONESIGNAL_REST_API_KEY", "")
GHL_PRIVATE_TOKEN = os.environ.get("GHL_PRIVATE_TOKEN", "")
GHL_LOCATION_ID = os.environ.get("GHL_LOCATION_ID", "")
# Shared secret the GoHighLevel workflow sends in the X-ZeroHarm-Key header when publishing to the app
INGEST_KEY = os.environ.get("INGEST_KEY", "")
# OTIS on-device assistant: model names from react-native-executorch
OTIS_ENABLED = os.environ.get("OTIS_ENABLED", "1") == "1"

# Toolbox talks with their text open in the app (with crew sign-in) before their Sunday newsletter. Set to 0 to hold
# every talk until its send time again. The Sunday push still goes out on schedule either way.
TALKS_UNLOCK_EARLY = os.environ.get("TALKS_UNLOCK_EARLY", "1") == "1"

# Monday Minute: the weekly AI-written talk, separate from Zero Harm Weekly.
MONDAY_MINUTE_ENABLED = os.environ.get("MONDAY_MINUTE_ENABLED", "1") == "1"
# Where its AI runs: "local" = your own Ollama server (private network, CPU), "anthropic" = Claude (needs ANTHROPIC_API_KEY).
AI_PROVIDER = os.environ.get("AI_PROVIDER", "local")
LOCAL_AI_URL = os.environ.get("LOCAL_AI_URL", "")            # e.g. http://ollama.railway.internal:11434
LOCAL_AI_MODEL = os.environ.get("LOCAL_AI_MODEL", "qwen3:8b")
LOCAL_AI_TIMEOUT = float(os.environ.get("LOCAL_AI_TIMEOUT", "1800"))  # seconds per call; CPU is slow
LOCAL_AI_REVIEW_MODEL = os.environ.get("LOCAL_AI_REVIEW_MODEL", "")  # optional bigger model for the safety review only, e.g. qwen3:14b
LOCAL_AI_THREADS = int(os.environ.get("LOCAL_AI_THREADS", "0"))      # set to the ollama service's vCPU limit; 0 = let Ollama decide
MONDAY_RAG = os.environ.get("MONDAY_RAG", "1") == "1"  # give the safety reviewer the regulation text and past findings
MONDAY_MODEL = os.environ.get("MONDAY_MODEL", "claude-opus-5-5")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
OTIS_MODEL = os.environ.get("OTIS_MODEL", "QWEN3_1_7B")
OTIS_SMALL_MODEL = os.environ.get("OTIS_SMALL_MODEL", "QWEN3_0_6B")
DATA_UPLOAD_MAX_MEMORY_SIZE = 21 * 1024 * 1024  # sign-in sheets with a group photo

LOGGING = {
    "version": 1,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}
