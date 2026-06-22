"""CSV row를 agent가 쓰기 쉬운 값 객체로 바꾸는 스키마입니다."""

from __future__ import annotations

import re
from dataclasses import dataclass

_RESOURCE_ID_PATTERN = re.compile(r"resource_[A-Za-z0-9_]+")
_RECIPE_ID_PATTERN = re.compile(r"recipe_[A-Za-z0-9_]+")


def _split_semicolon_ids(value: str) -> list[str]:
    return [part.strip() for part in value.split(";") if part.strip()]


def _find_ids(pattern: re.Pattern[str], value: str) -> list[str]:
    return list(dict.fromkeys(match.group(0) for match in pattern.finditer(value)))


def _parse_int_range(value: str) -> tuple[int, int]:
    parts = [part.strip() for part in value.split("-", 1)]
    if len(parts) != 2:
        return (1, 1)
    try:
        minimum = int(parts[0])
        maximum = int(parts[1])
    except ValueError:
        return (1, 1)
    if minimum <= 0 or maximum < minimum:
        return (1, 1)
    return (minimum, maximum)

@dataclass(frozen=True)
class QuestRewardRuleRow:
    reward_rule_id: str
    quest_type: str
    tier: str
    recommended_level_range: str
    base_xp: int
    base_credits: int
    resource_group: str
    resource_quantity_min: int
    resource_quantity_max: int
    scaling: str
    llm_reward_hint: str

    @classmethod
    def from_csv_row(cls, row: dict[str, str]) -> QuestRewardRuleRow:
        quantity_min, quantity_max = _parse_int_range(row["보상자원수량범위"])
        return cls(
            reward_rule_id=row["보상룰ID"],
            quest_type=row["퀘스트타입"],
            tier=row["진행티어"],
            recommended_level_range=row["권장레벨범위"],
            base_xp=int(row["기본XP"]),
            base_credits=int(row["기본크레딧"]),
            resource_group=row["보상자원그룹"],
            resource_quantity_min=quantity_min,
            resource_quantity_max=quantity_max,
            scaling=row["보상스케일링"],
            llm_reward_hint=row["LLM보상설명힌트"],
        )

@dataclass(frozen=True)
class ResourceRow:
    resource_id: str
    resource_name: str
    resource_type: str
    acquisition_method: str
    usage: str

    @classmethod
    def from_csv_row(cls, row: dict[str, str]) -> ResourceRow:
        return cls(
            resource_id=row["자원ID"],
            resource_name=row["자원명"],
            resource_type=row["종류"],
            acquisition_method=row["획득방법"],
            usage=row["사용처"],
        )


@dataclass(frozen=True)
class RecipeRow:
    recipe_id: str
    recipe_name: str
    input_resources: list[str]
    output_resources: list[str]
    tier: str
    quest_tags: list[str]
    llm_prompt_hint: str

    @classmethod
    def from_csv_row(cls, row: dict[str, str]) -> RecipeRow:
        return cls(
            recipe_id=row["레시피ID"],
            recipe_name=row["레시피명"],
            input_resources=_find_ids(_RESOURCE_ID_PATTERN, row["입력자원"]),
            output_resources=_find_ids(_RESOURCE_ID_PATTERN, row["출력자원"]),
            tier=row["진행티어"],
            quest_tags=_split_semicolon_ids(row["퀘스트생성태그"]),
            llm_prompt_hint=row["LLM설명힌트"],
        )


@dataclass(frozen=True)
class ScenarioContextRow:
    context_id: str
    arc: str
    theme: str
    summary: str
    quest_usage: str
    related_resources: list[str]
    related_recipes: list[str]
    related_quest_types: list[str]
    llm_prompt_hint: str
    source_section: str

    @classmethod
    def from_csv_row(cls, row: dict[str, str]) -> ScenarioContextRow:
        return cls(
            context_id=row["context_id"],
            arc=row["arc"],
            theme=row["theme"],
            summary=row["summary"],
            quest_usage=row["quest_usage"],
            related_resources=_split_semicolon_ids(row["related_resources"]),
            related_recipes=_split_semicolon_ids(row["related_recipes"]),
            related_quest_types=_split_semicolon_ids(row["related_quest_types"]),
            llm_prompt_hint=row["llm_prompt_hint"],
            source_section=row["source_section"],
        )
