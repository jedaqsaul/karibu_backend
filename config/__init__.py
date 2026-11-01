# This ensures the Celery app is always imported when Django starts,
# so shared_task decorators use this app.
from .celery import app as celery_app  # noqa: F401

__all__ = ("celery_app",)
