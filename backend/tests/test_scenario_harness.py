from __future__ import annotations

import pytest

from agents.pipeline import AgentPipeline
from tests.harness import StubLLM, top_agent_decision


@pytest.mark.parametrize(
    ("agent", "sub_agent", "expected_type"),
    [
        ("quest_generator", "quest_generator.production_quest", "production"),
        ("quest_generator", "quest_generator.delivery_quest", "delivery"),
        ("quest_generator", "quest_generator.exploration_quest", "exploration"),
    ],
)
def test_explicit_sub_agent_scenarios(
    agent: str,
    sub_agent: str,
    expected_type: str,
) -> None:
    pipeline = AgentPipeline(llm=StubLLM([top_agent_decision(agent), None]))

    response = pipeline.run(
        {
            "type": "agent.request",
            "request_id": f"request-{expected_type}",
            "agent": agent,
            "payload": {
                "sub_agent": sub_agent,
                "progression": {"stage": "early"},
                "resources": {"iron_ore": 12},
                "recent_events": ["first_factory_started"],
            },
        }
    )

    assert response["type"] == "agent.response"
    assert response["agent"] == agent
    assert response["payload"]["metadata"]["selectedLeafAgent"] == sub_agent
    assert "selectedSubAgent" not in response["payload"]["metadata"]


@pytest.mark.parametrize(
    "sub_agent",
    [
        "quest_generator.tutorial_quest",
        "quest_generator.economy_quest",
    ],
)
def test_removed_quest_sub_agents_are_rejected(sub_agent: str) -> None:
    pipeline = AgentPipeline(llm=StubLLM([top_agent_decision("quest_generator")]))

    response = pipeline.run(
        {
            "type": "agent.request",
            "request_id": "request-removed-quest-agent",
            "agent": "quest_generator",
            "payload": {
                "sub_agent": sub_agent,
                "question": "What should I do?",
            },
        }
    )

    assert response["type"] == "agent.error"
    assert response["agent"] == "quest_generator"
    assert response["error"]["code"] == "INVALID_SUB_AGENT"
    assert response["error"]["details"] == {"sub_agent": sub_agent}
