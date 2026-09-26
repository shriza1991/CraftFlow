"""Agent base contracts and execution context."""

import uuid
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field


class AgentContext(BaseModel):
    """Contextual metadata passed through agent execution chains."""

    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    conversation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    agent_run_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str | None = None
    channel: str = "api"
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentResponse(BaseModel):
    """Structured response produced by an agent."""

    content: str = Field(..., description="Agent message to the user/caller")
    agent_name: str = Field(..., description="Name of the agent producing the response")
    tool_calls: list[dict[str, Any]] = Field(
        default_factory=list, description="Record of tools invoked during this run"
    )
    context: AgentContext = Field(..., description="Correlation context of this run")


class BaseAgent(ABC):
    """Abstract base class for all specialized domain agents."""

    name: str
    description: str

    @abstractmethod
    async def run(
        self,
        input_text: str,
        context: AgentContext | None = None,
        **kwargs: Any,
    ) -> AgentResponse:
        """Execute agent workflow given an input prompt and contextual state."""
        pass
