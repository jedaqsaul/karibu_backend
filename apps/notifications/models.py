"""
notifications/models.py

Two models:
  Notification  — in-app notification record per user (bell icon inbox)
  EmailLog      — audit record of every email dispatched by the platform

Design decisions:
  - Notifications are soft-deleted (is_read flag), never hard deleted
  - EmailLog is immutable — records are created but never updated
  - Both use UUID primary keys
  - notification_type drives the frontend icon/colour rendering
"""

import uuid
from django.db import models
from django.conf import settings


class NotificationType(models.TextChoices):
    # Account
    WELCOME             = "welcome",              "Welcome"
    PASSWORD_RESET      = "password_reset",       "Password Reset"
    # Organizer
    ACCOUNT_APPROVED    = "account_approved",     "Account Approved"
    ACCOUNT_REJECTED    = "account_rejected",     "Account Rejected"
    # Events
    EVENT_APPROVED      = "event_approved",       "Event Approved"
    EVENT_REJECTED      = "event_rejected",       "Event Rejected"
    EVENT_CANCELLED     = "event_cancelled",      "Event Cancelled"
    EVENT_REMINDER      = "event_reminder",       "Event Reminder"
    # Tickets
    TICKET_PURCHASED    = "ticket_purchased",     "Ticket Purchased"
    TICKET_CANCELLED    = "ticket_cancelled",     "Ticket Cancelled"
    # System
    SYSTEM              = "system",               "System Notice"


class Notification(models.Model):
    """
    In-app notification record.
    One row per notification per user.
    The frontend polls GET /api/notifications/ to populate the bell icon.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )

    notification_type = models.CharField(
        max_length=30,
        choices=NotificationType.choices,
        db_index=True,
    )

    title   = models.CharField(max_length=200)
    message = models.TextField()

    # Optional deep-link so the frontend can navigate on click
    action_url = models.CharField(max_length=500, blank=True)

    # Read state
    is_read = models.BooleanField(default=False, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "notifications"
        ordering = ["-created_at"]
        indexes  = [
            models.Index(fields=["recipient", "is_read"]),
            models.Index(fields=["recipient", "created_at"]),
        ]

    def __str__(self):
        return f"[{self.notification_type}] → {self.recipient.email}: {self.title}"


class EmailLog(models.Model):
    """
    Immutable audit record of every email sent.
    Never updated — only inserted.
    Used by the admin to verify delivery and debug failures.
    """

    class EmailStatus(models.TextChoices):
        SENT    = "sent",    "Sent"
        FAILED  = "failed",  "Failed"
        SKIPPED = "skipped", "Skipped (no email backend)"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    recipient_email = models.EmailField(db_index=True)
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="email_logs",
    )

    subject         = models.CharField(max_length=500)
    email_type      = models.CharField(max_length=50, db_index=True)
    status          = models.CharField(
        max_length=10,
        choices=EmailStatus.choices,
        default=EmailStatus.SENT,
        db_index=True,
    )
    error_message   = models.TextField(blank=True)

    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "email_logs"
        ordering = ["-sent_at"]

    def __str__(self):
        return f"[{self.status}] {self.subject} → {self.recipient_email}"
