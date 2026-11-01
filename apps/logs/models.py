"""
logs/models.py

AuditLog — immutable record of every significant platform action.

Design decisions:
  - user_email is snapshotted at write time. If a user is deleted,
    the email remains in the log. Never rely on the FK alone for display.
  - content_type + object_id form a soft generic FK — no hard dependency
    on contenttypes framework, keeping the log table lightweight.
  - Records are never updated or deleted via application code.
    Purging is handled by the management command on a schedule.
  - AuditLog is written by log_action() in utils.py and by signals.
    Views call log_action() for business actions; signals handle
    automatic model-level state changes.
"""

import uuid
from django.db import models
from django.conf import settings


class AuditLog(models.Model):

    class ActionCategory(models.TextChoices):
        AUTH     = "auth",     "Authentication"
        ACCOUNT  = "account",  "Account"
        EVENT    = "event",    "Event"
        TICKET   = "ticket",   "Ticket"
        PAYMENT  = "payment",  "Payment"
        ADMIN    = "admin",    "Admin Action"
        SYSTEM   = "system",   "System"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Actor — FK is nullable in case of system actions or deleted users
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    # Snapshot — preserved even if user is deleted
    user_email = models.EmailField(blank=True, db_index=True)
    user_role  = models.CharField(max_length=20, blank=True)

    # Action
    action   = models.CharField(max_length=100, db_index=True)
    category = models.CharField(
        max_length=20,
        choices=ActionCategory.choices,
        default=ActionCategory.SYSTEM,
        db_index=True,
    )
    description = models.TextField(blank=True)

    # Network context
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)

    # Optional object link (soft generic FK)
    content_type = models.CharField(max_length=100, blank=True)
    object_id    = models.CharField(max_length=100, blank=True)

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "audit_logs"
        ordering = ["-created_at"]
        verbose_name = "Audit Log"
        verbose_name_plural = "Audit Logs"
        indexes = [
            models.Index(fields=["action",   "created_at"]),
            models.Index(fields=["category", "created_at"]),
            models.Index(fields=["user",     "created_at"]),
        ]

    def __str__(self):
        actor = self.user_email or "system"
        return f"[{self.action}] by {actor} at {self.created_at:%Y-%m-%d %H:%M}"


# ---------------------------------------------------------------------------
# Action → category mapping (used by log_action to auto-categorise)
# ---------------------------------------------------------------------------

ACTION_CATEGORY_MAP = {
    # Auth
    "LOGIN":           AuditLog.ActionCategory.AUTH,
    "LOGOUT":          AuditLog.ActionCategory.AUTH,
    "REGISTER":        AuditLog.ActionCategory.AUTH,
    "PASSWORD_CHANGE": AuditLog.ActionCategory.AUTH,
    "PASSWORD_RESET":  AuditLog.ActionCategory.AUTH,
    # Account
    "PROFILE_UPDATE":  AuditLog.ActionCategory.ACCOUNT,
    "AVATAR_UPLOAD":   AuditLog.ActionCategory.ACCOUNT,
    # Event
    "EVENT_CREATED":    AuditLog.ActionCategory.EVENT,
    "EVENT_UPDATED":    AuditLog.ActionCategory.EVENT,
    "EVENT_DELETED":    AuditLog.ActionCategory.EVENT,
    "EVENT_SUBMITTED":  AuditLog.ActionCategory.EVENT,
    "EVENT_CANCELLED":  AuditLog.ActionCategory.EVENT,
    "EVENT_APPROVED":   AuditLog.ActionCategory.ADMIN,
    "EVENT_REJECTED":   AuditLog.ActionCategory.ADMIN,
    # Ticket
    "TICKET_PURCHASED":  AuditLog.ActionCategory.TICKET,
    "TICKET_DOWNLOADED": AuditLog.ActionCategory.TICKET,
    "TICKET_CANCELLED":  AuditLog.ActionCategory.TICKET,
    "TICKET_SCANNED":    AuditLog.ActionCategory.TICKET,
    # Payment
    "MPESA_STK_PUSH_INITIATED": AuditLog.ActionCategory.PAYMENT,
    "MPESA_PAYMENT_SUCCESS":    AuditLog.ActionCategory.PAYMENT,
    "MPESA_PAYMENT_FAILED":     AuditLog.ActionCategory.PAYMENT,
    # Admin
    "ADMIN_USER_UPDATE":       AuditLog.ActionCategory.ADMIN,
    "USER_DEACTIVATE":         AuditLog.ActionCategory.ADMIN,
    "ORGANIZER_APPROVED":      AuditLog.ActionCategory.ADMIN,
    "ORGANIZER_REJECTED":      AuditLog.ActionCategory.ADMIN,
    "ADMIN_EVENT_UPDATED":     AuditLog.ActionCategory.ADMIN,
    "ADMIN_TICKET_CANCELLED":  AuditLog.ActionCategory.ADMIN,
    "CATEGORY_CREATED":        AuditLog.ActionCategory.ADMIN,
    "CATEGORY_UPDATED":        AuditLog.ActionCategory.ADMIN,
    "CATEGORY_DELETED":        AuditLog.ActionCategory.ADMIN,
}
