from __future__ import annotations

from pydantic import ValidationError

from agents.base import AgentContext
from agents.quest_generator.agent import QuestGeneratorAgent
from agents.quest_generator.production_quest import (
    ProductionQuestAgent,
    _quest_candidate_resource_ids,
)
from agents.quest_generator.schemas import QuestResponse
from quest_data.repository import QuestDataRepository


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


def test_quest_generator_fallback_combines_production_and_delivery_by_default() -> None:
    agent = QuestGeneratorAgent()

    result = agent.fallback(
        {
            "quest_type": "daily",
            "game_state": {
                "inventory": {
                    "resource_iron_ore": 12,
                    "resource_copper_ore": 5,
                }
            },
        },
        _context(),
    )

    response = QuestResponse.model_validate(result.payload)
    domains = [quest.domain for quest in response.quests]
    assert len(response.quests) == 5
    assert domains.count("production") == 3
    assert domains.count("delivery") == 2
    assert result.metadata == {
        "fallback": True,
        "sub_agent": "quest_generator",
        "domains": ["production", "delivery"],
    }


def test_quest_generator_fallback_uses_domain_counts_override() -> None:
    agent = QuestGeneratorAgent()

    result = agent.fallback(
        {
            "quest_generation_options": {
                "domain_counts": {
                    "production": 2,
                    "delivery": 4,
                }
            }
        },
        _context(),
    )

    response = QuestResponse.model_validate(result.payload)
    domains = [quest.domain for quest in response.quests]
    assert len(response.quests) == 6
    assert domains.count("production") == 2
    assert domains.count("delivery") == 4


def test_quest_generator_fallback_omits_zero_count_domains() -> None:
    agent = QuestGeneratorAgent()

    result = agent.fallback(
        {
            "quest_generation_options": {
                "count": 1,
            }
        },
        _context(),
    )

    response = QuestResponse.model_validate(result.payload)
    assert len(response.quests) == 1
    assert response.quests[0].domain == "production"


def test_quest_generator_prompt_includes_retrieved_game_context() -> None:
    agent = QuestGeneratorAgent()

    prompt = agent.build_prompt(
        {
            "quest_type": "daily",
            "quest_generation_options": {
                "count": 2,
                "domain_counts": {"production": 1, "delivery": 1},
            },
            "current_main_quest": {
                "id": "main_signal_parts",
                "title": "신호 설비 부품 준비",
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
                    "resource_circuit_board": 2,
                    "resource_copper_wire": 18,
                },
                "unlocked_recipes": ["recipe_make_circuit_board"],
            },
        },
        _context(),
    )

    assert "[RETRIEVED_GAME_CONTEXT]" in prompt
    assert "resource_circuit_board" in prompt
    assert "recipe_make_circuit_board" in prompt
    assert "reward_rules" in prompt
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


def test_production_quest_fallback_does_not_use_contexts_in_plain_csv_order() -> None:
    agent = ProductionQuestAgent()
    payload = {
        "quest_generation_options": {
            "count": 5,
        },
        "resources": {
            "resource_iron_ore": 12,
            "resource_copper_ore": 5,
        },
    }

    result = agent.fallback(payload, _context())

    descriptions = [
        quest.description
        for quest in QuestResponse.model_validate(result.payload).quests
    ]
    repository = QuestDataRepository()
    resource_ids = _quest_candidate_resource_ids(payload, repository)
    contexts = repository.find_scenario_contexts(
        related_resource_ids=resource_ids,
        quest_type="daily",
    )
    plain_order_matches = [
        description.startswith(context.summary)
        for description, context in zip(descriptions, contexts)
    ]
    assert not all(plain_order_matches)


def test_production_quest_fallback_rewrites_and_rotates_scenario_contexts() -> None:
    agent = ProductionQuestAgent()
    payload = {
        "quest_generation_options": {
            "count": 3,
            "quest_types": ["daily"],
        },
        "resources": {
            "resource_copper_wire": 52,
            "resource_circuit_board": 9,
            "resource_reinforced_glass": 4,
        },
    }

    result = agent.fallback(payload, _context())

    descriptions = [
        quest.description
        for quest in QuestResponse.model_validate(result.payload).quests
    ]
    repository = QuestDataRepository()
    copied_summary = next(
        context.summary
        for context in repository.list_scenario_contexts()
        if context.context_id == "scenario_signal_tower_build"
    )
    daily_marker = "\uc624\ub298\uc758 \uc0dd\uc0b0 \ub8e8\ud2f4:"
    openings = [description.split(daily_marker)[0].strip() for description in descriptions]
    assert all(copied_summary not in description for description in descriptions)
    assert len(set(openings)) > 1


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


