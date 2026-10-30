# n8n Follow-up Workflow Automation Contract & Handoff Guide

This directory documents the contract, environment configuration, and manual verification steps for building and integrating an n8n follow-up workflow with CraftFlow.

> [!IMPORTANT]
> **Workflow Export Reference Disclaimer:**
> The file [`workflows/n8n/follow_up_execution_workflow.json`](./follow_up_execution_workflow.json) is an **initial reference export requiring alignment** with the revised contract detailed below. When building the workflow manually in the n8n editor, adhere strictly to the contract and payload structures defined in this document.

---

## 1. Environment & Network Configuration

### Required Environment Variables

Configure these settings in your `.env` file:

```env
# n8n Dispatch Mode: 'mock' (default, safe local development) or 'live'
N8N_DISPATCH_MODE=mock

# Base URL of your n8n instance
N8N_BASE_URL=http://localhost:5678

# Shared authentication secret sent in X-Webhook-Secret header
N8N_WEBHOOK_SECRET=dev_n8n_webhook_secret_placeholder

# Webhook path CraftFlow calls when dispatching an approved follow-up
N8N_FOLLOWUP_WEBHOOK_PATH=webhook/craftflow-followup
```

### Host vs. Container URLs

| Scenario | CraftFlow URL from n8n (`CRAFTFLOW_API_URL`) | n8n URL from CraftFlow (`N8N_BASE_URL`) |
| :--- | :--- | :--- |
| **n8n on Host (`npm`/`npx`), Backend on Host** | `http://localhost:8000` | `http://localhost:5678` |
| **n8n in Docker Container, Backend on Host** | `http://host.docker.internal:8000` | `http://localhost:5678` |
| **Both in Docker Compose Network** | `http://craftflow-backend:8000` | `http://n8n:5678` |

### Test vs. Production Webhook Paths in n8n

n8n distinguishes between workflow testing and active production listening:
- **Editor / Test Mode**: n8n listens on `/webhook-test/...` (e.g. `webhook-test/craftflow-followup`). Configure `N8N_FOLLOWUP_WEBHOOK_PATH=webhook-test/craftflow-followup` when clicking "Listen for Test Event" in the n8n canvas.
- **Production Mode**: When the workflow is saved and toggled to **Active**, n8n listens on `/webhook/...` (e.g. `webhook/craftflow-followup`). Configure `N8N_FOLLOWUP_WEBHOOK_PATH=webhook/craftflow-followup`.

---

## 2. Human Approval & Dispatch Lifecycle

CraftFlow enforces strict state separation:
1. **Approval authorizes execution; it does NOT mark the follow-up delivered.**
   - When a human agent approves a follow-up (`POST /api/v1/followups/{id}/approve`), its state becomes `status="SCHEDULED"`, `approval_status="APPROVED"`, and `delivery_status="PENDING"`.
   - Outbound delivery remains pending until the scheduled execution time is reached.
2. **Safe Dispatch & Observability**:
   - In `N8N_DISPATCH_MODE=live`, CraftFlow posts the trigger payload to n8n with headers `X-Webhook-Secret`, `X-Request-ID`, and `Content-Type: application/json`.
   - Dispatch results are stored directly on the follow-up: `n8n_dispatch_status` (`DISPATCHED` or `FAILED`), `n8n_dispatched_at`, and `n8n_dispatch_error`.
   - If n8n is unreachable during approval, the follow-up remains approved, records `n8n_dispatch_status="FAILED"`, and logs an audit event.
3. **Safe Dispatch Retry**:
   - An authorized agent can safely retry dispatch via:
     ```http
     POST /api/v1/followups/{id}/retry-dispatch
     Authorization: Bearer <API_KEY_AGENT>
     ```
   - Retrying reuses the existing `delivery_id`, ensuring no duplicate logical deliveries are scheduled.

---

## 3. Scheduling & Timezone Contract

1. **Explicit Timezone Requirement**:
   - All datetime inputs (`scheduled_at`) must include an explicit timezone offset (e.g. `2026-11-05T14:30:00Z` or `+05:30`). Timezone-naive datetimes are rejected with HTTP 422.
   - All comparisons and stored timestamps are normalized to UTC.
