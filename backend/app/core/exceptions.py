"""Centralized exception hierarchy for the application."""

from typing import Any


class AppException(Exception):
    """Base application exception with error code and HTTP status mapping."""

    status_code: int = 500
    error_code: str = "INTERNAL_SERVER_ERROR"

    def __init__(
        self,
        message: str = "An unexpected error occurred",
        details: dict[str, Any] | None = None,
        status_code: int | None = None,
        error_code: str | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.details = details or {}
        if status_code is not None:
            self.status_code = status_code
        if error_code is not None:
            self.error_code = error_code


class ValidationException(AppException):
    """Raised when incoming data fails business validation."""

    status_code = 422
    error_code = "VALIDATION_ERROR"


class NotFoundException(AppException):
    """Raised when a requested resource does not exist."""

    status_code = 404
    error_code = "NOT_FOUND"


class ExternalServiceException(AppException):
    """Raised when an external API or service call fails."""

    status_code = 502
    error_code = "EXTERNAL_SERVICE_ERROR"


class AIProviderException(AppException):
    """Raised when an AI provider fails during inference or generation."""

    status_code = 502
    error_code = "AI_PROVIDER_ERROR"


class ToolExecutionException(AppException):
    """Raised when a tool fails to execute or rejects arguments."""

    status_code = 400
    error_code = "TOOL_EXECUTION_ERROR"


class RAGException(AppException):
    """Raised when document retrieval or indexing fails."""

    status_code = 500
    error_code = "RAG_ERROR"


class CRMException(AppException):
    """Raised when CRM operations fail."""

    status_code = 502
    error_code = "CRM_ERROR"


class DatabaseException(AppException):
    """Raised when database queries or connectivity fail."""

    status_code = 503
    error_code = "DATABASE_ERROR"