def test_production_quest_fallback_reads_current_main_required_quantities() -> None:
    agent = ProductionQuestAgent()

    result = agent.fallback(
        {
            "current_main_quest": {
                "id": "main_expand_mid_factory",
                "title": "mid_factory_expansion",
                "objectives": [
                    {
                        "target_item_id": "resource_steel_plate",
                        "required_quantity": 45,
                        "current_quantity": 18,
                    },
                    {
                        "target_item_id": "resource_copper_wire",
                        "required_quantity": 120,
                        "current_quantity": 52,
                    },
                    {
                        "target_item_id": "resource_electronic_circuit",
                        "required_quantity": 30,
                        "current_quantity": 9,
                    },
                ],
            },
            "quest_generation_options": {
                "count": 3,
                "quest_types": ["daily"],
                "link_to_main_quest": True,
            },
            "game_state": {
                "inventory": {
                    "resource_iron_ore": 140,
                }
            },
        },
        _context(),
    )

    quests = QuestResponse.model_validate(result.payload).quests
    target_ids = [quest.objectives[0].target_item_id for quest in quests]

    assert target_ids == [
        "resource_steel_plate",
        "resource_copper_wire",
        "resource_electronic_circuit",
    ]
    assert quests[0].objectives[0].quantity == 27
    assert all(quest.main_quest_link is not None for quest in quests)


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


def test_quest_plan_schema_accepts_llm_planning_fields() -> None:
    from agents.quest_generator.schemas import QuestPlanEnvelope

    plan = QuestPlanEnvelope.model_validate(
        {
            "quest_plan": {
                "analysis": "철괴와 구리괴 부족분이 초반 병목이다.",
                "domain_mix": {"production": 3, "delivery": 2},
                "quest_intents": [
                    {
                        "id": 1,
                        "domain": "production",
                        "target_item_id": "resource_iron_ingot",
                        "intent": "main_quest_deficit",
                        "reason": "메인 퀘스트 부족분을 보충한다.",
                        "title": "철괴 생산 안정화",
                        "description": "철괴 생산을 안정화해 다음 설비 제작을 준비하세요.",
                        "main_quest_link_reason": "메인 퀘스트의 철괴 부족분을 직접 보충합니다.",
                    }
                ],
            }
        }
    )

    assert plan.quest_plan.domain_mix.production == 3
    assert plan.quest_plan.domain_mix.delivery == 2
    assert plan.quest_plan.quest_intents[0].intent == "main_quest_deficit"


def test_quest_plan_schema_rejects_unknown_domain() -> None:
    from agents.quest_generator.schemas import QuestPlanEnvelope

    try:
        QuestPlanEnvelope.model_validate(
            {
                "quest_plan": {
                    "analysis": "invalid domain",
                    "domain_mix": {"production": 1, "delivery": 0},
                    "quest_intents": [
                        {
                            "id": 1,
                            "domain": "exploration",
                            "target_item_id": "resource_iron_ingot",
                            "intent": "bad_domain",
                            "reason": "domain is not allowed",
                        }
                    ],
                }
            }
        )
    except ValidationError as exc:
        assert "domain" in str(exc)
    else:
        raise AssertionError("Expected ValidationError")

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

def test_quest_response_requires_rewards() -> None:
    invalid_response = {
        "quests": [
            {
                "id": 1,
                "type": "daily",
                "domain": "production",
                "title": "reward missing",
                "description": "reward missing",
                "objectives": [
                    {
                        "target_item_id": "resource_iron_ore",
                        "quantity": 1,
                    }
                ],
                "clear_condition": {
                    "mode": "objective_count",
                    "target_item_id": "resource_iron_ore",
                    "required_quantity": 1,
                },
            }
        ]
    }

    try:
        QuestResponse.model_validate(invalid_response)
    except ValidationError as exc:
        assert "rewards" in str(exc)
    else:
        raise AssertionError("Expected ValidationError")


def test_build_quest_rewards_honors_selected_reward_types() -> None:
    from agents.quest_generator.rewards import build_quest_rewards

    rewards = build_quest_rewards(
        quest_type="daily",
        target_item_id="resource_iron_plate",
        payload={
            "progression": {"player_level": 6},
            "quest_generation_options": {
                "reward_options": {
                    "reward_types": ["resource"],
                    "resource_ids": ["resource_copper_ingot"],
                }
            },
        },
        context=_context(),
        repository=QuestDataRepository(),
    )

    assert rewards == [
        {
            "reward_type": "resource",
            "resource_id": "resource_copper_ingot",
            "resource_name": "구리괴",
            "amount": rewards[0]["amount"],
            "source_rule_id": "reward_daily_t2",
            "description": "기초 가공 자원 보상",
        }
    ]
    assert 2 <= rewards[0]["amount"] <= 4


