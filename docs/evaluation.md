# Offline inquiry contract evaluation

Run from the repository root after installing `python -m pip install -e ".[dev]"`:

```bash
python backend/app/scripts/evaluate.py --output artifacts/evaluation
python -m pytest backend/tests -q
```

The runner writes JSON case outcomes and a Markdown check summary. It exits nonzero if any case fails. Reports are generated locally and ignored by Git. CI also runs the evaluation.

Two synthetic business configurations exercise the same inquiry service: stone products priced in EUR and design consultations priced in INR. Each has supported questions, unsupported questions, generation failures, and outbound delivery failures. Data and databases are isolated per case; no customer messages or external AI calls occur.

The checks cover citations after reload, catalog currency and precise lead-time context, business identity, approval gating, rejection, repeat approval protection, visible provider failures, and delivery failures leaving leads uncontacted. Approved sends use the existing mock WhatsApp adapter.

## What the numbers mean

This is a deterministic workflow contract suite. Scripted answers and a keyword fixture retriever make failures reproducible. Passing does **not** establish LLM factuality, semantic retrieval quality, live messaging, PostgreSQL locking, multi-tenant isolation, or n8n execution. The two profiles are separate test cases, not simultaneously isolated tenants.

JSON reports retain case answers, citations, errors, per-check denominators, timings, timestamp, and source revision. Timings include fixture setup and are not production performance measurements.

## Next evaluation layer

1. Ingest separate realistic documents using the actual knowledge API.
2. Add representative questions, expected source IDs and explicit unsupported questions.
3. Run against PostgreSQL/pgvector and the chosen live model using a separate opt-in job.
4. Score retrieval recall, citation validity, unsupported-question handling and reviewed answer correctness separately.
5. Record model, embedding model, dataset version, latency and cost. Review failures before publishing portfolio quality claims.

## Delivery semantics

Inquiry approval and delivery are distinct. An approved WhatsApp reply is marked sent only when the adapter acknowledges a message ID. Missing recipients, adapter errors, missing acknowledgements and unsupported outbound channels return a failed delivery with no sent timestamp; the lead remains NEW. WEBSITE approval publishes the persisted response internally and needs no external provider.

A failed approved inquiry cannot simply be approved again. Inspect the provider before retrying an ambiguous send; the inquiry path does not yet have provider-level idempotency or a recovery endpoint. The separate follow-up pipeline already has delivery and attempt identifiers. Real messaging adapters remain future integration work.
