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
    "support",
    "backoffice",
    "invite",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.gzip.GZipMiddleware",  # the OTIS knowledge base is ~320 KB of JSON; gzip cuts it about 4x
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.http.ConditionalGetMiddleware",  # ETags on GETs: unchanged talks and feeds answer 304
    # Above Common and Csrf, so their refusals (and any 404, 405 or crash further in) reach it: under /api/ an error
    # that would be an HTML page goes out as {"error": ...} JSON like the views' own errors.
    "zeroharm.middleware.ApiJsonErrorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "zeroharm.middleware.AdminLoginLimitMiddleware",  # stops password guessing on /admin/login/
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

# Three caches, each for one kind of thing, so that filling one can never empty another.
# "default": content that is cheap to fetch again (weather, feeds). In memory, per process, 300 entries.
# "limits": ONLY the counters behind rate limits and lockouts (zeroharm.net.ScopedThrottle and every per-network
#   count in the apps). They used to sit in "default", where 300 weather lookups pushed them out and every limit
#   started again from zero. In memory, per process, with room for 100,000 counters. It needs its own LOCATION:
#   two in-memory caches with the same one are the same store. The cron is another process and does not see it:
#   a count the cron and the web service must both see belongs in "shared".
# "shared": lives in the database, so what is in it holds across a restart and is one copy no matter how many
#   processes serve (the Dockerfile runs a single threaded worker today): the console wrong-key count, the admin
#   sign-in counts, and the "already sent" notes the cron keeps for up to 14 days. Its table is made by migration
#   talks/0018 (and createcachetable in the Dockerfile start command). Django's stock size is 300 rows, and when
#   that is passed it deletes a third of the rows that have NOT run out, lowest key first. One wrong admin sign-in
#   writes up to three rows, so about 15 networks guessing could wipe the counts and the notes; hence the room.
#   Do not count with its incr(): it saves the count again for 5 minutes, whatever lifetime the count had.
CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
    "limits": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "limits", "OPTIONS": {"MAX_ENTRIES": 100_000}},
    "shared": {"BACKEND": "django.core.cache.backends.db.DatabaseCache", "LOCATION": "zeroharm_cache", "OPTIONS": {"MAX_ENTRIES": 100_000}},
}

# `manage.py test` empties the "limits" cache before every test, so a limit used up in one test is not still used
# up in the next (zeroharm/testing.py).
TEST_RUNNER = "zeroharm.testing.Runner"

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

# Who is calling (zeroharm/net.py is the one place that reads these). Railway's docs say its edge puts the caller's
# address in the X-Real-IP header. That has not been seen on this service yet: after a deploy, read the "Caller
# address:" line in the web log; the top of zeroharm/net.py says what to set here for each thing it can say.
# The edge also sends X-Forwarded-For, but there the LAST entry is one of the edge's own addresses, which
# changes from request to request, so counting on it mixes strangers together and lets one caller look like many.
# CLIENT_IP_HEADER: the header your host's proxy fills in with the caller's address. Only name a header the proxy
# always writes itself: one it merely passes through could be set by the caller to dodge every limit. Blank = skip it.
# NUM_PROXIES: used only when that header is missing: how many proxies sit in front, to count X-Forwarded-For entries
# from the right (proxies add theirs on the right, so a caller can only add on the left). 0 = ignore X-Forwarded-For
# and use the address of the connection itself.
CLIENT_IP_HEADER = os.environ.get("CLIENT_IP_HEADER", "X-Real-IP").strip()
NUM_PROXIES = int(os.environ.get("NUM_PROXIES", "1"))
# Django Ninja's stock throttles read X-Forwarded-For with this. Kept the same as the fallback above for any that are
# left; new limits use zeroharm.net.ScopedThrottle, which reads the caller through net.client_ip and ignores it.
NINJA_NUM_PROXIES = NUM_PROXIES

# The only LOGGING block (a second one further down used to replace this and switch Django's error log off).
# disable_existing_loggers stays False: Django's and gunicorn's loggers exist before this runs, and switching them off
# meant an HTTP 500 left no trace. Everything goes to the console, which is what Railway collects, as
# "LEVEL logger.name: message"; an unhandled error in a view is written by django.request with its traceback.
# gunicorn.error is not named here, so it keeps the handler gunicorn gave it. gunicorn.access (one line per request)
# is given the same plain output gunicorn uses plus a filter that drops the query string, because
# /backoffice/?key=... and /get/?c=... would otherwise put a secret and contact ids in the log.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"line": {"format": "{levelname} {name}: {message}", "style": "{"}, "bare": {"format": "{message}", "style": "{"}},
    "filters": {"no_query_string": {"()": "zeroharm.logs.NoQueryString"}},
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "line"},
        "access": {"class": "logging.StreamHandler", "stream": "ext://sys.stdout", "formatter": "bare", "filters": ["no_query_string"]},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        # Django gives this one its own handlers (console only in debug, email to nobody otherwise). One handler here,
        # and no passing up to the root, so each line appears once.
        "django": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "gunicorn.access": {"handlers": ["access"], "level": "INFO", "propagate": False},
    },
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
# Bearer key for the local content console (console/ folder). Blank turns the /api/console/ endpoints off.
CONSOLE_KEY = os.environ.get("CONSOLE_KEY", "")
# OTIS on-device assistant: model names from react-native-executorch
OTIS_ENABLED = os.environ.get("OTIS_ENABLED", "1") == "1"