2. **Early Execution Guard (`NOT_DUE`)**:
   - If n8n invokes the execution endpoint before `scheduled_at`, the backend **rejects execution with `status="NOT_DUE"`**.
   - An early call does **NOT** consume an attempt, increment retry counters, or write an attempt record.
   - The response includes `next_eligible_at` indicating when the follow-up may be executed.
3. **n8n Wait Strategy**:
   - In your n8n workflow, after receiving the trigger, add a **Wait Node** configured to `Wait Until Date`: `{{ $json.scheduled_at }}`.
   - This ensures n8n pauses until the exact scheduled timestamp before invoking the CraftFlow execution webhook.
4. **Rescheduling Invariant (`STALE_SCHEDULE`)**:
   - When a follow-up is rescheduled via `PATCH /api/v1/followups/{id}`, CraftFlow increments `schedule_version` (e.g. 1 $\rightarrow$ 2) and generates a fresh `delivery_id`.
   - Any older queued execution in n8n carrying the previous `schedule_version` or old `delivery_id` is immediately rejected with `status="STALE_SCHEDULE"`.

---

## 4. Idempotency, Retries, and Concurrency Contract

### Identifiers: Stable vs. Variable Across Retries

| Field | Nature | Behavior across Retries |
| :--- | :--- | :--- |
| `followup_id` | **Stable** | The primary key UUID of the follow-up entity. |
| `delivery_id` | **Stable** | Identifies the logical scheduled delivery cycle. Preserved across all retry attempts. |
| `schedule_version`| **Stable** | Monotonically increasing version of the schedule. Preserved unless follow-up is rescheduled. |
| `attempt` | **Variable** | Integer attempt counter (1, 2, 3...). Enforced by backend; cannot exceed `max_retries`. |
| `attempt_id` | **Variable** | Unique identifier per physical attempt (e.g. `att_{attempt}_{delivery_id}` or UUID). |

### Concurrency Protection & Database Guarantees

- **Atomic Row Locking**: Execution uses PostgreSQL `SELECT ... FOR UPDATE` to serialize concurrent calls.
- **Unique Constraints**: Table `follow_up_delivery_attempts` enforces `UNIQUE(attempt_id)` and `UNIQUE(delivery_id, attempt)`.
- **Atomic Claims**: Each valid execution creates an attempt claim with an expiration timeout (5 minutes). If a worker crashes mid-flight, stale claims expire safely.
- **Duplicate Replay (`DUPLICATE_REPLAY`)**: Re-sending an already executed `attempt_id` returns the cached delivery outcome immediately with `status="DUPLICATE_REPLAY"` and `duplicate=true`, causing zero duplicate sends.
- **Terminal Exhaustion (`FAILED`)**: If attempts reach `max_retries` (default: 3), the follow-up transitions to `status="FAILED"`, `delivery_status="FAILED"`, and returns `retryable=false`. Subsequent attempts are rejected.
- **Delivery Uncertainty Note**: External mock messaging is deterministic. In production with third-party providers (e.g. Meta WhatsApp Cloud API), CraftFlow guarantees at-most-once execution claim and persistent attempt tracking; physical delivery confirmation depends on external webhook status receipts.

---

## 5. Webhook Contract & JSON Examples

**Endpoint**: `POST /api/v1/webhooks/n8n`  
**Authentication Header**: `X-Webhook-Secret: <N8N_WEBHOOK_SECRET>`

### Execution Request Body (`N8nFollowUpEventRequest`)

```json
{
  "event_id": "evt_att_1_del_abc123",
  "event_type": "followup.execute",
  "followup_id": "d9608ca0-2ea4-4ccc-8077-3bd95047a420",
  "delivery_id": "del_163f3f466aed4a4c",
  "attempt_id": "att_1_del_163f3f466aed4a4c",
  "schedule_version": 1,
  "attempt": 1,
  "max_retries": 3,
  "payload": {
    "simulate_failure": false
  }
}
```

---

### Response Examples

