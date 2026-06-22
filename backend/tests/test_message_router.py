from __future__ import annotations

import json

from agents.pipeline import AgentPipeline
from tests.harness import (
    PipelineScenario,
    StubLLM,
    assert_agent_error,
    assert_agent_response,
    leaf_agent_decision,
    run_pipeline_scenario,
    top_agent_decision,
)

PRODUCTION_QUEST_RESPONSE = json.dumps(
    {
        "quests": [
            {
                "id": 1,
                "type": "daily",
                "domain": "production",
                "title": "Secure resource_iron_ore",
                "description": "Produce 1 unit for resource_iron_ore.",
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
    },
    ensure_ascii=False,
)
DELIVERY_QUEST_RESPONSE = json.dumps(
    {
        "quests": [
            {
                "id": 1,
                "type": "daily",
                "domain": "delivery",
                "title": "Move plates",
                "description": "Deliver plates to the central storage.",
                "objectives": [
                    {
                        "target_item_id": "resource_iron_plate",
                        "quantity": 2,
                    }
                ],
                "clear_condition": {
                    "mode": "objective_count",
                    "target_item_id": "resource_iron_plate",
                    "required_quantity": 2,
                },
            }
        ]
    },
    ensure_ascii=False,
)
QUEST_PAYLOAD = {
    "sub_agent": "quest_generator.delivery_quest",
    "progression": {"stage": "early"},
    "resources": {"iron_ore": 12},
}


def test_pipeline_uses_prompt_based_top_level_routing() -> None:
    response, llm = run_pipeline_scenario(
        PipelineScenario(
            name="top-level quest generator",
            agent="quest_generator",
            payload={"message": "create an objective"},
            request_id="request-1",
            llm_responses=[
                top_agent_decision("quest_generator"),
                None,
            ],
        )
    )

    assert_agent_response(
        response,
        agent="quest_generator",
    )
    assert len(response["payload"]["quests"]) == 5
    assert {
        quest["domain"]
        for quest in response["payload"]["quests"]
    } == {"production", "delivery"}
    assert "[OUTPUT_CONTRACT]" in llm.prompts[0]
    assert "[ALLOWED_LEAF_AGENT_IDS]" not in llm.prompts[1]
    assert "[TOOL_RESULT]" not in llm.prompts[-1]


def test_pipeline_routes_explicit_quest_leaf_without_leaf_llm_decision() -> None:
    pipeline = AgentPipeline(
        llm=StubLLM(
            [
                top_agent_decision("quest_generator"),
                DELIVERY_QUEST_RESPONSE,
            ]
        )
    )

    response = pipeline.run(
        {
            "type": "agent.request",
            "request_id": "request-explicit-delivery",
            "agent": "quest_generator",
            "payload": QUEST_PAYLOAD,
        }
    )

    assert_agent_response(
        response,
        agent="quest_generator",
        sub_agent="quest_generator.delivery_quest",
    )
    assert response["payload"]["quests"][0]["domain"] == "delivery"


def test_pipeline_accepts_json_top_level_routing_output() -> None:
    pipeline = AgentPipeline(
        llm=StubLLM(['{"agent":"quest_generator","reason":"old contract"}'])
    )

    response = pipeline.run(
        {
            "type": "agent.request",
            "request_id": "request-json-routing-output",
            "agent": "quest_generator",
            "payload": QUEST_PAYLOAD,
        }
    )

    assert_agent_response(
        response,
        agent="quest_generator",
        sub_agent="quest_generator.delivery_quest",
    )
    assert response["payload"]["quests"][0]["domain"] == "delivery"


def test_pipeline_accepts_json_sub_agent_routing_output() -> None:
    pipeline = AgentPipeline(
        llm=StubLLM(
            [
                top_agent_decision("quest_generator"),
                '{"sub_agent":"quest_generator.production_quest","reason":"old contract"}',
                PRODUCTION_QUEST_RESPONSE,
            ]
        )
    )

    response = pipeline.run(
        {
            "type": "agent.request",
            "request_id": "request-json-sub-agent-routing-output",
            "payload": {"message": "create a production objective"},
        }
    )

    assert_agent_response(
        response,
        agent="quest_generator",
        sub_agent="quest_generator.production_quest",
    )
    assert len(response["payload"]["quests"]) == 1


def test_pipeline_rejects_invalid_explicit_quest_sub_agent() -> None:
    pipeline = AgentPipeline(llm=StubLLM([top_agent_decision("quest_generator")]))

    response = pipeline.run(
        {
            "type": "agent.request",
            "request_id": "request-invalid-quest-sub-agent",
            "agent": "quest_generator",
            "payload": {"sub_agent": "quest_generator.unknown"},
        }
    )

    assert_agent_error(response, code="INVALID_SUB_AGENT")


def test_pipeline_returns_error_for_invalid_envelope() -> None:
    pipeline = AgentPipeline(llm=StubLLM([]))

    response = pipeline.run(
        {
            "type": "wrong.type",
            "request_id": "request-invalid-envelope",
            "payload": {},
        }
    )

    assert_agent_error(response, code="INVALID_ENVELOPE")


def test_cache_key_separates_context() -> None:
    llm = StubLLM(
        [
            top_agent_decision("quest_generator"),
            DELIVERY_QUEST_RESPONSE.replace("Move plates", "Site A"),
            top_agent_decision("quest_generator"),
            DELIVERY_QUEST_RESPONSE.replace("Move plates", "Site B"),
        ]
    )
    pipeline = AgentPipeline(llm=llm)

    first = pipeline.run(
        {
            "type": "agent.request",
            "request_id": "request-cache-a",
            "agent": "quest_generator",
            "payload": QUEST_PAYLOAD,
            "context": {"site": "a"},
        }
    )
    second = pipeline.run(
        {
            "type": "agent.request",
            "request_id": "request-cache-b",
            "agent": "quest_generator",
            "payload": QUEST_PAYLOAD,
            "context": {"site": "b"},
        }
    )

    assert first["payload"]["quests"][0]["title"] == "Site A"
    assert second["payload"]["quests"][0]["title"] == "Site B"
    assert_agent_response(
        first,
        agent="quest_generator",
        sub_agent="quest_generator.delivery_quest",
    )
    assert_agent_response(
        second,
        agent="quest_generator",
        sub_agent="quest_generator.delivery_quest",
    )

def test_pipeline_falls_back_when_quest_llm_returns_wrong_count() -> None:
    one_quest_response = json.dumps(
        {
            "quests": [
                {
                    "id": 1,
                    "type": "daily",
                    "domain": "delivery",
                    "title": "Only one",
                    "description": "Only one quest from the model.",
                    "objectives": [
                        {"target_item_id": "resource_iron_plate", "quantity": 2}
                    ],
                    "clear_condition": {
                        "mode": "objective_count",
                        "target_item_id": "resource_iron_plate",
                        "required_quantity": 2,
                    },
                    "rewards": [
                        {
                            "reward_type": "credits",
                            "amount": 35,
                            "source_rule_id": "reward_daily_t2",
                            "description": "중반 진입 일일 퀘스트는 생산 라인 보강에 도움이 되는 보상으로 안내한다.",
                        }
                    ],
                }
            ]
        },
        ensure_ascii=False,
    )
    pipeline = AgentPipeline(
        llm=StubLLM([top_agent_decision("quest_generator"), one_quest_response])
    )

    response = pipeline.run(
        {
            "type": "agent.request",
            "request_id": "request-wrong-count",
            "agent": "quest_generator",
            "payload": {
                "sub_agent": "quest_generator.delivery_quest",
                "quest_generation_options": {"count": 5},
                "item": "resource_iron_plate",
                "quantity": 2,
                "destination": "central_storage",
            },
        }
    )

    assert_agent_response(
        response,
        agent="quest_generator",
        sub_agent="quest_generator.delivery_quest",
    )
    assert len(response["payload"]["quests"]) == 5
    assert response["payload"]["metadata"]["fallback"] is True
    assert response["payload"]["metadata"]["fallbackReason"] == "invalid_llm_response"


def test_pipeline_falls_back_when_resource_reward_has_no_resource_id() -> None:
    bad_reward_response = json.dumps(
        {
            "quests": [
                {
                    "id": 1,
                    "type": "daily",
                    "domain": "production",
                    "title": "Bad resource reward",
                    "description": "The resource reward has no item identity.",
                    "objectives": [
                        {"target_item_id": "resource_iron_plate", "quantity": 2}
                    ],
                    "clear_condition": {
                        "mode": "objective_count",
                        "target_item_id": "resource_iron_plate",
                        "required_quantity": 2,
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
        },
        ensure_ascii=False,
    )
    pipeline = AgentPipeline(
        llm=StubLLM([top_agent_decision("quest_generator"), bad_reward_response])
    )

    response = pipeline.run(
        {
            "type": "agent.request",
            "request_id": "request-bad-resource-reward",
            "agent": "quest_generator",
            "payload": {
                "sub_agent": "quest_generator.production_quest",
                "quest_generation_options": {
                    "count": 1,
                    "reward_options": {
                        "reward_types": ["resource"],
                        "resource_ids": ["resource_copper_ingot"],
                    },
                },
                "resources": {"resource_iron_plate": 12},
            },
        }
    )

    quest = response["payload"]["quests"][0]
    assert_agent_response(
        response,
        agent="quest_generator",
        sub_agent="quest_generator.production_quest",
    )
    assert response["payload"]["metadata"]["fallback"] is True
    assert quest["rewards"][0]["reward_type"] == "resource"
    assert quest["rewards"][0]["resource_id"] == "resource_copper_ingot"

def test_pipeline_falls_back_when_top_level_quest_llm_returns_one_quest() -> None:
    one_quest_response = json.dumps(
        {
            "quests": [
                {
                    "id": 1,
                    "type": "daily",
                    "domain": "production",
                    "title": "Only one top-level quest",
                    "description": "Only one quest from the model.",
                    "objectives": [
                        {"target_item_id": "resource_iron_plate", "quantity": 2}
                    ],
                    "clear_condition": {
                        "mode": "objective_count",
                        "target_item_id": "resource_iron_plate",
                        "required_quantity": 2,
                    },
                    "rewards": [
                        {
                            "reward_type": "credits",
                            "amount": 35,
                            "source_rule_id": "reward_daily_t2",
                            "description": "중반 진입 일일 퀘스트는 생산 라인 보강에 도움이 되는 보상으로 안내한다.",
                        }
                    ],
                }
            ]
        },
        ensure_ascii=False,
    )
    pipeline = AgentPipeline(
        llm=StubLLM([top_agent_decision("quest_generator"), one_quest_response])
    )

    response = pipeline.run(
        {
            "type": "agent.request",
            "request_id": "request-top-level-one-quest",
            "agent": "quest_generator",
            "payload": {
                "quest_generation_options": {"count": 5},
                "game_state": {
                    "inventory": {
                        "resource_iron_plate": 12,
                    }
                },
            },
        }
    )

    assert_agent_response(
        response,
        agent="quest_generator",
        sub_agent="quest_generator",
    )
    assert len(response["payload"]["quests"]) == 5
    assert response["payload"]["metadata"]["fallback"] is True
    assert response["payload"]["metadata"]["fallbackReason"] == "invalid_llm_response"

def test_pipeline_falls_back_when_xp_credit_rewards_do_not_match_csv_rule() -> None:
    bad_reward_response = json.dumps(
        {
            "quests": [
                {
                    "id": 1,
                    "type": "daily",
                    "domain": "production",
                    "title": "Bad XP reward",
                    "description": "The model changed CSV reward amounts.",
                    "objectives": [
                        {"target_item_id": "resource_iron_plate", "quantity": 2}
                    ],
                    "clear_condition": {
                        "mode": "objective_count",
                        "target_item_id": "resource_iron_plate",
                        "required_quantity": 2,
                    },
                    "rewards": [
                        {
                            "reward_type": "xp",
                            "amount": 999,
                            "source_rule_id": "reward_daily_t2",
                            "description": "잘못된 XP 보상",
                        },
                        {
                            "reward_type": "credits",
                            "amount": 35,
                            "source_rule_id": "reward_daily_t2",
                            "description": "중반 진입 일일 퀘스트는 생산 라인 보강에 도움이 되는 보상으로 안내한다.",
                        },
                    ],
                }
            ]
        },
        ensure_ascii=False,
    )
    pipeline = AgentPipeline(
        llm=StubLLM([top_agent_decision("quest_generator"), bad_reward_response])
    )

    response = pipeline.run(
        {
            "type": "agent.request",
            "request_id": "request-bad-xp-credit-reward",
            "agent": "quest_generator",
            "payload": {
                "sub_agent": "quest_generator.production_quest",
                "quest_generation_options": {
                    "count": 1,
                    "reward_options": {"reward_types": ["xp", "credits"]},
                },
                "progression": {"player_level": 6},
                "resources": {"resource_iron_plate": 12},
            },
        }
    )

    quest = response["payload"]["quests"][0]
    assert_agent_response(
        response,
        agent="quest_generator",
        sub_agent="quest_generator.production_quest",
    )
    assert response["payload"]["metadata"]["fallback"] is True
    assert response["payload"]["metadata"]["fallbackReason"] == "invalid_llm_response"
    assert quest["rewards"] == [
        {
            "reward_type": "xp",
            "amount": 120,
            "resource_id": None,
            "resource_name": None,
            "source_rule_id": "reward_daily_t2",
            "description": "중반 진입 일일 퀘스트는 생산 라인 보강에 도움이 되는 보상으로 안내한다.",
        },
        {
            "reward_type": "credits",
            "amount": 35,
            "resource_id": None,
            "resource_name": None,
            "source_rule_id": "reward_daily_t2",
            "description": "중반 진입 일일 퀘스트는 생산 라인 보강에 도움이 되는 보상으로 안내한다.",
        },
    ]
