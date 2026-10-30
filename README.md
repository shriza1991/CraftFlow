# CraftFlow

CraftFlow is a configurable backend platform for business operations and AI-assisted workflows. It provides a modular foundation for product businesses, professional services, and custom manufacturers. Each deployment serves **one** business entity configured through environment variables.

---

## Architecture & Capabilities

- **FastAPI Application**: High-performance asynchronous API layer with versioned endpoints (`/api/v1/*`), OpenAPI documentation (`/docs`), centralized exception handling, correlation ID tracking (`X-Request-ID`), and health/readiness diagnostics.
- **Relational & Vector Data Model**: PostgreSQL 16 with `pgvector` extension for products, product variants, customers, leads, conversations, messages, follow-ups, audit logs, and knowledge base document chunks with vector embeddings.
- **Alembic Migrations**: Strictly tracked schema migrations with a single merge head (`d71a9e84b2c1`), supporting fresh deployments and upgrades from historical branches.
- **Modular Business Identity**: Configured via environment variables (`BUSINESS_NAME`, `BUSINESS_DESCRIPTION`, `BUSINESS_INDUSTRY`) and exposed via `GET /api/v1/business`.
- **General Grounded RAG & Semantic Search**: Parameterized retrieval and question-answering conditioned strictly on business knowledge context, supporting full document provenance, explicit refusal on unsupported questions, and zero hardcoded product bias.
- **End-to-End Inquiry Workflow & Human Approval**: Deterministic 7-step pipeline accepting customer inquiries, retrieving grounded business knowledge and catalog items, drafting structured responses with traceable citations, creating or updating CRM leads, enforcing human-in-the-loop review before outbound dispatch, and logging telemetry and audit trails.
- **n8n Integration & Follow-up Orchestration**: Narrow automation boundary with version-controlled n8n workflow export (`workflows/n8n/follow_up_execution_workflow.json`). The backend remains strictly responsible for business rules, human approval state, and delivery records, supporting authenticated webhooks, event identifiers, duplicate protection, bounded retries, and visible delivery status.
- **Role-Based Access Control (RBAC)**: Tiered access for single-business deployments (`admin`, `agent`, `viewer`) using API keys via `Authorization: Bearer <key>` or `X-API-Key: <key>`.
- **Business Invariants & Audit Trail**: Cross-record integrity enforcement (lead customer ownership, product variant validation, duplicate submission rejection) and automated append-only mutation audit logging.

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
| **Workflow Automation** | `N8N_DISPATCH_MODE=mock`<br>Simulated n8n dispatch without external network calls | `N8N_DISPATCH_MODE=live`<br>Dispatches authenticated webhooks to `N8N_BASE_URL` with retry endpoint |

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

### Step 6: Ingest Business Knowledge (Configurable)

CraftFlow ingests markdown documents from a configurable folder into pgvector. By default, the `knowledge_base/` directory is empty so that a new deployment does not inherit another business's documents by default.

To ingest one of the pre-packaged example businesses:

#### Example A: Ages Art (Luxury Marble Bathtubs & Stone Craftsmanship)
```powershell
# Copy Ages Art environment configuration:
Copy-Item examples/ages-art.env .env

# Ingest Ages Art knowledge documents into PostgreSQL + pgvector:
python -m app.scripts.ingest_knowledge --dir examples/knowledge/ages-art --business-name "Ages Art"
```

#### Example B: Northstar Design Studio (Interior Architecture & Consulting Services)
```powershell
# Copy Northstar Design Studio environment configuration:
Copy-Item examples/design-studio.env .env

# Ingest Northstar Design Studio knowledge documents into PostgreSQL + pgvector:
python -m app.scripts.ingest_knowledge --dir examples/knowledge/design-studio --business-name "Northstar Design Studio"
```

---

## Knowledge Base & Grounded RAG Architecture

CraftFlow's Retrieval-Augmented Generation (RAG) and semantic search layer is generalized to serve any single configurable business per deployment:

### 1. Zero Hardcoded Bias
- The RAG system prompt (`build_grounded_system_prompt()`) dynamically parameterizes the business identity (`BUSINESS_NAME`, `BUSINESS_DESCRIPTION`) rather than assuming a specific product catalog (e.g. marble bathtubs).
- Ingestion folder mapping (`get_folder_config()`) dynamically generates source names (e.g. `"<Business> Product Catalog"`, `"<Business> Service Catalog"`, `"<Business> FAQ"`, `"<Business> Business Policies"`).