# The next TALKS_EARLY_COUNT talks with their text open in the app (with crew sign-in) before their Sunday newsletter,
# without last week's answer. Set TALKS_UNLOCK_EARLY=0 to hold every talk until its send time again. The Sunday push still goes out on schedule either way.
TALKS_UNLOCK_EARLY = os.environ.get("TALKS_UNLOCK_EARLY", "1") == "1"
TALKS_EARLY_COUNT = int(os.environ.get("TALKS_EARLY_COUNT", "2"))  # how many upcoming talks open early

# The app's look. "auto": phones show the holiday look each December on their own (the first season starts November 10,
# 2026) and go back to normal on January 1. "default" turns the holiday look off now, "holiday" forces it on. No app update needed.
APP_THEME = os.environ.get("APP_THEME", "auto")

# Anonymous usage count: one row per phone per day with an approximate city, state and country, for the back office.
# USAGE_ENABLED=0 stops storing anything (phones still get a normal answer). The network address is never stored.
USAGE_ENABLED = os.environ.get("USAGE_ENABLED", "1") == "1"
# MaxMind-format city database used to turn a network address into an approximate place. The Docker build downloads
# the free DB-IP one here (python manage.py geo_update). Without the file, places from the network are blank.
GEOIP_DB_PATH = os.environ.get("GEOIP_DB_PATH", str(BASE_DIR / "geo" / "dbip-city-lite.mmdb"))
USAGE_KEEP_DAYS = int(os.environ.get("USAGE_KEEP_DAYS", "400"))  # usage_prune deletes older rows; 400 keeps a year-over-year view

# Support tickets and crash reports (support/): problems people report from the app, OTIS answers they flag, and
# errors the app reports by itself. SUPPORT_ENABLED=0 stops storing anything (phones still get a normal answer).
# The network address and the raw install id are never stored.
SUPPORT_ENABLED = os.environ.get("SUPPORT_ENABLED", "1") == "1"
# support_prune deletes single crash reports older than this many days. Tickets and their counts stay. A blank or
# mistyped value means 90; 0 or less means 1 (0 would delete every crash report each hour).
try:
    SUPPORT_CRASH_KEEP_DAYS = max(1, int(os.environ.get("SUPPORT_CRASH_KEEP_DAYS", "").strip() or 90))
except ValueError:
    SUPPORT_CRASH_KEEP_DAYS = 90
# The public address of this server, like https://api.example.com, used to put an "Open it" link to the admin in the
# owner's ticket emails. The cron service has no address of its own, so set the same value on web and cron.
# Blank = no link.
PUBLIC_URL = os.environ.get("PUBLIC_URL", "").strip().rstrip("/")

# Monday Minute: the weekly AI-written talk, separate from Zero Harm Weekly.
MONDAY_MINUTE_ENABLED = os.environ.get("MONDAY_MINUTE_ENABLED", "1") == "1"
# Where its AI runs: "local" = your own Ollama server (private network, CPU), "anthropic" = Claude (needs ANTHROPIC_API_KEY).
AI_PROVIDER = os.environ.get("AI_PROVIDER", "local")
LOCAL_AI_URL = os.environ.get("LOCAL_AI_URL", "")            # e.g. http://ollama.railway.internal:11434
LOCAL_AI_MODEL = os.environ.get("LOCAL_AI_MODEL", "qwen3:8b")
LOCAL_AI_TIMEOUT = float(os.environ.get("LOCAL_AI_TIMEOUT", "1800"))  # seconds per call; CPU is slow
LOCAL_AI_FAST_TIMEOUT = float(os.environ.get("LOCAL_AI_FAST_TIMEOUT", "180"))  # seconds per SHORT call (screening one comment), so a stuck one cannot hold the long wait above
# Seconds of AI work one cron run of monday_minute may use in all; what is not finished carries on in the next run.
# 0 = no ceiling.
MONDAY_STEP_BUDGET = float(os.environ.get("MONDAY_STEP_BUDGET", "1800"))
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
