# Karibu Backend

Django REST API for the Karibu event ticketing platform — authentication,
event management + approval workflow, ticket purchase/scanning, analytics,
notifications, and an audit log.

## Stack

- **Django 5.2** + **Django REST Framework**
- **SQLite** (local dev, zero setup) / **PostgreSQL** (production, via `DATABASE_URL`)
- **JWT authentication** via `djangorestframework-simplejwt` (access + rotating refresh tokens)
- **Celery** + **Redis** for async tasks (emails, reminders)
- **Cloudinary** for image storage (banners, avatars)
- **WhiteNoise** for static file serving in production
- **gunicorn** as the production WSGI server

---

## Local setup

```bash
cd karibu_backend

# 1. Create a virtualenv (recommended)
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Use the development settings module (SQLite, DEBUG=True, no .env required)
export DJANGO_SETTINGS_MODULE=config.settings.development     # Windows: set DJANGO_SETTINGS_MODULE=config.settings.development

# 4. Run migrations (creates db.sqlite3)
python manage.py migrate

# 5. Create a super admin account (role = super_admin)
python manage.py createsuperuser

# 6. Start the dev server
python manage.py runserver
```

The API is now live at **http://localhost:8000/api/**. Django's built-in
admin site is at `http://localhost:8000/django-admin/`.

> **Note on `DJANGO_SETTINGS_MODULE`:** `manage.py` defaults to
> `config.settings` (the empty package), which has no `ROOT_URLCONF` and
> will fail. Always export `config.settings.development` locally, or
> `config.settings.production` (with a full `.env`, see below) for a
> production-like run.

### Running against real services (optional, for local dev)

By default in `development.py`, Celery/email/Cloudinary calls degrade
gracefully or run synchronously — you don't need Redis or Cloudinary
credentials just to browse the API. If you want the real thing (e.g. to
test async email sending or image uploads through Cloudinary), copy
`.env.example` to `.env` and fill in `REDIS_URL` / `CLOUDINARY_*`, then:

```bash
celery -A config worker --loglevel=info   # in a second terminal
```

### Running tests

```bash
DJANGO_SETTINGS_MODULE=config.settings.development python manage.py test
```

### Seeding sample data

There's no fixture/seed command in this repo yet — after `createsuperuser`,
register an organizer via `POST /api/auth/register/organizer/`, approve
them from an admin session (`POST /api/admin/organizers/<id>/approval/`),
then create + submit an event as that organizer.

---

## Production deployment

All secrets are read from environment variables — see `.env.example` for
the full list. Minimum required for production:

```
SECRET_KEY
DATABASE_URL
REDIS_URL
CLOUDINARY_CLOUD_NAME / CLOUDINARY_API_KEY / CLOUDINARY_API_SECRET
EMAIL_HOST_USER / EMAIL_HOST_PASSWORD
FRONTEND_URL
ALLOWED_HOSTS
CORS_ALLOWED_ORIGINS
CSRF_TRUSTED_ORIGINS
```

```bash
export DJANGO_SETTINGS_MODULE=config.settings.production
python manage.py migrate --no-input
python manage.py collectstatic --no-input
```

Process types (see `Procfile`):

```
web:    gunicorn config.wsgi:application
worker: celery -A config worker --loglevel=warning
beat:   celery -A config beat   --loglevel=warning
```

---

## Authentication

JWT-based, via `djangorestframework-simplejwt`. There is **no cookie
session** — `POST /api/auth/login/` and `POST /api/auth/token/refresh/`
return `access` and `refresh` tokens directly in the JSON body. Send
`Authorization: Bearer <access>` on every authenticated request. Refresh
rotation is enabled: each call to `/auth/token/refresh/` blacklists the
old refresh token and issues a new one — the frontend must persist and
replace it every time.

Three roles: `attendee`, `organizer`, `super_admin`. Organizer accounts
require admin approval (`is_approved`) before their events can go live,
though they can create draft events immediately after registering.

---

## Full route reference

All routes below are prefixed with `/api/`. Auth column: **Public** (no
token needed), **JWT** (any authenticated user), or a specific role.

### Health

| Method | Path | Auth |
|---|---|---|
| GET | `/health/` | Public |

### Auth & account (`apps/accounts`)