def test_build_quest_rewards_accepts_tier_alias_resource_group() -> None:
    from agents.quest_generator.rewards import build_quest_rewards

    rewards = build_quest_rewards(
        quest_type="daily",
        target_item_id="resource_steel_plate",
        payload={
            "progression": {"player_level": 12},
            "quest_generation_options": {
                "reward_options": {
                    "reward_types": ["resource"],
                    "resource_groups": ["tier3"],
                }
            },
        },
        context=_context(),
        repository=QuestDataRepository(),
    )

    assert len(rewards) == 1
    assert rewards[0]["reward_type"] == "resource"
    assert rewards[0]["resource_id"].startswith("resource_")
    assert rewards[0]["resource_name"]
    assert rewards[0]["source_rule_id"] == "reward_daily_t3"
    assert 1 <= rewards[0]["amount"] <= 3


def test_build_quest_rewards_accepts_root_reward_options_for_legacy_clients() -> None:
    from agents.quest_generator.rewards import build_quest_rewards

    repository = QuestDataRepository()
    rewards = build_quest_rewards(
        quest_type="daily",
        target_item_id="resource_steel_plate",
        payload={
            "progression": {"player_level": 12},
            "reward_options": {
                "reward_types": ["xp", "resource"],
                "resource_groups": ["tier4"],
            },
        },
        context=_context(),
        repository=repository,
    )

    reward_types = [reward["reward_type"] for reward in rewards]
    resource_reward = next(
        reward for reward in rewards if reward["reward_type"] == "resource"
    )
    reward_resource = repository.get_resource(resource_reward["resource_id"])
    assert reward_types == ["xp", "resource"]
    assert reward_resource.resource_type == "\ud575\uc2ec \ubaa8\ub4c8"
    assert resource_reward["description"].startswith(reward_resource.resource_type)


def test_build_quest_rewards_falls_back_when_selection_is_empty() -> None:
    from agents.quest_generator.rewards import build_quest_rewards

    rewards = build_quest_rewards(
        quest_type="daily",
        target_item_id="resource_iron_plate",
        payload={
            "progression": {"player_level": 6},
            "quest_generation_options": {
                "reward_options": {"reward_types": []}
            },
        },
        context=_context(),
        repository=QuestDataRepository(),
    )

    assert rewards == [
        {
            "reward_type": "xp",
            "amount": 120,
            "source_rule_id": "reward_daily_t2",
            "description": "중반 진입 일일 퀘스트는 생산 라인 보강에 도움이 되는 보상으로 안내한다.",
        }
    ]


def test_production_quest_fallback_honors_reward_options() -> None:
    agent = ProductionQuestAgent()

    result = agent.fallback(
        {
            "quest_generation_options": {
                "count": 1,
                "reward_options": {
                    "reward_types": ["resource"],
                    "resource_ids": ["resource_copper_ingot"],
                },
            },
            "progression": {
                "player_level": 6,
            },
            "resources": {
                "resource_iron_plate": 12,
            },
        },
        _context(),
    )

    quest = QuestResponse.model_validate(result.payload).quests[0]
    assert len(quest.rewards) == 1
    assert quest.rewards[0].reward_type == "resource"
    assert quest.rewards[0].resource_id == "resource_copper_ingot"
    assert quest.rewards[0].source_rule_id == "reward_daily_t2"


def test_quest_generator_fallback_passes_reward_options_to_children() -> None:
    agent = QuestGeneratorAgent()

    result = agent.fallback(
        {
            "quest_generation_options": {
                "count": 2,
                "reward_options": {
                    "reward_types": ["resource"],
                    "resource_ids": ["resource_copper_ingot"],
                },
            },
            "progression": {
                "player_level": 6,
            },
            "game_state": {
                "inventory": {
                    "resource_iron_plate": 12,
                }
            },
        },
        _context(),
    )

    quests = QuestResponse.model_validate(result.payload).quests
    assert len(quests) == 2
    assert {quest.domain for quest in quests} == {"production", "delivery"}
    assert all(len(quest.rewards) == 1 for quest in quests)
    assert all(quest.rewards[0].reward_type == "resource" for quest in quests)
    assert all(quest.rewards[0].resource_id == "resource_copper_ingot" for quest in quests)

def test_quest_response_rejects_resource_reward_without_resource_identity() -> None:
    invalid_response = {
        "quests": [
            {
                "id": 1,
                "type": "daily",
                "domain": "production",
                "title": "bad reward",
                "description": "bad reward",
                "objectives": [
                    {
                        "target_item_id": "resource_iron_ore",
                        "quantity": 1,
                    }
                ],
                "clear_condition": {
                    "mode": "objective_count",
                    "target_item_id": "resource_iron_ore",
                    "required_quantity": 1,
                },
                "rewards": [
                    {
                        "reward_type": "resource",
                        "amount": 3,
                        "source_rule_id": "reward_daily_t2",
                        "description": "기초 가공 자원 보상",
                    }
                ],
            }
        ]
    }

    try:
        QuestResponse.model_validate(invalid_response)
    except ValidationError as exc:
        assert "resource_id" in str(exc)
    else:
        raise AssertionError("Expected ValidationError")
