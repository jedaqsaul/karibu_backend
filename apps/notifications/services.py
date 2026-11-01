"""
notifications/services.py

NotificationService — single point of entry for all notification dispatch.

Responsibilities:
  1. Create an in-app Notification record
  2. Render and send the HTML email
  3. Write an EmailLog record (success or failure)

Every public method is fire-and-forget: exceptions are caught, logged,
and never propagated to the caller. A failed notification must never
break the business transaction that triggered it.
"""

import logging
from datetime import datetime

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone

from .models import Notification, NotificationType, EmailLog

logger = logging.getLogger("karibu.notifications")


class NotificationService:
    """
    All dispatch methods follow the same pattern:
      1. Create Notification (in-app)
      2. Render HTML template
      3. Send email via Django's mail backend
      4. Log the attempt in EmailLog
    """

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @classmethod
    def _create_notification(
        cls,
        recipient,
        notification_type: str,
        title: str,
        message: str,
        action_url: str = "",
    ) -> Notification:
        """Create and return an in-app Notification record."""
        try:
            return Notification.objects.create(
                recipient=recipient,
                notification_type=notification_type,
                title=title,
                message=message,
                action_url=action_url,
            )
        except Exception:
            logger.exception(
                "Failed to create notification record: type=%s recipient=%s",
                notification_type, recipient.email,
            )
            return None

    @classmethod
    def _send_email(
        cls,
        recipient,
        subject: str,
        template_name: str,
        context: dict,
        email_type: str,
    ) -> bool:
        """
        Render template, send HTML email with plain-text fallback,
        and write an EmailLog record.
        Returns True on success, False on failure.
        """
        base_context = {
            "subject":      subject,
            "frontend_url": getattr(settings, "FRONTEND_URL", "https://karibu.co.ke"),
            "year":         datetime.now().year,
            "user":         recipient,
        }
        context = {**base_context, **context}

        html_content   = render_to_string(f"emails/{template_name}.html", context)
        plain_fallback = _html_to_plain(html_content)

        email_status    = EmailLog.EmailStatus.SENT
        error_message   = ""

        try:
            msg = EmailMultiAlternatives(
                subject=subject,
                body=plain_fallback,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[recipient.email],
            )
            msg.attach_alternative(html_content, "text/html")
            msg.send(fail_silently=False)
        except Exception as exc:
            email_status  = EmailLog.EmailStatus.FAILED
            error_message = str(exc)[:500]
            logger.exception(
                "Email dispatch failed: type=%s to=%s error=%s",
                email_type, recipient.email, error_message,
            )

        # Always write the log
        try:
            EmailLog.objects.create(
                recipient_email=recipient.email,
                recipient=recipient,
                subject=subject,
                email_type=email_type,
                status=email_status,
                error_message=error_message,
            )
        except Exception:
            logger.exception("Failed to write EmailLog for %s", recipient.email)

        return email_status == EmailLog.EmailStatus.SENT

    # ------------------------------------------------------------------
    # Account notifications
    # ------------------------------------------------------------------

    @classmethod
    def welcome(cls, user):
        """Sent immediately after registration."""
        try:
            cls._create_notification(
                recipient=user,
                notification_type=NotificationType.WELCOME,
                title="Welcome to Karibu!",
                message=f"Hi {user.first_name}, your account is ready. Start exploring events.",
                action_url="/events",
            )
            profile = getattr(user, "organizer_profile", None)
            if user.role == "organizer":
                template = "organizer_welcome"
                context  = {
                    "organization_name": profile.organization_name if profile else user.full_name,
                }
            else:
                template = "welcome"
                context  = {}

            cls._send_email(
                recipient=user,
                subject="Welcome to Karibu 🎉",
                template_name=template,
                context=context,
                email_type="welcome",
            )
        except Exception:
            logger.exception("welcome notification failed for %s", user.email)

    @classmethod
    def password_reset(cls, user, reset_url: str):
        """Sent when user requests a password reset."""
        try:
            cls._create_notification(
                recipient=user,
                notification_type=NotificationType.PASSWORD_RESET,
                title="Password Reset Requested",
                message="A password reset link has been sent to your email.",
            )
            cls._send_email(
                recipient=user,
                subject="Reset Your Karibu Password",
                template_name="password_reset",
                context={"reset_url": reset_url},
                email_type="password_reset",
            )
        except Exception:
            logger.exception("password_reset notification failed for %s", user.email)

    # ------------------------------------------------------------------
    # Organizer account notifications
    # ------------------------------------------------------------------

    @classmethod
    def organizer_approved(cls, user):
        """Sent when admin approves an organizer account."""
        try:
            profile = getattr(user, "organizer_profile", None)
            org_name = profile.organization_name if profile else user.full_name
            cls._create_notification(
                recipient=user,
                notification_type=NotificationType.ACCOUNT_APPROVED,
                title="Your organizer account is approved!",
                message=f"You can now create and publish events on Karibu.",
                action_url="/organizer/events/create",
            )
            cls._send_email(
                recipient=user,
                subject="Your Karibu Organizer Account is Approved ✅",
                template_name="organizer_approved",
                context={"organization_name": org_name},
                email_type="organizer_approved",
            )
        except Exception:
            logger.exception("organizer_approved notification failed for %s", user.email)

    @classmethod
    def organizer_rejected(cls, user, reason: str = ""):
        """Sent when admin rejects an organizer application."""
        try:
            profile = getattr(user, "organizer_profile", None)
            org_name = profile.organization_name if profile else user.full_name
            cls._create_notification(
                recipient=user,
                notification_type=NotificationType.ACCOUNT_REJECTED,
                title="Organizer application not approved",
                message=f"Your application could not be approved. {reason}".strip(),
            )
            cls._send_email(
                recipient=user,
                subject="Update on Your Karibu Organizer Application",
                template_name="organizer_rejected",
                context={"organization_name": org_name, "reason": reason},
                email_type="organizer_rejected",
            )
        except Exception:
            logger.exception("organizer_rejected notification failed for %s", user.email)

    # ------------------------------------------------------------------
    # Event notifications
    # ------------------------------------------------------------------

    @classmethod
    def event_approved(cls, user, event):
        """Sent to organizer when their event is approved and published."""
        try:
            cls._create_notification(
                recipient=user,
                notification_type=NotificationType.EVENT_APPROVED,
                title=f"'{event.title}' is now live!",
                message="Your event has been approved and published on Karibu.",
                action_url=f"/events/{event.slug}",
            )
            cls._send_email(
                recipient=user,
                subject=f"Your event '{event.title}' is live ✅",
                template_name="event_approved",
                context={"event": event},
                email_type="event_approved",
            )
        except Exception:
            logger.exception("event_approved notification failed for %s", user.email)

    @classmethod
    def event_rejected(cls, user, event, reason: str = ""):
        """Sent to organizer when their event is rejected."""
        try:
            cls._create_notification(
                recipient=user,
                notification_type=NotificationType.EVENT_REJECTED,
                title=f"'{event.title}' requires updates",
                message=f"Your event was not approved. {reason}".strip(),
                action_url=f"/organizer/events/{event.id}",
            )
            cls._send_email(
                recipient=user,
                subject=f"Update on your event '{event.title}'",
                template_name="event_rejected",
                context={"event": event, "reason": reason},
                email_type="event_rejected",
            )
        except Exception:
            logger.exception("event_rejected notification failed for %s", user.email)

    @classmethod
    def event_cancelled_to_attendees(cls, event):
        """
        Broadcast to all confirmed ticket holders when an event is cancelled.
        Each attendee gets their own in-app notification.
        """
        from apps.tickets.models import Ticket, TicketStatus
        tickets = (
            Ticket.objects
            .filter(event=event, status=TicketStatus.CONFIRMED)
            .select_related("attendee")
        )
        for ticket in tickets:
            try:
                cls._create_notification(
                    recipient=ticket.attendee,
                    notification_type=NotificationType.EVENT_CANCELLED,
                    title=f"'{event.title}' has been cancelled",
                    message="The event you have a ticket for has been cancelled.",
                    action_url="/tickets",
                )
                # No email per-attendee here to avoid bulk spam in Phase 5
                # Phase 7 will batch this via Celery
            except Exception:
                logger.exception(
                    "event_cancelled notification failed for ticket %s", ticket.ticket_number
                )

    @classmethod
    def event_reminder(cls, ticket):
        """
        Sent X days before the event to the ticket holder.
        Called by the management command / Celery task.
        """
        try:
            user  = ticket.attendee
            event = ticket.event
            days_until = (event.start_datetime.date() - timezone.now().date()).days

            cls._create_notification(
                recipient=user,
                notification_type=NotificationType.EVENT_REMINDER,
                title=f"Reminder: '{event.title}' is in {days_until} day(s)",
                message=f"Don't forget your ticket for {event.title} on "
                        f"{event.start_datetime.strftime('%d %B %Y')}.",
                action_url=f"/tickets/{ticket.id}",
            )
            cls._send_email(
                recipient=user,
                subject=f"Reminder: {event.title} is coming up!",
                template_name="event_reminder",
                context={"event": event, "ticket": ticket, "days_until": days_until},
                email_type="event_reminder",
            )
        except Exception:
            logger.exception(
                "event_reminder notification failed for ticket %s", ticket.ticket_number
            )

    # ------------------------------------------------------------------
    # Ticket notifications
    # ------------------------------------------------------------------

    @classmethod
    def ticket_purchased(cls, user, tickets: list, event):
        """Sent immediately after a successful ticket purchase."""
        try:
            ticket_count = len(tickets)
            cls._create_notification(
                recipient=user,
                notification_type=NotificationType.TICKET_PURCHASED,
                title=f"{ticket_count} ticket{'s' if ticket_count > 1 else ''} confirmed for '{event.title}'",
                message=f"Your purchase is confirmed. Download your tickets from your account.",
                action_url="/tickets",
            )
            cls._send_email(
                recipient=user,
                subject=f"Your ticket{'s' if ticket_count > 1 else ''} for {event.title} 🎟️",
                template_name="ticket_purchase",
                context={"event": event, "tickets": tickets},
                email_type="ticket_purchased",
            )
        except Exception:
            logger.exception("ticket_purchased notification failed for %s", user.email)

    @classmethod
    def ticket_cancelled(cls, user, ticket, reason: str = ""):
        """Sent when a ticket is cancelled (by attendee or admin)."""
        try:
            cls._create_notification(
                recipient=user,
                notification_type=NotificationType.TICKET_CANCELLED,
                title=f"Ticket {ticket.ticket_number} cancelled",
                message=f"Your ticket for '{ticket.event.title}' has been cancelled.",
                action_url="/tickets",
            )
            cls._send_email(
                recipient=user,
                subject=f"Ticket Cancellation: {ticket.ticket_number}",
                template_name="ticket_cancelled",
                context={"event": ticket.event, "ticket": ticket, "reason": reason},
                email_type="ticket_cancelled",
            )
        except Exception:
            logger.exception(
                "ticket_cancelled notification failed for ticket %s", ticket.ticket_number
            )


# ------------------------------------------------------------------
# Plain text fallback
# ------------------------------------------------------------------

def _html_to_plain(html: str) -> str:
    """
    Minimal HTML → plain text conversion for email fallback.
    Strips tags, collapses whitespace. No external library needed.
    """
    import re
    # Remove style and script blocks
    text = re.sub(r"<(style|script)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
    # Replace block elements with newlines
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</?(p|div|h[1-6]|tr|li)[^>]*>", "\n", text, flags=re.IGNORECASE)
    # Strip remaining tags
    text = re.sub(r"<[^>]+>", "", text)
    # Decode common entities
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">") \
               .replace("&nbsp;", " ").replace("&#39;", "'").replace("&middot;", "·")
    # Collapse whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()
