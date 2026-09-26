# Ages Art — AI-Powered Business Automation Platform

Production-ready, modular AI business automation system built for **Ages Art**, a luxury brand specializing in handmade marble bathtubs and architectural stone carving.

The platform bridges probabilistic AI reasoning (LLM agents, vector RAG search) with deterministic business logic (order processing, CRM lead management, WhatsApp communications, and human approval gates).

---

## 1. Project Purpose

High-net-worth clients, interior architects, and hospitality designers frequently inquire about custom marble bathtubs, requiring detailed answers regarding:
- Stone block origins (Carrara, Nero Marquina, Travertine, Calacatta)
- Strict weight and floor load considerations
- Custom dimensions, plumbing drains, and CAD/3D schematics
- 8–12 week artisan sculpting lead times and white-glove international freight
- Pricing, quotations, and deposit milestones

The Ages Art platform automates these multi-channel customer inquiries, qualifies sales leads, suggests matching bathtubs, and coordinates follow-ups while guaranteeing that the AI never executes unauthorized actions or directly queries databases without strict application validation.

---

## 2. Architecture & Design Principles

> **Core Invariant**: Separate deterministic business logic from probabilistic AI reasoning.

```
                    CUSTOMER
                       |
             WhatsApp / Website
                       |
                       v
                 FastAPI API
                       |
                       v
                 AI ORCHESTRATOR
                       |
          +------------+-------------+
          |            |             |
          v            v             v
     Sales Agent  Support Agent  Marketing Agent
          |            |             |
          +------------+-------------+
                       |
                       v
                   TOOL LAYER
                       |
       +---------------+----------------+
       |               |                |
       v               v                v
   Product DB         CRM           Knowledge Base (RAG)
       |               |                |
       +---------------+----------------+
                       |
                       v
                External Services (WhatsApp, Sheets, n8n)
```

- **LLM Provider Agnostic**: Swappable between OpenAI, Gemini, Anthropic, or local models via `LLMProvider`.
- **Tool Control**: Tools are strongly typed with Pydantic arguments, isolated in a centralized registry, and executed deterministically.
- **Traceability**: Every interaction carries an `X-Request-ID` correlation header tracked across logging, context variables, and external webhook triggers.

---

## 3. Project Structure

```text
CraftFlow/
├── backend/
│   ├── app/
│   │   ├── api/             # API routing & versioning (/api/v1)
│   │   │   ├── router.py
│   │   │   └── v1/health.py # Liveness & readiness probes
│   │   ├── core/            # Config, logging, exceptions, security, DI
│   │   │   ├── config.py
│   │   │   ├── logging.py
│   │   │   ├── exceptions.py
│   │   │   ├── security.py
│   │   │   └── dependencies.py
│   │   ├── db/              # SQLAlchemy 2.x session & models
│   │   │   ├── base.py
│   │   │   ├── session.py
│   │   │   └── models/
│   │   ├── schemas/         # Pydantic v2 data contracts & error responses
│   │   │   ├── common.py
│   │   │   └── health.py
│   │   ├── ai/              # LLMProvider abstraction & factory
│   │   │   ├── base.py
│   │   │   ├── factory.py
│   │   │   └── providers/   # MockLLMProvider, OpenAIProvider
│   │   ├── agents/          # BaseAgent contracts & AgentRegistry
│   │   │   ├── base.py
│   │   │   ├── registry.py
│   │   │   └── demo.py
│   │   ├── tools/           # Typed Tool abstraction & ToolRegistry
│   │   │   ├── base.py
│   │   │   ├── registry.py
│   │   │   └── demo.py
│   │   ├── rag/             # Knowledge Retriever abstraction & MockRetriever
│   │   │   ├── base.py
│   │   │   └── mock.py
│   │   ├── crm/             # CRMProvider abstraction & MockCRMProvider
│   │   │   ├── base.py
│   │   │   └── mock.py
│   │   ├── integrations/    # External clients (WhatsApp, Google, n8n)
│   │   │   ├── whatsapp/
│   │   │   ├── google/
│   │   │   └── n8n/
│   │   ├── services/        # Business logic services
│   │   └── main.py          # FastAPI application entrypoint
│   └── tests/
│       ├── conftest.py
│       ├── unit/            # Isolated unit test suites (offline)
│       └── integration/     # API & middleware integration tests
├── migrations/              # Alembic database migration environment
│   ├── alembic.ini
│   ├── env.py
│   └── versions/
├── workflows/
│   └── n8n/                 # Automation workflow specifications
├── knowledge_base/          # Markdown catalogs, policies, FAQs
│   ├── products/
│   ├── policies/
│   ├── faq/
│   └── company/
├── docs/                    # Architectural and developer documentation
│   ├── architecture.md
│   ├── agent-architecture.md
│   ├── api-contracts.md
│   └── development.md
├── docker/
│   └── Dockerfile
├── .env.example
├── docker-compose.yml
├── pyproject.toml
└── Makefile
```

