"""Orchestrator agent for selecting specialist agents."""

from __future__ import annotations

from typing import Any

from agents.agent_catalog import (
    RoutingSupportTool,
    create_default_routing_support_tools,
    get_top_level_agent_capabilities,
)
from agents.base import AgentContext

TOP_LEVEL_AGENT_IDS = tuple(
    capability.agent_id for capability in get_top_level_agent_capabilities()
)


class OrchestratorAgent:
    """Select the top-level specialist agent."""

    agent_id = "orchestrator"

    def __init__(
        self,
        tools: tuple[RoutingSupportTool, ...] | None = None,
    ) -> None:
        self.tools = create_default_routing_support_tools() if tools is None else tools

    def build_routing_prompt(
        self,
        payload: dict[str, Any],
        context: AgentContext,
        requested_agent: str | None = None,
    ) -> str:
        """Build the prompt used to select a top-level agent."""

        agent_hint = requested_agent or "none"
        allowed_agent_ids = "\n".join(
            f"- {agent_id}" for agent_id in TOP_LEVEL_AGENT_IDS
        )
        routing_tool_sections = self._build_routing_tool_sections(payload, context)
        return (
            "[ROLE]\n"
            "AI 퀘스트 에이전트 서버 최상위 오케스트레이터\n\n"
            "[TASK]\n"
            "요청을 처리할 최상위 Agent id를 하나만 결정한다.\n\n"
            "[ALLOWED_AGENT_IDS]\n"
            f"{allowed_agent_ids}\n\n"
            f"{routing_tool_sections}\n\n"
            "[REQUEST_HINT]\n"
            f"agent: {agent_hint}\n\n"
            "[REQUEST_CONTEXT]\n"
            f"{context.metadata}\n\n"
            "[REQUEST_PAYLOAD]\n"
            f"{payload}\n\n"
            "[OUTPUT_CONTRACT]\n"
            "Return only one JSON object with this shape:\n"
            '{"agent":"quest_generator"}\n'
            "The agent value MUST be one of ALLOWED_AGENT_IDS. Do not include markdown or explanations."
        )

    def _build_routing_tool_sections(
        self,
        payload: dict[str, Any],
        context: AgentContext,
    ) -> str:
        results = [
            tool.invoke(payload, context)
            for tool in self.tools
        ]
        return "\n\n".join(
            f"[{result.section}]\n{result.content}"
            for result in results
            if result.content
        )
