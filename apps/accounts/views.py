"""
accounts/views.py

All authentication and account management views.
Every view is a class-based APIView or ViewSet — no function-based views.
Permission classes are always declared explicitly.
"""

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status, generics
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.exceptions import TokenError

from apps.logs.utils import log_action
from apps.notifications.tasks import send_welcome_email

from .models import OrganizerProfile, UserRole
from .permissions import IsSuperAdmin, IsOrganizerOrAdmin, IsOrganizer
from .serializers import (
    AttendeeRegisterSerializer,
    OrganizerRegisterSerializer,
    UserProfileSerializer,
    AvatarUploadSerializer,
    ChangePasswordSerializer,
    PasswordResetRequestSerializer,
    PasswordResetConfirmSerializer,
    UserAdminSerializer,
    UserListSerializer,
    OrganizerProfileSerializer,
    OrganizerOwnProfileSerializer,
    OrganizerApprovalSerializer,
    KaribuTokenObtainPairSerializer,
)

User = get_user_model()


# ---------------------------------------------------------------------------
# Auth endpoints
# ---------------------------------------------------------------------------

class AttendeeRegisterView(APIView):
    """POST /api/auth/register/ — Public attendee registration."""
    permission_classes = [AllowAny]
    throttle_scope = "auth"

    def post(self, request):
        serializer = AttendeeRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        # Issue tokens immediately so the user is logged in after registering
        refresh = RefreshToken.for_user(user)

        # Fire welcome email asynchronously (using signals/tasks)
        send_welcome_email(user)
        log_action(user, "REGISTER", f"New attendee registered: {user.email}")

        return Response(
            {
                "message": "Registration successful.",
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": {
                    "id": str(user.id),
                    "email": user.email,
                    "full_name": user.full_name,
                    "role": user.role,
                },
            },
            status=status.HTTP_201_CREATED,
        )


class OrganizerRegisterView(APIView):
    """POST /api/auth/register/organizer/ — Organizer self-registration."""
    permission_classes = [AllowAny]
    throttle_scope = "auth"

    def post(self, request):
        serializer = OrganizerRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        send_welcome_email(user)
        log_action(user, "REGISTER", f"New organizer registered (pending approval): {user.email}")

        return Response(
            {
                "message": (
                    "Organizer registration successful. "
                    "Your account is pending approval by an administrator."
                ),
                "user": {
                    "id": str(user.id),
                    "email": user.email,
                    "full_name": user.full_name,
                    "role": user.role,
                    "is_approved": user.is_approved,
                },
            },
            status=status.HTTP_201_CREATED,
        )


class LoginView(TokenObtainPairView):
    """
    POST /api/auth/login/
    Returns access token, refresh token, and user summary.
    Uses KaribuTokenObtainPairSerializer which embeds role in the JWT payload.
    """
    permission_classes = [AllowAny]
    serializer_class = KaribuTokenObtainPairSerializer
    throttle_scope = "auth"

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code == 200:
            # Log successful login — user lookup is lightweight here
            try:
                user = User.objects.get(email=request.data.get("email", "").lower())
                log_action(user, "LOGIN", f"User logged in: {user.email}")
            except User.DoesNotExist:
                pass
        return response


class LogoutView(APIView):
    """
    POST /api/auth/logout/
    Blacklists the refresh token so it can never be used again.
    Access token expires naturally (15 min).
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get("refresh")
        if not refresh_token:
            return Response(
                {"error": "Refresh token is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
            log_action(request.user, "LOGOUT", f"User logged out: {request.user.email}")
        except TokenError:
            return Response(
                {"error": "Invalid or expired token."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response({"message": "Logged out successfully."}, status=status.HTTP_200_OK)


class TokenRefreshWithRotationView(APIView):
    """
    POST /api/auth/token/refresh/
    Issues a new access + refresh token pair.
    Old refresh token is blacklisted immediately (rotation enabled in settings).
    Uses simplejwt's built-in view — this is just a wrapper with logging.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        from rest_framework_simplejwt.views import TokenRefreshView
        return TokenRefreshView.as_view()(request._request)