| Method | Path | Auth | Notes |
|---|---|---|---|
| POST | `/auth/register/` | Public | Register as attendee |
| POST | `/auth/register/organizer/` | Public | Register as organizer (needs admin approval before going live) |
| POST | `/auth/login/` | Public | Returns `{ access, refresh, user }` |
| POST | `/auth/logout/` | JWT | Body: `{ refresh }` — blacklists it |
| POST | `/auth/token/refresh/` | Public | Body: `{ refresh }` → `{ access, refresh }` (rotation) |
| GET | `/auth/me/` | JWT | Shared profile fields (all roles) |
| PATCH | `/auth/me/` | JWT | Update `first_name`, `last_name`, `phone_number` |
| POST | `/auth/me/avatar/` | JWT | multipart, field `avatar` |
| POST | `/auth/me/change-password/` | JWT | `{ current_password, new_password, new_password_confirm }` |
| POST | `/auth/password-reset/` | Public | `{ email }` |
| POST | `/auth/password-reset/confirm/` | Public | Reset via emailed token |

### Organizer self-service (`apps/accounts`)

| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/organizer/profile/` | Organizer | Org name, bio, website, banner, `is_approved` |
| PATCH | `/organizer/profile/` | Organizer | Update org profile (multipart if uploading `banner_image`) |

### Admin — users (`apps/accounts`)

| Method | Path | Auth |
|---|---|---|
| GET | `/admin/users/` | Super Admin |
| GET | `/admin/users/<uuid:id>/` | Super Admin |
| PATCH | `/admin/users/<uuid:id>/` | Super Admin |
| POST | `/admin/users/<uuid:id>/deactivate/` | Super Admin |
| POST | `/admin/users/<uuid:id>/activate/` | Super Admin |

### Admin — organizer approval (`apps/accounts`)

| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/admin/organizers/pending/` | Super Admin | Organizers awaiting approval |
| POST | `/admin/organizers/<uuid:id>/approval/` | Super Admin | `{ action: "approve" }` or `{ action: "reject", rejection_reason }` — `id` is the **OrganizerProfile** id |

### Public events (`apps/events`)

| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/events/` | Public | Filters: `search`, `category`, `city`, `is_free`, `start_date`, `end_date`, `min_price`, `max_price`, `ordering`, `page`, `page_size` |
| GET | `/events/categories/` | Public | |
| GET | `/events/saved/` | Attendee | Your saved/bookmarked events |
| POST | `/events/<uuid:id>/save/` | Attendee | Toggle save — returns `{ saved: bool }` |
| GET | `/events/<slug:slug>/` | Public | Full event detail |

### Organizer events (`apps/events`)

| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/organizer/events/` | Organizer | Your own events |
| POST | `/organizer/events/create/` | Organizer | Creates a **draft**; multipart if uploading `banner_image` |
| GET | `/organizer/events/<uuid:id>/` | Organizer | |
| PATCH | `/organizer/events/<uuid:id>/` | Organizer | |
| DELETE | `/organizer/events/<uuid:id>/` | Organizer | Only while status is `draft` |
| POST | `/organizer/events/<uuid:id>/submit/` | Organizer | Submit draft for admin review |
| POST | `/organizer/events/<uuid:id>/cancel/` | Organizer | |
| POST | `/organizer/events/<uuid:id>/images/` | Organizer | Upload a gallery image, multipart field `image` |
| DELETE | `/organizer/events/<uuid:id>/images/<uuid:image_id>/` | Organizer | |

### Admin — events & categories (`apps/events`)

| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/admin/events/` | Super Admin | All events |
| GET | `/admin/events/pending/` | Super Admin | Awaiting review |
| GET | `/admin/events/<uuid:id>/` | Super Admin | |
| POST | `/admin/events/<uuid:id>/approval/` | Super Admin | `{ action: "approve" }` or `{ action: "reject", rejection_reason }` |
| GET | `/admin/categories/` | Super Admin | |
| POST | `/admin/categories/` | Super Admin | |
| PATCH | `/admin/categories/<uuid:id>/` | Super Admin | |
| DELETE | `/admin/categories/<uuid:id>/` | Super Admin | |

> There is **one ticket price + one capacity per event** (`ticket_price`,
> `total_capacity`, `is_free`) — no multi-tier "ticket types" model.

### Tickets — attendee (`apps/tickets`)

| Method | Path | Auth | Notes |
|---|---|---|---|
| POST | `/tickets/purchase/` | Attendee | `{ event_id, quantity }` — instant purchase, no payment gateway |
| GET | `/tickets/` | Attendee | Your tickets, paginated |
| GET | `/tickets/<uuid:id>/` | Attendee | |
| GET | `/tickets/<uuid:id>/download/` | Attendee | Ticket PDF |
| POST | `/tickets/<uuid:id>/cancel/` | Attendee | |

### Tickets — organizer (`apps/tickets`)

| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/organizer/events/<uuid:event_id>/tickets/` | Organizer | Attendee list for one of your events |
| POST | `/organizer/tickets/scan/` | Organizer | `{ code, event_id }` — validates + checks in, always returns 200 with `{ valid, result, result_display, ticket }` |

