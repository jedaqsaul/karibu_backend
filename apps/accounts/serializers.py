"""
accounts/serializers.py

All serializers for the accounts app.
Every field is explicitly declared — no Meta.fields = "__all__" anywhere.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.utils import timezone
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from shared.utils.media import resolve_media_url

from .models import OrganizerProfile, AttendeeProfile, UserRole

User = get_user_model()


# ---------------------------------------------------------------------------
# JWT — Custom token payload
# ---------------------------------------------------------------------------

class KaribuTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Extends the default JWT payload to include role, full_name, and avatar.
    The frontend reads these from the decoded token — no extra /me call needed
    just to determine which dashboard to render.
    """

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)

        # Custom claims embedded in the token
        token["role"] = user.role
        token["full_name"] = user.full_name
        token["email"] = user.email
        token["is_approved"] = user.is_approved
        token["avatar"] = resolve_media_url(user.avatar)

        return token

    def validate(self, attrs):
        data = super().validate(attrs)

        # Attach user summary to the response body as well (not just the token)
        data["user"] = {
            "id": str(self.user.id),
            "email": self.user.email,
            "full_name": self.user.full_name,
            "role": self.user.role,
            "is_approved": self.user.is_approved,
            "avatar": resolve_media_url(self.user.avatar),
        }

        return data


# ---------------------------------------------------------------------------
# Registration serializers
# ---------------------------------------------------------------------------

class AttendeeRegisterSerializer(serializers.ModelSerializer):
    """Public registration — always creates an ATTENDEE."""

    # Declared explicitly (instead of letting ModelSerializer auto-generate
    # this field) so DRF does NOT attach its automatic UniqueValidator,
    # which would otherwise fire before — and pre-empt — validate_email()
    # below, making our custom "An account with this email already exists."
    # message unreachable.
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = [
            "email", "first_name", "last_name",
            "phone_number", "password", "password_confirm",
        ]

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return value.lower()

    def validate(self, attrs):
        if attrs["password"] != attrs.pop("password_confirm"):
            raise serializers.ValidationError({"password_confirm": "Passwords do not match."})
        return attrs

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class OrganizerRegisterSerializer(serializers.ModelSerializer):
    """
    Organizer self-registration.
    Creates a User with role=ORGANIZER and is_approved=False.
    Also creates the linked OrganizerProfile in one transaction.
    """

    # See AttendeeRegisterSerializer above for why this is declared explicitly.
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True)
    organization_name = serializers.CharField(max_length=200)
    bio = serializers.CharField(required=False, allow_blank=True)
    website = serializers.URLField(required=False, allow_blank=True)

    class Meta:
        model = User
        fields = [
            "email", "first_name", "last_name", "phone_number",
            "password", "password_confirm",
            "organization_name", "bio", "website",
        ]

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return value.lower()

    def validate(self, attrs):
        if attrs["password"] != attrs.pop("password_confirm"):
            raise serializers.ValidationError({"password_confirm": "Passwords do not match."})
        return attrs

    def create(self, validated_data):
        org_fields = {
            "organization_name": validated_data.pop("organization_name"),
            "bio": validated_data.pop("bio", ""),
            "website": validated_data.pop("website", ""),
        }
        user = User.objects.create_organizer(**validated_data)
        OrganizerProfile.objects.create(user=user, **org_fields)
        return user


# ---------------------------------------------------------------------------
# Profile serializers
# ---------------------------------------------------------------------------

class UserProfileSerializer(serializers.ModelSerializer):
    """
    Read/update the authenticated user's own profile.
    Password is excluded — handled by a dedicated endpoint.
    Role and is_approved are read-only — only admins can change those.
    """

    full_name = serializers.CharField(source="get_full_name", read_only=True)
    avatar_url = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id", "email", "first_name", "last_name",
            "full_name", "phone_number", "role",
            "is_approved", "avatar", "avatar_url",
            "date_joined", "updated_at",
        ]
        read_only_fields = ["id", "email", "role", "is_approved", "date_joined", "updated_at"]
        extra_kwargs = {"avatar": {"write_only": True}}

    def get_avatar_url(self, obj):
        return resolve_media_url(obj.avatar)


class AvatarUploadSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["avatar"]

    def validate_avatar(self, value):
        max_size_mb = 5
        if value.size > max_size_mb * 1024 * 1024:
            raise serializers.ValidationError(f"Avatar must be under {max_size_mb}MB.")
        allowed_types = ["image/jpeg", "image/png", "image/webp"]
        if value.content_type not in allowed_types:
            raise serializers.ValidationError("Only JPEG, PNG, and WebP images are allowed.")
        return value


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, validators=[validate_password])
    new_password_confirm = serializers.CharField(write_only=True)

    def validate_current_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Current password is incorrect.")
        return value

    def validate(self, attrs):
        if attrs["new_password"] != attrs["new_password_confirm"]:
            raise serializers.ValidationError(
                {"new_password_confirm": "New passwords do not match."}
            )
        return attrs

    def save(self):
        user = self.context["request"].user
        user.set_password(self.validated_data["new_password"])
        user.save(update_fields=["password", "updated_at"])
        return user


# ---------------------------------------------------------------------------
# Password reset serializers
# ---------------------------------------------------------------------------

class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        # Always return success even if email doesn't exist (prevents user enumeration)
        return value.lower()


class PasswordResetConfirmSerializer(serializers.Serializer):
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True, validators=[validate_password])
    new_password_confirm = serializers.CharField(write_only=True)

    def validate(self, attrs):
        if attrs["new_password"] != attrs["new_password_confirm"]:
            raise serializers.ValidationError(
                {"new_password_confirm": "Passwords do not match."}
            )
        return attrs


# ---------------------------------------------------------------------------
# Admin-facing serializers
# ---------------------------------------------------------------------------

class UserAdminSerializer(serializers.ModelSerializer):
    """
    Full user detail for Super Admin views.
    Exposes fields that regular users cannot see or modify.
    """

    full_name = serializers.CharField(read_only=True)
    avatar_url = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id", "email", "first_name", "last_name", "full_name",
            "phone_number", "role", "is_approved", "is_active",
            "avatar_url", "date_joined", "updated_at",
        ]
        read_only_fields = ["id", "date_joined", "updated_at"]

    def get_avatar_url(self, obj):
        return resolve_media_url(obj.avatar)


class UserListSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer for list views — minimizes payload size.
    """

    full_name = serializers.CharField(read_only=True)

    class Meta:
        model = User
        fields = ["id", "email", "full_name", "role", "is_approved", "is_active", "date_joined"]


class OrganizerProfileSerializer(serializers.ModelSerializer):
    user = UserListSerializer(read_only=True)

    class Meta:
        model = OrganizerProfile
        fields = [
            "id", "user", "organization_name", "bio", "website",
            "banner_image", "approved_by", "approved_at",
            "rejection_reason", "created_at",
        ]
        read_only_fields = ["id", "user", "approved_by", "approved_at", "created_at"]


class OrganizerOwnProfileSerializer(serializers.ModelSerializer):
    """
    Read/update the authenticated organizer's OWN organizer profile
    (organization name, bio, website, banner image).
    Approval fields are read-only — only admins change those (see
    OrganizerApprovalActionView).
    """
    is_approved = serializers.BooleanField(source="user.is_approved", read_only=True)

    class Meta:
        model = OrganizerProfile
        fields = [
            "id", "organization_name", "bio", "website",
            "banner_image", "is_approved", "rejection_reason", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "is_approved", "rejection_reason", "created_at", "updated_at"]


class OrganizerApprovalSerializer(serializers.Serializer):
    """Used by Super Admin to approve or reject an organizer."""

    action = serializers.ChoiceField(choices=["approve", "reject"])
    rejection_reason = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        if attrs["action"] == "reject" and not attrs.get("rejection_reason"):
            raise serializers.ValidationError(
                {"rejection_reason": "A rejection reason is required when rejecting an organizer."}
            )
        return attrs