### 2. Traceable Document Provenance
All semantic search results (`POST /api/v1/knowledge/search`) and RAG response citations (`POST /api/v1/knowledge/query`) include structured, traceable provenance:
- `source_name`: Human-readable name of the knowledge source (e.g. "Northstar Design Studio Service Catalog")
- `source_id`: UUID identifying the originating knowledge source
- `document_id`: UUID identifying the parent document
- `chunk_id`: UUID of the specific text chunk
- `chunk_index`: Position of the chunk in the source document
- `title`: Markdown document heading / title
- `score`: Cosine similarity score
- `metadata`: Source file path, SKU tags, and category metadata

### 3. Grounding Semantics & Verification Disclaimers
- **Meaning of `grounded=True`**: `grounded=True` signifies that the answer was synthesized strictly conditioned on retrieved context snippets from the knowledge base rather than general model priors. It does **not** assert or imply that the factual claims have been independently or externally verified by humans or external fact-checkers.
- **Handling Missing & Unsupported Questions**: When an unsupported question is submitted:
  - If 0 chunks exceed the similarity threshold, the RAG service returns an explicit refusal message: `"No sufficiently relevant business knowledge was found to answer this question."` with `grounded=False` and `sources=[]`.
  - If chunks are retrieved but lack the required information, the prompt instructs the model to refuse: `"The available business knowledge does not contain enough information to answer this question."` The service detects this insufficient-evidence response and sets `grounded=False` with `sources=[]`.

### 4. Deployment Knowledge Isolation
- The default `knowledge_base/` directory contains only a README; neither example business's knowledge files are loaded unless explicitly configured via `KNOWLEDGE_BASE_DIR` in `.env` or `--dir` in `ingest_knowledge.py`.
- Both example knowledge sets (`examples/knowledge/ages-art` and `examples/knowledge/design-studio`) are preserved independently and validated via unit tests.

---

## Access Control, Business Invariants & Audit Trail

CraftFlow includes robust access control, relationship validation, and audit recording across all core APIs:

### 1. Authentication & Role-Based Access Control (RBAC)
All domain endpoints (`/api/v1/products`, `/api/v1/customers`, `/api/v1/leads`, `/api/v1/followups`, `/api/v1/conversations`) require authentication via:
- `Authorization: Bearer <API_KEY>` or
- `X-API-Key: <API_KEY>`

Three roles are supported for single-business deployments:
- **`admin`** (`API_KEY_ADMIN`): Full access to create, update, and read all entities.
- **`agent`** (`API_KEY_AGENT`): Front-office sales & support access. Can create/update customers, leads, follow-ups, and messages; read-only access to products.
- **`viewer`** (`API_KEY_VIEWER`): Read-only reporting access. All mutation endpoints return HTTP 403 `FORBIDDEN`.

Unauthenticated callers receive HTTP 401 `UNAUTHORIZED`.

### 2. Business Invariants & Cross-Record Validation
- **Follow-up Ownership**: Verifies that the follow-up's `customer_id` owns the referenced `lead_id` (`lead.customer_id == followup.customer_id`). If `conversation_id` is passed, it must belong to the same customer. Mismatches are rejected with HTTP 422.
- **Product Variant Belonging**: Verifies that any selected product variant in a lead item belongs to that specific product (`variant.product_id == prod_item.product_id`). Cross-product variant references are rejected with HTTP 422.

### 3. Duplicate Prevention & Transaction Boundaries
- **Concurrent & Duplicate Products**: Enforces SKU and slug uniqueness. Collisions trigger database rollback and return HTTP 422. Product variant SKU suffixes must also be unique within a product.
- **Customer Collisions**: Normalized email, phone, and WhatsApp collisions on create or update are rejected with HTTP 422 and transaction rollback.
- **Duplicate Leads & Follow-ups**: Identical active inquiry leads and duplicate pending follow-ups scheduled at the same timestamp are rejected with HTTP 422.

### 4. Mutation Audit Trail
Every product, customer, lead, and follow-up create or update logs an append-only audit record in `audit_logs`:
- Caller identification (`actor_id`, `actor_type`: `HUMAN` or `AGENT`)
- Action performed (`CREATE`, `UPDATE`)
- Affected resource (`resource_type`, `resource_id`)
- Contextual state snapshots (`before_state`, `after_state`)

---

## End-to-End Customer Inquiry Workflow & Human Approval Gate

CraftFlow implements a complete, deterministic inquiry lifecycle that ingests customer messages, synthesizes evidence-grounded drafts, updates CRM records, and halts outbound dispatch pending human authorization.

