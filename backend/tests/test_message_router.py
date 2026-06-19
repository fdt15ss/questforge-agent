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
