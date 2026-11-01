"""
logs/views.py

Two endpoints, both Super Admin only:
  - AuditLogListView  — paginated, filterable audit trail
  - AuditLogDetailView — single log entry detail

Audit logs are immutable — no create, update, or delete via API.
"""

from django.db.models import Q
from datetime import datetime, time
from django.utils import timezone

from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsSuperAdmin
from .models import AuditLog
from .serializers import AuditLogSerializer, AuditLogFilterSerializer


class AuditLogListView(generics.ListAPIView):
    """
    GET /api/admin/audit-logs/

    Filterable, paginated audit trail.

    Query params:
      ?action=LOGIN
      ?category=auth|account|event|ticket|admin|system
      ?user_email=someone@example.com
      ?search=<text>          (searches action + description + user_email)
      ?start_date=YYYY-MM-DD
      ?end_date=YYYY-MM-DD
    """
    permission_classes = [IsSuperAdmin]
    serializer_class   = AuditLogSerializer

    def get_queryset(self):
        params = AuditLogFilterSerializer(data=self.request.query_params)
        params.is_valid(raise_exception=True)
        v = params.validated_data

        qs = AuditLog.objects.select_related("user").order_by("-created_at")

        if v.get("action"):
            qs = qs.filter(action__iexact=v["action"])

        if v.get("category"):
            qs = qs.filter(category=v["category"])

        if v.get("user_email"):
            qs = qs.filter(user_email__icontains=v["user_email"])

        if v.get("search"):
            term = v["search"]
            qs = qs.filter(
                Q(action__icontains=term) |
                Q(description__icontains=term) |
                Q(user_email__icontains=term)
            )

        if v.get("start_date"):
            start_dt = timezone.make_aware(datetime.combine(v["start_date"], time.min))
            qs = qs.filter(created_at__gte=start_dt)

        if v.get("end_date"):
            end_dt = timezone.make_aware(datetime.combine(v["end_date"], time.max))
            qs = qs.filter(created_at__lte=end_dt)

        return qs


class AuditLogDetailView(APIView):
    """GET /api/admin/audit-logs/<id>/ — Single log entry."""
    permission_classes = [IsSuperAdmin]

    def get(self, request, id):
        try:
            log = AuditLog.objects.select_related("user").get(id=id)
        except AuditLog.DoesNotExist:
            return Response(
                {"error": "Audit log entry not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(AuditLogSerializer(log).data)


class AuditLogStatsView(APIView):
    """
    GET /api/admin/audit-logs/stats/

    Aggregated counts by category and most frequent actions.
    Used for the admin activity dashboard widget.
    """
    permission_classes = [IsSuperAdmin]

    def get(self, request):
        from django.db.models import Count

        by_category = (
            AuditLog.objects
            .values("category")
            .annotate(count=Count("id"))
            .order_by("-count")
        )

        top_actions = (
            AuditLog.objects
            .values("action")
            .annotate(count=Count("id"))
            .order_by("-count")[:10]
        )

        total = AuditLog.objects.count()

        return Response({
            "total_entries": total,
            "by_category": list(by_category),
            "top_actions":  list(top_actions),
        })
