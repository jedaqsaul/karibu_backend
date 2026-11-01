"""
accounts/models.py

Custom User model for Karibu. Replaces Django's default User entirely.
UUID primary key — never exposes sequential IDs in the API.
Role is a string enum stored directly on the user — no separate role table needed.
"""

import uuid
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone


class UserRole(models.TextChoices):
    SUPER_ADMIN = "super_admin", "Super Admin"
    ORGANIZER = "organizer", "Organizer"
    ATTENDEE = "attendee", "Attendee"


class UserManager(BaseUserManager):
    """
    Custom manager. Email is the unique identifier — no username field.
    """

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("An email address is required.")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("role", UserRole.ATTENDEE)
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_organizer(self, email, password=None, **extra_fields):
        extra_fields.setdefault("role", UserRole.ORGANIZER)
        extra_fields.setdefault("is_approved", False)
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields["role"] = UserRole.SUPER_ADMIN
        extra_fields["is_staff"] = True
        extra_fields["is_superuser"] = True
        extra_fields["is_approved"] = True
        return self._create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """
    Single user model for all three roles.
    Role-specific fields live in separate profile models via OneToOneField.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    email = models.EmailField(unique=True, db_index=True)
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    phone_number = models.CharField(max_length=20, blank=True, null=True)

    role = models.CharField(
        max_length=20,
        choices=UserRole.choices,
        default=UserRole.ATTENDEE,
        db_index=True,
    )

    is_approved = models.BooleanField(
        default=False,
        help_text="Organizers must be approved by a Super Admin before creating events.",
    )

    avatar = models.ImageField(upload_to="avatars/", blank=True, null=True)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    date_joined = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    class Meta:
        db_table = "users"
        ordering = ["-date_joined"]
        verbose_name = "User"
        verbose_name_plural = "Users"

    def __str__(self):
        return f"{self.full_name} <{self.email}>"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def is_super_admin(self):
        return self.role == UserRole.SUPER_ADMIN

    @property
    def is_organizer(self):
        return self.role == UserRole.ORGANIZER

    @property
    def is_attendee(self):
        return self.role == UserRole.ATTENDEE

    @property
    def is_active_organizer(self):
        return self.role == UserRole.ORGANIZER and self.is_approved


class OrganizerProfile(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="organizer_profile")

    organization_name = models.CharField(max_length=200)
    bio = models.TextField(blank=True)
    website = models.URLField(blank=True)
    banner_image = models.ImageField(upload_to="organizer_banners/", blank=True, null=True)

    approved_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="approved_organizers",
        limit_choices_to={"role": UserRole.SUPER_ADMIN},
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "organizer_profiles"

    def __str__(self):
        return f"OrganizerProfile({self.organization_name})"


class AttendeeProfile(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="attendee_profile")

    saved_events = models.ManyToManyField(
        "events.Event", blank=True, related_name="saved_by",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "attendee_profiles"

    def __str__(self):
        return f"AttendeeProfile({self.user.email})"
