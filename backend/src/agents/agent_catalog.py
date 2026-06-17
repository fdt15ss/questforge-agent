"""Deterministic agent catalog used by routing prompts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from agents.base import AgentContext, AgentTool


@dataclass(frozen=True)
class AgentCapability:
    """Short routing support description for one top-level agent."""

    agent_id: str
    summary: str
    when_to_use: str


@dataclass(frozen=True)
class RoutingToolResult:
    """Prompt section returned by a deterministic routing support tool."""

    name: str
    section: str
    content: str


class RoutingSupportTool(AgentTool, Protocol):
    """Read-only tool interface for deterministic routing prompt support."""

    name: str

    def invoke(
        self,
        payload: dict[str, Any],
        context: AgentContext,
        args: dict[str, Any] | None = None,
    ) -> RoutingToolResult:
        """Return one prompt section for routing support."""


TOP_LEVEL_AGENT_CAPABILITIES = (
    AgentCapability(
        agent_id="quest_generator",
        summary="게임 상태 데이터를 바탕으로 생산, 납품, 탐험 퀘스트를 생성한다.",
        when_to_use=(
            "목표, 미션, 온보딩, 진행도, 생산 목표, 납품 목표, 탐험 유도 요청에 사용한다."
        ),
    ),
)


class AgentCatalogTool:
    """Return top-level agent capabilities for orchestrator routing."""

    name = "agent_catalog.get_capabilities"

    def invoke(
        self,
        payload: dict[str, Any],
        context: AgentContext,
        args: dict[str, Any] | None = None,
    ) -> RoutingToolResult:
        return RoutingToolResult(
            name=self.name,
            section="AGENT_CAPABILITIES",
            content=format_top_level_agent_capabilities(),
        )


def get_top_level_agent_capabilities() -> tuple[AgentCapability, ...]:
    """Return top-level agent capabilities in routing order."""

    return TOP_LEVEL_AGENT_CAPABILITIES


def create_default_routing_support_tools() -> tuple[RoutingSupportTool, ...]:
    """Create deterministic tools used to enrich routing prompts."""

    return (AgentCatalogTool(),)


def format_top_level_agent_capabilities() -> str:
    """Return a compact prompt section for top-level routing support."""

    return "\n".join(
        (
            f"- {capability.agent_id}: {capability.summary} "
            f"사용 기준: {capability.when_to_use}"
        )
        for capability in TOP_LEVEL_AGENT_CAPABILITIES
    )