#### 1. Success (`DELIVERED`)
Returned when follow-up is due, approved, and delivered via provider:
```json
{
  "event_id": "evt_att_1_del_abc123",
  "followup_id": "d9608ca0-2ea4-4ccc-8077-3bd95047a420",
  "delivery_id": "del_163f3f466aed4a4c",
  "schedule_version": 1,
  "status": "DELIVERED",
  "delivery_status": "DELIVERED",
  "attempt": 1,
  "max_retries": 3,
  "retryable": false,
  "duplicate": false,
  "next_eligible_at": null,
  "message": "Follow-up message delivered successfully.",
  "delivery_record": {
    "event_id": "att_1_del_163f3f466aed4a4c",
    "attempt": 1,
    "status": "DELIVERED",
    "timestamp": "2026-10-30T12:00:00Z",
    "provider": "mock",
    "provider_message_id": "mock_wamid_8b9dd884cb56",
    "recipient": "+14155551565",
    "error": null,
    "retryable": false
  },
  "timestamp": "2026-10-30T12:00:00Z"
}
```

#### 2. Early Execution Blocked (`NOT_DUE`)
Returned if n8n calls before `scheduled_at`. Zero attempts consumed:
```json
{
  "event_id": "evt_early_1",
  "followup_id": "d9608ca0-2ea4-4ccc-8077-3bd95047a420",
  "delivery_id": "del_163f3f466aed4a4c",
  "schedule_version": 1,
  "status": "NOT_DUE",
  "delivery_status": "PENDING",
  "attempt": 0,
  "max_retries": 3,
  "retryable": false,
  "duplicate": false,
  "next_eligible_at": "2026-10-30T14:30:00Z",
  "message": "Follow-up is not due yet. Scheduled for 2026-10-30T14:30:00Z. Attempt not consumed.",
  "delivery_record": null,
  "timestamp": "2026-10-30T12:00:00Z"
}
```

#### 3. Transient Failure (`RETRYING`)
Returned when a retryable error occurs and `attempt < max_retries`:
```json
{
  "event_id": "evt_att_1_fail",
  "followup_id": "d9608ca0-2ea4-4ccc-8077-3bd95047a420",
  "delivery_id": "del_163f3f466aed4a4c",
  "schedule_version": 1,
  "status": "RETRYING",
  "delivery_status": "RETRYING",
  "attempt": 1,
  "max_retries": 3,
  "retryable": true,
  "duplicate": false,
  "next_eligible_at": null,
  "message": "Delivery failed transiently on attempt 1. Eligible for retry.",
  "delivery_record": {
    "event_id": "att_1_del_163f3f466aed4a4c",
    "attempt": 1,
    "status": "FAILED",
    "timestamp": "2026-10-30T12:00:00Z",
    "provider": "mock",
    "provider_message_id": null,
    "recipient": "+14155551565",
    "error": "Connection reset by peer",
    "retryable": true
  },
  "timestamp": "2026-10-30T12:00:00Z"
}
```

#### 4. Idempotent Replay (`DUPLICATE_REPLAY`)
Returned when an already processed `attempt_id` is received again:
```json
{
  "event_id": "evt_att_1_del_abc123",
  "followup_id": "d9608ca0-2ea4-4ccc-8077-3bd95047a420",
  "delivery_id": "del_163f3f466aed4a4c",
  "schedule_version": 1,
  "status": "DUPLICATE_REPLAY",
  "delivery_status": "DELIVERED",
  "attempt": 1,
  "max_retries": 3,
  "retryable": false,
  "duplicate": true,
  "next_eligible_at": null,
  "message": "Attempt 'att_1_del_163f3f466aed4a4c' was already processed. Returning recorded outcome.",
  "delivery_record": {
    "event_id": "att_1_del_163f3f466aed4a4c",
    "attempt": 1,
    "status": "DELIVERED",
    "timestamp": "2026-10-30T12:00:00Z",
    "provider": "mock",
    "provider_message_id": "mock_wamid_8b9dd884cb56",
    "recipient": "+14155551565",
    "error": null,
    "retryable": false
  },
  "timestamp": "2026-10-30T12:00:00Z"
}
```

