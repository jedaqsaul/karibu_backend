"""
shared/exceptions.py

Global exception handler for DRF.
Ensures all errors return a consistent JSON shape:
  { "error": "...", "detail": {...} }
Never leaks stack traces to the client in production.
"""

from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status
import logging

logger = logging.getLogger("karibu.api")


def karibu_exception_handler(exc, context):
    """
    Custom DRF exception handler.
    Wraps all error responses in a standard envelope.
    """
    response = exception_handler(exc, context)

    if response is not None:
        error_data = {
            "error": _get_error_message(response),
            "status_code": response.status_code,
        }

        # Include field-level validation errors under 'detail'
        if isinstance(response.data, dict) and any(
            isinstance(v, list) for v in response.data.values()
        ):
            error_data["detail"] = response.data
        elif "detail" in response.data:
            error_data["error"] = str(response.data["detail"])

        response.data = error_data

    else:
        # Unhandled exception — log it, return generic 500
        logger.exception(
            "Unhandled exception in %s",
            context.get("view", "unknown view"),
            exc_info=exc,
        )
        response = Response(
            {"error": "An unexpected error occurred. Please try again later."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return response


def _get_error_message(response):
    data = response.data
    if isinstance(data, dict):
        if "detail" in data:
            return str(data["detail"])
        if "non_field_errors" in data:
            return str(data["non_field_errors"][0])
    if isinstance(data, list) and data:
        return str(data[0])
    return "An error occurred."
