"""
tickets/services.py

Shared ticket-creation logic used by more than one purchase path:
  - TicketPurchaseView (free events — instant confirm, no payment needed)
  - apps.payments MpesaCallbackView (paid events — confirm after M-Pesa
    payment succeeds)

Keeping this here (rather than duplicating it in apps.payments) means both
flows create tickets, generate PDFs, and send confirmation emails in
exactly the same way.
"""

import logging

from django.db import transaction

from shared.utils.ticket_number import generate_ticket_number
from shared.utils.pdf import generate_ticket_pdf

from .models import Ticket, TicketStatus

logger = logging.getLogger("karibu.tickets")


def create_confirmed_tickets(event, attendee, quantity, price_paid):
    """
    Atomically create `quantity` CONFIRMED tickets for `attendee` and bump
    event.tickets_sold. Does NOT check capacity — callers are expected to
    have already validated availability (see each call site for why).

    Returns the list of created Ticket instances.
    """
    created_tickets = []
    with transaction.atomic():
        for _ in range(quantity):
            ticket = Ticket.objects.create(
                event=event,
                attendee=attendee,
                ticket_number=generate_ticket_number(),
                price_paid=price_paid,
                currency="KES",
                status=TicketStatus.CONFIRMED,
            )
            created_tickets.append(ticket)

        event.tickets_sold = event.tickets_sold + quantity
        event.save(update_fields=["tickets_sold"])

    return created_tickets


def generate_and_attach_pdf(ticket: Ticket):
    """
    Generate the ticket PDF and store the URL.
    In production, the PDF bytes go to Cloudinary.
    In development, we just mark it as generated.
    """
    try:
        generate_ticket_pdf(ticket)
        # In production: upload to Cloudinary and store the returned URL
        # pdf_url = upload_pdf_to_cloudinary(pdf_bytes, ticket.ticket_number)
        # For now: mark generated and store an empty url (Cloudinary wired in Phase 7)
        ticket.pdf_generated = True
        ticket.save(update_fields=["pdf_generated"])
    except Exception:
        logger.exception(
            "PDF generation failed for ticket %s", ticket.ticket_number
        )


def send_ticket_email(attendee, tickets: list, event):
    """Dispatch purchase confirmation email with ticket details."""
    try:
        from apps.notifications.tasks import send_ticket_purchase_email
        send_ticket_purchase_email(attendee, tickets, event)
    except Exception:
        logger.exception("Ticket email failed for user %s", attendee.email)
