from __future__ import annotations

from pathlib import Path

import pytest

from quest_data.repository import QuestDataRepository

REPO_ROOT = Path(__file__).resolve().parents[2]
GAME_DATA_DIR = REPO_ROOT / "data" / "game"


def test_repository_loads_scenario_context_rows() -> None:
    repository = QuestDataRepository(GAME_DATA_DIR)

    contexts = repository.list_scenario_contexts()

    assert len(contexts) == 17
    assert contexts[0].context_id == "scenario_crash_survival"
    assert contexts[0].arc == "초반"
    assert "생존 기지" in contexts[0].summary


def test_repository_finds_spaceship_scenario_by_related_resource() -> None:
    repository = QuestDataRepository(GAME_DATA_DIR)

    contexts = repository.find_scenario_contexts(
        related_resource_ids=["resource_scout_spaceship"],
        quest_type="weekly",
    )

    assert [context.context_id for context in contexts] == [
        "scenario_scout_spaceship",
        "scenario_sandbox_space_industry",
    ]
    assert "정찰 우주선" in contexts[0].llm_prompt_hint


def test_repository_finds_scenario_by_related_recipe() -> None:
    repository = QuestDataRepository(GAME_DATA_DIR)

    contexts = repository.find_scenario_contexts(
        related_recipe_ids=["recipe_assemble_navigation_computer"],
        quest_type="weekly",
    )

    assert {context.context_id for context in contexts} == {
        "scenario_survivor_ai_expert",
        "scenario_magnetic_origin",
        "scenario_signal_amplifier",
        "scenario_scout_spaceship",
    }


def test_repository_loads_resources_and_recipes_by_id() -> None:
    repository = QuestDataRepository(GAME_DATA_DIR)

    resource = repository.get_resource("resource_scout_spaceship")
    recipe = repository.get_recipe("recipe_assemble_scout_spaceship")

    assert resource.resource_name == "소형 탐사 우주선"
    assert resource.resource_type == "최종 제작물"
    assert recipe.recipe_name == "소형 탐사 우주선 최종 조립 공정"
    assert recipe.output_resources == ["resource_scout_spaceship"]

def test_repository_lists_recipe_rows() -> None:
    repository = QuestDataRepository(GAME_DATA_DIR)

    recipes = repository.list_recipes()

    expected_recipe_id = 'recipe_make_circuit_board'
    recipe_prefix = 'recipe_'
    assert recipes
    assert any(recipe.recipe_id == expected_recipe_id for recipe in recipes)
    assert all(recipe.recipe_id.startswith(recipe_prefix) for recipe in recipes)

def test_repository_loads_reward_rules_from_csv() -> None:
    repository = QuestDataRepository(GAME_DATA_DIR)

    rule = repository.get_reward_rule("reward_daily_t2")

    assert rule.reward_rule_id == "reward_daily_t2"
    assert rule.quest_type == "daily"
    assert rule.tier == "T2"
    assert rule.base_xp == 120
    assert rule.base_credits == 35
    assert rule.resource_group == "기초 가공 자원"
    assert rule.resource_quantity_min == 2
    assert rule.resource_quantity_max == 4
    assert rule.llm_reward_hint

def test_repository_rejects_unknown_resource_id() -> None:
    repository = QuestDataRepository(GAME_DATA_DIR)

    with pytest.raises(KeyError, match="unknown_resource"):
        repository.get_resource("unknown_resource")
