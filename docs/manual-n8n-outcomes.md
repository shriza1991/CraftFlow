# Complete the manually built n8n workflow

Keep your existing authenticated webhook, prepare-request, Wait, and HTTP Request nodes. Configure these steps in your editor; nothing in this change modifies your n8n instance.

The backend response body is the source of truth. HTTP 200 alone does not mean delivered. In the HTTP Request node, keep the response as JSON and do not wrap it in a full-response envelope unless you adjust every expression below.

## Preserve request context

Before adding a loop, preserve the request sent to the backend alongside its response. A reliable layout is:

1. From the node immediately before HTTP Request, send the same single item both to HTTP Request and to input 1 of a Merge node.
2. Send HTTP Request's output to input 2 of Merge.
3. Configure Merge to combine by position. Input 1 must contain `request`; input 2 supplies backend fields such as `status`, `attempt` and `retryable`.
4. Feed the merged item into a Switch on `{{ $json.status }}`.

Keep one item per execution while learning. Verify the Merge output contains both `request.delivery_id` and the response `status`. Do not rely on a fixed reference to the first execution when looping: it can reuse an old attempt ID.

## Route outcomes

| Backend status | Action |
|---|---|
| DELIVERED, ALREADY_COMPLETED | End successfully; inspect the follow-up record. |
| DUPLICATE_REPLAY, DUPLICATE_IGNORED | End without another send. A replay is not permission for a new attempt. |
| CANCELLED, STALE_SCHEDULE, UNAPPROVED | End without sending; review cancellation, schedule or approval. |
| NOT_DUE | Wait until next_eligible_at, then replay the same request and attempt ID. |
| CLAIM_ACTIVE | Stop for inspection while learning. Do not start a competing attempt. |
| RETRYING with retryable=true | Prepare a new attempt, wait with a delay, then execute again. |
| FAILED | End as a visible failed execution; inspect backend failure details. |
| Any unknown status | Stop for inspection. |

For NOT_DUE, validate `next_eligible_at` exists before configuring the Wait date. Preserve the original `request` and route back to the pre-HTTP merge input and HTTP Request together.

For RETRYING, add a Code node using the merged item:

```javascript
const data = $input.first().json;
if (data.status !== 'RETRYING' || data.retryable !== true) {
  throw new Error('Backend did not authorize a retry');
}
if (!data.request || data.attempt >= data.max_retries) {
  throw new Error('Missing request or attempt limit reached');
}
const attempt = data.attempt + 1;
const attemptId = 'att_' + attempt + '_' + data.request.delivery_id;
const eligibleAt = Date.parse(data.next_eligible_at ?? '');
if (!Number.isFinite(eligibleAt)) {
  throw new Error('Backend did not provide a valid retry time');
}
return [{
  json: {
    request: {
      ...data.request,
      attempt,
      attempt_id: attemptId,
      event_id: attemptId
    },
    scheduled_at: new Date(Math.max(eligibleAt, Date.now() + 30000)).toISOString()
  }
}];
```

Feed this into your existing Wait node, using `{{ $json.scheduled_at }}`. From Wait, reconnect to both HTTP Request and the request-side input of Merge. Keep delivery_id and schedule_version unchanged. A new attempt gets a new attempt_id; retrying an HTTP transport error replays the **same** attempt_id.

The current backend's `max_retries` bounds total attempts, including the first, despite the field name. Do not enable HTTP Request's automatic retry for business failures. On timeout or network error, inspect and replay the original request ID; generating a new attempt can duplicate a send with an unknown outcome.

## Verify manually before activating

- Approve one due follow-up: expect DELIVERED with the mock adapter.
- Replay the identical execution payload: expect duplicate protection and no additional send.
- Set a future schedule: expect NOT_DUE and no send before it is due.
- Reschedule after queueing: the old schedule_version must be rejected as stale.
- For a disposable follow-up only, put `simulate_failure: true` in the execution payload. Expect bounded RETRYING outcomes followed by FAILED. To demonstrate recovery, remove the flag only from a new authorized retry request.
- Confirm a rejected/unapproved follow-up cannot send.

Use your existing X-Webhook-Secret credential for the backend webhook. It is distinct from API_KEY_AGENT used for agent API routes. Keep credentials in n8n's credential store, not Code nodes or exported workflow JSON.

Test webhook URLs are temporary listeners. After verification, activate/publish the workflow and configure the backend with its production webhook URL. Test from the backend runtime actually bound to port 8000; stop any obsolete container serving older routes.
