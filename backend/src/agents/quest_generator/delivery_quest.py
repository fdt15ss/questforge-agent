"""납품 퀘스트를 생성하는 leaf agent입니다.

`QuestGeneratorAgent`가 요청을 `quest_generator.delivery_quest`로 라우팅하면
공통 파이프라인이 이 클래스를 실행합니다. 생산 퀘스트와 달리 준비된 목록에서
id를 고르지 않고, LLM에게 특정 자원이나 제작품을 창고, 기지, 요청 지점에
납품하는 퀘스트 하나를 정해진 JSON 모양으로 작성하게 합니다.
"""

from __future__ import annotations

import json
from typing import Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from agents.base import AgentContext, AgentRunResult
from agents.quest_generator.rewards import build_quest_rewards
from agents.quest_generator.schemas import QuestResponse
from quest_data.repository import QuestDataRepository
from quest_data.retrieval import retrieve_game_context
from quest_data.vector_context import default_vector_store

DEFAULT_DELIVERY_QUEST_COUNT = 5
MAX_DELIVERY_QUEST_COUNT = 10
DEFAULT_QUEST_TYPES = ("daily", "weekly", "surprise")


class DeliveryQuestGraphState(TypedDict, total=False):
    """DeliveryQuestAgent 내부 LangGraph에서 공유하는 상태입니다.

    공통 AgentPipeline의 큰 그래프와 별개로, 이 상태는 납품 퀘스트 하나를
    만들기 위한 작은 그래프 안에서만 사용됩니다.

    LangGraph의 각 노드는 이 dict에 값을 조금씩 추가합니다. 예를 들어
    `delivery.normalize_payload` 노드는 `item`, `quantity`, `destination`을
    채우고, 다음 노드인 `delivery.select_goal`은 그 값을 읽어서 `title`과
    `objective`를 만듭니다.
    """

    mode: Literal["prompt", "fallback"]
    payload: dict[str, Any]
    context: AgentContext
    item: str
    quantity: int
    destination: str
    quest_count: int
    quest_types: list[str]
    title: str
    objective: str
    prompt: str
    responsePayload: dict[str, Any]


def _coerce_positive_int(value: object, default: int) -> int:
    """payload 값을 양수 정수로 정규화하고, 실패하면 기본값을 반환합니다."""

    if isinstance(value, int) and value > 0:
        return value
    if isinstance(value, str) and value.isdecimal():
        parsed = int(value)
        if parsed > 0:
            return parsed
    return default


def _coerce_text(value: object, default: str) -> str:
    """payload 값을 비어 있지 않은 문자열로 정규화하고, 실패하면 기본값을 반환합니다."""

    if isinstance(value, str) and value.strip():
        return value.strip()
    return default


def _resolve_quest_count(payload: dict[str, Any]) -> int:
    """payload에서 생성할 delivery quest 개수를 읽습니다."""

    options = payload.get("quest_generation_options")
    nested_count = options.get("count") if isinstance(options, dict) else None
    simple_count = payload.get("quest_count")
    raw_count = nested_count if nested_count is not None else simple_count
    if isinstance(raw_count, int) and 1 <= raw_count <= MAX_DELIVERY_QUEST_COUNT:
        return raw_count
    return DEFAULT_DELIVERY_QUEST_COUNT


def _resolve_quest_types(payload: dict[str, Any]) -> list[str]:
    """payload에서 허용된 cadence type 목록을 읽습니다."""

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


def _build_delivery_payload(state: DeliveryQuestGraphState) -> dict[str, Any]:
    """Build a QuestResponse-shaped delivery quest payload."""

    item = state["item"]
    base_quantity = state["quantity"]
    destination = state["destination"]
    quest_types = state.get("quest_types", list(DEFAULT_QUEST_TYPES))
    repository = QuestDataRepository()
    quests: list[dict[str, Any]] = []
    for index in range(state["quest_count"]):
        quest_type = quest_types[index % len(quest_types)]
        quantity = base_quantity + index
        quests.append(
            {
                "id": index + 1,
                "type": quest_type,
                "domain": "delivery",
                "title": f"{item} 납품 {index + 1}",
                "description": (
                    f"{destination}에 {item} {quantity}개를 보내 "
                    "막히는 생산 흐름을 풀어 주세요."
                ),
                "objectives": [
                    {
                        "target_item_id": item,
                        "quantity": quantity,
                    }
                ],
                "clear_condition": {
                    "mode": "objective_count",
                    "target_item_id": item,
                    "required_quantity": quantity,
                },
                            "rewards": build_quest_rewards(
                    quest_type=quest_type,
                    target_item_id=item,
                    payload=state.get("payload", {}),
                    context=state["context"],
                    repository=repository,
                ),
            }
        )
    return QuestResponse.model_validate({"quests": quests}).model_dump(mode="json")


