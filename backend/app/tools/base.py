"""Typed Tool abstractions ensuring deterministic execution."""

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field


class ToolResult(BaseModel):
    """Structured output returned by any tool execution."""

    success: bool = Field(..., description="Whether the tool executed successfully")
    data: Any = Field(default=None, description="Returned payload or result of execution")
    error: str | None = Field(default=None, description="Error message if execution failed")


class Tool(ABC):
    """Abstract base class for all deterministic business and utility tools."""

    name: str
    description: str
    args_schema: type[BaseModel] | None = None

    @abstractmethod
    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        """Validate input arguments and execute the deterministic business action."""
        pass

    def get_openai_schema(self) -> dict[str, Any]:
        """Convert tool specification to standard OpenAI tool calling definition."""
        schema: dict[str, Any] = {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
            },
        }
        if self.args_schema:
            schema["function"]["parameters"] = self.args_schema.model_json_schema()
        else:
            schema["function"]["parameters"] = {
                "type": "object",
                "properties": {},
            }
        return schema
