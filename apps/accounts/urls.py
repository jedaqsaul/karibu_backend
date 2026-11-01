"""
accounts/urls.py — All auth and account management URL patterns.
Mounted at /api/ in config/urls.py
"""

from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    AttendeeRegisterView,
    OrganizerRegisterView,
    LoginView,
    LogoutView,
    MyProfileView,
    AvatarUploadView,
    ChangePasswordView,
    PasswordResetRequestView,
    PasswordResetConfirmView,
    AdminUserListView,
    AdminUserDetailView,
    AdminDeactivateUserView,
    AdminActivateUserView,
    OrganizerApprovalListView,
    OrganizerApprovalActionView,
    OrganizerOwnProfileView,
)

# Auth endpoints
auth_urlpatterns = [
    path("auth/register/", AttendeeRegisterView.as_view(), name="attendee-register"),
    path("auth/register/organizer/", OrganizerRegisterView.as_view(), name="organizer-register"),
    path("auth/login/", LoginView.as_view(), name="login"),
    path("auth/logout/", LogoutView.as_view(), name="logout"),
    path("auth/token/refresh/", TokenRefreshView.as_view(), name="token-refresh"),

    # Profile
    path("auth/me/", MyProfileView.as_view(), name="my-profile"),
    path("auth/me/avatar/", AvatarUploadView.as_view(), name="avatar-upload"),
    path("auth/me/change-password/", ChangePasswordView.as_view(), name="change-password"),

    # Password reset (unauthenticated)
    path("auth/password-reset/", PasswordResetRequestView.as_view(), name="password-reset-request"),
    path("auth/password-reset/confirm/", PasswordResetConfirmView.as_view(), name="password-reset-confirm"),
]

# Organizer self-service endpoints
organizer_urlpatterns = [
    path("organizer/profile/", OrganizerOwnProfileView.as_view(), name="organizer-own-profile"),
]

# Admin endpoints
admin_urlpatterns = [
    path("admin/users/", AdminUserListView.as_view(), name="admin-user-list"),
    path("admin/users/<uuid:id>/", AdminUserDetailView.as_view(), name="admin-user-detail"),
    path("admin/users/<uuid:id>/deactivate/", AdminDeactivateUserView.as_view(), name="admin-deactivate-user"),
    path("admin/users/<uuid:id>/activate/", AdminActivateUserView.as_view(), name="admin-activate-user"),
    path("admin/organizers/pending/", OrganizerApprovalListView.as_view(), name="admin-organizer-pending"),
    path("admin/organizers/<uuid:id>/approval/", OrganizerApprovalActionView.as_view(), name="admin-organizer-approval"),
]

urlpatterns = auth_urlpatterns + organizer_urlpatterns + admin_urlpatterns
