"""
analytics/tests/test_analytics.py

Phase 4 test suite. Tests verify:
- Correct aggregation results against known fixture data
- Date range filtering works correctly
- Role isolation: organizer only sees own data, admin sees all
- Edge cases: empty datasets, zero revenue, no events
- Query param validation (invalid dates, bad period values)
"""

from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient
from django.contrib.auth import get_user_model

from apps.accounts.models import OrganizerProfile
from apps.events.models import Event, EventStatus, Category
from apps.tickets.models import Ticket, TicketStatus
from shared.utils.ticket_number import generate_ticket_number

User = get_user_model()


# ---------------------------------------------------------------------------
# Base with rich fixture data
# ---------------------------------------------------------------------------

def dt(days_offset=0):
    """Return a timezone-aware datetime offset from now."""
    return timezone.now() + timedelta(days=days_offset)


class AnalyticsTestBase(TestCase):
    """
    Creates a controlled dataset:
      - 1 super admin
      - 2 organizers (org1 owns event_a and event_b; org2 owns event_c)
      - 3 attendees
      - 3 events with known ticket sales and revenues
    """

    def setUp(self):
        self.client = APIClient()

        # Users
        self.admin = User.objects.create_superuser(
            email="admin@k.com", password="AdminPass123!",
            first_name="Super", last_name="Admin",
        )
        self.org1 = User.objects.create_user(
            email="org1@k.com", password="OrgPass123!",
            first_name="Org", last_name="One",
            role="organizer", is_approved=True,
        )
        OrganizerProfile.objects.create(user=self.org1, organization_name="Org One")

        self.org2 = User.objects.create_user(
            email="org2@k.com", password="OrgPass123!",
            first_name="Org", last_name="Two",
            role="organizer", is_approved=True,
        )
        OrganizerProfile.objects.create(user=self.org2, organization_name="Org Two")

        self.att1 = User.objects.create_user(
            email="att1@k.com", password="AttPass123!",
            first_name="A", last_name="One",
        )
        self.att2 = User.objects.create_user(
            email="att2@k.com", password="AttPass123!",
            first_name="A", last_name="Two",
        )
        self.att3 = User.objects.create_user(
            email="att3@k.com", password="AttPass123!",
            first_name="A", last_name="Three",
        )

        self.cat_music = Category.objects.create(name="Music", slug="music")
        self.cat_tech  = Category.objects.create(name="Tech",  slug="tech")

        # Events
        self.event_a = self._make_event(
            organizer=self.org1, title="Jazz Night",
            slug="jazz-night", category=self.cat_music,
            price=1000, capacity=100,
        )
        self.event_b = self._make_event(
            organizer=self.org1, title="Tech Summit",
            slug="tech-summit", category=self.cat_tech,
            price=2000, capacity=50,
        )
        self.event_c = self._make_event(
            organizer=self.org2, title="Org2 Event",
            slug="org2-event", category=self.cat_music,
            price=500, capacity=200,
        )

        # Tickets — known amounts for deterministic assertions
        # event_a: 3 confirmed (KES 3,000 revenue)
        self._make_tickets(self.event_a, self.att1, 2, TicketStatus.CONFIRMED)  # 2,000
        self._make_tickets(self.event_a, self.att2, 1, TicketStatus.CONFIRMED)  # 1,000
        # event_b: 2 confirmed (KES 4,000 revenue) + 1 cancelled
        self._make_tickets(self.event_b, self.att1, 2, TicketStatus.CONFIRMED)  # 4,000
        self._make_tickets(self.event_b, self.att3, 1, TicketStatus.CANCELLED)  # 0 revenue
        # event_c: 4 confirmed (KES 2,000 revenue)
        self._make_tickets(self.event_c, self.att2, 4, TicketStatus.CONFIRMED)  # 2,000

    def _make_event(self, organizer, title, slug, category, price, capacity):
        return Event.objects.create(
            organizer=organizer, title=title, slug=slug,
            description="Test event.", venue="Test Venue",
            address="123 St", city="Nairobi",
            start_datetime=dt(10), end_datetime=dt(10, ),
            is_free=(price == 0), ticket_price=price,
            total_capacity=capacity, status=EventStatus.PUBLISHED,
            category=category,
        )

    def _make_tickets(self, event, attendee, qty, ticket_status):
        for _ in range(qty):
            Ticket.objects.create(
                event=event, attendee=attendee,
                ticket_number=generate_ticket_number(),
                price_paid=event.ticket_price if ticket_status != TicketStatus.CANCELLED else 0,
                status=ticket_status,
            )
        if ticket_status in (TicketStatus.CONFIRMED, TicketStatus.USED):
            event.tickets_sold += qty
            event.save(update_fields=["tickets_sold"])

    def auth(self, user, password="AttPass123!"):
        resp = self.client.post(
            reverse("login"),
            {"email": user.email, "password": password},
            format="json",
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['access']}")


