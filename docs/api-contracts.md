> **Historical Ages Art design:** This document includes the original single-business example and planned capabilities. See the root README for the current configurable scope and implementation status.

# API Contracts — Ages Art AI Automation

## 1. Global Conventions

- All requests accept and return JSON (`application/json`).
- All requests should optionally include `X-Request-ID`. If missing, the server generates a UUIDv4 and returns it in the response header and body.
- Dates and timestamps are formatted in ISO-8601 UTC (`YYYY-MM-DDTHH:MM:SS.mmmmmmZ`).

---

## 2. Active P0 Endpoints

### 2.1 Health Check (Liveness Probe)

Checks whether the HTTP service is alive. Does not probe the database.

- **Method**: `GET`
- **Path**: `/api/v1/health`
- **Response Code**: `200 OK`
- **Response Body**:
```json
{
  "status": "ok",
  "service": "ai-business-automation",
  "version": "0.1.0"
}
```

---

### 2.2 Readiness Check (Readiness Probe)

Verifies critical dependencies (PostgreSQL database connectivity).

- **Method**: `GET`
- **Path**: `/api/v1/readiness`
- **Success Response Code**: `200 OK`
- **Success Response Body**:
```json
{
  "status": "ready",
  "dependencies": {
    "database": "healthy"
  }
}
```
- **Failure Response Code**: `503 Service Unavailable`
- **Failure Response Body**:
```json
{
  "status": "not_ready",
  "dependencies": {
    "database": "unhealthy"
  }
}
```

---

## 3. Authentication & Role-Based Access Control (RBAC)

CraftFlow protects business endpoints with role-based access control tailored for single-business deployments.

### 3.1 Authentication Headers
Clients authenticate by providing an API key in either:
- **Authorization header**: `Authorization: Bearer <API_KEY>`
- **X-API-Key header**: `X-API-Key: <API_KEY>`

Requests with missing or invalid API keys receive HTTP 401 with code `UNAUTHORIZED`.

### 3.2 Roles & Permissions Matrix
Each API key maps to one of three roles:
- **`admin`**: Full administrative access. Can modify the product catalog, customer records, sales leads, follow-ups, conversations, and knowledge sources.
- **`agent`**: Front-office sales & support access. Can create and update customers, leads, follow-up touchpoints, and conversation messages. Read-only access to products.
- **`viewer`**: Read-only reporting access. Can view products, customers, leads, follow-ups, and conversations. Any POST or PATCH mutation is rejected with HTTP 403 `FORBIDDEN`.

| Endpoint Group | Read (`GET`) | Write / Mutate (`POST`, `PATCH`) |
| :--- | :--- | :--- |
| `/api/v1/health`, `/api/v1/readiness`, `/api/v1/business` | Public | N/A |
| `/api/v1/products` | `viewer`, `agent`, `admin` | `admin` only |
| `/api/v1/customers` | `viewer`, `agent`, `admin` | `agent`, `admin` |
| `/api/v1/leads` | `viewer`, `agent`, `admin` | `agent`, `admin` |
| `/api/v1/followups` | `viewer`, `agent`, `admin` | `agent`, `admin` |
| `/api/v1/conversations` | `viewer`, `agent`, `admin` | `agent`, `admin` |
| `/api/v1/inquiries` | `viewer`, `agent`, `admin` | `agent`, `admin` |
| `/api/v1/webhooks/n8n` | N/A | Authenticated via `X-Webhook-Secret` |
| `/api/v1/knowledge` | `viewer`, `agent`, `admin` | `admin` |

### 3.3 Documented Development API Keys
Configured in `.env` (see `.env.example` and `examples/*.env`):
- `API_KEY_ADMIN="cf_admin_dev_key_2026"`
- `API_KEY_AGENT="cf_agent_dev_key_2026"`
- `API_KEY_VIEWER="cf_viewer_dev_key_2026"`

---

## 4. Centralized Error Contract

