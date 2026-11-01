from django.contrib import admin
from .models import Notification, EmailLog


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display  = ["recipient", "notification_type", "title", "is_read", "created_at"]
    list_filter   = ["notification_type", "is_read"]
    search_fields = ["recipient__email", "title", "message"]
    readonly_fields = ["id", "recipient", "notification_type", "title",
                       "message", "action_url", "read_at", "created_at"]
    ordering = ["-created_at"]

    def has_add_permission(self, request):
        return False  # System-generated only

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(EmailLog)
class EmailLogAdmin(admin.ModelAdmin):
    list_display  = ["recipient_email", "email_type", "status", "subject", "sent_at"]
    list_filter   = ["status", "email_type", "sent_at"]
    search_fields = ["recipient_email", "subject"]
    readonly_fields = ["id", "recipient_email", "recipient", "subject",
                       "email_type", "status", "error_message", "sent_at"]
    ordering = ["-sent_at"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser
