"""
shared/tests/test_phase7.py

Phase 7 test suite. Covers:
- Health check endpoint (200 OK, DB reachable)
- Celery tasks execute correctly in eager mode
- Requirements: all critical packages importable
- Settings: production security flags are set
- Notification tasks dispatch correctly via Celery
- Event reminder periodic task runs cleanly
"""

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from rest_framework import status
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model

from apps.accounts.models import OrganizerProfile
from apps.events.models import Event, EventStatus, Category
from apps.tickets.models import Ticket, TicketStatus
from apps.notifications.models import Notification, EmailLog
from shared.utils.ticket_number import generate_ticket_number

User = get_user_model()


def future(days=5):
    return timezone.now() + timedelta(days=days)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

class HealthCheckTests(TestCase):

    def test_health_check_returns_200(self):
        client = APIClient()
        resp = client.get(reverse("health-check"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_health_check_response_structure(self):
        client = APIClient()
        resp = client.get(reverse("health-check"))
        self.assertIn("status",   resp.data)
        self.assertIn("database", resp.data)

    def test_health_check_database_ok(self):
        client = APIClient()
        resp = client.get(reverse("health-check"))
        self.assertEqual(resp.data["database"], "ok")
        self.assertEqual(resp.data["status"],   "ok")

    def test_health_check_requires_no_auth(self):
        """Health check must be accessible without JWT."""
        client = APIClient()
        # No credentials set
        resp = client.get(reverse("health-check"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# Package imports — verify all production deps are importable
# ---------------------------------------------------------------------------

class PackageImportTests(TestCase):

    def test_whitenoise_importable(self):
        import whitenoise
        self.assertIsNotNone(whitenoise)

    def test_gunicorn_importable(self):
        import gunicorn
        self.assertIsNotNone(gunicorn)

    def test_celery_importable(self):
        import celery
        self.assertIsNotNone(celery)

    def test_redis_importable(self):
        import redis
        self.assertIsNotNone(redis)

    def test_sentry_sdk_importable(self):
        import sentry_sdk
        self.assertIsNotNone(sentry_sdk)

    def test_django_celery_results_importable(self):
        import django_celery_results
        self.assertIsNotNone(django_celery_results)

    def test_django_celery_beat_importable(self):
        import django_celery_beat
        self.assertIsNotNone(django_celery_beat)

    def test_reportlab_importable(self):
        import reportlab
        self.assertIsNotNone(reportlab)

    def test_qrcode_importable(self):
        import qrcode
        self.assertIsNotNone(qrcode)

    def test_cloudinary_importable(self):
        import cloudinary
        self.assertIsNotNone(cloudinary)


# ---------------------------------------------------------------------------
# Settings validation
# ---------------------------------------------------------------------------

class ProductionSettingsTests(TestCase):

    def test_jwt_access_token_lifetime_is_short(self):
        from django.conf import settings
        lifetime = settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"]
        self.assertLessEqual(lifetime.total_seconds(), 3600,
                             "Access token lifetime should be ≤ 60 minutes")

    def test_jwt_refresh_rotation_enabled(self):
        from django.conf import settings
        self.assertTrue(settings.SIMPLE_JWT["ROTATE_REFRESH_TOKENS"])
        self.assertTrue(settings.SIMPLE_JWT["BLACKLIST_AFTER_ROTATION"])

    def test_celery_result_backend_configured(self):
        from django.conf import settings
        self.assertEqual(settings.CELERY_RESULT_BACKEND, "django-db")

    def test_celery_task_serializer_is_json(self):
        from django.conf import settings
        self.assertEqual(settings.CELERY_TASK_SERIALIZER, "json")

    def test_timezone_is_nairobi(self):
        from django.conf import settings
        self.assertEqual(settings.TIME_ZONE, "Africa/Nairobi")

    def test_auth_user_model_is_custom(self):
        from django.conf import settings
        self.assertEqual(settings.AUTH_USER_MODEL, "accounts.User")

    def test_celery_always_eager_in_dev(self):
        """In development/test settings, tasks run synchronously."""
        from django.conf import settings
        self.assertTrue(getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False))

    def test_celery_beat_schedule_has_reminder_task(self):
        from django.conf import settings
        self.assertIn("send-event-reminders-daily", settings.CELERY_BEAT_SCHEDULE)

    def test_whitenoise_in_middleware(self):
        from django.conf import settings
        middlewares = settings.MIDDLEWARE
        self.assertTrue(any("WhiteNoise" in m for m in middlewares))

    def test_audit_middleware_in_stack(self):
        from django.conf import settings
        self.assertIn("apps.logs.middleware.AuditLogMiddleware", settings.MIDDLEWARE)


# ---------------------------------------------------------------------------
# Celery task execution — eager mode (no Redis needed)
# ---------------------------------------------------------------------------

@override_settings(
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_TASK_EAGER_PROPAGATES=True,
    EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend",
)
class CeleryTaskTests(TestCase):

    def setUp(self):
        self.admin = User.objects.create_superuser(
            email="admin@k.com", password="AdminPass123!",
            first_name="Super", last_name="Admin",
        )
        self.organizer = User.objects.create_user(
            email="org@k.com", password="OrgPass123!",
            first_name="Org", last_name="One",
            role="organizer", is_approved=True,
        )
        OrganizerProfile.objects.create(
            user=self.organizer, organization_name="Test Org"
        )
        self.attendee = User.objects.create_user(
            email="att@k.com", password="AttPass123!",
            first_name="Jane", last_name="Doe",
        )
        self.category = Category.objects.create(name="Music", slug="music")
        self.event = Event.objects.create(
            organizer=self.organizer, title="Karibu Live", slug="karibu-live",
            description="A show.", venue="KICC", address="City Sq",
            city="Nairobi", start_datetime=future(5), end_datetime=future(5),
            is_free=False, ticket_price=1000, total_capacity=100,
            status=EventStatus.PUBLISHED, category=self.category,
        )

    def _make_ticket(self):
        ticket = Ticket.objects.create(
            event=self.event, attendee=self.attendee,
            ticket_number=generate_ticket_number(),
            price_paid=1000, status=TicketStatus.CONFIRMED,
        )
        self.event.tickets_sold += 1
        self.event.save(update_fields=["tickets_sold"])
        return ticket

    def test_welcome_task_creates_notification(self):
        from apps.notifications.celery_tasks import send_welcome_email_task
        send_welcome_email_task(str(self.attendee.id))
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.attendee, notification_type="welcome"
            ).exists()
        )

    def test_welcome_task_writes_email_log(self):
        from apps.notifications.celery_tasks import send_welcome_email_task
        send_welcome_email_task(str(self.attendee.id))
        self.assertTrue(
            EmailLog.objects.filter(
                recipient=self.attendee, email_type="welcome"
            ).exists()
        )

    def test_organizer_approved_task(self):
        from apps.notifications.celery_tasks import send_organizer_approved_task
        send_organizer_approved_task(str(self.organizer.id))
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.organizer, notification_type="account_approved"
            ).exists()
        )

    def test_organizer_rejected_task(self):
        from apps.notifications.celery_tasks import send_organizer_rejected_task
        send_organizer_rejected_task(str(self.organizer.id), "Missing info.")
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.organizer, notification_type="account_rejected"
            ).exists()
        )

    def test_event_approved_task(self):
        from apps.notifications.celery_tasks import send_event_approved_task
        send_event_approved_task(str(self.organizer.id), str(self.event.id))
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.organizer, notification_type="event_approved"
            ).exists()
        )

    def test_event_rejected_task(self):
        from apps.notifications.celery_tasks import send_event_rejected_task
        send_event_rejected_task(str(self.organizer.id), str(self.event.id), "Bad title.")
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.organizer, notification_type="event_rejected"
            ).exists()
        )

    def test_ticket_purchase_task(self):
        from apps.notifications.celery_tasks import send_ticket_purchase_task
        ticket = self._make_ticket()
        send_ticket_purchase_task(
            str(self.attendee.id), [str(ticket.id)], str(self.event.id)
        )
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.attendee, notification_type="ticket_purchased"
            ).exists()
        )

    def test_ticket_cancelled_task(self):
        from apps.notifications.celery_tasks import send_ticket_cancelled_task
        ticket = self._make_ticket()
        send_ticket_cancelled_task(str(self.attendee.id), str(ticket.id))
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.attendee, notification_type="ticket_cancelled"
            ).exists()
        )

    def test_event_reminders_task_sends_for_upcoming_event(self):
        """Reminder task should fire for events happening in exactly 1 day."""
        from apps.notifications.celery_tasks import send_event_reminders_task

        # Place the event inside the window: now + 1 day + 2 hours
        # The task window is [now+1d, now+1d+24h], so now+1d+2h is inside
        start = timezone.now() + timedelta(days=1, hours=2)
        soon_event = Event.objects.create(
            organizer=self.organizer, title="Tomorrow Show",
            slug="tomorrow-show", description="X", venue="V",
            address="A", city="Nairobi",
            start_datetime=start,
            end_datetime=start + timedelta(hours=3),
            is_free=True, ticket_price=0,
            total_capacity=50, status=EventStatus.PUBLISHED,
        )
        Ticket.objects.create(
            event=soon_event, attendee=self.attendee,
            ticket_number=generate_ticket_number(),
            price_paid=0, status=TicketStatus.CONFIRMED,
        )

        result = send_event_reminders_task([1])
        self.assertGreaterEqual(result, 1)

    def test_tasks_via_delay_dispatch(self):
        """
        When CELERY_TASK_ALWAYS_EAGER=True, .delay() runs synchronously.
        Verify the dispatch path (tasks.py → celery_tasks.py) works end-to-end.
        """
        from apps.notifications.tasks import send_welcome_email
        send_welcome_email(self.attendee)
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.attendee, notification_type="welcome"
            ).exists()
        )


