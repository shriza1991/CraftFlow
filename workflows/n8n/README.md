# n8n Workflow Automation Directory

This directory stores version-controlled n8n workflow definitions, node templates, and export JSON files for external business automations.

---

## 1. Version-Controlled Workflow Export

The approved follow-up automation workflow is defined in:
[`workflows/n8n/follow_up_execution_workflow.json`](./follow_up_execution_workflow.json)

### Workflow Overview:
```
[Inbound Webhook Trigger]
        │
        ▼
[Prepare Event & Headers] ──► Generate event_id, attach X-Webhook-Secret & X-Request-ID
        │
        ▼
[CraftFlow Backend Relay] ──► POST /api/v1/webhooks/n8n (Backend validates approval & idempotency)
        │
        ▼
[Route Delivery Outcome] (Switch Node)
        │
        ├─► [DELIVERED / DUPLICATE_IGNORED] ──► [Webhook Response (Success)]
        ├─► [CANCELLED / UNAPPROVED]        ──► [Webhook Response (Skipped / Invariant Guarded)]
        ├─► [RETRYING (retryable=true)]     ──► [Wait Node (5s)] ──► [Increment Attempt] ──┐
        │                                                                                  │
        │   └─────────────────────────── Loop back to Backend Relay ───────────────────────┘
        │
        └─► [FAILED (max retries exhausted)]──► [Webhook Response (Terminal Failure)]
```

### Key Workflow Responsibilities:
- **Narrow Automation Boundary**: n8n coordinates scheduling and webhook relays; the CraftFlow FastAPI backend strictly controls business validation, human approval verification, idempotency tracking, and delivery record persistence.
- **Event Identifiers & Idempotency**: Each trigger payload carries an `event_id` (e.g. `evt_...`). If repeated events or webhook retries occur, CraftFlow ignores duplicates without sending duplicate messages or creating duplicate follow-up records.
- **Bounded Failure Handling & Retries**: When delivery encounters a transient failure and `attempt < max_retries`, the workflow waits (5 seconds), increments the attempt counter, and loops back to retry. Once attempts reach `max_retries` (default: 3), the workflow transitions to a terminal failure state.

---

## 2. Local Setup Instructions

### Option A: Running n8n with Docker (Recommended)

1. Start n8n using Docker:
```bash
docker run -it --rm --name n8n -p 5678:5678 -e N8N_WEBHOOK_SECRET=dev_n8n_webhook_secret_placeholder -e CRAFTFLOW_API_URL=http://host.docker.internal:8000 n8nio/n8n
```

> **Note for Docker users**: When connecting from an n8n container to CraftFlow running on your host machine, use `http://host.docker.internal:8000` as `CRAFTFLOW_API_URL`.

### Option B: Running n8n via npm

```bash
npx n8n
```
Set environment variables in your terminal or `.env`:
- `N8N_WEBHOOK_SECRET="dev_n8n_webhook_secret_placeholder"`
- `CRAFTFLOW_API_URL="http://localhost:8000"`

---

## 3. Importing the Workflow into n8n

1. Open n8n in your browser: `http://localhost:5678`
2. In the left navigation bar, click **Workflows** $\rightarrow$ **Add Workflow**.
3. In the canvas menu (top right three dots), select **Import from File...**.
4. Choose [`workflows/n8n/follow_up_execution_workflow.json`](./follow_up_execution_workflow.json).
5. Click **Save** and toggle the workflow to **Active**.

---

## 4. Mock Messaging Provider vs. Live Provider Setup

### Default Demo: Mock Messaging Provider (Offline)
By default, CraftFlow uses `WHATSAPP_PROVIDER=mock`, which executes immediately without requiring external API keys or telephone numbers:
- Generates simulated provider message IDs: `mock_wamid_<hash>`.
- Supports controlled transient failure testing by passing `payload: {"simulate_failure": true, "simulate_error": "Gateway timeout"}` in the event payload.
- All outbound messages are persisted in CraftFlow's `messages` table and visible in `FollowUp.metadata["delivery_records"]`.

### Live Provider Setup: Meta WhatsApp Cloud API (Production)
To switch from mock messaging to live WhatsApp Cloud API delivery:

1. Obtain WhatsApp Business API credentials from [Meta for Developers](https://developers.facebook.com):
   - System User Access Token (`WHATSAPP_ACCESS_TOKEN`)
   - Phone Number ID (`WHATSAPP_PHONE_NUMBER_ID`)
   - Business Account ID (`WHATSAPP_BUSINESS_ACCOUNT_ID`)

2. Configure `.env`:
```env
WHATSAPP_PROVIDER=meta
WHATSAPP_ACCESS_TOKEN=your_meta_system_user_access_token
WHATSAPP_PHONE_NUMBER_ID=your_phone_number_id
WHATSAPP_BUSINESS_ACCOUNT_ID=your_business_account_id
```

3. Webhook Authentication:
   - Configure `N8N_WEBHOOK_SECRET` in `.env` and set the identical value in your n8n environment variables.
   - Workflows calling `/api/v1/webhooks/n8n` must supply `X-Webhook-Secret: <N8N_WEBHOOK_SECRET>`.

---

## 5. Running the Local Verification Demo

To test the complete lifecycle offline (approval, delivery, duplicate protection, failure handling, retries, cancellation):

#### PowerShell (Windows):
```powershell
.\.venv\Scripts\python.exe backend/app/scripts/demo_n8n_followup.py
```

#### Bash (macOS / Linux):
```bash
python backend/app/scripts/demo_n8n_followup.py
```
