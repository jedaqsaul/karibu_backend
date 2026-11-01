"""
notifications/tests/test_notifications.py

Phase 5 test suite. Covers:
- NotificationService creates in-app records for all event types
- Email rendering does not raise (console backend in test)
- EmailLog is written for every dispatch attempt
- Notification inbox API: list, unread count, mark read, delete, clear
- Admin email log endpoint
- Permission enforcement
- Edge cases: double mark-read, mark non-owned notifications
"""

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model
from datetime import timedelta

from apps.accounts.models import OrganizerProfile
from apps.events.models import Event, EventStatus, Category
from apps.tickets.models import Ticket, TicketStatus
from apps.notifications.models import Notification, NotificationType, EmailLog
from apps.notifications.services import NotificationService
from shared.utils.ticket_number import generate_ticket_number

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def future(days=10):
    return timezone.now() + timedelta(days=days)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend")
class NotificationTestBase(TestCase):
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
        OrganizerProfile.objects.create(
            user=self.organizer, organization_name="Test Events Ltd"
        )
        self.attendee = User.objects.create_user(
            email="att@k.com", password="AttPass123!",
            first_name="Jane", last_name="Doe",
        )
        self.attendee2 = User.objects.create_user(
            email="att2@k.com", password="AttPass123!",
            first_name="John", last_name="Smith",
        )

        self.category = Category.objects.create(name="Music", slug="music")
        self.event = Event.objects.create(
            organizer=self.organizer, title="Karibu Live", slug="karibu-live",
            description="A great show.", venue="KICC", address="City Square",
            city="Nairobi", start_datetime=future(5), end_datetime=future(5),
            is_free=False, ticket_price=1000, total_capacity=100,
            status=EventStatus.PUBLISHED, category=self.category,
        )

    def auth(self, user, password="AttPass123!"):
        resp = self.client.post(
            reverse("login"),
            {"email": user.email, "password": password},
            format="json",
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['access']}")

    def make_ticket(self, attendee=None):
        attendee = attendee or self.attendee
        ticket = Ticket.objects.create(
            event=self.event, attendee=attendee,
            ticket_number=generate_ticket_number(),
            price_paid=self.event.ticket_price,
            status=TicketStatus.CONFIRMED,
        )
        self.event.tickets_sold += 1
        self.event.save(update_fields=["tickets_sold"])
        return ticket


# ---------------------------------------------------------------------------
# NotificationService — in-app record creation
# ---------------------------------------------------------------------------

@override_settings(EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend")
class NotificationServiceRecordTests(NotificationTestBase):

    def test_welcome_creates_notification(self):
        NotificationService.welcome(self.attendee)
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.attendee,
                notification_type=NotificationType.WELCOME,
            ).exists()
        )

    def test_organizer_welcome_creates_notification(self):
        NotificationService.welcome(self.organizer)
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.organizer,
                notification_type=NotificationType.WELCOME,
            ).exists()
        )

    def test_organizer_approved_creates_notification(self):
        NotificationService.organizer_approved(self.organizer)
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.organizer,
                notification_type=NotificationType.ACCOUNT_APPROVED,
            ).exists()
        )

    def test_organizer_rejected_creates_notification(self):
        NotificationService.organizer_rejected(self.organizer, reason="Missing info.")
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.organizer,
                notification_type=NotificationType.ACCOUNT_REJECTED,
            ).exists()
        )

    def test_event_approved_creates_notification(self):
        NotificationService.event_approved(self.organizer, self.event)
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.organizer,
                notification_type=NotificationType.EVENT_APPROVED,
            ).exists()
        )

    def test_event_rejected_creates_notification(self):
        NotificationService.event_rejected(self.organizer, self.event, reason="Bad title.")
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.organizer,
                notification_type=NotificationType.EVENT_REJECTED,
            ).exists()
        )

    def test_ticket_purchased_creates_notification(self):
        ticket = self.make_ticket()
        NotificationService.ticket_purchased(self.attendee, [ticket], self.event)
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.attendee,
                notification_type=NotificationType.TICKET_PURCHASED,
            ).exists()
        )

    def test_ticket_cancelled_creates_notification(self):
        ticket = self.make_ticket()
        NotificationService.ticket_cancelled(self.attendee, ticket)
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.attendee,
                notification_type=NotificationType.TICKET_CANCELLED,
            ).exists()
        )

    def test_event_reminder_creates_notification(self):
        ticket = self.make_ticket()
        NotificationService.event_reminder(ticket)
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.attendee,
                notification_type=NotificationType.EVENT_REMINDER,
            ).exists()
        )

    def test_event_cancelled_notifies_all_attendees(self):
        ticket1 = self.make_ticket(attendee=self.attendee)
        ticket2 = self.make_ticket(attendee=self.attendee2)
        NotificationService.event_cancelled_to_attendees(self.event)
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.attendee,
                notification_type=NotificationType.EVENT_CANCELLED,
            ).exists()
        )
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.attendee2,
                notification_type=NotificationType.EVENT_CANCELLED,
            ).exists()
        )

    def test_notification_is_unread_by_default(self):
        NotificationService.welcome(self.attendee)
        notif = Notification.objects.get(
            recipient=self.attendee, notification_type=NotificationType.WELCOME
        )
        self.assertFalse(notif.is_read)
        self.assertIsNone(notif.read_at)

    def test_notification_action_url_set_on_ticket_purchase(self):
        ticket = self.make_ticket()
        NotificationService.ticket_purchased(self.attendee, [ticket], self.event)
        notif = Notification.objects.get(
            recipient=self.attendee, notification_type=NotificationType.TICKET_PURCHASED
        )
        self.assertEqual(notif.action_url, "/tickets")


