from __future__ import annotations

import json

from agents.pipeline import AgentPipeline
from agents.quest_generator.service import QuestAgentService
from agents.quest_generator.tools import PRODUCTION_QUEST_SELECTION_TOOL_NAME
from tests.harness import (
    PipelineScenario,
    StubLLM,
    assert_agent_error,
    assert_agent_response,
    leaf_agent_decision,
    run_pipeline_scenario,
    top_agent_decision,
)

QUEST_SELECTED_IDS = [10, 9, 8, 7, 6]
QUEST_TOOL_CALL = json.dumps(
    {
        "tool_call": {
            "name": PRODUCTION_QUEST_SELECTION_TOOL_NAME,
            "args": {"selected_quest_ids": QUEST_SELECTED_IDS},
        }
    },
)
QUEST_TOOL_RESPONSE = json.dumps(
    QuestAgentService().generate_quest_json_from_ids(QUEST_SELECTED_IDS),
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
            name="prompt routed quest",
            agent=None,
            payload={"message": "create an objective"},
            request_id="request-1",
            llm_responses=[
                top_agent_decision("quest_generator"),
                leaf_agent_decision("quest_generator.production_quest"),
                QUEST_TOOL_CALL,
                QUEST_TOOL_RESPONSE,
            ],
        )
    )

    assert_agent_response(
        response,
        agent="quest_generator",
        sub_agent="quest_generator.production_quest",
    )
    assert len(response["payload"]["quests"]) == 5
    assert response["payload"]["quests"][0]["type"] == "production"
    assert response["payload"]["metadata"]["toolCalls"] == [
        {"name": PRODUCTION_QUEST_SELECTION_TOOL_NAME, "ok": True},
    ]
    assert "[OUTPUT_CONTRACT]" in llm.prompts[0]
    assert "[ALLOWED_LEAF_AGENT_IDS]" in llm.prompts[1]
    assert "[TOOL_RESULT]" in llm.prompts[-1]


def test_pipeline_routes_explicit_quest_leaf_without_leaf_llm_decision() -> None:
    pipeline = AgentPipeline(
        llm=StubLLM(
            [
                top_agent_decision("quest_generator"),
                '{"quest":{"type":"delivery","title":"Move plates","objective":"Deliver plates"}}',
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
    assert response["payload"]["quest"]["type"] == "delivery"


def test_pipeline_rejects_json_top_level_routing_output() -> None:
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

    assert_agent_error(response, code="ROUTING_UNAVAILABLE")
    assert response["agent"] == "quest_generator"


def test_pipeline_rejects_json_sub_agent_routing_output() -> None:
    pipeline = AgentPipeline(
        llm=StubLLM(
            [
                top_agent_decision("quest_generator"),
                '{"sub_agent":"quest_generator.production_quest","reason":"old contract"}',
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

    assert_agent_error(response, code="ROUTING_UNAVAILABLE")
    assert response["agent"] == "quest_generator"


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
            '{"quest":{"type":"delivery","title":"Site A","objective":"Deliver to A"}}',
            top_agent_decision("quest_generator"),
            '{"quest":{"type":"delivery","title":"Site B","objective":"Deliver to B"}}',
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

    assert first["payload"]["quest"]["title"] == "Site A"
    assert second["payload"]["quest"]["title"] == "Site B"
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
