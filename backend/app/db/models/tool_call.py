"""ToolCall domain entity tracking tool executions within an agent run."""

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, JSONType, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.models.enums import ToolCallStatus

if TYPE_CHECKING:
    from app.db.models.agent_run import AgentRun


class ToolCall(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Deterministic tool call audit record executed on behalf of an agent."""

    __tablename__ = "tool_calls"

    agent_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tool_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(50), default=ToolCallStatus.REQUESTED.value, nullable=False, index=True
    )

    arguments: Mapped[dict] = mapped_column("arguments", JSONType, default=dict, nullable=False)
    result_summary: Mapped[dict | None] = mapped_column("result_summary", JSONType, nullable=True)

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    agent_run: Mapped["AgentRun"] = relationship("AgentRun", back_populates="tool_calls")
