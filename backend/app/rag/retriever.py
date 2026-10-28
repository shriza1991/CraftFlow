"""PostgreSQL + pgvector semantic vector retriever."""

import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.models.enums import KnowledgeDocumentStatus
from app.db.models.knowledge_chunk import KnowledgeChunk
from app.db.models.knowledge_document import KnowledgeDocument
from app.db.models.knowledge_source import KnowledgeSource
from app.rag.base import RAGTrace, RetrievalChunk, RetrievalResult, Retriever
from app.rag.embeddings import EmbeddingProvider, get_embedding_provider

logger = get_logger(__name__)
settings = get_settings()


class VectorRetriever(Retriever):
    """pgvector semantic vector retriever querying KnowledgeChunks."""

    def __init__(
        self,
        db: Session,
        embedding_provider: EmbeddingProvider | None = None,
    ):
        self.db = db
        self.embedding_provider = embedding_provider or get_embedding_provider()

    async def search(
        self,
        query: str,
        top_k: int | None = None,
        filters: dict[str, Any] | None = None,
        threshold: float | None = None,
    ) -> RetrievalResult:
        """Execute semantic vector search against PostgreSQL KnowledgeChunks."""
        k = top_k or settings.RAG_TOP_K
        min_score = threshold if threshold is not None else settings.RAG_SIMILARITY_THRESHOLD
        filters_dict = filters or {}

        start_time = time.perf_counter()

        # 1. Generate query embedding
        query_vector = self.embedding_provider.embed_text(query)

        # 2. Compute cosine distance: chunk.embedding <=> query_vector
        distance = KnowledgeChunk.embedding.cosine_distance(query_vector)

        # 3. Base query joining Document and Source to verify active status and provenance
        stmt = (
            select(
                KnowledgeChunk,
                KnowledgeDocument.title,
                KnowledgeDocument.source_id,
                KnowledgeDocument.document_type,
                KnowledgeSource.name.label("source_name"),
                distance.label("distance"),
            )
            .join(KnowledgeDocument, KnowledgeChunk.document_id == KnowledgeDocument.id)
            .outerjoin(KnowledgeSource, KnowledgeDocument.source_id == KnowledgeSource.id)
            .where(KnowledgeDocument.status == KnowledgeDocumentStatus.ACTIVE.value)
        )

        # 4. Apply metadata filters
        if "document_type" in filters_dict and filters_dict["document_type"]:
            stmt = stmt.where(KnowledgeDocument.document_type == filters_dict["document_type"])
        if "source_id" in filters_dict and filters_dict["source_id"]:
            stmt = stmt.where(KnowledgeDocument.source_id == filters_dict["source_id"])
        if "language" in filters_dict and filters_dict["language"]:
            stmt = stmt.where(KnowledgeDocument.language == filters_dict["language"])

        # Order by distance ascending and fetch candidates
        stmt = stmt.order_by(distance.asc()).limit(k * 2)
        results = self.db.execute(stmt).all()

        retrieved_chunks: list[RetrievalChunk] = []
        for chunk, doc_title, source_id, _doc_type, src_name, dist_val in results:
            # Cosine similarity = 1.0 - cosine_distance
            similarity = round(max(0.0, 1.0 - float(dist_val)), 4)
            if similarity < min_score:
                continue

            # Additional JSONB metadata filtering (e.g. product_id)
            if "product_id" in filters_dict and filters_dict["product_id"]:
                chunk_prod_id = chunk.metadata_.get("product_id")
                if chunk_prod_id != filters_dict["product_id"]:
                    continue

            retrieved_chunks.append(
                RetrievalChunk(
                    id=chunk.id,
                    document_id=chunk.document_id,
                    content=chunk.content,
                    score=similarity,
                    title=doc_title,
                    source_id=source_id,
                    source_name=src_name,
                    chunk_index=chunk.chunk_index,
                    metadata=chunk.metadata_,
                )
            )
            if len(retrieved_chunks) >= k:
                break

        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        trace = RAGTrace(
            query=query,
            embedding_provider=self.embedding_provider.__class__.__name__,
            embedding_model=getattr(self.embedding_provider, "_model", "deterministic-mock"),
            top_k=k,
            threshold=min_score,
            filters=filters_dict,
            retrieved_count=len(retrieved_chunks),
            duration_ms=duration_ms,
        )

        logger.info(
            f"VectorRetriever searched '{query}': found {len(retrieved_chunks)} chunks in {duration_ms}ms",
            extra={
                "event": "retriever_search",
                "extra_payload": {
                    "query": query,
                    "count": len(retrieved_chunks),
                    "duration_ms": duration_ms,
                },
            },
        )

        return RetrievalResult(
            query=query,
            chunks=retrieved_chunks,
            total_found=len(retrieved_chunks),
            trace=trace,
        )
