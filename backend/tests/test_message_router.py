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
    assert "quest_plan" in llm.prompts[1]
    assert "quest_intents" in llm.prompts[1]
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

def test_pipeline_merges_quest_text_updates_into_draft_response() -> None:
    text_update_response = json.dumps(
        {
            "quest_text_updates": [
                {
                    "id": 1,
                    "title": "개선된 철판 생산 목표",
                    "description": "철판 생산 흐름을 안정화하도록 자연스럽게 다듬은 설명입니다.",
                }
            ]
        },
        ensure_ascii=False,
    )
    pipeline = AgentPipeline(
        llm=StubLLM([top_agent_decision("quest_generator"), text_update_response])
    )

    response = pipeline.run(
        {
            "type": "agent.request",
            "request_id": "request-text-updates",
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
    first_quest = response["payload"]["quests"][0]
    assert first_quest["title"] == "개선된 철판 생산 목표"
    assert first_quest["description"] == "철판 생산 흐름을 안정화하도록 자연스럽게 다듬은 설명입니다."
    assert first_quest["objectives"]
    assert first_quest["clear_condition"]
    assert first_quest["rewards"]
    assert response["payload"]["metadata"]["llm"] == "used"
    assert "fallback" not in response["payload"]["metadata"]

def test_pipeline_merges_quest_plan_into_draft_response() -> None:
    quest_plan_response = json.dumps(
        {
            "quest_plan": {
                "analysis": "\ucca0\uad34 \ubd80\uc871\ubd84\uacfc \ub0a9\ud488 \ub8e8\ud2f4\uc744 \ud568\uaed8 \uc815\ub9ac\ud574\uc57c \ud55c\ub2e4.",
                "domain_mix": {"production": 1, "delivery": 1},
                "quest_intents": [
                    {
                        "id": 1,
                        "domain": "production",
                        "target_item_id": "resource_iron_ingot",
                        "intent": "main_quest_deficit",
                        "reason": "\uba54\uc778 \ud018\uc2a4\ud2b8\uc758 \ucca0\uad34 \ubd80\uc871\ubd84\uc744 \uba3c\uc800 \ud574\uacb0\ud55c\ub2e4.",
                        "title": "\ucca0\uad34 \uc0dd\uc0b0 \uc548\uc815\ud654",
                        "description": "\ucca0\uad34 \uc0dd\uc0b0\uc744 \uc548\uc815\ud654\ud574 \uae30\ucd08 \uc0dd\uc0b0 \ub77c\uc778 \ubcf5\uad6c\ub97c \uc55e\ub2f9\uae30\uc138\uc694.",
                        "main_quest_link_reason": "\ucca0\uad34 \ubd80\uc871\ubd84\uc744 \uc9c1\uc811 \ubcf4\ucda9\ud569\ub2c8\ub2e4.",
                    },
                    {
                        "id": 2,
                        "domain": "delivery",
                        "target_item_id": "\ucca0\uad34",
                        "intent": "delivery_routine",
                        "reason": "\ub0a9\ud488 \ub8e8\ud2f4\uc744 \ud568\uaed8 \uc720\uc9c0\ud55c\ub2e4.",
                    }
                ],
            }
        },
        ensure_ascii=False,
    )
    pipeline = AgentPipeline(
        llm=StubLLM([top_agent_decision("quest_generator"), quest_plan_response])
    )

    response = pipeline.run(
        {
            "type": "agent.request",
            "request_id": "quest-plan-merge",
            "session_id": "test-session",
            "client_id": "test-client",
            "agent": "quest_generator",
            "payload": {
                "quest_generation_options": {
                    "count": 2,
                    "domain_counts": {"production": 1, "delivery": 1},
                },
                "current_main_quest": {
                    "id": "main_basic",
                    "title": "\uae30\ucd08 \uc0dd\uc0b0 \ubcf5\uad6c",
                    "objectives": [
                        {
                            "target_item_id": "resource_iron_ingot",
                            "required_quantity": 20,
                            "current_quantity": 6,
                        }
                    ],
                },
                "game_state": {
                    "inventory": {
                        "resource_iron_ore": 18,
                        "resource_iron_ingot": 6,
                    }
                },
            },
        }
    )

    assert response["type"] == "agent.response"
    quests = response["payload"]["quests"]
    assert len(quests) == 2
    assert quests[0]["title"] == "\ucca0\uad34 \uc0dd\uc0b0 \uc548\uc815\ud654"
    assert quests[0]["metadata"]["llm_intent"] == "main_quest_deficit"
    assert quests[0]["metadata"]["llm_reason"] == "\uba54\uc778 \ud018\uc2a4\ud2b8\uc758 \ucca0\uad34 \ubd80\uc871\ubd84\uc744 \uba3c\uc800 \ud574\uacb0\ud55c\ub2e4."
    assert quests[0]["objectives"][0]["target_item_id"] == "resource_iron_ingot"
    assert "rewards" in quests[0]
    assert quests[1]["metadata"]["llm_intent"] == "delivery_routine"
    assert quests[1]["objectives"] == [{"target_item_id": "\ucca0\uad34", "quantity": 5}]
    assert quests[1]["clear_condition"] == {
        "mode": "objective_count",
        "target_item_id": "\ucca0\uad34",
        "required_quantity": 5,
        "label": None,
    }
    assert quests[1]["rewards"]
    assert response["payload"]["metadata"]["quest_plan_analysis"] == "\ucca0\uad34 \ubd80\uc871\ubd84\uacfc \ub0a9\ud488 \ub8e8\ud2f4\uc744 \ud568\uaed8 \uc815\ub9ac\ud574\uc57c \ud55c\ub2e4."


def test_pipeline_falls_back_when_quest_plan_domain_mismatches_draft() -> None:
    invalid_plan_response = json.dumps(
        {
            "quest_plan": {
                "analysis": "도메인을 잘못 제안한다.",
                "domain_mix": {"production": 1, "delivery": 0},
                "quest_intents": [
                    {
                        "id": 1,
                        "domain": "delivery",
                        "target_item_id": "resource_iron_ingot",
                        "intent": "bad_domain",
                        "reason": "draft와 다른 도메인이다.",
                    }
                ],
            }
        },
        ensure_ascii=False,
    )
    pipeline = AgentPipeline(
        llm=StubLLM([top_agent_decision("quest_generator"), invalid_plan_response])
    )

    response = pipeline.run(
        {
            "type": "agent.request",
            "request_id": "quest-plan-invalid-domain",
            "session_id": "test-session",
            "client_id": "test-client",
            "agent": "quest_generator",
            "payload": {
                "quest_generation_options": {
                    "count": 1,
                    "domain_counts": {"production": 1},
                },
                "game_state": {
                    "inventory": {
                        "resource_iron_ingot": 6,
                    }
                },
            },
        }
    )

    assert response["type"] == "agent.response"
    assert response["payload"]["metadata"]["fallback"] is True
    assert response["payload"]["metadata"]["fallbackReason"] == "invalid_llm_response"
    assert response["payload"]["quests"][0]["domain"] == "production"


def test_pipeline_falls_back_when_quest_plan_target_mismatches_draft() -> None:
    invalid_plan_response = json.dumps(
        {
            "quest_plan": {
                "analysis": "목표 아이템을 잘못 제안한다.",
                "domain_mix": {"production": 1, "delivery": 0},
                "quest_intents": [
                    {
                        "id": 1,
                        "domain": "production",
                        "target_item_id": "resource_titanium_ore",
                        "intent": "bad_target",
                        "reason": "draft 목표와 다른 target이다.",
                    }
                ],
            }
        },
        ensure_ascii=False,
    )
    pipeline = AgentPipeline(
        llm=StubLLM([top_agent_decision("quest_generator"), invalid_plan_response])
    )

    response = pipeline.run(
        {
            "type": "agent.request",
            "request_id": "quest-plan-invalid-target",
            "session_id": "test-session",
            "client_id": "test-client",
            "agent": "quest_generator",
            "payload": {
                "quest_generation_options": {
                    "count": 1,
                    "domain_counts": {"production": 1},
                },
                "game_state": {
                    "inventory": {
                        "resource_iron_ingot": 6,
                    }
                },
            },
        }
    )

    assert response["type"] == "agent.response"
    assert response["payload"]["metadata"]["fallback"] is True
    assert response["payload"]["metadata"]["fallbackReason"] == "invalid_llm_response"
    assert response["payload"]["quests"][0]["objectives"][0]["target_item_id"] == "resource_iron_ingot"


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

def test_pipeline_falls_back_when_top_level_quest_llm_returns_bare_quest() -> None:
    bare_quest_response = json.dumps(
        {
            "id": 1,
            "type": "daily",
            "domain": "production",
            "title": "Single quest",
            "description": "The LLM ignored the QuestResponse envelope.",
            "objectives": [
                {
                    "target_item_id": "resource_iron_plate",
                    "quantity": 20,
                }
            ],
            "clear_condition": {
                "mode": "objective_count",
                "target_item_id": "resource_iron_plate",
                "required_quantity": 20,
            },
            "rewards": [
                {
                    "reward_type": "xp",
                    "amount": 170,
                    "source_rule_id": "reward_daily_t3",
                    "description": "중급 일일 퀘스트는 병목 해소와 다음 제작 준비를 보상 문맥에 넣는다.",
                }
            ],
        },
        ensure_ascii=False,
    )
    pipeline = AgentPipeline(
        llm=StubLLM([top_agent_decision("quest_generator"), bare_quest_response])
    )

    response = pipeline.run(
        {
            "type": "agent.request",
            "request_id": "request-top-level-bare-quest",
            "agent": "quest_generator",
            "payload": {
                "quest_generation_options": {"count": 5},
                "progression": {"player_level": 12},
            },
        }
    )

    assert_agent_response(
        response,
        agent="quest_generator",
        sub_agent="quest_generator",
    )
    assert "quests" in response["payload"]
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
