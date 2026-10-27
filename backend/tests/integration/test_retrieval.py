"""Integration tests for VectorRetriever against PostgreSQL + pgvector."""

import pytest
from app.db.models.enums import KnowledgeDocumentStatus, KnowledgeSourceType
from app.rag.retriever import VectorRetriever
from app.services.knowledge_ingestion_service import KnowledgeIngestionService
from sqlalchemy.orm import Session


@pytest.mark.asyncio
async def test_vector_retriever_semantic_match(db_session: Session):
    # Ingest two distinct documents
    KnowledgeIngestionService.ingest_raw_document(
        db=db_session,
        source_name="Product Catalog",
        source_type=KnowledgeSourceType.PRODUCT_CATALOG,
        title="Carrara Marble Specifications",
        content="The Carrara Monolithic bathtub weighs 680 kg and is carved from Bianco Carrara marble in Italy.",
        document_type="PRODUCT_GUIDE",
    )
    KnowledgeIngestionService.ingest_raw_document(
        db=db_session,
        source_name="Care Policies",
        source_type=KnowledgeSourceType.CARE_GUIDE,
        title="Marble Cleaning Protocols",
        content="Clean marble exclusively with pH-neutral soap. Never use vinegar, bleach, or acidic descalers.",
        document_type="CARE_GUIDE",
    )

    retriever = VectorRetriever(db=db_session)

    # Search for cleaning
    result = await retriever.search(
        query="How should I clean my marble bathtub without acid?",
        top_k=2,
    )
    assert len(result.chunks) > 0
    top_chunk = result.chunks[0]
    assert top_chunk.score > 0.0
    assert "pH-neutral soap" in top_chunk.content or "Carrara" in top_chunk.content


@pytest.mark.asyncio
async def test_vector_retriever_metadata_filtering(db_session: Session):
    KnowledgeIngestionService.ingest_raw_document(
        db=db_session,
        source_name="Catalog",
        source_type=KnowledgeSourceType.PRODUCT_CATALOG,
        title="Product Spec Sheet",
        content="Marble specifications and dimensions.",
        document_type="PRODUCT_GUIDE",
    )
    KnowledgeIngestionService.ingest_raw_document(
        db=db_session,
        source_name="Care",
        source_type=KnowledgeSourceType.CARE_GUIDE,
        title="Care Spec Sheet",
        content="Marble care instructions and sealing routine.",
        document_type="CARE_GUIDE",
    )

    retriever = VectorRetriever(db=db_session)

    # Filter by CARE_GUIDE only
    result = await retriever.search(
        query="Marble specifications and guidelines",
        top_k=5,
        filters={"document_type": "CARE_GUIDE"},
    )
    for chunk in result.chunks:
        assert chunk.title == "Care Spec Sheet"


@pytest.mark.asyncio
async def test_vector_retriever_excludes_archived_documents(db_session: Session):
    doc = KnowledgeIngestionService.ingest_raw_document(
        db=db_session,
        source_name="Old Policies",
        source_type=KnowledgeSourceType.BUSINESS_POLICY,
        title="Archived Warranty 2020",
        content="Obsolete 1-year warranty terms for vintage bathtubs.",
        document_type="POLICY",
    )
    # Archive the document
    doc.status = KnowledgeDocumentStatus.ARCHIVED.value
    db_session.commit()

    retriever = VectorRetriever(db=db_session)
    result = await retriever.search(
        query="What is the warranty period?",
        top_k=5,
    )
    for chunk in result.chunks:
        assert chunk.document_id != doc.id
