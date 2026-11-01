"""
events/tests/test_events.py

Phase 2 test suite. Covers:
- Category CRUD (admin only)
- Public event listing and filtering
- Organizer create / update / delete / submit / cancel flow
- Admin approval / rejection flow
- Permission enforcement across all three roles
"""

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient
from datetime import timedelta

from django.contrib.auth import get_user_model
from apps.accounts.models import OrganizerProfile
from apps.events.models import Event, EventStatus, Category, EventImage

User = get_user_model()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_future_dt(days=10):
    return timezone.now() + timedelta(days=days)

def make_future_end(days=10, hours=3):
    return timezone.now() + timedelta(days=days, hours=hours)


class EventTestBase(TestCase):
    def setUp(self):
        self.client = APIClient()

        # Super Admin
        self.admin = User.objects.create_superuser(
            email="admin@karibu.com", password="AdminPass123!",
            first_name="Super", last_name="Admin",
        )

        # Approved organizer
        self.organizer_user = User.objects.create_user(
            email="organizer@karibu.com", password="OrgPass123!",
            first_name="Org", last_name="One",
            role="organizer", is_approved=True,
        )
        OrganizerProfile.objects.create(
            user=self.organizer_user,
            organization_name="Test Events Ltd",
        )

        # Attendee
        self.attendee = User.objects.create_user(
            email="attendee@karibu.com", password="AttPass123!",
            first_name="Att", last_name="One",
        )

        # Category
        self.category = Category.objects.create(name="Music", slug="music")

        # Reusable event payload
        self.event_payload = {
            "title": "Nairobi Jazz Night",
            "description": "An amazing jazz night in the heart of Nairobi.",
            "venue": "KICC Rooftop",
            "address": "City Square, Nairobi",
            "city": "Nairobi",
            "start_datetime": make_future_dt(10).isoformat(),
            "end_datetime": make_future_end(10).isoformat(),
            "is_free": False,
            "ticket_price": "1500.00",
            "total_capacity": 200,
            "category_id": str(self.category.id),
        }

    def auth(self, user, password):
        resp = self.client.post(
            reverse("login"),
            {"email": user.email, "password": password},
            format="json",
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['access']}")

    def create_published_event(self, title="Live Event"):
        """Helper: create a published event owned by the organizer."""
        return Event.objects.create(
            organizer=self.organizer_user,
            title=title,
            slug=title.lower().replace(" ", "-"),
            description="A published event.",
            venue="Test Venue",
            address="123 Test St",
            city="Nairobi",
            start_datetime=make_future_dt(5),
            end_datetime=make_future_end(5),
            is_free=False,
            ticket_price=500,
            total_capacity=100,
            status=EventStatus.PUBLISHED,
            category=self.category,
        )

    def create_draft_event(self, title="Draft Event"):
        return Event.objects.create(
            organizer=self.organizer_user,
            title=title,
            slug=title.lower().replace(" ", "-"),
            description="A draft event.",
            venue="Test Venue",
            address="123 Test St",
            city="Nairobi",
            start_datetime=make_future_dt(5),
            end_datetime=make_future_end(5),
            is_free=False,
            ticket_price=500,
            total_capacity=100,
            status=EventStatus.DRAFT,
        )


# ---------------------------------------------------------------------------
# Category tests
# ---------------------------------------------------------------------------

