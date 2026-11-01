"""
tickets/models.py

Two models:
  - Ticket: one record per purchased ticket, unique QR code, download tracking
  - TicketValidation: immutable scan log per ticket — who scanned, when, where

Design decisions:
  - ticket_code is a UUID rendered as uppercase hex, used in the QR payload
  - One ticket = one entry. Bulk purchases create N separate Ticket records,
    each with their own code. This makes per-entry scanning unambiguous.
  - price_paid is stored at purchase time — event price changes never affect
    existing tickets.
  - status drives the full ticket lifecycle: pending → confirmed → cancelled / refunded
"""

import uuid
from django.db import models
from django.conf import settings


class TicketStatus(models.TextChoices):
    PENDING   = "pending",   "Pending Payment"
    CONFIRMED = "confirmed", "Confirmed"
    CANCELLED = "cancelled", "Cancelled"
    REFUNDED  = "refunded",  "Refunded"
    USED      = "used",      "Used"


class Ticket(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Relationships
    event = models.ForeignKey(
        "events.Event",
        on_delete=models.PROTECT,   # never silently delete tickets when event deleted
        related_name="tickets",
    )
    attendee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="tickets",
    )

    # Ticket identity
    ticket_code = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        db_index=True,
        help_text="Embedded in the QR code. Used for validation scanning.",
    )
    ticket_number = models.CharField(
        max_length=20,
        unique=True,
        db_index=True,
        help_text="Human-readable reference e.g. KRB-00001.",
    )

    # Pricing — snapshot at time of purchase
    price_paid = models.DecimalField(max_digits=10, decimal_places=2)
    currency   = models.CharField(max_length=3, default="KES")

    # Status
    status = models.CharField(
        max_length=20,
        choices=TicketStatus.choices,
        default=TicketStatus.PENDING,
        db_index=True,
    )

    # PDF tracking
    pdf_generated  = models.BooleanField(default=False)
    pdf_url        = models.URLField(blank=True)   # Cloudinary URL of the generated PDF
    download_count = models.PositiveIntegerField(default=0)

    # Email
    email_sent    = models.BooleanField(default=False)
    email_sent_at = models.DateTimeField(null=True, blank=True)

    # Timestamps
    purchased_at = models.DateTimeField(auto_now_add=True)
    updated_at   = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tickets"
        ordering = ["-purchased_at"]
        indexes  = [
            models.Index(fields=["event", "status"]),
            models.Index(fields=["attendee", "status"]),
        ]

    def __str__(self):
        return f"{self.ticket_number} — {self.event.title} [{self.get_status_display()}]"

    @property
    def qr_payload(self):
        """The string encoded inside the QR code."""
        return str(self.ticket_code).upper().replace("-", "")

    @property
    def is_valid_for_entry(self):
        return self.status == TicketStatus.CONFIRMED


class TicketValidation(models.Model):
    """
    Immutable record of each scan attempt.
    Created whether the scan succeeds or fails — the result field records the outcome.
    Never deleted.
    """

    class ScanResult(models.TextChoices):
        SUCCESS       = "success",       "Valid — Entry Granted"
        ALREADY_USED  = "already_used",  "Already Used"
        INVALID_CODE  = "invalid_code",  "Invalid Code"
        CANCELLED     = "cancelled",     "Ticket Cancelled"
        EVENT_MISMATCH = "event_mismatch", "Wrong Event"

    id     = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ticket = models.ForeignKey(
        Ticket,
        on_delete=models.PROTECT,
        related_name="validations",
        null=True,
        blank=True,    # null when the scanned code doesn't match any ticket
    )
    scanned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="ticket_scans",
    )

    scanned_code = models.CharField(max_length=100)   # raw string from the scanner
    result       = models.CharField(max_length=20, choices=ScanResult.choices)
    scanned_at   = models.DateTimeField(auto_now_add=True, db_index=True)
    device_info  = models.CharField(max_length=300, blank=True)

    class Meta:
        db_table = "ticket_validations"
        ordering = ["-scanned_at"]

    def __str__(self):
        return f"Scan [{self.result}] at {self.scanned_at:%Y-%m-%d %H:%M}"
