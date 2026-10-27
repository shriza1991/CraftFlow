"""Integration tests for API v1 middleware and routing."""

import pytest
from app.agents.registry import get_agent_registry
from app.tools.registry import get_tool_registry
from fastapi.testclient import TestClient
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_request_id_correlation_preserved(async_client: AsyncClient):
    """Verify that caller-supplied X-Request-ID header is preserved and returned."""
    custom_req_id = "test-custom-correlation-12345"
    response = await async_client.get(
        "/api/v1/health",
        headers={"X-Request-ID": custom_req_id},
    )
    assert response.status_code == 200
    assert response.headers.get("X-Request-ID") == custom_req_id


@pytest.mark.asyncio
async def test_openapi_schema_generated(async_client: AsyncClient):
    """Verify OpenAPI JSON specification is generated correctly with knowledge and business routes."""
    response = await async_client.get("/openapi.json")
    assert response.status_code == 200
    data = response.json()
    assert data["info"]["title"] in ["Ages Art AI Business Automation", "CraftFlow"]
    assert "/api/v1/health" in data["paths"]
    assert "/api/v1/readiness" in data["paths"]
    assert "/api/v1/business" in data["paths"]
    assert "/api/v1/knowledge/sources" in data["paths"]
    assert "/api/v1/knowledge/documents" in data["paths"]
    assert "/api/v1/knowledge/search" in data["paths"]
    assert "/api/v1/knowledge/query" in data["paths"]


@pytest.mark.asyncio
async def test_business_endpoint(async_client: AsyncClient):
    """Verify public business endpoint returns business profile."""
    response = await async_client.get("/api/v1/business")
    assert response.status_code == 200
    payload = response.json()
    assert "name" in payload
    assert "description" in payload
    assert "industry" in payload


def test_lifespan_registry_initialization(test_client: TestClient):
    """Verify that startup lifespan registered default tools and demo agent."""
    tool_reg = get_tool_registry()
    agent_reg = get_agent_registry()

    assert "search_products" in [t.name for t in tool_reg.list()]
    assert "health_check" in [t.name for t in tool_reg.list()]
    assert "demo_agent" in [a.name for a in agent_reg.list()]
