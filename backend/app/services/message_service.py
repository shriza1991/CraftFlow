"""Message domain service managing message logging and conversation ordering."""

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundException
from app.db.models.conversation import Conversation
from app.db.models.message import Message
from app.schemas.message import MessageCreate
from app.schemas.pagination import PageParams


class MessageService:
    """Operations for persisting customer and AI messages in conversation threads."""

    @staticmethod
    def append_message(db: Session, conversation_id: str, message_in: MessageCreate) -> Message:
        """Append an inbound or outbound message to an existing conversation."""
        conv = db.get(Conversation, conversation_id)
        if not conv:
            raise NotFoundException(
                message=f"Conversation with ID '{conversation_id}' not found.",
                details={"conversation_id": conversation_id},
            )

        now = datetime.now(UTC)
        msg_data = message_in.model_dump(exclude={"metadata_", "sent_at"})
        msg = Message(
            conversation_id=conversation_id,
            **msg_data,
            sent_at=message_in.sent_at or now,
            metadata_=message_in.metadata_,
        )
        db.add(msg)

        # Update conversation last message timestamp
        conv.last_message_at = msg.sent_at

        db.flush()
        db.refresh(msg)
        db.commit()
        return msg

    @staticmethod
    def list_messages(
        db: Session,
        conversation_id: str,
        page_params: PageParams,
    ) -> tuple[list[Message], int]:
        """List messages belonging to a conversation ordered chronologically."""
        conv = db.get(Conversation, conversation_id)
        if not conv:
            raise NotFoundException(
                message=f"Conversation with ID '{conversation_id}' not found.",
                details={"conversation_id": conversation_id},
            )

        query = select(Message).where(Message.conversation_id == conversation_id)
        count_query = select(func.count(Message.id)).where(Message.conversation_id == conversation_id)

        total = db.scalar(count_query) or 0
        items = list(
            db.scalars(
                query.order_by(Message.created_at.asc())
                .offset(page_params.offset)
                .limit(page_params.limit)
            ).all()
        )
        return items, total