# ---------------------------------------------------------------------------
# Profile endpoints
# ---------------------------------------------------------------------------

class MyProfileView(APIView):
    """
    GET  /api/auth/me/  — Fetch own profile
    PATCH /api/auth/me/ — Update own profile (name, phone)
    """
    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get(self, request):
        serializer = UserProfileSerializer(request.user)
        return Response(serializer.data)

    def patch(self, request):
        serializer = UserProfileSerializer(
            request.user, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        log_action(request.user, "PROFILE_UPDATE", "User updated their profile.")
        return Response(serializer.data)


class AvatarUploadView(APIView):
    """
    POST /api/auth/me/avatar/ — Upload or replace own avatar.
    Accepts multipart/form-data.
    """
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        serializer = AvatarUploadSerializer(
            request.user, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        log_action(request.user, "AVATAR_UPLOAD", "User updated their avatar.")
        return Response(
            {
                "message": "Avatar updated successfully.",
                "avatar_url": request.user.avatar.url if request.user.avatar else None,
            }
        )


class ChangePasswordView(APIView):
    """POST /api/auth/me/change-password/ — Authenticated password change."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        log_action(request.user, "PASSWORD_CHANGE", "User changed their password.")
        return Response({"message": "Password updated successfully."})


class OrganizerOwnProfileView(APIView):
    """
    GET   /api/organizer/profile/  — Fetch own organizer profile (org name, bio, website, banner)
    PATCH /api/organizer/profile/  — Update own organizer profile

    Distinct from /api/auth/me/, which covers the shared User fields
    (name, phone, avatar). This endpoint covers the organizer-specific
    OrganizerProfile fields.
    """
    permission_classes = [IsOrganizer]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_object(self, request):
        profile, _ = OrganizerProfile.objects.get_or_create(
            user=request.user,
            defaults={"organization_name": request.user.full_name or request.user.email},
        )
        return profile

    def get(self, request):
        serializer = OrganizerOwnProfileSerializer(self.get_object(request))
        return Response(serializer.data)

    def patch(self, request):
        serializer = OrganizerOwnProfileSerializer(
            self.get_object(request), data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        log_action(request.user, "PROFILE_UPDATE", "Organizer updated their organization profile.")
        return Response(serializer.data)


# ---------------------------------------------------------------------------
# Password reset (unauthenticated)
# ---------------------------------------------------------------------------

class PasswordResetRequestView(APIView):
    """
    POST /api/auth/password-reset/
    Sends a reset email. Always returns 200 to prevent user enumeration.
    """
    permission_classes = [AllowAny]
    throttle_scope = "auth"

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]

        try:
            user = User.objects.get(email=email)
            from apps.notifications.tasks import send_password_reset_email
            send_password_reset_email(user)
        except User.DoesNotExist:
            pass  # Silent — prevents enumeration

        return Response(
            {"message": "If an account with that email exists, a reset link has been sent."}
        )


class PasswordResetConfirmView(APIView):
    """POST /api/auth/password-reset/confirm/ — Validate token and set new password."""
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        from apps.notifications.utils import verify_password_reset_token
        user = verify_password_reset_token(serializer.validated_data["token"])

        if not user:
            return Response(
                {"error": "Invalid or expired reset token."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.set_password(serializer.validated_data["new_password"])
        user.save(update_fields=["password", "updated_at"])
        log_action(user, "PASSWORD_RESET", "Password reset via email token.")

        return Response({"message": "Password reset successfully. You can now log in."})


# ---------------------------------------------------------------------------
# Super Admin — User management
# ---------------------------------------------------------------------------

class AdminUserListView(generics.ListAPIView):
    """GET /api/admin/users/ — Paginated list of all users."""
    permission_classes = [IsSuperAdmin]
    serializer_class = UserListSerializer

    def get_queryset(self):
        qs = User.objects.all()
        role = self.request.query_params.get("role")
        is_active = self.request.query_params.get("is_active")
        search = self.request.query_params.get("search")

        if role:
            qs = qs.filter(role=role)
        if is_active is not None:
            qs = qs.filter(is_active=is_active.lower() == "true")
        if search:
            qs = qs.filter(email__icontains=search) | qs.filter(first_name__icontains=search)

        return qs.order_by("-date_joined")


class AdminUserDetailView(generics.RetrieveUpdateAPIView):
    """GET/PATCH /api/admin/users/<id>/ — Full user detail and updates."""
    permission_classes = [IsSuperAdmin]
    serializer_class = UserAdminSerializer
    queryset = User.objects.all()
    lookup_field = "id"

    def perform_update(self, serializer):
        user = serializer.save()
        log_action(
            self.request.user, "ADMIN_USER_UPDATE",
            f"Admin updated user: {user.email}"
        )


class AdminDeactivateUserView(APIView):
    """POST /api/admin/users/<id>/deactivate/ — Soft-deactivate a user."""
    permission_classes = [IsSuperAdmin]

    def post(self, request, id):
        try:
            user = User.objects.get(id=id)
        except User.DoesNotExist:
            return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)

        if user.role == UserRole.SUPER_ADMIN:
            return Response(
                {"error": "Cannot deactivate a Super Admin."},
                status=status.HTTP_403_FORBIDDEN,
            )

        user.is_active = False
        user.save(update_fields=["is_active"])
        log_action(request.user, "USER_DEACTIVATE", f"Deactivated user: {user.email}")
        return Response({"message": f"User {user.email} has been deactivated."})


class AdminActivateUserView(APIView):
    """POST /api/admin/users/<id>/activate/ — Reactivate a previously deactivated user."""
    permission_classes = [IsSuperAdmin]

    def post(self, request, id):
        try:
            user = User.objects.get(id=id)
        except User.DoesNotExist:
            return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)

        user.is_active = True
        user.save(update_fields=["is_active"])
        log_action(request.user, "ADMIN_USER_UPDATE", f"Reactivated user: {user.email}")
        return Response({"message": f"User {user.email} has been reactivated."})


# ---------------------------------------------------------------------------
# Super Admin — Organizer approval
# ---------------------------------------------------------------------------

class OrganizerApprovalListView(generics.ListAPIView):
    """GET /api/admin/organizers/pending/ — All organizers awaiting approval."""
    permission_classes = [IsSuperAdmin]
    serializer_class = OrganizerProfileSerializer

    def get_queryset(self):
        return OrganizerProfile.objects.filter(
            user__is_approved=False,
            user__role=UserRole.ORGANIZER,
            user__is_active=True,
        ).select_related("user").order_by("-created_at")


class OrganizerApprovalActionView(APIView):
    """
    POST /api/admin/organizers/<id>/approval/
    Body: { "action": "approve" | "reject", "rejection_reason": "..." }
    """
    permission_classes = [IsSuperAdmin]

    def post(self, request, id):
        try:
            profile = OrganizerProfile.objects.select_related("user").get(id=id)
        except OrganizerProfile.DoesNotExist:
            return Response({"error": "Organizer profile not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = OrganizerApprovalSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        action = serializer.validated_data["action"]
        user = profile.user

        if action == "approve":
            user.is_approved = True
            user.save(update_fields=["is_approved"])
            profile.approved_by = request.user
            profile.approved_at = timezone.now()
            profile.rejection_reason = ""
            profile.save(update_fields=["approved_by", "approved_at", "rejection_reason"])

            from apps.notifications.tasks import send_organizer_approved_email
            send_organizer_approved_email(user)
            log_action(request.user, "ORGANIZER_APPROVED", f"Approved organizer: {user.email}")

            return Response({"message": f"Organizer {user.email} has been approved."})

        else:  # reject
            reason = serializer.validated_data["rejection_reason"]
            profile.rejection_reason = reason
            profile.save(update_fields=["rejection_reason"])

            from apps.notifications.tasks import send_organizer_rejected_email
            send_organizer_rejected_email(user, reason)
            log_action(request.user, "ORGANIZER_REJECTED",
                       f"Rejected organizer: {user.email}. Reason: {reason}")

            return Response({"message": f"Organizer {user.email} has been rejected."})
