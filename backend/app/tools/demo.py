"""P0 Demo Tools demonstrating typed argument validation and execution."""

from typing import Any

from pydantic import BaseModel, Field

from app.tools.base import Tool, ToolResult


class ProductSearchArgs(BaseModel):
    """Arguments for mock product search."""

    query: str = Field(..., description="Product search keyword, e.g. 'marble bathtub'")
    max_results: int = Field(default=3, description="Maximum number of items to return")


class MockProductSearchTool(Tool):
    """P0 Scaffolding Tool: Searches catalog for luxury bathtubs."""

    name = "search_products"
    description = "Searches the Ages Art luxury bathtub catalog by keyword or style."
    args_schema = ProductSearchArgs

    # Scaffolding data for P0 testing
    MOCK_CATALOG = [
        {
            "id": "prod_1",
            "name": "Carrara Oval Freestanding Bathtub",
            "material": "Carrara White Marble",
            "dimensions": "1800 x 850 x 580 mm",
            "finish": "Honed Matte",
            "price_usd": 12500,
        },
        {
            "id": "prod_2",
            "name": "Nero Marquina Monolithic Bathtub",
            "material": "Nero Marquina Black Marble",
            "dimensions": "1900 x 900 x 600 mm",
            "finish": "Polished Gloss",
            "price_usd": 15800,
        },
        {
            "id": "prod_3",
            "name": "Travertine Romano Minimalist Tub",
            "material": "Roman Silver Travertine",
            "dimensions": "1750 x 800 x 550 mm",
            "finish": "Natural Vein Cut",
            "price_usd": 11200,
        },
    ]

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        try:
            parsed = ProductSearchArgs(**arguments)
        except Exception as exc:
            return ToolResult(success=False, error=f"Invalid arguments: {exc!s}")

        q = parsed.query.lower()
        matched = [
            item
            for item in self.MOCK_CATALOG
            if q in item["name"].lower() or q in item["material"].lower()
        ]
        return ToolResult(
            success=True,
            data=matched[: parsed.max_results],
        )


class HealthCheckTool(Tool):
    """P0 Diagnostic Tool: returns basic environment health metadata."""

    name = "health_check"
    description = "Performs an internal self-check of system subsystems."
    args_schema = None

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        return ToolResult(
            success=True,
            data={"status": "subsystems_operational", "tool": "health_check"},
        )
