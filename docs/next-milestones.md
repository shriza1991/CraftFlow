# CraftFlow completion checklist

## Implemented in this increment
- [x] Persist inquiry evidence for later review.
- [x] Preserve catalog currencies and exact lead times in model context.
- [x] Exclude inactive products from explicit SKU lookup.
- [x] Separate human approval from delivery success.
- [x] Keep failed sends from marking a lead contacted.
- [x] Require adapter acknowledgement for WhatsApp sends.
- [x] Exercise two business profiles through offline contract cases.
- [x] Run offline evaluation in CI and document its limits.

## Manual n8n completion
- [ ] Add response status routing and preserve request context across waits.
- [ ] Add bounded business retry branch with fresh attempt IDs.
- [ ] Test due times, duplicate delivery, stale schedules and retry exhaustion.
- [ ] Activate/publish workflow and verify production webhook transport.
See [manual node guide](manual-n8n-outcomes.md).

## Real AI and delivery integration
- [ ] Evaluate actual pgvector retrieval using a versioned document/question dataset.
- [ ] Evaluate the chosen live model with reviewed grounded-answer expectations.
- [ ] Implement a real messaging adapter and authenticated inbound provider webhook.
- [ ] Add provider-level idempotency and recovery for ambiguous inquiry sends.
- [ ] Keep send credentials and real recipients outside default demo/test configuration.

## Portfolio release
- [ ] Record one successful end-to-end run per business profile.
- [ ] Record one rejection, one duplicate and one exhausted retry.
- [ ] Verify PostgreSQL migrations and concurrency tests in CI.
- [ ] Publish architecture, setup instructions and measured evaluation results.
- [ ] Demonstrate business configuration without claiming tenant isolation.

The backend is a runnable development baseline. Offline tests do not certify live n8n, live AI or production messaging; mark those milestones complete only after observing their actual runs.
