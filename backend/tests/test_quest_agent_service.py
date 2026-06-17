from __future__ import annotations

import random

from pydantic import ValidationError

from agents.quest_generator.schemas import QuestResponse
from agents.quest_generator.service import QuestAgentService


def test_service_returns_five_random_quests_from_example_pool() -> None:
    service = QuestAgentService(rng=random.Random(0))

    result = service.generate_quest_json()

    QuestResponse.model_validate(result)
    quests = result["quests"]
    assert len(quests) == 5
    assert len({quest["id"] for quest in quests}) == 5
    assert {quest["id"] for quest in quests}.issubset(set(range(1, 11)))
    assert all(isinstance(quest["id"], int) for quest in quests)


def test_service_available_quest_pool_has_ten_csv_based_examples() -> None:
    service = QuestAgentService(rng=random.Random(0))

    result = service.available_quest_json()

    assert len(result) == 10
    assert [quest["id"] for quest in result] == list(range(1, 11))
    assert {quest["objectives"][0]["target_item_id"] for quest in result} == {
        "iron_ore",
        "copper_ore",
        "coal",
        "wood",
        "iron_ingot",
        "copper_ingot",
        "iron_powder",
        "copper_powder",
        "charcoal",
        "coal_dust",
    }


def test_service_quest_objectives_keep_item_id_and_quantity_only() -> None:
    service = QuestAgentService(rng=random.Random(1))

    result = service.generate_quest_json()

    objective = result["quests"][0]["objectives"][0]
    assert set(objective) == {"target_item_id", "quantity"}
    assert "action" not in objective
    assert "target_item_name" not in objective


def test_service_returns_quests_selected_by_ids_from_example_pool() -> None:
    service = QuestAgentService(rng=random.Random(1))

    result = service.generate_quest_json_from_ids([10, 9, 8, 7, 6])

    QuestResponse.model_validate(result)
    assert [quest["id"] for quest in result["quests"]] == [10, 9, 8, 7, 6]
    assert result["quests"][0]["objectives"][0]["target_item_id"] == "coal_dust"


def test_service_rejects_invalid_selected_quest_ids() -> None:
    service = QuestAgentService(rng=random.Random(1))

    try:
        service.generate_quest_json_from_ids([1, 2, 3, 4, 99])
    except ValueError as exc:
        assert "알 수 없는 퀘스트 id입니다: 99" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_quest_response_rejects_invalid_quantity() -> None:
    invalid_response = {
        "quests": [
            {
                "id": 1,
                "type": "production",
                "title": "invalid",
                "description": "invalid",
                "objectives": [
                    {
                        "target_item_id": "iron_ore",
                        "quantity": 0,
                    }
                ],
            }
        ]
    }

    try:
        QuestResponse.model_validate(invalid_response)
    except ValidationError as exc:
        assert "greater than 0" in str(exc)
    else:
        raise AssertionError("Expected ValidationError")
