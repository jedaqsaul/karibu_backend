from django.contrib import admin
from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display  = ["action", "category", "user_email", "user_role",
                     "description", "ip_address", "created_at"]
    list_filter   = ["category", "action", "created_at"]
    search_fields = ["user_email", "action", "description", "ip_address"]
    readonly_fields = [
        "id", "user", "user_email", "user_role",
        "action", "category", "description",
        "ip_address", "user_agent",
        "content_type", "object_id",
        "created_at",
    ]
    ordering = ["-created_at"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser
