"""
events/models.py

Full event model for Karibu.
Covers the complete lifecycle: draft → pending_approval → published → cancelled/completed.
Category and EventImage are separate models for clean normalization.
"""

import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.exceptions import ValidationError


class EventStatus(models.TextChoices):
    DRAFT            = "draft",            "Draft"
    PENDING_APPROVAL = "pending_approval", "Pending Approval"
    PUBLISHED        = "published",        "Published"
    CANCELLED        = "cancelled",        "Cancelled"
    COMPLETED        = "completed",        "Completed"


class Category(models.Model):
    """
    Event categories managed by Super Admin.
    e.g. Music, Tech, Sports, Comedy, Culture, Food & Drink
    """
    id   = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True, db_index=True)
    icon = models.CharField(max_length=100, blank=True, help_text="Icon class or emoji")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table    = "event_categories"
        ordering    = ["name"]
        verbose_name_plural = "Categories"

    def __str__(self):
        return self.name


class Event(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Ownership
    organizer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="events",
        limit_choices_to={"role": "organizer"},
    )

    # Core fields
    title       = models.CharField(max_length=300)
    slug        = models.SlugField(max_length=320, unique=True, db_index=True)
    description = models.TextField()
    category    = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="events",
    )
    tags = models.CharField(
        max_length=500,
        blank=True,
        help_text="Comma-separated tags e.g. 'live,outdoor,afrobeats'",
    )

    # Location
    venue        = models.CharField(max_length=300)
    address      = models.CharField(max_length=500)
    city         = models.CharField(max_length=100, db_index=True)
    country      = models.CharField(max_length=100, default="Kenya")
    latitude     = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude    = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    # Scheduling
    start_datetime = models.DateTimeField(db_index=True)
    end_datetime   = models.DateTimeField()

    # Ticketing
    is_free        = models.BooleanField(default=False)
    ticket_price   = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    total_capacity = models.PositiveIntegerField()
    tickets_sold   = models.PositiveIntegerField(default=0)

    # Banner image — stored in Cloudinary in production
    banner_image = models.ImageField(
        upload_to="event_banners/",
        blank=True,
        null=True,
    )

    # Status & approval
    status = models.CharField(
        max_length=20,
        choices=EventStatus.choices,
        default=EventStatus.DRAFT,
        db_index=True,
    )
    rejection_reason = models.TextField(blank=True)

    # Approval tracking
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_by  = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_events",
        limit_choices_to={"role": "super_admin"},
    )
    approved_at = models.DateTimeField(null=True, blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "events"
        ordering = ["-start_datetime"]
        indexes  = [
            models.Index(fields=["status", "start_datetime"]),
            models.Index(fields=["city", "status"]),
            models.Index(fields=["organizer", "status"]),
        ]

    def __str__(self):
        return f"{self.title} ({self.get_status_display()})"

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def clean(self):
        if self.end_datetime and self.start_datetime:
            if self.end_datetime <= self.start_datetime:
                raise ValidationError({"end_datetime": "End time must be after start time."})
        if self.is_free:
            self.ticket_price = 0.00
        if self.tickets_sold > self.total_capacity:
            raise ValidationError("Tickets sold cannot exceed total capacity.")

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def tickets_remaining(self):
        return max(0, self.total_capacity - self.tickets_sold)

    @property
    def is_sold_out(self):
        return self.tickets_remaining == 0

    @property
    def is_upcoming(self):
        return self.start_datetime > timezone.now()

    @property
    def is_past(self):
        return self.end_datetime < timezone.now()


class EventImage(models.Model):
    """
    Additional gallery images for an event (beyond the banner).
    Stored in Cloudinary. Max 10 per event enforced in the serializer.
    """
    id        = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event     = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="gallery_images")
    image     = models.ImageField(upload_to="event_gallery/")
    caption   = models.CharField(max_length=200, blank=True)
    order     = models.PositiveSmallIntegerField(default=0)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "event_images"
        ordering = ["order", "uploaded_at"]

    def __str__(self):
        return f"Image for {self.event.title}"
