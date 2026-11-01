"""
logs/utils.py

log_action() — the single function imported by all other apps.
Never raises — logging failures must never break the caller.
"""

import logging
from .models import AuditLog, ACTION_CATEGORY_MAP

logger = logging.getLogger("karibu.audit")


def log_action(
    user,
    action: str,
    description: str = "",
    request=None,
    content_type: str = "",
    object_id: str = "",
):
    """
    Create a persistent AuditLog entry.

    Args:
        user:         The User performing the action (None for system actions).
        action:       Short uppercase identifier e.g. "LOGIN", "EVENT_CREATED".
        description:  Human-readable detail.
        request:      Optional Django request — used to extract IP and user-agent.
        content_type: Optional model name e.g. "Event".
        object_id:    Optional object UUID string.
    """
    ip_address = None
    user_agent = ""

    if request:
        ip_address = _get_client_ip(request)
        user_agent = request.META.get("HTTP_USER_AGENT", "")[:500]

    category = ACTION_CATEGORY_MAP.get(action, AuditLog.ActionCategory.SYSTEM)

    try:
        AuditLog.objects.create(
            user=user,
            user_email=getattr(user, "email", "") or "",
            user_role=getattr(user, "role", "") or "",
            action=action,
            category=category,
            description=description,
            ip_address=ip_address,
            user_agent=user_agent,
            content_type=content_type,
            object_id=object_id,
        )
    except Exception:
        logger.exception(
            "Failed to write audit log: action=%s user=%s",
            action, getattr(user, "email", "unknown"),
        )


def _get_client_ip(request) -> str:
    x_forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded:
        return x_forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")
