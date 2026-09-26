"""Conversation domain service managing omnichannel session threads."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import NotFoundException
from app.db.models.conversation import Conversation
from app.db.models.customer import Customer
from app.schemas.conversation import ConversationCreate
from app.schemas.pagination import PageParams
from app.services.audit_service import AuditService


class ConversationService:
    """Business operations for conversation sessions across WhatsApp, Website, etc."""

    @staticmethod
    def create_conversation(db: Session, conv_in: ConversationCreate) -> Conversation:
        """Create a new interaction conversation thread for a customer."""
        customer = db.get(Customer, conv_in.customer_id)
        if not customer:
            raise NotFoundException(
                message=f"Customer with ID '{conv_in.customer_id}' not found.",
                details={"customer_id": conv_in.customer_id},
            )

        conv = Conversation(
            customer_id=conv_in.customer_id,
            channel=conv_in.channel.value if hasattr(conv_in.channel, "value") else str(conv_in.channel),
            external_conversation_id=conv_in.external_conversation_id,
            status=conv_in.status.value if hasattr(conv_in.status, "value") else str(conv_in.status),
            metadata_=conv_in.metadata_,
        )
        db.add(conv)
        db.flush()
        db.refresh(conv)

        AuditService.record(
            db=db,
            action="CONVERSATION_CREATED",
            entity_type="Conversation",
            entity_id=conv.id,
            description=f"Created {conv.channel} conversation for customer '{customer.first_name}'.",
        )
        db.commit()
        return conv

    @staticmethod
    def get_conversation(db: Session, conversation_id: str) -> Conversation:
        """Retrieve conversation with messages or raise NotFoundException."""
        stmt = (
            select(Conversation)
            .where(Conversation.id == conversation_id)
            .options(selectinload(Conversation.messages))
        )
        conv = db.scalar(stmt)
        if not conv:
            raise NotFoundException(
                message=f"Conversation with ID '{conversation_id}' not found.",
                details={"conversation_id": conversation_id},
            )
        return conv

    @staticmethod
    def list_conversations(
        db: Session,
        page_params: PageParams,
        customer_id: str | None = None,
    ) -> tuple[list[Conversation], int]:
        """List conversations with pagination."""
        query = select(Conversation).options(selectinload(Conversation.messages))
        count_query = select(func.count(Conversation.id))

        if customer_id:
            query = query.where(Conversation.customer_id == customer_id)
            count_query = count_query.where(Conversation.customer_id == customer_id)

        total = db.scalar(count_query) or 0
        items = list(
            db.scalars(
                query.order_by(Conversation.started_at.desc())
                .offset(page_params.offset)
                .limit(page_params.limit)
            ).all()
        )
        return items, total
