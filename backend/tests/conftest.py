"""Pytest shared fixtures and test configuration."""

import os
from collections.abc import AsyncGenerator, Generator

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

# Set test environment flags before importing application code
os.environ["APP_ENV"] = "test"
os.environ["AI_PROVIDER"] = "mock"
os.environ["EMBEDDING_PROVIDER"] = "mock"
os.environ["CRM_PROVIDER"] = "mock"
os.environ["WHATSAPP_PROVIDER"] = "mock"

from app.core.config import get_settings
from app.db.session import engine, get_db
from app.main import app
from sqlalchemy.orm import Session


@pytest.fixture(autouse=True)
def reset_settings_cache():
    """Clear cached settings before each test run."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """Yield a database session within an isolated savepoint transaction that rolls back after test."""
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint")

    yield session

    session.close()
    if transaction.is_active:
        transaction.rollback()
    connection.close()


@pytest.fixture
def test_client() -> Generator[TestClient, None, None]:
    """Synchronous test client for simple endpoint tests."""
    with TestClient(app=app, base_url="http://testserver") as client:
        yield client


@pytest.fixture
def client_with_db(db_session: Session) -> Generator[TestClient, None, None]:
    """TestClient that uses the transactional db_session for API calls."""
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app=app, base_url="http://testserver") as client:
        yield client
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """Asynchronous HTTPX client for testing async endpoints."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client
