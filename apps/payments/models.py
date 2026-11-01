"""
payments/models.py

MpesaTransaction tracks one STK Push payment attempt end to end:

  INITIATED  → STK push request sent to Safaricom, waiting on the customer
               to enter their M-Pesa PIN on their phone.
  SUCCESS    → Safaricom's callback confirmed payment; tickets have been
               created (see apps.tickets.services.create_confirmed_tickets).
  FAILED     → Safaricom's callback reported a non-zero ResultCode
               (cancelled by user, insufficient funds, timeout, etc.)
  CANCELLED  → Reserved for future manual/admin cancellation of a stuck
               INITIATED transaction; not currently set automatically.

Deliberately has NO foreign key to apps.tickets.Ticket — that would create
a cross-app schema dependency for what is fundamentally a payment-gateway
integration. Instead, once tickets are created we snapshot their ids and
ticket_numbers into `ticket_snapshot` (JSONField), which is enough for the
status-polling endpoint to return full ticket data without a DB relation.
"""

import uuid
from django.db import models
from django.conf import settings


class MpesaTransactionStatus(models.TextChoices):
    INITIATED = "initiated", "Initiated — awaiting customer PIN entry"
    SUCCESS   = "success",   "Payment Successful"
    FAILED    = "failed",    "Payment Failed"
    CANCELLED = "cancelled", "Cancelled"


class MpesaTransaction(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Who / what this payment is for
    user  = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="mpesa_transactions",
    )
    event = models.ForeignKey(
        "events.Event",
        on_delete=models.PROTECT,
        related_name="mpesa_transactions",
    )
    quantity = models.PositiveIntegerField(default=1)
    amount   = models.DecimalField(max_digits=10, decimal_places=2)

    # Safaricom identifiers — CheckoutRequestID is what the callback and
    # status-query endpoints use to find this record again.
    phone_number        = models.CharField(max_length=15, help_text="Normalized 2547XXXXXXXX format.")
    merchant_request_id = models.CharField(max_length=100, blank=True)
    checkout_request_id = models.CharField(max_length=100, unique=True, db_index=True)

    status = models.CharField(
        max_length=20,
        choices=MpesaTransactionStatus.choices,
        default=MpesaTransactionStatus.INITIATED,
        db_index=True,
    )

    # Populated from the Daraja callback
    result_code           = models.IntegerField(null=True, blank=True)
    result_desc            = models.CharField(max_length=300, blank=True)
    mpesa_receipt_number   = models.CharField(max_length=50, blank=True)
    transaction_date_raw    = models.CharField(
        max_length=20, blank=True,
        help_text="Raw Safaricom timestamp e.g. '20260802182530'.",
    )

    # Snapshot of the tickets created once this payment succeeds — see
    # module docstring for why this isn't a real FK relation.
    ticket_snapshot = models.JSONField(default=list, blank=True)

    # Raw callback payload, kept for debugging/audit — Safaricom's payload
    # shape has changed before, and this makes it easy to diagnose issues
    # without needing to reproduce them.
    callback_raw = models.JSONField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "mpesa_transactions"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["event", "status"]),
        ]

    def __str__(self):
        return f"M-Pesa [{self.status}] {self.checkout_request_id} — KES {self.amount}"

    @property
    def is_pending(self):
        return self.status == MpesaTransactionStatus.INITIATED
