"""퀘스트 요청을 어떤 하위 퀘스트 에이전트가 처리할지 고르는 진입점입니다.

이 모듈은 실제 퀘스트 내용을 직접 만들지 않습니다. 대신 요청 payload와
실행 context를 LLM에게 보여주고, production/delivery 같은 leaf agent 중
어느 쪽이 이어서 처리해야 하는지 결정하게 합니다.
"""

from __future__ import annotations

from typing import Any

from agents.base import AgentContext

QUEST_SUB_AGENT_IDS = (
    "quest_generator.production_quest",
    "quest_generator.delivery_quest",
)


class QuestGeneratorAgent:
    """퀘스트 생성 요청을 leaf agent로 보내기 위한 상위 관리자입니다.

    `agent_id`는 외부 요청에서 이 에이전트를 찾을 때 쓰는 이름이고,
    `tools`가 비어 있다는 것은 이 단계에서는 도구를 실행하지 않고
    라우팅 프롬프트만 만든다는 뜻입니다.
    """

    agent_id = "quest_generator"
    tools = ()

    def build_routing_prompt(
        self,
        payload: dict[str, Any],
        context: AgentContext,
    ) -> str:
        """LLM에게 선택 가능한 leaf agent 목록을 알려주는 프롬프트를 만듭니다.

        반환값은 곧바로 LLM 입력으로 쓰이는 문자열입니다. LLM은 이 문자열을
        보고 `QUEST_SUB_AGENT_IDS` 중 하나만 출력해야 하며, 실제 분기는
        파이프라인의 라우팅 단계에서 처리합니다.
        """

        allowed_leaf_agent_ids = "\n".join(
            f"- {sub_agent_id}" for sub_agent_id in QUEST_SUB_AGENT_IDS
        )
        return (
            "[ROLE]\n"
            "퀘스트 생성 도메인 오케스트레이터\n\n"
            "[TASK]\n"
            "퀘스트 요청을 처리할 leaf Agent id를 하나만 결정한다.\n\n"
            "[ALLOWED_LEAF_AGENT_IDS]\n"
            f"{allowed_leaf_agent_ids}\n\n"
            "[REQUEST_CONTEXT]\n"
            f"{context.metadata}\n\n"
            "[REQUEST_PAYLOAD]\n"
            f"{payload}\n\n"
            "[OUTPUT_CONTRACT]\n"
            "ALLOWED_LEAF_AGENT_IDS 중 하나의 id만 그대로 출력한다.\n"
            "JSON, markdown, 설명, reason, 따옴표, 코드블록은 출력하지 않는다."
        )
