"""Common API response and error schemas."""

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field

DataT = TypeVar("DataT")


class ErrorDetail(BaseModel):
    """Detailed error object matching structured API contract."""

    code: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable error description")
    request_id: str = Field(..., description="Correlation request ID")
    details: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional contextual metadata or field validation errors",
    )


class ErrorResponse(BaseModel):
    """Standard error response payload."""

    error: ErrorDetail


class APIResponse(BaseModel, Generic[DataT]):
    """Standard successful API response envelope."""

    status: str = Field(default="success", description="Response status (success/error)")
    data: DataT = Field(..., description="Payload data")
    request_id: str | None = Field(default=None, description="Correlation request ID")
