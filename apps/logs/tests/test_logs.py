"""
logs/tests/test_logs.py

Phase 6 test suite. Covers:
- log_action() creates correct records with user_email snapshot and category
- Signals auto-log User, Event, Ticket state changes
- AuditLog API: list, filter, detail, stats
- Purge management command (dry-run and actual delete)
- Permission enforcement — admin only
"""

from datetime import timedelta
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model

from apps.accounts.models import OrganizerProfile
from apps.events.models import Event, EventStatus, Category
from apps.tickets.models import Ticket, TicketStatus
from apps.logs.models import AuditLog
from apps.logs.utils import log_action
from shared.utils.ticket_number import generate_ticket_number

User = get_user_model()


def future(days=10):
    return timezone.now() + timedelta(days=days)


class LogTestBase(TestCase):
    def setUp(self):
        self.client = APIClient()

        self.admin = User.objects.create_superuser(
            email="admin@k.com", password="AdminPass123!",
            first_name="Super", last_name="Admin",
        )
        self.organizer = User.objects.create_user(
            email="org@k.com", password="OrgPass123!",
            first_name="Org", last_name="One",
            role="organizer", is_approved=True,
        )
        OrganizerProfile.objects.create(user=self.organizer, organization_name="Org Ltd")

        self.attendee = User.objects.create_user(
            email="att@k.com", password="AttPass123!",
            first_name="Jane", last_name="Doe",
        )
        self.category = Category.objects.create(name="Music", slug="music")

    def auth(self, user, password="AttPass123!"):
        resp = self.client.post(
            reverse("login"),
            {"email": user.email, "password": password},
            format="json",
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['access']}")


# ---------------------------------------------------------------------------
# log_action() unit tests
# ---------------------------------------------------------------------------

class LogActionTests(LogTestBase):

    def test_log_action_creates_record(self):
        log_action(self.attendee, "LOGIN", "User logged in.")
        self.assertTrue(
            AuditLog.objects.filter(user=self.attendee, action="LOGIN").exists()
        )

    def test_log_action_snapshots_user_email(self):
        log_action(self.attendee, "LOGIN")
        log = AuditLog.objects.get(user=self.attendee, action="LOGIN")
        self.assertEqual(log.user_email, self.attendee.email)

    def test_log_action_snapshots_user_role(self):
        log_action(self.attendee, "LOGIN")
        log = AuditLog.objects.get(user=self.attendee, action="LOGIN")
        self.assertEqual(log.user_role, "attendee")

    def test_log_action_auto_categorises_auth_actions(self):
        log_action(self.attendee, "LOGIN")
        log = AuditLog.objects.get(user=self.attendee, action="LOGIN")
        self.assertEqual(log.category, AuditLog.ActionCategory.AUTH)

    def test_log_action_auto_categorises_event_actions(self):
        log_action(self.organizer, "EVENT_CREATED", "Created an event.")
        log = AuditLog.objects.get(user=self.organizer, action="EVENT_CREATED")
        self.assertEqual(log.category, AuditLog.ActionCategory.EVENT)

    def test_log_action_auto_categorises_admin_actions(self):
        log_action(self.admin, "EVENT_APPROVED")
        log = AuditLog.objects.get(user=self.admin, action="EVENT_APPROVED")
        self.assertEqual(log.category, AuditLog.ActionCategory.ADMIN)

    def test_log_action_with_none_user(self):
        """System actions don't have a user — must not raise."""
        log_action(None, "SYSTEM", "System action.")
        self.assertTrue(AuditLog.objects.filter(action="SYSTEM").exists())

    def test_log_action_records_content_type_and_object_id(self):
        log_action(
            self.attendee, "TICKET_PURCHASED",
            content_type="Ticket", object_id="abc-123",
        )
        log = AuditLog.objects.get(action="TICKET_PURCHASED", user=self.attendee)
        self.assertEqual(log.content_type, "Ticket")
        self.assertEqual(log.object_id, "abc-123")

    def test_log_action_never_raises_on_bad_input(self):
        """Must be silent even if something unexpected is passed."""
        try:
            log_action(None, "X" * 200)  # action too long — db will truncate or error
        except Exception:
            self.fail("log_action raised an exception")


# ---------------------------------------------------------------------------
# Signal tests — automatic logging on model state changes
# ---------------------------------------------------------------------------

