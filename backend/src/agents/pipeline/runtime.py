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
from agents.quest_generator.rewards import build_quest_rewards
from agents.quest_generator.schemas import QuestPlanEnvelope, QuestResponse
from agents.router import AgentRouter, UnknownAgentError, create_default_agent_router
from cache.response_cache import ResponseCache
from llm.adapter import LLMAdapter, create_llm_adapter
from llm.settings import LLMModelSlot, LLMSettings
from protocol.errors import build_error_payload
from quest_data.repository import QuestDataRepository
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


def _expected_quest_response_count(payload: dict[str, Any]) -> int | None:
    options = payload.get("quest_generation_options")
    if not isinstance(options, dict):
        options = {}

    raw_domain_counts = options.get("domain_counts")
    if isinstance(raw_domain_counts, dict):
        domain_counts = [
            count
            for count in raw_domain_counts.values()
            if isinstance(count, int) and 1 <= count <= 10
        ]
        if domain_counts:
            return sum(domain_counts)

    raw_count = options.get("count")
    if raw_count is None:
        raw_count = payload.get("quest_count")
    if isinstance(raw_count, int) and 1 <= raw_count <= 10:
        return raw_count
    return None




def _has_reward_options(payload: dict[str, Any]) -> bool:
    options = payload.get("quest_generation_options")
    return isinstance(options, dict) and isinstance(options.get("reward_options"), dict)


def _llm_payload_contains_rewards(payload: dict[str, Any]) -> bool:
    quests = payload.get("quests")
    if not isinstance(quests, list):
        return False
    return any(isinstance(quest, dict) and "rewards" in quest for quest in quests)


def _should_validate_quest_llm_payload(
    payload: dict[str, Any],
    request_payload: dict[str, Any],
    expected_count: int | None,
) -> bool:
    return (
        expected_count is not None
        or _has_reward_options(request_payload)
        or _llm_payload_contains_rewards(payload)
    )




def _quest_target_item_id(quest: Any) -> str:
    if not quest.objectives:
        return ""
    return quest.objectives[0].target_item_id


def _validate_xp_credit_rewards(
    response: QuestResponse,
    *,
    request_payload: dict[str, Any],
    context: AgentContext,
) -> None:
    repository = QuestDataRepository()
    for quest in response.quests:
        target_item_id = _quest_target_item_id(quest)
        expected_rewards = build_quest_rewards(
            quest_type=quest.type,
            target_item_id=target_item_id,
            payload=request_payload,
            context=context,
            repository=repository,
        )
        expected_by_type = {
            reward["reward_type"]: reward
            for reward in expected_rewards
            if reward["reward_type"] in {"xp", "credits"}
        }
        actual_by_type = {
            reward.reward_type: reward
            for reward in quest.rewards
            if reward.reward_type in {"xp", "credits"}
        }
        if set(actual_by_type) != set(expected_by_type):
            raise ValueError("Quest XP/credits reward types do not match reward_options")
        for reward_type, expected_reward in expected_by_type.items():
            actual_reward = actual_by_type[reward_type]
            if actual_reward.amount != expected_reward["amount"]:
                raise ValueError(f"Quest {reward_type} reward amount does not match CSV rule")
            if actual_reward.source_rule_id != expected_reward["source_rule_id"]:
                raise ValueError(f"Quest {reward_type} reward rule does not match CSV rule")

def _is_quest_plan_payload(payload: dict[str, Any]) -> bool:
    return isinstance(payload.get("quest_plan"), dict)


def _is_quest_text_update_payload(payload: dict[str, Any]) -> bool:
    return isinstance(payload.get("quest_text_updates"), list)


