"""Unit tests for Health and Readiness probes."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_endpoint(async_client: AsyncClient):
    """Test that /api/v1/health returns 200 without requiring database connectivity."""
    response = await async_client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "ai-business-automation"
    assert "version" in data
    assert "X-Request-ID" in response.headers


@pytest.mark.asyncio
async def test_readiness_healthy(async_client: AsyncClient, monkeypatch):
    """Test /api/v1/readiness when database is available."""
    monkeypatch.setattr("app.api.v1.health.check_database_connectivity", lambda: True)

    response = await async_client.get("/api/v1/readiness")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["dependencies"]["database"] == "healthy"


@pytest.mark.asyncio
async def test_readiness_unhealthy(async_client: AsyncClient, monkeypatch):
    """Test /api/v1/readiness when database connectivity fails."""
    monkeypatch.setattr("app.api.v1.health.check_database_connectivity", lambda: False)

    response = await async_client.get("/api/v1/readiness")
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "not_ready"
    assert data["dependencies"]["database"] == "unhealthy"
