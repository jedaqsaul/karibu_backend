"""
WSGI config for Karibu.

Exposes the WSGI callable as a module-level variable named ``application``.
Production: gunicorn config.wsgi:application --workers 4 --bind 0.0.0.0:8000
"""

import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")
application = get_wsgi_application()
