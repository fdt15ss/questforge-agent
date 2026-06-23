from __future__ import annotations

from pathlib import Path

from quest_data.repository import QuestDataRepository
from quest_data.retrieval import retrieve_game_context


GAME_DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "game"


def _payload() -> dict[str, object]:
    return {
        "quest_type": "daily",
        "quest_generation_options": {
            "quest_types": ["daily"],
        },
        "current_main_quest": {
            "title": "회로기판 생산망 복구",
            "description": "구리선과 철판으로 회로기판을 만들어 신호 설비를 준비한다.",
            "objectives": [
                {
                    "target_item_id": "resource_circuit_board",
                    "required_quantity": 10,
                    "current_quantity": 2,
                }
            ],
        },
        "game_state": {
            "inventory": {
                "resource_copper_wire": 18,
                "resource_iron_plate": 9,
                "resource_circuit_board": 2,
            },
            "unlocked_recipes": ["recipe_make_circuit_board"],
        },
        "recent_events": [
            "회로기판 생산이 신호 설비 확장의 병목이 되었다.",
        ],
    }


def test_retrieve_game_context_finds_resources_recipes_and_rewards() -> None:
    repository = QuestDataRepository(GAME_DATA_DIR)

    context = retrieve_game_context(_payload(), repository)

    resource_ids = [resource["resource_id"] for resource in context["resources"]]
    recipe_ids = [recipe["recipe_id"] for recipe in context["recipes"]]
    reward_rule_ids = [
        reward_rule["reward_rule_id"] for reward_rule in context["reward_rules"]
    ]

    assert "resource_circuit_board" in resource_ids
    assert "recipe_make_circuit_board" in recipe_ids
    assert "reward_daily_t" in "".join(reward_rule_ids)
    assert context["query"]["resource_ids"][:1] == ["resource_circuit_board"]


def test_retrieve_game_context_is_deterministic_and_respects_limits() -> None:
    repository = QuestDataRepository(GAME_DATA_DIR)

    first = retrieve_game_context(
        _payload(),
        repository,
        max_resources=3,
        max_recipes=2,
        max_scenarios=2,
        max_reward_rules=1,
    )
    second = retrieve_game_context(
        _payload(),
        repository,
        max_resources=3,
        max_recipes=2,
        max_scenarios=2,
        max_reward_rules=1,
    )

    assert first == second
    assert len(first["resources"]) <= 3
    assert len(first["recipes"]) <= 2
    assert len(first["scenario_contexts"]) <= 2
    assert len(first["reward_rules"]) <= 1
