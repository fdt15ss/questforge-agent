"""LangGraph로 생산 퀘스트를 직접 만드는 leaf agent입니다.

이 파일의 핵심 아이디어는 간단합니다.

1. 요청 payload에서 원하는 퀘스트 개수와 보유 자원 정보를 읽습니다.
2. `QuestDataRepository`로 CSV 게임 데이터를 조회해 참고할 context를 모읍니다.
3. LangGraph의 각 node가 차례대로 작은 일을 처리합니다.
4. 마지막에는 항상 `QuestResponse` schema를 통과한 dict만 반환합니다.

예전 구현은 미리 준비된 퀘스트 후보 10개 중에서 LLM이 id를 고르는 방식이었습니다.
지금 구현은 서버가 구조를 직접 만들고, LLM은 제목과 설명을 다듬는 역할만 맡깁니다.
그래서 LLM이 실패해도 같은 graph를 통해 deterministic fallback 응답을 만들 수 있습니다.
"""

from __future__ import annotations

import json
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from agents.base import AgentContext, AgentRunResult
from agents.quest_generator.schemas import QuestResponse
from quest_data.repository import QuestDataRepository
from quest_data.schemas import ScenarioContextRow

DEFAULT_PRODUCTION_QUEST_COUNT = 5
MAX_PRODUCTION_QUEST_COUNT = 10
DEFAULT_QUEST_TYPES = ("daily", "weekly", "surprise")


class ProductionQuestGraphState(TypedDict, total=False):
    """생산 퀘스트 graph node들이 서로 주고받는 상태입니다.

    LangGraph는 dict 형태의 state를 node 사이에 전달합니다. 각 node는 자신이
    새로 계산한 일부 key만 반환하고, LangGraph가 이전 state와 합쳐 줍니다.
    """

    payload: dict[str, Any]
    context: AgentContext
    quest_count: int
    quest_types: list[str]
    main_quest: dict[str, Any]
    main_quest_deficits: dict[str, int]
    retrieved_context: dict[str, Any]
    response_payload: dict[str, Any]


def _resolve_quest_count(payload: dict[str, Any]) -> int:
    """payload에서 생성할 퀘스트 개수를 안전하게 읽습니다.

    클라이언트는 자세한 옵션인 `quest_generation_options.count`를 보낼 수 있고,
    간단히 `quest_count`만 보낼 수도 있습니다. 둘 다 없거나 값이 너무 크면
    기본값 5를 씁니다. 이 제한은 LLM prompt와 WebSocket 응답이 과도하게
    커지는 것을 막기 위한 안전장치입니다.
    """

    options = payload.get("quest_generation_options")
    nested_count = options.get("count") if isinstance(options, dict) else None
    simple_count = payload.get("quest_count")
    raw_count = nested_count if nested_count is not None else simple_count
    if isinstance(raw_count, int) and 1 <= raw_count <= MAX_PRODUCTION_QUEST_COUNT:
        return raw_count
    return DEFAULT_PRODUCTION_QUEST_COUNT


def _resolve_quest_types(payload: dict[str, Any]) -> list[str]:
    """요청 payload에서 생성을 허용할 퀘스트 타입 목록을 읽습니다.

    클라이언트가 `quest_generation_options.quest_types`를 보내면 그 안의 값만
    사용합니다. 잘못된 값만 들어오거나 필드가 없으면 기본값인 일일/주간/깜짝
    세 타입을 모두 사용합니다.
    """

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


def _current_main_quest(payload: dict[str, Any]) -> dict[str, Any]:
    """선택 입력인 `current_main_quest`를 안전하게 dict로 꺼냅니다."""

    current_main_quest = payload.get("current_main_quest")
    return current_main_quest if isinstance(current_main_quest, dict) else {}


def _main_quest_link_enabled(payload: dict[str, Any]) -> bool:
    """현재 요청에서 메인 퀘스트 연결 정보를 만들지 판단합니다."""

    if not _current_main_quest(payload):
        return False
    options = payload.get("quest_generation_options")
    if not isinstance(options, dict):
        return True
    return options.get("link_to_main_quest") is not False


