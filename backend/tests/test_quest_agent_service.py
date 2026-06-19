from __future__ import annotations

from pydantic import ValidationError

from agents.base import AgentContext
from agents.quest_generator.production_quest import ProductionQuestAgent
from agents.quest_generator.schemas import QuestResponse


def _context() -> AgentContext:
    return AgentContext(
        request_id="request-test",
        session_id="session-test",
        client_id="client-test",
        metadata={},
    )


def test_production_quest_fallback_generates_five_quests_by_default() -> None:
    agent = ProductionQuestAgent()

    result = agent.fallback(
        {
            "resources": {
                "resource_iron_ore": 12,
                "resource_copper_ore": 5,
            }
        },
        _context(),
    )

    response = QuestResponse.model_validate(result.payload)
    assert len(response.quests) == 5
    assert {quest.type for quest in response.quests} == {
        "daily",
        "weekly",
        "surprise",
    }
    assert all(quest.domain == "production" for quest in response.quests)
    assert all(quest.clear_condition.mode in {"objective_count", "manual"} for quest in response.quests)
    assert len({quest.id for quest in response.quests}) == 5


def test_production_quest_fallback_uses_non_sequential_quantities() -> None:
    agent = ProductionQuestAgent()

    result = agent.fallback(
        {
            "resources": {
                "resource_iron_ore": 12,
                "resource_copper_ore": 5,
            }
        },
        _context(),
    )

    quests = QuestResponse.model_validate(result.payload).quests
    quantities = [quest.objectives[0].quantity for quest in quests]
    assert quantities != list(range(1, len(quantities) + 1))
    assert len(set(quantities)) > 2


def test_production_quest_fallback_uses_type_specific_description_patterns() -> None:
    agent = ProductionQuestAgent()

    result = agent.fallback(
        {
            "quest_generation_options": {
                "count": 6,
            },
            "resources": {
                "resource_iron_ore": 12,
                "resource_copper_ore": 5,
            },
        },
        _context(),
    )

    quests = QuestResponse.model_validate(result.payload).quests
    descriptions_by_type = {quest.type: quest.description for quest in quests}
    assert "오늘의 생산 루틴" in descriptions_by_type["daily"]
    assert "이번 주 생산 계획" in descriptions_by_type["weekly"]
    assert "예상 밖의 변수" in descriptions_by_type["surprise"]


def test_production_quest_fallback_uses_nested_count_override() -> None:
    agent = ProductionQuestAgent()

    result = agent.fallback(
        {
            "quest_generation_options": {
                "count": 8,
            },
            "resources": {
                "resource_iron_ore": 12,
            },
        },
        _context(),
    )

    response = QuestResponse.model_validate(result.payload)
    assert len(response.quests) == 8


def test_production_quest_fallback_uses_simple_count_when_nested_count_missing() -> None:
    agent = ProductionQuestAgent()

    result = agent.fallback(
        {
            "quest_count": 7,
        },
        _context(),
    )

    response = QuestResponse.model_validate(result.payload)
    assert len(response.quests) == 7


def test_production_quest_fallback_clamps_invalid_count_to_default() -> None:
    agent = ProductionQuestAgent()

    result = agent.fallback(
        {
            "quest_generation_options": {
                "count": 99,
            },
        },
        _context(),
    )

    response = QuestResponse.model_validate(result.payload)
    assert len(response.quests) == 5


def test_production_quest_fallback_uses_requested_quest_types() -> None:
    agent = ProductionQuestAgent()

    result = agent.fallback(
        {
            "quest_generation_options": {
                "count": 4,
                "quest_types": ["weekly", "surprise"],
            },
        },
        _context(),
    )

    response = QuestResponse.model_validate(result.payload)
    assert {quest.type for quest in response.quests}.issubset(
        {"weekly", "surprise"}
    )
    assert "daily" not in {quest.type for quest in response.quests}


def test_production_quest_fallback_links_to_current_main_quest() -> None:
    agent = ProductionQuestAgent()

    result = agent.fallback(
        {
            "current_main_quest": {
                "id": "main_restore_power_grid",
                "title": "전력망 복구",
                "description": "기지 생산 라인을 다시 가동하기 위해 전력망을 복구한다.",
                "objectives": [
                    {
                        "target_item_id": "resource_copper_ingot",
                        "quantity": 10,
                    }
                ],
                "progress": {
                    "resource_copper_ingot": 4,
                },
            },
            "quest_generation_options": {
                "count": 3,
                "quest_types": ["daily", "weekly", "surprise"],
                "link_to_main_quest": True,
            },
        },
        _context(),
    )

    response = QuestResponse.model_validate(result.payload)
    assert response.quests[0].main_quest_link is not None
    assert response.quests[0].main_quest_link.main_quest_id == "main_restore_power_grid"
    assert response.quests[0].objectives[0].target_item_id == "resource_copper_ingot"


