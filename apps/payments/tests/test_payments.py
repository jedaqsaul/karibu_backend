"""
payments/tests/test_payments.py

Covers:
- STK push initiation (happy path, free-event rejection, sold-out rejection,
  invalid phone, unauthenticated)
- Callback handling (success creates tickets, failure doesn't, unknown
  CheckoutRequestID and malformed payloads are handled gracefully,
  duplicate callbacks are idempotent)
- Status polling with the Daraja fallback query

All Safaricom calls are mocked — no real network access.
"""

from unittest.mock import patch
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from rest_framework import status
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model

from apps.events.models import Event, EventStatus, Category
from apps.tickets.models import Ticket
from apps.payments.models import MpesaTransaction, MpesaTransactionStatus

User = get_user_model()


def future(days=10, hours=0):
    return timezone.now() + timedelta(days=days, hours=hours)


class PaymentsTestBase(TestCase):
    def setUp(self):
        self.client = APIClient()

        self.attendee = User.objects.create_user(
            email="att@karibu.com", password="AttPass123!",
            first_name="Jane", last_name="Doe",
        )
        self.organizer = User.objects.create_user(
            email="org@karibu.com", password="OrgPass123!",
            first_name="Org", last_name="One",
            role="organizer", is_approved=True,
        )
        self.category = Category.objects.create(name="Music", slug="music")

        self.event = Event.objects.create(
            organizer=self.organizer,
            title="Karibu Live", slug="karibu-live",
            description="A great show.",
            venue="KICC", address="City Square", city="Nairobi",
            start_datetime=future(5), end_datetime=future(5, hours=3),
            is_free=False, ticket_price=1000,
            total_capacity=50, tickets_sold=0,
            status=EventStatus.PUBLISHED,
            category=self.category,
        )

    def auth(self, user, password="AttPass123!"):
        resp = self.client.post(
            reverse("login"), {"email": user.email, "password": password}, format="json",
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['access']}")


# ---------------------------------------------------------------------------
# STK push initiation
# ---------------------------------------------------------------------------