All error responses strictly follow the standard `ErrorResponse` schema:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid request payload or query parameters.",
    "request_id": "c1f77d32-e421-4d9a-b8cf-d07f311352a1",
    "details": {
      "errors": [
        {
          "loc": ["body", "email"],
          "msg": "value is not a valid email address",
          "type": "value_error"
        }
      ]
    }
  }
}
```

Standard Error Codes:
- `VALIDATION_ERROR` (HTTP 422): Invariant violation, relationship mismatch, or duplicate collision.
- `UNAUTHORIZED` (HTTP 401): Missing, malformed, or invalid API key or Bearer token.
- `FORBIDDEN` (HTTP 403): Caller role has insufficient permissions for the requested endpoint.
- `NOT_FOUND` (HTTP 404): Resource not found.
- `EXTERNAL_SERVICE_ERROR` (HTTP 502)
- `AI_PROVIDER_ERROR` (HTTP 502)
- `TOOL_EXECUTION_ERROR` (HTTP 400)
- `DATABASE_ERROR` (HTTP 503)
- `INTERNAL_SERVER_ERROR` (HTTP 500)

---

## 5. Business Invariants & Integrity Rules

CraftFlow enforces domain integrity and cross-record invariants across all business services:

### 5.1 Follow-up Ownership Invariant
- A follow-up touchpoint's `customer_id` **must strictly match** the owner of the referenced `lead_id` (`lead.customer_id == followup.customer_id`).
- If an optional `conversation_id` is supplied, its `customer_id` must also match `followup.customer_id`.
- Attempts to schedule follow-ups across mismatched customer and lead records are rejected with HTTP 422 `VALIDATION_ERROR`.

### 5.2 Lead Product Variant Integrity
- Any `variant_id` specified in a lead's requested product list **must belong to the referenced `product_id`** (`variant.product_id == lead_product.product_id`).
- Attempting to attach an existing variant from Product A to Product B is rejected with HTTP 422 `VALIDATION_ERROR`.

### 5.3 Duplicate Prevention & Concurrency Handling
- **Products**: SKUs and URL slugs are strictly unique. Re-using an existing SKU or slug on create or update is rejected with HTTP 422 and initiates an immediate transaction rollback. Variant SKU suffixes must be unique within a product.
- **Customers**: Primary email, phone number, and WhatsApp identifier are normalized and checked for collisions. Updates that would duplicate another customer's identifier fail cleanly with HTTP 422 and transaction rollback.
- **Leads**: Submitting duplicate active inquiry leads with identical details for the same customer is rejected with HTTP 422.
- **Follow-ups**: Scheduling duplicate pending follow-ups for the same lead and customer at the identical scheduled timestamp is rejected with HTTP 422.

### 5.4 Audit Trail & Mutation Logging
Every state mutation on Products, Customers, Leads, and Follow-ups creates an append-only entry in `audit_logs`:
- `actor_id`: Identified caller (e.g., `admin_user`, `agent_user`, or API key identity).
- `actor_type`: `HUMAN` or `AGENT`.
- `action`: `CREATE` or `UPDATE`.
- `resource_type`: `PRODUCT`, `CUSTOMER`, `LEAD`, `FOLLOW_UP`.
- `resource_id`: UUID of the affected entity.
- `before_state` & `after_state`: JSON snapshots of relevant state changes.

---

## 6. Active Domain & Knowledge Endpoints

All list endpoints support pagination parameters:
- `page`: Integer >= 1 (default: 1)
- `page_size`: Integer between 1 and 100 (default: 20)

### 4.1 Products API
- `GET /api/v1/products`: List products (supports `page`, `page_size`, `material`, `active_only` query filters).
- `POST /api/v1/products`: Create a luxury bathtub product with optional variants.
- `GET /api/v1/products/{product_id}`: Retrieve product details including variants.
- `PATCH /api/v1/products/{product_id}`: Update product attributes (price, lead time, status).

### 4.2 Customers API
- `GET /api/v1/customers`: List customers with pagination and search query.
- `POST /api/v1/customers`: Create a customer with normalized email and phone. Deduplicates deterministically.
- `GET /api/v1/customers/{customer_id}`: Retrieve customer details.
- `PATCH /api/v1/customers/{customer_id}`: Update customer profile information.

### 4.3 Leads API
- `GET /api/v1/leads`: List sales leads (supports `status`, `customer_id`, `page`, `page_size`).
- `POST /api/v1/leads`: Create a qualified lead linked to a customer and requested products/variants.
- `GET /api/v1/leads/{lead_id}`: Retrieve lead details with associated products.
- `PATCH /api/v1/leads/{lead_id}`: Update lead status enforcing state machine invariants (e.g. `LOST` cannot jump directly to `WON`).

### 4.4 Conversations & Messages API
- `POST /api/v1/conversations`: Start or register a customer interaction session on a channel (`WHATSAPP`, `WEBSITE`, `EMAIL`, etc.).
- `GET /api/v1/conversations/{conversation_id}`: Retrieve conversation with historical messages.
- `GET /api/v1/conversations/{conversation_id}/messages`: List conversation messages in chronological order.
- `POST /api/v1/conversations/{conversation_id}/messages`: Append an inbound or outbound message to the conversation thread.

### 4.5 Follow-ups API
- `GET /api/v1/followups`: List scheduled follow-ups (supports `status`, `lead_id`, `customer_id`, pagination).
- `POST /api/v1/followups`: Schedule a follow-up touchpoint linked to lead and customer.
- `PATCH /api/v1/followups/{followup_id}`: Update follow-up status (e.g., mark `COMPLETED`). Prevents `COMPLETED` from reverting to `PENDING`.
- `POST /api/v1/followups/{followup_id}/approve`: Human approval gate: approve scheduled follow-up for execution and optionally trigger n8n relay (`require_agent_or_admin`).
- `POST /api/v1/followups/{followup_id}/cancel`: Cancel a scheduled follow-up, preventing outbound delivery (`require_agent_or_admin`).
- `GET /api/v1/followups/{followup_id}/delivery`: Retrieve visible delivery status, attempts, retry bounds, and delivery audit history (`require_viewer_or_above`).

### 4.6 Business Profile API
- `GET /api/v1/business`: Retrieve metadata describing the active single business configured for this deployment (`business_name`, `business_description`, `business_industry`).

### 4.7 Knowledge Base & Grounded RAG API
- `GET /api/v1/knowledge/sources`: List knowledge sources and origins with pagination.
- `POST /api/v1/knowledge/sources`: Register a knowledge source (e.g., catalog, guides, FAQ, policy).
- `POST /api/v1/knowledge/documents`: Create a versioned markdown document and index it into pgvector.
- `GET /api/v1/knowledge/documents/{document_id}`: Retrieve document metadata and indexing status.
- `POST /api/v1/knowledge/documents/{document_id}/index`: Re-chunk, re-embed, and persist document vectors into pgvector.
- `POST /api/v1/knowledge/search`: Semantic vector search returning top-k matching chunks with similarity scores and full provenance (`document_id`, `chunk_id`, `source_id`, `source_name`, `title`, `chunk_index`, `metadata`).
- `POST /api/v1/knowledge/query`: Grounded RAG question-answering assistant.
  - **Grounding Semantics**: `grounded=true` indicates the response was synthesized and conditioned on retrieved evidence from the business knowledge base. It does **not** indicate that factual claims have been independently or externally verified.
  - **Missing & Insufficient Evidence**: If 0 relevant chunks match the query threshold, or if retrieved chunks lack necessary facts, the endpoint returns an explicit insufficient-evidence response with `grounded=false` and `sources=[]`.

### 6.8 Inquiry Workflow & Human Approval API

Enforces an end-to-end customer inquiry workflow with strict human-in-the-loop authorization prior to sending any outbound message:

- `POST /api/v1/inquiries`: Ingest customer inquiry, run knowledge retrieval & catalog search, draft a grounded response with structured evidence citations, upsert customer & lead records, and halt outbound dispatch pending human review (`status="COMPLETED"` or `"NEEDS_REVIEW"`, `outbound_message_sent=false`, `approval_status="PENDING_APPROVAL"`).
  - **Permissions**: `agent`, `admin`
  - **Request Body**:
    ```json
    {
      "customer": {
        "name": "Eleanor Vance",
        "email": "eleanor@example.com",
        "phone": "+14155552671",
        "location": "San Francisco, CA"
      },
      "message": {
        "content": "Hi, what are your lead times and pricing for Carrara marble bathtubs?",
        "channel": "WEBSITE",
        "sender_name": "Eleanor Vance"
      },
      "preferred_channel": "WEBSITE"
    }
    ```
  - **Response Body (`InquiryWorkflowResponse`)**:
    - `run_id`: UUID of the workflow execution (`AgentRun`).
    - `status`: `COMPLETED`, `NEEDS_REVIEW`, or `FAILED`.
    - `customer_id`, `conversation_id`, `lead_id`.
    - `draft`:
      - `content`: Synthesized response text.
      - `grounded`: `true` if supported by knowledge; `false` if unsupported.
      - `approval_status`: `"PENDING_APPROVAL"`.
      - `outbound_message_sent`: `false` (always `false` until approved).
      - `citations`: Traceable list of `EVIDENCE_SOURCE` items (`KNOWLEDGE` or `CATALOG`).
    - `steps`: Array of individual `WorkflowStepResult` records with step name, status, and diagnostic data.

- `GET /api/v1/inquiries/{run_id}`: Retrieve workflow execution telemetry, draft response status, and step diagnostics.
  - **Permissions**: `viewer`, `agent`, `admin`

- `POST /api/v1/inquiries/{run_id}/approve`: Human review approval gate. Approves the draft response, dispatches the outbound message, updates message status to `SENT`, transitions the CRM lead to `CONTACTED`, and logs an audit trail.
  - **Permissions**: `agent`, `admin`
  - **Request Body**:
    ```json
    {
      "custom_message": "Optional overridden message text reviewed and edited by human agent.",
      "reviewer_notes": "Verified availability with procurement team."
    }
    ```
  - **Response Body**:
    ```json
    {
      "run_id": "f15f2fbe-e527-4d0b-bf5d-09eeefa4ac13",
      "approval_status": "APPROVED",
      "outbound_message_sent": true,
      "message_id": "54aecc9a-1a67-441c-a172-3e98f7cd0ed3",
      "lead_id": "d404d397-bc64-43ec-982b-c785862cc97c",
      "lead_status": "CONTACTED",
      "sent_content": "Thank you for contacting us...",
      "approved_by": "cf_agent_dev_key_2026",
      "approved_at": "2026-10-29T14:00:00Z"
    }
    ```

- `POST /api/v1/inquiries/{run_id}/reject`: Human review decline gate. Declines the draft response, ensures no outbound message is sent (`approval_status="REJECTED"`), and records the reviewer's rationale in the audit trail.
  - **Permissions**: `agent`, `admin`
  - **Request Body**:
    ```json
    {
      "reason": "Customer inquiry is outside our geographical service area."
    }
    ```

### 6.9 n8n Automation Relay Webhook API

Authenticated webhook integration for n8n automation relay. Enforces backend business rules, human approval verification, idempotency protection, bounded retries, and visible delivery records:

- `POST /api/v1/webhooks/n8n`:
  - **Authentication**: `X-Webhook-Secret: <N8N_WEBHOOK_SECRET>` (returns HTTP 401 `WEBHOOK_AUTHENTICATION_FAILED` if missing or invalid).
  - **Request Body (`N8nFollowUpEventRequest`)**:
    ```json
    {
      "event_id": "evt_01J9ABC123456789",
      "event_type": "followup.execute",
      "followup_id": "9b480cef-ff98-4ed4-89d6-f16a5210877e",
      "attempt": 1,
      "max_retries": 3,
      "payload": {
        "simulate_failure": false
      }
    }
    ```
  - **Supported `event_type` actions**:
    - `"followup.execute"`: Verify approval, deliver follow-up message via configured provider, record delivery attempt, and update CRM status.
    - `"followup.schedule"`: Schedule a follow-up with automatic deduplication preventing duplicate creation.
    - `"followup.cancel"`: Cancel a follow-up.
  - **Response Body (`N8nFollowUpEventResponse`)**:
    ```json
    {
      "event_id": "evt_01J9ABC123456789",
      "followup_id": "9b480cef-ff98-4ed4-89d6-f16a5210877e",
      "status": "DELIVERED",
      "delivery_status": "DELIVERED",
      "attempt": 1,
      "max_retries": 3,
      "retryable": false,
      "message": "Follow-up message delivered successfully.",
      "duplicate": false,
      "delivery_record": {
        "event_id": "evt_01J9ABC123456789",
        "attempt": 1,
        "status": "DELIVERED",
        "timestamp": "2026-10-29T15:45:00Z",
        "provider": "mock",
        "provider_message_id": "mock_wamid_03b46ecb8c69",
        "recipient": "+14155552671",
        "error": null,
        "retryable": false
      },
      "timestamp": "2026-10-29T15:45:00Z"
    }
    ```
  - **Guarantees & Enforced Invariants**:
    - **Approval Gate**: Follow-ups with `approval_status != "APPROVED"` return `status="UNAPPROVED"` with `delivery_status="PENDING_APPROVAL"`; zero messages dispatched.
    - **Cancellation Guard**: Follow-ups with `status == "CANCELLED"` return `status="CANCELLED"`; zero messages dispatched.
    - **Event Idempotency**: Repeated webhooks with an already-processed `event_id` return `status="DUPLICATE_IGNORED"` with `duplicate=true`; zero duplicate sends.
    - **Bounded Retries**: Transient failures return `status="RETRYING"` with `retryable=true` until `attempt >= max_retries`, at which point the follow-up transitions to `status="FAILED"` with `retryable=false`.
    - **Observability**: Every attempt appends an immutable `DeliveryRecord` visible in `FollowUp.metadata["delivery_records"]` and via `GET /api/v1/followups/{id}/delivery`.

---

## 7. Planned Future Endpoints (Milestones P3 → P13)

| Path | Method | Milestone | Description |
|---|---|---|---|
| `/api/v1/chat` | POST | P3 | Conversational AI orchestrator endpoint |
| `/api/v1/webhooks/whatsapp` | GET, POST | P4 | Meta WhatsApp Cloud API webhook |
| `/api/v1/approvals` | GET, POST | P9 | Human-in-the-loop approval management |