### Tickets — admin (`apps/tickets`)

| Method | Path | Auth |
|---|---|---|
| GET | `/admin/tickets/` | Super Admin |
| GET | `/admin/tickets/<uuid:id>/` | Super Admin |
| POST | `/admin/tickets/<uuid:id>/cancel/` | Super Admin |

### Analytics — organizer (`apps/analytics`)

| Method | Path | Auth |
|---|---|---|
| GET | `/organizer/analytics/summary/` | Organizer |
| GET | `/organizer/analytics/revenue/` | Organizer — params: `period`, `start_date`, `end_date` |
| GET | `/organizer/analytics/events/` | Organizer |
| GET | `/organizer/analytics/events/<uuid:event_id>/` | Organizer |

### Analytics — admin (`apps/analytics`)

| Method | Path | Auth |
|---|---|---|
| GET | `/admin/analytics/summary/` | Super Admin |
| GET | `/admin/analytics/revenue/` | Super Admin — params: `period`, `start_date`, `end_date` |
| GET | `/admin/analytics/tickets/` | Super Admin |
| GET | `/admin/analytics/registrations/` | Super Admin |
| GET | `/admin/analytics/revenue-by-category/` | Super Admin |
| GET | `/admin/analytics/top-events/` | Super Admin |
| GET | `/admin/analytics/top-organizers/` | Super Admin |

### Notifications (`apps/notifications`) — all roles

| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/notifications/` | JWT | Paginated |
| GET | `/notifications/unread-count/` | JWT | |
| POST | `/notifications/mark-read/` | JWT | `{ notification_ids: [...] }` |
| POST | `/notifications/mark-all-read/` | JWT | |
| DELETE | `/notifications/<uuid:id>/` | JWT | |
| DELETE | `/notifications/clear/` | JWT | Deletes **all** of your notifications |

### Admin — audit logs (`apps/logs`)

| Method | Path | Auth |
|---|---|---|
| GET | `/admin/audit-logs/` | Super Admin |
| GET | `/admin/audit-logs/stats/` | Super Admin |
| GET | `/admin/audit-logs/<uuid:id>/` | Super Admin |

### Admin — email logs (`apps/notifications`)

| Method | Path | Auth |
|---|---|---|
| GET | `/admin/email-logs/` | Super Admin |

---

## Known gaps / things intentionally not built

These were found while aligning the frontend to this backend and are
documented here rather than silently patched over:

- **No platform-wide settings model.** Anything like site name, SMTP
  config, or global toggles has no backing table or endpoint — the admin
  "Settings" page in the frontend is local-only and says so.
- **No payment gateway / orders / promo codes.** `POST /tickets/purchase/`
  is a direct, instant purchase. If real payments are ever needed, that's
  a new app, not a tweak to this one.
- **No "featured event" flag.** `Event` has no `is_featured` field.
- **Ticket price is per-event, not per-tier.** If multi-tier ticketing
  (VIP/Regular/Early-bird) is wanted later, that's a new `TicketType`
  model + a migration of `Ticket.price_paid`/`Event.ticket_price`.

## Management commands

```bash
# Send event reminder emails (normally run by Celery Beat)
python manage.py send_event_reminders --days 1 3

# Purge old audit logs
python manage.py purge_audit_logs --days 365 --dry-run
python manage.py purge_audit_logs --days 365
```

## Project structure

```
karibu_backend/
├── config/
│   ├── settings/
│   │   ├── base.py         # shared config
│   │   ├── development.py  # local dev — SQLite, DEBUG=True
│   │   └── production.py   # production — Postgres, security headers
│   ├── celery.py
│   └── urls.py              # root router — mounts every app's urls.py under /api/
├── apps/
│   ├── accounts/            # auth, users, roles, organizer approval + self-profile
│   ├── events/               # event CRUD, approval workflow, saved events
│   ├── tickets/               # purchase, PDF, QR scan/check-in
│   ├── analytics/              # aggregated stats (organizer + admin)
│   ├── notifications/           # in-app + email notifications
│   └── logs/                     # audit trail
├── shared/                        # pagination, exception handling, health check
├── templates/emails/
├── requirements.txt
├── Procfile
└── .env.example
```
# karibu_backend
# karibu
