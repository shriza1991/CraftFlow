# CraftFlow

CraftFlow is a configurable backend platform for business operations and AI-assisted workflows. It provides a modular foundation for product businesses, professional services, and custom manufacturers. Each deployment serves **one** business entity configured through environment variables.

---

## Architecture & Capabilities

- **FastAPI Application**: High-performance asynchronous API layer with versioned endpoints (`/api/v1/*`), OpenAPI documentation (`/docs`), centralized exception handling, correlation ID tracking (`X-Request-ID`), and health/readiness diagnostics.
- **Relational & Vector Data Model**: PostgreSQL 16 with `pgvector` extension for products, product variants, customers, leads, conversations, messages, follow-ups, audit logs, and knowledge base document chunks with vector embeddings.
- **Alembic Migrations**: Strictly tracked schema migrations with a single merge head (`012e8b346d5b`), supporting fresh deployments and upgrades from historical branches.
- **Modular Business Identity**: Configured via environment variables (`BUSINESS_NAME`, `BUSINESS_DESCRIPTION`, `BUSINESS_INDUSTRY`) and exposed via `GET /api/v1/business`.

---

## Mock Integrations vs. Live Integrations

CraftFlow is designed with swappable provider interfaces so you can develop and test offline without external accounts or API keys, then switch to live providers in production:

| Component | Mock Implementation (Default / Offline) | Live Implementation (Production / Configurable) |
| :--- | :--- | :--- |
| **Relational Database** | In-memory SQLite supported for unit tests (`test_general_business.py`) | PostgreSQL 16 (`DATABASE_URL=postgresql+psycopg://...`) |
| **Vector Search** | Deterministic mock vector generation & similarity scoring | PostgreSQL `pgvector` extension (`VECTOR_DB_PROVIDER=pgvector`) with 1536-dim embeddings |
| **AI / LLM Provider** | `AI_PROVIDER=mock`<br>Returns simulated agent responses deterministically | `AI_PROVIDER=openai`<br>Connects to OpenAI API (`OPENAI_API_KEY`, `OPENAI_MODEL=gpt-4o-mini`) |
| **Embeddings** | `EMBEDDING_PROVIDER=mock`<br>Generates deterministic 1536-dimensional mock vectors | `EMBEDDING_PROVIDER=openai`<br>Calls `text-embedding-3-small` via OpenAI API |
| **CRM Integration** | `CRM_PROVIDER=mock`<br>In-memory customer and lead tracking | `CRM_PROVIDER=hubspot` (or webhook automation)<br>Syncs contacts with external CRM |
| **WhatsApp Messaging** | `WHATSAPP_PROVIDER=mock`<br>Simulates outbound payload generation | `WHATSAPP_PROVIDER=meta`<br>Dispatches live messages via Meta Cloud API |
| **Workflow Automation** | Local mock webhook endpoints | `N8N_BASE_URL` & `N8N_WEBHOOK_SECRET`<br>Dispatches triggers to external n8n workflows |

---

## Local Setup Guide

### Prerequisites
- Python 3.12+
- Docker and Docker Compose (recommended for PostgreSQL + pgvector)

---

### Step 1: Clone & Configure Environment

#### PowerShell (Windows):
```powershell
Copy-Item .env.example .env
```

#### Bash (macOS / Linux):
```bash
cp .env.example .env
```

Review `.env` and adjust settings as needed. By default, PostgreSQL maps host port `5435` to container port `5432` to avoid conflicts with any local PostgreSQL instance on port `5432`:
- `DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5435/ages_art_db`
- `TEST_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5435/ages_art_db_test`

---

### Step 2: Set Up Python Virtual Environment

#### PowerShell (Windows):
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

#### Bash (macOS / Linux):
```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

> **Note**: In PowerShell, always wrap `".[dev]"` in double quotes to prevent PowerShell from interpreting square brackets as glob wildcards.

---

### Step 3: Start PostgreSQL with pgvector

Use Docker Compose to start the database container:

```bash
docker compose up -d postgres
```

The Docker Compose configuration automatically provisions both the development database (`ages_art_db`) and the isolated test database (`ages_art_db_test`) with the `vector` extension enabled via `docker/init-db.sql`.

To verify the database container is healthy:
```bash
docker compose ps
```

---

### Step 4: Run Database Migrations

Apply Alembic migrations to bring the development database schema up to the latest head:

```bash
python -m alembic upgrade head
```

Verify single head status:
```bash
python -m alembic heads
```

---

### Step 5: Start the Backend Application

#### Local Development Server (Recommended):
```bash
uvicorn app.main:app --reload --app-dir backend --port 8000
```

#### Running Entire Stack with Docker:
Alternatively, you can run both backend and postgres services inside Docker:
```bash
docker compose up -d
```
The backend container uses `docker/entrypoint.sh` to run database migrations automatically before starting `uvicorn`.

#### Verify Server Health:
- Interactive Swagger UI: `http://localhost:8000/docs`
- Health check: `http://localhost:8000/api/v1/health`
- Readiness check: `http://localhost:8000/api/v1/readiness`
- Business profile: `http://localhost:8000/api/v1/business`

---

## Testing & Database Isolation

### Test Database Isolation
CraftFlow tests are designed to **never mutate or depend on development data**:
- Test configurations automatically route database connections to `TEST_DATABASE_URL` (default: `.../ages_art_db_test`), keeping `ages_art_db` completely untouched.
- Database tests execute inside isolated transaction savepoints (`join_transaction_mode="create_savepoint"`) and rollback on completion.
- If PostgreSQL is not running locally, database-dependent tests skip cleanly rather than hanging or failing. When PostgreSQL is online, all tests execute and pass.

### Running Tests

#### Run all tests:
```bash
python -m pytest backend/tests -v
```

#### Run unit tests only:
```bash
python -m pytest backend/tests/unit -v
```

#### Run integration tests only:
```bash
python -m pytest backend/tests/integration -v
```

#### Run code style and linter checks:
```bash
python -m ruff check backend
python -m ruff format --check backend
```

---

## Continuous Integration (CI)

A GitHub Actions workflow is defined in `.github/workflows/ci.yml`. It runs automatically on all pull requests and pushes targeting `main`:
1. **Lint Job**: Validates code style using `ruff check backend` and `ruff format --check backend`.
2. **Test Job**: Launches a `pgvector/pgvector:pg16` service container, verifies the single Alembic head, applies database migrations, and executes all unit and PostgreSQL/pgvector integration tests against the isolated test database. CI reports a build failure if any check or test fails.
