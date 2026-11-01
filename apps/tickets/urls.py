"""
tickets/urls.py — All ticket endpoint URL patterns.
Mounted at /api/ in config/urls.py
"""

from django.urls import path
from .views import (
    # Attendee
    TicketPurchaseView,
    MyTicketListView,
    MyTicketDetailView,
    TicketDownloadView,
    TicketCancelView,
    # Organizer
    OrganizerEventTicketsView,
    TicketScanView,
    # Admin
    AdminTicketListView,
    AdminTicketDetailView,
    AdminTicketCancelView,
)

attendee_urlpatterns = [
    path("tickets/",                    MyTicketListView.as_view(),   name="my-ticket-list"),
    path("tickets/purchase/",           TicketPurchaseView.as_view(), name="ticket-purchase"),
    path("tickets/<uuid:id>/",          MyTicketDetailView.as_view(), name="my-ticket-detail"),
    path("tickets/<uuid:id>/download/", TicketDownloadView.as_view(), name="ticket-download"),
    path("tickets/<uuid:id>/cancel/",   TicketCancelView.as_view(),   name="ticket-cancel"),
]

organizer_urlpatterns = [
    path("organizer/events/<uuid:event_id>/tickets/", OrganizerEventTicketsView.as_view(), name="organizer-event-tickets"),
    path("organizer/tickets/scan/",                   TicketScanView.as_view(),            name="ticket-scan"),
]

admin_urlpatterns = [
    path("admin/tickets/",                    AdminTicketListView.as_view(),   name="admin-ticket-list"),
    path("admin/tickets/<uuid:id>/",          AdminTicketDetailView.as_view(), name="admin-ticket-detail"),
    path("admin/tickets/<uuid:id>/cancel/",   AdminTicketCancelView.as_view(), name="admin-ticket-cancel"),
]

urlpatterns = attendee_urlpatterns + organizer_urlpatterns + admin_urlpatterns
