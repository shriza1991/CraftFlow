"""Unit tests verifying RAG generalization, source provenance, and grounding semantics."""

import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from app.ai.providers.mock_provider import MockLLMProvider
from app.rag.base import RetrievalChunk, RetrievalResult, Retriever
from app.rag.context import ContextBuilder
from app.schemas.rag import RAGQueryRequest
from app.scripts.ingest_knowledge import get_folder_config, ingest_knowledge_base
from app.services.rag_service import (
    RAGService,
    build_grounded_system_prompt,
    is_insufficient_evidence_response,
)


class DummyRetriever(Retriever):
    """Configurable test retriever returning pre-canned chunks."""

    def __init__(self, chunks: list[RetrievalChunk] | None = None):
        self.chunks = chunks or []

    async def search(
        self, query: str, top_k: int = 4, filters=None, threshold=None
    ) -> RetrievalResult:
        filtered = [c for c in self.chunks if threshold is None or c.score >= threshold]
        sliced = filtered[:top_k]
        return RetrievalResult(
            query=query,
            chunks=sliced,
            total_found=len(sliced),
        )


def test_build_grounded_system_prompt_generalization():
    """Verify system prompt dynamically adapts to configured business and avoids bathtub bias."""
    # Default prompt
    prompt_default = build_grounded_system_prompt()
    assert "business knowledge assistant" in prompt_default
    assert "luxury marble bathtub" not in prompt_default.lower()

    # Ages Art
    prompt_ages = build_grounded_system_prompt(
        business_name="Ages Art",
        business_description="luxury stone craftsmanship and bespoke marble bathtubs",
    )
    assert "business knowledge assistant for Ages Art" in prompt_ages
    assert "bespoke marble bathtubs" in prompt_ages
    assert "Answer ONLY using facts directly stated in the Context below" in prompt_ages

    # Northstar Design Studio (Service Business)
    prompt_design = build_grounded_system_prompt(
        business_name="Northstar Design Studio",
        business_description="interior architecture and residential space planning",
    )
    assert "business knowledge assistant for Northstar Design Studio" in prompt_design
    assert "interior architecture" in prompt_design
    assert "bathtub" not in prompt_design.lower()
    assert "marble" not in prompt_design.lower()


def test_insufficient_evidence_detection():
    """Verify detector catches standard refusal and missing-information responses."""
    assert is_insufficient_evidence_response(
        "The available business knowledge does not contain enough information to answer this question."
    )
    assert is_insufficient_evidence_response(
        "No sufficiently relevant business knowledge was found to answer this question."
    )
    assert is_insufficient_evidence_response(
        "I'm sorry, but there is not enough information in the provided context."
    )
    assert is_insufficient_evidence_response(
        "The context does not provide pricing details for commercial projects."
    )
    assert not is_insufficient_evidence_response(
        "The Full Room Design service costs $2,500 and includes CAD drawings and 3D renderings."
    )


def test_context_builder_provenance_and_citations():
    """Verify ContextBuilder formats chunk headers with source names and extracts complete provenance."""
    doc_id = str(uuid.uuid4())
    chunk_id = str(uuid.uuid4())
    source_id = str(uuid.uuid4())

    chunk = RetrievalChunk(
        id=chunk_id,
        document_id=doc_id,
        source_id=source_id,
        source_name="Northstar Design Studio Service Catalog",
        title="Full Room Design",
        content="Full Room Design includes 2 rounds of revisions and a 3D rendering.",
        chunk_index=0,
        score=0.92,
        metadata={"category": "services", "sku": "DESIGN-ROOM-02"},
    )

    # Context formatting
    context = ContextBuilder.build_context([chunk])
    assert "Northstar Design Studio Service Catalog - Full Room Design" in context
    assert f"DocID: {doc_id}" in context
    assert "Chunk 0" in context
    assert "Relevance: 0.92" in context
    assert "Full Room Design includes 2 rounds of revisions" in context

    # Source extraction
    sources = ContextBuilder.extract_sources([chunk])
    assert len(sources) == 1
    src = sources[0]
    assert src["document_id"] == str(doc_id)
    assert src["chunk_id"] == str(chunk_id)
    assert src["source_id"] == str(source_id)
    assert src["source_name"] == "Northstar Design Studio Service Catalog"
    assert src["title"] == "Full Room Design"
    assert src["score"] == 0.92
    assert src["metadata"] == {"category": "services", "sku": "DESIGN-ROOM-02"}