def _main_quest_deficits(main_quest: dict[str, Any]) -> dict[str, int]:
    """메인 퀘스트 objective와 progress를 비교해 부족한 아이템 수량을 계산합니다."""

    objectives = main_quest.get("objectives")
    progress = main_quest.get("progress")
    if not isinstance(objectives, list):
        return {}
    if not isinstance(progress, dict):
        progress = {}

    deficits: dict[str, int] = {}
    for objective in objectives:
        if not isinstance(objective, dict):
            continue
        target_item_id = objective.get("target_item_id")
        required_quantity = objective.get("quantity")
        current_quantity = progress.get(target_item_id, 0)
        if not isinstance(target_item_id, str) or not target_item_id:
            continue
        if not isinstance(required_quantity, int) or required_quantity <= 0:
            continue
        if not isinstance(current_quantity, int | float):
            current_quantity = 0
        missing_quantity = required_quantity - int(current_quantity)
        if missing_quantity > 0:
            deficits[target_item_id] = missing_quantity
    return deficits


def _resource_ids_from_inventory(inventory: object) -> list[str]:
    """inventory 형태의 dict에서 resource id만 골라냅니다.

    `game_state.inventory`와 기존 `resources`는 둘 다
    `{"resource_id": quantity}` 모양입니다. 같은 검증 로직을 재사용하기 위해
    작은 helper로 분리했습니다.
    """

    if not isinstance(inventory, dict):
        return []
    return [
        key
        for key, value in inventory.items()
        if isinstance(key, str)
        and key.strip()
        and isinstance(value, int | float)
        and not isinstance(value, bool)
    ]


def _append_unique_resource_ids(
    resource_ids: list[str],
    candidates: list[str],
) -> None:
    """resource id 목록에 중복 없이 후보를 뒤에 붙입니다.

    후보 순서가 곧 퀘스트 생성 우선순서입니다. 그래서 메인 퀘스트 부족분처럼
    더 중요한 값은 먼저 넣고, game_state나 CSV fallback 값은 뒤에 섞습니다.
    """

    for candidate in candidates:
        if candidate not in resource_ids:
            resource_ids.append(candidate)


def _game_state(payload: dict[str, Any]) -> dict[str, Any]:
    """선택 입력인 `game_state`를 안전하게 dict로 꺼냅니다."""

    game_state = payload.get("game_state")
    return game_state if isinstance(game_state, dict) else {}


def _payload_resource_ids(payload: dict[str, Any]) -> list[str]:
    """payload에서 퀘스트 목표 후보가 될 resource id 목록을 뽑습니다.

    새 payload 구조에서는 `game_state.inventory`가 현재 플레이 상태의 정식 위치입니다.
    예전 MVP payload와의 호환을 위해 `resources`도 계속 받지만, 둘 다 있으면
    `game_state.inventory`를 우선합니다. 메인 퀘스트 부족분은 첫 후보로 넣되,
    다른 퀘스트도 만들 수 있도록 나머지 플레이 상태 후보를 뒤에 이어 붙입니다.
    """

    resource_ids: list[str] = []
    _append_unique_resource_ids(
        resource_ids,
        list(_main_quest_deficits(_current_main_quest(payload))),
    )

    game_state_resource_ids = _resource_ids_from_inventory(
        _game_state(payload).get("inventory")
    )
    if game_state_resource_ids:
        _append_unique_resource_ids(resource_ids, game_state_resource_ids)
    else:
        _append_unique_resource_ids(
            resource_ids,
            _resource_ids_from_inventory(payload.get("resources")),
        )
    return resource_ids