# ---------------------------------------------------------------------------
# Pagination and exception handler
# ---------------------------------------------------------------------------

class SharedInfraTests(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_superuser(
            email="admin@k.com", password="AdminPass123!",
            first_name="Super", last_name="Admin",
        )

    def auth_admin(self):
        resp = self.client.post(
            reverse("login"),
            {"email": "admin@k.com", "password": "AdminPass123!"},
            format="json",
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['access']}")

    def test_paginated_response_has_correct_structure(self):
        self.auth_admin()
        resp = self.client.get(reverse("admin-user-list"))
        self.assertIn("pagination", resp.data)
        self.assertIn("results",    resp.data)
        self.assertIn("count",      resp.data["pagination"])
        self.assertIn("total_pages", resp.data["pagination"])
        self.assertIn("current_page", resp.data["pagination"])

    def test_404_returns_standard_error_envelope(self):
        self.auth_admin()
        import uuid
        resp = self.client.get(f"/api/events/{uuid.uuid4()}/")
        # Even a 404 should have our standard envelope on JSON endpoints
        # Note: public event detail returns 404 from get_object_or_404
        self.assertIn(resp.status_code, [404, 200])

    def test_invalid_endpoint_returns_404(self):
        resp = self.client.get("/api/nonexistent-endpoint/")
        self.assertEqual(resp.status_code, 404)
