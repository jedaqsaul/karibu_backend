"""
notifications/tasks.py

Public dispatch interface for all other apps.
All functions now dispatch to Celery async tasks via .delay().
In development (CELERY_TASK_ALWAYS_EAGER=True) they run synchronously.
In production they are queued via Redis and processed by workers.

Other apps import ONLY from this module — never from celery_tasks.py.
"""

import logging

logger = logging.getLogger("karibu.notifications")


def send_welcome_email(user):
    try:
        from .celery_tasks import send_welcome_email_task
        send_welcome_email_task.delay(str(user.id))
    except Exception:
        logger.exception("Failed to queue welcome email for %s", user.email)


def send_password_reset_email(user):
    try:
        from .celery_tasks import send_password_reset_task
        send_password_reset_task.delay(str(user.id))
    except Exception:
        logger.exception("Failed to queue password reset email for %s", user.email)


def send_organizer_approved_email(user):
    try:
        from .celery_tasks import send_organizer_approved_task
        send_organizer_approved_task.delay(str(user.id))
    except Exception:
        logger.exception("Failed to queue organizer approved email for %s", user.email)


def send_organizer_rejected_email(user, reason=""):
    try:
        from .celery_tasks import send_organizer_rejected_task
        send_organizer_rejected_task.delay(str(user.id), reason)
    except Exception:
        logger.exception("Failed to queue organizer rejected email for %s", user.email)


def send_event_approved_email(user, event):
    try:
        from .celery_tasks import send_event_approved_task
        send_event_approved_task.delay(str(user.id), str(event.id))
    except Exception:
        logger.exception("Failed to queue event approved email for %s", user.email)


def send_event_rejected_email(user, event, reason=""):
    try:
        from .celery_tasks import send_event_rejected_task
        send_event_rejected_task.delay(str(user.id), str(event.id), reason)
    except Exception:
        logger.exception("Failed to queue event rejected email for %s", user.email)


def send_ticket_purchase_email(user, tickets: list, event):
    try:
        from .celery_tasks import send_ticket_purchase_task
        ticket_ids = [str(t.id) for t in tickets]
        send_ticket_purchase_task.delay(str(user.id), ticket_ids, str(event.id))
    except Exception:
        logger.exception("Failed to queue ticket purchase email for %s", user.email)


def send_ticket_cancelled_email(user, ticket, reason=""):
    try:
        from .celery_tasks import send_ticket_cancelled_task
        send_ticket_cancelled_task.delay(str(user.id), str(ticket.id), reason)
    except Exception:
        logger.exception("Failed to queue ticket cancelled email for %s", user.email)


def send_event_reminder(ticket):
    try:
        from .services import NotificationService
        NotificationService.event_reminder(ticket)
    except Exception:
        logger.exception(
            "Failed to send event reminder for ticket %s", ticket.ticket_number
        )
