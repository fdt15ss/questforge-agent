"""퀘스트 요청을 어떤 하위 퀘스트 에이전트가 처리할지 고르는 진입점입니다.

이 모듈은 실제 퀘스트 내용을 직접 만들지 않습니다. 대신 요청 payload와
실행 context를 LLM에게 보여주고, production/delivery 같은 leaf agent 중
어느 쪽이 이어서 처리해야 하는지 결정하게 합니다.
"""

from __future__ import annotations

import json
import os
from typing import Any

from agents.base import AgentContext, AgentRunResult
from agents.quest_generator.delivery_quest import DeliveryQuestAgent
from agents.quest_generator.production_quest import ProductionQuestAgent
from agents.quest_generator.schemas import QuestResponse
from llm.settings import LLMSettings
from quest_data.repository import QuestDataRepository
from quest_data.retrieval import retrieve_game_context
from quest_data.vector_context import default_vector_store

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


def _quest_prompt_mode(payload: dict[str, Any]) -> str:
    options = _quest_generation_options(payload)
    override = options.get("prompt_mode")
    if override in {"rich", "compact"}:
        return str(override)

    env_mode = os.getenv("QUESTFORGE_QUEST_PROMPT_MODE", "auto").strip().lower()
    if env_mode in {"rich", "compact"}:
        return env_mode

    default_provider = os.getenv("QUESTFORGE_LLM_DEFAULT_PROVIDER", "").strip().lower()
    if default_provider in {"none", "google", "openai", "local"}:
        return "compact" if default_provider == "local" else "rich"

    try:
        settings = LLMSettings.from_env()
    except ValueError:
        return "rich"
    return "compact" if settings.default.provider == "local" else "rich"


def _compact_request(payload: dict[str, Any]) -> dict[str, Any]:
    main_quest = payload.get("current_main_quest")
    main_summary: dict[str, Any] = {}
    if isinstance(main_quest, dict):
        main_summary = {
            "id": main_quest.get("id"),
            "title": main_quest.get("title"),
            "objectives": _compact_main_objectives(main_quest),
        }

    return {
        "quest_type": payload.get("quest_type", "daily"),
        "quest_generation_options": {
            "count": sum(_resolve_domain_counts(payload).values()),
            "domain_counts": _resolve_domain_counts(payload),
        },
        "progression": payload.get("progression", {}),
        "current_main_quest": main_summary,
        "recent_events": _string_items(payload.get("recent_events"), limit=3),
    }


def _compact_main_objectives(main_quest: dict[str, Any]) -> list[dict[str, Any]]:
    objectives = main_quest.get("objectives")
    if not isinstance(objectives, list):
        return []
    compact_objectives = []
    for objective in objectives[:5]:
        if isinstance(objective, dict):
            compact_objectives.append(
                {
                    "target_item_id": objective.get("target_item_id"),
                    "required_quantity": objective.get("required_quantity"),
                    "current_quantity": objective.get("current_quantity"),
                }
            )
    return compact_objectives


def _compact_game_context(context: dict[str, Any]) -> dict[str, Any]:
    return {
        "resources": _compact_rows(
            context.get("resources"),
            ("resource_id", "resource_name", "resource_type", "usage"),
        ),
        "recipes": _compact_rows(
            context.get("recipes"),
            ("recipe_id", "recipe_name", "input_resources", "output_resources", "tier"),
        ),
        "scenario_contexts": _compact_rows(
            context.get("scenario_contexts"),
            ("context_id", "theme", "quest_usage", "llm_prompt_hint"),
        ),
        "reward_rules": _compact_rows(
            context.get("reward_rules"),
            ("reward_rule_id", "quest_type", "tier", "resource_group", "llm_reward_hint"),
        ),
        "semantic_matches": _compact_semantic_matches(context.get("semantic_matches")),
    }


def _compact_rows(
    rows: object,
    fields: tuple[str, ...],
    *,
    limit: int = 3,
) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        return []
    compact_rows: list[dict[str, Any]] = []
    for row in rows[:limit]:
        if isinstance(row, dict):
            compact_rows.append({field: row.get(field) for field in fields if field in row})
    return compact_rows


def _compact_semantic_matches(rows: object, *, limit: int = 3) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        return []
    compact_rows: list[dict[str, Any]] = []
    for row in rows[:limit]:
        if not isinstance(row, dict):
            continue
        document = str(row.get("document", ""))[:180]
        compact_rows.append(
            {
                "id": row.get("id"),
                "source_type": row.get("source_type"),
                "source_id": row.get("source_id"),
                "document": document,
            }
        )
    return compact_rows


def _string_items(value: object, *, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value[:limit] if isinstance(item, str) and item]


