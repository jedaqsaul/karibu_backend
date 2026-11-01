"""
analytics/urls.py — All analytics endpoint URL patterns.
Mounted at /api/ in config/urls.py
"""

from django.urls import path
from .views import (
    # Admin
    AdminPlatformSummaryView,
    AdminRevenueOverTimeView,
    AdminTicketsOverTimeView,
    AdminRevenueByCategoryView,
    AdminUserRegistrationsView,
    AdminTopEventsView,
    AdminTopOrganizersView,
    # Organizer
    OrganizerSummaryView,
    OrganizerRevenueOverTimeView,
    OrganizerEventPerformanceView,
    OrganizerSingleEventAnalyticsView,
)

admin_urlpatterns = [
    path("admin/analytics/summary/",              AdminPlatformSummaryView.as_view(),   name="admin-analytics-summary"),
    path("admin/analytics/revenue/",              AdminRevenueOverTimeView.as_view(),   name="admin-analytics-revenue"),
    path("admin/analytics/tickets/",              AdminTicketsOverTimeView.as_view(),   name="admin-analytics-tickets"),
    path("admin/analytics/revenue-by-category/",  AdminRevenueByCategoryView.as_view(), name="admin-analytics-revenue-by-category"),
    path("admin/analytics/registrations/",        AdminUserRegistrationsView.as_view(), name="admin-analytics-registrations"),
    path("admin/analytics/top-events/",           AdminTopEventsView.as_view(),         name="admin-analytics-top-events"),
    path("admin/analytics/top-organizers/",       AdminTopOrganizersView.as_view(),     name="admin-analytics-top-organizers"),
]

organizer_urlpatterns = [
    path("organizer/analytics/summary/",              OrganizerSummaryView.as_view(),              name="organizer-analytics-summary"),
    path("organizer/analytics/revenue/",              OrganizerRevenueOverTimeView.as_view(),      name="organizer-analytics-revenue"),
    path("organizer/analytics/events/",               OrganizerEventPerformanceView.as_view(),     name="organizer-analytics-events"),
    path("organizer/analytics/events/<uuid:event_id>/", OrganizerSingleEventAnalyticsView.as_view(), name="organizer-analytics-event-detail"),
]

urlpatterns = admin_urlpatterns + organizer_urlpatterns
