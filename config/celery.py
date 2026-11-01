"""
config/celery.py

Celery application instance for Karibu.
Import this in __init__.py so Django auto-discovers tasks.

Worker start command (production):
  celery -A config worker --loglevel=info --concurrency=4

Beat scheduler start command (production):
  celery -A config beat --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler
"""

import os
from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

app = Celery("karibu")

# Read Celery config from Django settings under the CELERY_ namespace
app.config_from_object("django.conf:settings", namespace="CELERY")

# Auto-discover tasks in all installed apps
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """Sanity-check task. Run: celery -A config call config.celery.debug_task"""
    print(f"Request: {self.request!r}")
