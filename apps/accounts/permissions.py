"""
accounts/permissions.py

Reusable DRF permission classes for the Karibu platform.
All views must declare permission_classes explicitly — no implicit defaults.
"""

from rest_framework.permissions import BasePermission
from .models import UserRole


class IsSuperAdmin(BasePermission):
    """Grants access only to Super Admin users."""
    message = "Access restricted to Super Admins."

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role == UserRole.SUPER_ADMIN
        )


class IsOrganizer(BasePermission):
    """
    Grants access only to approved Organizers.
    Unapproved organizers are explicitly blocked with a descriptive message.
    """
    message = "Access restricted to approved Organizers."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.role != UserRole.ORGANIZER:
            return False
        if not request.user.is_approved:
            self.message = "Your organizer account is pending approval by an administrator."
            return False
        return True


class IsAttendee(BasePermission):
    """Grants access only to Attendee users."""
    message = "Access restricted to Attendees."

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role == UserRole.ATTENDEE
        )


class IsOrganizerOrAdmin(BasePermission):
    """Grants access to approved Organizers or Super Admins."""
    message = "Access restricted to Organizers or Admins."

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.role == UserRole.SUPER_ADMIN:
            return True
        if request.user.role == UserRole.ORGANIZER and request.user.is_approved:
            return True
        return False


class IsOwnerOrAdmin(BasePermission):
    """
    Object-level permission.
    Grants access if the user owns the object or is a Super Admin.
    The object must have a `user` or `owner` attribute.
    """
    message = "You do not have permission to access this resource."

    def has_object_permission(self, request, view, obj):
        if request.user.role == UserRole.SUPER_ADMIN:
            return True
        owner = getattr(obj, "user", None) or getattr(obj, "owner", None)
        return owner == request.user


class IsOwnerOrganizerOrAdmin(BasePermission):
    """
    Object-level permission for events.
    The object must have an `organizer` attribute pointing to a User.
    """
    message = "You do not have permission to modify this resource."

    def has_object_permission(self, request, view, obj):
        if request.user.role == UserRole.SUPER_ADMIN:
            return True
        organizer = getattr(obj, "organizer", None)
        return organizer == request.user