@pytest.mark.asyncio
async def test_rag_service_answers_service_business_query_with_provenance():
    """Verify RAGService answers queries for a service business with full provenance."""
    doc_id = str(uuid.uuid4())
    chunk_id = str(uuid.uuid4())
    source_id = str(uuid.uuid4())

    chunk = RetrievalChunk(
        id=chunk_id,
        document_id=doc_id,
        source_id=source_id,
        source_name="Northstar Design Studio Service Catalog",
        title="Design Consultation",
        content="The Initial Design Consultation is a 60-minute session for a flat fee of $100.",
        chunk_index=0,
        score=0.88,
        metadata={"sku": "DESIGN-CONSULT-01"},
    )

    mock_db = MagicMock()
    retriever = DummyRetriever(chunks=[chunk])
    llm = MockLLMProvider(
        default_reply="The Initial Design Consultation is a 60-minute session priced at $100."
    )

    rag = RAGService(
        db=mock_db,
        retriever=retriever,
        llm_provider=llm,
        business_name="Northstar Design Studio",
        business_description="bespoke interior architecture",
    )

    request = RAGQueryRequest(question="How much is an initial consultation?", top_k=2)
    response = await rag.answer_query(request)

    assert response.grounded is True
    assert response.retrieval_count == 1
    assert len(response.sources) == 1
    citation = response.sources[0]
    assert citation.title == "Design Consultation"
    assert citation.source_name == "Northstar Design Studio Service Catalog"
    assert citation.document_id == str(doc_id)
    assert citation.chunk_id == str(chunk_id)
    assert citation.source_id == str(source_id)
    assert citation.metadata == {"sku": "DESIGN-CONSULT-01"}
    assert "$100" in response.answer


@pytest.mark.asyncio
async def test_rag_service_unsupported_question_zero_chunks():
    """Verify an unsupported question with 0 retrieved chunks returns grounded=False and sources=[]."""
    mock_db = MagicMock()
    retriever = DummyRetriever(chunks=[])
    llm = MockLLMProvider()

    rag = RAGService(db=mock_db, retriever=retriever, llm_provider=llm)

    request = RAGQueryRequest(question="What is the policy for commercial rocket flights?")
    response = await rag.answer_query(request)

    assert response.grounded is False
    assert response.sources == []
    assert response.retrieval_count == 0
    assert "No sufficiently relevant business knowledge was found" in response.answer


@pytest.mark.asyncio
async def test_rag_service_unsupported_question_llm_refusal():
    """Verify grounded=False and sources=[] when retrieved chunks lack sufficient evidence and LLM refuses."""
    doc_id = str(uuid.uuid4())
    chunk = RetrievalChunk(
        id=str(uuid.uuid4()),
        document_id=doc_id,
        source_name="Ages Art Catalog",
        title="Nero Marquina Bathtub",
        content="The Nero Marquina is an oval bathtub carved from black marble.",
        score=0.45,
    )

    mock_db = MagicMock()
    retriever = DummyRetriever(chunks=[chunk])

    # LLM correctly determines that the question cannot be answered from the retrieved context
    llm = MockLLMProvider(
        default_reply="The available business knowledge does not contain enough information to answer this question."
    )

    rag = RAGService(db=mock_db, retriever=retriever, llm_provider=llm)

    request = RAGQueryRequest(question="What is the warranty period for helicopter landing pads?")
    response = await rag.answer_query(request)

    # Must NOT claim grounded=True merely because chunks were retrieved
    assert response.grounded is False
    assert response.sources == []
    assert response.retrieval_count == 1
    assert "does not contain enough information" in response.answer


def test_get_folder_config_supports_products_and_services():
    """Verify get_folder_config handles both product and service businesses without hardcoded bathtub text."""
    cfg_ages = get_folder_config("Ages Art")
    assert cfg_ages["products"]["source_name"] == "Ages Art Product Catalog"
    assert cfg_ages["guides"]["source_name"] == "Ages Art Guides & Documentation"

    cfg_northstar = get_folder_config("Northstar Design Studio")
    assert cfg_northstar["services"]["source_name"] == "Northstar Design Studio Service Catalog"
    assert cfg_northstar["services"]["document_type"] == "SERVICE_CATALOG"
    assert cfg_northstar["policies"]["source_name"] == "Northstar Design Studio Business Policies"


def test_default_knowledge_base_isolation():
    """Verify default knowledge_base directory does not load either example's documents by default."""
    default_kb = Path("knowledge_base")
    assert default_kb.exists()

    # In dry-run mode, verify no documents are processed from default knowledge_base
    stats = ingest_knowledge_base(base_dir=default_kb, dry_run=True)
    assert stats["documents_processed"] == 0
    assert stats["chunks_created"] == 0


def test_ages_art_example_ingestion_dry_run():
    """Verify Ages Art example knowledge base contains expected categories and chunks cleanly."""
    ages_art_kb = Path("examples/knowledge/ages-art")
    assert ages_art_kb.exists()

    stats = ingest_knowledge_base(base_dir=ages_art_kb, dry_run=True, business_name="Ages Art")
    assert stats["documents_processed"] >= 10
    assert stats["chunks_created"] >= 10
    assert stats["failures"] == 0


def test_design_studio_example_ingestion_dry_run():
    """Verify Northstar Design Studio example knowledge base contains expected services and chunks cleanly."""
    design_studio_kb = Path("examples/knowledge/design-studio")
    assert design_studio_kb.exists()

    stats = ingest_knowledge_base(
        base_dir=design_studio_kb, dry_run=True, business_name="Northstar Design Studio"
    )
    assert stats["documents_processed"] == 6
    assert stats["chunks_created"] >= 6
    assert stats["failures"] == 0
