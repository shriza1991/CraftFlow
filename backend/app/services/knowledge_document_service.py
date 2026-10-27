"""Knowledge Document domain service managing document lifecycle and versioning."""

import hashlib

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundException
from app.db.models.enums import IndexingStatus, KnowledgeDocumentStatus
from app.db.models.knowledge_document import KnowledgeDocument
from app.db.models.knowledge_source import KnowledgeSource
from app.schemas.knowledge import KnowledgeDocumentCreate, KnowledgeDocumentUpdate
from app.schemas.pagination import PageParams


def compute_content_checksum(content: str) -> str:
    """Compute SHA-256 hex digest for normalized content."""
    normalized = content.strip().encode("utf-8")
    return hashlib.sha256(normalized).hexdigest()


class KnowledgeDocumentService:
    """Operations for managing versioned business knowledge documents."""

    @staticmethod
    def create_document(db: Session, doc_in: KnowledgeDocumentCreate) -> KnowledgeDocument:
        """Create a new knowledge document or a new version if title exists in the source."""
        # 1. Validate source existence
        source = db.get(KnowledgeSource, doc_in.source_id)
        if not source:
            raise NotFoundException(
                message=f"KnowledgeSource with ID '{doc_in.source_id}' not found.",
                details={"source_id": doc_in.source_id},
            )

        # 2. Compute checksum
        checksum = compute_content_checksum(doc_in.content)

        # 3. Check for existing version of this document in the same source
        existing_versions = list(
            db.scalars(
                select(KnowledgeDocument)
                .where(
                    KnowledgeDocument.source_id == doc_in.source_id,
                    KnowledgeDocument.title == doc_in.title,
                )
                .order_by(KnowledgeDocument.version.desc())
            ).all()
        )

        version = doc_in.version
        if existing_versions:
            latest = existing_versions[0]
            # If same content checksum, return latest existing document (idempotency)
            if latest.checksum == checksum:
                return latest
            # Increment version
            version = latest.version + 1

        doc = KnowledgeDocument(
            source_id=doc_in.source_id,
            title=doc_in.title,
            document_type=doc_in.document_type,
            content=doc_in.content,
            version=version,
            status=doc_in.status.value if hasattr(doc_in.status, "value") else str(doc_in.status),
            language=doc_in.language,
            checksum=checksum,
            metadata_=doc_in.metadata_,
            indexing_status=IndexingStatus.PENDING.value,
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)
        return doc

    @staticmethod
    def get_document(db: Session, doc_id: str) -> KnowledgeDocument:
        """Retrieve document by ID or raise NotFoundException."""
        doc = db.get(KnowledgeDocument, doc_id)
        if not doc:
            raise NotFoundException(
                message=f"KnowledgeDocument with ID '{doc_id}' not found.",
                details={"document_id": doc_id},
            )
        return doc

    @staticmethod
    def list_documents(
        db: Session,
        page_params: PageParams,
        source_id: str | None = None,
        document_type: str | None = None,
        status: KnowledgeDocumentStatus | None = None,
        search: str | None = None,
    ) -> tuple[list[KnowledgeDocument], int]:
        """List knowledge documents with pagination and filtering."""
        query = select(KnowledgeDocument)
        count_query = select(func.count(KnowledgeDocument.id))

        if source_id:
            query = query.where(KnowledgeDocument.source_id == source_id)
            count_query = count_query.where(KnowledgeDocument.source_id == source_id)

        if document_type:
            query = query.where(KnowledgeDocument.document_type == document_type)
            count_query = count_query.where(KnowledgeDocument.document_type == document_type)

        if status:
            status_val = status.value if hasattr(status, "value") else str(status)
            query = query.where(KnowledgeDocument.status == status_val)
            count_query = count_query.where(KnowledgeDocument.status == status_val)

        if search:
            search_pattern = f"%{search}%"
            query = query.where(KnowledgeDocument.title.ilike(search_pattern))
            count_query = count_query.where(KnowledgeDocument.title.ilike(search_pattern))

        total = db.scalar(count_query) or 0
        items = list(
            db.scalars(
                query.order_by(KnowledgeDocument.title.asc(), KnowledgeDocument.version.desc())
                .offset(page_params.offset)
                .limit(page_params.limit)
            ).all()
        )
        return items, total

    @staticmethod
    def update_document(
        db: Session,
        doc_id: str,
        updates: KnowledgeDocumentUpdate,
    ) -> KnowledgeDocument:
        """Update knowledge document attributes. Marks indexing as PENDING if content changes."""
        doc = KnowledgeDocumentService.get_document(db, doc_id)
        update_dict = updates.model_dump(exclude_unset=True)

        if "content" in update_dict and update_dict["content"]:
            new_content = update_dict["content"]
            new_checksum = compute_content_checksum(new_content)
            if new_checksum != doc.checksum:
                doc.content = new_content
                doc.checksum = new_checksum
                doc.indexing_status = IndexingStatus.PENDING.value

        if "status" in update_dict and update_dict["status"]:
            st = update_dict["status"]
            doc.status = st.value if hasattr(st, "value") else str(st)

        if "metadata_" in update_dict and update_dict["metadata_"] is not None:
            doc.metadata_ = update_dict["metadata_"]

        for key, value in update_dict.items():
            if key not in ("status", "metadata_", "content") and value is not None:
                setattr(doc, key, value)

        db.commit()
        db.refresh(doc)
        return doc

    @staticmethod
    def delete_document(db: Session, doc_id: str) -> None:
        """Delete document and all associated chunks."""
        doc = KnowledgeDocumentService.get_document(db, doc_id)
        db.delete(doc)
        db.commit()
