"""서버 안에 준비된 예제 퀘스트 중에서 응답할 퀘스트를 고르는 서비스입니다.

초보자 관점에서 보면 이 파일은 "퀘스트 데이터 저장소 + 검증 도우미"에
가깝습니다. 아직 DB를 쓰지 않기 때문에 `_EXAMPLE_QUESTS`에 예제 데이터를
두고, 메서드에서 Pydantic 모델로 모양을 검증한 뒤 JSON-friendly dict로
바꿔 반환합니다.
"""

from __future__ import annotations

import random
from typing import Any

from agents.quest_generator.schemas import Quest, QuestResponse

_EXAMPLE_QUESTS: tuple[dict[str, Any], ...] = (
    {
        "id": 1,
        "type": "production",
        "title": "철광석 10개 채굴",
        "description": "기초 생산 라인을 준비하기 위해 철광석 10개를 채굴하세요.",
        "objectives": [{"target_item_id": "iron_ore", "quantity": 10}],
    },
    {
        "id": 2,
        "type": "production",
        "title": "구리광석 8개 채굴",
        "description": "전력 설비 확장을 위해 구리광석 8개를 확보하세요.",
        "objectives": [{"target_item_id": "copper_ore", "quantity": 8}],
    },
    {
        "id": 3,
        "type": "production",
        "title": "석탄 6개 확보",
        "description": "발전 설비 가동을 위해 석탄 6개를 확보하세요.",
        "objectives": [{"target_item_id": "coal", "quantity": 6}],
    },
    {
        "id": 4,
        "type": "production",
        "title": "목재 8개 확보",
        "description": "초기 연료와 목탄 제작을 위해 목재 8개를 확보하세요.",
        "objectives": [{"target_item_id": "wood", "quantity": 8}],
    },
    {
        "id": 5,
        "type": "production",
        "title": "철괴 5개 제련",
        "description": "철광석을 제련해 철괴 5개를 생산하세요.",
        "objectives": [{"target_item_id": "iron_ingot", "quantity": 5}],
    },
    {
        "id": 6,
        "type": "production",
        "title": "구리괴 5개 제련",
        "description": "구리광석을 제련해 구리괴 5개를 생산하세요.",
        "objectives": [{"target_item_id": "copper_ingot", "quantity": 5}],
    },
    {
        "id": 7,
        "type": "production",
        "title": "철가루 6개 분쇄",
        "description": "그라인더로 철괴를 가공해 철가루 6개를 생산하세요.",
        "objectives": [{"target_item_id": "iron_powder", "quantity": 6}],
    },
    {
        "id": 8,
        "type": "production",
        "title": "구리가루 6개 분쇄",
        "description": "그라인더로 구리괴를 가공해 구리가루 6개를 생산하세요.",
        "objectives": [{"target_item_id": "copper_powder", "quantity": 6}],
    },
    {
        "id": 9,
        "type": "production",
        "title": "목탄 4개 제작",
        "description": "제련기로 목재를 가공해 목탄 4개를 생산하세요.",
        "objectives": [{"target_item_id": "charcoal", "quantity": 4}],
    },
    {
        "id": 10,
        "type": "production",
        "title": "석탄가루 4개 분쇄",
        "description": "그라인더로 석탄을 분쇄해 석탄가루 4개를 생산하세요.",
        "objectives": [{"target_item_id": "coal_dust", "quantity": 4}],
    },
)


class QuestAgentService:
    """예제 퀘스트 목록을 읽고 응답 payload로 바꾸는 작은 서비스입니다.

    agent 클래스는 프롬프트와 fallback 흐름에 집중하고, 실제 퀘스트 목록
    선택과 검증은 이 서비스가 맡습니다. 나중에 DB나 CSV를 붙이더라도
    agent 코드를 크게 바꾸지 않게 하려는 분리입니다.
    """

    def __init__(self, rng: random.Random | None = None) -> None:
        """퀘스트 샘플링에 사용할 난수 생성기를 준비합니다.

        테스트에서는 `random.Random(0)`처럼 고정된 생성기를 넣어 결과를
        예측 가능하게 만들고, 실제 실행에서는 `SystemRandom`으로 매번 다른
        퀘스트 조합을 뽑습니다.
        """

        self._rng = rng or random.SystemRandom()

    def generate_quest_json(self, count: int = 5) -> dict[str, Any]:
        """예제 목록에서 `count`개를 무작위로 뽑아 응답 dict로 반환합니다.

        `Quest.model_validate`는 각 퀘스트가 스키마에 맞는지 확인하고,
        `model_dump(mode="json")`은 FastAPI/WebSocket 응답으로 보내기 쉬운
        기본 Python 타입만 남깁니다.
        """

        selected_quests = self._rng.sample(_EXAMPLE_QUESTS, k=count)
        quests = [Quest.model_validate(quest) for quest in selected_quests]
        return QuestResponse(quests=quests).model_dump(mode="json")

    def available_quest_json(self) -> list[dict[str, Any]]:
        """LLM이 고를 수 있는 전체 생산 퀘스트 후보 목록을 반환합니다.

        `ProductionQuestAgent`는 이 목록을 프롬프트에 넣고, LLM에게 여기 있는
        id 중 5개만 tool_call로 고르라고 지시합니다.
        """

        return [
            Quest.model_validate(quest).model_dump(mode="json")
            for quest in _EXAMPLE_QUESTS
        ]

    def generate_quest_json_from_ids(
        self,
        quest_ids: list[int],
        count: int = 5,
    ) -> dict[str, Any]:
        """LLM이 선택한 id 목록을 실제 퀘스트 payload로 변환합니다.

        id 개수와 중복 여부를 먼저 검사한 뒤, 모르는 id가 섞여 있으면
        `ValueError`를 던집니다. tool 계층은 이 예외를 잡아 클라이언트가
        이해할 수 있는 error payload로 바꿉니다.
        """

        if len(quest_ids) != count or len(set(quest_ids)) != count:
            raise ValueError(f"정확히 {count}개의 서로 다른 퀘스트 id가 필요합니다.")

        quests_by_id = {quest["id"]: quest for quest in _EXAMPLE_QUESTS}
        try:
            selected_quests = [quests_by_id[quest_id] for quest_id in quest_ids]
        except KeyError as exc:
            raise ValueError(f"알 수 없는 퀘스트 id입니다: {exc.args[0]}") from exc

        quests = [Quest.model_validate(quest) for quest in selected_quests]
        return QuestResponse(quests=quests).model_dump(mode="json")
