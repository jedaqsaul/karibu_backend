"""
logs/signals.py

Signal handlers that automatically write AuditLog entries when models
change state. This is the second tier of audit logging — the first is
explicit log_action() calls in views.

Signals handle cases where the state change happens outside a view
(management commands, admin panel, shell, tests) or where the view
author might forget to call log_action().

Covered transitions:
  User:    is_active=False (deactivation), is_approved=True (organizer approval)
  Event:   status changes
  Ticket:  status changes
"""

import logging
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

logger = logging.getLogger("karibu.audit")

# Store pre-save state so we can detect what changed
_pre_save_cache = {}


# ---------------------------------------------------------------------------
# User signals
# ---------------------------------------------------------------------------

@receiver(pre_save, sender="accounts.User")
def capture_user_pre_save(sender, instance, **kwargs):
    if instance.pk:
        try:
            old = sender.objects.get(pk=instance.pk)
            _pre_save_cache[f"user_{instance.pk}"] = {
                "is_active":   old.is_active,
                "is_approved": old.is_approved,
                "role":        old.role,
            }
        except sender.DoesNotExist:
            pass


@receiver(post_save, sender="accounts.User")
def on_user_save(sender, instance, created, **kwargs):
    from .utils import log_action

    if created:
        return  # Registration is logged by the view directly

    cache_key = f"user_{instance.pk}"
    old = _pre_save_cache.pop(cache_key, {})

    # Detect deactivation
    if old.get("is_active") is True and not instance.is_active:
        log_action(
            user=None,
            action="USER_DEACTIVATE",
            description=f"User {instance.email} was deactivated.",
            content_type="User",
            object_id=str(instance.pk),
        )

    # Detect organizer approval via admin panel or shell
    if (
        old.get("is_approved") is False
        and instance.is_approved
        and instance.role == "organizer"
    ):
        log_action(
            user=None,
            action="ORGANIZER_APPROVED",
            description=f"Organizer {instance.email} approved (signal).",
            content_type="User",
            object_id=str(instance.pk),
        )


# ---------------------------------------------------------------------------
# Event signals
# ---------------------------------------------------------------------------

@receiver(pre_save, sender="events.Event")
def capture_event_pre_save(sender, instance, **kwargs):
    if instance.pk:
        try:
            old = sender.objects.get(pk=instance.pk)
            _pre_save_cache[f"event_{instance.pk}"] = {"status": old.status}
        except sender.DoesNotExist:
            pass


@receiver(post_save, sender="events.Event")
def on_event_save(sender, instance, created, **kwargs):
    from .utils import log_action

    cache_key = f"event_{instance.pk}"
    old = _pre_save_cache.pop(cache_key, {})

    if created:
        log_action(
            user=instance.organizer,
            action="EVENT_CREATED",
            description=f"Event created: '{instance.title}' (signal).",
            content_type="Event",
            object_id=str(instance.pk),
        )
        return

    old_status = old.get("status")
    new_status = instance.status

    if old_status and old_status != new_status:
        action_map = {
            "published":        "EVENT_APPROVED",
            "cancelled":        "EVENT_CANCELLED",
            "pending_approval": "EVENT_SUBMITTED",
            "draft":            "EVENT_UPDATED",
            "completed":        "EVENT_COMPLETED",
        }
        action = action_map.get(new_status, "EVENT_UPDATED")
        log_action(
            user=instance.organizer,
            action=action,
            description=(
                f"Event '{instance.title}' status changed: "
                f"{old_status} → {new_status} (signal)."
            ),
            content_type="Event",
            object_id=str(instance.pk),
        )


# ---------------------------------------------------------------------------
# Ticket signals
# ---------------------------------------------------------------------------

@receiver(pre_save, sender="tickets.Ticket")
def capture_ticket_pre_save(sender, instance, **kwargs):
    if instance.pk:
        try:
            old = sender.objects.get(pk=instance.pk)
            _pre_save_cache[f"ticket_{instance.pk}"] = {"status": old.status}
        except sender.DoesNotExist:
            pass


@receiver(post_save, sender="tickets.Ticket")
def on_ticket_save(sender, instance, created, **kwargs):
    from .utils import log_action

    cache_key = f"ticket_{instance.pk}"
    old = _pre_save_cache.pop(cache_key, {})

    if created:
        log_action(
            user=instance.attendee,
            action="TICKET_PURCHASED",
            description=(
                f"Ticket {instance.ticket_number} purchased for "
                f"'{instance.event.title}' (signal)."
            ),
            content_type="Ticket",
            object_id=str(instance.pk),
        )
        return

    old_status = old.get("status")
    new_status = instance.status

    if old_status and old_status != new_status:
        action_map = {
            "used":      "TICKET_USED",
            "cancelled": "TICKET_CANCELLED",
            "refunded":  "TICKET_REFUNDED",
        }
        action = action_map.get(new_status, "TICKET_UPDATED")
        log_action(
            user=instance.attendee,
            action=action,
            description=(
                f"Ticket {instance.ticket_number} status: "
                f"{old_status} → {new_status} (signal)."
            ),
            content_type="Ticket",
            object_id=str(instance.pk),
        )
