# Knowledge Base Repository

This directory serves as the local knowledge base repository for your CraftFlow deployment.

## Adding Knowledge for Your Business
Place markdown (`.md`) files organized into subfolders corresponding to your business functions:
- `products/` or `services/`: Product guides, service descriptions, specifications, pricing sheets.
- `guides/`: Installation instructions, onboarding walkthroughs, care manuals, process guides.
- `faq/`: Frequently asked questions and common customer inquiries.
- `policies/`: Shipping, return, warranty, cancellation, and scheduling policies.
- `company/`: Company history, contact information, hours of operation, and mission statements.

## Ingesting Documents into pgvector
To parse, chunk, embed, and index markdown documents into PostgreSQL + pgvector:
```bash
python -m app.scripts.ingest_knowledge
```

## Ready-to-Use Example Knowledge Sets
CraftFlow includes two reference business knowledge sets:
1. **Ages Art** (luxury stone bathtub manufacturing): `examples/knowledge/ages-art/`
2. **Northstar Design Studio** (interior design & professional services): `examples/knowledge/design-studio/`

To ingest an example knowledge set, specify `--dir` or set `KNOWLEDGE_BASE_DIR` in your `.env`:
```bash
python -m app.scripts.ingest_knowledge --dir examples/knowledge/ages-art
# or
python -m app.scripts.ingest_knowledge --dir examples/knowledge/design-studio
```
By default, neither example's documents are loaded into a new deployment.

