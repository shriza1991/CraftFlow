"""Demo tools with injectable, explicitly simulated catalog data."""

from typing import Any

from pydantic import BaseModel, Field

from app.tools.base import Tool, ToolResult


class ProductSearchArgs(BaseModel):
    query: str = Field(..., min_length=1, description="Text to search in the demo catalog")
    max_results: int = Field(default=3, ge=1, le=100)


class MockProductSearchTool(Tool):
    """Search explicitly supplied demo items; never accesses the database."""

    name = "search_products"
    description = "Search an explicitly configured demo catalog."
    args_schema = ProductSearchArgs

    def __init__(self, catalog: list[dict[str, Any]] | None = None):
        self.catalog = list(catalog or [])

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        try:
            parsed = ProductSearchArgs(**arguments)
        except Exception as exc:
            return ToolResult(success=False, error=f"Invalid arguments: {exc!s}")
        terms = parsed.query.casefold().split()
        matched = [
            item
            for item in self.catalog
            if any(term in " ".join(str(v) for v in item.values()).casefold() for term in terms)
        ]
        return ToolResult(success=True, data=matched[: parsed.max_results])


class HealthCheckTool(Tool):
    """P0 diagnostic tool."""

    name = "health_check"
    description = "Performs an internal self-check of system subsystems."
    args_schema = None

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        return ToolResult(
            success=True, data={"status": "subsystems_operational", "tool": "health_check"}
        )