def test_production_quest_fallback_mixes_main_and_independent_quests() -> None:
    agent = ProductionQuestAgent()

    result = agent.fallback(
        {
            "current_main_quest": {
                "id": "main_restore_power_grid",
                "title": "전력망 복구",
                "objectives": [
                    {
                        "target_item_id": "resource_copper_ingot",
                        "quantity": 10,
                    }
                ],
                "progress": {
                    "resource_copper_ingot": 4,
                },
            },
            "quest_generation_options": {
                "count": 5,
                "link_to_main_quest": True,
            },
        },
        _context(),
    )

    quests = QuestResponse.model_validate(result.payload).quests
    target_ids = {
        objective.target_item_id
        for quest in quests
        for objective in quest.objectives
    }
    linked_quests = [quest for quest in quests if quest.main_quest_link is not None]
    independent_quests = [quest for quest in quests if quest.main_quest_link is None]

    assert "resource_copper_ingot" in target_ids
    assert len(target_ids) > 1
    assert linked_quests
    assert independent_quests


def test_production_quest_fallback_prefers_payload_resources() -> None:
    agent = ProductionQuestAgent()

    result = agent.fallback(
        {
            "resources": {
                "resource_iron_ore": 12,
                "resource_copper_ore": 5,
            }
        },
        _context(),
    )

    target_ids = {
        objective.target_item_id
        for quest in QuestResponse.model_validate(result.payload).quests
        for objective in quest.objectives
    }
    assert "resource_iron_ore" in target_ids
    assert "resource_copper_ore" in target_ids


def test_production_quest_fallback_uses_game_state_inventory() -> None:
    agent = ProductionQuestAgent()

    result = agent.fallback(
        {
            "game_state": {
                "inventory": {
                    "resource_copper_ingot": 4,
                    "resource_iron_ingot": 2,
                },
                "unlocked_equipment": ["equipment_smelter"],
                "unlocked_recipes": ["recipe_smelt_copper"],
            }
        },
        _context(),
    )

    first_quest = QuestResponse.model_validate(result.payload).quests[0]
    assert first_quest.objectives[0].target_item_id == "resource_copper_ingot"


def test_production_quest_fallback_prefers_game_state_inventory_over_legacy_resources() -> None:
    agent = ProductionQuestAgent()

    result = agent.fallback(
        {
            "resources": {
                "resource_iron_ore": 12,
            },
            "game_state": {
                "inventory": {
                    "resource_copper_ingot": 4,
                }
            },
        },
        _context(),
    )

    first_quest = QuestResponse.model_validate(result.payload).quests[0]
    assert first_quest.objectives[0].target_item_id == "resource_copper_ingot"


def test_production_quest_fallback_mentions_unlocked_equipment_context() -> None:
    agent = ProductionQuestAgent()

    result = agent.fallback(
        {
            "game_state": {
                "inventory": {
                    "resource_copper_ingot": 4,
                },
                "unlocked_equipment": ["equipment_smelter"],
            },
        },
        _context(),
    )

    first_quest = QuestResponse.model_validate(result.payload).quests[0]
    assert "equipment_smelter" in first_quest.description


def test_production_quest_fallback_blends_context_into_description() -> None:
    agent = ProductionQuestAgent()

    result = agent.fallback(
        {
            "game_state": {
                "inventory": {
                    "resource_copper_ingot": 4,
                },
                "unlocked_equipment": ["equipment_smelter"],
                "unlocked_recipes": ["recipe_smelt_copper"],
            },
        },
        _context(),
    )

    first_quest = QuestResponse.model_validate(result.payload).quests[0]
    assert "상황:" not in first_quest.description
    assert "사용 가능한 설비:" not in first_quest.description
    assert "해금된 제작법:" not in first_quest.description
    assert "equipment_smelter" in first_quest.description
    assert "recipe_smelt_copper" in first_quest.description


def test_production_quest_fallback_uses_contextual_titles_and_descriptions() -> None:
    agent = ProductionQuestAgent()

    result = agent.fallback(
        {
            "resources": {
                "resource_scout_spaceship": 1,
            },
            "recent_events": ["scout_spaceship_unlocked"],
        },
        _context(),
    )

    quests = QuestResponse.model_validate(result.payload).quests
    assert all("Production Quest" not in quest.title for quest in quests)
    assert any("resource_scout_spaceship" in quest.description for quest in quests)


def test_quest_response_rejects_invalid_quantity() -> None:
    invalid_response = {
        "quests": [
            {
                "id": 1,
                "type": "daily",
                "domain": "production",
                "title": "invalid",
                "description": "invalid",
                "objectives": [
                    {
                        "target_item_id": "iron_ore",
                        "quantity": 0,
                    }
                ],
                "clear_condition": {
                    "mode": "objective_count",
                    "target_item_id": "iron_ore",
                    "required_quantity": 0,
                },
            }
        ]
    }

    try:
        QuestResponse.model_validate(invalid_response)
    except ValidationError as exc:
        assert "greater than 0" in str(exc)
    else:
        raise AssertionError("Expected ValidationError")
