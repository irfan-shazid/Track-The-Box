"""
Django settings for the Personal Expense Tracker.

Single-user app backed by Neon (serverless Postgres), deployed on Vercel.
"""

import os
import sys
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# On Vercel the filesystem is read-only and there is no .env file; real env
# vars are injected by the platform. load_dotenv() is a no-op if none exists.
load_dotenv(BASE_DIR / ".env")


def env_bool(name, default=False):
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


# --------------------------------------------------------------------------
# Core
# --------------------------------------------------------------------------

SECRET_KEY = os.environ.get("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY is not set. Copy .env.example to .env and fill it in.")

DEBUG = env_bool("DEBUG", False)

ALLOWED_HOSTS = [h.strip() for h in os.environ.get("ALLOWED_HOSTS", "").split(",") if h.strip()]
# Vercel injects the deployment hostname at runtime.
if os.environ.get("VERCEL_URL"):
    ALLOWED_HOSTS.append(os.environ["VERCEL_URL"])
if os.environ.get("VERCEL_PROJECT_PRODUCTION_URL"):
    ALLOWED_HOSTS.append(os.environ["VERCEL_PROJECT_PRODUCTION_URL"])
if DEBUG and not ALLOWED_HOSTS:
    ALLOWED_HOSTS = ["127.0.0.1", "localhost"]

# Django 4+ requires the scheme for CSRF trusted origins.
CSRF_TRUSTED_ORIGINS = [
    f"https://{host}" for host in ALLOWED_HOSTS if host not in {"127.0.0.1", "localhost", "*"}
]
CSRF_TRUSTED_ORIGINS.append("https://*.vercel.app")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "expenses",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# --------------------------------------------------------------------------
# Database — Neon
# --------------------------------------------------------------------------
#
# Neon hands out two connection strings and the difference matters:
#
#   DATABASE_URL         pooled   host contains "-pooler"  -> PgBouncer, transaction mode
#   DATABASE_URL_DIRECT  direct   no "-pooler" in the host -> a real Postgres session
#
# The running app uses the pooled endpoint: serverless functions open and drop
# connections constantly, and PgBouncer absorbs that. Schema work (migrate,
# makemigrations) needs a real session — advisory locks and some DDL do not
# survive transaction pooling — so those commands swap in the direct URL below.
#
# Both endpoints require TLS; Neon refuses plaintext connections, so sslmode=require
# is forced onto whichever URL we end up with.

SCHEMA_COMMANDS = {"migrate", "makemigrations", "sqlmigrate", "squashmigrations", "dbshell"}
USING_DIRECT_DB = bool(set(sys.argv) & SCHEMA_COMMANDS)

_pooled = os.environ.get("DATABASE_URL", "")
_direct = os.environ.get("DATABASE_URL_DIRECT", "")

DATABASE_URL = (_direct or _pooled) if USING_DIRECT_DB else (_pooled or _direct)
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not set. Put your Neon pooled connection string in .env "
        "(and DATABASE_URL_DIRECT for migrations)."
    )

if "sslmode=" not in DATABASE_URL:
    DATABASE_URL += ("&" if "?" in DATABASE_URL else "?") + "sslmode=require"

DATABASES = {
    "default": dj_database_url.parse(
        DATABASE_URL,
        # PgBouncer owns the pooling. Holding connections open on our side just
        # burns Neon compute and starves the pool, so never reuse them.
        conn_max_age=0,
        conn_health_checks=False,
        ssl_require=True,
    )
}

# Server-side cursors (what .iterator() uses) do not survive PgBouncer's
# transaction pooling — the cursor's session is gone by the next statement.
DATABASES["default"]["DISABLE_SERVER_SIDE_CURSORS"] = True

# Neon scales compute to zero after inactivity on the free tier. The first
# request after an idle period pays a few seconds of cold start; give the
# driver room for it instead of failing the request.
DATABASES["default"].setdefault("OPTIONS", {})
DATABASES["default"]["OPTIONS"]["connect_timeout"] = 10

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# --------------------------------------------------------------------------
# Auth — single user, created with createsuperuser. No signup view exists.
# --------------------------------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "login"


# --------------------------------------------------------------------------
# I18N / TZ
# --------------------------------------------------------------------------

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Dhaka"
USE_I18N = True
USE_TZ = True

# Expense.date is a DateField, so "today" is a plain calendar day in Dhaka —
# no UTC drift pushing a late-night expense into the next month.


# --------------------------------------------------------------------------
# Static files — WhiteNoise
# --------------------------------------------------------------------------

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]

# collectstatic writes to staticfiles_build/static/. On Vercel that directory is
# the static-build output, published straight to the CDN, and the "/static/(.*)"
# route in vercel.json serves it before a request ever reaches the function.
# Locally, WhiteNoise serves the same directory when DEBUG is off.
STATIC_ROOT = BASE_DIR / "staticfiles_build" / "static"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    # Compressed, but deliberately NOT the manifest variant: the manifest lives
    # in the static output, which the serverless function never sees, so hashed
    # lookups would fail at runtime.
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}
WHITENOISE_AUTOREFRESH = DEBUG


# --------------------------------------------------------------------------
# App settings
# --------------------------------------------------------------------------

# Currency lives here and in the |money template filter, nowhere else.
CURRENCY_SYMBOL = "\u09f3"  # BDT taka sign
CURRENCY_CODE = "BDT"

MESSAGE_STORAGE = "django.contrib.messages.storage.cookie.CookieStorage"


# --------------------------------------------------------------------------
# Security — on in production, relaxed for local http://
# --------------------------------------------------------------------------

if not DEBUG:
    # Vercel terminates TLS at the edge and forwards this header, so Django can
    # tell an HTTPS request from an HTTP one behind the proxy.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = True

    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"

    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = "same-origin"
    X_FRAME_OPTIONS = "DENY"

    # One year of HSTS. Deliberately no includeSubDomains/preload: those are
    # hard to walk back, and would apply to a custom domain's other subdomains.
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = False
    SECURE_HSTS_PRELOAD = False
