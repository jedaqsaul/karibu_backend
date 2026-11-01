"""
analytics/views.py

All views delegate to the service layer — no ORM here.
Views are responsible only for:
  1. Authenticating and authorising the request
  2. Validating query params
  3. Calling the right service method
  4. Returning the result as JSON
"""

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsSuperAdmin, IsOrganizer
from apps.logs.utils import log_action

from .serializers import (
    DateRangeParamsSerializer,
    TopEventsParamsSerializer,
    TopOrganizersParamsSerializer,
    EventPerformanceParamsSerializer,
)
from .services import AdminAnalyticsService, OrganizerAnalyticsService


# ---------------------------------------------------------------------------
# Super Admin analytics
# ---------------------------------------------------------------------------

class AdminPlatformSummaryView(APIView):
    """
    GET /api/admin/analytics/summary/
    Top-level KPI cards: total users, revenue, events, ticket sales.
    """
    permission_classes = [IsSuperAdmin]

    def get(self, request):
        data = AdminAnalyticsService.platform_summary()
        return Response(data)


class AdminRevenueOverTimeView(APIView):
    """
    GET /api/admin/analytics/revenue/
    Revenue chart data grouped by day/week/month.

    Query params:
      ?start_date=YYYY-MM-DD  (default: 30 days ago)
      ?end_date=YYYY-MM-DD    (default: today)
      ?period=day|week|month  (default: day)
    """
    permission_classes = [IsSuperAdmin]

    def get(self, request):
        params = DateRangeParamsSerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        data = AdminAnalyticsService.revenue_over_time(request.query_params)
        return Response({"results": data, "params": params.validated_data})


class AdminTicketsOverTimeView(APIView):
    """
    GET /api/admin/analytics/tickets/
    Ticket sales volume chart grouped by period.
    """
    permission_classes = [IsSuperAdmin]

    def get(self, request):
        params = DateRangeParamsSerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        data = AdminAnalyticsService.tickets_over_time(request.query_params)
        return Response({"results": data, "params": params.validated_data})


class AdminRevenueByCategoryView(APIView):
    """
    GET /api/admin/analytics/revenue-by-category/
    Pie chart: revenue per category.
    """
    permission_classes = [IsSuperAdmin]

    def get(self, request):
        params = DateRangeParamsSerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        data = AdminAnalyticsService.revenue_by_category(request.query_params)
        return Response({"results": data})


class AdminUserRegistrationsView(APIView):
    """
    GET /api/admin/analytics/registrations/
    User signup trend over time.
    """
    permission_classes = [IsSuperAdmin]

    def get(self, request):
        params = DateRangeParamsSerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        data = AdminAnalyticsService.user_registrations_over_time(request.query_params)
        return Response({"results": data})


class AdminTopEventsView(APIView):
    """
    GET /api/admin/analytics/top-events/
    Top events by revenue or ticket count.

    Query params:
      ?limit=10
      ?order_by=revenue|ticket_count
    """
    permission_classes = [IsSuperAdmin]

    def get(self, request):
        params = TopEventsParamsSerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        data = AdminAnalyticsService.top_events(request.query_params)
        return Response({"results": data})


class AdminTopOrganizersView(APIView):
    """
    GET /api/admin/analytics/top-organizers/
    Top organizers by revenue.
    """
    permission_classes = [IsSuperAdmin]

    def get(self, request):
        params = TopOrganizersParamsSerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        data = AdminAnalyticsService.top_organizers(request.query_params)
        return Response({"results": data})


# ---------------------------------------------------------------------------
# Organizer analytics
# ---------------------------------------------------------------------------

class OrganizerSummaryView(APIView):
    """
    GET /api/organizer/analytics/summary/
    KPI cards for the organizer's own dashboard.
    """
    permission_classes = [IsOrganizer]

    def get(self, request):
        data = OrganizerAnalyticsService.summary(request.user)
        return Response(data)


class OrganizerRevenueOverTimeView(APIView):
    """
    GET /api/organizer/analytics/revenue/
    Revenue chart scoped to this organizer's events.
    """
    permission_classes = [IsOrganizer]

    def get(self, request):
        params = DateRangeParamsSerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        data = OrganizerAnalyticsService.revenue_over_time(request.user, request.query_params)
        return Response({"results": data})


class OrganizerEventPerformanceView(APIView):
    """
    GET /api/organizer/analytics/events/
    Per-event breakdown: capacity, sold, fill rate, revenue.

    Query params:
      ?status=published|draft|...
    """
    permission_classes = [IsOrganizer]

    def get(self, request):
        params = EventPerformanceParamsSerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        data = OrganizerAnalyticsService.event_performance(request.user, request.query_params)
        return Response({"results": data})


class OrganizerSingleEventAnalyticsView(APIView):
    """
    GET /api/organizer/analytics/events/<event_id>/
    Deep analytics for a single event: sales timeline, scan stats.
    """
    permission_classes = [IsOrganizer]

    def get(self, request, event_id):
        data = OrganizerAnalyticsService.single_event_detail(request.user, str(event_id))
        if data is None:
            from rest_framework import status
            return Response(
                {"error": "Event not found or does not belong to you."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(data)
