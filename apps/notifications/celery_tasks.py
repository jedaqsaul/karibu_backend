"""
notifications/celery_tasks.py

Async Celery task versions of all notification dispatch functions.
These replace the synchronous calls in views when a Celery worker is running.

In development (CELERY_TASK_ALWAYS_EAGER=True) these run synchronously inline.
In production they are dispatched to the Redis queue and executed by workers.

Naming convention:
  - Views call tasks.py functions (stable, thin wrappers)
  - tasks.py delegates to celery_tasks.py via .delay()
  - celery_tasks.py calls NotificationService directly

This keeps the task queue as an infrastructure detail — views
never import from celery_tasks.py directly.
"""

from celery import shared_task
from datetime import timedelta
import logging

logger = logging.getLogger("karibu.notifications")


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,   # retry after 60 seconds
    name="notifications.send_welcome_email",
)
def send_welcome_email_task(self, user_id: str):
    try:
        from django.contrib.auth import get_user_model
        from .services import NotificationService
        User = get_user_model()
        user = User.objects.get(id=user_id)
        NotificationService.welcome(user)
    except Exception as exc:
        logger.exception("send_welcome_email_task failed for user_id=%s", user_id)
        raise self.retry(exc=exc)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    name="notifications.send_password_reset",
)
def send_password_reset_task(self, user_id: str):
    try:
        from django.contrib.auth import get_user_model
        from django.conf import settings
        from .services import NotificationService
        from .utils import generate_password_reset_token
        User = get_user_model()
        user      = User.objects.get(id=user_id)
        token     = generate_password_reset_token(user)
        reset_url = f"{settings.FRONTEND_URL}/reset-password?token={token}"
        NotificationService.password_reset(user, reset_url)
    except Exception as exc:
        logger.exception("send_password_reset_task failed for user_id=%s", user_id)
        raise self.retry(exc=exc)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    name="notifications.send_organizer_approved",
)
def send_organizer_approved_task(self, user_id: str):
    try:
        from django.contrib.auth import get_user_model
        from .services import NotificationService
        User = get_user_model()
        user = User.objects.get(id=user_id)
        NotificationService.organizer_approved(user)
    except Exception as exc:
        raise self.retry(exc=exc)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    name="notifications.send_organizer_rejected",
)
def send_organizer_rejected_task(self, user_id: str, reason: str = ""):
    try:
        from django.contrib.auth import get_user_model
        from .services import NotificationService
        User = get_user_model()
        user = User.objects.get(id=user_id)
        NotificationService.organizer_rejected(user, reason)
    except Exception as exc:
        raise self.retry(exc=exc)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    name="notifications.send_event_approved",
)
def send_event_approved_task(self, user_id: str, event_id: str):
    try:
        from django.contrib.auth import get_user_model
        from apps.events.models import Event
        from .services import NotificationService
        User  = get_user_model()
        user  = User.objects.get(id=user_id)
        event = Event.objects.get(id=event_id)
        NotificationService.event_approved(user, event)
    except Exception as exc:
        raise self.retry(exc=exc)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    name="notifications.send_event_rejected",
)
def send_event_rejected_task(self, user_id: str, event_id: str, reason: str = ""):
    try:
        from django.contrib.auth import get_user_model
        from apps.events.models import Event
        from .services import NotificationService
        User  = get_user_model()
        user  = User.objects.get(id=user_id)
        event = Event.objects.get(id=event_id)
        NotificationService.event_rejected(user, event, reason)
    except Exception as exc:
        raise self.retry(exc=exc)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    name="notifications.send_ticket_purchase",
)
def send_ticket_purchase_task(self, user_id: str, ticket_ids: list, event_id: str):
    try:
        from django.contrib.auth import get_user_model
        from apps.events.models import Event
        from apps.tickets.models import Ticket
        from .services import NotificationService
        User    = get_user_model()
        user    = User.objects.get(id=user_id)
        event   = Event.objects.get(id=event_id)
        tickets = list(Ticket.objects.filter(id__in=ticket_ids).select_related("event"))
        NotificationService.ticket_purchased(user, tickets, event)
    except Exception as exc:
        raise self.retry(exc=exc)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    name="notifications.send_ticket_cancelled",
)
def send_ticket_cancelled_task(self, user_id: str, ticket_id: str, reason: str = ""):
    try:
        from django.contrib.auth import get_user_model
        from apps.tickets.models import Ticket
        from .services import NotificationService
        User   = get_user_model()
        user   = User.objects.get(id=user_id)
        ticket = Ticket.objects.select_related("event").get(id=ticket_id)
        NotificationService.ticket_cancelled(user, ticket, reason)
    except Exception as exc:
        raise self.retry(exc=exc)


@shared_task(
    name="notifications.send_event_reminders_task",
    ignore_result=True,
)
def send_event_reminders_task(days: list = None):
    """
    Periodic task: send event reminders.
    Scheduled by Celery Beat at 8 AM EAT daily.
    Replaces the management command in production.
    """
    from datetime import timedelta
    from django.utils import timezone
    from apps.tickets.models import Ticket, TicketStatus
    from .services import NotificationService

    days    = days or [1, 3]
    now     = timezone.now()
    total   = 0

    for day_offset in days:
        window_start = now + timedelta(days=day_offset)
        window_end   = window_start + timedelta(hours=24)
        tickets = (
            Ticket.objects
            .filter(
                status=TicketStatus.CONFIRMED,
                event__start_datetime__gte=window_start,
                event__start_datetime__lt=window_end,
            )
            .select_related("attendee", "event")
        )
        for ticket in tickets:
            NotificationService.event_reminder(ticket)
            total += 1

    logger.info("send_event_reminders_task: dispatched %d reminders", total)
    return total
