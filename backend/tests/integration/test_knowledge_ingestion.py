"""Integration tests for KnowledgeIngestionService with real PostgreSQL + pgvector."""

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import RAGException
from app.db.models.enums import IndexingStatus, KnowledgeSourceType
from app.db.models.knowledge_chunk import KnowledgeChunk
from app.db.models.knowledge_document import KnowledgeDocument
from app.rag.embeddings import EmbeddingProvider, MockEmbeddingProvider
from app.services.knowledge_ingestion_service import KnowledgeIngestionService


def test_ingest_raw_document_success(db_session: Session):
    title = "Nero Marquina Bathtub Specifications"
    content = (
        "The Nero Marquina bathtub is sculpted from deep black Spanish marble. "
        "It features striking white calcite veins. Net dry weight is 620 kg."
    )

    doc = KnowledgeIngestionService.ingest_raw_document(
        db=db_session,
        source_name="Product Catalog Origin",
        source_type=KnowledgeSourceType.PRODUCT_CATALOG,
        title=title,
        content=content,
        document_type="PRODUCT_GUIDE",
        metadata={"material": "Nero Marquina"},
    )

    assert doc.id is not None
    assert doc.indexing_status == IndexingStatus.COMPLETED.value
    assert doc.indexed_at is not None

    chunks = list(
        db_session.scalars(
            select(KnowledgeChunk).where(KnowledgeChunk.document_id == doc.id)
        ).all()
    )
    assert len(chunks) >= 1
    assert len(chunks[0].embedding) == 1536
    assert "Nero Marquina" in chunks[0].content


def test_reindexing_replaces_old_chunks(db_session: Session):
    title = "Travertine Maintenance Rules"
    content_v1 = "Initial guidelines for travertine sealing."

    doc = KnowledgeIngestionService.ingest_raw_document(
        db=db_session,
        source_name="Care Origin",
        source_type=KnowledgeSourceType.CARE_GUIDE,
        title=title,
        content=content_v1,
        document_type="CARE_GUIDE",
    )

    initial_chunks = list(
        db_session.scalars(
            select(KnowledgeChunk).where(KnowledgeChunk.document_id == doc.id)
        ).all()
    )
    assert len(initial_chunks) == 1

    # Update content on document and re-index
    doc.content = "Updated guidelines for travertine sealing. Use fluoropolymer sealer every 12 months."
    db_session.commit()

    reindexed_doc = KnowledgeIngestionService.ingest_document(
        db=db_session,
        doc_id=doc.id,
    )
    assert reindexed_doc.indexing_status == IndexingStatus.COMPLETED.value

    new_chunks = list(
        db_session.scalars(
            select(KnowledgeChunk).where(KnowledgeChunk.document_id == doc.id)
        ).all()
    )
    assert len(new_chunks) >= 1
    assert "fluoropolymer" in new_chunks[0].content


def test_failed_ingestion_transaction_rollback(db_session: Session):
    class FailingProvider(EmbeddingProvider):
        @property
        def dimension(self) -> int:
            return 1536

        def embed_text(self, text: str) -> list[float]:
            raise RuntimeError("Simulated embedding provider outage")

        def embed_batch(self, texts: list[str]) -> list[list[float]]:
            raise RuntimeError("Simulated embedding provider outage")

    title = "Failing Ingestion Test"
    content = "Some content that will trigger an embedding failure."

    with pytest.raises(RAGException):
        KnowledgeIngestionService.ingest_raw_document(
            db=db_session,
            source_name="Failure Origin",
            source_type=KnowledgeSourceType.OTHER,
            title=title,
            content=content,
            embedding_provider=FailingProvider(),
        )

    # Verify no orphan chunks were saved
    doc = db_session.scalar(
        select(KnowledgeDocument).where(KnowledgeDocument.title == title)
    )
    if doc:
        chunks = list(
            db_session.scalars(
                select(KnowledgeChunk).where(KnowledgeChunk.document_id == doc.id)
            ).all()
        )
        assert len(chunks) == 0
        assert doc.indexing_status == IndexingStatus.FAILED.value