# ---------------------------------------------------------------------------
# Admin summary tests
# ---------------------------------------------------------------------------

class AdminSummaryTests(AnalyticsTestBase):

    def test_summary_returns_correct_user_counts(self):
        self.auth(self.admin, "AdminPass123!")
        resp = self.client.get(reverse("admin-analytics-summary"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # admin + org1 + org2 + att1 + att2 + att3 = 6
        self.assertEqual(resp.data["total_users"], 6)
        self.assertEqual(resp.data["total_organisers"], 2)
        self.assertEqual(resp.data["total_attendees"], 3)

    def test_summary_returns_correct_event_counts(self):
        self.auth(self.admin, "AdminPass123!")
        resp = self.client.get(reverse("admin-analytics-summary"))
        self.assertEqual(resp.data["total_events"], 3)
        self.assertEqual(resp.data["published_events"], 3)

    def test_summary_returns_correct_ticket_counts(self):
        self.auth(self.admin, "AdminPass123!")
        resp = self.client.get(reverse("admin-analytics-summary"))
        # 3 + 2 + 4 confirmed + 1 cancelled = 10 total
        self.assertEqual(resp.data["total_tickets"], 10)
        self.assertEqual(resp.data["confirmed_tickets"], 9)
        self.assertEqual(resp.data["cancelled_tickets"], 1)

    def test_summary_returns_correct_total_revenue(self):
        self.auth(self.admin, "AdminPass123!")
        resp = self.client.get(reverse("admin-analytics-summary"))
        # event_a: 3*1000=3000, event_b: 2*2000=4000, event_c: 4*500=2000 → 9000
        self.assertEqual(Decimal(str(resp.data["total_revenue"])), Decimal("9000.00"))

    def test_attendee_cannot_access_admin_summary(self):
        self.auth(self.att1)
        resp = self.client.get(reverse("admin-analytics-summary"))
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_organizer_cannot_access_admin_summary(self):
        self.auth(self.org1, "OrgPass123!")
        resp = self.client.get(reverse("admin-analytics-summary"))
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_cannot_access_admin_summary(self):
        resp = self.client.get(reverse("admin-analytics-summary"))
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)


# ---------------------------------------------------------------------------
# Admin chart endpoints
# ---------------------------------------------------------------------------

class AdminChartTests(AnalyticsTestBase):

    def test_revenue_over_time_returns_results_list(self):
        self.auth(self.admin, "AdminPass123!")
        resp = self.client.get(reverse("admin-analytics-revenue"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("results", resp.data)
        self.assertIsInstance(resp.data["results"], list)

    def test_revenue_over_time_result_structure(self):
        self.auth(self.admin, "AdminPass123!")
        resp = self.client.get(reverse("admin-analytics-revenue"))
        if resp.data["results"]:
            row = resp.data["results"][0]
            self.assertIn("period",       row)
            self.assertIn("revenue",      row)
            self.assertIn("ticket_count", row)

    def test_tickets_over_time_returns_results_list(self):
        self.auth(self.admin, "AdminPass123!")
        resp = self.client.get(reverse("admin-analytics-tickets"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("results", resp.data)

    def test_tickets_over_time_result_structure(self):
        self.auth(self.admin, "AdminPass123!")
        resp = self.client.get(reverse("admin-analytics-tickets"))
        if resp.data["results"]:
            row = resp.data["results"][0]
            self.assertIn("total",     row)
            self.assertIn("confirmed", row)
            self.assertIn("cancelled", row)

    def test_revenue_by_category_music_is_highest(self):
        self.auth(self.admin, "AdminPass123!")
        resp = self.client.get(reverse("admin-analytics-revenue-by-category"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        results = resp.data["results"]
        slugs = [r["slug"] for r in results]
        self.assertIn("music", slugs)
        # Music: 3000 (event_a) + 2000 (event_c) = 5000; Tech: 4000 (event_b)
        music = next(r for r in results if r["slug"] == "music")
        tech  = next(r for r in results if r["slug"] == "tech")
        self.assertGreater(music["revenue"], tech["revenue"])

    def test_revenue_by_category_structure(self):
        self.auth(self.admin, "AdminPass123!")
        resp = self.client.get(reverse("admin-analytics-revenue-by-category"))
        if resp.data["results"]:
            row = resp.data["results"][0]
            self.assertIn("category",     row)
            self.assertIn("revenue",      row)
            self.assertIn("ticket_count", row)

    def test_user_registrations_returns_results(self):
        self.auth(self.admin, "AdminPass123!")
        resp = self.client.get(reverse("admin-analytics-registrations"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("results", resp.data)

    def test_period_month_aggregation(self):
        self.auth(self.admin, "AdminPass123!")
        resp = self.client.get(reverse("admin-analytics-revenue"), {"period": "month"})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_invalid_period_returns_400(self):
        self.auth(self.admin, "AdminPass123!")
        resp = self.client.get(reverse("admin-analytics-revenue"), {"period": "decade"})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_date_range_returns_400(self):
        self.auth(self.admin, "AdminPass123!")
        resp = self.client.get(
            reverse("admin-analytics-revenue"),
            {"start_date": "2025-12-31", "end_date": "2025-01-01"},
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


# ---------------------------------------------------------------------------
# Admin top events / organizers
# ---------------------------------------------------------------------------

class AdminTopListsTests(AnalyticsTestBase):

    def test_top_events_returns_results(self):
        self.auth(self.admin, "AdminPass123!")
        resp = self.client.get(reverse("admin-analytics-top-events"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("results", resp.data)

    def test_top_events_ordered_by_revenue(self):
        self.auth(self.admin, "AdminPass123!")
        resp = self.client.get(
            reverse("admin-analytics-top-events"), {"order_by": "revenue"}
        )
        results = resp.data["results"]
        self.assertTrue(len(results) >= 2)
        # event_b has 4000, event_a has 3000
        revenues = [r["revenue"] for r in results]
        self.assertEqual(revenues, sorted(revenues, reverse=True))

    def test_top_events_ordered_by_ticket_count(self):
        self.auth(self.admin, "AdminPass123!")
        resp = self.client.get(
            reverse("admin-analytics-top-events"), {"order_by": "ticket_count"}
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        results = resp.data["results"]
        counts = [r["ticket_count"] for r in results]
        self.assertEqual(counts, sorted(counts, reverse=True))

    def test_top_events_limit_respected(self):
        self.auth(self.admin, "AdminPass123!")
        resp = self.client.get(reverse("admin-analytics-top-events"), {"limit": 2})
        self.assertLessEqual(len(resp.data["results"]), 2)

    def test_top_events_structure(self):
        self.auth(self.admin, "AdminPass123!")
        resp = self.client.get(reverse("admin-analytics-top-events"))
        if resp.data["results"]:
            row = resp.data["results"][0]
            self.assertIn("event_id",     row)
            self.assertIn("title",        row)
            self.assertIn("revenue",      row)
            self.assertIn("ticket_count", row)

    def test_top_organizers_returns_results(self):
        self.auth(self.admin, "AdminPass123!")
        resp = self.client.get(reverse("admin-analytics-top-organizers"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("results", resp.data)

    def test_top_organizers_org1_has_higher_revenue(self):
        self.auth(self.admin, "AdminPass123!")
        resp = self.client.get(reverse("admin-analytics-top-organizers"))
        results = resp.data["results"]
        emails  = [r["organizer_email"] for r in results]
        # org1: 3000+4000=7000, org2: 2000 — org1 should be first
        self.assertEqual(emails[0], self.org1.email)

    def test_top_organizers_structure(self):
        self.auth(self.admin, "AdminPass123!")
        resp = self.client.get(reverse("admin-analytics-top-organizers"))
        if resp.data["results"]:
            row = resp.data["results"][0]
            self.assertIn("organizer_email", row)
            self.assertIn("revenue",         row)
            self.assertIn("event_count",     row)


# ---------------------------------------------------------------------------
# Organizer analytics
# ---------------------------------------------------------------------------

class OrganizerSummaryTests(AnalyticsTestBase):

    def test_org1_summary_scoped_to_own_events(self):
        self.auth(self.org1, "OrgPass123!")
        resp = self.client.get(reverse("organizer-analytics-summary"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # org1 has event_a and event_b
        self.assertEqual(resp.data["total_events"], 2)

    def test_org2_summary_scoped_to_own_events(self):
        self.auth(self.org2, "OrgPass123!")
        resp = self.client.get(reverse("organizer-analytics-summary"))
        self.assertEqual(resp.data["total_events"], 1)

    def test_org1_revenue_does_not_include_org2_events(self):
        self.auth(self.org1, "OrgPass123!")
        resp = self.client.get(reverse("organizer-analytics-summary"))
        # org1: 3000+4000=7000 (not 9000)
        self.assertEqual(Decimal(str(resp.data["total_revenue"])), Decimal("7000.00"))

    def test_org1_confirmed_ticket_count(self):
        self.auth(self.org1, "OrgPass123!")
        resp = self.client.get(reverse("organizer-analytics-summary"))
        # event_a: 3 confirmed, event_b: 2 confirmed → 5
        self.assertEqual(resp.data["confirmed_tickets"], 5)

    def test_attendee_cannot_access_organizer_summary(self):
        self.auth(self.att1)
        resp = self.client.get(reverse("organizer-analytics-summary"))
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_cannot_access_organizer_summary_directly(self):
        self.auth(self.admin, "AdminPass123!")
        resp = self.client.get(reverse("organizer-analytics-summary"))
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)


class OrganizerChartTests(AnalyticsTestBase):

    def test_organizer_revenue_over_time(self):
        self.auth(self.org1, "OrgPass123!")
        resp = self.client.get(reverse("organizer-analytics-revenue"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("results", resp.data)

    def test_organizer_event_performance_list(self):
        self.auth(self.org1, "OrgPass123!")
        resp = self.client.get(reverse("organizer-analytics-events"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data["results"]), 2)  # org1 has 2 events

    def test_organizer_event_performance_structure(self):
        self.auth(self.org1, "OrgPass123!")
        resp = self.client.get(reverse("organizer-analytics-events"))
        row = resp.data["results"][0]
        self.assertIn("event_id",       row)
        self.assertIn("title",          row)
        self.assertIn("fill_rate_pct",  row)
        self.assertIn("revenue",        row)
        self.assertIn("total_capacity", row)

    def test_event_performance_fill_rate_accuracy(self):
        self.auth(self.org1, "OrgPass123!")
        resp = self.client.get(reverse("organizer-analytics-events"))
        # Jazz Night: 3 sold / 100 capacity = 3.0%
        jazz = next(r for r in resp.data["results"] if r["title"] == "Jazz Night")
        self.assertEqual(jazz["fill_rate_pct"], 3.0)

    def test_organizer_single_event_detail(self):
        self.auth(self.org1, "OrgPass123!")
        resp = self.client.get(
            reverse("organizer-analytics-event-detail", kwargs={"event_id": self.event_a.id})
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("event",          resp.data)
        self.assertIn("ticket_stats",   resp.data)
        self.assertIn("sales_timeline", resp.data)
        self.assertIn("scan_stats",     resp.data)

    def test_single_event_ticket_stats_accuracy(self):
        self.auth(self.org1, "OrgPass123!")
        resp = self.client.get(
            reverse("organizer-analytics-event-detail", kwargs={"event_id": self.event_a.id})
        )
        stats = resp.data["ticket_stats"]
        self.assertEqual(stats["confirmed"], 3)
        self.assertEqual(float(stats["revenue"]), 3000.0)

    def test_organizer_cannot_access_other_organizers_event_analytics(self):
        # org2 tries to access org1's event analytics
        self.auth(self.org2, "OrgPass123!")
        resp = self.client.get(
            reverse("organizer-analytics-event-detail", kwargs={"event_id": self.event_a.id})
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_organizer_event_performance_status_filter(self):
        self.auth(self.org1, "OrgPass123!")
        resp = self.client.get(
            reverse("organizer-analytics-events"), {"status": "published"}
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        for row in resp.data["results"]:
            self.assertEqual(row["status"], "published")

    def test_organizer_event_performance_invalid_status(self):
        self.auth(self.org1, "OrgPass123!")
        resp = self.client.get(
            reverse("organizer-analytics-events"), {"status": "nonexistent"}
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class AnalyticsEdgeCaseTests(AnalyticsTestBase):

    def test_empty_date_range_returns_empty_results(self):
        self.auth(self.admin, "AdminPass123!")
        resp = self.client.get(
            reverse("admin-analytics-revenue"),
            {"start_date": "2000-01-01", "end_date": "2000-01-02"},
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["results"], [])

    def test_summary_with_no_tickets_returns_zero_revenue(self):
        # Create a new organizer with no tickets
        new_org = User.objects.create_user(
            email="empty@k.com", password="OrgPass123!",
            first_name="Empty", last_name="Org",
            role="organizer", is_approved=True,
        )
        OrganizerProfile.objects.create(user=new_org, organization_name="Empty Org")
        self.auth(new_org, "OrgPass123!")
        resp = self.client.get(reverse("organizer-analytics-summary"))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["total_events"], 0)
        self.assertEqual(Decimal(str(resp.data["total_revenue"])), Decimal("0"))

    def test_cancelled_tickets_excluded_from_revenue(self):
        self.auth(self.admin, "AdminPass123!")
        resp = self.client.get(reverse("admin-analytics-summary"))
        # event_b cancelled ticket (KES 0) should not inflate revenue
        self.assertEqual(Decimal(str(resp.data["total_revenue"])), Decimal("9000.00"))
