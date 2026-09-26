"""Security utilities including webhook signature verification and timing-safe checks."""

import hashlib
import hmac

from app.core.config import get_settings
from app.core.exceptions import AppException


class WebhookAuthenticationError(AppException):
    """Raised when incoming webhook authentication or signature fails."""

    status_code = 401
    error_code = "WEBHOOK_AUTHENTICATION_FAILED"


def verify_webhook_secret(provided_secret: str | None, expected_secret: str | None = None) -> bool:
    """Validate webhook secret against configured secret using timing-safe comparison."""
    if expected_secret is None:
        expected_secret = get_settings().N8N_WEBHOOK_SECRET

    if not provided_secret or not expected_secret:
        return False

    return hmac.compare_digest(provided_secret.encode("utf-8"), expected_secret.encode("utf-8"))


def verify_hmac_sha256(payload: bytes, signature: str, secret: str) -> bool:
    """Verify HMAC SHA-256 signature for secure external webhooks (e.g. WhatsApp / Meta)."""
    expected_sig = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, expected_sig)
