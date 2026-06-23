"""퀘스트 보상 payload를 CSV 보상룰과 요청 옵션에서 생성합니다."""

from __future__ import annotations

from typing import Any

from agents.base import AgentContext
from quest_data.repository import QuestDataRepository
from quest_data.schemas import QuestRewardRuleRow, ResourceRow

_ALLOWED_REWARD_TYPES = ("xp", "credits", "resource")
_DEFAULT_REWARD_TYPES = ("xp", "credits", "resource")
_RESOURCE_GROUP_ALIASES = {
    "t1": "원재료",
    "tier1": "원재료",
    "t2": "기초 가공 자원",
    "tier2": "기초 가공 자원",
    "t3": "중급 가공 자원",
    "tier3": "중급 가공 자원",
    "t4": "고급 핵심 모듈",
    "tier4": "고급 핵심 모듈",
}


def _tier_from_payload(payload: dict[str, Any]) -> str:
    progression = payload.get("progression")
    player_level = None
    if isinstance(progression, dict):
        raw_level = progression.get("player_level")
        if isinstance(raw_level, int):
            player_level = raw_level
    if player_level is None:
        return "T1"
    if player_level <= 5:
        return "T1"
    if player_level <= 10:
        return "T2"
    if player_level <= 15:
        return "T3"
    return "T4"


def _reward_options(payload: dict[str, Any]) -> dict[str, Any]:
    options = payload.get("quest_generation_options")
    if isinstance(options, dict):
        reward_options = options.get("reward_options")
        if isinstance(reward_options, dict):
            return reward_options

    legacy_reward_options = payload.get("reward_options")
    if isinstance(legacy_reward_options, dict):
        return legacy_reward_options
    return {}


def _selected_reward_types(payload: dict[str, Any]) -> list[str]:
    reward_options = _reward_options(payload)
    raw_types = reward_options.get("reward_types")
    if raw_types is None:
        return list(_DEFAULT_REWARD_TYPES)
    if not isinstance(raw_types, list):
        return ["xp"]
    selected = [value for value in raw_types if value in _ALLOWED_REWARD_TYPES]
    return selected or ["xp"]


def _normalize_resource_group(resource_group: str) -> str:
    normalized_key = resource_group.strip().lower().replace("_", "").replace("-", "")
    return _RESOURCE_GROUP_ALIASES.get(normalized_key, resource_group)


def _deterministic_index(seed: str, length: int) -> int:
    if length <= 0:
        return 0
    return sum(ord(char) for char in seed) % length


def _deterministic_amount(*, rule: QuestRewardRuleRow, seed: str) -> int:
    spread = rule.resource_quantity_max - rule.resource_quantity_min
    if spread <= 0:
        return rule.resource_quantity_min
    return rule.resource_quantity_min + (sum(ord(char) for char in seed) % (spread + 1))


def _resource_candidates(
    *,
    payload: dict[str, Any],
    rule: QuestRewardRuleRow,
    repository: QuestDataRepository,
) -> list[ResourceRow]:
    reward_options = _reward_options(payload)
    resource_ids = reward_options.get("resource_ids")
    if isinstance(resource_ids, list) and resource_ids:
        valid_ids = {value for value in resource_ids if isinstance(value, str)}
        return [
            resource
            for resource in repository.list_resources()
            if resource.resource_id in valid_ids
        ]

    resource_groups = reward_options.get("resource_groups")
    if isinstance(resource_groups, list) and resource_groups:
        candidates: list[ResourceRow] = []
        seen_ids: set[str] = set()
        for resource_group in resource_groups:
            if not isinstance(resource_group, str):
                continue
            for resource in repository.find_reward_resource_candidates(
                _normalize_resource_group(resource_group)
            ):
                if resource.resource_id not in seen_ids:
                    seen_ids.add(resource.resource_id)
                    candidates.append(resource)
        return candidates

    return repository.find_reward_resource_candidates(rule.resource_group)


def _select_reward_resource(
    *,
    candidates: list[ResourceRow],
    target_item_id: str,
    quest_type: str,
    context: AgentContext,
) -> ResourceRow | None:
    if not candidates:
        return None
    seed = f"{target_item_id}:{quest_type}:{context.session_id}:{context.client_id}"
    return candidates[_deterministic_index(seed, len(candidates))]


def _resource_reward_description(
    *,
    payload: dict[str, Any],
    rule: QuestRewardRuleRow,
    resource: ResourceRow,
) -> str:
    reward_options = _reward_options(payload)
    resource_groups = reward_options.get("resource_groups")
    if isinstance(resource_groups, list) and resource_groups:
        return f"{resource.resource_type} 보상"
    return f"{rule.resource_group} 보상"


def build_quest_rewards(
    *,
    quest_type: str,
    target_item_id: str,
    payload: dict[str, Any],
    context: AgentContext,
    repository: QuestDataRepository,
) -> list[dict[str, Any]]:
    """quest type, 진행도, 요청 reward_options에 맞는 보상을 생성합니다."""

    tier = _tier_from_payload(payload)
    rule = repository.find_reward_rule(quest_type=quest_type, tier=tier)
    selected_types = _selected_reward_types(payload)
    rewards: list[dict[str, Any]] = []

    if "xp" in selected_types:
        rewards.append(
            {
                "reward_type": "xp",
                "amount": rule.base_xp,
                "source_rule_id": rule.reward_rule_id,
                "description": rule.llm_reward_hint,
            }
        )

    if "credits" in selected_types:
        rewards.append(
            {
                "reward_type": "credits",
                "amount": rule.base_credits,
                "source_rule_id": rule.reward_rule_id,
                "description": rule.llm_reward_hint,
            }
        )

    if "resource" in selected_types:
        candidates = _resource_candidates(
            payload=payload,
            rule=rule,
            repository=repository,
        )
        reward_resource = _select_reward_resource(
            candidates=candidates,
            target_item_id=target_item_id,
            quest_type=quest_type,
            context=context,
        )
        if reward_resource is not None:
            rewards.append(
                {
                    "reward_type": "resource",
                    "resource_id": reward_resource.resource_id,
                    "resource_name": reward_resource.resource_name,
                    "amount": _deterministic_amount(
                        rule=rule,
                        seed=f"{target_item_id}:{quest_type}:{rule.reward_rule_id}",
                    ),
                    "source_rule_id": rule.reward_rule_id,
                    "description": _resource_reward_description(
                        payload=payload,
                        rule=rule,
                        resource=reward_resource,
                    ),
                }
            )

    return rewards or [
        {
            "reward_type": "xp",
            "amount": rule.base_xp,
            "source_rule_id": rule.reward_rule_id,
            "description": rule.llm_reward_hint,
        }
    ]