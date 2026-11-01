"""
tickets/serializers.py

All ticket serializers. Fields are always declared explicitly.
The purchase serializer is deliberately minimal — quantity and event_id only.
All ticket pricing, code generation, and status are server-controlled.
"""

from rest_framework import serializers
from apps.events.serializers import EventListSerializer
from .models import Ticket, TicketStatus, TicketValidation


class TicketPurchaseSerializer(serializers.Serializer):
    """
    Input for POST /api/tickets/purchase/
    Client sends only event_id and quantity.
    Everything else — price, code, number — is set server-side.
    """
    event_id = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1, max_value=10)

    def validate(self, attrs):
        from apps.events.models import Event, EventStatus

        try:
            event = Event.objects.select_for_update().get(
                id=attrs["event_id"],
                status=EventStatus.PUBLISHED,
            )
        except Event.DoesNotExist:
            raise serializers.ValidationError(
                {"event_id": "Event not found or is not available for purchase."}
            )

        qty = attrs["quantity"]
        if event.tickets_remaining < qty:
            raise serializers.ValidationError(
                {
                    "quantity": (
                        f"Only {event.tickets_remaining} ticket(s) remaining. "
                        f"You requested {qty}."
                    )
                }
            )

        attrs["event"] = event
        return attrs


class TicketListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views — my tickets page."""
    event_title  = serializers.CharField(source="event.title", read_only=True)
    event_slug   = serializers.CharField(source="event.slug", read_only=True)
    event_date   = serializers.DateTimeField(source="event.start_datetime", read_only=True)
    event_venue  = serializers.CharField(source="event.venue", read_only=True)
    event_city   = serializers.CharField(source="event.city", read_only=True)

    class Meta:
        model  = Ticket
        fields = [
            "id", "ticket_number", "ticket_code",
            "event_title", "event_slug", "event_date", "event_venue", "event_city",
            "price_paid", "currency", "status",
            "pdf_generated", "download_count",
            "purchased_at",
        ]


class TicketDetailSerializer(serializers.ModelSerializer):
    """Full ticket detail including event info and validation history."""
    event        = EventListSerializer(read_only=True)
    validations  = serializers.SerializerMethodField()
    qr_payload   = serializers.CharField(read_only=True)

    class Meta:
        model  = Ticket
        fields = [
            "id", "ticket_number", "ticket_code", "qr_payload",
            "event", "price_paid", "currency", "status",
            "pdf_generated", "pdf_url", "download_count",
            "email_sent", "email_sent_at",
            "purchased_at", "updated_at",
            "validations",
        ]

    def get_validations(self, obj):
        # Only show validation history to organizers/admins via the admin serializer.
        # Attendees see an empty list here — they only need to know if their ticket is valid.
        request = self.context.get("request")
        if request and hasattr(request.user, "role"):
            from apps.accounts.models import UserRole
            if request.user.role in (UserRole.ORGANIZER, UserRole.SUPER_ADMIN):
                return TicketValidationSerializer(
                    obj.validations.all()[:10], many=True
                ).data
        return []


class TicketValidationSerializer(serializers.ModelSerializer):
    scanned_by_name = serializers.CharField(
        source="scanned_by.full_name", read_only=True, default=""
    )

    class Meta:
        model  = TicketValidation
        fields = [
            "id", "scanned_code", "result",
            "scanned_by_name", "scanned_at", "device_info",
        ]


class TicketScanSerializer(serializers.Serializer):
    """
    Input for POST /api/organizer/tickets/scan/
    Organizer's scanner sends the raw QR code string and the event they're running.
    """
    code     = serializers.CharField(max_length=100)
    event_id = serializers.UUIDField()

    def validate_code(self, value):
        return value.strip().upper().replace("-", "")


class TicketCancelSerializer(serializers.Serializer):
    """Admin/organizer ticket cancellation input."""
    reason = serializers.CharField(required=False, allow_blank=True)


class AdminTicketSerializer(serializers.ModelSerializer):
    """Full admin view of a ticket — all fields, read-only."""
    event      = EventListSerializer(read_only=True)
    attendee_email = serializers.EmailField(source="attendee.email", read_only=True)
    attendee_name  = serializers.CharField(source="attendee.full_name", read_only=True)
    validations    = TicketValidationSerializer(many=True, read_only=True)
    qr_payload     = serializers.CharField(read_only=True)

    class Meta:
        model  = Ticket
        fields = [
            "id", "ticket_number", "ticket_code", "qr_payload",
            "event", "attendee_email", "attendee_name",
            "price_paid", "currency", "status",
            "pdf_generated", "pdf_url", "download_count",
            "email_sent", "email_sent_at",
            "purchased_at", "updated_at",
            "validations",
        ]
