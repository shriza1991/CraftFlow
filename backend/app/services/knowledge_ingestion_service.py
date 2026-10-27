"""Knowledge Ingestion Service orchestrating chunking, embedding, and vector persistence."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import RAGException
from app.core.logging import get_logger
from app.db.models.enums import IndexingStatus, KnowledgeDocumentStatus, KnowledgeSourceType
from app.db.models.knowledge_chunk import KnowledgeChunk
from app.db.models.knowledge_document import KnowledgeDocument
from app.rag.chunking import TextChunker
from app.rag.embeddings import EmbeddingProvider, get_embedding_provider
from app.schemas.knowledge import KnowledgeDocumentCreate
from app.services.knowledge_document_service import KnowledgeDocumentService
from app.services.knowledge_source_service import KnowledgeSourceService

logger = get_logger(__name__)
settings = get_settings()


class KnowledgeIngestionService:
    """Service handling the ingestion lifecycle from document content to pgvector storage."""

    @staticmethod
    def ingest_document(
        db: Session,
        doc_id: str,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> KnowledgeDocument:
        """Atomically chunk, embed, and index a KnowledgeDocument.

        If indexing fails, the transaction is rolled back and the document status
        is recorded as FAILED with error details.
        """
        doc = KnowledgeDocumentService.get_document(db, doc_id)
        provider = embedding_provider or get_embedding_provider()

        logger.info(
            f"Starting ingestion for document {doc.id} (title='{doc.title}', v{doc.version})",
            extra={
                "extra_payload": {"document_id": doc.id, "title": doc.title, "version": doc.version}
            },
        )

        # Mark as processing
        doc.indexing_status = IndexingStatus.PROCESSING.value
        db.commit()

        try:
            # 1. Chunk document
            chunker = TextChunker()
            base_meta = {
                "source_id": doc.source_id,
                "document_id": doc.id,
                "document_version": doc.version,
                "document_title": doc.title,
                "document_type": doc.document_type,
                **(doc.metadata_ or {}),
            }
            chunks = chunker.chunk_document(doc.content, base_metadata=base_meta)

            if not chunks:
                doc.indexing_status = IndexingStatus.COMPLETED.value
                doc.indexed_at = datetime.now(UTC)
                doc.indexing_error = None
                db.commit()
                db.refresh(doc)
                return doc

            # 2. Generate embeddings
            texts = [c.content for c in chunks]
            embeddings = provider.embed_batch(texts)

            if len(embeddings) != len(chunks):
                raise RAGException(
                    message="Embedding count mismatch with chunks",
                    details={"chunks": len(chunks), "embeddings": len(embeddings)},
                )

            # 3. Validate dimension
            expected_dim = settings.EMBEDDING_DIMENSION
            for idx, emb in enumerate(embeddings):
                if len(emb) != expected_dim:
                    raise RAGException(
                        message=f"Embedding dimension mismatch at chunk {idx}: expected {expected_dim}, got {len(emb)}",
                        details={"expected": expected_dim, "actual": len(emb)},
                    )

            # 4. Atomic persistence: remove previous chunks and insert new chunks
            db.execute(delete(KnowledgeChunk).where(KnowledgeChunk.document_id == doc.id))

            for chunk, emb in zip(chunks, embeddings, strict=True):
                chunk_obj = KnowledgeChunk(
                    document_id=doc.id,
                    chunk_index=chunk.chunk_index,
                    content=chunk.content,
                    token_count=chunk.token_count,
                    character_count=chunk.character_count,
                    metadata_=chunk.metadata,
                    embedding=emb,
                    embedding_model=settings.EMBEDDING_MODEL,
                    embedding_dimension=len(emb),
                )
                db.add(chunk_obj)

            # 5. Mark document as completed
            doc.indexing_status = IndexingStatus.COMPLETED.value
            doc.indexed_at = datetime.now(UTC)
            doc.indexing_error = None

            db.commit()
            db.refresh(doc)
            logger.info(
                f"Successfully indexed document {doc.id} ({len(chunks)} chunks created)",
                extra={"extra_payload": {"document_id": doc.id, "chunks_created": len(chunks)}},
            )
            return doc

        except Exception as exc:
            db.rollback()
            logger.error(
                f"Failed to index document {doc.id}: {exc}",
                extra={"extra_payload": {"document_id": doc.id, "error": str(exc)}},
            )
            try:
                # Update status in fresh transaction
                doc.indexing_status = IndexingStatus.FAILED.value
                doc.indexing_error = str(exc)
                db.commit()
            except Exception:
                db.rollback()

            raise RAGException(
                message=f"Failed to ingest document '{doc.title}': {exc!s}",
                details={"document_id": doc.id, "error": str(exc)},
            ) from exc

    @staticmethod
    def ingest_raw_document(
        db: Session,
        source_name: str,
        source_type: KnowledgeSourceType,
        title: str,
        content: str,
        document_type: str = "GENERAL",
        metadata: dict[str, Any] | None = None,
        language: str = "en",
        embedding_provider: EmbeddingProvider | None = None,
    ) -> KnowledgeDocument:
        """Create/get source, create/version document, and execute indexing pipeline."""
        source = KnowledgeSourceService.get_or_create_source(
            db=db,
            name=source_name,
            source_type=source_type,
        )

        doc_create = KnowledgeDocumentCreate(
            source_id=source.id,
            title=title,
            document_type=document_type,
            content=content,
            language=language,
            metadata_=metadata or {},
            status=KnowledgeDocumentStatus.ACTIVE,
        )

        doc = KnowledgeDocumentService.create_document(db, doc_create)

        # Index document
        return KnowledgeIngestionService.ingest_document(
            db=db,
            doc_id=doc.id,
            embedding_provider=embedding_provider,
        )
