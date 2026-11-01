"""
analytics/serializers.py

Analytics serializers validate query parameters coming in
and structure the data going out.
All response data is built from service layer dicts — no model instances.
"""

from rest_framework import serializers


# ---------------------------------------------------------------------------
# Query parameter validators
# ---------------------------------------------------------------------------

class DateRangeParamsSerializer(serializers.Serializer):
    """Shared validator for date range + period params on analytics endpoints."""

    start_date = serializers.DateField(required=False)
    end_date   = serializers.DateField(required=False)
    period     = serializers.ChoiceField(
        choices=["day", "week", "month"],
        default="day",
        required=False,
    )

    def validate(self, attrs):
        start = attrs.get("start_date")
        end   = attrs.get("end_date")
        if start and end and end < start:
            raise serializers.ValidationError(
                {"end_date": "end_date must be after start_date."}
            )
        return attrs


class TopEventsParamsSerializer(DateRangeParamsSerializer):
    limit    = serializers.IntegerField(min_value=1, max_value=50, default=10, required=False)
    order_by = serializers.ChoiceField(
        choices=["revenue", "ticket_count"],
        default="revenue",
        required=False,
    )


class TopOrganizersParamsSerializer(DateRangeParamsSerializer):
    limit = serializers.IntegerField(min_value=1, max_value=50, default=10, required=False)


class EventPerformanceParamsSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=["draft", "pending_approval", "published", "cancelled", "completed"],
        required=False,
        allow_blank=True,
    )
