"""
accounts/admin.py — Django admin registrations.
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _
from .models import User, OrganizerProfile, AttendeeProfile


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ["email", "full_name", "role", "is_approved", "is_active", "date_joined"]
    list_filter = ["role", "is_approved", "is_active"]
    search_fields = ["email", "first_name", "last_name"]
    ordering = ["-date_joined"]

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (_("Personal info"), {"fields": ("first_name", "last_name", "phone_number", "avatar")}),
        (_("Role & Status"), {"fields": ("role", "is_approved", "is_active")}),
        (_("Permissions"), {"fields": ("is_staff", "is_superuser", "groups", "user_permissions")}),
        (_("Dates"), {"fields": ("date_joined", "last_login")}),
    )
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("email", "first_name", "last_name", "role", "password1", "password2"),
        }),
    )

    readonly_fields = ["date_joined", "last_login"]


@admin.register(OrganizerProfile)
class OrganizerProfileAdmin(admin.ModelAdmin):
    list_display = ["organization_name", "user", "approved_at", "approved_by"]
    list_filter = ["approved_at"]
    search_fields = ["organization_name", "user__email"]
    raw_id_fields = ["user", "approved_by"]


@admin.register(AttendeeProfile)
class AttendeeProfileAdmin(admin.ModelAdmin):
    list_display = ["user", "created_at"]
    search_fields = ["user__email"]
    raw_id_fields = ["user"]