def build_delivery_quest_graph() -> CompiledStateGraph:
    """납품 퀘스트 전용 LangGraph를 만들고 컴파일합니다.

    그래프는 payload를 정규화한 뒤 납품 목표를 만들고, 요청한 mode에 따라
    LLM prompt 또는 deterministic fallback payload 중 하나를 생성합니다.

    초보자용으로 흐름을 풀면 다음과 같습니다.
    1. 입력 payload에서 아이템, 수량, 납품 장소를 꺼냅니다.
    2. 비어 있거나 잘못된 값은 안전한 기본값으로 바꿉니다.
    3. 공통 납품 목표 문장을 만듭니다.
    4. `mode`가 `prompt`면 LLM용 프롬프트를, `fallback`이면 기본 응답 JSON을 만듭니다.
    """

    def normalize_payload(
        state: DeliveryQuestGraphState,
    ) -> DeliveryQuestGraphState:
        """사용자 payload를 LangGraph가 쓰기 쉬운 세 필드로 정리합니다.

        이 노드는 그래프의 첫 번째 실제 작업입니다. 뒤 노드들이 같은 이름의
        필드를 믿고 읽을 수 있도록 `item`, `quantity`, `destination`을 항상
        채워서 반환합니다.
        """

        payload = state.get("payload", {})
        return {
            "item": _coerce_text(payload.get("item"), "철괴"),
            "quantity": _coerce_positive_int(payload.get("quantity"), 5),
            "destination": _coerce_text(payload.get("destination"), "창고"),
            "quest_count": _resolve_quest_count(payload),
            "quest_types": _resolve_quest_types(payload),
        }

    def select_goal(state: DeliveryQuestGraphState) -> DeliveryQuestGraphState:
        """정규화된 필드로 납품 퀘스트 제목과 목표 문장을 만듭니다.

        `normalize_payload`가 만든 `item`, `quantity`, `destination`을 읽고,
        prompt와 fallback 양쪽에서 함께 사용할 `title`과 `objective`를
        state에 추가합니다.
        """

        item = state["item"]
        quantity = state["quantity"]
        destination = state["destination"]
        return {
            "title": f"{item} 납품",
            "objective": f"{item} {quantity}개를 {destination}에 납품하세요.",
        }

    def build_prompt(state: DeliveryQuestGraphState) -> DeliveryQuestGraphState:
        """LLM에게 보낼 납품 퀘스트 생성 프롬프트를 state에 추가합니다.

        이 노드는 `mode`가 `prompt`일 때만 실행됩니다. 앞 노드에서 만든
        `objective`를 프롬프트에 넣어 LLM이 아이템, 수량, 납품 장소를 빠뜨리지
        않게 합니다. leaf agent는 기존 `quest_text_updates` 계약을 유지합니다.
        """

        payload = state.get("payload", {})
        draft_payload = _build_delivery_payload(state)
        retrieved_game_context = retrieve_game_context(
            payload,
            QuestDataRepository(),
            vector_store=default_vector_store(),
        )
        return {
            "prompt": (
                "You are a delivery quest generation agent.\n\n"
                "[TASK]\n"
                f"Return exactly {len(draft_payload['quests'])} quest text updates as one JSON object. "
                "Use the QuestTextUpdate schema. Each update must reference a draft quest id. "
                "Do not return objectives, clear_condition, rewards, or full quests. "
                "The server will preserve every other field from DRAFT_QUESTS. You may improve only title "
                "and description. Use RETRIEVED_GAME_CONTEXT as authoritative game knowledge, "
                "but do not invent server-owned objectives, clear conditions, rewards, quantities, "
                "or schema fields. Return only id, title, and description. "
                "The title and description MUST be written in Korean.\n\n"
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
        }

    def build_fallback(state: DeliveryQuestGraphState) -> DeliveryQuestGraphState:
        """LLM을 쓰지 못할 때 반환할 기본 납품 퀘스트 payload를 만듭니다.

        이 노드는 `mode`가 `fallback`일 때만 실행됩니다. prompt 경로와 같은
        `title`, `objective`를 쓰기 때문에 LLM 사용 여부와 관계없이 납품 목표
        모양이 일관됩니다.
        """

        return {"responsePayload": _build_delivery_payload(state)}

    def route_output_mode(
        state: DeliveryQuestGraphState,
    ) -> Literal["prompt", "fallback"]:
        """`delivery.select_goal` 다음에 어느 노드로 갈지 결정합니다.

        LangGraph의 conditional edge가 이 반환값을 보고 `delivery.build_prompt`
        또는 `delivery.build_fallback` 중 하나로 이동합니다.
        """

        return state.get("mode", "prompt")

    graph = StateGraph(DeliveryQuestGraphState)
    graph.add_node("delivery.normalize_payload", normalize_payload)
    graph.add_node("delivery.select_goal", select_goal)
    graph.add_node("delivery.build_prompt", build_prompt)
    graph.add_node("delivery.build_fallback", build_fallback)
    graph.add_edge(START, "delivery.normalize_payload")
    graph.add_edge("delivery.normalize_payload", "delivery.select_goal")
    graph.add_conditional_edges(
        "delivery.select_goal",
        route_output_mode,
        {
            "prompt": "delivery.build_prompt",
            "fallback": "delivery.build_fallback",
        },
    )
    graph.add_edge("delivery.build_prompt", END)
    graph.add_edge("delivery.build_fallback", END)
    return graph.compile()


class DeliveryQuestAgent:
    """플레이어가 아이템을 모아 지정 장소에 납품하는 퀘스트를 담당합니다.

    이 leaf agent는 별도 tool을 쓰지 않으므로 `tools`가 비어 있습니다.
    대신 `build_prompt`가 LLM에게 직접 JSON 응답 형식을 지시합니다.
    `fallback`은 LLM이 실패해도 UI가 보여줄 기본 납품 퀘스트를 만듭니다.
    """

    agent_id = "quest_generator.delivery_quest"
    tools = ()
    response_schema = QuestResponse

    def __init__(self) -> None:
        """DeliveryQuestAgent가 사용할 내부 LangGraph를 한 번 컴파일합니다."""

        self.graph = build_delivery_quest_graph()

    def describe_graph(self) -> str:
        """포트폴리오와 테스트에서 확인할 수 있는 내부 LangGraph 요약입니다."""

        return (
            "StateGraph: START -> delivery.normalize_payload -> "
            "delivery.select_goal -> "
            "{delivery.build_prompt | delivery.build_fallback} -> END"
        )

    def build_prompt(self, payload: dict[str, Any], context: AgentContext) -> str:
        """납품 퀘스트 JSON 하나를 만들도록 LLM에 전달할 프롬프트를 반환합니다.

        상위 `quest_generator`는 `quest_plan`으로 기획 의도를 받습니다.
        leaf agent는 특정 도메인 draft가 이미 확정된 뒤 실행되므로 기존처럼
        `quest_text_updates`만 받아 제목/설명 품질을 보강합니다.

        Returns:
            LLM에게 전달할 prompt 문자열입니다.
        """

        state = self.graph.invoke(
            {
                "mode": "prompt",
                "payload": payload,
                "context": context,
            }
        )
        return state["prompt"]

    def fallback(
        self,
        payload: dict[str, Any],
        context: AgentContext,
    ) -> AgentRunResult:
        """LLM 응답을 사용할 수 없을 때 기본 납품 퀘스트를 반환합니다.

        실패 상황에서도 UI가 표시할 수 있는 최소 퀘스트를 제공하기 위한
        안전한 기본값입니다. 반환하는 `AgentRunResult`의 `metadata`에는 어떤
        leaf agent가 fallback을 만들었는지 추적할 수 있는 `sub_agent`가 들어갑니다.

        내부적으로는 LangGraph를 `mode="fallback"`으로 실행해 fallback payload
        생성 경로만 타게 합니다.
        """

        state = self.graph.invoke(
            {
                "mode": "fallback",
                "payload": payload,
                "context": context,
            }
        )
        return AgentRunResult(
            agent="quest_generator",
            payload=state["responsePayload"],
            metadata={
                "fallback": True,
                "sub_agent": self.agent_id,
                "graph": "delivery_quest",
            },
        )
