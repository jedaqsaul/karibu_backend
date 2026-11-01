"""
tickets/views.py

Three access tiers:
  Attendee  — purchase, list own tickets, download PDF
  Organizer — list event tickets, scan QR codes
  Admin     — full platform ticket view, manual cancellation
"""

import io
from django.db import transaction
from django.http import HttpResponse, FileResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status, generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsSuperAdmin, IsOrganizer, IsOrganizerOrAdmin
from apps.logs.utils import log_action
from shared.utils.pdf import generate_ticket_pdf

from .models import Ticket, TicketStatus, TicketValidation
from .services import create_confirmed_tickets, generate_and_attach_pdf, send_ticket_email
from .serializers import (
    TicketPurchaseSerializer,
    TicketListSerializer,
    TicketDetailSerializer,
    TicketScanSerializer,
    AdminTicketSerializer,
)


# ---------------------------------------------------------------------------
# Attendee endpoints
# ---------------------------------------------------------------------------

class TicketPurchaseView(APIView):
    """
    POST /api/tickets/purchase/

    Instant-confirm purchase flow — FREE EVENTS ONLY.

    Paid events must go through apps.payments (M-Pesa STK Push):
      POST /api/payments/mpesa/stkpush/ initiates payment, and a ticket is
      only ever created once Safaricom confirms the payment succeeded via
      the callback. This endpoint intentionally refuses to issue a ticket
      for a paid event without a completed payment.

    Atomic purchase flow for free events:
      1. Validate event availability + seat count (serializer, with SELECT FOR UPDATE)
      2. Create Ticket record(s) with CONFIRMED status
      3. Increment event.tickets_sold
      4. Generate PDF
      5. Send confirmation email
      6. Return ticket data

    Wrapped in a single database transaction so a failure at any step
    rolls back entirely — no orphaned tickets, no oversold events.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = TicketPurchaseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        event    = serializer.validated_data["event"]
        quantity = serializer.validated_data["quantity"]
        attendee = request.user

        if not event.is_free:
            return Response(
                {
                    "error": (
                        "This event requires payment. "
                        "Initiate an M-Pesa payment via /api/payments/mpesa/stkpush/ "
                        "instead — a ticket is issued automatically once payment is confirmed."
                    )
                },
                status=status.HTTP_402_PAYMENT_REQUIRED,
            )

        created_tickets = create_confirmed_tickets(
            event=event, attendee=attendee, quantity=quantity, price_paid=event.ticket_price,
        )

        # PDF generation and email are outside the transaction —
        # failures here don't roll back the purchase.
        for ticket in created_tickets:
            generate_and_attach_pdf(ticket)

        send_ticket_email(attendee, created_tickets, event)

        log_action(
            attendee, "TICKET_PURCHASED",
            f"Purchased {quantity} ticket(s) for '{event.title}' — "
            f"Nos: {', '.join(t.ticket_number for t in created_tickets)}",
        )

        return Response(
            {
                "message": f"{quantity} ticket(s) purchased successfully.",
                "tickets": TicketListSerializer(created_tickets, many=True).data,
            },
            status=status.HTTP_201_CREATED,
        )


class MyTicketListView(generics.ListAPIView):
    """GET /api/tickets/ — Paginated list of the authenticated attendee's tickets."""
    permission_classes = [IsAuthenticated]
    serializer_class   = TicketListSerializer

    def get_queryset(self):
        qs = (
            Ticket.objects
            .filter(attendee=self.request.user)
            .select_related("event", "event__category")
            .order_by("-purchased_at")
        )
        # Optional status filter
        ticket_status = self.request.query_params.get("status")
        if ticket_status:
            qs = qs.filter(status=ticket_status)
        return qs


class MyTicketDetailView(APIView):
    """GET /api/tickets/<id>/ — Full detail of one of the attendee's own tickets."""
    permission_classes = [IsAuthenticated]

    def get(self, request, id):
        ticket = get_object_or_404(
            Ticket.objects.select_related("event", "attendee")
                          .prefetch_related("validations"),
            id=id,
            attendee=request.user,
        )
        return Response(
            TicketDetailSerializer(ticket, context={"request": request}).data
        )


