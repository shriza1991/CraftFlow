"""Demo Agent for P0 architecture validation."""

from typing import Any

from app.agents.base import AgentContext, AgentResponse, BaseAgent
from app.ai.base import LLMMessage, LLMProvider
from app.ai.factory import get_llm_provider
from app.core.config import get_settings
from app.tools.registry import ToolRegistry, get_tool_registry


class DemoAgent(BaseAgent):
    """P0 Validation Agent verifying LLM and Tool orchestration boundaries."""

    name = "demo_agent"
    description = "P0 architectural verification agent for testing and baseline validation."

    def __init__(
        self,
        llm_provider: LLMProvider | None = None,
        tool_registry: ToolRegistry | None = None,
    ):
        self.llm = llm_provider or get_llm_provider()
        self.tools = tool_registry or get_tool_registry()

    async def run(
        self,
        input_text: str,
        context: AgentContext | None = None,
        **kwargs: Any,
    ) -> AgentResponse:
        ctx = context or AgentContext()
        recorded_tool_calls: list[dict[str, Any]] = []

        # If user requests product lookup in prompt, demonstrate deterministic tool dispatch
        if "product" in input_text.lower() or "search" in input_text.lower():
            try:
                search_tool = self.tools.get("search_products")
                tool_res = await search_tool.execute({"query": input_text, "max_results": 2})
                recorded_tool_calls.append(
                    {
                        "tool": "search_products",
                        "arguments": {"query": input_text, "max_results": 2},
                        "result": tool_res.model_dump(),
                    }
                )
            except Exception:
                pass

        # Call LLM provider with messages
        settings = get_settings()
        messages = [
            LLMMessage(
                role="system",
                content=(
                    f"You are the assistant for {settings.BUSINESS_NAME}. "
                    f"{settings.BUSINESS_DESCRIPTION} "
                    "Use verified information; do not invent business facts."
                ),
            ),
            LLMMessage(role="user", content=input_text),
        ]
        llm_resp = await self.llm.generate(messages, **kwargs)

        return AgentResponse(
            content=llm_resp.content,
            agent_name=self.name,
            tool_calls=recorded_tool_calls,
            context=ctx,
        )