def _merge_quest_plan(
    *,
    llm_payload: dict[str, Any],
    draft_payload: dict[str, Any],
) -> dict[str, Any]:
    plan = QuestPlanEnvelope.model_validate(llm_payload).quest_plan
    response = QuestResponse.model_validate(draft_payload)
    merged_payload = response.model_dump(mode="json")
    quests_by_id = {
        quest["id"]: quest
        for quest in merged_payload["quests"]
        if isinstance(quest.get("id"), int)
    }

    draft_quest_ids = set(quests_by_id)
    intent_ids = [intent.id for intent in plan.quest_intents]
    if len(intent_ids) != len(merged_payload["quests"]):
        raise ValueError("quest_plan must include exactly one intent per draft quest")
    if len(set(intent_ids)) != len(intent_ids) or set(intent_ids) != draft_quest_ids:
        raise ValueError("quest_plan intent ids must match draft quest ids")

    intent_domain_counts = {"production": 0, "delivery": 0}
    for intent in plan.quest_intents:
        intent_domain_counts[intent.domain] += 1
    if (
        intent_domain_counts["production"] != plan.domain_mix.production
        or intent_domain_counts["delivery"] != plan.domain_mix.delivery
    ):
        raise ValueError("quest_plan domain_mix must match intent domains")

    for intent in plan.quest_intents:
        quest = quests_by_id.get(intent.id)
        if quest is None:
            raise ValueError("quest_plan intent id must match a draft quest")
        if quest.get("domain") != intent.domain:
            raise ValueError("quest_plan intent domain must match draft quest")
        objectives = quest.get("objectives")
        if not isinstance(objectives, list) or not objectives:
            raise ValueError("draft quest must include objectives")
        first_objective = objectives[0]
        if not isinstance(first_objective, dict):
            raise ValueError("draft quest objective must be an object")
        if first_objective.get("target_item_id") != intent.target_item_id:
            raise ValueError("quest_plan target_item_id must match draft quest")

        if intent.title:
            quest["title"] = intent.title.strip()
        if intent.description:
            quest["description"] = intent.description.strip()

        metadata = quest.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
            quest["metadata"] = metadata
        metadata["llm_intent"] = intent.intent.strip()
        metadata["llm_reason"] = intent.reason.strip()

        main_quest_link = quest.get("main_quest_link")
        if (
            intent.main_quest_link_reason
            and isinstance(main_quest_link, dict)
        ):
            main_quest_link["reason"] = intent.main_quest_link_reason.strip()

    response_metadata = merged_payload.get("metadata")
    if not isinstance(response_metadata, dict):
        response_metadata = {}
        merged_payload["metadata"] = response_metadata
    response_metadata["quest_plan_analysis"] = plan.analysis.strip()
    response_metadata["quest_plan_domain_mix"] = (
        f"production:{plan.domain_mix.production},delivery:{plan.domain_mix.delivery}"
    )

    return QuestResponse.model_validate(merged_payload).model_dump(mode="json")


def _merge_quest_text_updates(
    *,
    llm_payload: dict[str, Any],
    draft_payload: dict[str, Any],
) -> dict[str, Any]:
    response = QuestResponse.model_validate(draft_payload)
    merged_payload = response.model_dump(mode="json")
    quests_by_id = {
        quest["id"]: quest
        for quest in merged_payload["quests"]
        if isinstance(quest.get("id"), int)
    }

    updates = llm_payload.get("quest_text_updates")
    if not isinstance(updates, list):
        raise ValueError("quest_text_updates must be a list")

    for update in updates:
        if not isinstance(update, dict):
            raise ValueError("each quest_text_updates item must be an object")
        quest_id = update.get("id")
        if not isinstance(quest_id, int) or quest_id not in quests_by_id:
            raise ValueError("quest_text_updates item id must match a draft quest")
        quest = quests_by_id[quest_id]

        title = update.get("title")
        if isinstance(title, str) and title.strip():
            quest["title"] = title.strip()

        description = update.get("description")
        if isinstance(description, str) and description.strip():
            quest["description"] = description.strip()

        reason = update.get("main_quest_link_reason")
        main_quest_link = quest.get("main_quest_link")
        if (
            isinstance(reason, str)
            and reason.strip()
            and isinstance(main_quest_link, dict)
        ):
            main_quest_link["reason"] = reason.strip()

    return QuestResponse.model_validate(merged_payload).model_dump(mode="json")

def _validate_quest_llm_payload(
    payload: dict[str, Any],
    *,
    expected_count: int | None,
    request_payload: dict[str, Any],
    context: AgentContext,
) -> dict[str, Any]:
    response = QuestResponse.model_validate(payload)
    if expected_count is not None and len(response.quests) != expected_count:
        raise ValueError(
            f"QuestResponse must contain exactly {expected_count} quests"
        )
    _validate_xp_credit_rewards(
        response,
        request_payload=request_payload,
        context=context,
    )
    return response.model_dump(mode="json")


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

            try:
                agent = agent_router.get(state["selectedLeafAgent"])
                expected_count = _expected_quest_response_count(state["typedPayload"])
                if expected_count is None and state.get("selectedLeafAgent") == "quest_generator":
                    expected_count = 5
                if getattr(agent, "response_schema", None) is QuestResponse:
                    if _is_quest_plan_payload(payload):
                        draft = agent.fallback(state["typedPayload"], state["context"])
                        payload = _merge_quest_plan(
                            llm_payload=payload,
                            draft_payload=draft.payload,
                        )
                    elif _is_quest_text_update_payload(payload):
                        draft = agent.fallback(state["typedPayload"], state["context"])
                        payload = _merge_quest_text_updates(
                            llm_payload=payload,
                            draft_payload=draft.payload,
                        )
                    if _should_validate_quest_llm_payload(
                        payload,
                        state["typedPayload"],
                        expected_count,
                    ):
                        payload = _validate_quest_llm_payload(
                            payload,
                            expected_count=expected_count,
                            request_payload=state["typedPayload"],
                            context=state["context"],
                        )
            except (UnknownAgentError, ValidationError, ValueError) as exc:
                return {
                    "llmParseFailed": True,
                    "fallbackReason": "invalid_llm_response",
                    "llmAttempts": _mark_latest_llm_attempt(
                        state,
                        "invalid_schema",
                        f"{raw}\n{exc}",
                    ),
                }
            metadata = payload.pop("metadata", None)
            if not isinstance(metadata, dict):
                metadata = {}
            metadata["llm"] = "used"
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
