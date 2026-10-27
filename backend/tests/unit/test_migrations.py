"""Unit tests for Alembic migration history, single-head topology, and upgrade paths."""

import io
import socket
from contextlib import redirect_stdout
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from app.core.config import get_settings
from app.db.session import check_database_connectivity
from sqlalchemy.engine import make_url

REPO_ROOT = Path(__file__).resolve().parents[3]
ALEMBIC_INI = REPO_ROOT / "alembic.ini"
CATALOG_HEAD = "b7e2f91a4d10"
KNOWLEDGE_HEAD = "cbb711ecfc74"
MERGE_HEAD = "012e8b346d5b"
BASE_REVISION = "6a8433ba6cdb"


@pytest.fixture
def alembic_config() -> Config:
    """Fixture returning Alembic Config for the CraftFlow repository."""
    assert ALEMBIC_INI.exists(), f"alembic.ini not found at {ALEMBIC_INI}"
    return Config(str(ALEMBIC_INI))


@pytest.fixture
def script_directory(alembic_config: Config) -> ScriptDirectory:
    """Fixture returning ScriptDirectory initialized from the repository config."""
    return ScriptDirectory.from_config(alembic_config)


def test_alembic_has_exactly_one_head(script_directory: ScriptDirectory):
    """Confirm Alembic has resolved to a single merge head."""
    heads = script_directory.get_heads()
    assert len(heads) == 1, f"Expected exactly 1 Alembic head, found {len(heads)}: {heads}"
    assert heads[0] == MERGE_HEAD


def test_merge_revision_preserves_both_histories(script_directory: ScriptDirectory):
    """Verify that merge revision preserves catalog generalization and knowledge base histories."""
    head_rev = script_directory.get_revision(MERGE_HEAD)
    assert head_rev is not None, f"Merge revision {MERGE_HEAD} not found"
    assert head_rev.is_merge_point is True

    down_revs = (
        set(head_rev.down_revision)
        if isinstance(head_rev.down_revision, tuple | list)
        else {head_rev.down_revision}
    )
    assert down_revs == {CATALOG_HEAD, KNOWLEDGE_HEAD}, (
        f"Merge revision must preserve both {CATALOG_HEAD} and {KNOWLEDGE_HEAD}, got {down_revs}"
    )

    catalog_rev = script_directory.get_revision(CATALOG_HEAD)
    assert catalog_rev is not None
    assert catalog_rev.down_revision == BASE_REVISION

    kb_rev = script_directory.get_revision(KNOWLEDGE_HEAD)
    assert kb_rev is not None
    assert kb_rev.down_revision == BASE_REVISION

    base_rev = script_directory.get_revision(BASE_REVISION)
    assert base_rev is not None
    assert base_rev.down_revision is None


def test_upgrade_fresh_database_sql_path(alembic_config: Config):
    """Test upgrading a fresh database from base to head via SQL generation."""
    buf = io.StringIO()
    with redirect_stdout(buf):
        command.upgrade(alembic_config, "head", sql=True)
    sql = buf.getvalue()

    # Verify initial business domain
    assert "CREATE TABLE customers" in sql
    assert "CREATE TABLE products" in sql
    # Verify knowledge base and vector tables
    assert "CREATE EXTENSION IF NOT EXISTS vector" in sql
    assert "CREATE TABLE knowledge_sources" in sql
    assert "CREATE TABLE knowledge_documents" in sql
    assert "CREATE TABLE knowledge_chunks" in sql
    # Verify catalog generalization
    assert "ALTER TABLE products ALTER COLUMN material DROP NOT NULL" in sql
    # Verify merge head version recording
    assert MERGE_HEAD in sql


def test_upgrade_from_catalog_generalization_head_sql_path(alembic_config: Config):
    """Test upgrading an existing database already at the catalog generalization head."""
    buf = io.StringIO()
    with redirect_stdout(buf):
        command.upgrade(alembic_config, f"{CATALOG_HEAD}:head", sql=True)
    sql = buf.getvalue()

    # The upgrade must apply the missing knowledge base branch and merge
    assert "CREATE EXTENSION IF NOT EXISTS vector" in sql
    assert "CREATE TABLE knowledge_sources" in sql
    assert "CREATE TABLE knowledge_documents" in sql
    assert "CREATE TABLE knowledge_chunks" in sql
    assert MERGE_HEAD in sql


def test_upgrade_from_knowledge_base_head_sql_path(alembic_config: Config):
    """Test upgrading an existing database already at the knowledge base head."""
    buf = io.StringIO()
    with redirect_stdout(buf):
        command.upgrade(alembic_config, f"{KNOWLEDGE_HEAD}:head", sql=True)
    sql = buf.getvalue()

    # The upgrade must apply the missing catalog generalization branch and merge
    assert "ALTER TABLE products ALTER COLUMN material DROP NOT NULL" in sql
    assert MERGE_HEAD in sql


def test_live_database_upgrade(alembic_config: Config):
    """Attempt live database upgrade if reachable; clearly record if untested due to environment."""
    settings = get_settings()
    db_url = make_url(settings.DATABASE_URL)
    host = db_url.host or "localhost"
    port = db_url.port or 5432

    # Fast probe to see if port is open before attempting SQLAlchemy connection
    try:
        with socket.create_connection((host, port), timeout=0.5):
            pass
    except (OSError, TimeoutError) as exc:
        pytest.skip(
            f"Live database upgrade check could not run: cannot connect to {host}:{port} ({exc}). "
            "PostgreSQL service or container is offline. Offline SQL migration and graph paths verified."
        )

    if not check_database_connectivity():
        pytest.skip(
            f"Live database upgrade check could not run: authentication or database connection failed on {host}:{port}. "
            "Offline SQL migration and graph paths verified."
        )

    # If DB is online and healthy, perform live migration upgrade to head
    command.upgrade(alembic_config, "head")
