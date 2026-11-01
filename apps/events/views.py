"""
events/views.py

All event-related views for Karibu.
Separated into three access tiers: public, organizer, and super admin.
Every view declares permission_classes explicitly.
"""

from django.utils import timezone
from django.shortcuts import get_object_or_404
from rest_framework import status, generics
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsSuperAdmin, IsOrganizer, IsOrganizerOrAdmin, IsAttendee
from apps.accounts.models import AttendeeProfile
from apps.logs.utils import log_action

from .filters import EventFilter, OrganizerEventFilter
from .models import Event, EventStatus, Category, EventImage
from .serializers import (
    CategorySerializer,
    EventListSerializer,
    EventDetailSerializer,
    EventWriteSerializer,
    EventSubmitSerializer,
    EventApprovalSerializer,
    EventAdminSerializer,
    EventImageSerializer,
)


# ---------------------------------------------------------------------------
# Public endpoints — no auth required
# ---------------------------------------------------------------------------

class PublicEventListView(generics.ListAPIView):
    """
    GET /api/events/
    Publicly browsable, paginated event list.
    Only returns PUBLISHED events.
    Supports full filtering via EventFilter + ordering.
    """
    permission_classes  = [AllowAny]
    serializer_class    = EventListSerializer
    filterset_class     = EventFilter
    ordering_fields     = ["start_datetime", "ticket_price", "created_at"]
    ordering            = ["start_datetime"]

    def get_queryset(self):
        return (
            Event.objects
            .filter(status=EventStatus.PUBLISHED)
            .select_related("organizer", "category")
            .order_by("start_datetime")
        )


class PublicEventDetailView(APIView):
    """
    GET /api/events/<slug>/
    Single published event detail. No auth required.
    """
    permission_classes = [AllowAny]

    def get(self, request, slug):
        event = get_object_or_404(
            Event.objects.select_related("organizer", "category")
                         .prefetch_related("gallery_images"),
            slug=slug,
            status=EventStatus.PUBLISHED,
        )
        return Response(EventDetailSerializer(event).data)


class PublicCategoryListView(generics.ListAPIView):
    """GET /api/events/categories/ — All active categories."""
    permission_classes = [AllowAny]
    serializer_class   = CategorySerializer
    queryset           = Category.objects.all()
    pagination_class   = None  # Return all categories without pagination


class SavedEventsListView(generics.ListAPIView):
    """
    GET /api/events/saved/
    The authenticated attendee's saved (bookmarked) events.
    """
    permission_classes = [IsAttendee]
    serializer_class    = EventListSerializer

    def get_queryset(self):
        profile, _ = AttendeeProfile.objects.get_or_create(user=self.request.user)
        return profile.saved_events.select_related("organizer", "category").order_by("-start_datetime")


class ToggleSaveEventView(APIView):
    """
    POST /api/events/<id>/save/
    Toggles whether the authenticated attendee has saved this event.
    Returns { "saved": true|false }.
    """
    permission_classes = [IsAttendee]

    def post(self, request, id):
        event = get_object_or_404(Event, id=id, status=EventStatus.PUBLISHED)
        profile, _ = AttendeeProfile.objects.get_or_create(user=request.user)

        if profile.saved_events.filter(id=event.id).exists():
            profile.saved_events.remove(event)
            return Response({"saved": False})

        profile.saved_events.add(event)
        return Response({"saved": True})


# ---------------------------------------------------------------------------
# Organizer endpoints
# ---------------------------------------------------------------------------

class OrganizerEventListView(generics.ListAPIView):
    """
    GET /api/organizer/events/
    The authenticated organizer's own events. All statuses visible to them.
    """
    permission_classes = [IsOrganizer]
    serializer_class   = EventListSerializer
    filterset_class    = OrganizerEventFilter
    ordering_fields    = ["start_datetime", "created_at", "status"]
    ordering           = ["-created_at"]

    def get_queryset(self):
        return (
            Event.objects
            .filter(organizer=self.request.user)
            .select_related("category")
            .order_by("-created_at")
        )


class OrganizerEventCreateView(APIView):
    """
    POST /api/organizer/events/
    Create a new event. Starts in DRAFT status.
    Accepts multipart/form-data for banner image upload.
    """
    permission_classes = [IsOrganizer]
    parser_classes     = [MultiPartParser, FormParser, JSONParser]

    def post(self, request):
        serializer = EventWriteSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        event = serializer.save()
        log_action(request.user, "EVENT_CREATED", f"Organizer created event: {event.title}")
        return Response(
            EventDetailSerializer(event).data,
            status=status.HTTP_201_CREATED,
        )


