"""
events/serializers.py

All serializers for the events app.
No Meta.fields = "__all__". Every field is explicitly declared.
Read vs write serializers are separated to avoid over-posting vulnerabilities.
"""

from django.utils.text import slugify
from django.utils import timezone
from rest_framework import serializers

from apps.accounts.serializers import UserListSerializer
from shared.utils.media import resolve_media_url
from .models import Event, EventStatus, Category, EventImage


# ---------------------------------------------------------------------------
# Category
# ---------------------------------------------------------------------------

class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model  = Category
        fields = ["id", "name", "slug", "icon"]
        read_only_fields = ["id", "slug"]

    def validate_name(self, value):
        slug = slugify(value)
        qs = Category.objects.filter(slug=slug)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("A category with this name already exists.")
        return value

    def create(self, validated_data):
        validated_data["slug"] = slugify(validated_data["name"])
        return super().create(validated_data)

    def update(self, instance, validated_data):
        if "name" in validated_data:
            validated_data["slug"] = slugify(validated_data["name"])
        return super().update(instance, validated_data)


# ---------------------------------------------------------------------------
# Event Images
# ---------------------------------------------------------------------------

class EventImageSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model  = EventImage
        fields = ["id", "image", "image_url", "caption", "order", "uploaded_at"]
        read_only_fields = ["id", "image_url", "uploaded_at"]
        extra_kwargs = {"image": {"write_only": True}}

    def get_image_url(self, obj):
        return resolve_media_url(obj.image)

    def validate_image(self, value):
        max_size_mb = 10
        if value.size > max_size_mb * 1024 * 1024:
            raise serializers.ValidationError(f"Image must be under {max_size_mb}MB.")
        allowed = ["image/jpeg", "image/png", "image/webp"]
        if value.content_type not in allowed:
            raise serializers.ValidationError("Only JPEG, PNG, and WebP images are allowed.")
        return value

    def validate(self, attrs):
        # Enforce 10-image gallery limit per event
        event = self.context.get("event")
        if event and EventImage.objects.filter(event=event).count() >= 10:
            raise serializers.ValidationError(
                "An event may have a maximum of 10 gallery images."
            )
        return attrs


# ---------------------------------------------------------------------------
# Event — list view (lightweight)
# ---------------------------------------------------------------------------

class EventListSerializer(serializers.ModelSerializer):
    """
    Minimal payload for list endpoints.
    Avoids sending description, full gallery, etc. in paginated lists.
    """
    category     = CategorySerializer(read_only=True)
    banner_url   = serializers.SerializerMethodField()
    organizer_name = serializers.CharField(source="organizer.full_name", read_only=True)
    tickets_remaining = serializers.IntegerField(read_only=True)
    is_sold_out  = serializers.BooleanField(read_only=True)

    class Meta:
        model  = Event
        fields = [
            "id", "title", "slug", "category", "organizer_name",
            "venue", "city", "country",
            "start_datetime", "end_datetime",
            "is_free", "ticket_price",
            "total_capacity", "tickets_remaining", "is_sold_out",
            "banner_url", "status",
        ]

    def get_banner_url(self, obj):
        return resolve_media_url(obj.banner_image)


# ---------------------------------------------------------------------------
# Event — detail view (full)
# ---------------------------------------------------------------------------

class EventDetailSerializer(serializers.ModelSerializer):
    category       = CategorySerializer(read_only=True)
    organizer      = UserListSerializer(read_only=True)
    gallery_images = EventImageSerializer(many=True, read_only=True)
    banner_url     = serializers.SerializerMethodField()
    tickets_remaining = serializers.IntegerField(read_only=True)
    is_sold_out    = serializers.BooleanField(read_only=True)
    is_upcoming    = serializers.BooleanField(read_only=True)

    class Meta:
        model  = Event
        fields = [
            "id", "title", "slug", "description", "tags",
            "category", "organizer",
            "venue", "address", "city", "country", "latitude", "longitude",
            "start_datetime", "end_datetime",
            "is_free", "ticket_price",
            "total_capacity", "tickets_sold", "tickets_remaining", "is_sold_out",
            "banner_url", "gallery_images",
            "status", "rejection_reason",
            "created_at", "updated_at",
            "is_upcoming",
        ]

    def get_banner_url(self, obj):
        return resolve_media_url(obj.banner_image)


# ---------------------------------------------------------------------------
# Event — write serializer (create / update)
# ---------------------------------------------------------------------------

