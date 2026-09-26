"""Unit tests for Agent abstraction and DemoAgent execution."""

import pytest
from app.agents.base import AgentContext
from app.agents.demo import DemoAgent
from app.agents.registry import AgentRegistry
from app.ai.providers.mock_provider import MockLLMProvider
from app.tools.demo import MockProductSearchTool
from app.tools.registry import ToolRegistry


def test_agent_initialization():
    """Verify agent registration and registry lookup."""
    registry = AgentRegistry()
    agent = DemoAgent()
    registry.register(agent)

    assert len(registry.list()) == 1
    assert registry.get("demo_agent").name == "demo_agent"


@pytest.mark.asyncio
async def test_demo_agent():
    """Verify DemoAgent runs and executes tool dispatch deterministically."""
    mock_llm = MockLLMProvider(default_reply="Here are the bathtub options.")
    tools = ToolRegistry()
    tools.register(MockProductSearchTool())

    agent = DemoAgent(llm_provider=mock_llm, tool_registry=tools)
    ctx = AgentContext(channel="website")

    # Prompt triggering product search
    response = await agent.run("Please search product catalog for bathtubs", context=ctx)

    assert response.agent_name == "demo_agent"
    assert response.content == "Here are the bathtub options."
    assert len(response.tool_calls) == 1
    assert response.tool_calls[0]["tool"] == "search_products"
    assert response.context.channel == "website"