```
[Inbound Inquiry]
        │
        ▼
1. Customer Intake  ──► Upsert Customer profile (email/phone normalization)
        │
        ▼
2. Conversation Intake ──► Register inbound Message on channel (WEBSITE/WHATSAPP)
        │
        ▼
3. Knowledge Retrieval ──► Cosine vector search in pgvector (similarity threshold >= 0.70)
        │
        ▼
4. Catalog Search      ──► Parameterized SQL search on active products & variants
        │
        ▼
5. Response Drafting   ──► Advisory LLM synthesizes draft conditioned on evidence;
        │                  Draft Message created with status="DRAFT", grounded=True/False
        ▼
6. Lead Management     ──► Upsert qualified CRM Lead (status="NEW", priority, channel)
        │
        ▼
7. Outbound Dispatch   ──► HALT: outbound_message_sent=False, approval_status="PENDING_APPROVAL"
                                    │
               ┌────────────────────┴────────────────────┐
               ▼                                         ▼
   POST .../approve (Human Agent)             POST .../reject (Human Agent)
   - Mark message status="SENT"               - Mark approval_status="REJECTED"
   - Dispatch to WhatsApp / Channel           - outbound_message_sent=False
   - Transition lead to "CONTACTED"           - Audit log recorded
   - Audit log recorded
```

### 1. Mandatory Human Approval Gate
- **No Unapproved Outbound Messages**: The draft response is stored in the database with `status="DRAFT"`, and the workflow sets `outbound_message_sent=False` and `approval_status="PENDING_APPROVAL"`. Under no circumstances is an outbound message dispatched automatically.
- **Review & Edit Capability**: An authorized agent or admin can review the draft, inspect citations, and optionally provide an edited message body when approving (`POST /api/v1/inquiries/{run_id}/approve`).
- **Decline & Rejection**: Calling `POST /api/v1/inquiries/{run_id}/reject` marks the run and draft `REJECTED`, blocks dispatch, and documents the reviewer's rationale in the audit trail.

### 2. Evidence Grounding & Traceable Citations
Draft responses link directly to their source evidence:
- **Knowledge Base Citations**: Document title, source name, chunk UUID, and cosine similarity score.
- **Catalog Citations**: Live product SKU, product name, material, base price, and production lead times.
- If information is missing from the knowledge base, the model generates an explicit refusal rather than fabricating answers.

### 3. Clear State & Failure Visibility
Each step produces an isolated `WorkflowStepResult` with execution status, timing, and diagnostic details:
- **`COMPLETED`**: All steps succeeded; draft response is ready for human review (`approval_status="PENDING_APPROVAL"`).
- **`NEEDS_REVIEW`**: Unsupported questions or insufficient knowledge (0 matching chunks). Generates an explicit insufficient-evidence response (`grounded=False`, `citations=[]`) while preserving the customer and lead in the CRM for human sales follow-up.
- **`FAILED`**: External provider timeouts, AI errors, or downstream failures. Halts the pipeline, records the failing step and error message in `AgentRun` telemetry, and guarantees that no outbound message is sent.

### 4. SQL & Domain Invariant Safety
- **No Arbitrary SQL Execution**: The advisory LLM has no database access, execution permissions, or raw SQL capabilities.
- **Strict Service Boundaries**: All CRM and catalog updates execute through validated backend services (`CustomerService`, `LeadService`, `ProductService`, `KnowledgeService`) using parameterized queries and enforcing relational domain invariants.

### 5. Reproducible Demo (Mock Providers)
CraftFlow includes a standalone demo script exercising the entire workflow across three key scenarios without requiring external API keys:

```powershell
# PowerShell (Windows):
.\.venv\Scripts\python.exe backend/app/scripts/demo_inquiry.py

# Bash (macOS / Linux):
python backend/app/scripts/demo_inquiry.py
```

The script demonstrates:
1. **Scenario 1 (Valid Inquiry)**: Customer intake, vector knowledge retrieval, catalog search, grounded draft creation with citations, lead generation, and human review approval followed by simulated dispatch.
2. **Scenario 2 (Unsupported Inquiry)**: Zero knowledge matches, producing a clean `NEEDS_REVIEW` state, `grounded=False`, and zero hallucinations, while maintaining the CRM lead for manual follow-up.
3. **Scenario 3 (Provider Failure)**: Simulated AI provider timeout, capturing step-level failure in `response_drafting`, setting `status="FAILED"`, and showing diagnostics without sending any message.

---

## n8n Follow-up Automation & Delivery Contract