class EventWriteSerializer(serializers.ModelSerializer):
    """
    Used for both create and update.
    Organizer is injected from request.user — never from request body.
    Slug is auto-generated and enforced unique.
    """
    category_id = serializers.UUIDField(write_only=True, required=False, allow_null=True)

    class Meta:
        model  = Event
        fields = [
            "title", "description", "tags",
            "category_id",
            "venue", "address", "city", "country", "latitude", "longitude",
            "start_datetime", "end_datetime",
            "is_free", "ticket_price",
            "total_capacity",
            "banner_image",
        ]

    def validate_category_id(self, value):
        if value is None:
            return None
        try:
            return Category.objects.get(id=value)
        except Category.DoesNotExist:
            raise serializers.ValidationError("Category not found.")

    def validate_start_datetime(self, value):
        if value <= timezone.now():
            raise serializers.ValidationError("Start time must be in the future.")
        return value

    def validate_banner_image(self, value):
        if value:
            max_size_mb = 10
            if value.size > max_size_mb * 1024 * 1024:
                raise serializers.ValidationError(f"Banner must be under {max_size_mb}MB.")
            allowed = ["image/jpeg", "image/png", "image/webp"]
            if value.content_type not in allowed:
                raise serializers.ValidationError("Only JPEG, PNG, and WebP images are allowed.")
        return value

    def validate(self, attrs):
        start = attrs.get("start_datetime", getattr(self.instance, "start_datetime", None))
        end   = attrs.get("end_datetime", getattr(self.instance, "end_datetime", None))
        if start and end and end <= start:
            raise serializers.ValidationError({"end_datetime": "End time must be after start time."})

        is_free = attrs.get("is_free", getattr(self.instance, "is_free", False))
        if is_free:
            attrs["ticket_price"] = 0.00
        else:
            price = attrs.get("ticket_price", getattr(self.instance, "ticket_price", 0))
            if price <= 0:
                raise serializers.ValidationError(
                    {"ticket_price": "Paid events must have a ticket price greater than 0."}
                )

        return attrs

    def _generate_unique_slug(self, title, instance=None):
        base_slug = slugify(title)[:300]
        slug = base_slug
        n = 1
        qs = Event.objects.filter(slug=slug)
        if instance:
            qs = qs.exclude(pk=instance.pk)
        while qs.exists():
            slug = f"{base_slug}-{n}"
            n += 1
            qs = Event.objects.filter(slug=slug)
            if instance:
                qs = qs.exclude(pk=instance.pk)
        return slug

    def create(self, validated_data):
        category = validated_data.pop("category_id", None)
        organizer = self.context["request"].user
        slug = self._generate_unique_slug(validated_data["title"])

        event = Event.objects.create(
            organizer=organizer,
            category=category,
            slug=slug,
            **validated_data,
        )
        return event

    def update(self, instance, validated_data):
        category = validated_data.pop("category_id", ...)  # ... sentinel = not provided
        if category is not ...:
            instance.category = category

        # Regenerate slug only if title changed
        if "title" in validated_data and validated_data["title"] != instance.title:
            instance.slug = self._generate_unique_slug(validated_data["title"], instance)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        instance.save()
        return instance


# ---------------------------------------------------------------------------
# Event — submission for approval
# ---------------------------------------------------------------------------

class EventSubmitSerializer(serializers.Serializer):
    """Body is empty — the action is the intent. Validates the event is ready."""

    def validate(self, attrs):
        event = self.context["event"]
        errors = {}
        if not event.title:
            errors["title"] = "Title is required before submitting."
        if not event.description:
            errors["description"] = "Description is required before submitting."
        if not event.venue:
            errors["venue"] = "Venue is required before submitting."
        if not event.start_datetime:
            errors["start_datetime"] = "Start time is required before submitting."
        if event.status not in (EventStatus.DRAFT, EventStatus.PENDING_APPROVAL):
            errors["status"] = f"Cannot submit an event with status '{event.status}'."
        if errors:
            raise serializers.ValidationError(errors)
        return attrs


# ---------------------------------------------------------------------------
# Event — admin approval
# ---------------------------------------------------------------------------

class EventApprovalSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["approve", "reject"])
    rejection_reason = serializers.CharField(required=False, allow_blank=True)

    def validate(self, attrs):
        if attrs["action"] == "reject" and not attrs.get("rejection_reason"):
            raise serializers.ValidationError(
                {"rejection_reason": "A rejection reason is required when rejecting an event."}
            )
        return attrs


# ---------------------------------------------------------------------------
# Event — admin update (can change status directly)
# ---------------------------------------------------------------------------

class EventAdminSerializer(serializers.ModelSerializer):
    """Admin-only serializer. Can set any status and override any field."""

    class Meta:
        model  = Event
        fields = [
            "id", "title", "slug", "description", "tags",
            "category", "organizer",
            "venue", "address", "city", "country", "latitude", "longitude",
            "start_datetime", "end_datetime",
            "is_free", "ticket_price", "total_capacity", "tickets_sold",
            "banner_image", "status", "rejection_reason",
            "submitted_at", "approved_by", "approved_at",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "slug", "organizer", "tickets_sold", "created_at", "updated_at"]
