"""Unit tests for centralized exception handling and error response formatting."""

import pytest
from app.core.exceptions import (
    AppException,
    CRMException,
    NotFoundException,
    ValidationException,
)
from httpx import AsyncClient


def test_exception_hierarchy():
    """Verify application exception inheritance and HTTP status code defaults."""
    val_err = ValidationException("Invalid dimensions specified")
    assert val_err.status_code == 422
    assert val_err.error_code == "VALIDATION_ERROR"
    assert isinstance(val_err, AppException)

    not_found = NotFoundException("Product not found")
    assert not_found.status_code == 404
    assert not_found.error_code == "NOT_FOUND"

    crm_err = CRMException("CRM rate limit exceeded")
    assert crm_err.status_code == 502
    assert crm_err.error_code == "CRM_ERROR"


@pytest.mark.asyncio
async def test_not_found_error_response(async_client: AsyncClient):
    """Verify non-existent routes return structured ErrorResponse instead of generic 404."""
    response = await async_client.get("/api/v1/non_existent_route")
    assert response.status_code == 404
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "NOT_FOUND"
    assert "request_id" in data["error"]
