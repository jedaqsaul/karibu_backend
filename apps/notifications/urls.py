"""
notifications/urls.py
"""

from django.urls import path
from .views import (
    NotificationListView,
    NotificationUnreadCountView,
    NotificationMarkReadView,
    NotificationMarkAllReadView,
    NotificationDeleteView,
    NotificationClearAllView,
    AdminEmailLogListView,
)

user_urlpatterns = [
    path("notifications/",               NotificationListView.as_view(),       name="notification-list"),
    path("notifications/unread-count/",  NotificationUnreadCountView.as_view(), name="notification-unread-count"),
    path("notifications/mark-read/",     NotificationMarkReadView.as_view(),    name="notification-mark-read"),
    path("notifications/mark-all-read/", NotificationMarkAllReadView.as_view(), name="notification-mark-all-read"),
    path("notifications/clear/",         NotificationClearAllView.as_view(),    name="notification-clear"),
    path("notifications/<uuid:id>/",     NotificationDeleteView.as_view(),      name="notification-delete"),
]

admin_urlpatterns = [
    path("admin/email-logs/", AdminEmailLogListView.as_view(), name="admin-email-logs"),
]

urlpatterns = user_urlpatterns + admin_urlpatterns
