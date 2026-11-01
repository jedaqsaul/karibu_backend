"""
Karibu Platform — Base Settings
Shared across all environments. Never import this directly in production.
"""

import os
import logging
from pathlib import Path
from datetime import timedelta
from decouple import config

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = config("SECRET_KEY", default="change-me-in-production")

DEBUG = False

ALLOWED_HOSTS = []

# ---------------------------------------------------------------------------
# Application definition
# ---------------------------------------------------------------------------

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "cloudinary",
    "cloudinary_storage",
    "django_filters",
    "django_celery_results",
    "django_celery_beat",
]

LOCAL_APPS = [
    "apps.accounts",
    "apps.events",
    "apps.tickets",
    "apps.payments",
    "apps.analytics",
    "apps.notifications",
    "apps.logs",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",              # serve static files efficiently
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.logs.middleware.AuditLogMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# ---------------------------------------------------------------------------
# Custom user model
# ---------------------------------------------------------------------------

AUTH_USER_MODEL = "accounts.User"

# ---------------------------------------------------------------------------
# Password validation
# ---------------------------------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------------------
# Internationalisation
# ---------------------------------------------------------------------------

LANGUAGE_CODE = "en-us"
TIME_ZONE     = "Africa/Nairobi"
USE_I18N      = True
USE_TZ        = True

# ---------------------------------------------------------------------------
# Static & Media
# ---------------------------------------------------------------------------

STATIC_URL  = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

MEDIA_URL  = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Django REST Framework
# ---------------------------------------------------------------------------

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_RENDERER_CLASSES": (
        "rest_framework.renderers.JSONRenderer",
    ),
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_PAGINATION_CLASS": "shared.pagination.KaribuPageNumberPagination",
    "PAGE_SIZE": 20,
    "EXCEPTION_HANDLER": "shared.exceptions.karibu_exception_handler",
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "100/hour",
        "user": "1000/hour",
        "auth": "10/minute",
    },
}

# ---------------------------------------------------------------------------
# Simple JWT
# ---------------------------------------------------------------------------

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME":  timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS":  True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "ALGORITHM":    "HS256",
    "SIGNING_KEY":  config("SECRET_KEY", default="change-me-in-production"),
    "AUTH_HEADER_TYPES":  ("Bearer",),
    "AUTH_HEADER_NAME":   "HTTP_AUTHORIZATION",
    "TOKEN_OBTAIN_SERIALIZER": "apps.accounts.serializers.KaribuTokenObtainPairSerializer",
    "AUTH_COOKIE":            "karibu_access",
    "AUTH_COOKIE_REFRESH":    "karibu_refresh",
    "AUTH_COOKIE_HTTP_ONLY":  True,
    "AUTH_COOKIE_SAMESITE":   "Lax",
}

# ---------------------------------------------------------------------------
# Cloudinary
# ---------------------------------------------------------------------------

CLOUDINARY_STORAGE = {
    "CLOUD_NAME": config("CLOUDINARY_CLOUD_NAME", default=""),
    "API_KEY":    config("CLOUDINARY_API_KEY",    default=""),
    "API_SECRET": config("CLOUDINARY_API_SECRET", default=""),
}

# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------

EMAIL_BACKEND       = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST          = config("EMAIL_HOST",          default="smtp.gmail.com")
EMAIL_PORT          = config("EMAIL_PORT",          default=587, cast=int)
EMAIL_USE_TLS       = True
EMAIL_HOST_USER     = config("EMAIL_HOST_USER",     default="")
EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD", default="")
DEFAULT_FROM_EMAIL  = config("DEFAULT_FROM_EMAIL",  default="Karibu <no-reply@karibu.co.ke>")

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------

CORS_ALLOWED_ORIGINS = config(
    "CORS_ALLOWED_ORIGINS",
    default="http://localhost:5173,http://localhost:3000",
    cast=lambda v: [s.strip() for s in v.split(",")],
)
CORS_ALLOW_CREDENTIALS = True

# ---------------------------------------------------------------------------
# Celery
# ---------------------------------------------------------------------------

CELERY_BROKER_URL    = config("REDIS_URL", default="redis://localhost:6379/0")
CELERY_RESULT_BACKEND = "django-db"
CELERY_CACHE_BACKEND  = "django-cache"

