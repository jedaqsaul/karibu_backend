"""
Karibu Platform — Development Settings
"""

import sys
from .base import *  # noqa: F401, F403

DEBUG = True

ALLOWED_HOSTS = ["*"]

# ---------------------------------------------------------------------------
# Database — SQLite for local development
# ---------------------------------------------------------------------------

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",  # noqa: F405
    }
}

# ---------------------------------------------------------------------------
# Email — print to console
# ---------------------------------------------------------------------------

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# ---------------------------------------------------------------------------
# Media — local filesystem (no Cloudinary in dev)
# ---------------------------------------------------------------------------

DEFAULT_FILE_STORAGE = "django.core.files.storage.FileSystemStorage"

# ---------------------------------------------------------------------------
# Static files — simple storage in development
# ---------------------------------------------------------------------------

STATICFILES_STORAGE = "django.contrib.staticfiles.storage.StaticFilesStorage"

# ---------------------------------------------------------------------------
# DRF — enable browsable API in dev
# ---------------------------------------------------------------------------

REST_FRAMEWORK = {           # noqa: F405
    **REST_FRAMEWORK,        # noqa: F405
    "DEFAULT_RENDERER_CLASSES": (
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ),
}

# ---------------------------------------------------------------------------
# CORS — allow everything in development
# ---------------------------------------------------------------------------

CORS_ALLOW_ALL_ORIGINS = True

# ---------------------------------------------------------------------------
# Test overrides — disable throttling during test runs
# ---------------------------------------------------------------------------

if "test" in sys.argv:
    REST_FRAMEWORK = {
        **REST_FRAMEWORK,
        "DEFAULT_THROTTLE_CLASSES": [],
        "DEFAULT_THROTTLE_RATES":   {},
    }
    # Use sync email in tests (already console, but make explicit)
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# ---------------------------------------------------------------------------
# Celery — run tasks synchronously in development (no Redis required)
# ---------------------------------------------------------------------------

CELERY_TASK_ALWAYS_EAGER  = True   # tasks run inline, no worker needed
CELERY_TASK_EAGER_PROPAGATES = True
