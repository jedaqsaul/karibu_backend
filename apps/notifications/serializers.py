"""
notifications/serializers.py
"""

from rest_framework import serializers
from .models import Notification, EmailLog


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Notification
        fields = [
            "id", "notification_type", "title", "message",
            "action_url", "is_read", "read_at", "created_at",
        ]
        read_only_fields = [
            "id", "notification_type", "title", "message",
            "action_url", "read_at", "created_at",
        ]


class MarkReadSerializer(serializers.Serializer):
    """Body for marking specific notifications as read."""
    notification_ids = serializers.ListField(
        child=serializers.UUIDField(),
        min_length=1,
        max_length=100,
    )


class EmailLogSerializer(serializers.ModelSerializer):
    class Meta:
        model  = EmailLog
        fields = [
            "id", "recipient_email", "subject", "email_type",
            "status", "error_message", "sent_at",
        ]