CELERY_TASK_SERIALIZER   = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT    = ["json"]
CELERY_TIMEZONE          = TIME_ZONE
CELERY_TASK_TRACK_STARTED = True

CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"

# Periodic tasks — event reminders at 8 AM EAT daily
from celery.schedules import crontab  # noqa: E402

CELERY_BEAT_SCHEDULE = {
    "send-event-reminders-daily": {
        "task":     "apps.notifications.celery_tasks.send_event_reminders_task",
        "schedule": crontab(hour=8, minute=0),
        "args":     ([1, 3],),   # send reminders for events 1 and 3 days out
    },
}

# ---------------------------------------------------------------------------
# Sentry — error tracking
# ---------------------------------------------------------------------------

SENTRY_DSN = config("SENTRY_DSN", default="")

# ---------------------------------------------------------------------------
# Frontend URL
# ---------------------------------------------------------------------------

FRONTEND_URL = config("FRONTEND_URL", default="http://localhost:5173")

# ---------------------------------------------------------------------------
# M-Pesa (Safaricom Daraja API) — STK Push / Lipa Na M-Pesa Online
# ---------------------------------------------------------------------------
# Sandbox credentials come from https://developer.safaricom.co.ke — create
# an app there to get MPESA_CONSUMER_KEY/SECRET. The values below default to
# Safaricom's publicly documented sandbox test shortcode/passkey so STK push
# works out of the box against the sandbox once you add your own consumer
# key/secret (they're free, no real money moves in sandbox).
#
# MPESA_CALLBACK_URL MUST be a publicly reachable HTTPS URL for Safaricom's
# servers to call — see apps/payments/services.py module docstring for how
# to handle this in local development (tunnel + status-poll fallback).
MPESA_ENVIRONMENT   = config("MPESA_ENVIRONMENT", default="sandbox")  # "sandbox" | "production"
MPESA_CONSUMER_KEY    = config("MPESA_CONSUMER_KEY", default="")
MPESA_CONSUMER_SECRET = config("MPESA_CONSUMER_SECRET", default="")
MPESA_SHORTCODE     = config("MPESA_SHORTCODE", default="174379")  # Safaricom sandbox test shortcode
MPESA_PASSKEY       = config(
    "MPESA_PASSKEY",
    default="bfb279f9aa9bdbcf158e97dd71a467cd2e0c893059b10f78e6b72ada1ed2c919",  # Safaricom's published sandbox passkey
)
MPESA_CALLBACK_URL  = config(
    "MPESA_CALLBACK_URL",
    default="https://example.ngrok-free.app/api/payments/mpesa/callback/",
)
MPESA_BASE_URL = (
    "https://api.safaricom.co.ke" if MPESA_ENVIRONMENT == "production"
    else "https://sandbox.safaricom.co.ke"
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {process:d} {thread:d} {message}",
            "style":  "{",
        },
        "simple": {
            "format": "{levelname} {asctime} {message}",
            "style":  "{",
        },
    },
    "filters": {
        "require_debug_false": {"()": "django.utils.log.RequireDebugFalse"},
        "require_debug_true":  {"()": "django.utils.log.RequireDebugTrue"},
    },
    "handlers": {
        "console": {
            "class":     "logging.StreamHandler",
            "formatter": "simple",
        },
        "console_verbose": {
            "class":     "logging.StreamHandler",
            "formatter": "verbose",
        },
        "null": {
            "class": "logging.NullHandler",
        },
    },
    "loggers": {
        "django": {
            "handlers":  ["console"],
            "level":     "WARNING",
            "propagate": True,
        },
        "django.security": {
            "handlers":  ["console_verbose"],
            "level":     "ERROR",
            "propagate": False,
        },
        "karibu.api": {
            "handlers":  ["console_verbose"],
            "level":     "WARNING",
            "propagate": False,
        },
        "karibu.audit": {
            "handlers":  ["console"],
            "level":     "INFO",
            "propagate": False,
        },
        "karibu.notifications": {
            "handlers":  ["console"],
            "level":     "INFO",
            "propagate": False,
        },
        "karibu.tickets": {
            "handlers":  ["console"],
            "level":     "INFO",
            "propagate": False,
        },
        "celery": {
            "handlers":  ["console"],
            "level":     "INFO",
            "propagate": True,
        },
    },
    "root": {
        "handlers": ["console"],
        "level":    "WARNING",
    },
}