def _quest_candidate_resource_ids(
    payload: dict[str, Any],
    repository: QuestDataRepository,
) -> list[str]:
    """요청과 CSV fallback을 섞어 실제 퀘스트 목표 후보를 만듭니다.

    메인 퀘스트가 특정 아이템 하나만 부족하더라도 모든 서브퀘스트가 같은
    목표가 되면 플레이가 단조로워집니다. 그래서 요청에서 읽은 후보가 부족하면
    scenario CSV에서 가져온 범용 생산 후보로 남은 자리를 채웁니다.
    """

    resource_ids = _payload_resource_ids(payload)
    _append_unique_resource_ids(resource_ids, _fallback_resource_ids(repository))
    return resource_ids[:MAX_PRODUCTION_QUEST_COUNT]


def _string_list(value: object) -> list[str]:
    """설비/레시피 목록처럼 문자열 배열이어야 하는 값을 정리합니다."""

    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def _game_state_context_note(payload: dict[str, Any]) -> str:
    """퀘스트 설명에 자연스럽게 섞어 넣을 game_state 요약 문장을 만듭니다.

    지금은 설비와 레시피 해금 정보를 반영합니다. 나중에 active equipment 상태,
    기지 단계, 위험도 같은 값이 필요해지면 이 함수에만 추가하면 됩니다.
    """

    game_state = _game_state(payload)
    unlocked_equipment = _string_list(game_state.get("unlocked_equipment"))
    unlocked_recipes = _string_list(game_state.get("unlocked_recipes"))
    notes: list[str] = []
    if unlocked_equipment:
        notes.append(f"{', '.join(unlocked_equipment)} 설비를 바로 활용할 수 있고")
    if unlocked_recipes:
        notes.append(f"{', '.join(unlocked_recipes)} 제작법도 이미 확보되어 있습니다")
    if not notes:
        return ""
    return " ".join(notes).rstrip(".") + "."


def _fallback_resource_ids(repository: QuestDataRepository) -> list[str]:
    """payload에 resource가 없을 때 CSV scenario에서 쓸만한 resource id를 고릅니다."""

    resource_ids: list[str] = []
    for context in repository.list_scenario_contexts():
        for resource_id in context.related_resources:
            if resource_id not in resource_ids:
                resource_ids.append(resource_id)
    return resource_ids[:MAX_PRODUCTION_QUEST_COUNT]


def _quest_title(index: int, resource_name: str) -> str:
    """퀘스트 카드에 표시할 deterministic 제목을 만듭니다."""

    verbs = [
        "확보",
        "제련",
        "비축",
        "준비",
        "안정화",
    ]
    return f"{resource_name} {verbs[index % len(verbs)]}"


def _quest_type_label(quest_type: str) -> str:
    """퀘스트 타입을 사용자에게 보여줄 한글 label로 바꿉니다."""

    return {
        "daily": "일일 퀘스트",
        "weekly": "주간 퀘스트",
        "surprise": "깜짝 퀘스트",
    }.get(quest_type, "퀘스트")


def _quantity_from_mapping(mapping: object, target_item_id: str) -> int | None:
    """Return a positive quantity for a target item from an inventory-like mapping."""

    if not isinstance(mapping, dict):
        return None
    value = mapping.get(target_item_id)
    if (
        isinstance(value, int | float)
        and not isinstance(value, bool)
        and value > 0
    ):
        return int(value)
    return None


def _payload_quantity(payload: dict[str, Any], target_item_id: str) -> int | None:
    """Read current player stock from game_state first, then legacy resources."""

    game_state_quantity = _quantity_from_mapping(
        _game_state(payload).get("inventory"),
        target_item_id,
    )
    if game_state_quantity is not None:
        return game_state_quantity
    return _quantity_from_mapping(payload.get("resources"), target_item_id)


