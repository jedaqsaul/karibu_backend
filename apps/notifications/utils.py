"""
notifications/utils.py — Token generation for password reset.
Uses Django's built-in PasswordResetTokenGenerator — no external deps needed.
"""

from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.contrib.auth import get_user_model
import logging

logger = logging.getLogger("karibu.notifications")
User = get_user_model()
_token_generator = PasswordResetTokenGenerator()


def generate_password_reset_token(user) -> str:
    """Returns a URL-safe token string encoding the user's pk."""
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = _token_generator.make_token(user)
    return f"{uid}.{token}"


def verify_password_reset_token(token_string: str):
    """
    Decodes and validates a password reset token.
    Returns the User on success, None on failure.
    """
    try:
        uid_b64, token = token_string.split(".", 1)
        uid = force_str(urlsafe_base64_decode(uid_b64))
        user = User.objects.get(pk=uid)
        if _token_generator.check_token(user, token):
            return user
    except Exception:
        logger.debug("Invalid password reset token: %s", token_string)
    return None
