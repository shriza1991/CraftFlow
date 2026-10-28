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

## 3. Centralized Error Contract

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
- `VALIDATION_ERROR` (HTTP 422)
- `NOT_FOUND` (HTTP 404)
- `EXTERNAL_SERVICE_ERROR` (HTTP 502)
- `AI_PROVIDER_ERROR` (HTTP 502)
- `TOOL_EXECUTION_ERROR` (HTTP 400)
- `DATABASE_ERROR` (HTTP 503)
- `INTERNAL_SERVER_ERROR` (HTTP 500)

---

## 4. Active Domain & Knowledge Endpoints

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

---

## 5. Planned Future Endpoints (Milestones P3 → P13)

| Path | Method | Milestone | Description |
|---|---|---|---|
| `/api/v1/chat` | POST | P3 | Conversational AI orchestrator endpoint |
| `/api/v1/webhooks/whatsapp` | GET, POST | P4 | Meta WhatsApp Cloud API webhook |
| `/api/v1/webhooks/n8n` | POST | P5 | n8n automation relay endpoint |
| `/api/v1/approvals` | GET, POST | P9 | Human-in-the-loop approval management |
