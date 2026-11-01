"""
Karibu Platform — Production Settings
All secrets come from environment variables. Nothing is hardcoded here.
"""

import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration
from sentry_sdk.integrations.celery import CeleryIntegration
from decouple import config
import dj_database_url
from .base import *  # noqa: F401, F403

DEBUG = False

ALLOWED_HOSTS = config(
    "ALLOWED_HOSTS",
    default="karibu.co.ke,www.karibu.co.ke",
    cast=lambda v: [s.strip() for s in v.split(",")],
)

# ---------------------------------------------------------------------------
# Database — PostgreSQL
# ---------------------------------------------------------------------------

DATABASES = {
    "default": dj_database_url.config(
        default=config("DATABASE_URL"),
        conn_max_age=600,
        ssl_require=True,
    )
}

# ---------------------------------------------------------------------------
# Cloudinary — production media storage
# ---------------------------------------------------------------------------

DEFAULT_FILE_STORAGE = "cloudinary_storage.storage.MediaCloudinaryStorage"

# ---------------------------------------------------------------------------
# Security hardening
# ---------------------------------------------------------------------------

SECURE_SSL_REDIRECT             = True
SECURE_HSTS_SECONDS             = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS  = True
SECURE_HSTS_PRELOAD             = True
SECURE_CONTENT_TYPE_NOSNIFF     = True
SECURE_BROWSER_XSS_FILTER       = True
X_FRAME_OPTIONS                 = "DENY"
SESSION_COOKIE_SECURE           = True
SESSION_COOKIE_HTTPONLY         = True
CSRF_COOKIE_SECURE              = True
CSRF_COOKIE_HTTPONLY            = True
CSRF_TRUSTED_ORIGINS = config(
    "CSRF_TRUSTED_ORIGINS",
    default="https://karibu.co.ke,https://www.karibu.co.ke",
    cast=lambda v: [s.strip() for s in v.split(",")],
)

# ---------------------------------------------------------------------------
# Logging — structured JSON-ready logs for production (stdout → log aggregator)
# ---------------------------------------------------------------------------

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "production": {
            "format": '{"time": "%(asctime)s", "level": "%(levelname)s", '
                      '"logger": "%(name)s", "message": %(message)s}',
        },
    },
    "handlers": {
        "console": {
            "class":     "logging.StreamHandler",
            "formatter": "production",
        },
    },
    "loggers": {
        "django":               {"handlers": ["console"], "level": "ERROR",   "propagate": False},
        "django.security":      {"handlers": ["console"], "level": "ERROR",   "propagate": False},
        "karibu.api":           {"handlers": ["console"], "level": "ERROR",   "propagate": False},
        "karibu.audit":         {"handlers": ["console"], "level": "INFO",    "propagate": False},
        "karibu.notifications": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "karibu.tickets":       {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "celery":               {"handlers": ["console"], "level": "WARNING", "propagate": False},
    },
    "root": {"handlers": ["console"], "level": "ERROR"},
}

# ---------------------------------------------------------------------------
# Sentry — error tracking
# ---------------------------------------------------------------------------

if SENTRY_DSN:  # noqa: F405
    sentry_sdk.init(
        dsn=SENTRY_DSN,                # noqa: F405
        integrations=[
            DjangoIntegration(transaction_style="url"),
            CeleryIntegration(),
        ],
        traces_sample_rate=0.1,        # 10% of requests traced for performance
        send_default_pii=False,        # never send PII to Sentry
        environment="production",
        release=config("GIT_COMMIT_SHA", default="unknown"),
    )
