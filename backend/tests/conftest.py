"""Pytest shared fixtures and test configuration."""

import os
import socket
from collections.abc import AsyncGenerator, Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

# 1. Set test environment flags before importing application code
os.environ["APP_ENV"] = "test"
os.environ["APP_NAME"] = "CraftFlow"
os.environ["AI_PROVIDER"] = "mock"
os.environ["EMBEDDING_PROVIDER"] = "mock"
os.environ["CRM_PROVIDER"] = "mock"
os.environ["WHATSAPP_PROVIDER"] = "mock"

# 2. Configure isolated test database URL to prevent mutating development data
from app.core.config import Settings, get_settings  # noqa: E402

_raw_settings = Settings()
test_db_url = _raw_settings.effective_test_database_url
os.environ["DATABASE_URL"] = test_db_url
get_settings.cache_clear()

from app.db.session import engine, get_db  # noqa: E402
from app.main import app  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

_db_initialized = False


def check_postgres_reachable(url_str: str, timeout: float = 0.5) -> bool:
    """Fast socket check whether PostgreSQL host and port accept connections."""
    try:
        from sqlalchemy.engine import make_url

        parsed = make_url(url_str)
        host = parsed.host or "localhost"
        port = parsed.port or 5432
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (OSError, TimeoutError):
        return False


@pytest.fixture(scope="session")
def setup_test_database() -> bool:
    """Ensure isolated test database exists and migrations are applied once per test session."""
    global _db_initialized
    if _db_initialized:
        return True

    settings = get_settings()
    if not check_postgres_reachable(settings.DATABASE_URL, timeout=0.5):
        return False

    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import make_url

    url = make_url(settings.DATABASE_URL)
    maint_url = url.set(database="postgres")
    try:
        maint_engine = create_engine(maint_url, isolation_level="AUTOCOMMIT")
        with maint_engine.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :dbname"),
                {"dbname": url.database},
            ).scalar()
            if not exists:
                conn.execute(text(f'CREATE DATABASE "{url.database}"'))
        maint_engine.dispose()
    except Exception:
        pass

    try:
        test_engine = create_engine(settings.DATABASE_URL, isolation_level="AUTOCOMMIT")
        with test_engine.connect() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        test_engine.dispose()

        alembic_ini = Path(__file__).resolve().parents[2] / "alembic.ini"
        if alembic_ini.exists():
            cfg = Config(str(alembic_ini))
            cfg.set_main_option("sqlalchemy.url", settings.DATABASE_URL)
            command.upgrade(cfg, "head")

        _db_initialized = True
        return True
    except Exception:
        return False


@pytest.fixture(autouse=True)
def reset_settings_cache():
    """Clear cached settings before each test run."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def db_session(setup_test_database: bool) -> Generator[Session, None, None]:
    """Yield a database session within an isolated savepoint transaction that rolls back after test."""
    if not setup_test_database:
        pytest.skip(
            "PostgreSQL test database is unavailable/not reachable. "
            "Run 'docker compose up -d' or set TEST_DATABASE_URL to run database tests."
        )

    connection = engine.connect()
    transaction = connection.begin()
    session = Session(
        bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
    )

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
