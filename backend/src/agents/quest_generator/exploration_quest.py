"""Exploration quest leaf agent.

This leaf builds deterministic exploration quests that can be shown even when the
LLM fails. The server owns objectives, clear conditions, rewards, and counts; the
LLM may only rewrite title and description through quest_text_updates.
"""

from __future__ import annotations

import json
from typing import Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from agents.base import AgentContext, AgentRunResult
from agents.quest_generator.deadlines import quest_deadline, surprise_duration_minutes_from_payload
from agents.quest_generator.rewards import build_quest_rewards
from agents.quest_generator.schemas import QuestResponse
from quest_data.repository import QuestDataRepository
from quest_data.retrieval import retrieve_game_context
from quest_data.vector_context import default_vector_store

DEFAULT_EXPLORATION_QUEST_COUNT = 5
MAX_EXPLORATION_QUEST_COUNT = 10
DEFAULT_QUEST_TYPES = ("daily", "weekly", "surprise")


class ExplorationQuestGraphState(TypedDict, total=False):
    mode: Literal["prompt", "fallback"]
    payload: dict[str, Any]
    context: AgentContext
    quest_count: int
    quest_types: list[str]
    targets: list[dict[str, str]]
    retrieved_game_context: dict[str, Any]
    response_payload: dict[str, Any]
    prompt: str


def _resolve_quest_count(payload: dict[str, Any]) -> int:
    options = payload.get("quest_generation_options")
    nested_count = options.get("count") if isinstance(options, dict) else None
    simple_count = payload.get("quest_count")
    raw_count = nested_count if nested_count is not None else simple_count
    if isinstance(raw_count, int) and 1 <= raw_count <= MAX_EXPLORATION_QUEST_COUNT:
        return raw_count
    return DEFAULT_EXPLORATION_QUEST_COUNT


def _resolve_quest_types(payload: dict[str, Any]) -> list[str]:
    options = payload.get("quest_generation_options")
    raw_types = options.get("quest_types") if isinstance(options, dict) else None
    if not isinstance(raw_types, list):
        return list(DEFAULT_QUEST_TYPES)
    quest_types = [
        quest_type
        for quest_type in raw_types
        if isinstance(quest_type, str) and quest_type in DEFAULT_QUEST_TYPES
    ]
    return quest_types or list(DEFAULT_QUEST_TYPES)


