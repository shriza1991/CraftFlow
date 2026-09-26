"""Pytest shared fixtures and test configuration."""

import os
from collections.abc import AsyncGenerator, Generator

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

# Set test environment flags before importing application code
os.environ["APP_ENV"] = "test"
os.environ["AI_PROVIDER"] = "mock"
os.environ["CRM_PROVIDER"] = "mock"
os.environ["WHATSAPP_PROVIDER"] = "mock"

from app.core.config import get_settings
from app.main import app


@pytest.fixture(autouse=True)
def reset_settings_cache():
    """Clear cached settings before each test run."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def test_client() -> Generator[TestClient, None, None]:
    """Synchronous test client for simple endpoint tests."""
    with TestClient(app=app, base_url="http://testserver") as client:
        yield client


@pytest.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """Asynchronous HTTPX client for testing async endpoints."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client
