"""Conversation and Message management API endpoints."""

import math

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_db
from app.schemas.conversation import ConversationCreate, ConversationResponse
from app.schemas.message import MessageCreate, MessageResponse
from app.schemas.pagination import PageParams, PaginatedResponse
from app.services.conversation_service import ConversationService
from app.services.message_service import MessageService

router = APIRouter(prefix="/conversations", tags=["Conversations & Messages"])


@router.post(
    "",
    response_model=ConversationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Conversation",
    description="Start a new omnichannel conversation thread for a customer.",
)
def create_conversation(
    conv_in: ConversationCreate,
    db: Session = Depends(get_db),
) -> ConversationResponse:
    conv = ConversationService.create_conversation(db=db, conv_in=conv_in)
    return ConversationResponse.model_validate(conv)


@router.get(
    "/{conversation_id}",
    response_model=ConversationResponse,
    summary="Get Conversation",
    description="Retrieve conversation metadata and message history.",
)
def get_conversation(
    conversation_id: str,
    db: Session = Depends(get_db),
) -> ConversationResponse:
    conv = ConversationService.get_conversation(db=db, conversation_id=conversation_id)
    return ConversationResponse.model_validate(conv)


@router.get(
    "/{conversation_id}/messages",
    response_model=PaginatedResponse[MessageResponse],
    summary="List Conversation Messages",
    description="Retrieve paginated messages for a conversation ordered chronologically.",
)
def list_messages(
    conversation_id: str,
    page: int = Query(default=1, ge=1, description="Page number"),
    page_size: int = Query(default=50, ge=1, le=100, description="Items per page"),
    db: Session = Depends(get_db),
) -> PaginatedResponse[MessageResponse]:
    params = PageParams(page=page, page_size=page_size)
    items, total = MessageService.list_messages(
        db=db, conversation_id=conversation_id, page_params=params
    )
    total_pages = math.ceil(total / params.page_size) if total > 0 else 0
    return PaginatedResponse(
        items=[MessageResponse.model_validate(m) for m in items],
        total=total,
        page=params.page,
        page_size=params.page_size,
        total_pages=total_pages,
    )


@router.post(
    "/{conversation_id}/messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Append Message",
    description="Log a new inbound customer message or outbound AI response to a conversation.",
)
def append_message(
    conversation_id: str,
    message_in: MessageCreate,
    db: Session = Depends(get_db),
) -> MessageResponse:
    msg = MessageService.append_message(
        db=db, conversation_id=conversation_id, message_in=message_in
    )
    return MessageResponse.model_validate(msg)