---

## 4. Prerequisites

- Python 3.12+ (tested on Python 3.13)
- Docker & Docker Compose
- Git

---

## 5. Quickstart & Installation

### Step 1: Clone and Set Up Virtual Environment
```bash
git clone <repository_url>
cd CraftFlow

python -m venv .venv

# On Windows:
.venv\Scripts\activate
# On Linux/macOS:
source .venv/bin/activate
```

### Step 2: Install Dependencies
```bash
pip install --upgrade pip
pip install -e ".[dev]"
```

### Step 3: Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Default values operate in `mock` mode, requiring no third-party API keys for development and testing.

---

## 6. Docker Development Environment

Launch the PostgreSQL database (with `pgvector`) and the FastAPI backend:
```bash
docker compose up -d
```
Verify container status:
```bash
docker compose ps
```

---

## 7. Running Backend Locally

Run the development server with live reload:
```bash
uvicorn app.main:app --reload --app-dir backend --port 8000
```

Interactive API documentation:
- Swagger UI: [http://localhost:8000/docs](http://localhost:8000/docs)
- ReDoc: [http://localhost:8000/redoc](http://localhost:8000/redoc)
- OpenAPI JSON: [http://localhost:8000/openapi.json](http://localhost:8000/openapi.json)

---

## 8. API Endpoints (P0 Foundation & P1 Business Domain)

| Endpoint | Method | Purpose | Requires DB |
|---|---|---|---|
| `/api/v1/health` | GET | Liveness probe returning service and version | No |
| `/api/v1/readiness` | GET | Readiness probe checking PostgreSQL connectivity | Yes |
| `/api/v1/products` | GET, POST | List catalog products (paginated) / create product with variants | Yes |
| `/api/v1/products/{id}` | GET, PATCH | Retrieve product details / update attributes | Yes |
| `/api/v1/customers` | GET, POST | List / create customer (normalized & deduplicated) | Yes |
| `/api/v1/customers/{id}` | GET, PATCH | Retrieve / update customer profile | Yes |
| `/api/v1/leads` | GET, POST | List / create sales leads linked to products | Yes |
| `/api/v1/leads/{id}` | GET, PATCH | Retrieve lead / update status with state transitions | Yes |
| `/api/v1/conversations` | POST | Open multi-channel interaction session | Yes |
| `/api/v1/conversations/{id}` | GET | Retrieve conversation session with messages | Yes |
| `/api/v1/conversations/{id}/messages` | GET, POST | List messages chronologically / append message | Yes |
| `/api/v1/followups` | GET, POST | List scheduled follow-ups / schedule new follow-up | Yes |
| `/api/v1/followups/{id}` | PATCH | Update follow-up status (e.g. mark completed) | Yes |

---

## 9. Database Seeding & Development Fixtures

Populate the database with realistic synthetic luxury bathtub catalog, customer, lead, conversation, follow-up, agent run, and audit log data:

```bash
# Seed development database
python -m app.scripts.seed
# Or via make:
make seed

# Reset and re-seed from scratch:
python -m app.scripts.seed --reset
# Or via make:
make seed-reset
```

---

## 10. Running Tests & Quality Verification

Run the entire test suite (unit + real database integration tests):
```bash
pytest -v backend/tests
```

Run linting with Ruff:
```bash
ruff check backend
```

Validate byte compilation:
```bash
python -m compileall backend
```

---

## 11. Roadmap & Milestones

- **[x] P0 — Project Foundation & Architecture** *(Complete)*
- **[x] P1 — Business Data Foundation & Domain Model** *(Complete)*
- **[ ] P2 — Knowledge Base & pgvector RAG** (Vector ingestion & semantic search)
- **[ ] P3 — Core Agent Orchestrator** (LangGraph state machine & router)
- **[ ] P4 — WhatsApp & Omnichannel Communication** (Meta Cloud API & webhook security)
- **[ ] P5 — n8n Automation Workflows** (Visual triggers & background jobs)
- **[ ] P6 — CRM Integration & Lead Pipeline** (Bi-directional customer sync)
- **[ ] P7 — Automated Customer Follow-up Engine**
- **[ ] P8 — Product Recommendation & Visual Presentation**
- **[ ] P9 — Human-in-the-Loop & Approval Dashboard**
- **[ ] P10 — AI Marketing & Content Generation Engine**
- **[ ] P11 — Business Analytics & Executive Reporting**
- **[ ] P12 — Security Hardening, Rate Limiting & Monitoring**
- **[ ] P13 — Production Deployment & Handover**
