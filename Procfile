# Render / Railway / Heroku Procfile
web:     gunicorn config.wsgi:application --workers 4 --worker-class sync --bind 0.0.0.0:$PORT --timeout 120 --log-level warning
worker:  celery -A config worker --loglevel=warning --concurrency=4
beat:    celery -A config beat   --loglevel=warning --scheduler django_celery_beat.schedulers:DatabaseScheduler
