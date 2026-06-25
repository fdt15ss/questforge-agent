from __future__ import annotations

import pytest

from agents.base import AgentContext, AgentRunResult
from agents.router import AgentRouter, UnknownAgentError, create_default_agent_router
from cache.response_cache import ResponseCache
from llm.adapter import NoopLLMAdapter
from protocol.errors import build_error_payload
from protocol.messages import (
    AgentErrorEnvelope,
    AgentRequestEnvelope,
    AgentResponseEnvelope,
)


class DummyAgent:
    agent_id = "dummy"

    def build_prompt(self, payload: dict[str, object], context: AgentContext) -> str:
        return "dummy prompt"

    def fallback(
        self,
        payload: dict[str, object],
        context: AgentContext,
    ) -> AgentRunResult:
        return AgentRunResult(agent=self.agent_id, payload={"ok": True})


def test_agent_request_envelope_defaults_and_allows_extra_fields() -> None:
    envelope = AgentRequestEnvelope.model_validate(
        {
            "type": "agent.request",
            "payload": {"message": "hello"},
            "trace_id": "trace-1",
        }
    )

    assert envelope.request_id
    assert envelope.payload == {"message": "hello"}
    assert envelope.context == {}
    assert envelope.model_extra == {"trace_id": "trace-1"}


def test_agent_response_and_error_envelopes_dump_protocol_shapes() -> None:
    response = AgentResponseEnvelope(
        request_id="request-1",
        session_id="session-1",
        client_id="client-1",
        agent="quest_generator",
        payload={"summary": "ok"},
    )
    error = AgentErrorEnvelope(
        request_id="request-2",
        agent="quest_generator",
        error=build_error_payload("INVALID_INPUT", "Bad input"),
    )

    assert response.model_dump(mode="json") == {
        "type": "agent.response",
        "request_id": "request-1",
        "session_id": "session-1",
        "client_id": "client-1",
        "agent": "quest_generator",
        "payload": {"summary": "ok"},
        "streams": [],
    }
    assert error.error == {
        "code": "INVALID_INPUT",
        "message": "Bad input",
        "details": {},
    }


def test_build_error_payload_preserves_details() -> None:
    assert build_error_payload(
        "INVALID_SUB_AGENT",
        "Invalid sub-agent",
        details={"sub_agent": "unknown"},
    ) == {
        "code": "INVALID_SUB_AGENT",
        "message": "Invalid sub-agent",
        "details": {"sub_agent": "unknown"},
    }


def test_agent_router_registers_and_retrieves_agent() -> None:
    router = AgentRouter()
    agent = DummyAgent()

    router.register(agent)

    assert router.has("dummy") is True
    assert router.get("dummy") is agent
    assert router.list_agent_ids() == ["dummy"]


def test_agent_router_raises_for_unknown_agent() -> None:
    router = AgentRouter()

    with pytest.raises(UnknownAgentError, match="Unknown agent: missing"):
        router.get("missing")


def test_default_agent_router_registers_quest_top_level_and_leaf_agents() -> None:
    router = create_default_agent_router()

    assert router.list_agent_ids() == [
        "quest_generator",
        "quest_generator.delivery_quest",
        "quest_generator.exploration_quest",
        "quest_generator.production_quest",
    ]


def test_response_cache_returns_stored_payload_by_key() -> None:
    cache = ResponseCache()
    payload = {"summary": "cached"}

    cache.set("cache-key", payload)

    assert cache.get("cache-key") is payload
    assert cache.get("missing") is None


def test_noop_llm_adapter_forces_fallback_path() -> None:
    assert NoopLLMAdapter().invoke("prompt") is None
