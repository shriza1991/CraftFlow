"""Unit tests for Tool registry and deterministic execution."""

import pytest
from app.core.exceptions import ToolExecutionException
from app.tools.demo import HealthCheckTool, MockProductSearchTool
from app.tools.registry import ToolRegistry


def test_tool_registration():
    """Verify tool registration, listing, and schema generation."""
    registry = ToolRegistry()
    tool = HealthCheckTool()
    registry.register(tool)

    assert len(registry.list()) == 1
    assert registry.get("health_check").name == "health_check"

    schemas = registry.get_schemas()
    assert len(schemas) == 1
    assert schemas[0]["function"]["name"] == "health_check"


def test_tool_duplicate_registration_fails():
    """Verify registering a tool with duplicate name raises ToolExecutionException."""
    registry = ToolRegistry()
    tool = HealthCheckTool()
    registry.register(tool)

    with pytest.raises(ToolExecutionException):
        registry.register(tool)


def test_tool_lookup_missing():
    """Verify missing tool lookup raises exception."""
    registry = ToolRegistry()
    with pytest.raises(ToolExecutionException):
        registry.get("non_existent_tool")


@pytest.mark.asyncio
async def test_product_search_tool_execution():
    """Verify MockProductSearchTool validates arguments and returns structured results."""
    tool = MockProductSearchTool()
    res = await tool.execute({"query": "Carrara", "max_results": 2})

    assert res.success is True
    assert len(res.data) >= 1
    assert "Carrara" in res.data[0]["name"]


@pytest.mark.asyncio
async def test_product_search_tool_invalid_args():
    """Verify MockProductSearchTool safely fails on invalid arguments."""
    tool = MockProductSearchTool()
    # Missing required 'query'
    res = await tool.execute({"invalid_arg": 123})
    assert res.success is False
    assert res.error is not None
