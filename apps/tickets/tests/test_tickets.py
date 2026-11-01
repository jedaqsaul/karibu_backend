"""
tickets/tests/test_tickets.py

Phase 3 test suite. Covers:
- Ticket purchase (happy path, oversell protection, wrong event state)
- My tickets list and detail
- PDF download
- Attendee self-cancellation
- Organizer: view event tickets, QR scan flow (all result branches)
- Admin: list all tickets, force-cancel
- Permission enforcement across all roles
"""

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from rest_framework import status
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model

from apps.accounts.models import OrganizerProfile
from apps.events.models import Event, EventStatus, Category
from apps.tickets.models import Ticket, TicketStatus, TicketValidation

User = get_user_model()


# ---------------------------------------------------------------------------
# Shared base
# ---------------------------------------------------------------------------

def future(days=10, hours=0):
    return timezone.now() + timedelta(days=days, hours=hours)


class TicketTestBase(TestCase):
    def setUp(self):
        self.client = APIClient()

        self.admin = User.objects.create_superuser(
            email="admin@karibu.com", password="AdminPass123!",
            first_name="Super", last_name="Admin",
        )

        self.organizer = User.objects.create_user(
            email="org@karibu.com", password="OrgPass123!",
            first_name="Org", last_name="One",
            role="organizer", is_approved=True,
        )
        OrganizerProfile.objects.create(user=self.organizer, organization_name="Org Ltd")

        self.attendee = User.objects.create_user(
            email="att@karibu.com", password="AttPass123!",
            first_name="Jane", last_name="Doe",
        )

        self.attendee2 = User.objects.create_user(
            email="att2@karibu.com", password="AttPass123!",
            first_name="John", last_name="Smith",
        )

        self.category = Category.objects.create(name="Music", slug="music")

        self.event = Event.objects.create(
            organizer=self.organizer,
            title="Karibu Live",
            slug="karibu-live",
            description="A great show.",
            venue="KICC", address="City Square", city="Nairobi",
            start_datetime=future(5), end_datetime=future(5, hours=3),
            is_free=False, ticket_price=1000,
            total_capacity=50, tickets_sold=0,
            status=EventStatus.PUBLISHED,
            category=self.category,
        )

        # TicketPurchaseView (instant-confirm) only applies to free events —
        # paid events go through apps.payments (M-Pesa). Purchase tests use
        # this fixture; self.event above stays paid for the other test
        # classes (download/cancel/scan), which create tickets directly.
        self.free_event = Event.objects.create(
            organizer=self.organizer,
            title="Community Meetup",
            slug="community-meetup",
            description="A free get-together.",
            venue="iHub", address="Ngong Road", city="Nairobi",
            start_datetime=future(5), end_datetime=future(5, hours=3),
            is_free=True, ticket_price=0,
            total_capacity=50, tickets_sold=0,
            status=EventStatus.PUBLISHED,
            category=self.category,
        )

    def auth(self, user, password="AttPass123!"):
        resp = self.client.post(
            reverse("login"),
            {"email": user.email, "password": password},
            format="json",
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['access']}")

    def make_confirmed_ticket(self, attendee=None, event=None):
        """Helper to create a confirmed ticket directly."""
        from shared.utils.ticket_number import generate_ticket_number
        attendee = attendee or self.attendee
        event    = event    or self.event
        ticket   = Ticket.objects.create(
            event=event, attendee=attendee,
            ticket_number=generate_ticket_number(),
            price_paid=event.ticket_price,
            status=TicketStatus.CONFIRMED,
        )
        event.tickets_sold += 1
        event.save(update_fields=["tickets_sold"])
        return ticket


# ---------------------------------------------------------------------------
# Purchase
# ---------------------------------------------------------------------------

