"""
logs/serializers.py
"""

from rest_framework import serializers
from .models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    user_display = serializers.SerializerMethodField()

    class Meta:
        model  = AuditLog
        fields = [
            "id", "user_display", "user_email", "user_role",
            "action", "category", "description",
            "ip_address", "content_type", "object_id",
            "created_at",
        ]

    def get_user_display(self, obj):
        if obj.user:
            return obj.user.full_name
        return obj.user_email or "system"


class AuditLogFilterSerializer(serializers.Serializer):
    """Validates query params for the audit log list endpoint."""
    action      = serializers.CharField(required=False, allow_blank=True)
    category    = serializers.ChoiceField(
        choices=AuditLog.ActionCategory.choices,
        required=False, allow_blank=True,
    )
    user_email  = serializers.EmailField(required=False)
    start_date  = serializers.DateField(required=False)
    end_date    = serializers.DateField(required=False)
    search      = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        start = attrs.get("start_date")
        end   = attrs.get("end_date")
        if start and end and end < start:
            raise serializers.ValidationError(
                {"end_date": "end_date must be after start_date."}
            )
        return attrs
