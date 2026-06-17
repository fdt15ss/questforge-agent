"""Cache, fallback, and validation helpers for the agent pipeline."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import ValidationError

from agents.base import AgentContext, AgentRunResult
from agents.pipeline.state import AgentGraphState
from agents.router import AgentRouter
from protocol.errors import build_error_payload
from protocol.messages import AgentErrorEnvelope, AgentRequestEnvelope


def run_fallback(
    router: AgentRouter,
    state: AgentGraphState,
) -> AgentRunResult:
    agent = router.get(state["selectedLeafAgent"])
    return agent.fallback(state["typedPayload"], state["context"])


def build_cache_key(
    agent: str,
    leaf_agent: str,
    payload: dict[str, Any],
    context: AgentContext,
) -> str:
    raw = json.dumps(
        {
            "agent": agent,
            "leaf_agent": leaf_agent,
            "payload": payload,
            "context": {
                "session_id": context.session_id,
                "client_id": context.client_id,
                "metadata": context.metadata,
            },
        },
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_validation_error(
    exc: ValidationError,
    raw_message: AgentRequestEnvelope | dict[str, Any] | None = None,
) -> dict[str, Any]:
    error = AgentErrorEnvelope(
        request_id=_raw_string_field(raw_message, "request_id"),
        session_id=_raw_string_field(raw_message, "session_id"),
        client_id=_raw_string_field(raw_message, "client_id"),
        agent=_raw_string_field(raw_message, "agent"),
        error=build_error_payload(
            "INVALID_ENVELOPE",
            "Agent request envelope validation failed.",
            details={"errors": exc.errors()},
        )
    )
    return error.model_dump(mode="json")


def _raw_string_field(
    raw_message: AgentRequestEnvelope | dict[str, Any] | None,
    field: str,
) -> str | None:
    if raw_message is None:
        return None
    value = (
        raw_message.get(field)
        if isinstance(raw_message, dict)
        else getattr(raw_message, field, None)
    )
    return value if isinstance(value, str) else None
