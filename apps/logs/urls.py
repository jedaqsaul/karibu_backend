"""
logs/urls.py
"""

from django.urls import path
from .views import AuditLogListView, AuditLogDetailView, AuditLogStatsView

urlpatterns = [
    path("admin/audit-logs/",          AuditLogListView.as_view(),   name="admin-audit-log-list"),
    path("admin/audit-logs/stats/",    AuditLogStatsView.as_view(),  name="admin-audit-log-stats"),
    path("admin/audit-logs/<uuid:id>/", AuditLogDetailView.as_view(), name="admin-audit-log-detail"),
]
