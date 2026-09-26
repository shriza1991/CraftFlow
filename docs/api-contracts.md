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

## 4. Planned Future Endpoints (Milestones P1 → P13)

| Path | Method | Milestone | Description |
|---|---|---|---|
| `/api/v1/leads` | POST, GET | P1 | Create/list customer CRM leads |
| `/api/v1/products` | GET | P1 | Product catalog and dimension inquiries |
| `/api/v1/rag/search` | POST | P2 | Vector knowledge search |
| `/api/v1/chat` | POST | P3 | Conversational AI orchestrator endpoint |
| `/api/v1/webhooks/whatsapp` | GET, POST | P4 | Meta WhatsApp Cloud API webhook |
| `/api/v1/webhooks/n8n` | POST | P5 | n8n automation relay endpoint |
| `/api/v1/approvals` | GET, POST | P9 | Human-in-the-loop approval management |
