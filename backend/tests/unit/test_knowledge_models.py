"""Unit tests for knowledge base domain models and constraints."""

import pytest
from sqlalchemy.orm import Session

from app.db.models.enums import IndexingStatus, KnowledgeDocumentStatus, KnowledgeSourceType
from app.db.models.knowledge_chunk import KnowledgeChunk
from app.db.models.knowledge_document import KnowledgeDocument
from app.db.models.knowledge_source import KnowledgeSource
from app.services.knowledge_document_service import compute_content_checksum


def test_create_knowledge_source_and_document(db_session: Session):
    source = KnowledgeSource(
        name="Ages Art Catalog",
        source_type=KnowledgeSourceType.PRODUCT_CATALOG.value,
        description="Master product catalog specifications",
        is_active=True,
    )
    db_session.add(source)
    db_session.commit()
    db_session.refresh(source)

    assert source.id is not None
    assert source.name == "Ages Art Catalog"

    content = "The Carrara Monolithic is carved from Italian Bianco Carrara marble."
    checksum = compute_content_checksum(content)

    doc = KnowledgeDocument(
        source_id=source.id,
        title="Carrara Monolithic Guide",
        document_type="PRODUCT_GUIDE",
        content=content,
        version=1,
        status=KnowledgeDocumentStatus.ACTIVE.value,
        language="en",
        checksum=checksum,
        metadata_={"material": "Carrara", "origin": "Italy"},
        indexing_status=IndexingStatus.PENDING.value,
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)

    assert doc.id is not None
    assert doc.source_id == source.id
    assert doc.checksum == checksum
    assert doc.metadata_["material"] == "Carrara"


def test_knowledge_chunk_vector_relationship(db_session: Session):
    source = KnowledgeSource(
        name="Care Guide Origin",
        source_type=KnowledgeSourceType.CARE_GUIDE.value,
    )
    db_session.add(source)
    db_session.commit()

    doc = KnowledgeDocument(
        source_id=source.id,
        title="Marble Care & Cleaning",
        document_type="CARE_GUIDE",
        content="Always clean marble with pH neutral soap.",
        version=1,
        checksum=compute_content_checksum("Always clean marble with pH neutral soap."),
        indexing_status=IndexingStatus.COMPLETED.value,
    )
    db_session.add(doc)
    db_session.commit()

    chunk = KnowledgeChunk(
        document_id=doc.id,
        chunk_index=0,
        content="Always clean marble with pH neutral soap.",
        token_count=10,
        character_count=42,
        metadata_={"section": "Cleaning"},
        embedding=[0.01] * 1536,
        embedding_model="text-embedding-3-small",
        embedding_dimension=1536,
    )
    db_session.add(chunk)
    db_session.commit()
    db_session.refresh(chunk)

    assert chunk.id is not None
    assert len(chunk.embedding) == 1536
    assert chunk.document.title == "Marble Care & Cleaning"
    assert len(doc.chunks) == 1
