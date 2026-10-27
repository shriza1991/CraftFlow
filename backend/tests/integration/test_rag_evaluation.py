"""RAG evaluation dataset and grounding benchmark tests."""

import pytest
from sqlalchemy.orm import Session

from app.db.models.enums import KnowledgeSourceType
from app.schemas.rag import RAGQueryRequest
from app.services.knowledge_ingestion_service import KnowledgeIngestionService
from app.services.rag_service import RAGService


@pytest.fixture(autouse=True)
def setup_evaluation_knowledge(db_session: Session):
    """Seed evaluation dataset into pgvector."""
    # 1. Care Guide
    KnowledgeIngestionService.ingest_raw_document(
        db=db_session,
        source_name="CraftFlow Care Guides",
        source_type=KnowledgeSourceType.CARE_GUIDE,
        title="Care & Maintenance Guide",
        content=(
            "Natural marble requires pH-neutral cleaners and annual sealing. "
            "Never use vinegar, lemon juice, or abrasive powders on marble. "
            "Rinse surfaces with warm clean water after bathing."
        ),
        document_type="CARE_GUIDE",
    )
    # 2. Product Guide
    KnowledgeIngestionService.ingest_raw_document(
        db=db_session,
        source_name="CraftFlow Catalog",
        source_type=KnowledgeSourceType.PRODUCT_CATALOG,
        title="Carrara Monolithic Product Guide",
        content=(
            "The Carrara Monolithic bathtub standard lead time is 8 to 10 weeks from architectural sign-off. "
            "Carved from Bianco Carrara marble, dry weight is 680 kg."
        ),
        document_type="PRODUCT_GUIDE",
    )
    # 3. Installation Guide
    KnowledgeIngestionService.ingest_raw_document(
        db=db_session,
        source_name="CraftFlow Architectural Guides",
        source_type=KnowledgeSourceType.INSTALLATION_GUIDE,
        title="Installation & Structural Engineering Guide",
        content=(
            "Monolithic stone bathtubs require floor joists rated for at least 4.5 kN/m² concentrated load. "
            "Finished subfloor must be verified by a certified structural engineer."
        ),
        document_type="GUIDE",
    )


@pytest.mark.asyncio
async def test_eval_maintenance_guidance_query(db_session: Session):
    rag = RAGService(db=db_session)
    req = RAGQueryRequest(
        question="What is the maintenance guidance for marble?",
        top_k=3,
    )
    res = await rag.answer_query(req)

    assert res.grounded is True
    assert res.retrieval_count > 0
    assert any("Care & Maintenance Guide" in s.title for s in res.sources if s.title)


@pytest.mark.asyncio
async def test_eval_lead_time_query(db_session: Session):
    rag = RAGService(db=db_session)
    req = RAGQueryRequest(
        question="What is the lead time for Carrara Monolithic?",
        top_k=3,
    )
    res = await rag.answer_query(req)

    assert res.grounded is True
    assert res.retrieval_count > 0
    assert any("Carrara Monolithic" in s.title for s in res.sources if s.title)


@pytest.mark.asyncio
async def test_eval_structural_load_query(db_session: Session):
    rag = RAGService(db=db_session)
    req = RAGQueryRequest(
        question="What floor joist load rating is required for stone bathtub installation?",
        top_k=3,
    )
    res = await rag.answer_query(req)

    assert res.grounded is True
    assert res.retrieval_count > 0
    assert any("Installation & Structural Engineering" in s.title for s in res.sources if s.title)


@pytest.mark.asyncio
async def test_eval_missing_knowledge_refusal(db_session: Session):
    rag = RAGService(db=db_session)
    # Question on topic completely outside our bathtub domain
    req = RAGQueryRequest(
        question="What is the company refund policy on cryptocurrency tokens?",
        threshold=0.8,
    )
    res = await rag.answer_query(req)

    assert res.grounded is False
    assert res.retrieval_count == 0
    assert len(res.sources) == 0
    assert "No sufficiently relevant business knowledge was found" in res.answer
