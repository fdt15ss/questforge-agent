"""퀘스트 에이전트가 LLM tool_call로 사용할 도구입니다.

LLM은 최종 payload를 직접 만들지 않고, 선택한 퀘스트 id만 이 도구에 넘깁니다.
도구는 id를 검증한 뒤 서비스 계층을 호출해 실제 퀘스트 응답으로 바꿉니다.
"""

from __future__ import annotations

from typing import Any

from agents.base import AgentContext
from agents.quest_generator.service import QuestAgentService

PRODUCTION_QUEST_SELECTION_TOOL_NAME = "quest_generator.select_production_quests"


class ProductionQuestSelectionTool:
    """LLM이 고른 퀘스트 id를 기존 production quest payload로 변환합니다.

    공통 파이프라인은 `name` 값으로 어떤 도구를 실행할지 찾습니다. 그래서
    프롬프트에 적힌 tool name과 이 클래스의 `name`이 같아야 합니다.
    """

    name = PRODUCTION_QUEST_SELECTION_TOOL_NAME

    def invoke(
        self,
        payload: dict[str, Any],
        context: AgentContext,
        args: dict[str, Any] | None = None,
    ) -> object:
        """tool_call 인자를 검사하고 선택된 퀘스트 목록 또는 오류를 반환합니다.

        `args`에는 `{"selected_quest_ids": [1, 2, 3, 4, 5]}` 같은 값이 들어와야
        합니다. 형식이 틀리거나 없는 id가 포함되면 예외를 밖으로 흘리지 않고
        에러 dict로 바꿔 파이프라인이 처리할 수 있게 합니다.
        """

        selected_ids = (args or {}).get("selected_quest_ids")
        if not isinstance(selected_ids, list) or not all(
            type(quest_id) is int for quest_id in selected_ids
        ):
            return {
                "status": "error",
                "code": "INVALID_QUEST_SELECTION",
                "message": "selected_quest_ids는 정수 id 목록이어야 합니다.",
            }

        try:
            return QuestAgentService().generate_quest_json_from_ids(selected_ids)
        except ValueError as exc:
            return {
                "status": "error",
                "code": "INVALID_QUEST_SELECTION",
                "message": str(exc),
            }
