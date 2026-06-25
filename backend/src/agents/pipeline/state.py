"""Shared state types for the agent pipeline."""

from __future__ import annotations

from typing import Annotated, Any, Literal, TypedDict

from langgraph.graph import add_messages

from agents.base import AgentContext
from protocol.messages import AgentRequestEnvelope

TopRoute = Literal[
    "quest_generator",
    "error",
]


class AgentGraphState(TypedDict, total=False):
    """Shared LangGraph state for one agent request."""

    messages: Annotated[list[Any], add_messages]
    envelope: AgentRequestEnvelope
    context: AgentContext
    selectedAgent: str
    selectedLeafAgent: str
    typedPayload: dict[str, Any]
    cacheKey: str
    cachedPayload: dict[str, Any]
    cachedMetadata: dict[str, Any]
    prompt: str
    promptMessages: list[dict[str, str]]
    promptBatches: list[str]
    routingPrompt: str
    routingRaw: str | None
    llmRaw: str | None
    llmSlot: str
    llmProvider: str
    llmModel: str
    llmParseFailed: bool
    llmAttempts: list[dict[str, Any]]
    toolCallRequest: dict[str, Any]
    toolFollowupPrompt: str
    toolCalls: list[dict[str, Any]]
    fallbackReason: str
    middlewareLogs: list[dict[str, Any]]
    responsePayload: dict[str, Any]
    responseMetadata: dict[str, Any]
    streams: list[dict[str, Any]]
    error: dict[str, Any]
    responseEnvelope: dict[str, Any]