class OrganizerEventDetailView(APIView):
    """
    GET    /api/organizer/events/<id>/  — View own event detail
    PATCH  /api/organizer/events/<id>/  — Update (only if DRAFT or returned after rejection)
    DELETE /api/organizer/events/<id>/  — Delete (only if DRAFT)
    """
    permission_classes = [IsOrganizer]
    parser_classes     = [MultiPartParser, FormParser, JSONParser]

    def _get_own_event(self, request, id):
        return get_object_or_404(Event, id=id, organizer=request.user)

    def get(self, request, id):
        event = self._get_own_event(request, id)
        return Response(
            EventDetailSerializer(
                event,
                context={"request": request}
            ).data
        )

    def patch(self, request, id):
        event = self._get_own_event(request, id)
        if event.status not in (EventStatus.DRAFT,):
            return Response(
                {"error": f"Events with status '{event.status}' cannot be edited. "
                          f"Only DRAFT events can be updated."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = EventWriteSerializer(
            event,
            data=request.data,
            partial=True,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        event = serializer.save()
        log_action(request.user, "EVENT_UPDATED", f"Organizer updated event: {event.title}")
        return Response(EventDetailSerializer(event).data)

    def delete(self, request, id):
        event = self._get_own_event(request, id)
        if event.status != EventStatus.DRAFT:
            return Response(
                {"error": "Only DRAFT events can be deleted."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        title = event.title
        event.delete()
        log_action(request.user, "EVENT_DELETED", f"Organizer deleted event: {title}")
        return Response(status=status.HTTP_204_NO_CONTENT)


class OrganizerEventSubmitView(APIView):
    """
    POST /api/organizer/events/<id>/submit/
    Submit a DRAFT event for admin approval.
    """
    permission_classes = [IsOrganizer]

    def post(self, request, id):
        event = get_object_or_404(Event, id=id, organizer=request.user)
        serializer = EventSubmitSerializer(
            data={},
            context={"event": event},
        )
        serializer.is_valid(raise_exception=True)

        event.status       = EventStatus.PENDING_APPROVAL
        event.submitted_at = timezone.now()
        event.save(update_fields=["status", "submitted_at"])

        log_action(
            request.user, "EVENT_SUBMITTED",
            f"Organizer submitted event for approval: {event.title}"
        )
        return Response({
            "message": "Event submitted for approval.",
            "status": event.status,
        })


class OrganizerEventCancelView(APIView):
    """
    POST /api/organizer/events/<id>/cancel/
    Cancel a published event. Cannot cancel completed events.
    """
    permission_classes = [IsOrganizer]

    def post(self, request, id):
        event = get_object_or_404(Event, id=id, organizer=request.user)
        if event.status not in (EventStatus.PUBLISHED, EventStatus.PENDING_APPROVAL):
            return Response(
                {"error": f"Cannot cancel an event with status '{event.status}'."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        event.status = EventStatus.CANCELLED
        event.save(update_fields=["status"])
        log_action(request.user, "EVENT_CANCELLED", f"Organizer cancelled event: {event.title}")
        return Response({"message": "Event cancelled.", "status": event.status})


# ---------------------------------------------------------------------------
# Gallery image endpoints
# ---------------------------------------------------------------------------

class EventImageUploadView(APIView):
    """
    POST   /api/organizer/events/<id>/images/  — Upload a gallery image
    DELETE /api/organizer/events/<id>/images/<image_id>/  — Remove gallery image
    """
    permission_classes = [IsOrganizer]
    parser_classes     = [MultiPartParser, FormParser]

    def post(self, request, id):
        event = get_object_or_404(Event, id=id, organizer=request.user)
        serializer = EventImageSerializer(
            data=request.data,
            context={"event": event},
        )
        serializer.is_valid(raise_exception=True)
        image = serializer.save(event=event)
        log_action(request.user, "EVENT_IMAGE_UPLOADED", f"Gallery image added to: {event.title}")
        return Response(
            EventImageSerializer(image).data,
            status=status.HTTP_201_CREATED,
        )

    def delete(self, request, id, image_id):
        event = get_object_or_404(Event, id=id, organizer=request.user)
        image = get_object_or_404(EventImage, id=image_id, event=event)
        image.delete()
        log_action(request.user, "EVENT_IMAGE_DELETED", f"Gallery image removed from: {event.title}")
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Super Admin — event management
# ---------------------------------------------------------------------------

class AdminEventListView(generics.ListAPIView):
    """
    GET /api/admin/events/
    Full event list across all organizers. All statuses. Fully filterable.
    """
    permission_classes = [IsSuperAdmin]
    serializer_class   = EventListSerializer
    filterset_class    = EventFilter
    ordering_fields    = ["start_datetime", "created_at", "status", "tickets_sold"]
    ordering           = ["-created_at"]

    def get_queryset(self):
        return (
            Event.objects
            .select_related("organizer", "category")
            .order_by("-created_at")
        )


class AdminEventDetailView(APIView):
    """
    GET   /api/admin/events/<id>/  — Full event detail with all fields
    PATCH /api/admin/events/<id>/  — Admin can override any field
    """
    permission_classes = [IsSuperAdmin]
    parser_classes     = [MultiPartParser, FormParser, JSONParser]

    def get(self, request, id):
        event = get_object_or_404(
            Event.objects.select_related("organizer", "category", "approved_by")
                         .prefetch_related("gallery_images"),
            id=id,
        )
        return Response(EventAdminSerializer(event).data)

    def patch(self, request, id):
        event = get_object_or_404(Event, id=id)
        serializer = EventAdminSerializer(event, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        event = serializer.save()
        log_action(request.user, "ADMIN_EVENT_UPDATED", f"Admin updated event: {event.title}")
        return Response(EventAdminSerializer(event).data)


class AdminEventApprovalView(APIView):
    """
    POST /api/admin/events/<id>/approval/
    Body: { "action": "approve" | "reject", "rejection_reason": "..." }
    """
    permission_classes = [IsSuperAdmin]

    def post(self, request, id):
        event = get_object_or_404(
            Event.objects.select_related("organizer"),
            id=id,
        )

        if event.status != EventStatus.PENDING_APPROVAL:
            return Response(
                {"error": f"Only events with status 'pending_approval' can be actioned. "
                          f"This event is '{event.status}'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = EventApprovalSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        action = serializer.validated_data["action"]

        if action == "approve":
            event.status      = EventStatus.PUBLISHED
            event.approved_by = request.user
            event.approved_at = timezone.now()
            event.rejection_reason = ""
            event.save(update_fields=["status", "approved_by", "approved_at", "rejection_reason"])

            from apps.notifications.tasks import send_event_approved_email
            send_event_approved_email(event.organizer, event)
            log_action(request.user, "EVENT_APPROVED", f"Approved event: {event.title}")
            return Response({"message": f"Event '{event.title}' has been approved and published."})

        else:
            reason = serializer.validated_data["rejection_reason"]
            event.status = EventStatus.DRAFT
            event.rejection_reason = reason
            event.save(update_fields=["status", "rejection_reason"])

            from apps.notifications.tasks import send_event_rejected_email
            send_event_rejected_email(event.organizer, event, reason)
            log_action(
                request.user, "EVENT_REJECTED",
                f"Rejected event: {event.title}. Reason: {reason}"
            )
            return Response({"message": f"Event '{event.title}' has been rejected."})


class AdminPendingEventsView(generics.ListAPIView):
    """
    GET /api/admin/events/pending/
    Events awaiting approval — sorted by submission date (oldest first).
    """
    permission_classes = [IsSuperAdmin]
    serializer_class   = EventListSerializer
    pagination_class   = None

    def get_queryset(self):
        return (
            Event.objects
            .filter(status=EventStatus.PENDING_APPROVAL)
            .select_related("organizer", "category")
            .order_by("submitted_at")
        )


# ---------------------------------------------------------------------------
# Category management — admin only
# ---------------------------------------------------------------------------

class AdminCategoryListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/admin/categories/ — List all categories
    POST /api/admin/categories/ — Create a new category
    """
    permission_classes = [IsSuperAdmin]
    serializer_class   = CategorySerializer
    queryset           = Category.objects.all()
    pagination_class   = None

    def perform_create(self, serializer):
        category = serializer.save()
        log_action(self.request.user, "CATEGORY_CREATED", f"Created category: {category.name}")


class AdminCategoryDetailView(generics.RetrieveUpdateDestroyAPIView):
    """GET / PATCH / DELETE /api/admin/categories/<id>/"""
    permission_classes = [IsSuperAdmin]
    serializer_class   = CategorySerializer
    queryset           = Category.objects.all()
    lookup_field       = "id"

    def perform_update(self, serializer):
        cat = serializer.save()
        log_action(self.request.user, "CATEGORY_UPDATED", f"Updated category: {cat.name}")

    def perform_destroy(self, instance):
        name = instance.name
        instance.delete()
        log_action(self.request.user, "CATEGORY_DELETED", f"Deleted category: {name}")
