"""Security utilities including webhook signature verification, authentication, and RBAC."""

import hashlib
import hmac
from enum import StrEnum

from fastapi import Depends, Security
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.exceptions import AppException, ForbiddenException, UnauthorizedException


class WebhookAuthenticationError(AppException):
    """Raised when incoming webhook authentication or signature fails."""

    status_code = 401
    error_code = "WEBHOOK_AUTHENTICATION_FAILED"


class Role(StrEnum):
    """Role-based access control roles for a single-business deployment."""

    ADMIN = "admin"
    AGENT = "agent"
    VIEWER = "viewer"


class AuthenticatedUser(BaseModel):
    """Identity context of an authenticated caller."""

    id: str
    username: str
    role: Role


_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
_http_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    api_key: str | None = Security(_api_key_header),
    bearer_creds: HTTPAuthorizationCredentials | None = Security(_http_bearer),
) -> AuthenticatedUser:
    """Authenticate incoming request using either 'Authorization: Bearer <key>' or 'X-API-Key'."""
    settings = get_settings()

    token = None
    if bearer_creds and bearer_creds.credentials:
        token = bearer_creds.credentials.strip()
    elif api_key:
        token = api_key.strip()

    if not token:
        raise UnauthorizedException(
            message="Authentication required. Provide 'Authorization: Bearer <key>' or 'X-API-Key' header.",
            details={"accepted_headers": ["Authorization", "X-API-Key"]},
        )

    # Timing-safe comparison against configured role keys
    if settings.API_KEY_ADMIN and hmac.compare_digest(token, settings.API_KEY_ADMIN):
        return AuthenticatedUser(id="admin-01", username="admin", role=Role.ADMIN)

    if settings.API_KEY_AGENT and hmac.compare_digest(token, settings.API_KEY_AGENT):
        return AuthenticatedUser(id="agent-01", username="sales_agent", role=Role.AGENT)

    if settings.API_KEY_VIEWER and hmac.compare_digest(token, settings.API_KEY_VIEWER):
        return AuthenticatedUser(id="viewer-01", username="viewer", role=Role.VIEWER)

    raise UnauthorizedException(
        message="Invalid authentication credentials.",
        details={"hint": "Verify the provided API key or Bearer token"},
    )


def require_role(*allowed_roles: Role):
    """FastAPI dependency factory enforcing role-based access control."""

    def role_checker(
        current_user: AuthenticatedUser = Depends(get_current_user),
    ) -> AuthenticatedUser:
        if current_user.role not in allowed_roles:
            raise ForbiddenException(
                message=f"Access forbidden: role '{current_user.role.value}' lacks required permissions.",
                details={
                    "user_role": current_user.role.value,
                    "allowed_roles": [r.value for r in allowed_roles],
                },
            )
        return current_user

    return role_checker


# Convenience dependencies
require_admin = require_role(Role.ADMIN)
require_agent_or_admin = require_role(Role.ADMIN, Role.AGENT)
require_viewer_or_above = require_role(Role.ADMIN, Role.AGENT, Role.VIEWER)


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
