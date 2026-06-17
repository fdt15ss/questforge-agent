"""Agent message envelope models."""

from __future__ import annotations

from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class AgentRequestEnvelope(BaseModel):
    """Public request envelope accepted by the agent pipeline."""

    model_config = ConfigDict(extra="allow")

    type: Literal["agent.request"] = "agent.request"
    request_id: str = Field(default_factory=lambda: str(uuid4()))
    session_id: str | None = None
    client_id: str | None = None
    agent: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)


class AgentResponseEnvelope(BaseModel):
    """Public response envelope returned by the agent pipeline."""

    type: Literal["agent.response"] = "agent.response"
    request_id: str
    session_id: str | None = None
    client_id: str | None = None
    agent: str
    payload: dict[str, Any]
    streams: list[dict[str, Any]] = Field(default_factory=list)


class AgentErrorEnvelope(BaseModel):
    """Public error envelope returned by the agent pipeline."""

    type: Literal["agent.error"] = "agent.error"
    request_id: str | None = None
    session_id: str | None = None
    client_id: str | None = None
    agent: str | None = None
    error: dict[str, Any]