def _draft_quantity(
    *,
    payload: dict[str, Any],
    target_item_id: str,
    quest_type: str,
    index: int,
    main_quest_deficits: dict[str, int],
) -> int:
    """Build deterministic quest quantities without falling back to 1, 2, 3."""

    deficit = main_quest_deficits.get(target_item_id)
    if isinstance(deficit, int) and deficit > 0:
        return deficit

    base_by_type = {
        "daily": 3,
        "weekly": 8,
        "surprise": 5,
    }
    cadence_by_type = {
        "daily": 1,
        "weekly": 2,
        "surprise": 3,
    }
    current_stock = _payload_quantity(payload, target_item_id) or 0
    stock_factor = min(current_stock // 4, 6)
    resource_factor = sum(ord(char) for char in target_item_id) % 4
    cadence_factor = (index % 3) * cadence_by_type.get(quest_type, 1)
    return max(
        1,
        base_by_type.get(quest_type, 3)
        + stock_factor
        + resource_factor
        + cadence_factor,
    )


def _quest_description(
    *,
    quest_type: str,
    resource_name: str,
    target_item_id: str,
    quantity: int,
    context_summary: str,
) -> str:
    """LLM 없이도 읽을 수 있는 기본 퀘스트 설명을 만듭니다."""

    objective = f"{resource_name}({target_item_id}) {quantity}개"
    prefix = f"{context_summary} " if context_summary else ""
    if quest_type == "daily":
        return f"{prefix}오늘의 생산 루틴: {objective}를 안정적으로 생산하세요."
    if quest_type == "weekly":
        return f"{prefix}이번 주 생산 계획: {objective}를 확보해 라인 운영 여유를 만드세요."
    if quest_type == "surprise":
        return f"{prefix}예상 밖의 변수에 대비해 {objective}를 미리 생산하세요."
    return f"{prefix}{_quest_type_label(quest_type)} 목표로 {objective}를 생산하세요."


def _clear_condition(
    *,
    quest_type: str,
    target_item_id: str,
    quantity: int,
) -> dict[str, Any]:
    """퀘스트 타입에 맞는 완료 조건을 만듭니다."""

    if quest_type == "surprise":
        return {
            "mode": "manual",
            "label": "깜짝 상황 대응 완료",
        }
    return {
        "mode": "objective_count",
        "target_item_id": target_item_id,
        "required_quantity": quantity,
    }


def _main_quest_link(
    *,
    quest_type: str,
    main_quest: dict[str, Any],
    target_item_id: str,
) -> dict[str, str] | None:
    """생성 퀘스트와 메인 퀘스트의 관계 설명을 만듭니다."""

    main_quest_id = main_quest.get("id")
    main_quest_title = main_quest.get("title")
    if not isinstance(main_quest_id, str) or not main_quest_id:
        return None
    if not isinstance(main_quest_title, str) or not main_quest_title:
        return None

    relation_kind = {
        "daily": "required_material",
        "weekly": "progress_support",
        "surprise": "risk_buffer",
    }.get(quest_type, "progress_support")
    reason = {
        "daily": (
            f"메인 퀘스트 '{main_quest_title}' 진행에 필요한 "
            f"{target_item_id} 부족분을 직접 보충합니다."
        ),
        "weekly": (
            f"메인 퀘스트 '{main_quest_title}'의 장기 진행을 돕는 "
            "주간 생산 목표입니다."
        ),
        "surprise": (
            f"메인 퀘스트 '{main_quest_title}' 진행 중 발생할 수 있는 "
            "돌발 상황에 대비합니다."
        ),
    }.get(quest_type, f"메인 퀘스트 '{main_quest_title}' 진행을 지원합니다.")
    return {
        "main_quest_id": main_quest_id,
        "main_quest_title": main_quest_title,
        "relation_kind": relation_kind,
        "reason": reason,
    }


def _context_summary(
    contexts: list[ScenarioContextRow],
    index: int,
    resource_name: str,
) -> str:
    """여러 scenario context 중 현재 quest에 붙일 summary를 고릅니다."""

    if not contexts:
        return f"현재 공장 목표를 위해 {resource_name}이(가) 필요합니다."
    context = contexts[index % len(contexts)]
    return context.summary


def build_production_quest_graph() -> CompiledStateGraph:
    """생산 퀘스트 생성용 LangGraph를 만들고 compile합니다.

    각 node는 하나의 작은 책임만 가집니다.

    - `production.normalize_payload`: 요청에서 생성 개수를 정합니다.
    - `production.retrieve_context`: CSV repository에서 참고 context를 가져옵니다.
    - `production.build_quests`: schema에 맞는 quest draft를 만듭니다.
    - `production.validate_response`: Pydantic으로 최종 모양을 검증합니다.
    """

    def normalize_payload(
        state: ProductionQuestGraphState,
    ) -> ProductionQuestGraphState:
        payload = state.get("payload", {})
        main_quest = _current_main_quest(payload)
        return {
            "quest_count": _resolve_quest_count(payload),
            "quest_types": _resolve_quest_types(payload),
            "main_quest": main_quest,
            "main_quest_deficits": _main_quest_deficits(main_quest),
        }

    def retrieve_context(
        state: ProductionQuestGraphState,
    ) -> ProductionQuestGraphState:
        payload = state.get("payload", {})
        repository = QuestDataRepository()
        resource_ids = _quest_candidate_resource_ids(payload, repository)

        contexts = repository.find_scenario_contexts(
            related_resource_ids=resource_ids,
            quest_type="daily",
        )
        if not contexts:
            contexts = repository.find_scenario_contexts(
                related_resource_ids=resource_ids,
                quest_type="weekly",
            )

        return {
            "retrieved_context": {
                "resource_ids": resource_ids or ["resource_iron_ore"],
                "scenario_contexts": contexts,
                "game_state_note": _game_state_context_note(payload),
            }
        }

    def build_quests(
        state: ProductionQuestGraphState,
    ) -> ProductionQuestGraphState:
        quest_count = state["quest_count"]
        quest_types = state.get("quest_types", list(DEFAULT_QUEST_TYPES))
        main_quest = state.get("main_quest", {})
        main_quest_deficits = state.get("main_quest_deficits", {})
        link_to_main_quest = _main_quest_link_enabled(state.get("payload", {}))
        retrieved_context = state.get("retrieved_context", {})
        resource_ids = retrieved_context.get("resource_ids", ["resource_iron_ore"])
        contexts = retrieved_context.get("scenario_contexts", [])
        game_state_note = retrieved_context.get("game_state_note", "")

        repository = QuestDataRepository()
        quests = []
        for index in range(quest_count):
            target_item_id = resource_ids[index % len(resource_ids)]
            quest_type = quest_types[index % len(quest_types)]
            quantity = _draft_quantity(
                payload=state.get("payload", {}),
                target_item_id=target_item_id,
                quest_type=quest_type,
                index=index,
                main_quest_deficits=main_quest_deficits,
            )

            try:
                resource_name = repository.get_resource(target_item_id).resource_name
            except KeyError:
                resource_name = target_item_id

            context_summary = _context_summary(contexts, index, resource_name)
            if game_state_note:
                context_summary = f"{context_summary} {game_state_note}"
            main_quest_link = (
                _main_quest_link(
                    quest_type=quest_type,
                    main_quest=main_quest,
                    target_item_id=target_item_id,
                )
                if link_to_main_quest and target_item_id in main_quest_deficits
                else None
            )
            quest = {
                "id": index + 1,
                "type": quest_type,
                "domain": "production",
                "title": _quest_title(index, resource_name),
                "description": _quest_description(
                    quest_type=quest_type,
                    resource_name=resource_name,
                    target_item_id=target_item_id,
                    quantity=quantity,
                    context_summary=context_summary,
                ),
                "objectives": [
                    {
                        "target_item_id": target_item_id,
                        "quantity": quantity,
                    }
                ],
                "clear_condition": _clear_condition(
                    quest_type=quest_type,
                    target_item_id=target_item_id,
                    quantity=quantity,
                ),
            }
            if main_quest_link is not None:
                quest["main_quest_link"] = main_quest_link
            quests.append(
                quest
            )

        return {"response_payload": {"quests": quests}}

    def validate_response(
        state: ProductionQuestGraphState,
    ) -> ProductionQuestGraphState:
        response = QuestResponse.model_validate(state["response_payload"])
        return {"response_payload": response.model_dump(mode="json")}

    graph = StateGraph(ProductionQuestGraphState)
    graph.add_node("production.normalize_payload", normalize_payload)
    graph.add_node("production.retrieve_context", retrieve_context)
    graph.add_node("production.build_quests", build_quests)
    graph.add_node("production.validate_response", validate_response)
    graph.add_edge(START, "production.normalize_payload")
    graph.add_edge("production.normalize_payload", "production.retrieve_context")
    graph.add_edge("production.retrieve_context", "production.build_quests")
    graph.add_edge("production.build_quests", "production.validate_response")
    graph.add_edge("production.validate_response", END)
    return graph.compile()


class ProductionQuestAgent:
    """자원 생산 목표를 가진 production quest를 만드는 leaf agent입니다."""

    agent_id = "quest_generator.production_quest"
    tools = ()

    def __init__(self) -> None:
        """agent가 사용할 내부 LangGraph를 한 번 compile해 둡니다."""

        self.graph = build_production_quest_graph()

    def describe_graph(self) -> str:
        """테스트와 디버깅에서 graph 흐름을 확인할 수 있게 요약합니다."""

        return (
            "StateGraph: START -> production.normalize_payload -> "
            "production.retrieve_context -> production.build_quests -> "
            "production.validate_response -> END"
        )

    def build_prompt(self, payload: dict[str, Any], context: AgentContext) -> str:
        """LLM에게 보낼 prompt를 만듭니다.

        graph가 먼저 안전한 draft quest JSON을 만듭니다. 그 뒤 LLM에게는 구조를
        바꾸지 말고 title/description만 더 자연스럽게 다듬으라고 지시합니다.
        이렇게 하면 LLM이 엉뚱한 id나 잘못된 quantity를 새로 만들 가능성을
        줄일 수 있습니다.
        """

        state = self.graph.invoke(
            {
                "payload": payload,
                "context": context,
            }
        )
        draft_payload = state["response_payload"]
        quest_count = len(draft_payload["quests"])
        return (
            "[ROLE]\n"
            "You are a production quest generation agent.\n\n"
            "[TASK]\n"
            f"Return exactly {quest_count} quests as one JSON object. "
            "Use the QuestResponse schema. Keep every quest id, type, domain, "
            "objective target_item_id, objective quantity, clear_condition, "
            "and main_quest_link exactly as shown in DRAFT_QUESTS. "
            "You may improve only title, description, and main_quest_link.reason. "
            "The title and description MUST be written in Korean.\n\n"
            "[DRAFT_QUESTS]\n"
            f"{json.dumps(draft_payload, ensure_ascii=False)}\n\n"
            "[REQUEST_PAYLOAD]\n"
            f"{json.dumps(payload, ensure_ascii=False, default=str)}\n\n"
            "[OUTPUT_CONTRACT]\n"
            "Return only one JSON object with this shape:\n"
            '{"quests":[{"id":1,"type":"daily","domain":"production","title":"...",'
            '"description":"...","objectives":[{"target_item_id":"...",'
            '"quantity":1}],"clear_condition":{"mode":"objective_count",'
            '"target_item_id":"...","required_quantity":1}}]}\n'
        )

    def fallback(
        self,
        payload: dict[str, Any],
        context: AgentContext,
    ) -> AgentRunResult:
        """LLM을 사용할 수 없을 때도 같은 graph로 production quest를 만듭니다."""

        state = self.graph.invoke(
            {
                "payload": payload,
                "context": context,
            }
        )
        return AgentRunResult(
            agent="quest_generator",
            payload=state["response_payload"],
            metadata={"fallback": True, "sub_agent": self.agent_id},
        )