def _text(value: object, default: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return default


def _append_unique_target(
    targets: list[dict[str, str]],
    *,
    target_id: str,
    label: str,
    target_kind: str,
    related_resource_id: str | None = None,
) -> None:
    if not target_id or any(target["id"] == target_id for target in targets):
        return
    target = {
        "id": target_id,
        "label": label or target_id,
        "target_kind": target_kind or "site",
    }
    if related_resource_id:
        target["related_resource_id"] = related_resource_id
    targets.append(target)


def _payload_exploration_targets(payload: dict[str, Any]) -> list[dict[str, str]]:
    raw_targets = payload.get("exploration_targets")
    if not isinstance(raw_targets, list):
        return []

    targets: list[dict[str, str]] = []
    for index, raw_target in enumerate(raw_targets):
        if not isinstance(raw_target, dict):
            continue
        target_id = _text(raw_target.get("id"), f"exploration_target_{index + 1}")
        label = _text(raw_target.get("label"), target_id.replace("_", " ").title())
        target_kind = _text(raw_target.get("target_kind"), "site")
        related_resource_id = raw_target.get("related_resource_id")
        _append_unique_target(
            targets,
            target_id=target_id,
            label=label,
            target_kind=target_kind,
            related_resource_id=related_resource_id if isinstance(related_resource_id, str) else None,
        )
    return targets


def _recent_event_targets(payload: dict[str, Any]) -> list[dict[str, str]]:
    recent_events = payload.get("recent_events")
    if not isinstance(recent_events, list):
        return []

    targets: list[dict[str, str]] = []
    for index, event in enumerate(recent_events[:MAX_EXPLORATION_QUEST_COUNT]):
        if not isinstance(event, str) or not event.strip():
            continue
        label = event.strip()[:60]
        target_kind = "signal" if "signal" in event.lower() else "site"
        _append_unique_target(
            targets,
            target_id=f"exploration_recent_event_{index + 1}",
            label=label,
            target_kind=target_kind,
        )
    return targets


def _main_quest_targets(payload: dict[str, Any]) -> list[dict[str, str]]:
    main_quest = payload.get("current_main_quest")
    if not isinstance(main_quest, dict):
        return []

    label = _text(main_quest.get("title"), _text(main_quest.get("id"), "Main quest site"))
    description = _text(main_quest.get("description"), "")
    target_kind = "signal" if "signal" in f"{label} {description}".lower() else "site"
    return [
        {
            "id": f"exploration_main_{_text(main_quest.get('id'), 'quest')}",
            "label": label,
            "target_kind": target_kind,
        }
    ]


def _scenario_targets(repository: QuestDataRepository) -> list[dict[str, str]]:
    targets: list[dict[str, str]] = []
    for index, row in enumerate(repository.list_scenario_contexts()[:MAX_EXPLORATION_QUEST_COUNT]):
        label = row.theme.strip() or row.context_id
        related_resource_id = row.related_resources[0] if row.related_resources else None
        _append_unique_target(
            targets,
            target_id=f"exploration_{row.context_id}",
            label=label,
            target_kind="site",
            related_resource_id=related_resource_id,
        )
    return targets


def _fallback_targets() -> list[dict[str, str]]:
    return [
        {
            "id": "exploration_signal_ping",
            "label": "약한 구조 신호",
            "target_kind": "signal",
        },
        {
            "id": "exploration_crash_site_survey",
            "label": "추락 지점 조사",
            "target_kind": "site",
        },
        {
            "id": "exploration_resource_scan",
            "label": "자원 광맥 스캔",
            "target_kind": "resource_node",
            "related_resource_id": "resource_copper_ore",
        },
        {
            "id": "exploration_route_check",
            "label": "이동 경로 안전 확인",
            "target_kind": "route",
        },
        {
            "id": "exploration_anomaly_probe",
            "label": "이상 신호 조사",
            "target_kind": "anomaly",
        },
    ]


def _candidate_targets(
    payload: dict[str, Any],
    repository: QuestDataRepository,
) -> list[dict[str, str]]:
    targets: list[dict[str, str]] = []
    for source_targets in (
        _payload_exploration_targets(payload),
        _recent_event_targets(payload),
        _main_quest_targets(payload),
        _scenario_targets(repository),
        _fallback_targets(),
    ):
        for target in source_targets:
            _append_unique_target(
                targets,
                target_id=target["id"],
                label=target["label"],
                target_kind=target["target_kind"],
                related_resource_id=target.get("related_resource_id"),
            )
    return targets[:MAX_EXPLORATION_QUEST_COUNT]


def _target_kind_label(target_kind: str) -> str:
    return {
        "signal": "신호",
        "site": "지점",
        "resource_node": "자원 지점",
        "route": "경로",
        "anomaly": "이상 지점",
    }.get(target_kind, "탐험 대상")


def _quest_title(*, quest_type: str, target: dict[str, str]) -> str:
    label = target["label"]
    if quest_type == "weekly":
        return f"{label} 탐험 경로 작성"
    if quest_type == "surprise":
        return f"{label} 이상 징후 조사"
    return f"{label} 안전 확인"


def _quest_description(*, quest_type: str, target: dict[str, str]) -> str:
    label = target["label"]
    target_kind = _target_kind_label(target["target_kind"])
    if quest_type == "weekly":
        return f"{label} 주변을 짧게 탐험하고 후속 조사가 필요한 {target_kind} 상태를 기록한다."
    if quest_type == "surprise":
        return f"{label} 근처에서 갑작스러운 반응이 감지됐다. 공장 계획에 영향을 주기 전에 {target_kind} 상태를 확인한다."
    return f"{label} 상태를 확인하고 다음 탐험을 진행해도 안전한지 기록한다."


def _main_quest_link(
    *,
    quest_type: str,
    main_quest: object,
    target: dict[str, str],
) -> dict[str, str] | None:
    if not isinstance(main_quest, dict):
        return None
    main_quest_id = main_quest.get("id")
    main_quest_title = main_quest.get("title")
    if not isinstance(main_quest_id, str) or not main_quest_id:
        return None
    if not isinstance(main_quest_title, str) or not main_quest_title:
        return None

    relation_kind = "risk_buffer" if quest_type == "surprise" else "progress_support"
    return {
        "main_quest_id": main_quest_id,
        "main_quest_title": main_quest_title,
        "relation_kind": relation_kind,
        "reason": f"{target['label']} 탐험은 {main_quest_title} 진행에 필요한 위험 요소를 줄인다.",
    }


def _clear_condition_label(*, quest_type: str, target: dict[str, str]) -> str:
    label = target["label"]
    if quest_type == "surprise":
        return f"{label} 이상 징후 조사 완료"
    if quest_type == "weekly":
        return f"{label} 탐험 기록 완료"
    return f"{label} 방문 완료"

def _build_exploration_payload(state: ExplorationQuestGraphState) -> dict[str, Any]:
    quest_count = state["quest_count"]
    quest_types = state.get("quest_types", list(DEFAULT_QUEST_TYPES))
    targets = state.get("targets") or _fallback_targets()
    payload = state.get("payload", {})
    repository = QuestDataRepository()
    surprise_duration_minutes = surprise_duration_minutes_from_payload(payload)

    quests: list[dict[str, Any]] = []
    for index in range(quest_count):
        quest_type = quest_types[index % len(quest_types)]
        generated_at, expires_at = quest_deadline(
            quest_type,
            surprise_duration_minutes=surprise_duration_minutes,
        )
        target = targets[index % len(targets)]
        target_id = target["id"]
        reward_target_id = target.get("related_resource_id", target_id)
        quest: dict[str, Any] = {
            "id": index + 1,
            "type": quest_type,
            "domain": "exploration",
            "title": _quest_title(quest_type=quest_type, target=target),
            "generated_at": generated_at,
            "expires_at": expires_at,
            "description": _quest_description(quest_type=quest_type, target=target),
            "objectives": [
                {
                    "target_item_id": target_id,
                    "quantity": 1,
                }
            ],
            "clear_condition": {
                "mode": "manual",
                "target_item_id": target_id,
                "label": _clear_condition_label(quest_type=quest_type, target=target),
            },
            "rewards": build_quest_rewards(
                quest_type=quest_type,
                target_item_id=reward_target_id,
                payload=payload,
                context=state["context"],
                repository=repository,
            ),
            "metadata": {
                key: value
                for key, value in {
                    "target_kind": target["target_kind"],
                    "related_resource_id": target.get("related_resource_id"),
                }.items()
                if value
            },
        }
        main_quest_link = _main_quest_link(
            quest_type=quest_type,
            main_quest=payload.get("current_main_quest"),
            target=target,
        )
        if main_quest_link is not None:
            quest["main_quest_link"] = main_quest_link
        quests.append(quest)

    return QuestResponse.model_validate({"quests": quests}).model_dump(mode="json")


def build_exploration_quest_graph() -> CompiledStateGraph:
    def normalize_payload(
        state: ExplorationQuestGraphState,
    ) -> ExplorationQuestGraphState:
        payload = state.get("payload", {})
        return {
            "quest_count": _resolve_quest_count(payload),
            "quest_types": _resolve_quest_types(payload),
        }

    def retrieve_context(
        state: ExplorationQuestGraphState,
    ) -> ExplorationQuestGraphState:
        payload = state.get("payload", {})
        repository = QuestDataRepository()
        return {
            "targets": _candidate_targets(payload, repository),
            "retrieved_game_context": retrieve_game_context(
                payload,
                repository,
                vector_store=default_vector_store(),
            ),
        }

    def build_quests(
        state: ExplorationQuestGraphState,
    ) -> ExplorationQuestGraphState:
        return {"response_payload": _build_exploration_payload(state)}

    def validate_response(
        state: ExplorationQuestGraphState,
    ) -> ExplorationQuestGraphState:
        response = QuestResponse.model_validate(state["response_payload"])
        return {"response_payload": response.model_dump(mode="json")}

    graph = StateGraph(ExplorationQuestGraphState)
    graph.add_node("exploration.normalize_payload", normalize_payload)
    graph.add_node("exploration.retrieve_context", retrieve_context)
    graph.add_node("exploration.build_quests", build_quests)
    graph.add_node("exploration.validate_response", validate_response)
    graph.add_edge(START, "exploration.normalize_payload")
    graph.add_edge("exploration.normalize_payload", "exploration.retrieve_context")
    graph.add_edge("exploration.retrieve_context", "exploration.build_quests")
    graph.add_edge("exploration.build_quests", "exploration.validate_response")
    graph.add_edge("exploration.validate_response", END)
    return graph.compile()


class ExplorationQuestAgent:
    agent_id = "quest_generator.exploration_quest"
    tools = ()
    response_schema = QuestResponse

    def __init__(self) -> None:
        self.graph = build_exploration_quest_graph()

    def describe_graph(self) -> str:
        return (
            "StateGraph: START -> exploration.normalize_payload -> "
            "exploration.retrieve_context -> exploration.build_quests -> "
            "exploration.validate_response -> END"
        )

    def build_prompt(self, payload: dict[str, Any], context: AgentContext) -> str:
        state = self.graph.invoke(
            {
                "mode": "prompt",
                "payload": payload,
                "context": context,
            }
        )
        draft_payload = state["response_payload"]
        retrieved_game_context = state["retrieved_game_context"]
        quest_count = len(draft_payload["quests"])
        return (
            "[ROLE]\n"
            "You are an exploration quest generation agent.\n\n"
            "[TASK]\n"
            f"Return exactly {quest_count} quest text updates as one JSON object. "
            "Use the QuestTextUpdate schema. Each update must reference a draft quest id. "
            "Do not return objectives, clear_condition, rewards, metadata, or full quests. "
            "The server will preserve every other field from DRAFT_QUESTS. "
            "You may improve only title and description. Use RETRIEVED_GAME_CONTEXT as "
            "authoritative game knowledge, but do not invent server-owned objectives, clear "
            "conditions, rewards, quantities, or schema fields. The title and description "
            "MUST be written in Korean.\n\n"
            "[DRAFT_QUESTS]\n"
            f"{json.dumps(draft_payload, ensure_ascii=False)}\n\n"
            "[REQUEST_PAYLOAD]\n"
            f"{json.dumps(payload, ensure_ascii=False, default=str)}\n\n"
            "[RETRIEVED_GAME_CONTEXT]\n"
            f"{json.dumps(retrieved_game_context, ensure_ascii=False)}\n\n"
            "[OUTPUT_CONTRACT]\n"
            "Return only one JSON object with this shape:\n"
            '{"quest_text_updates":[{"id":1,"title":"...","description":"..."}]}\n'
            "Do not include quests, objectives, clear_condition, rewards, metadata, markdown, or explanations.\n"
        )

    def fallback(
        self,
        payload: dict[str, Any],
        context: AgentContext,
    ) -> AgentRunResult:
        state = self.graph.invoke(
            {
                "mode": "fallback",
                "payload": payload,
                "context": context,
            }
        )
        return AgentRunResult(
            agent="quest_generator",
            payload=state["response_payload"],
            metadata={
                "fallback": True,
                "sub_agent": self.agent_id,
                "graph": "exploration_quest",
            },
        )
