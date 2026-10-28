"""CLI script to ingest knowledge base markdown documents into PostgreSQL + pgvector."""

import argparse
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.models.enums import IndexingStatus, KnowledgeSourceType
from app.db.models.knowledge_chunk import KnowledgeChunk
from app.db.models.knowledge_document import KnowledgeDocument
from app.db.models.knowledge_source import KnowledgeSource
from app.db.session import SessionLocal
from app.rag.chunking import TextChunker
from app.rag.embeddings import get_embedding_provider
from app.services.knowledge_document_service import (
    compute_content_checksum,
)
from app.services.knowledge_ingestion_service import KnowledgeIngestionService
from app.services.knowledge_source_service import KnowledgeSourceService

logger = get_logger(__name__)
settings = get_settings()


def get_folder_config(business_name: str | None = None) -> dict[str, dict[str, Any]]:
    """Build folder mapping to knowledge source names and document types for a business."""
    name = business_name or settings.BUSINESS_NAME
    return {
        "products": {
            "source_name": f"{name} Product Catalog",
            "source_type": KnowledgeSourceType.PRODUCT_CATALOG,
            "document_type": "PRODUCT_GUIDE",
        },
        "services": {
            "source_name": f"{name} Service Catalog",
            "source_type": KnowledgeSourceType.PRODUCT_CATALOG,
            "document_type": "SERVICE_CATALOG",
        },
        "guides": {
            "source_name": f"{name} Guides & Documentation",
            "source_type": KnowledgeSourceType.INSTALLATION_GUIDE,
            "document_type": "GUIDE",
        },
        "faq": {
            "source_name": f"{name} FAQ",
            "source_type": KnowledgeSourceType.FAQ,
            "document_type": "FAQ",
        },
        "policies": {
            "source_name": f"{name} Business Policies",
            "source_type": KnowledgeSourceType.BUSINESS_POLICY,
            "document_type": "POLICY",
        },
        "sales": {
            "source_name": f"{name} Sales & Consultation Guide",
            "source_type": KnowledgeSourceType.SALES_GUIDE,
            "document_type": "SALES_GUIDE",
        },
        "company": {
            "source_name": f"{name} Company Information",
            "source_type": KnowledgeSourceType.COMPANY_INFORMATION,
            "document_type": "COMPANY_INFO",
        },
    }


FOLDER_CONFIG = get_folder_config()


def extract_title_from_markdown(content: str, fallback_filename: str) -> str:
    """Extract first H1 markdown heading or fallback to cleaned filename."""
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("# "):
            title = line[2:].strip()
            # Clean out subtitle if present
            if " — " in title:
                title = title.split(" — ")[0].strip()
            return title
    # Fallback to Title Cased filename
    return fallback_filename.replace("_", " ").replace("-", " ").title()


