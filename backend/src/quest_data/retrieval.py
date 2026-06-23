"""Structured CSV retrieval for quest-generation prompts."""

from __future__ import annotations

import re
from dataclasses import asdict
from typing import Any, TypedDict

from quest_data.repository import QuestDataRepository

_RESOURCE_ID_RE = re.compile(r"resource_[a-z0-9_]+")
_RECIPE_ID_RE = re.compile(r"recipe_[a-z0-9_]+")
_TEXT_TOKEN_RE = re.compile(r"[A-Za-z0-9_가-힣]{2,}")


class RetrievedGameContext(TypedDict):
    query: dict[str, list[str]]
    resources: list[dict[str, Any]]
    recipes: list[dict[str, Any]]
    scenario_contexts: list[dict[str, Any]]
    reward_rules: list[dict[str, Any]]


def retrieve_game_context(
    payload: dict[str, Any],
    repository: QuestDataRepository,
    *,
    max_resources: int = 8,
    max_recipes: int = 6,
    max_scenarios: int = 5,
    max_reward_rules: int = 3,
) -> RetrievedGameContext:
    """Return compact, deterministic CSV context relevant to a quest request."""

    query = _query_signals(payload)
    resource_ids = set(query["resource_ids"])
    recipe_ids = set(query["recipe_ids"])
    quest_types = set(query["quest_types"])
    tokens = set(query["text_tokens"])

    resources = _ranked(
        repository.list_resources(),
        lambda row: _resource_score(row, resource_ids, tokens),
        lambda row: row.resource_id,
        max_resources,
    )
    ranked_resource_ids = {resource.resource_id for resource in resources}
    all_resource_ids = resource_ids | ranked_resource_ids

    recipes = _ranked(
        repository.list_recipes(),
        lambda row: _recipe_score(row, all_resource_ids, recipe_ids, tokens),
        lambda row: row.recipe_id,
        max_recipes,
    )
    ranked_recipe_ids = {recipe.recipe_id for recipe in recipes}
    all_recipe_ids = recipe_ids | ranked_recipe_ids

    scenarios = _ranked(
        repository.list_scenario_contexts(),
        lambda row: _scenario_score(
            row,
            all_resource_ids,
            all_recipe_ids,
            quest_types,
            tokens,
        ),
        lambda row: row.context_id,
        max_scenarios,
    )
    reward_rules = _ranked(
        repository.list_reward_rules(),
        lambda row: _reward_rule_score(row, quest_types, tokens),
        lambda row: row.reward_rule_id,
        max_reward_rules,
    )

    return {
        "query": query,
        "resources": [_row_dict(row) for row in resources],
        "recipes": [_row_dict(row) for row in recipes],
        "scenario_contexts": [_row_dict(row) for row in scenarios],
        "reward_rules": [_row_dict(row) for row in reward_rules],
    }


def _query_signals(payload: dict[str, Any]) -> dict[str, list[str]]:
    resource_ids: list[str] = []
    recipe_ids: list[str] = []
    quest_types: list[str] = []

    main_quest = payload.get("current_main_quest")
    if isinstance(main_quest, dict):
        objectives = main_quest.get("objectives")
        if isinstance(objectives, list):
            for objective in objectives:
                if isinstance(objective, dict):
                    _append_unique(resource_ids, objective.get("target_item_id"))

    game_state = payload.get("game_state")
    if isinstance(game_state, dict):
        inventory = game_state.get("inventory")
        if isinstance(inventory, dict):
            for key in inventory:
                _append_unique(resource_ids, key)
        unlocked_recipes = game_state.get("unlocked_recipes")
        if isinstance(unlocked_recipes, list):
            for recipe_id in unlocked_recipes:
                _append_unique(recipe_ids, recipe_id)

    _append_unique(quest_types, payload.get("quest_type"))
    options = payload.get("quest_generation_options")
    if isinstance(options, dict):
        for quest_type in _string_list(options.get("quest_types")):
            _append_unique(quest_types, quest_type)
        for quest_type in _string_list(options.get("types")):
            _append_unique(quest_types, quest_type)

    text = " ".join(_collect_text(payload))
    for resource_id in _RESOURCE_ID_RE.findall(text):
        _append_unique(resource_ids, resource_id)
    for recipe_id in _RECIPE_ID_RE.findall(text):
        _append_unique(recipe_ids, recipe_id)

    tokens = [
        token.lower()
        for token in _TEXT_TOKEN_RE.findall(text)
        if not token.startswith(("resource_", "recipe_"))
    ]

    return {
        "resource_ids": resource_ids,
        "recipe_ids": recipe_ids,
        "quest_types": quest_types or ["daily"],
        "text_tokens": _unique(tokens)[:30],
    }


def _resource_score(row: Any, resource_ids: set[str], tokens: set[str]) -> int:
    score = 0
    if row.resource_id in resource_ids:
        score += 100
    score += 2 * _token_overlap(tokens, _row_text(row))
    return score


def _recipe_score(
    row: Any,
    resource_ids: set[str],
    recipe_ids: set[str],
    tokens: set[str],
) -> int:
    score = 0
    if row.recipe_id in recipe_ids:
        score += 100
    score += 25 * len(resource_ids.intersection(row.input_resources))
    score += 35 * len(resource_ids.intersection(row.output_resources))
    score += 2 * _token_overlap(tokens, _row_text(row))
    return score


def _scenario_score(
    row: Any,
    resource_ids: set[str],
    recipe_ids: set[str],
    quest_types: set[str],
    tokens: set[str],
) -> int:
    score = 0
    score += 30 * len(resource_ids.intersection(row.related_resources))
    score += 25 * len(recipe_ids.intersection(row.related_recipes))
    score += 15 * len(quest_types.intersection(row.related_quest_types))
    score += _token_overlap(tokens, _row_text(row))
    return score


def _reward_rule_score(row: Any, quest_types: set[str], tokens: set[str]) -> int:
    score = 0
    if row.quest_type in quest_types:
        score += 50
    score += _token_overlap(tokens, _row_text(row))
    return score


def _ranked(
    rows: list[Any],
    score_row: Any,
    key_row: Any,
    limit: int,
) -> list[Any]:
    scored = [(score_row(row), key_row(row), row) for row in rows]
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [row for score, _key, row in scored if score > 0][: max(limit, 0)]


def _row_dict(row: Any) -> dict[str, Any]:
    return asdict(row)


def _row_text(row: Any) -> str:
    return " ".join(str(value) for value in asdict(row).values())


def _token_overlap(tokens: set[str], text: str) -> int:
    if not tokens:
        return 0
    row_tokens = {token.lower() for token in _TEXT_TOKEN_RE.findall(text)}
    return len(tokens.intersection(row_tokens))


def _collect_text(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        text: list[str] = []
        for key, nested in value.items():
            text.extend(_collect_text(key))
            text.extend(_collect_text(nested))
        return text
    if isinstance(value, list):
        text = []
        for nested in value:
            text.extend(_collect_text(nested))
        return text
    return []


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]


def _append_unique(values: list[str], value: object) -> None:
    if isinstance(value, str) and value and value not in values:
        values.append(value)


def _unique(values: list[str]) -> list[str]:
    unique_values: list[str] = []
    for value in values:
        if value not in unique_values:
            unique_values.append(value)
    return unique_values