class QuestGeneratorAgent:
    """퀘스트 생성 요청을 leaf agent로 보내기 위한 상위 관리자입니다.

    `agent_id`는 외부 요청에서 이 에이전트를 찾을 때 쓰는 이름이고,
    `tools`가 비어 있다는 것은 이 단계에서는 도구를 실행하지 않고
    라우팅 프롬프트만 만든다는 뜻입니다.
    """

    agent_id = "quest_generator"
    tools = ()
    response_schema = QuestResponse

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
            "Return only one JSON object with this shape:\n"
            '{"sub_agent":"quest_generator.production_quest"}\n'
            "The sub_agent value MUST be one of ALLOWED_LEAF_AGENT_IDS. Do not include markdown or explanations."
        )

    def build_prompt(self, payload: dict[str, Any], context: AgentContext) -> str:
        """Build a prompt for combined production/delivery quest generation."""

        draft_payload = self._build_combined_payload(payload, context)
        retrieved_game_context = retrieve_game_context(
            payload,
            QuestDataRepository(),
            vector_store=default_vector_store(),
        )
        quest_count = len(draft_payload["quests"])
        domain_mix = {
            "production": sum(
                1 for quest in draft_payload["quests"] if quest["domain"] == "production"
            ),
            "delivery": sum(
                1 for quest in draft_payload["quests"] if quest["domain"] == "delivery"
            ),
        }
        quest_plan_contract = {
            "quest_plan": {
                "analysis": "...",
                "domain_mix": domain_mix,
                "quest_intents": [
                    {
                        "id": quest["id"],
                        "domain": quest["domain"],
                        "target_item_id": quest["objectives"][0]["target_item_id"],
                        "intent": "main_quest_deficit",
                        "reason": "...",
                        "title": "...",
                        "description": "...",
                        "main_quest_link_reason": "...",
                    }
                    for quest in draft_payload["quests"]
                ],
            }
        }
        if _quest_prompt_mode(payload) == "compact":
            compact_request = _compact_request(payload)
            compact_game_context = _compact_game_context(retrieved_game_context)
            return (
                "[ROLE]\n"
                "QuestForge quest planner.\n\n"
                "[TASK]\n"
                f"Return exactly {quest_count} Korean quest planning intents as one JSON object. "
                "Use the QuestPlan schema. Keep each DRAFT_QUESTS id, domain, and target_item_id exactly. "
                "Server owns objectives, clear_condition, rewards, quantities, and final count. "
                "Return JSON only. No markdown.\n\n"
                "[DRAFT_QUESTS]\n"
                f"{json.dumps(draft_payload, ensure_ascii=False, separators=(",", ":"))}\n\n"
                "[COMPACT_REQUEST]\n"
                f"{json.dumps(compact_request, ensure_ascii=False, separators=(",", ":"), default=str)}\n\n"
                "[COMPACT_GAME_CONTEXT]\n"
                f"{json.dumps(compact_game_context, ensure_ascii=False, separators=(",", ":"))}\n\n"
                "[OUTPUT_JSON]\n"
                f"{json.dumps(quest_plan_contract, ensure_ascii=False, separators=(",", ":"))}\n"
            )

        return (
            "[ROLE]\n"
            "You are the top-level QuestForge quest generator.\n\n"
            "[TASK]\n"
            f"Return exactly {quest_count} quest planning intents as one JSON object. "
            "Use the QuestPlan schema. Analyze REQUEST_PAYLOAD and DRAFT_QUESTS, then decide "
            "why each draft quest is useful right now. Each quest_intents item must reference "
            "a draft quest id and must keep that draft quest's domain and target_item_id. "
            "Do not return quests, objectives, clear_condition, rewards, quantity, metadata, "
            "markdown, or explanations outside JSON. "
            "The server will preserve quantity, rewards, clear_condition, and final quest count. "
            "You may improve title, description, and main_quest_link_reason. "
            "Use RETRIEVED_GAME_CONTEXT as authoritative game knowledge, but do not invent "
            "server-owned objectives, clear conditions, rewards, quantities, or schema fields. "
            "The analysis, reason, title, and description MUST be written in Korean.\n\n"
            "[DRAFT_QUESTS]\n"
            f"{json.dumps(draft_payload, ensure_ascii=False)}\n\n"
            "[REQUEST_PAYLOAD]\n"
            f"{json.dumps(payload, ensure_ascii=False, default=str)}\n\n"
            "[RETRIEVED_GAME_CONTEXT]\n"
            f"{json.dumps(retrieved_game_context, ensure_ascii=False)}\n\n"
            "[OUTPUT_CONTRACT]\n"
            "Return only one JSON object with this shape:\n"
            f"{json.dumps(quest_plan_contract, ensure_ascii=False, separators=(",", ":"))}\n"
            "Do not include quest_text_updates, quests, objectives, clear_condition, rewards, metadata, markdown, or explanations.\n"
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
