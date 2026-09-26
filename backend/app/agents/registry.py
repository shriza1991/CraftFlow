"""Agent registry for dynamic agent lookup and orchestration."""

from __future__ import annotations

from app.agents.base import BaseAgent
from app.core.exceptions import AppException


class AgentRegistry:
    """Registry maintaining active agent instances."""

    def __init__(self) -> None:
        self._agents: dict[str, BaseAgent] = {}

    def register(self, agent: BaseAgent) -> None:
        """Register an agent instance."""
        if agent.name in self._agents:
            raise AppException(
                message=f"Agent '{agent.name}' is already registered.",
                status_code=400,
                error_code="AGENT_ALREADY_REGISTERED",
            )
        self._agents[agent.name] = agent

    def get(self, name: str) -> BaseAgent:
        """Retrieve an agent instance by name."""
        if name not in self._agents:
            raise AppException(
                message=f"Agent '{name}' not found.",
                status_code=404,
                error_code="AGENT_NOT_FOUND",
            )
        return self._agents[name]

    def list(self) -> list[BaseAgent]:
        """List all registered agents."""
        return list(self._agents.values())


_agent_registry = AgentRegistry()


def get_agent_registry() -> AgentRegistry:
    """Dependency provider for AgentRegistry."""
    return _agent_registry