#### 5. Stale Rescheduled Execution (`STALE_SCHEDULE`)
Returned when an older queued event calls with an outdated version/delivery_id:
```json
{
  "event_id": "evt_stale_1",
  "followup_id": "d9608ca0-2ea4-4ccc-8077-3bd95047a420",
  "delivery_id": "del_old_1111",
  "schedule_version": 1,
  "status": "STALE_SCHEDULE",
  "delivery_status": "PENDING",
  "attempt": 1,
  "max_retries": 3,
  "retryable": false,
  "duplicate": false,
  "next_eligible_at": null,
  "message": "Follow-up schedule has changed (current version: 2, request version: 1). Stale execution rejected.",
  "delivery_record": null,
  "timestamp": "2026-10-30T12:00:00Z"
}
```

#### 6. Cancelled Follow-up (`CANCELLED`)
Returned when follow-up was cancelled before execution:
```json
{
  "event_id": "evt_cancelled_1",
  "followup_id": "d9608ca0-2ea4-4ccc-8077-3bd95047a420",
  "delivery_id": "del_163f3f466aed4a4c",
  "schedule_version": 1,
  "status": "CANCELLED",
  "delivery_status": "CANCELLED",
  "attempt": 1,
  "max_retries": 3,
  "retryable": false,
  "duplicate": false,
  "next_eligible_at": null,
  "message": "Follow-up is cancelled. Execution halted.",
  "delivery_record": null,
  "timestamp": "2026-10-30T12:00:00Z"
}
```

#### 7. Terminal Failure (`FAILED`)
Returned when max retries are exhausted:
```json
{
  "event_id": "evt_att_3_fail",
  "followup_id": "d9608ca0-2ea4-4ccc-8077-3bd95047a420",
  "delivery_id": "del_163f3f466aed4a4c",
  "schedule_version": 1,
  "status": "FAILED",
  "delivery_status": "FAILED",
  "attempt": 3,
  "max_retries": 3,
  "retryable": false,
  "duplicate": false,
  "next_eligible_at": null,
  "message": "Max retries (3) exhausted: Gateway unavailable",
  "delivery_record": {
    "event_id": "att_3_del_163f3f466aed4a4c",
    "attempt": 3,
    "status": "FAILED",
    "timestamp": "2026-10-30T12:00:00Z",
    "provider": "mock",
    "provider_message_id": null,
    "recipient": "+14155551565",
    "error": "Gateway unavailable",
    "retryable": false
  },
  "timestamp": "2026-10-30T12:00:00Z"
}
```

---

## 6. Manual Verification Checklist

When building the workflow in the n8n editor, verify each behavior using this checklist:

- [ ] **Webhook Authentication**: Calling `/api/v1/webhooks/n8n` without `X-Webhook-Secret` or with an invalid secret returns `401 WEBHOOK_AUTHENTICATION_FAILED`.
- [ ] **Approval Barrier**: Triggering an execution before human approval returns `status="UNAPPROVED"`.
- [ ] **Early Execution Guard**: Triggering execution before `scheduled_at` returns `status="NOT_DUE"` with `next_eligible_at`, without consuming attempts.
- [ ] **Wait Until Due**: The n8n Wait node successfully pauses until `{{ $json.scheduled_at }}` before relaying to the backend.
- [ ] **Successful Delivery**: Calling when due returns `status="DELIVERED"`, records a provider message ID, transitions `delivery_status="DELIVERED"`, and records an outbound message.
- [ ] **Duplicate Replay**: Re-sending an identical `attempt_id` returns `status="DUPLICATE_REPLAY"` and `duplicate=true` without duplicating sends.
- [ ] **Rescheduling Invalidation**: Rescheduling a follow-up (`PATCH /api/v1/followups/{id}`) causes old queued calls to return `status="STALE_SCHEDULE"`.
- [ ] **Cancellation Check**: Cancelling a follow-up halts execution with `status="CANCELLED"`.
- [ ] **Bounded Retries**: Simulating a failure loops up to `max_retries`, transitioning to `status="FAILED"` once exhausted.
- [ ] **Dispatch Retry**: Testing `POST /api/v1/followups/{id}/retry-dispatch` succeeds without altering `delivery_id`.

To run the complete automated verification script locally:
```powershell
.\.venv\Scripts\python.exe backend/app/scripts/demo_n8n_followup.py
```
