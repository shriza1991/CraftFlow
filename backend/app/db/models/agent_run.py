"""AgentRun domain entity tracking AI agent executions."""

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, JSONType, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.models.enums import AgentRunStatus

if TYPE_CHECKING:
    from app.db.models.conversation import Conversation
    from app.db.models.lead import Lead
    from app.db.models.tool_call import ToolCall


class AgentRun(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Execution telemetry and outcome for an AI Agent workflow."""

    __tablename__ = "agent_runs"

    agent_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    agent_version: Mapped[str] = mapped_column(String(50), default="1.0.0", nullable=False)

    conversation_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("conversations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    customer_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("customers.id", ondelete="SET NULL"), nullable=True
    )
    lead_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("leads.id", ondelete="SET NULL"), nullable=True
    )

    status: Mapped[str] = mapped_column(
        String(50), default=AgentRunStatus.PENDING.value, nullable=False, index=True
    )

    input_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    metadata_: Mapped[dict] = mapped_column("metadata", JSONType, default=dict, nullable=False)

    # Relationships
    conversation: Mapped["Conversation | None"] = relationship(
        "Conversation", back_populates="agent_runs"
    )
    lead: Mapped["Lead | None"] = relationship("Lead", back_populates="agent_runs")
    tool_calls: Mapped[list["ToolCall"]] = relationship(
        "ToolCall", back_populates="agent_run", cascade="all, delete-orphan"
    )
