"""Centralized Tool Registry for registering, retrieving, and discovering tools."""

from __future__ import annotations

from typing import Any

from app.core.exceptions import ToolExecutionException
from app.tools.base import Tool


class ToolRegistry:
    """Registry maintaining all available tools exposed to agents."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register a new tool instance."""
        if tool.name in self._tools:
            raise ToolExecutionException(
                message=f"Tool '{tool.name}' is already registered.",
                details={"tool_name": tool.name},
            )
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        """Retrieve a registered tool by name."""
        if name not in self._tools:
            raise ToolExecutionException(
                message=f"Tool '{name}' not found in registry.",
                details={"tool_name": name},
            )
        return self._tools[name]

    def list(self) -> list[Tool]:
        """List all registered tools."""
        return list(self._tools.values())

    def get_schemas(self) -> list[dict[str, Any]]:
        """Export tool definitions for LLM tool calling."""
        return [tool.get_openai_schema() for tool in self._tools.values()]


# Default singleton instance
_registry = ToolRegistry()


def get_tool_registry() -> ToolRegistry:
    """Dependency provider for the ToolRegistry."""
    return _registry
