"""Common AI agent execution pipeline."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from langgraph.graph import StateGraph
from langgraph.graph.state import CompiledStateGraph
from pydantic import ValidationError

from agents.base import AgentContext
from agents.orchestrator import TOP_LEVEL_AGENT_IDS, OrchestratorAgent
from agents.pipeline.graph_edges import wire_agent_graph
from agents.pipeline.llm_fallback import (
    LLMCallSlot,
    build_llm_call_slots,
    invoke_llm_call_slot,
)
from agents.pipeline.middleware import (
    append_middleware_log,
    build_current_model_metadata,
)
from agents.pipeline.state import AgentGraphState
from agents.pipeline.tool_node import (
    append_tool_metadata,
    build_agent_tool_node,
    build_tool_followup_prompt,
    build_tool_node_input,
)
from agents.pipeline.utils import (
    build_cache_key,
    build_validation_error,
    run_fallback,
)
from agents.quest_generator.agent import QUEST_SUB_AGENT_IDS, QuestGeneratorAgent
from agents.router import AgentRouter, UnknownAgentError, create_default_agent_router
from cache.response_cache import ResponseCache
from llm.adapter import LLMAdapter, create_llm_adapter
from llm.settings import LLMModelSlot, LLMSettings
from protocol.errors import build_error_payload
from protocol.messages import (
    AgentErrorEnvelope,
    AgentRequestEnvelope,
    AgentResponseEnvelope,
)


class _FallbackRoutingLLM:
    """LLM adapter wrapper that tries multiple slots sequentially on failure."""

    def __init__(self, slots: list[LLMCallSlot]) -> None:
        self.slots = slots

    def invoke(self, prompt: str) -> str | None:
        for slot in self.slots:
            res = slot.adapter.invoke(prompt)
            if res is not None:
                return res
        return None


def _clean_routing_decision(raw: str | None) -> str:
    """Clean raw routing model output by stripping whitespace and outer JSON quotes."""
    if not raw:
        return ""
    cleaned = raw.strip()
    parsed = _parse_llm_json_object(cleaned)
    if parsed is not None:
        for key in ("agent", "sub_agent", "selectedAgent", "selectedLeafAgent"):
            value = parsed.get(key)
            if isinstance(value, str):
                return value.strip()
    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in {'"', "'"}:
        cleaned = cleaned[1:-1]
    return cleaned.strip()


def _parse_llm_json_object(raw: str | None) -> dict[str, Any] | None:
    """LLM 원문에서 응답 JSON object를 꺼냅니다.

    Gemini나 OpenAI는 프롬프트로 "JSON만 반환"이라고 지시해도 종종
    ```json 코드블록이나 짧은 설명 문장을 함께 붙입니다. 서버 계약은 여전히
    JSON object 하나이지만, 사용자가 바로 에러를 받지 않도록 원문 안에서
    첫 번째 JSON object만 추출해 봅니다.
    """

    if not raw:
        return None

    decoder = json.JSONDecoder()
    cleaned = raw.strip()
    for index, char in enumerate(cleaned):
        if char != "{":
            continue
        try:
            parsed, _ = decoder.raw_decode(cleaned[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _mark_latest_llm_attempt(
    state: AgentGraphState,
    status: str,
    raw: str | None = None,
) -> list[dict[str, Any]]:
    """Mark the latest LLM attempt with the final parse status."""

    attempts = [dict(attempt) for attempt in state.get("llmAttempts", [])]
    if attempts:
        attempts[-1]["status"] = status
        if raw:
            attempts[-1]["rawPreview"] = " ".join(raw.split())[:240]
    return attempts


class AgentPipeline:
    """LangGraph-backed execution pipeline for agent requests."""

    def __init__(
        self,
        *,
        router: AgentRouter | None = None,
        cache: ResponseCache | None = None,
        llm: LLMAdapter | None = None,
        llm_settings: LLMSettings | None = None,
        llm_adapter_factory: Callable[[LLMModelSlot], LLMAdapter] = create_llm_adapter,
    ) -> None:
        self.router = router or create_default_agent_router()
        self.cache = cache or ResponseCache()
        self.llm = llm
        self.llm_settings = llm_settings
        self.llm_adapter_factory = llm_adapter_factory
        self.graph = self._build_graph()

    def run(self, message: AgentRequestEnvelope | dict[str, Any]) -> dict[str, Any]:
        """Run one request through the compiled graph."""

        try:
            envelope = (
                message
                if isinstance(message, AgentRequestEnvelope)
                else AgentRequestEnvelope.model_validate(message)
            )
        except ValidationError as exc:
            return build_validation_error(exc, message)

        state = self.graph.invoke({"envelope": envelope})
        return state["responseEnvelope"]

    def _build_graph(self) -> CompiledStateGraph:
        """Build and compile the LangGraph agent pipeline."""

        agent_router = self.router
        response_cache = self.cache
        llm_slots = build_llm_call_slots(
            llm=self.llm,
            settings=self.llm_settings,
            adapter_factory=self.llm_adapter_factory,
        )
        llm_slots_by_name = {slot.name: slot for slot in llm_slots}
        routing_llm = self.llm or _FallbackRoutingLLM(list(llm_slots))
        orchestrator = OrchestratorAgent()
        quest_generator = QuestGeneratorAgent()

        def build_context(state: AgentGraphState) -> AgentGraphState:
            envelope = state["envelope"]
            return {
                "context": AgentContext(
                    request_id=envelope.request_id,
                    session_id=envelope.session_id,
                    client_id=envelope.client_id,
                    metadata=envelope.context,
                ),
                "typedPayload": envelope.payload,
                "streams": [],
            }

        def log_agent_started(state: AgentGraphState) -> AgentGraphState:
            return append_middleware_log(
                state,
                "agent.middleware.before",
                "agent_started",
                {
                    "selectedAgent": state["selectedAgent"],
                    "selectedLeafAgent": state["selectedLeafAgent"],
                },
            )

        def validate_envelope(state: AgentGraphState) -> AgentGraphState:
            envelope = state["envelope"]
            if envelope.type != "agent.request":
                return {
                    "error": build_error_payload(
                        "INVALID_MESSAGE_TYPE",
                        "Only agent.request messages can enter the agent pipeline.",
                        details={"type": envelope.type},
                    )
                }
            if not isinstance(envelope.payload, dict):
                return {
                    "error": build_error_payload(
                        "INVALID_PAYLOAD",
                        "Agent request payload must be an object.",
                    )
                }
            return {}

        def route_top_agent(state: AgentGraphState) -> AgentGraphState:
            if state.get("error"):
                return {}

            envelope = state["envelope"]
            context = state["context"]
            payload = state["typedPayload"]

            routing_prompt = orchestrator.build_routing_prompt(
                payload,
                context,
                requested_agent=envelope.agent,
            )
            routing_raw = routing_llm.invoke(routing_prompt)
            return {
                "routingPrompt": routing_prompt,
                "routingRaw": routing_raw,
                "selectedAgent": _clean_routing_decision(routing_raw),
            }

        def route_quest_sub_agent(state: AgentGraphState) -> AgentGraphState:
            explicit_sub_agent = state["typedPayload"].get("sub_agent")
            if explicit_sub_agent is not None:
                if (
                    isinstance(explicit_sub_agent, str)
                    and explicit_sub_agent in QUEST_SUB_AGENT_IDS
                ):
                    return {"selectedLeafAgent": explicit_sub_agent}
                return {
                    "error": build_error_payload(
                        "INVALID_SUB_AGENT",
                        "Explicit sub_agent is not valid for quest_generator.",
                        details={"sub_agent": explicit_sub_agent},
                    )
                }

            if state["envelope"].agent == "quest_generator":
                return {"selectedLeafAgent": "quest_generator"}

            routing_prompt = quest_generator.build_routing_prompt(
                state["typedPayload"],
                state["context"],
            )
            routing_raw = routing_llm.invoke(routing_prompt)
            return {
                "routingPrompt": routing_prompt,
                "routingRaw": routing_raw,
                "selectedLeafAgent": _clean_routing_decision(routing_raw),
            }

        def cache_lookup(state: AgentGraphState) -> AgentGraphState:
            cache_key = build_cache_key(
                state["selectedAgent"],
                state["selectedLeafAgent"],
                state["typedPayload"],
                state["context"],
            )
            cached_entry = response_cache.get_entry(cache_key)
            output: AgentGraphState = {"cacheKey": cache_key}
            if cached_entry is not None:
                output["cachedPayload"] = cached_entry.payload
                output["cachedMetadata"] = cached_entry.metadata
            return output

        def build_cached_response(state: AgentGraphState) -> AgentGraphState:
            return {
                "responsePayload": state["cachedPayload"],
                "responseMetadata": {
                    **state.get("cachedMetadata", {}),
                    "cache": "hit",
                },
            }

        def build_prompt(state: AgentGraphState) -> AgentGraphState:
            try:
                agent = agent_router.get(state["selectedLeafAgent"])
            except UnknownAgentError:
                return {
                    "error": build_error_payload(
                        "UNKNOWN_AGENT",
                        f"Unknown leaf agent: {state['selectedLeafAgent']}",
                        details={"agent": state["selectedLeafAgent"]},
                    )
                }
            prompt = agent.build_prompt(state["typedPayload"], state["context"])
            output: AgentGraphState = {"prompt": prompt}
            build_prompt_messages = getattr(agent, "build_prompt_messages", None)
            if callable(build_prompt_messages):
                output["promptMessages"] = build_prompt_messages(
                    state["typedPayload"],
                    state["context"],
                )
            return output

        def call_llm_default(state: AgentGraphState) -> AgentGraphState:
            if state.get("error"):
                return {}
            return invoke_llm_call_slot(
                llm_slots[0],
                state["prompt"],
                state.get("promptMessages"),
                state.get("llmAttempts"),
            )

        def call_llm_fallback1(state: AgentGraphState) -> AgentGraphState:
            if state.get("error"):
                return {}
            return invoke_llm_call_slot(
                llm_slots[1],
                state["prompt"],
                state.get("promptMessages"),
                state.get("llmAttempts"),
            )

        def call_llm_fallback2(state: AgentGraphState) -> AgentGraphState:
            if state.get("error"):
                return {}
            return invoke_llm_call_slot(
                llm_slots[2],
                state["prompt"],
                state.get("promptMessages"),
                state.get("llmAttempts"),
            )

        def call_llm_tool_followup(state: AgentGraphState) -> AgentGraphState:
            if state.get("error"):
                return {}
            slot = llm_slots_by_name.get(state.get("llmSlot", ""))
            if slot is None:
                return {}
            return invoke_llm_call_slot(
                slot,
                state["toolFollowupPrompt"],
                previous_attempts=state.get("llmAttempts"),
            )

        def parse_llm_response(state: AgentGraphState) -> AgentGraphState:
            raw = state.get("llmRaw")
            if not raw:
                return {}

            payload = _parse_llm_json_object(raw)
            if payload is None:
                return {
                    "llmParseFailed": True,
                    "fallbackReason": "invalid_llm_response",
                    "llmAttempts": _mark_latest_llm_attempt(
                        state,
                        "invalid_json",
                        raw,
                    ),
                }

            metadata = {"llm": "used"}
            attempts = _mark_latest_llm_attempt(state, "parsed_json")
            if attempts:
                metadata["llmAttempts"] = attempts
            if state.get("llmSlot"):
                metadata["llmSlot"] = state["llmSlot"]
            if state.get("llmProvider"):
                metadata["llmProvider"] = state["llmProvider"]
            if state.get("llmModel"):
                metadata["llmModel"] = state["llmModel"]
            current_model = build_current_model_metadata(state)
            if current_model is not None:
                metadata["currentModel"] = current_model
            metadata = {
                **metadata,
                **append_tool_metadata(state),
            }
            return {"responsePayload": payload, "responseMetadata": metadata}

        def build_fallback(state: AgentGraphState) -> AgentGraphState:
            result = run_fallback(agent_router, state)
            metadata = dict(result.metadata)
            fallback_reason = state.get("fallbackReason") or "llm_unavailable"
            metadata["fallbackReason"] = fallback_reason
            if state.get("llmAttempts"):
                metadata["llmAttempts"] = state["llmAttempts"]
            current_model = build_current_model_metadata(state)
            if current_model is not None:
                metadata["currentModel"] = current_model
            metadata = {
                **metadata,
                **append_tool_metadata(state),
            }
            output: AgentGraphState = {
                "fallbackReason": "llm_unavailable",
                "responsePayload": result.payload,
                "responseMetadata": metadata,
            }
            return {
                **output,
                **append_middleware_log(
                    state,
                    "agent.middleware.fallback",
                    "deterministic_fallback",
                    {
                        "reason": fallback_reason,
                        "selectedAgent": state["selectedAgent"],
                        "selectedLeafAgent": state["selectedLeafAgent"],
                    },
                ),
            }

        def validate_response_schema(state: AgentGraphState) -> AgentGraphState:
            payload = state.get("responsePayload")
            if not isinstance(payload, dict):
                return {
                    "error": build_error_payload(
                        "INVALID_AGENT_RESPONSE",
                        "Agent response payload must be an object.",
                    )
                }
            return {}

        def cache_write(state: AgentGraphState) -> AgentGraphState:
            if not state.get("cacheKey"):
                return {}

            response_cache.set(
                state["cacheKey"],
                state["responsePayload"],
                state.get("responseMetadata", {}),
            )
            return {}

        def log_agent_finished(state: AgentGraphState) -> AgentGraphState:
            return append_middleware_log(
                state,
                "agent.middleware.after",
                "agent_finished",
                {
                    "selectedAgent": state["selectedAgent"],
                    "selectedLeafAgent": state["selectedLeafAgent"],
                },
            )

        def build_agent_response(state: AgentGraphState) -> AgentGraphState:
            envelope = state["envelope"]
            metadata = {
                **state.get("responseMetadata", {}),
                "selectedAgent": state["selectedAgent"],
                "selectedLeafAgent": state["selectedLeafAgent"],
            }
            if state.get("middlewareLogs"):
                metadata["middlewareLogs"] = state["middlewareLogs"]
            response = AgentResponseEnvelope(
                request_id=envelope.request_id,
                session_id=envelope.session_id,
                client_id=envelope.client_id,
                agent=state["selectedAgent"],
                payload={
                    **state["responsePayload"],
                    "metadata": metadata,
                },
                streams=state.get("streams", []),
            )
            return {"responseEnvelope": response.model_dump(mode="json")}

        def build_agent_error(state: AgentGraphState) -> AgentGraphState:
            envelope = state["envelope"]
            selected_agent = state.get("selectedAgent")
            response_agent = (
                selected_agent if selected_agent in TOP_LEVEL_AGENT_IDS else envelope.agent
            )
            default_error = build_error_payload(
                "ROUTING_UNAVAILABLE",
                "Agent routing requires a valid orchestrator model decision.",
            )
            response = AgentErrorEnvelope(
                request_id=envelope.request_id,
                session_id=envelope.session_id,
                client_id=envelope.client_id,
                agent=response_agent,
                error=state.get("error") or default_error,
            )
            return {"responseEnvelope": response.model_dump(mode="json")}

        graph = StateGraph(AgentGraphState)
        graph.add_node("build_context", build_context)
        graph.add_node("agent.middleware.before", log_agent_started)
        graph.add_node("validate_envelope", validate_envelope)
        graph.add_node("route_top_agent", route_top_agent)
        graph.add_node("quest_generator.route_sub_agent", route_quest_sub_agent)
        graph.add_node("cache_lookup", cache_lookup)
        graph.add_node("build_cached_response", build_cached_response)
        graph.add_node("build_prompt", build_prompt)
        graph.add_node("call_llm.default", call_llm_default)
        graph.add_node("call_llm.fallback1", call_llm_fallback1)
        graph.add_node("call_llm.fallback2", call_llm_fallback2)
        graph.add_node("prepare_tool_call", build_tool_node_input(agent_router))
        graph.add_node("agent.tool_node", build_agent_tool_node(agent_router))
        graph.add_node("build_tool_followup_prompt", build_tool_followup_prompt)
        graph.add_node("call_llm.tool_followup", call_llm_tool_followup)
        graph.add_node("parse_llm_response", parse_llm_response)
        graph.add_node("agent.middleware.fallback", build_fallback)
        graph.add_node("validate_response_schema", validate_response_schema)
        graph.add_node("cache_write", cache_write)
        graph.add_node("agent.middleware.after", log_agent_finished)
        graph.add_node("build_agent_response", build_agent_response)
        graph.add_node("build_agent_error", build_agent_error)

        wire_agent_graph(graph)
        return graph.compile()

def run_agent_pipeline(message: AgentRequestEnvelope | dict[str, Any]) -> dict[str, Any]:
    """Run one message through a default agent pipeline."""

    try:
        return AgentPipeline().run(message)
    except ValidationError as exc:
        return build_validation_error(exc, message)
