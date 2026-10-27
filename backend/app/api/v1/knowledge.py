"""Knowledge Base and RAG API endpoints."""

import math

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_db
from app.db.models.enums import KnowledgeDocumentStatus
from app.schemas.knowledge import (
    KnowledgeDocumentCreate,
    KnowledgeDocumentResponse,
    KnowledgeSearchRequest,
    KnowledgeSearchResponse,
    KnowledgeSourceCreate,
    KnowledgeSourceResponse,
)
from app.schemas.pagination import PageParams, PaginatedResponse
from app.schemas.rag import RAGQueryRequest, RAGQueryResponse
from app.services.knowledge_document_service import KnowledgeDocumentService
from app.services.knowledge_ingestion_service import KnowledgeIngestionService
from app.services.knowledge_source_service import KnowledgeSourceService
from app.services.rag_service import RAGService

router = APIRouter(prefix="/knowledge", tags=["Knowledge Base & RAG"])


# ------------------------------------------------------------------------------
# Knowledge Sources
# ------------------------------------------------------------------------------
@router.get(
    "/sources",
    response_model=PaginatedResponse[KnowledgeSourceResponse],
    summary="List Knowledge Sources",
    description="Retrieve paginated list of knowledge sources/origins.",
)
def list_sources(
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    active_only: bool = Query(default=True, description="Filter active sources only"),
    db: Session = Depends(get_db),
) -> PaginatedResponse[KnowledgeSourceResponse]:
    params = PageParams(page=page, page_size=page_size)
    items, total = KnowledgeSourceService.list_sources(
        db=db,
        page_params=params,
        active_only=active_only,
    )
    total_pages = math.ceil(total / params.page_size) if total > 0 else 0
    return PaginatedResponse(
        items=[KnowledgeSourceResponse.model_validate(s) for s in items],
        total=total,
        page=params.page,
        page_size=params.page_size,
        total_pages=total_pages,
    )


@router.post(
    "/sources",
    response_model=KnowledgeSourceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Knowledge Source",
    description="Register a new origin for business knowledge (e.g., FAQ, CATALOG).",
)
def create_source(
    source_in: KnowledgeSourceCreate,
    db: Session = Depends(get_db),
) -> KnowledgeSourceResponse:
    source = KnowledgeSourceService.create_source(db=db, source_in=source_in)
    return KnowledgeSourceResponse.model_validate(source)


@router.get(
    "/sources/{source_id}",
    response_model=KnowledgeSourceResponse,
    summary="Get Knowledge Source",
    description="Retrieve details of a knowledge source by ID.",
)
def get_source(
    source_id: str,
    db: Session = Depends(get_db),
) -> KnowledgeSourceResponse:
    source = KnowledgeSourceService.get_source(db=db, source_id=source_id)
    return KnowledgeSourceResponse.model_validate(source)


# ------------------------------------------------------------------------------
# Knowledge Documents
# ------------------------------------------------------------------------------
@router.get(
    "/documents",
    response_model=PaginatedResponse[KnowledgeDocumentResponse],
    summary="List Knowledge Documents",
    description="Retrieve paginated list of business documents with optional filters.",
)
def list_documents(
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=20, ge=1, le=100, description="Items per page"),
    source_id: str | None = Query(default=None, description="Filter by source ID"),
    document_type: str | None = Query(default=None, description="Filter by document type"),
    status: KnowledgeDocumentStatus | None = Query(default=None, description="Filter by document status"),
    search: str | None = Query(default=None, description="Search in document title"),
    db: Session = Depends(get_db),
) -> PaginatedResponse[KnowledgeDocumentResponse]:
    params = PageParams(page=page, page_size=page_size)
    items, total = KnowledgeDocumentService.list_documents(
        db=db,
        page_params=params,
        source_id=source_id,
        document_type=document_type,
        status=status,
        search=search,
    )
    total_pages = math.ceil(total / params.page_size) if total > 0 else 0
    return PaginatedResponse(
        items=[KnowledgeDocumentResponse.model_validate(d) for d in items],
        total=total,
        page=params.page,
        page_size=params.page_size,
        total_pages=total_pages,
    )


@router.post(
    "/documents",
    response_model=KnowledgeDocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Knowledge Document",
    description="Create a versioned business document and automatically index it into pgvector.",
)
def create_document(
    doc_in: KnowledgeDocumentCreate,
    auto_index: bool = Query(default=True, description="Immediately chunk and embed into pgvector"),
    db: Session = Depends(get_db),
) -> KnowledgeDocumentResponse:
    doc = KnowledgeDocumentService.create_document(db=db, doc_in=doc_in)
    if auto_index:
        doc = KnowledgeIngestionService.ingest_document(db=db, doc_id=doc.id)
    return KnowledgeDocumentResponse.model_validate(doc)


@router.get(
    "/documents/{document_id}",
    response_model=KnowledgeDocumentResponse,
    summary="Get Knowledge Document",
    description="Retrieve document metadata and indexing status.",
)
def get_document(
    document_id: str,
    db: Session = Depends(get_db),
) -> KnowledgeDocumentResponse:
    doc = KnowledgeDocumentService.get_document(db=db, doc_id=document_id)
    return KnowledgeDocumentResponse.model_validate(doc)


@router.post(
    "/documents/{document_id}/index",
    response_model=KnowledgeDocumentResponse,
    summary="Index Knowledge Document",
    description="Re-chunk, re-embed, and persist document vectors into pgvector.",
)
def index_document(
    document_id: str,
    db: Session = Depends(get_db),
) -> KnowledgeDocumentResponse:
    doc = KnowledgeIngestionService.ingest_document(db=db, doc_id=document_id)
    return KnowledgeDocumentResponse.model_validate(doc)


# ------------------------------------------------------------------------------
# Semantic Search & Grounded RAG Query
# ------------------------------------------------------------------------------
@router.post(
    "/search",
    response_model=KnowledgeSearchResponse,
    summary="Search Knowledge Base",
    description="Execute raw semantic vector retrieval against pgvector without invoking an LLM.",
)
async def search_knowledge(
    search_req: KnowledgeSearchRequest,
    db: Session = Depends(get_db),
) -> KnowledgeSearchResponse:
    rag_service = RAGService(db=db)
    return await rag_service.search_knowledge(search_req)


@router.post(
    "/query",
    response_model=RAGQueryResponse,
    summary="RAG Knowledge Assistant",
    description="Ask a natural language question and receive an answer strictly grounded in business knowledge.",
)
async def query_knowledge(
    query_req: RAGQueryRequest,
    db: Session = Depends(get_db),
) -> RAGQueryResponse:
    rag_service = RAGService(db=db)
    return await rag_service.answer_query(query_req)
