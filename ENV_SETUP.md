# Karibu Backend — Environment Variables

Copy this into a `.env` file in `karibu_backend/` and fill in the real values. Never commit `.env` to version control — only `.env.example` should be tracked.

```bash
# ============================================================
# Karibu Backend — Environment Variables
# Copy to .env and fill in all values before running.
# NEVER commit .env to version control.
# ============================================================

# Django
DJANGO_SETTINGS_MODULE=config.settings.production
SECRET_KEY=your-50-character-random-secret-key-here

# Database (PostgreSQL)
DATABASE_URL=postgres://user:password@host:5432/karibu_db

# Redis (Celery broker)
REDIS_URL=redis://localhost:6379/0

# Cloudinary
CLOUDINARY_CLOUD_NAME=your_cloud_name
CLOUDINARY_API_KEY=your_api_key
CLOUDINARY_API_SECRET=your_api_secret

# Email (SMTP)
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_HOST_USER=your@gmail.com
EMAIL_HOST_PASSWORD=your_app_password
DEFAULT_FROM_EMAIL=Karibu <no-reply@karibu.co.ke>

# Frontend URL (used in email links)
FRONTEND_URL=https://karibu.co.ke

# M-Pesa (Safaricom Daraja API)
MPESA_ENVIRONMENT=sandbox
MPESA_CONSUMER_KEY=
MPESA_CONSUMER_SECRET=
MPESA_SHORTCODE=174379
MPESA_PASSKEY=
MPESA_CALLBACK_URL=https://your-public-url.example.com/api/payments/mpesa/callback/

# Allowed hosts (comma-separated)
ALLOWED_HOSTS=karibu.co.ke,www.karibu.co.ke

# CORS (comma-separated)
CORS_ALLOWED_ORIGINS=https://karibu.co.ke,https://www.karibu.co.ke

# CSRF (comma-separated)
CSRF_TRUSTED_ORIGINS=https://karibu.co.ke,https://www.karibu.co.ke

# Sentry (optional — leave blank to disable)
SENTRY_DSN=

# Git SHA for Sentry release tracking (set by CI/CD)
GIT_COMMIT_SHA=
```

---

## What's new: M-Pesa variables

| Variable | What it is | Where to get it |
|---|---|---|
| `MPESA_ENVIRONMENT` | `sandbox` or `production` | Use `sandbox` until you're ready to take real payments |
| `MPESA_CONSUMER_KEY` | App-specific API key | Create an app at [developer.safaricom.co.ke](https://developer.safaricom.co.ke) → copy from your app's dashboard |
| `MPESA_CONSUMER_SECRET` | App-specific API secret | Same dashboard, next to the consumer key |
| `MPESA_SHORTCODE` | The paybill/till number STK push charges against | `174379` is Safaricom's public **sandbox** test shortcode — leave as-is until you go live, then swap in your real paybill/till number |
| `MPESA_PASSKEY` | Signs the STK push request | Sandbox passkey is already hardcoded as a fallback in `config/settings/base.py` if you leave this blank — you only need to set it here for production |
| `MPESA_CALLBACK_URL` | Where Safaricom sends the payment result | **Must be a real, publicly reachable HTTPS URL** — `localhost` will never receive anything. For local dev, use an ngrok (or similar) tunnel URL; in production, your real domain |

### Notes

- If `MPESA_CONSUMER_KEY`/`MPESA_CONSUMER_SECRET` are left blank, any STK push attempt fails gracefully with a clear `502` error — it won't crash the app.
- `MPESA_SHORTCODE` and `MPESA_PASSKEY` already default to Safaricom's published sandbox test values in `config/settings/base.py`, so sandbox testing works with just a consumer key/secret set.
- Until `MPESA_CALLBACK_URL` points somewhere Safaricom can actually reach, payments still resolve correctly — the status-polling endpoint (`GET /api/payments/mpesa/<id>/status/`) actively queries Safaricom directly as a fallback. See `apps/payments/services.py` for details.