class TicketDownloadView(APIView):
    """
    GET /api/tickets/<id>/download/

    Returns the ticket PDF as a file download.
    Regenerates the PDF on the fly if not yet generated (safety net).
    Increments download_count each time.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, id):
        ticket = get_object_or_404(
            Ticket.objects.select_related("event", "attendee"),
            id=id,
            attendee=request.user,
        )

        if ticket.status != TicketStatus.CONFIRMED:
            return Response(
                {"error": f"Cannot download a ticket with status '{ticket.status}'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        pdf_bytes = generate_ticket_pdf(ticket)

        ticket.download_count += 1
        ticket.save(update_fields=["download_count"])

        log_action(
            request.user, "TICKET_DOWNLOADED",
            f"Downloaded ticket {ticket.ticket_number}",
        )

        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = (
            f'attachment; filename="karibu-ticket-{ticket.ticket_number}.pdf"'
        )
        return response


class TicketCancelView(APIView):
    """
    POST /api/tickets/<id>/cancel/

    Attendee self-cancellation.
    Only CONFIRMED tickets can be cancelled.
    Tickets are not deletable — they remain with status=CANCELLED for records.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, id):
        ticket = get_object_or_404(
            Ticket.objects.select_related("event"),
            id=id,
            attendee=request.user,
        )

        if ticket.status != TicketStatus.CONFIRMED:
            return Response(
                {"error": f"Only confirmed tickets can be cancelled. This ticket is '{ticket.status}'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not ticket.event.is_upcoming:
            return Response(
                {"error": "Cannot cancel a ticket for an event that has already started or passed."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            ticket.status = TicketStatus.CANCELLED
            ticket.save(update_fields=["status", "updated_at"])

            # Return the seat to the pool
            ticket.event.tickets_sold = max(0, ticket.event.tickets_sold - 1)
            ticket.event.save(update_fields=["tickets_sold"])

        log_action(
            request.user, "TICKET_CANCELLED",
            f"Attendee cancelled ticket {ticket.ticket_number} for '{ticket.event.title}'",
        )

        return Response({"message": f"Ticket {ticket.ticket_number} has been cancelled."})


# ---------------------------------------------------------------------------
# Organizer endpoints
# ---------------------------------------------------------------------------

class OrganizerEventTicketsView(generics.ListAPIView):
    """
    GET /api/organizer/events/<event_id>/tickets/

    All tickets for a specific event the organizer owns.
    Supports ?status= filter.
    """
    permission_classes = [IsOrganizer]
    serializer_class   = AdminTicketSerializer

    def get_queryset(self):
        from apps.events.models import Event
        event = get_object_or_404(
            Event, id=self.kwargs["event_id"], organizer=self.request.user
        )
        qs = (
            Ticket.objects
            .filter(event=event)
            .select_related("event", "attendee")
            .prefetch_related("validations")
            .order_by("-purchased_at")
        )
        ticket_status = self.request.query_params.get("status")
        if ticket_status:
            qs = qs.filter(status=ticket_status)
        return qs


class TicketScanView(APIView):
    """
    POST /api/organizer/tickets/scan/

    QR code validation endpoint for the organizer's scanner.
    Accepts the raw scanned string + event_id.

    Validation logic:
      1. Look up the ticket by code
      2. Confirm it belongs to the correct event
      3. Confirm it is CONFIRMED (not used, cancelled, etc.)
      4. Mark it USED
      5. Write an immutable TicketValidation record regardless of outcome
    """
    permission_classes = [IsOrganizer]

    def post(self, request):
        serializer = TicketScanSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        code     = serializer.validated_data["code"]
        event_id = serializer.validated_data["event_id"]

        # Verify the event belongs to this organizer
        from apps.events.models import Event
        event = get_object_or_404(Event, id=event_id, organizer=request.user)

        ticket = None
        result = TicketValidation.ScanResult.INVALID_CODE

        try:
            # ticket_code stored as UUID; QR payload is uppercase hex without dashes
            import uuid as _uuid
            ticket_uuid = _uuid.UUID(code)
            ticket = Ticket.objects.select_for_update().get(ticket_code=ticket_uuid)

            if ticket.event_id != event.id:
                result = TicketValidation.ScanResult.EVENT_MISMATCH

            elif ticket.status == TicketStatus.USED:
                result = TicketValidation.ScanResult.ALREADY_USED

            elif ticket.status in (TicketStatus.CANCELLED, TicketStatus.REFUNDED):
                result = TicketValidation.ScanResult.CANCELLED

            elif ticket.status == TicketStatus.CONFIRMED:
                with transaction.atomic():
                    ticket.status = TicketStatus.USED
                    ticket.save(update_fields=["status", "updated_at"])
                result = TicketValidation.ScanResult.SUCCESS

        except (Ticket.DoesNotExist, ValueError):
            result = TicketValidation.ScanResult.INVALID_CODE

        # Write validation record — always, regardless of outcome
        TicketValidation.objects.create(
            ticket=ticket if result != TicketValidation.ScanResult.INVALID_CODE else None,
            scanned_by=request.user,
            scanned_code=code,
            result=result,
            device_info=request.META.get("HTTP_USER_AGENT", "")[:300],
        )

        is_success = result == TicketValidation.ScanResult.SUCCESS
        log_action(
            request.user, "TICKET_SCANNED",
            f"Scan result: {result} — code: {code[:16]}",
        )

        return Response(
            {
                "valid": is_success,
                "result": result,
                "result_display": dict(TicketValidation.ScanResult.choices).get(result, result),
                "ticket": TicketListSerializer(ticket).data if ticket else None,
            },
            status=status.HTTP_200_OK,
        )


# ---------------------------------------------------------------------------
# Super Admin endpoints
# ---------------------------------------------------------------------------

class AdminTicketListView(generics.ListAPIView):
    """GET /api/admin/tickets/ — All tickets across all events."""
    permission_classes = [IsSuperAdmin]
    serializer_class   = AdminTicketSerializer

    def get_queryset(self):
        qs = (
            Ticket.objects
            .select_related("event", "attendee")
            .prefetch_related("validations")
            .order_by("-purchased_at")
        )
        event_id      = self.request.query_params.get("event_id")
        ticket_status = self.request.query_params.get("status")

        if event_id:
            qs = qs.filter(event_id=event_id)
        if ticket_status:
            qs = qs.filter(status=ticket_status)
        return qs


class AdminTicketDetailView(APIView):
    """GET /api/admin/tickets/<id>/ — Full ticket detail."""
    permission_classes = [IsSuperAdmin]

    def get(self, request, id):
        ticket = get_object_or_404(
            Ticket.objects
                  .select_related("event", "attendee")
                  .prefetch_related("validations"),
            id=id,
        )
        return Response(
            AdminTicketSerializer(ticket, context={"request": request}).data
        )


class AdminTicketCancelView(APIView):
    """POST /api/admin/tickets/<id>/cancel/ — Admin force-cancels a ticket."""
    permission_classes = [IsSuperAdmin]

    def post(self, request, id):
        ticket = get_object_or_404(
            Ticket.objects.select_related("event"),
            id=id,
        )

        if ticket.status not in (TicketStatus.CONFIRMED, TicketStatus.PENDING):
            return Response(
                {"error": f"Cannot cancel a ticket with status '{ticket.status}'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        reason = request.data.get("reason", "Cancelled by administrator.")

        with transaction.atomic():
            ticket.status = TicketStatus.CANCELLED
            ticket.save(update_fields=["status", "updated_at"])

            if ticket.event.tickets_sold > 0:
                ticket.event.tickets_sold -= 1
                ticket.event.save(update_fields=["tickets_sold"])

        log_action(
            request.user, "ADMIN_TICKET_CANCELLED",
            f"Admin cancelled ticket {ticket.ticket_number}. Reason: {reason}",
        )
        return Response(
            {"message": f"Ticket {ticket.ticket_number} cancelled.", "reason": reason}
        )