def ingest_knowledge_base(
    base_dir: Path,
    reset: bool = False,
    dry_run: bool = False,
    business_name: str | None = None,
) -> dict[str, Any]:
    """Ingest markdown files from knowledge base directory."""
    if not base_dir.exists():
        print(f"[ERROR] Knowledge directory not found: {base_dir}")
        return {"error": "Directory not found"}

    stats = {
        "documents_processed": 0,
        "documents_skipped": 0,
        "chunks_created": 0,
        "embeddings_generated": 0,
        "failures": 0,
    }

    db: Session = SessionLocal()
    try:
        if reset and not dry_run:
            print("[INFO] Resetting knowledge tables (chunks, documents, sources)...")
            db.execute(delete(KnowledgeChunk))
            db.execute(delete(KnowledgeDocument))
            db.execute(delete(KnowledgeSource))
            db.commit()
            print("[INFO] Reset completed.")

        md_files = sorted(base_dir.rglob("*.md"))
        print(f"[INFO] Discovered {len(md_files)} markdown files in {base_dir}")

        provider = get_embedding_provider()
        chunker = TextChunker()
        folder_config = get_folder_config(business_name)
        b_name = business_name or settings.BUSINESS_NAME

        for md_path in md_files:
            # Skip readme files
            if md_path.name.lower() == "readme.md":
                continue

            folder_name = md_path.parent.name.lower()
            cfg = folder_config.get(
                folder_name,
                {
                    "source_name": f"{b_name} {folder_name.title()}",
                    "source_type": KnowledgeSourceType.OTHER,
                    "document_type": "GENERAL",
                },
            )

            raw_text = md_path.read_text(encoding="utf-8")
            title = extract_title_from_markdown(raw_text, md_path.stem)
            checksum = compute_content_checksum(raw_text)

            if dry_run:
                chunks = chunker.chunk_document(raw_text)
                print(f"[DRY-RUN] Would ingest '{title}' ({len(chunks)} chunks)")
                stats["documents_processed"] += 1
                stats["chunks_created"] += len(chunks)
                continue

            try:
                # Check if document with same title & checksum already indexed
                source = KnowledgeSourceService.get_or_create_source(
                    db=db,
                    name=cfg["source_name"],
                    source_type=cfg["source_type"],
                )

                # Check existing doc
                existing_doc = (
                    db.query(KnowledgeDocument)
                    .filter(
                        KnowledgeDocument.source_id == source.id,
                        KnowledgeDocument.title == title,
                        KnowledgeDocument.checksum == checksum,
                        KnowledgeDocument.indexing_status == IndexingStatus.COMPLETED.value,
                    )
                    .first()
                )

                if existing_doc and not reset:
                    # Check chunks actually exist
                    chunk_count = (
                        db.query(KnowledgeChunk)
                        .filter(KnowledgeChunk.document_id == existing_doc.id)
                        .count()
                    )
                    if chunk_count > 0:
                        print(
                            f"[SKIP] '{title}' already indexed with matching checksum ({chunk_count} chunks)"
                        )
                        stats["documents_skipped"] += 1
                        continue

                doc = KnowledgeIngestionService.ingest_raw_document(
                    db=db,
                    source_name=cfg["source_name"],
                    source_type=cfg["source_type"],
                    title=title,
                    content=raw_text,
                    document_type=cfg["document_type"],
                    metadata={"file_path": str(md_path.relative_to(base_dir))},
                    embedding_provider=provider,
                )

                chunks_count = (
                    db.query(KnowledgeChunk).filter(KnowledgeChunk.document_id == doc.id).count()
                )
                stats["documents_processed"] += 1
                stats["chunks_created"] += chunks_count
                stats["embeddings_generated"] += chunks_count
                print(f"[OK] Ingested '{title}' (v{doc.version}, {chunks_count} chunks)")

            except Exception as e:
                db.rollback()
                stats["failures"] += 1
                print(f"[FAIL] Error ingesting '{title}': {e}")

    finally:
        db.close()

    return stats


def main() -> None:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description="Ingest CraftFlow Knowledge Base into pgvector.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Rebuild all knowledge tables and embeddings from scratch.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Inspect files and chunks without writing to the database.",
    )
    parser.add_argument("--dir", type=str, default=None, help="Path to knowledge_base directory.")
    parser.add_argument(
        "--business-name",
        type=str,
        default=None,
        help="Name of the business (defaults to BUSINESS_NAME setting).",
    )
    args = parser.parse_args()

    # Determine knowledge directory
    if args.dir:
        kb_path = Path(args.dir)
    else:
        # Check settings.KNOWLEDGE_BASE_DIR first, then fallbacks
        candidates = [
            Path(settings.KNOWLEDGE_BASE_DIR),
            Path("knowledge_base"),
            Path(__file__).resolve().parent.parent.parent.parent / "knowledge_base",
            Path(__file__).resolve().parent.parent.parent / "knowledge_base",
        ]
        kb_path = next((p for p in candidates if p.exists()), Path("knowledge_base"))

    print("=" * 60)
    print("CraftFlow Knowledge Base Ingestion Pipeline (P2)")
    print("=" * 60)
    print(f"Target Directory: {kb_path.resolve()}")
    print(f"Business Name: {args.business_name or settings.BUSINESS_NAME}")
    print(f"Reset: {args.reset} | Dry-Run: {args.dry_run}")
    print("-" * 60)

    stats = ingest_knowledge_base(
        base_dir=kb_path.resolve(),
        reset=args.reset,
        dry_run=args.dry_run,
        business_name=args.business_name,
    )

    print("-" * 60)
    print("Ingestion Summary:")
    for k, v in stats.items():
        print(f"  {k.replace('_', ' ').title()}: {v}")
    print("=" * 60)

    if stats.get("failures", 0) > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
