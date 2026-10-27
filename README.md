# CraftFlow

CraftFlow is an early-stage backend for business operations and AI-assisted workflows. It can be configured for a product business, a professional service, or a custom manufacturer. Each deployment currently serves **one** business; there is no tenant isolation or multi-business hosting yet.

## Implemented foundation

- FastAPI APIs for products and services, customers, leads, conversations, messages, and follow-ups.
- SQLAlchemy models, PostgreSQL migrations, validation, audit records, pagination, and business state checks.
- Deployment-specific business identity via environment variables, exposed at `GET /api/v1/business`.
- AI provider and agent/tool interfaces, plus a simple demo agent. The search tool and retriever are mocks with no default business facts; they are not connected to the persisted catalog or a vector index.
- Integration clients and scaffolding for WhatsApp, Google, and n8n. Automated follow-up delivery, real retrieval, agent orchestration, approval workflows, and external integrations are future work.

The original Ages Art sample data is retained in `backend/app/scripts/seed.py` as an optional example. It is not loaded automatically and does not define the platform's scope.

## Configure a business

Copy `.env.example` to `.env` and set `BUSINESS_NAME`, `BUSINESS_DESCRIPTION`, and `BUSINESS_INDUSTRY`. These are public, non-secret values and are used in the demo agent's system context and business endpoint. `examples/ages-art.env` and `examples/design-studio.env` illustrate two separate deployments. Restart the application after changing environment configuration.

`examples/catalog.json` contains example API payloads for a service and a manufactured product. Create them individually with `POST /api/v1/products`. Material and physical dimensions are optional; use `metadata` for domain-specific attributes. Set availability, lead time, currency, and customization explicitly to suit the business.

## Run locally

Requires Python 3.12+, PostgreSQL, and optionally Docker Compose.

```bash
cp .env.example .env
pip install -e '.[dev]'
docker compose up -d
python -m alembic upgrade head
uvicorn app.main:app --reload --app-dir backend --port 8000
```

Alternatively run the backend outside Docker against the PostgreSQL instance. The Compose backend and local uvicorn both listen on port 8000; use one at a time. API docs are available at `/docs` in development.

For an existing Ages Art database, run `python -m alembic upgrade head`: the new migration permits catalog items without a material and leaves existing rows intact. Before downgrading, explicitly backfill any items with null materials; the old constraint cannot store them.

## Test

```bash
python -m pytest backend/tests/unit --ignore=backend/tests/unit/test_domain_models.py
python -m pytest backend/tests/integration
```

Existing database integration tests require a reachable PostgreSQL database configured by `DATABASE_URL`; they create records in an isolated transaction. Mock integrations do not contact providers.

## Next steps

Implement an actual inquiry-to-follow-up flow, production retrieval, authenticated and authorized APIs, durable jobs and idempotent webhook delivery, human approvals, and measured end-to-end evaluation. Multi-tenant hosting would additionally require tenant-scoped data, credentials, access control, jobs, and retrieval; changing the business name alone does not provide isolation.
