"""
payments/serializers.py
"""

from rest_framework import serializers

from .models import MpesaTransaction
from .services import normalize_phone


class STKPushInitiateSerializer(serializers.Serializer):
    """
    Input for POST /api/payments/mpesa/stkpush/

    Client sends event_id, quantity, and the phone number to charge —
    everything else (amount, account reference, etc.) is derived server-side.
    """
    event_id     = serializers.UUIDField()
    quantity     = serializers.IntegerField(min_value=1, max_value=10, default=1)
    phone_number = serializers.CharField()

    def validate_phone_number(self, value):
        try:
            return normalize_phone(value)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc))

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

        if event.is_free:
            raise serializers.ValidationError(
                {"event_id": "This event is free — use /api/tickets/purchase/ instead."}
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


class MpesaTransactionSerializer(serializers.ModelSerializer):
    """Status of a payment — polled by the frontend after initiating STK push."""
    event_title = serializers.CharField(source="event.title", read_only=True)

    class Meta:
        model = MpesaTransaction
        fields = [
            "id", "status", "amount", "quantity", "phone_number",
            "checkout_request_id", "mpesa_receipt_number", "result_desc",
            "event_title", "ticket_snapshot", "created_at", "updated_at",
        ]
        read_only_fields = fields