class TicketPurchaseTests(TicketTestBase):

    def test_attendee_can_purchase_single_ticket(self):
        self.auth(self.attendee)
        resp = self.client.post(
            reverse("ticket-purchase"),
            {"event_id": str(self.free_event.id), "quantity": 1},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(resp.data["tickets"]), 1)
        self.assertEqual(resp.data["tickets"][0]["status"], TicketStatus.CONFIRMED)

    def test_bulk_purchase_creates_separate_tickets(self):
        self.auth(self.attendee)
        resp = self.client.post(
            reverse("ticket-purchase"),
            {"event_id": str(self.free_event.id), "quantity": 3},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(resp.data["tickets"]), 3)
        # All ticket numbers must be unique
        numbers = [t["ticket_number"] for t in resp.data["tickets"]]
        self.assertEqual(len(numbers), len(set(numbers)))

    def test_tickets_sold_increments_atomically(self):
        self.auth(self.attendee)
        self.client.post(
            reverse("ticket-purchase"),
            {"event_id": str(self.free_event.id), "quantity": 4},
            format="json",
        )
        self.free_event.refresh_from_db()
        self.assertEqual(self.free_event.tickets_sold, 4)

    def test_price_paid_is_snapshot_of_event_price(self):
        self.auth(self.attendee)
        resp = self.client.post(
            reverse("ticket-purchase"),
            {"event_id": str(self.free_event.id), "quantity": 1},
            format="json",
        )
        ticket_id = resp.data["tickets"][0]["id"]
        ticket    = Ticket.objects.get(id=ticket_id)
        self.assertEqual(ticket.price_paid, self.free_event.ticket_price)

    def test_paid_event_rejected_use_mpesa_instead(self):
        """
        This endpoint is for free events only — paid events must go through
        apps.payments (M-Pesa STK Push). This is the fix that closes the
        gap where a paid event could previously be "purchased" with no
        payment at all.
        """
        self.auth(self.attendee)
        resp = self.client.post(
            reverse("ticket-purchase"),
            {"event_id": str(self.event.id), "quantity": 1},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_402_PAYMENT_REQUIRED)
        self.assertEqual(Ticket.objects.filter(event=self.event).count(), 0)

    def test_oversell_blocked(self):
        """Cannot purchase more tickets than seats remaining."""
        self.free_event.tickets_sold = 48
        self.free_event.save(update_fields=["tickets_sold"])  # 2 remaining

        self.auth(self.attendee)
        resp = self.client.post(
            reverse("ticket-purchase"),
            {"event_id": str(self.free_event.id), "quantity": 5},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_purchase_from_draft_event(self):
        draft = Event.objects.create(
            organizer=self.organizer, title="Draft", slug="draft-ev",
            description="X", venue="V", address="A", city="Nairobi",
            start_datetime=future(3), end_datetime=future(3, hours=2),
            is_free=False, ticket_price=500, total_capacity=100,
            status=EventStatus.DRAFT,
        )
        self.auth(self.attendee)
        resp = self.client.post(
            reverse("ticket-purchase"),
            {"event_id": str(draft.id), "quantity": 1},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unauthenticated_cannot_purchase(self):
        resp = self.client.post(
            reverse("ticket-purchase"),
            {"event_id": str(self.event.id), "quantity": 1},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_quantity_must_be_at_least_1(self):
        self.auth(self.attendee)
        resp = self.client.post(
            reverse("ticket-purchase"),
            {"event_id": str(self.event.id), "quantity": 0},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_quantity_capped_at_10(self):
        self.auth(self.attendee)
        resp = self.client.post(
            reverse("ticket-purchase"),
            {"event_id": str(self.event.id), "quantity": 11},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_ticket_number_format(self):
        self.auth(self.attendee)
        resp = self.client.post(
            reverse("ticket-purchase"),
            {"event_id": str(self.free_event.id), "quantity": 1},
            format="json",
        )
        number = resp.data["tickets"][0]["ticket_number"]
        self.assertTrue(number.startswith("KRB-"))
        self.assertEqual(len(number), 9)  # KRB-00001

    def test_free_event_purchase_sets_zero_price(self):
        free_event = Event.objects.create(
            organizer=self.organizer, title="Free Show", slug="free-show",
            description="X", venue="V", address="A", city="Nairobi",
            start_datetime=future(3), end_datetime=future(3, hours=2),
            is_free=True, ticket_price=0, total_capacity=100,
            status=EventStatus.PUBLISHED,
        )
        self.auth(self.attendee)
        resp = self.client.post(
            reverse("ticket-purchase"),
            {"event_id": str(free_event.id), "quantity": 1},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data["tickets"][0]["price_paid"], "0.00")


# ---------------------------------------------------------------------------
# My tickets
# ---------------------------------------------------------------------------

class MyTicketsTests(TicketTestBase):

    def test_attendee_can_list_own_tickets(self):
        ticket = self.make_confirmed_ticket()
        self.auth(self.attendee)
        resp = self.client.get(reverse("my-ticket-list"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        ids = [t["id"] for t in resp.data["results"]]
        self.assertIn(str(ticket.id), ids)

    def test_attendee_cannot_see_other_attendees_tickets(self):
        self.make_confirmed_ticket(attendee=self.attendee2)
        self.auth(self.attendee)
        resp = self.client.get(reverse("my-ticket-list"))
        self.assertEqual(resp.data["pagination"]["count"], 0)

    def test_attendee_can_view_own_ticket_detail(self):
        ticket = self.make_confirmed_ticket()
        self.auth(self.attendee)
        resp = self.client.get(reverse("my-ticket-detail", kwargs={"id": ticket.id}))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["ticket_number"], ticket.ticket_number)

    def test_attendee_cannot_view_other_ticket_detail(self):
        ticket = self.make_confirmed_ticket(attendee=self.attendee2)
        self.auth(self.attendee)
        resp = self.client.get(reverse("my-ticket-detail", kwargs={"id": ticket.id}))
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_status_filter_on_ticket_list(self):
        self.make_confirmed_ticket()
        self.auth(self.attendee)
        resp = self.client.get(reverse("my-ticket-list"), {"status": "cancelled"})
        self.assertEqual(resp.data["pagination"]["count"], 0)

    def test_qr_payload_in_detail_response(self):
        ticket = self.make_confirmed_ticket()
        self.auth(self.attendee)
        resp = self.client.get(reverse("my-ticket-detail", kwargs={"id": ticket.id}))
        self.assertIn("qr_payload", resp.data)
        self.assertTrue(len(resp.data["qr_payload"]) == 32)  # 32-char hex


# ---------------------------------------------------------------------------
# PDF download
# ---------------------------------------------------------------------------

class TicketDownloadTests(TicketTestBase):

    def test_attendee_can_download_confirmed_ticket(self):
        ticket = self.make_confirmed_ticket()
        self.auth(self.attendee)
        resp = self.client.get(reverse("ticket-download", kwargs={"id": ticket.id}))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp["Content-Type"], "application/pdf")
        self.assertIn(ticket.ticket_number, resp["Content-Disposition"])
        # Verify it's a real PDF
        self.assertTrue(resp.content.startswith(b"%PDF"))

    def test_download_increments_download_count(self):
        ticket = self.make_confirmed_ticket()
        self.auth(self.attendee)
        self.client.get(reverse("ticket-download", kwargs={"id": ticket.id}))
        self.client.get(reverse("ticket-download", kwargs={"id": ticket.id}))
        ticket.refresh_from_db()
        self.assertEqual(ticket.download_count, 2)

    def test_cannot_download_cancelled_ticket(self):
        ticket = self.make_confirmed_ticket()
        ticket.status = TicketStatus.CANCELLED
        ticket.save()
        self.auth(self.attendee)
        resp = self.client.get(reverse("ticket-download", kwargs={"id": ticket.id}))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_download_other_attendees_ticket(self):
        ticket = self.make_confirmed_ticket(attendee=self.attendee2)
        self.auth(self.attendee)
        resp = self.client.get(reverse("ticket-download", kwargs={"id": ticket.id}))
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)


# ---------------------------------------------------------------------------
# Attendee cancellation
# ---------------------------------------------------------------------------

class TicketCancellationTests(TicketTestBase):

    def test_attendee_can_cancel_confirmed_ticket(self):
        ticket = self.make_confirmed_ticket()
        self.auth(self.attendee)
        resp = self.client.post(reverse("ticket-cancel", kwargs={"id": ticket.id}))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, TicketStatus.CANCELLED)

    def test_cancellation_restores_seat_count(self):
        ticket = self.make_confirmed_ticket()
        sold_before = self.event.tickets_sold
        self.auth(self.attendee)
        self.client.post(reverse("ticket-cancel", kwargs={"id": ticket.id}))
        self.event.refresh_from_db()
        self.assertEqual(self.event.tickets_sold, sold_before - 1)

    def test_cannot_cancel_already_used_ticket(self):
        ticket = self.make_confirmed_ticket()
        ticket.status = TicketStatus.USED
        ticket.save()
        self.auth(self.attendee)
        resp = self.client.post(reverse("ticket-cancel", kwargs={"id": ticket.id}))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_cancel_past_event_ticket(self):
        past_event = Event.objects.create(
            organizer=self.organizer, title="Past Event", slug="past-ev",
            description="X", venue="V", address="A", city="Nairobi",
            start_datetime=timezone.now() - timedelta(days=2),
            end_datetime=timezone.now() - timedelta(days=1),
            is_free=False, ticket_price=500, total_capacity=100,
            status=EventStatus.PUBLISHED,
        )
        ticket = self.make_confirmed_ticket(event=past_event)
        self.auth(self.attendee)
        resp = self.client.post(reverse("ticket-cancel", kwargs={"id": ticket.id}))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


# ---------------------------------------------------------------------------
# Organizer scan
# ---------------------------------------------------------------------------

class TicketScanTests(TicketTestBase):

    def test_valid_scan_marks_ticket_used(self):
        ticket = self.make_confirmed_ticket()
        self.auth(self.organizer, "OrgPass123!")
        resp = self.client.post(
            reverse("ticket-scan"),
            {"code": ticket.qr_payload, "event_id": str(self.event.id)},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(resp.data["valid"])
        self.assertEqual(resp.data["result"], TicketValidation.ScanResult.SUCCESS)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, TicketStatus.USED)

    def test_scan_creates_validation_record(self):
        ticket = self.make_confirmed_ticket()
        self.auth(self.organizer, "OrgPass123!")
        self.client.post(
            reverse("ticket-scan"),
            {"code": ticket.qr_payload, "event_id": str(self.event.id)},
            format="json",
        )
        self.assertEqual(TicketValidation.objects.filter(ticket=ticket).count(), 1)

    def test_already_used_ticket_returns_correct_result(self):
        ticket = self.make_confirmed_ticket()
        ticket.status = TicketStatus.USED
        ticket.save()
        self.auth(self.organizer, "OrgPass123!")
        resp = self.client.post(
            reverse("ticket-scan"),
            {"code": ticket.qr_payload, "event_id": str(self.event.id)},
            format="json",
        )
        self.assertFalse(resp.data["valid"])
        self.assertEqual(resp.data["result"], TicketValidation.ScanResult.ALREADY_USED)

    def test_invalid_code_returns_correct_result(self):
        self.auth(self.organizer, "OrgPass123!")
        resp = self.client.post(
            reverse("ticket-scan"),
            {"code": "DEADBEEFDEADBEEFDEADBEEFDEADBEEF", "event_id": str(self.event.id)},
            format="json",
        )
        self.assertFalse(resp.data["valid"])
        self.assertEqual(resp.data["result"], TicketValidation.ScanResult.INVALID_CODE)

    def test_ticket_for_wrong_event_returns_mismatch(self):
        other_event = Event.objects.create(
            organizer=self.organizer, title="Other Event", slug="other-ev",
            description="X", venue="V", address="A", city="Nairobi",
            start_datetime=future(3), end_datetime=future(3, hours=2),
            is_free=False, ticket_price=500, total_capacity=100,
            status=EventStatus.PUBLISHED,
        )
        ticket = self.make_confirmed_ticket(event=other_event)
        # Scan this ticket but claim it's for self.event
        self.auth(self.organizer, "OrgPass123!")
        resp = self.client.post(
            reverse("ticket-scan"),
            {"code": ticket.qr_payload, "event_id": str(self.event.id)},
            format="json",
        )
        self.assertFalse(resp.data["valid"])
        self.assertEqual(resp.data["result"], TicketValidation.ScanResult.EVENT_MISMATCH)

    def test_cancelled_ticket_scan_returns_cancelled_result(self):
        ticket = self.make_confirmed_ticket()
        ticket.status = TicketStatus.CANCELLED
        ticket.save()
        self.auth(self.organizer, "OrgPass123!")
        resp = self.client.post(
            reverse("ticket-scan"),
            {"code": ticket.qr_payload, "event_id": str(self.event.id)},
            format="json",
        )
        self.assertFalse(resp.data["valid"])
        self.assertEqual(resp.data["result"], TicketValidation.ScanResult.CANCELLED)

    def test_attendee_cannot_use_scan_endpoint(self):
        self.auth(self.attendee)
        resp = self.client.post(
            reverse("ticket-scan"),
            {"code": "ABC", "event_id": str(self.event.id)},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_scan_always_writes_validation_record_even_on_failure(self):
        self.auth(self.organizer, "OrgPass123!")
        self.client.post(
            reverse("ticket-scan"),
            {"code": "INVALIDCODE999", "event_id": str(self.event.id)},
            format="json",
        )
        self.assertEqual(TicketValidation.objects.filter(result="invalid_code").count(), 1)

    def test_organizer_cannot_scan_other_organizers_event(self):
        other_org = User.objects.create_user(
            email="other@karibu.com", password="Pass123!",
            first_name="O", last_name="T", role="organizer", is_approved=True,
        )
        OrganizerProfile.objects.create(user=other_org, organization_name="Other Org")
        ticket = self.make_confirmed_ticket()
        self.auth(other_org, "Pass123!")
        resp = self.client.post(
            reverse("ticket-scan"),
            {"code": ticket.qr_payload, "event_id": str(self.event.id)},
            format="json",
        )
        # Event belongs to self.organizer — other_org gets 404
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)


# ---------------------------------------------------------------------------
# Organizer event tickets list
# ---------------------------------------------------------------------------

class OrganizerEventTicketsTests(TicketTestBase):

    def test_organizer_can_list_tickets_for_own_event(self):
        self.make_confirmed_ticket()
        self.auth(self.organizer, "OrgPass123!")
        resp = self.client.get(
            reverse("organizer-event-tickets", kwargs={"event_id": self.event.id})
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(resp.data["pagination"]["count"], 1)

    def test_organizer_cannot_list_tickets_for_other_organizers_event(self):
        other_org = User.objects.create_user(
            email="org2@karibu.com", password="Pass123!",
            first_name="O", last_name="T", role="organizer", is_approved=True,
        )
        OrganizerProfile.objects.create(user=other_org, organization_name="Org 2")
        self.auth(other_org, "Pass123!")
        resp = self.client.get(
            reverse("organizer-event-tickets", kwargs={"event_id": self.event.id})
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_attendee_cannot_list_event_tickets(self):
        self.auth(self.attendee)
        resp = self.client.get(
            reverse("organizer-event-tickets", kwargs={"event_id": self.event.id})
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------

class AdminTicketTests(TicketTestBase):

    def test_admin_can_list_all_tickets(self):
        self.make_confirmed_ticket()
        self.auth(self.admin, "AdminPass123!")
        resp = self.client.get(reverse("admin-ticket-list"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(resp.data["pagination"]["count"], 1)

    def test_admin_can_view_ticket_detail(self):
        ticket = self.make_confirmed_ticket()
        self.auth(self.admin, "AdminPass123!")
        resp = self.client.get(reverse("admin-ticket-detail", kwargs={"id": ticket.id}))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("attendee_email", resp.data)

    def test_admin_can_cancel_confirmed_ticket(self):
        ticket = self.make_confirmed_ticket()
        self.auth(self.admin, "AdminPass123!")
        resp = self.client.post(
            reverse("admin-ticket-cancel", kwargs={"id": ticket.id}),
            {"reason": "Fraudulent purchase detected."},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, TicketStatus.CANCELLED)

    def test_admin_filter_tickets_by_event(self):
        self.make_confirmed_ticket()
        self.auth(self.admin, "AdminPass123!")
        resp = self.client.get(
            reverse("admin-ticket-list"), {"event_id": str(self.event.id)}
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_attendee_cannot_access_admin_ticket_list(self):
        self.auth(self.attendee)
        resp = self.client.get(reverse("admin-ticket-list"))
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
