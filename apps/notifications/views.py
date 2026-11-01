"""
notifications/views.py

In-app notification inbox endpoints.
Attendees and organizers can fetch, mark-read, and clear their notifications.
Admin gets a read-only EmailLog view for debugging delivery.
"""

from django.utils import timezone
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsSuperAdmin
from apps.logs.utils import log_action

from .models import Notification, EmailLog
from .serializers import NotificationSerializer, MarkReadSerializer, EmailLogSerializer


class NotificationListView(generics.ListAPIView):
    """
    GET /api/notifications/
    Paginated list of the authenticated user's notifications.
    Supports ?is_read=true|false filter.
    """
    permission_classes = [IsAuthenticated]
    serializer_class   = NotificationSerializer

    def get_queryset(self):
        qs = Notification.objects.filter(recipient=self.request.user)
        is_read = self.request.query_params.get("is_read")
        if is_read is not None:
            qs = qs.filter(is_read=is_read.lower() == "true")
        return qs.order_by("-created_at")


class NotificationUnreadCountView(APIView):
    """
    GET /api/notifications/unread-count/
    Lightweight endpoint polled by the frontend bell icon.
    Returns { "unread_count": N }
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        count = Notification.objects.filter(
            recipient=request.user, is_read=False
        ).count()
        return Response({"unread_count": count})


class NotificationMarkReadView(APIView):
    """
    POST /api/notifications/mark-read/
    Body: { "notification_ids": ["uuid1", "uuid2", ...] }
    Marks the given notifications as read. Only acts on the user's own notifications.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = MarkReadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        ids = serializer.validated_data["notification_ids"]
        updated = Notification.objects.filter(
            recipient=request.user,
            id__in=ids,
            is_read=False,
        ).update(is_read=True, read_at=timezone.now())

        return Response({"marked_read": updated})


class NotificationMarkAllReadView(APIView):
    """
    POST /api/notifications/mark-all-read/
    Marks every unread notification for the user as read in one query.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        updated = Notification.objects.filter(
            recipient=request.user,
            is_read=False,
        ).update(is_read=True, read_at=timezone.now())

        return Response({"marked_read": updated})


class NotificationDeleteView(APIView):
    """
    DELETE /api/notifications/<id>/
    Hard-delete a single notification. Only owner can delete.
    """
    permission_classes = [IsAuthenticated]

    def delete(self, request, id):
        try:
            notification = Notification.objects.get(id=id, recipient=request.user)
        except Notification.DoesNotExist:
            return Response(
                {"error": "Notification not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        notification.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class NotificationClearAllView(APIView):
    """
    DELETE /api/notifications/clear/
    Deletes all of the authenticated user's notifications.
    """
    permission_classes = [IsAuthenticated]

    def delete(self, request):
        deleted_count, _ = Notification.objects.filter(recipient=request.user).delete()
        return Response({"deleted": deleted_count})


# ---------------------------------------------------------------------------
# Admin — Email log
# ---------------------------------------------------------------------------

class AdminEmailLogListView(generics.ListAPIView):
    """
    GET /api/admin/email-logs/
    Full email dispatch log for debugging.
    Supports ?status=sent|failed and ?email_type= filters.
    """
    permission_classes = [IsSuperAdmin]
    serializer_class   = EmailLogSerializer

    def get_queryset(self):
        qs = EmailLog.objects.all()
        log_status = self.request.query_params.get("status")
        email_type = self.request.query_params.get("email_type")
        recipient  = self.request.query_params.get("recipient")

        if log_status:
            qs = qs.filter(status=log_status)
        if email_type:
            qs = qs.filter(email_type=email_type)
        if recipient:
            qs = qs.filter(recipient_email__icontains=recipient)

        return qs.order_by("-sent_at")