class SignalLoggingTests(LogTestBase):

    def _make_event(self, status=EventStatus.DRAFT):
        return Event.objects.create(
            organizer=self.organizer, title="Signal Test Event",
            slug="signal-test", description="X", venue="V",
            address="A", city="Nairobi",
            start_datetime=future(5), end_datetime=future(5),
            is_free=False, ticket_price=500,
            total_capacity=100, status=status,
        )

    def test_signal_logs_event_creation(self):
        initial_count = AuditLog.objects.filter(action="EVENT_CREATED").count()
        self._make_event()
        self.assertGreater(
            AuditLog.objects.filter(action="EVENT_CREATED").count(),
            initial_count,
        )

    def test_signal_logs_event_status_change_to_published(self):
        event = self._make_event(status=EventStatus.PENDING_APPROVAL)
        AuditLog.objects.all().delete()  # clear creation log
        event.status = EventStatus.PUBLISHED
        event.save(update_fields=["status"])
        self.assertTrue(
            AuditLog.objects.filter(action="EVENT_APPROVED").exists()
        )

    def test_signal_logs_event_cancellation(self):
        event = self._make_event(status=EventStatus.PUBLISHED)
        AuditLog.objects.all().delete()
        event.status = EventStatus.CANCELLED
        event.save(update_fields=["status"])
        self.assertTrue(
            AuditLog.objects.filter(action="EVENT_CANCELLED").exists()
        )

    def test_signal_logs_ticket_creation(self):
        event = self._make_event(status=EventStatus.PUBLISHED)
        AuditLog.objects.all().delete()
        Ticket.objects.create(
            event=event, attendee=self.attendee,
            ticket_number=generate_ticket_number(),
            price_paid=500, status=TicketStatus.CONFIRMED,
        )
        self.assertTrue(
            AuditLog.objects.filter(action="TICKET_PURCHASED").exists()
        )

    def test_signal_logs_ticket_used(self):
        event = self._make_event(status=EventStatus.PUBLISHED)
        ticket = Ticket.objects.create(
            event=event, attendee=self.attendee,
            ticket_number=generate_ticket_number(),
            price_paid=500, status=TicketStatus.CONFIRMED,
        )
        AuditLog.objects.all().delete()
        ticket.status = TicketStatus.USED
        ticket.save(update_fields=["status"])
        self.assertTrue(
            AuditLog.objects.filter(action="TICKET_USED").exists()
        )

    def test_signal_logs_ticket_cancellation(self):
        event = self._make_event(status=EventStatus.PUBLISHED)
        ticket = Ticket.objects.create(
            event=event, attendee=self.attendee,
            ticket_number=generate_ticket_number(),
            price_paid=500, status=TicketStatus.CONFIRMED,
        )
        AuditLog.objects.all().delete()
        ticket.status = TicketStatus.CANCELLED
        ticket.save(update_fields=["status"])
        self.assertTrue(
            AuditLog.objects.filter(action="TICKET_CANCELLED").exists()
        )

    def test_signal_logs_user_deactivation(self):
        AuditLog.objects.all().delete()
        self.attendee.is_active = False
        self.attendee.save(update_fields=["is_active"])
        self.assertTrue(
            AuditLog.objects.filter(action="USER_DEACTIVATE").exists()
        )


# ---------------------------------------------------------------------------
# Audit log API
# ---------------------------------------------------------------------------

