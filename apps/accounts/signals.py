"""
accounts/signals.py

Post-save signals for the accounts app.
Only AttendeeProfile is auto-created via signal.
OrganizerProfile creation is owned by OrganizerRegisterSerializer
to allow org-specific fields (name, bio, website) to be set atomically.
"""

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model

from .models import UserRole, AttendeeProfile

User = get_user_model()


@receiver(post_save, sender=User)
def create_attendee_profile(sender, instance, created, **kwargs):
    """
    Auto-create an AttendeeProfile for every new attendee user.
    Organizer profiles are created explicitly in OrganizerRegisterSerializer.
    Super Admins do not get a profile.
    """
    if created and instance.role == UserRole.ATTENDEE:
        AttendeeProfile.objects.get_or_create(user=instance)
