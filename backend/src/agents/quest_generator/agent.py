"""퀘스트 요청을 어떤 하위 퀘스트 에이전트가 처리할지 고르는 진입점입니다.

이 모듈은 실제 퀘스트 내용을 직접 만들지 않습니다. 대신 요청 payload와
실행 context를 LLM에게 보여주고, production/delivery 같은 leaf agent 중
어느 쪽이 이어서 처리해야 하는지 결정하게 합니다.
"""

from __future__ import annotations

import json
from typing import Any

from agents.base import AgentContext, AgentRunResult
from agents.quest_generator.delivery_quest import DeliveryQuestAgent
from agents.quest_generator.production_quest import ProductionQuestAgent
from agents.quest_generator.schemas import QuestResponse

QUEST_SUB_AGENT_IDS = (
    "quest_generator.production_quest",
    "quest_generator.delivery_quest",
)
QUEST_DOMAINS = ("production", "delivery")
DEFAULT_TOTAL_QUEST_COUNT = 5
MAX_TOTAL_QUEST_COUNT = 10


def _quest_generation_options(payload: dict[str, Any]) -> dict[str, Any]:
    options = payload.get("quest_generation_options")
    return dict(options) if isinstance(options, dict) else {}


def _resolve_total_quest_count(payload: dict[str, Any]) -> int:
    options = _quest_generation_options(payload)
    nested_count = options.get("count")
    simple_count = payload.get("quest_count")
    raw_count = nested_count if nested_count is not None else simple_count
    if isinstance(raw_count, int) and 1 <= raw_count <= MAX_TOTAL_QUEST_COUNT:
        return raw_count
    return DEFAULT_TOTAL_QUEST_COUNT


def _resolve_domains(payload: dict[str, Any]) -> list[str]:
    options = _quest_generation_options(payload)
    raw_domains = options.get("domains")
    if not isinstance(raw_domains, list):
        return list(QUEST_DOMAINS)
    domains = [
        domain
        for domain in raw_domains
        if isinstance(domain, str) and domain in QUEST_DOMAINS
    ]
    return domains or list(QUEST_DOMAINS)


def _resolve_domain_counts(payload: dict[str, Any]) -> dict[str, int]:
    options = _quest_generation_options(payload)
    raw_domain_counts = options.get("domain_counts")
    if isinstance(raw_domain_counts, dict):
        domain_counts = {
            domain: count
            for domain, count in raw_domain_counts.items()
            if (
                domain in QUEST_DOMAINS
                and isinstance(count, int)
                and 1 <= count <= MAX_TOTAL_QUEST_COUNT
            )
        }
        if domain_counts:
            return domain_counts

    domains = _resolve_domains(payload)
    total_count = _resolve_total_quest_count(payload)
    base_count = total_count // len(domains)
    remainder = total_count % len(domains)
    return {
        domain: base_count + (1 if index < remainder else 0)
        for index, domain in enumerate(domains)
        if base_count + (1 if index < remainder else 0) > 0
    }


def _payload_for_domain(
    payload: dict[str, Any],
    *,
    domain: str,
    count: int,
) -> dict[str, Any]:
    domain_payload = dict(payload)
    options = _quest_generation_options(payload)
    options.pop("domain_counts", None)
    options["domains"] = [domain]
    options["count"] = count
    domain_payload["quest_generation_options"] = options
    return domain_payload


class QuestGeneratorAgent:
    """퀘스트 생성 요청을 leaf agent로 보내기 위한 상위 관리자입니다.

    `agent_id`는 외부 요청에서 이 에이전트를 찾을 때 쓰는 이름이고,
    `tools`가 비어 있다는 것은 이 단계에서는 도구를 실행하지 않고
    라우팅 프롬프트만 만든다는 뜻입니다.
    """

    agent_id = "quest_generator"
    tools = ()

    def __init__(self) -> None:
        self.production_agent = ProductionQuestAgent()
        self.delivery_agent = DeliveryQuestAgent()

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

    def build_prompt(self, payload: dict[str, Any], context: AgentContext) -> str:
        """Build a prompt for combined production/delivery quest generation."""

        draft_payload = self._build_combined_payload(payload, context)
        quest_count = len(draft_payload["quests"])
        return (
            "[ROLE]\n"
            "You are the top-level QuestForge quest generator.\n\n"
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
        """Build deterministic quests across the default production/delivery domains."""

        domain_counts = _resolve_domain_counts(payload)
        return AgentRunResult(
            agent=self.agent_id,
            payload=self._build_combined_payload(payload, context),
            metadata={
                "fallback": True,
                "sub_agent": self.agent_id,
                "domains": list(domain_counts),
            },
        )

    def _build_combined_payload(
        self,
        payload: dict[str, Any],
        context: AgentContext,
    ) -> dict[str, Any]:
        domain_counts = _resolve_domain_counts(payload)
        combined_quests: list[dict[str, Any]] = []
        for domain, count in domain_counts.items():
            domain_payload = _payload_for_domain(payload, domain=domain, count=count)
            if domain == "production":
                result = self.production_agent.fallback(domain_payload, context)
            else:
                result = self.delivery_agent.fallback(domain_payload, context)
            response = QuestResponse.model_validate(result.payload)
            for quest in response.model_dump(mode="json")["quests"]:
                quest["id"] = len(combined_quests) + 1
                combined_quests.append(quest)
        return QuestResponse.model_validate(
            {"quests": combined_quests}
        ).model_dump(mode="json")
