"""
events/signals.py

Auto-mark events as COMPLETED once their end_datetime has passed.
This is handled at query time via a management command in production,
but signals track status changes for audit logging here.
"""

from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Event, EventStatus


@receiver(post_save, sender=Event)
def log_event_status_change(sender, instance, created, **kwargs):
    """
    Log status transitions. The audit log entry is created
    in the view — this signal is a safety net for admin panel changes.
    """
    pass  # Extended in Phase 6 with full audit trail
