"""
events/urls.py — URL patterns for all event-related endpoints.
Mounted at /api/ in config/urls.py
"""

from django.urls import path
from .views import (
    # Public
    PublicEventListView,
    PublicEventDetailView,
    PublicCategoryListView,
    # Attendee — saved events
    SavedEventsListView,
    ToggleSaveEventView,
    # Organizer
    OrganizerEventListView,
    OrganizerEventCreateView,
    OrganizerEventDetailView,
    OrganizerEventSubmitView,
    OrganizerEventCancelView,
    EventImageUploadView,
    # Admin
    AdminEventListView,
    AdminEventDetailView,
    AdminEventApprovalView,
    AdminPendingEventsView,
    AdminCategoryListCreateView,
    AdminCategoryDetailView,
)

# Public
# NOTE: "events/saved/" and "events/categories/" MUST be declared before
# "events/<slug:slug>/" — otherwise the slug pattern would greedily match
# them as an event slug and they'd never be reached.
public_urlpatterns = [
    path("events/",                  PublicEventListView.as_view(),     name="public-event-list"),
    path("events/categories/",       PublicCategoryListView.as_view(),  name="public-category-list"),
    path("events/saved/",            SavedEventsListView.as_view(),     name="attendee-saved-events"),
    path("events/<uuid:id>/save/",   ToggleSaveEventView.as_view(),     name="attendee-toggle-save"),
    path("events/<slug:slug>/",      PublicEventDetailView.as_view(),   name="public-event-detail"),
]

# Organizer
organizer_urlpatterns = [
    path("organizer/events/",                              OrganizerEventListView.as_view(),   name="organizer-event-list"),
    path("organizer/events/create/",                       OrganizerEventCreateView.as_view(), name="organizer-event-create"),
    path("organizer/events/<uuid:id>/",                    OrganizerEventDetailView.as_view(), name="organizer-event-detail"),
    path("organizer/events/<uuid:id>/submit/",             OrganizerEventSubmitView.as_view(), name="organizer-event-submit"),
    path("organizer/events/<uuid:id>/cancel/",             OrganizerEventCancelView.as_view(), name="organizer-event-cancel"),
    path("organizer/events/<uuid:id>/images/",             EventImageUploadView.as_view(),     name="organizer-event-image-upload"),
    path("organizer/events/<uuid:id>/images/<uuid:image_id>/", EventImageUploadView.as_view(), name="organizer-event-image-delete"),
]

# Admin
admin_urlpatterns = [
    path("admin/events/",                    AdminEventListView.as_view(),         name="admin-event-list"),
    path("admin/events/pending/",            AdminPendingEventsView.as_view(),     name="admin-event-pending"),
    path("admin/events/<uuid:id>/",          AdminEventDetailView.as_view(),       name="admin-event-detail"),
    path("admin/events/<uuid:id>/approval/", AdminEventApprovalView.as_view(),     name="admin-event-approval"),
    path("admin/categories/",               AdminCategoryListCreateView.as_view(), name="admin-category-list"),
    path("admin/categories/<uuid:id>/",     AdminCategoryDetailView.as_view(),     name="admin-category-detail"),
]

urlpatterns = public_urlpatterns + organizer_urlpatterns + admin_urlpatterns
