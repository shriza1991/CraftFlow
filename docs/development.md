# Development Guide — Ages Art AI Automation

## 1. Prerequisites

- Python 3.12+ (Python 3.13 supported)
- Docker & Docker Compose
- Make (optional, but convenient)

---

## 2. Local Setup

### 2.1 Clone and Environment Setup
```bash
# Clone the repository
git clone <repo-url>
cd CraftFlow

# Create virtual environment
python -m venv .venv

# Activate virtual environment
# Windows (PowerShell):
.venv\Scripts\Activate.ps1
# Linux / macOS:
source .venv/bin/activate

# Install dependencies in editable mode
pip install -e ".[dev]"
```

### 2.2 Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

---

## 3. Running Services with Docker

Start PostgreSQL with pgvector and the backend:
```bash
docker compose up -d
```
Check status:
```bash
docker compose ps
docker compose logs -f backend
```

---

## 4. Running Backend Locally

If running PostgreSQL via Docker and backend directly:
```bash
uvicorn app.main:app --reload --app-dir backend --port 8000
```
Open interactive Swagger documentation:
- URL: `http://localhost:8000/docs`
- Health check: `http://localhost:8000/api/v1/health`
- Readiness check: `http://localhost:8000/api/v1/readiness`

---

## 5. Running Tests & Quality Checks

```bash
# Run pytest test suite
pytest -v backend/tests

# Run Ruff linter
ruff check backend

# Verify compilation
python -m compileall backend
```

---

## 6. Database Migrations

Generate a new migration:
```bash
alembic revision --autogenerate -m "create_initial_schema"
```

Apply migrations:
```bash
alembic upgrade head
```

Rollback one migration:
```bash
alembic downgrade -1
```

---

## 7. Database Seeding

Populate the database with realistic synthetic luxury bathtub catalog, customer, lead, conversation, follow-up, agent run, and audit log data:

```bash
# Run seed script (idempotent; halts if data exists)
python -m app.scripts.seed
# Or via make:
make seed

# Reset / re-seed from scratch:
python -m app.scripts.seed --reset
# Or via make:
make seed-reset
```

