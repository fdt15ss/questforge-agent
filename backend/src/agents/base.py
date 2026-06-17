"""Base agent contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class AgentContext:
    """Runtime context shared across agent execution."""

    request_id: str
    session_id: str | None = None
    client_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentRunResult:
    """Normalized result produced by an agent."""

    agent: str
    payload: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)


class AgentTool(Protocol):
    """Common read-only tool contract attachable to agents."""

    name: str

    def invoke(
        self,
        payload: dict[str, Any],
        context: AgentContext,
        args: dict[str, Any] | None = None,
    ) -> object:
        """Execute the tool with request payload and agent context."""


class Agent(Protocol):
    """Minimal contract for executable agents."""

    agent_id: str
    tools: tuple[AgentTool, ...]

    def build_prompt(
        self,
        payload: dict[str, Any],
        context: AgentContext,
    ) -> str:
        """Build a prompt for the selected agent."""

    def fallback(
        self,
        payload: dict[str, Any],
        context: AgentContext,
    ) -> AgentRunResult:
        """Build a deterministic response when LLM output is unavailable."""