class CategoryTests(EventTestBase):

    def test_admin_can_create_category(self):
        self.auth(self.admin, "AdminPass123!")
        resp = self.client.post(
            reverse("admin-category-list"),
            {"name": "Tech", "icon": "💻"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data["slug"], "tech")

    def test_category_slug_auto_generated(self):
        self.auth(self.admin, "AdminPass123!")
        resp = self.client.post(
            reverse("admin-category-list"),
            {"name": "Food & Drink", "icon": "🍹"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data["slug"], "food-drink")

    def test_duplicate_category_name_rejected(self):
        self.auth(self.admin, "AdminPass123!")
        self.client.post(reverse("admin-category-list"), {"name": "Sports"}, format="json")
        resp = self.client.post(reverse("admin-category-list"), {"name": "Sports"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_organizer_cannot_create_category(self):
        self.auth(self.organizer_user, "OrgPass123!")
        resp = self.client.post(
            reverse("admin-category-list"),
            {"name": "Comedy"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_public_can_list_categories(self):
        resp = self.client.get(reverse("public-category-list"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# Public event listing
# ---------------------------------------------------------------------------

class PublicEventListTests(EventTestBase):

    def test_public_list_returns_only_published(self):
        self.create_published_event("Published One")
        self.create_draft_event("Draft Hidden")
        resp = self.client.get(reverse("public-event-list"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        titles = [e["title"] for e in resp.data["results"]]
        self.assertIn("Published One", titles)
        self.assertNotIn("Draft Hidden", titles)

    def test_public_list_no_auth_required(self):
        resp = self.client.get(reverse("public-event-list"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_filter_by_city(self):
        self.create_published_event("Nairobi Event")
        Event.objects.create(
            organizer=self.organizer_user, title="Mombasa Event",
            slug="mombasa-event", description="X", venue="V",
            address="A", city="Mombasa",
            start_datetime=make_future_dt(3), end_datetime=make_future_end(3),
            is_free=True, ticket_price=0, total_capacity=50,
            status=EventStatus.PUBLISHED,
        )
        resp = self.client.get(reverse("public-event-list"), {"city": "Nairobi"})
        titles = [e["title"] for e in resp.data["results"]]
        self.assertIn("Nairobi Event", titles)
        self.assertNotIn("Mombasa Event", titles)

    def test_filter_by_is_free(self):
        self.create_published_event("Paid Event")
        Event.objects.create(
            organizer=self.organizer_user, title="Free Event",
            slug="free-event", description="X", venue="V",
            address="A", city="Nairobi",
            start_datetime=make_future_dt(4), end_datetime=make_future_end(4),
            is_free=True, ticket_price=0, total_capacity=50,
            status=EventStatus.PUBLISHED,
        )
        resp = self.client.get(reverse("public-event-list"), {"is_free": "true"})
        titles = [e["title"] for e in resp.data["results"]]
        self.assertIn("Free Event", titles)
        self.assertNotIn("Paid Event", titles)

    def test_filter_by_category_slug(self):
        self.create_published_event("Music Event")
        resp = self.client.get(reverse("public-event-list"), {"category": "music"})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_search_filter(self):
        self.create_published_event("Jazz Night Out")
        resp = self.client.get(reverse("public-event-list"), {"search": "Jazz"})
        titles = [e["title"] for e in resp.data["results"]]
        self.assertIn("Jazz Night Out", titles)

    def test_price_range_filter(self):
        self.create_published_event("Expensive Event")
        resp = self.client.get(reverse("public-event-list"), {"price_max": "2000"})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_public_event_detail(self):
        event = self.create_published_event("Detail Event")
        resp = self.client.get(reverse("public-event-detail", kwargs={"slug": event.slug}))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["title"], "Detail Event")

    def test_draft_event_not_accessible_publicly(self):
        event = self.create_draft_event("Hidden Draft")
        resp = self.client.get(reverse("public-event-detail", kwargs={"slug": event.slug}))
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_pagination_structure(self):
        resp = self.client.get(reverse("public-event-list"))
        self.assertIn("pagination", resp.data)
        self.assertIn("results", resp.data)


# ---------------------------------------------------------------------------
# Organizer event CRUD
# ---------------------------------------------------------------------------

class OrganizerEventCRUDTests(EventTestBase):

    def test_organizer_can_create_event(self):
        self.auth(self.organizer_user, "OrgPass123!")
        resp = self.client.post(
            reverse("organizer-event-create"),
            self.event_payload,
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data["status"], EventStatus.DRAFT)
        self.assertIn("slug", resp.data)

    def test_event_slug_auto_generated(self):
        self.auth(self.organizer_user, "OrgPass123!")
        resp = self.client.post(
            reverse("organizer-event-create"),
            self.event_payload,
            format="json",
        )
        self.assertTrue(len(resp.data["slug"]) > 0)

    def test_attendee_cannot_create_event(self):
        self.auth(self.attendee, "AttPass123!")
        resp = self.client.post(
            reverse("organizer-event-create"),
            self.event_payload,
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_unapproved_organizer_cannot_create_event(self):
        unapproved = User.objects.create_user(
            email="unapp@karibu.com", password="Pass123!",
            first_name="U", last_name="N", role="organizer", is_approved=False,
        )
        OrganizerProfile.objects.create(user=unapproved, organization_name="Unap Org")
        self.auth(unapproved, "Pass123!")
        resp = self.client.post(
            reverse("organizer-event-create"),
            self.event_payload,
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_end_before_start_rejected(self):
        self.auth(self.organizer_user, "OrgPass123!")
        payload = {
            **self.event_payload,
            "end_datetime": make_future_dt(9).isoformat(),  # before start (day 10)
        }
        resp = self.client.post(
            reverse("organizer-event-create"),
            payload,
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_paid_event_without_price_rejected(self):
        self.auth(self.organizer_user, "OrgPass123!")
        payload = {**self.event_payload, "is_free": False, "ticket_price": "0.00"}
        resp = self.client.post(
            reverse("organizer-event-create"),
            payload,
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_organizer_can_update_draft_event(self):
        self.auth(self.organizer_user, "OrgPass123!")
        event = self.create_draft_event("Old Title")
        resp = self.client.patch(
            reverse("organizer-event-detail", kwargs={"id": event.id}),
            {"title": "New Title"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["title"], "New Title")

    def test_organizer_cannot_update_published_event(self):
        self.auth(self.organizer_user, "OrgPass123!")
        event = self.create_published_event("Published")
        resp = self.client.patch(
            reverse("organizer-event-detail", kwargs={"id": event.id}),
            {"title": "New Title"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_organizer_can_delete_draft(self):
        self.auth(self.organizer_user, "OrgPass123!")
        event = self.create_draft_event("To Delete")
        resp = self.client.delete(
            reverse("organizer-event-detail", kwargs={"id": event.id})
        )
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Event.objects.filter(id=event.id).exists())

    def test_organizer_cannot_delete_published_event(self):
        self.auth(self.organizer_user, "OrgPass123!")
        event = self.create_published_event("Cannot Delete")
        resp = self.client.delete(
            reverse("organizer-event-detail", kwargs={"id": event.id})
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_organizer_cannot_access_other_organizers_events(self):
        other = User.objects.create_user(
            email="other@karibu.com", password="Pass123!",
            first_name="O", last_name="T", role="organizer", is_approved=True,
        )
        OrganizerProfile.objects.create(user=other, organization_name="Other Org")
        event = self.create_draft_event("Other's Event")
        event.organizer = other
        event.save()

        self.auth(self.organizer_user, "OrgPass123!")
        resp = self.client.get(
            reverse("organizer-event-detail", kwargs={"id": event.id})
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)


# ---------------------------------------------------------------------------
# Organizer submit / cancel flow
# ---------------------------------------------------------------------------

class EventWorkflowTests(EventTestBase):

    def test_organizer_can_submit_draft_for_approval(self):
        self.auth(self.organizer_user, "OrgPass123!")
        event = self.create_draft_event("Submission Test")
        resp = self.client.post(
            reverse("organizer-event-submit", kwargs={"id": event.id})
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        event.refresh_from_db()
        self.assertEqual(event.status, EventStatus.PENDING_APPROVAL)
        self.assertIsNotNone(event.submitted_at)

    def test_organizer_can_cancel_published_event(self):
        self.auth(self.organizer_user, "OrgPass123!")
        event = self.create_published_event("To Cancel")
        resp = self.client.post(
            reverse("organizer-event-cancel", kwargs={"id": event.id})
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        event.refresh_from_db()
        self.assertEqual(event.status, EventStatus.CANCELLED)

    def test_cannot_cancel_completed_event(self):
        self.auth(self.organizer_user, "OrgPass123!")
        event = self.create_draft_event("Completed")
        event.status = EventStatus.COMPLETED
        event.save()
        resp = self.client.post(
            reverse("organizer-event-cancel", kwargs={"id": event.id})
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


# ---------------------------------------------------------------------------
# Admin approval flow
# ---------------------------------------------------------------------------

class AdminEventApprovalTests(EventTestBase):

    def _submit_event(self):
        event = self.create_draft_event("Approval Test Event")
        event.status = EventStatus.PENDING_APPROVAL
        event.submitted_at = timezone.now()
        event.save()
        return event

    def test_admin_can_approve_pending_event(self):
        self.auth(self.admin, "AdminPass123!")
        event = self._submit_event()
        resp = self.client.post(
            reverse("admin-event-approval", kwargs={"id": event.id}),
            {"action": "approve"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        event.refresh_from_db()
        self.assertEqual(event.status, EventStatus.PUBLISHED)
        self.assertIsNotNone(event.approved_at)
        self.assertEqual(event.approved_by, self.admin)

    def test_admin_can_reject_pending_event(self):
        self.auth(self.admin, "AdminPass123!")
        event = self._submit_event()
        resp = self.client.post(
            reverse("admin-event-approval", kwargs={"id": event.id}),
            {"action": "reject", "rejection_reason": "Missing venue details."},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        event.refresh_from_db()
        self.assertEqual(event.status, EventStatus.DRAFT)
        self.assertEqual(event.rejection_reason, "Missing venue details.")

    def test_rejection_without_reason_fails(self):
        self.auth(self.admin, "AdminPass123!")
        event = self._submit_event()
        resp = self.client.post(
            reverse("admin-event-approval", kwargs={"id": event.id}),
            {"action": "reject"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_approve_draft_event(self):
        self.auth(self.admin, "AdminPass123!")
        event = self.create_draft_event("Draft Only")
        resp = self.client.post(
            reverse("admin-event-approval", kwargs={"id": event.id}),
            {"action": "approve"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_organizer_cannot_approve_events(self):
        self.auth(self.organizer_user, "OrgPass123!")
        event = self._submit_event()
        resp = self.client.post(
            reverse("admin-event-approval", kwargs={"id": event.id}),
            {"action": "approve"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_pending_events_list(self):
        self.auth(self.admin, "AdminPass123!")
        self._submit_event()
        resp = self.client.get(reverse("admin-event-pending"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(len(resp.data) >= 1)

    def test_admin_can_see_all_events(self):
        self.auth(self.admin, "AdminPass123!")
        self.create_draft_event("Admin Sees This")
        resp = self.client.get(reverse("admin-event-list"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_attendee_cannot_see_admin_event_list(self):
        self.auth(self.attendee, "AttPass123!")
        resp = self.client.get(reverse("admin-event-list"))
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
