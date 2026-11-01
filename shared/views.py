"""
shared/views.py — Health check endpoint.

GET /api/health/  — returns 200 if the application is running and DB is reachable.
Used by load balancers, uptime monitors, and deployment health gates.
Returns 503 if the DB is unreachable.
"""

from django.db import connection
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status


class HealthCheckView(APIView):
    """
    Lightweight health check.
    Checks: application running, database connection alive.
    Never exposes internal details in production.
    """
    permission_classes = [AllowAny]
    authentication_classes = []   # skip JWT overhead for health checks

    def get(self, request):
        checks = {
            "status":   "ok",
            "database": "ok",
        }
        http_status = status.HTTP_200_OK

        try:
            connection.ensure_connection()
        except Exception:
            checks["database"] = "unreachable"
            checks["status"]   = "degraded"
            http_status        = status.HTTP_503_SERVICE_UNAVAILABLE

        return Response(checks, status=http_status)