# ---------------------------------------------------------------------------
# NotificationService — EmailLog creation
# ---------------------------------------------------------------------------

@override_settings(EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend")
class EmailLogTests(NotificationTestBase):

    def test_welcome_email_creates_log(self):
        NotificationService.welcome(self.attendee)
        self.assertTrue(
            EmailLog.objects.filter(
                recipient=self.attendee,
                email_type="welcome",
            ).exists()
        )

    def test_organizer_approved_email_creates_log(self):
        NotificationService.organizer_approved(self.organizer)
        self.assertTrue(
            EmailLog.objects.filter(
                recipient=self.organizer,
                email_type="organizer_approved",
            ).exists()
        )

    def test_ticket_purchase_email_creates_log(self):
        ticket = self.make_ticket()
        NotificationService.ticket_purchased(self.attendee, [ticket], self.event)
        self.assertTrue(
            EmailLog.objects.filter(
                recipient=self.attendee,
                email_type="ticket_purchased",
            ).exists()
        )

    def test_email_log_status_is_sent_on_success(self):
        NotificationService.welcome(self.attendee)
        log = EmailLog.objects.get(recipient=self.attendee, email_type="welcome")
        self.assertEqual(log.status, EmailLog.EmailStatus.SENT)

    def test_email_log_records_recipient_email(self):
        NotificationService.welcome(self.attendee)
        log = EmailLog.objects.get(recipient=self.attendee, email_type="welcome")
        self.assertEqual(log.recipient_email, self.attendee.email)


# ---------------------------------------------------------------------------
# Notification inbox API
# ---------------------------------------------------------------------------

@override_settings(EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend")
class NotificationAPITests(NotificationTestBase):

    def _create_notif(self, user=None, notification_type=NotificationType.SYSTEM,
                      title="Test", message="Test message"):
        user = user or self.attendee
        return Notification.objects.create(
            recipient=user, notification_type=notification_type,
            title=title, message=message,
        )

    def test_authenticated_user_can_list_notifications(self):
        self._create_notif()
        self.auth(self.attendee)
        resp = self.client.get(reverse("notification-list"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(resp.data["pagination"]["count"], 1)

    def test_user_only_sees_own_notifications(self):
        self._create_notif(user=self.attendee)
        self._create_notif(user=self.attendee2)
        self.auth(self.attendee)
        resp = self.client.get(reverse("notification-list"))
        for notif in resp.data["results"]:
            # All returned notifications must belong to attendee
            n = Notification.objects.get(id=notif["id"])
            self.assertEqual(n.recipient, self.attendee)

    def test_filter_unread_notifications(self):
        n1 = self._create_notif(title="Unread")
        n2 = self._create_notif(title="Read")
        n2.is_read = True
        n2.save()
        self.auth(self.attendee)
        resp = self.client.get(reverse("notification-list"), {"is_read": "false"})
        titles = [n["title"] for n in resp.data["results"]]
        self.assertIn("Unread", titles)
        self.assertNotIn("Read", titles)

    def test_unread_count_endpoint(self):
        self._create_notif()
        self._create_notif()
        self.auth(self.attendee)
        resp = self.client.get(reverse("notification-unread-count"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["unread_count"], 2)

    def test_unread_count_ignores_read_notifications(self):
        n = self._create_notif()
        n.is_read = True
        n.save()
        self.auth(self.attendee)
        resp = self.client.get(reverse("notification-unread-count"))
        self.assertEqual(resp.data["unread_count"], 0)

    def test_mark_specific_notifications_read(self):
        n1 = self._create_notif(title="N1")
        n2 = self._create_notif(title="N2")
        self.auth(self.attendee)
        resp = self.client.post(
            reverse("notification-mark-read"),
            {"notification_ids": [str(n1.id), str(n2.id)]},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["marked_read"], 2)
        n1.refresh_from_db()
        self.assertTrue(n1.is_read)
        self.assertIsNotNone(n1.read_at)

    def test_mark_all_read(self):
        self._create_notif()
        self._create_notif()
        self.auth(self.attendee)
        resp = self.client.post(reverse("notification-mark-all-read"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["marked_read"], 2)
        unread = Notification.objects.filter(recipient=self.attendee, is_read=False).count()
        self.assertEqual(unread, 0)

    def test_cannot_mark_other_users_notifications_read(self):
        n = self._create_notif(user=self.attendee2)
        self.auth(self.attendee)
        resp = self.client.post(
            reverse("notification-mark-read"),
            {"notification_ids": [str(n.id)]},
            format="json",
        )
        # Returns 200 but marked_read should be 0 (wrong owner)
        self.assertEqual(resp.data["marked_read"], 0)
        n.refresh_from_db()
        self.assertFalse(n.is_read)

    def test_delete_own_notification(self):
        n = self._create_notif()
        self.auth(self.attendee)
        resp = self.client.delete(reverse("notification-delete", kwargs={"id": n.id}))
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Notification.objects.filter(id=n.id).exists())

    def test_cannot_delete_other_users_notification(self):
        n = self._create_notif(user=self.attendee2)
        self.auth(self.attendee)
        resp = self.client.delete(reverse("notification-delete", kwargs={"id": n.id}))
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_clear_all_notifications(self):
        self._create_notif()
        self._create_notif()
        self.auth(self.attendee)
        resp = self.client.delete(reverse("notification-clear"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["deleted"], 2)
        self.assertEqual(Notification.objects.filter(recipient=self.attendee).count(), 0)

    def test_unauthenticated_cannot_access_notifications(self):
        resp = self.client.get(reverse("notification-list"))
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_notification_list_response_structure(self):
        self._create_notif()
        self.auth(self.attendee)
        resp = self.client.get(reverse("notification-list"))
        row = resp.data["results"][0]
        self.assertIn("id",                row)
        self.assertIn("notification_type", row)
        self.assertIn("title",             row)
        self.assertIn("message",           row)
        self.assertIn("is_read",           row)
        self.assertIn("created_at",        row)

    def test_mark_read_requires_notification_ids(self):
        self.auth(self.attendee)
        resp = self.client.post(
            reverse("notification-mark-read"), {}, format="json"
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


# ---------------------------------------------------------------------------
# Admin email log
# ---------------------------------------------------------------------------

@override_settings(EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend")
class AdminEmailLogAPITests(NotificationTestBase):

    def test_admin_can_view_email_logs(self):
        NotificationService.welcome(self.attendee)
        self.auth(self.admin, "AdminPass123!")
        resp = self.client.get(reverse("admin-email-logs"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(resp.data["pagination"]["count"], 1)

    def test_admin_can_filter_logs_by_status(self):
        NotificationService.welcome(self.attendee)
        self.auth(self.admin, "AdminPass123!")
        resp = self.client.get(reverse("admin-email-logs"), {"status": "sent"})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_admin_can_filter_logs_by_email_type(self):
        NotificationService.welcome(self.attendee)
        self.auth(self.admin, "AdminPass123!")
        resp = self.client.get(reverse("admin-email-logs"), {"email_type": "welcome"})
        for log in resp.data["results"]:
            self.assertEqual(log["email_type"], "welcome")

    def test_admin_can_filter_logs_by_recipient(self):
        NotificationService.welcome(self.attendee)
        self.auth(self.admin, "AdminPass123!")
        resp = self.client.get(reverse("admin-email-logs"), {"recipient": "att@k.com"})
        for log in resp.data["results"]:
            self.assertIn("att@k.com", log["recipient_email"])

    def test_attendee_cannot_access_email_logs(self):
        self.auth(self.attendee)
        resp = self.client.get(reverse("admin-email-logs"))
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_organizer_cannot_access_email_logs(self):
        self.auth(self.organizer, "OrgPass123!")
        resp = self.client.get(reverse("admin-email-logs"))
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_email_log_response_structure(self):
        NotificationService.welcome(self.attendee)
        self.auth(self.admin, "AdminPass123!")
        resp = self.client.get(reverse("admin-email-logs"))
        row = resp.data["results"][0]
        self.assertIn("recipient_email", row)
        self.assertIn("email_type",      row)
        self.assertIn("status",          row)
        self.assertIn("sent_at",         row)
