"""
logs/middleware.py

Lightweight audit middleware.
Logs every mutating request (POST, PUT, PATCH, DELETE) with user, path, and IP.
Read-only requests (GET, HEAD, OPTIONS) are not logged at middleware level
— they are logged selectively in views where needed.
"""

import logging
import time

logger = logging.getLogger("karibu.audit")

MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
SKIP_PATHS = {"/api/auth/token/refresh/", "/admin/jsi18n/"}


class AuditLogMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start = time.monotonic()
        response = self.get_response(request)
        duration_ms = round((time.monotonic() - start) * 1000, 2)

        if request.method in MUTATING_METHODS and request.path not in SKIP_PATHS:
            user = getattr(request, "user", None)
            user_info = (
                f"{user.email} [{user.role}]"
                if user and user.is_authenticated
                else "anonymous"
            )
            logger.info(
                "%s %s | user=%s | ip=%s | status=%s | %sms",
                request.method,
                request.path,
                user_info,
                _get_client_ip(request),
                response.status_code,
                duration_ms,
            )

        return response


def _get_client_ip(request):
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "unknown")