class AuditLogAPITests(LogTestBase):

    def _seed_logs(self):
        log_action(self.attendee, "LOGIN",         "Logged in.")
        log_action(self.organizer, "EVENT_CREATED", "Created an event.")
        log_action(self.admin,    "EVENT_APPROVED", "Approved an event.")

    def test_admin_can_list_audit_logs(self):
        self._seed_logs()
        self.auth(self.admin, "AdminPass123!")
        resp = self.client.get(reverse("admin-audit-log-list"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(resp.data["pagination"]["count"], 3)

    def test_audit_log_response_structure(self):
        log_action(self.attendee, "LOGIN")
        self.auth(self.admin, "AdminPass123!")
        resp = self.client.get(reverse("admin-audit-log-list"))
        row = resp.data["results"][0]
        self.assertIn("action",      row)
        self.assertIn("category",    row)
        self.assertIn("user_email",  row)
        self.assertIn("created_at",  row)

    def test_filter_by_action(self):
        self._seed_logs()
        self.auth(self.admin, "AdminPass123!")
        resp = self.client.get(reverse("admin-audit-log-list"), {"action": "LOGIN"})
        for row in resp.data["results"]:
            self.assertEqual(row["action"], "LOGIN")

    def test_filter_by_category(self):
        self._seed_logs()
        self.auth(self.admin, "AdminPass123!")
        resp = self.client.get(reverse("admin-audit-log-list"), {"category": "auth"})
        for row in resp.data["results"]:
            self.assertEqual(row["category"], "auth")

    def test_filter_by_user_email(self):
        self._seed_logs()
        self.auth(self.admin, "AdminPass123!")
        resp = self.client.get(
            reverse("admin-audit-log-list"), {"user_email": "att@k.com"}
        )
        for row in resp.data["results"]:
            self.assertIn("att@k.com", row["user_email"])

    def test_search_filter(self):
        log_action(self.attendee, "LOGIN", "User logged in from mobile.")
        self.auth(self.admin, "AdminPass123!")
        resp = self.client.get(
            reverse("admin-audit-log-list"), {"search": "mobile"}
        )
        self.assertGreaterEqual(resp.data["pagination"]["count"], 1)

    def test_date_range_filter(self):
        log_action(self.attendee, "LOGIN")
        self.auth(self.admin, "AdminPass123!")
        today = timezone.now().date().isoformat()
        resp = self.client.get(
            reverse("admin-audit-log-list"),
            {"start_date": today, "end_date": today},
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_invalid_date_range_returns_400(self):
        self.auth(self.admin, "AdminPass123!")
        resp = self.client.get(
            reverse("admin-audit-log-list"),
            {"start_date": "2025-12-31", "end_date": "2025-01-01"},
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_admin_can_view_single_log_entry(self):
        log_action(self.attendee, "LOGIN")
        log = AuditLog.objects.filter(action="LOGIN").first()
        self.auth(self.admin, "AdminPass123!")
        resp = self.client.get(
            reverse("admin-audit-log-detail", kwargs={"id": log.id})
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["action"], "LOGIN")

    def test_nonexistent_log_returns_404(self):
        self.auth(self.admin, "AdminPass123!")
        import uuid
        resp = self.client.get(
            reverse("admin-audit-log-detail", kwargs={"id": uuid.uuid4()})
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_audit_log_stats_endpoint(self):
        self._seed_logs()
        self.auth(self.admin, "AdminPass123!")
        resp = self.client.get(reverse("admin-audit-log-stats"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("total_entries", resp.data)
        self.assertIn("by_category",   resp.data)
        self.assertIn("top_actions",   resp.data)
        self.assertGreater(resp.data["total_entries"], 0)

    def test_attendee_cannot_access_audit_logs(self):
        self.auth(self.attendee)
        resp = self.client.get(reverse("admin-audit-log-list"))
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_organizer_cannot_access_audit_logs(self):
        self.auth(self.organizer, "OrgPass123!")
        resp = self.client.get(reverse("admin-audit-log-list"))
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_cannot_access_audit_logs(self):
        resp = self.client.get(reverse("admin-audit-log-list"))
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)


# ---------------------------------------------------------------------------
# Purge management command
# ---------------------------------------------------------------------------

class PurgeCommandTests(LogTestBase):

    def test_dry_run_does_not_delete(self):
        log_action(self.attendee, "LOGIN")
        # Force the created_at to be old
        old_time = timezone.now() - timedelta(days=400)
        AuditLog.objects.filter(action="LOGIN").update(created_at=old_time)

        from django.core.management import call_command
        from io import StringIO
        out = StringIO()
        call_command("purge_audit_logs", "--days", "365", "--dry-run", stdout=out)

        # Entry should still exist
        self.assertTrue(AuditLog.objects.filter(action="LOGIN").exists())
        self.assertIn("DRY RUN", out.getvalue())

    def test_purge_deletes_old_entries(self):
        log_action(self.attendee, "LOGIN")
        old_time = timezone.now() - timedelta(days=400)
        AuditLog.objects.filter(action="LOGIN").update(created_at=old_time)

        count_before = AuditLog.objects.count()

        from django.core.management import call_command
        from io import StringIO
        call_command("purge_audit_logs", "--days", "365", stdout=StringIO())

        self.assertLess(AuditLog.objects.count(), count_before)

    def test_purge_preserves_recent_entries(self):
        log_action(self.attendee, "LOGIN")  # recent — should survive

        from django.core.management import call_command
        from io import StringIO
        call_command("purge_audit_logs", "--days", "365", stdout=StringIO())

        # Recent LOGIN should still be there
        self.assertTrue(
            AuditLog.objects.filter(action="LOGIN", user=self.attendee).exists()
        )
