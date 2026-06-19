from __future__ import annotations

from typing import Protocol

import pytest

from agents.base import AgentContext, AgentRunResult
from agents.quest_generator.delivery_quest import DeliveryQuestAgent
from agents.quest_generator.production_quest import ProductionQuestAgent


class LeafAgent(Protocol):
    agent_id: str

    def build_prompt(self, payload: dict[str, object], context: AgentContext) -> str:
        """Build a leaf-agent prompt."""

    def fallback(
        self,
        payload: dict[str, object],
        context: AgentContext,
    ) -> AgentRunResult:
        """Build a fallback result."""


@pytest.fixture
def context() -> AgentContext:
    return AgentContext(
        request_id="request-test",
        session_id="session-test",
        client_id="client-test",
        metadata={"screen": "factory"},
    )


@pytest.mark.parametrize(
    ("agent", "expected_type"),
    [
        (ProductionQuestAgent(), "daily"),
        (DeliveryQuestAgent(), "delivery"),
    ],
)
def test_quest_leaf_agents_return_normalized_fallbacks(
    agent: LeafAgent,
    expected_type: str,
    context: AgentContext,
) -> None:
    prompt = agent.build_prompt({"quest_type": expected_type}, context)
    result = agent.fallback({"quest_type": expected_type}, context)

    assert prompt
    assert context.request_id not in prompt
    assert result.agent == "quest_generator"
    if isinstance(agent, ProductionQuestAgent):
        assert len(result.payload["quests"]) == 5
        assert result.payload["quests"][0]["type"] == expected_type
        assert result.payload["quests"][0]["domain"] == "production"
        assert "clear_condition" in result.payload["quests"][0]
        assert result.metadata == {"fallback": True, "sub_agent": agent.agent_id}
    else:
        assert result.payload["quest"]["type"] == expected_type
        assert result.metadata == {
            "fallback": True,
            "sub_agent": agent.agent_id,
            "graph": "delivery_quest",
        }


def test_delivery_quest_agent_uses_langgraph_for_prompt_and_fallback(
    context: AgentContext,
) -> None:
    agent = DeliveryQuestAgent()
    payload = {
        "item": "copper plate",
        "quantity": 3,
        "destination": "central storage",
    }

    prompt = agent.build_prompt(payload, context)
    result = agent.fallback(payload, context)

    assert "StateGraph" in agent.describe_graph()
    assert "delivery.normalize_payload" in agent.describe_graph()
    assert "delivery.select_goal" in agent.describe_graph()
    assert "delivery.build_prompt" in agent.describe_graph()
    assert "delivery.build_fallback" in agent.describe_graph()
    assert "copper plate" in prompt
    assert "3" in prompt
    assert "central storage" in prompt
    assert result.payload["quest"]["type"] == "delivery"
    assert result.payload["quest"]["title"]
    assert result.payload["quest"]["objective"]
    assert result.metadata == {
        "fallback": True,
        "sub_agent": "quest_generator.delivery_quest",
        "graph": "delivery_quest",
    }


def test_production_quest_fallback_returns_five_generated_quests(
    context: AgentContext,
) -> None:
    agent = ProductionQuestAgent()

    result = agent.fallback({}, context)

    assert result.agent == "quest_generator"
    assert len(result.payload["quests"]) == 5
    assert all(isinstance(quest["id"], int) for quest in result.payload["quests"])
    assert set(result.payload["quests"][0]["objectives"][0]) == {
        "target_item_id",
        "quantity",
    }
    assert result.metadata == {"fallback": True, "sub_agent": agent.agent_id}


def test_production_quest_agent_uses_langgraph_for_generation(
    context: AgentContext,
) -> None:
    agent = ProductionQuestAgent()

    graph_description = agent.describe_graph()

    assert "StateGraph" in graph_description
    assert "production.normalize_payload" in graph_description
    assert "production.retrieve_context" in graph_description
    assert "production.build_quests" in graph_description
    assert "production.validate_response" in graph_description


def test_production_quest_agent_does_not_expose_selection_tool(
    context: AgentContext,
) -> None:
    agent = ProductionQuestAgent()

    prompt = agent.build_prompt({}, context)

    assert agent.tools == ()
    assert "quest_generator.select_production_quests" not in prompt
    assert "AVAILABLE_QUESTS" not in prompt


def test_production_quest_prompt_requests_direct_quest_response(
    context: AgentContext,
) -> None:
    agent = ProductionQuestAgent()

    prompt = agent.build_prompt(
        {
            "quest_generation_options": {
                "count": 6,
            },
            "resources": {
                "resource_iron_ore": 12,
            },
        },
        context,
    )

    assert '"quests"' in prompt
    assert "6" in prompt
    assert "tool_call" not in prompt
    assert "selected_quest_ids" not in prompt
