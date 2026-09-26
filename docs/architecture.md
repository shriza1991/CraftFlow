# Ages Art AI Business Automation — System Architecture

## 1. Executive Summary & Design Philosophy

The Ages Art platform automates high-touch luxury customer inquiries, sales lead qualification, and business workflows for handmade marble bathtubs and stone art.

The core architectural invariant of this system is:
> **Strict separation of deterministic business logic from probabilistic AI reasoning.**

The Large Language Model (LLM) is treated as a reasoning engine, not an execution engine. It is never granted direct access to databases, financial systems, or unvetted external APIs. Instead, it interprets user intent, formulates structured tool requests, and receives verified facts executed by the application layer.

---

## 2. Layered Architecture

```
                    ┌─────────────────────────────────────────┐
                    │            API Gateway / Web            │
                    │   FastAPI (REST, Webhooks, Docs)        │
                    └────────────────────┬────────────────────┘
                                         │
                    ┌────────────────────▼────────────────────┐
                    │             Service Layer               │
                    │   Validation, Security, Lifespan        │
                    └────────────────────┬────────────────────┘
                                         │
        ┌────────────────────────────────┼────────────────────────────────┐
        │                                │                                │
        ▼                                ▼                                ▼
┌───────────────┐              ┌───────────────────┐            ┌───────────────────┐
│   AI Layer    │              │    Agent Layer    │            │     RAG Layer     │
│ Providers &   │◄─────────────┤ Multi-Agent State │───────────►│ Hybrid Search,    │
│ LLM Factory   │              │ Orchestrator      │            │ Vector Embeddings │
└───────────────┘              └─────────┬─────────┘            └───────────────────┘
                                         │
                               ┌─────────▼─────────┐
                               │    Tool Layer     │
                               │  Typed Registries │
                               └─────────┬─────────┘
                                         │
        ┌────────────────────────────────┼────────────────────────────────┐
        ▼                                ▼                                ▼
┌───────────────┐              ┌───────────────────┐            ┌───────────────────┐
│   Database    │              │        CRM        │            │  External APIs    │
│ PostgreSQL +  │              │ Lead Pipeline &   │            │ WhatsApp, Sheets, │
│ pgvector      │              │ Customer History  │            │ n8n Automation    │
└───────────────┘              └───────────────────┘            └───────────────────┘
```

### 2.1 API Layer (`app/api`)
- Exposes versioned endpoints (`/api/v1/`).
- Enforces request correlation (`X-Request-ID`), structured logging, and centralized exception handling.
- Validates all incoming payloads using Pydantic v2 schemas before passing them into inner layers.

### 2.2 Service Layer (`app/services`)
- Orchestrates multi-step business transactions.
- Applies authorization, safety boundaries, rate limiting, and business validation rules.

### 2.3 AI Layer (`app/ai`)
- Encapsulates LLM interactions behind the `LLMProvider` abstract contract.
- Houses provider implementations (`MockLLMProvider`, `OpenAIProvider`, and future Anthropic/Gemini/local adapters).
- **Why this abstraction exists**: It decouples reasoning provider selection from application and agent code. Swapping OpenAI for Gemini or a local model requires zero agent rewrites, and tests run offline without network or token costs.

### 2.4 Agent Layer (`app/agents`)
- Coordinates conversational workflows and intent routing.
- Prepares for LangGraph multi-agent orchestration (Sales, Support, Marketing, Analytics).
- Consumes tools via typed interfaces, preventing direct API coupling.

### 2.5 Tool Layer (`app/tools`)
- Every tool is a typed class implementing `Tool` and registered in `ToolRegistry`.
- Enforces strict input validation via Pydantic argument schemas.
- Converts to OpenAI function calling definitions automatically.
- **Why tools are isolated**: An agent can only suggest calling a tool that is explicitly registered. The application runtime validates arguments and executes the code.

### 2.6 RAG Layer (`app/rag`)
- Decouples knowledge storage and vector indexing from agents.
- Defines the `Retriever` contract (`search(query, top_k, filters)`).
- Will support PostgreSQL with `pgvector` for domain knowledge (product specs, stone care, shipping lead times).

### 2.7 CRM Layer (`app/crm`)
- Decouples customer relationship data from specific CRM software.
- The `CRMProvider` abstraction allows transparent switching between Mock, HubSpot, Salesforce, or internal database-backed CRMs without altering agent logic.

### 2.8 Integration Boundaries & n8n
- External APIs (Meta WhatsApp Cloud API, Google Sheets, etc.) have dedicated clients and services.
- `n8n` is used for visual workflow automation, webhooks, and background batch jobs. Communication with n8n is authenticated via `N8N_WEBHOOK_SECRET` and correlated via `X-Request-ID`.

---

## 3. Observability & Tracing

Every request, whether coming from a website user, an incoming WhatsApp webhook, or an internal scheduled task, flows with a unique `request_id`:
```
WhatsApp Inbound Webhook (X-Request-ID: req_01j8...)
  └─► FastAPI Middleware (attaches to ContextVar + logs event)
        └─► Orchestrator Agent (evaluates user intent)
              └─► Tool Call (Product Catalog Query)
                    └─► CRM Update (Record customer interest)
                          └─► Outbound WhatsApp Notification
```
All log entries are structured JSON containing `timestamp`, `level`, `service`, `request_id`, `event`, and `message`.
