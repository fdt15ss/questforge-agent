"""생산 퀘스트를 고르는 leaf agent입니다.

상위 `QuestGeneratorAgent`가 생산 퀘스트가 맞다고 판단하면 이 클래스가
실제로 사용할 프롬프트를 만듭니다. 현재 구현은 LLM이 새 퀘스트를 쓰는
방식이 아니라, 준비된 예제 퀘스트 목록에서 id 5개를 고르게 합니다.
"""

from __future__ import annotations

import json
from typing import Any

from agents.base import AgentContext, AgentRunResult
from agents.quest_generator.service import QuestAgentService
from agents.quest_generator.tools import (
    PRODUCTION_QUEST_SELECTION_TOOL_NAME,
    ProductionQuestSelectionTool,
)


class ProductionQuestAgent:
    """자원 채집 또는 아이템 제작 생산 퀘스트 선택을 담당합니다.

    `tools`에 `ProductionQuestSelectionTool`을 등록해 두었기 때문에,
    LLM은 텍스트 답변 대신 tool_call로 선택한 퀘스트 id를 넘겨야 합니다.
    """

    agent_id = "quest_generator.production_quest"
    tools = (ProductionQuestSelectionTool(),)

    def build_prompt(self, payload: dict[str, Any], context: AgentContext) -> str:
        """LLM이 기존 생산 퀘스트 중 5개를 고르도록 지시하는 프롬프트를 만듭니다.

        `available_quests`는 서버에 하드코딩된 예제 퀘스트 목록입니다. 프롬프트는
        LLM에게 제목이나 설명을 새로 만들지 말고, 목록에 있는 id만 고르라고
        강하게 제한합니다.
        """

        available_quests = json.dumps(
            QuestAgentService().available_quest_json(),
            ensure_ascii=False,
        )
        return (
            "[ROLE]\n"
            "팩토리 스페이스 생산 퀘스트 선택 에이전트입니다.\n\n"
            "[TASK]\n"
            "AVAILABLE_QUESTS에 있는 기존 퀘스트 id 중 정확히 5개를 고르세요.\n"
            "퀘스트 제목, 설명, 목표는 새로 만들거나 고치거나 번역하지 마세요.\n"
            "고른 id는 반드시 tool_call로만 전달하세요.\n\n"
            "[TOOLS]\n"
            f"- {PRODUCTION_QUEST_SELECTION_TOOL_NAME}\n"
            '  args: {"selected_quest_ids":[정수 id 5개]}\n\n'
            "[AVAILABLE_QUESTS]\n"
            f"{available_quests}\n\n"
            "[REQUEST_PAYLOAD]\n"
            f"{payload}\n\n"
            "[OUTPUT_CONTRACT]\n"
            "도구 실행 전 첫 응답은 다음 형태의 tool_call JSON 객체만 반환하세요:\n"
            '{"tool_call":{"name":"quest_generator.select_production_quests",'
            '"args":{"selected_quest_ids":[2,4,6,8,10]}}}\n'
            "위 id 값은 형식 예시일 뿐이며 그대로 따라 쓰지 마세요.\n"
            "AVAILABLE_QUESTS 안의 id만 정확히 5개, 중복 없이 사용하세요.\n"
            "요청과 AVAILABLE_QUESTS를 보고 가장 적절한 5개 id를 고르세요.\n"
            "quests, selected_quest_ids 직접 응답, markdown, 주석, 이유, 추가 key는 포함하지 마세요."
        )

    def fallback(
        self,
        payload: dict[str, Any],
        context: AgentContext,
    ) -> AgentRunResult:
        """LLM 응답을 사용할 수 없을 때 예시 생산 퀘스트를 반환합니다.

        네트워크 오류나 LLM 출력 파싱 실패가 있어도 클라이언트가 빈 응답을
        받지 않도록 서비스에서 무작위 생산 퀘스트 5개를 뽑아 돌려줍니다.
        """

        return AgentRunResult(
            agent="quest_generator",
            payload=QuestAgentService().generate_quest_json(),
            metadata={"fallback": True, "sub_agent": self.agent_id},
        )
