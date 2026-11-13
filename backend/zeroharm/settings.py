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
    "usage",
    "backoffice",
    "invite",
    "legal",
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
    "backoffice.middleware.GhlFrameMiddleware",  # below XFrameOptions, so it can lift the frame ban for GoHighLevel
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
# Where the owner's alerts go: an email the minute someone signs up or removes their sign-up, and one summary a day
# of new phones. Sent through GoHighLevel with the token above. Blank = no alerts.
OWNER_ALERT_EMAIL = os.environ.get("OWNER_ALERT_EMAIL", "").strip()
# Shared secret the GoHighLevel workflow sends in the X-ZeroHarm-Key header when publishing to the app
INGEST_KEY = os.environ.get("INGEST_KEY", "")
# Back office inside GoHighLevel: /backoffice/?key=<BACKOFFICE_KEY> as a GHL custom menu link (see README).
BACKOFFICE_KEY = os.environ.get("BACKOFFICE_KEY", "")
GHL_FRAME_ANCESTORS = ["https://app.gohighlevel.com", "https://*.gohighlevel.com", "https://app.leadconnectorhq.com", "https://*.leadconnectorhq.com"] + [
    h.strip() for h in os.environ.get("GHL_APP_DOMAINS", "").split(",") if h.strip()  # your white-label app address, e.g. https://app.yourbrand.com
]
# Show the Django admin inside GoHighLevel too. Needs login cookies that work inside a frame (SameSite=None); Safari
# and some Chrome setups block those, so the safer default is off: the dashboard's admin links open in a new tab.
GHL_EMBED_ADMIN = os.environ.get("GHL_EMBED_ADMIN", "0") == "1"
if GHL_EMBED_ADMIN and not DEBUG:
    SESSION_COOKIE_SAMESITE = "None"
    CSRF_COOKIE_SAMESITE = "None"
# The invite link (/get/): where phones are sent once the app is in the stores. Blank = that store isn't live yet, and
# the page says "coming soon". Set them on Railway once the app is approved; no app update needed.
APP_STORE_URL = os.environ.get("APP_STORE_URL", "").strip()
PLAY_STORE_URL = os.environ.get("PLAY_STORE_URL", "").strip()
# OTIS on-device assistant: model names from react-native-executorch
OTIS_ENABLED = os.environ.get("OTIS_ENABLED", "1") == "1"

# The next TALKS_EARLY_COUNT talks with their text open in the app (with crew sign-in) before their Sunday newsletter,
# without last week's answer. Set TALKS_UNLOCK_EARLY=0 to hold every talk until its send time again. The Sunday push still goes out on schedule either way.
TALKS_UNLOCK_EARLY = os.environ.get("TALKS_UNLOCK_EARLY", "1") == "1"
TALKS_EARLY_COUNT = int(os.environ.get("TALKS_EARLY_COUNT", "2"))  # how many upcoming talks open early

# The app's look. "auto": phones show the holiday look each December on their own (the first season starts November 10,
# 2026) and go back to normal on January 1. "default" turns the holiday look off now, "holiday" forces it on. No app update needed.
APP_THEME = os.environ.get("APP_THEME", "auto")

# Daily usage count: one row per phone per day with an approximate city, state and country, for the back office.
# USAGE_ENABLED=0 stops storing anything (phones still get a normal answer). The network address is never stored.
USAGE_ENABLED = os.environ.get("USAGE_ENABLED", "1") == "1"
# MaxMind-format city database used to turn a network address into an approximate place. The Docker build downloads
# the free DB-IP one here (python manage.py geo_update). Without the file, places from the network are blank.
GEOIP_DB_PATH = os.environ.get("GEOIP_DB_PATH", str(BASE_DIR / "geo" / "dbip-city-lite.mmdb"))
USAGE_KEEP_DAYS = int(os.environ.get("USAGE_KEEP_DAYS", "400"))  # usage_prune deletes older rows; 400 keeps a year-over-year view

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
# Safety gate (monday/gate.py): talks publish on their own only after this AI setup passes the safety test.
MONDAY_GATE = os.environ.get("MONDAY_GATE", "1") == "1"
MONDAY_GATE_MIN_CATCH = float(os.environ.get("MONDAY_GATE_MIN_CATCH", "0.9"))              # planted mistakes caught
MONDAY_GATE_MAX_FALSE_BLOCK = float(os.environ.get("MONDAY_GATE_MAX_FALSE_BLOCK", "0.34"))  # good talks wrongly blocked
MONDAY_GATE_MIN_CASES = int(os.environ.get("MONDAY_GATE_MIN_CASES", "20"))                 # planted mistakes tested
MONDAY_GATE_MAX_ERRORS = float(os.environ.get("MONDAY_GATE_MAX_ERRORS", "0.1"))            # share of calls that failed
MONDAY_GATE_MAX_AGE_DAYS = int(os.environ.get("MONDAY_GATE_MAX_AGE_DAYS", "90"))           # a pass this old must be redone
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