class STKPushInitiateTests(PaymentsTestBase):

    @patch("apps.payments.views.DarajaClient.stk_push")
    def test_initiate_success_creates_pending_transaction(self, mock_stk_push):
        mock_stk_push.return_value = {
            "MerchantRequestID": "merchant-123",
            "CheckoutRequestID": "checkout-123",
            "ResponseCode": "0",
            "CustomerMessage": "Enter your PIN.",
        }
        self.auth(self.attendee)
        resp = self.client.post(
            reverse("mpesa-stkpush"),
            {"event_id": str(self.event.id), "quantity": 2, "phone_number": "0712345678"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(resp.data["checkout_request_id"], "checkout-123")

        txn = MpesaTransaction.objects.get(checkout_request_id="checkout-123")
        self.assertEqual(txn.status, MpesaTransactionStatus.INITIATED)
        self.assertEqual(txn.quantity, 2)
        self.assertEqual(txn.amount, Decimal("2000.00"))
        self.assertEqual(txn.phone_number, "254712345678")
        # No ticket exists yet — only created once payment is confirmed.
        self.assertEqual(Ticket.objects.filter(event=self.event).count(), 0)

    def test_free_event_rejected(self):
        free_event = Event.objects.create(
            organizer=self.organizer, title="Free Meetup", slug="free-meetup",
            description="X", venue="V", address="A", city="Nairobi",
            start_datetime=future(3), end_datetime=future(3, hours=2),
            is_free=True, ticket_price=0, total_capacity=50,
            status=EventStatus.PUBLISHED,
        )
        self.auth(self.attendee)
        resp = self.client.post(
            reverse("mpesa-stkpush"),
            {"event_id": str(free_event.id), "quantity": 1, "phone_number": "0712345678"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_sold_out_event_rejected(self):
        self.event.tickets_sold = 50
        self.event.save(update_fields=["tickets_sold"])
        self.auth(self.attendee)
        resp = self.client.post(
            reverse("mpesa-stkpush"),
            {"event_id": str(self.event.id), "quantity": 1, "phone_number": "0712345678"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_phone_number_rejected(self):
        self.auth(self.attendee)
        resp = self.client.post(
            reverse("mpesa-stkpush"),
            {"event_id": str(self.event.id), "quantity": 1, "phone_number": "12345"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unauthenticated_cannot_initiate(self):
        resp = self.client.post(
            reverse("mpesa-stkpush"),
            {"event_id": str(self.event.id), "quantity": 1, "phone_number": "0712345678"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    @patch("apps.payments.views.DarajaClient.stk_push")
    def test_daraja_failure_returns_502(self, mock_stk_push):
        from apps.payments.services import DarajaError
        mock_stk_push.side_effect = DarajaError("Safaricom is down")
        self.auth(self.attendee)
        resp = self.client.post(
            reverse("mpesa-stkpush"),
            {"event_id": str(self.event.id), "quantity": 1, "phone_number": "0712345678"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_502_BAD_GATEWAY)
        self.assertEqual(MpesaTransaction.objects.count(), 0)


# ---------------------------------------------------------------------------
# Callback handling
# ---------------------------------------------------------------------------

def make_transaction(event, user, quantity=1, checkout_id="checkout-abc"):
    return MpesaTransaction.objects.create(
        user=user, event=event, quantity=quantity,
        amount=event.ticket_price * quantity,
        phone_number="254712345678",
        merchant_request_id="merchant-abc",
        checkout_request_id=checkout_id,
    )


SUCCESS_CALLBACK = {
    "Body": {
        "stkCallback": {
            "MerchantRequestID": "merchant-abc",
            "CheckoutRequestID": "checkout-abc",
            "ResultCode": 0,
            "ResultDesc": "The service request is processed successfully.",
            "CallbackMetadata": {
                "Item": [
                    {"Name": "Amount", "Value": 1000.0},
                    {"Name": "MpesaReceiptNumber", "Value": "NLJ7RT61SV"},
                    {"Name": "TransactionDate", "Value": 20260802182530},
                    {"Name": "PhoneNumber", "Value": 254712345678},
                ]
            },
        }
    }
}

FAILURE_CALLBACK = {
    "Body": {
        "stkCallback": {
            "MerchantRequestID": "merchant-abc",
            "CheckoutRequestID": "checkout-abc",
            "ResultCode": 1032,
            "ResultDesc": "Request cancelled by user.",
        }
    }
}


class MpesaCallbackTests(PaymentsTestBase):

    def test_successful_callback_creates_ticket_and_updates_transaction(self):
        txn = make_transaction(self.event, self.attendee)

        resp = self.client.post(
            reverse("mpesa-callback"), SUCCESS_CALLBACK, format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        txn.refresh_from_db()
        self.assertEqual(txn.status, MpesaTransactionStatus.SUCCESS)
        self.assertEqual(txn.mpesa_receipt_number, "NLJ7RT61SV")
        self.assertEqual(len(txn.ticket_snapshot), 1)

        self.event.refresh_from_db()
        self.assertEqual(self.event.tickets_sold, 1)
        self.assertEqual(Ticket.objects.filter(event=self.event, attendee=self.attendee).count(), 1)

    def test_failed_callback_does_not_create_ticket(self):
        txn = make_transaction(self.event, self.attendee)

        resp = self.client.post(
            reverse("mpesa-callback"), FAILURE_CALLBACK, format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        txn.refresh_from_db()
        self.assertEqual(txn.status, MpesaTransactionStatus.FAILED)
        self.assertEqual(txn.result_desc, "Request cancelled by user.")

        self.event.refresh_from_db()
        self.assertEqual(self.event.tickets_sold, 0)
        self.assertEqual(Ticket.objects.count(), 0)

    def test_duplicate_success_callback_is_idempotent(self):
        make_transaction(self.event, self.attendee)

        self.client.post(reverse("mpesa-callback"), SUCCESS_CALLBACK, format="json")
        self.client.post(reverse("mpesa-callback"), SUCCESS_CALLBACK, format="json")

        self.event.refresh_from_db()
        self.assertEqual(self.event.tickets_sold, 1)  # not 2
        self.assertEqual(Ticket.objects.count(), 1)

    def test_unknown_checkout_request_id_does_not_crash(self):
        resp = self.client.post(
            reverse("mpesa-callback"),
            {
                "Body": {
                    "stkCallback": {
                        "CheckoutRequestID": "does-not-exist",
                        "ResultCode": 0,
                    }
                }
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_malformed_payload_does_not_crash(self):
        resp = self.client.post(reverse("mpesa-callback"), {"garbage": True}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_callback_requires_no_authentication(self):
        """Safaricom calls this with no auth header at all."""
        make_transaction(self.event, self.attendee)
        self.client.credentials()  # ensure no auth header is set
        resp = self.client.post(reverse("mpesa-callback"), SUCCESS_CALLBACK, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# Status polling
# ---------------------------------------------------------------------------

class PaymentStatusTests(PaymentsTestBase):

    def test_status_reflects_current_state(self):
        txn = make_transaction(self.event, self.attendee)
        self.auth(self.attendee)
        with patch("apps.payments.views.DarajaClient.query_stk_status") as mock_query:
            mock_query.return_value = {"ResultCode": None}  # still pending
            resp = self.client.get(reverse("mpesa-status", kwargs={"id": txn.id}))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["status"], MpesaTransactionStatus.INITIATED)

    def test_status_poll_confirms_success_via_fallback_query(self):
        """
        Simulates local dev where the callback never arrives — the status
        endpoint actively queries Safaricom and confirms the payment itself.
        """
        txn = make_transaction(self.event, self.attendee)
        self.auth(self.attendee)
        with patch("apps.payments.views.DarajaClient.query_stk_status") as mock_query:
            mock_query.return_value = {"ResultCode": 0, "ResultDesc": "Success"}
            resp = self.client.get(reverse("mpesa-status", kwargs={"id": txn.id}))

        self.assertEqual(resp.data["status"], MpesaTransactionStatus.SUCCESS)
        self.event.refresh_from_db()
        self.assertEqual(self.event.tickets_sold, 1)

    def test_other_users_transaction_not_visible(self):
        other = User.objects.create_user(
            email="other@karibu.com", password="OtherPass123!",
            first_name="Other", last_name="Person",
        )
        txn = make_transaction(self.event, other)
        self.auth(self.attendee)
        resp = self.client.get(reverse("mpesa-status", kwargs={"id": txn.id}))
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