CraftFlow provides a contract-backed backend integration for follow-up automations designed for manual workflow construction in [n8n](https://n8n.io). The backend remains strictly responsible for business invariants, human approval state, scheduling verification, and delivery attempt records.

### 1. Narrow Automation Boundary & Reference Export
- **Backend Responsibility**: The FastAPI backend enforces whether a follow-up is eligible for delivery (must be `approval_status="APPROVED"` and not `CANCELLED`), prevents premature execution (`NOT_DUE`), manages database-backed attempt uniqueness and row locking, records all delivery attempts, and appends messages to conversation history.
- **n8n Responsibility**: n8n coordinates waiting until `scheduled_at`, triggers the webhook relay, and manages retry backoff loops.
- **Reference Workflow Export**: An initial reference export is stored in [`workflows/n8n/follow_up_execution_workflow.json`](./workflows/n8n/follow_up_execution_workflow.json) for reference and alignment. Complete setup, environment variables, and manual construction instructions are documented in [`workflows/n8n/README.md`](./workflows/n8n/README.md).

### 2. Configurable Dispatch & Safe Retries
- **Dispatch Modes**: Configured via `N8N_DISPATCH_MODE` (`mock` by default for safe offline development, or `live` to send authenticated HTTP requests to `N8N_BASE_URL`).
- **Dispatch Observability**: Real dispatch outcomes are saved directly on the follow-up: `n8n_dispatch_status` (`DISPATCHED` or `FAILED`), `n8n_dispatched_at`, and `n8n_dispatch_error`.
- **Safe Dispatch Retry**: An approved follow-up whose dispatch failed can be retried safely via `POST /api/v1/followups/{id}/retry-dispatch`, which reuses the existing `delivery_id` without creating duplicate logical deliveries.

### 3. Scheduling & Timezone Invariants
- **Explicit Timezones**: `scheduled_at` strictly requires an explicit timezone offset (e.g. `2026-11-05T14:30:00Z` or `+05:30`); ambiguous timezone-naive inputs are rejected with HTTP 422. Comparisons are normalized to UTC.
- **Early Execution Guard (`NOT_DUE`)**: Calling the execution webhook before `scheduled_at` returns `status="NOT_DUE"` with `next_eligible_at`. No attempt is consumed and no attempt counter is incremented.
- **Rescheduling Invalidation (`STALE_SCHEDULE`)**: Rescheduling increments `schedule_version` and generates a fresh `delivery_id`. Outdated queued executions return `status="STALE_SCHEDULE"`.

### 4. Idempotency, Retries, and Concurrency Contract
- **Stable Delivery ID vs. Attempt ID**: `delivery_id` is stable across all attempts of a scheduled delivery cycle, while `attempt_id` is unique to each individual attempt.
- **Database-Backed Uniqueness & Concurrency**: Table `follow_up_delivery_attempts` enforces uniqueness on `attempt_id` and `(delivery_id, attempt)`. Atomic execution claims with PostgreSQL `SELECT ... FOR UPDATE` row locks prevent concurrent duplicate execution.
- **Idempotent Replay (`DUPLICATE_REPLAY`)**: Replaying the same `attempt_id` returns the recorded outcome with `status="DUPLICATE_REPLAY"` and `duplicate=true` without re-sending messages.
- **Bounded Retries**: Transient failures return `status="RETRYING"` with `retryable=true` until `attempt >= max_retries` (default: 3), after which the follow-up transitions to `status="FAILED"` with `retryable=false`.

### 5. Visible Delivery Status in CRM
The complete delivery history is visible at all times via `GET /api/v1/followups/{id}/delivery`:
- `delivery_status`: `PENDING`, `DELIVERED`, `RETRYING`, `FAILED`, or `CANCELLED`.
- `delivery_attempts`: Total attempts executed.
- `delivery_records`: Chronological list of all attempts with timestamp, provider message ID, recipient, error details, and retry eligibility.

### 6. Mock vs. Live Messaging Setup
- **Mock Provider (Default / Offline)**: `WHATSAPP_PROVIDER=mock` simulates instant delivery with mock IDs (`mock_wamid_<hash>`) and supports deterministic error injection for testing.
- **Live Provider (Production)**: Configure `WHATSAPP_PROVIDER=meta` with `WHATSAPP_ACCESS_TOKEN` and `WHATSAPP_PHONE_NUMBER_ID` in `.env`. Full setup instructions are documented in [`workflows/n8n/README.md`](./workflows/n8n/README.md). Enabling real n8n dispatch (`N8N_DISPATCH_MODE=live`) does not affect message mocking.

### 7. Running the n8n Follow-up Demo

Test the complete lifecycle offline without external accounts or services:

```powershell
# PowerShell (Windows):
.\.venv\Scripts\python.exe backend/app/scripts/demo_n8n_followup.py

# Bash (macOS / Linux):
python backend/app/scripts/demo_n8n_followup.py
```

The demo demonstrates:
1. Approved follow-up moving through n8n automation and mock delivery.
2. Repeated event ID duplicate protection (no duplicate sends).
3. Cancelled follow-up delivery rejection.
4. Transient delivery failure, retry progression, and bounded failure exhaustion (max 3 retries).
5. Unapproved follow-up protection (enforcing backend approval gate).

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
