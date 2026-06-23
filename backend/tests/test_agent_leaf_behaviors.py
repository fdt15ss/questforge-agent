from __future__ import annotations

from typing import Protocol

import pytest

from agents.base import AgentContext, AgentRunResult
from agents.quest_generator.delivery_quest import DeliveryQuestAgent
from agents.quest_generator.production_quest import ProductionQuestAgent
from agents.quest_generator.schemas import QuestResponse


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
        response = QuestResponse.model_validate(result.payload)
        assert len(response.quests) == 5
        assert response.quests[0].type == "daily"
        assert response.quests[0].domain == "delivery"
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
    assert "quest_text_updates" in prompt
    assert "quest_plan" not in prompt
    response = QuestResponse.model_validate(result.payload)
    assert len(response.quests) == 5
    assert response.quests[0].domain == "delivery"
    assert response.quests[0].title
    assert response.quests[0].objectives[0].target_item_id == "copper plate"
    assert result.metadata == {
        "fallback": True,
        "sub_agent": "quest_generator.delivery_quest",
        "graph": "delivery_quest",
    }


def test_delivery_quest_fallback_uses_nested_count_override(
    context: AgentContext,
) -> None:
    agent = DeliveryQuestAgent()

    result = agent.fallback(
        {
            "quest_generation_options": {
                "count": 2,
            },
            "item": "iron plate",
            "quantity": 4,
            "destination": "power grid depot",
        },
        context,
    )

    response = QuestResponse.model_validate(result.payload)
    assert len(response.quests) == 2
    assert all(quest.domain == "delivery" for quest in response.quests)


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


def test_production_quest_prompt_asks_llm_to_rewrite_descriptions(
    context: AgentContext,
) -> None:
    agent = ProductionQuestAgent()

    prompt = agent.build_prompt(
        {
            "resources": {
                "resource_iron_ore": 12,
                "resource_copper_ore": 5,
            },
            "recent_events": ["first_factory_started"],
        },
        context,
    )

    assert "rewrite title and description" in prompt
    assert "Do not copy DRAFT_QUESTS descriptions verbatim" in prompt
    assert "QuestTextUpdate schema" in prompt
    assert "Each update must reference a draft quest id" in prompt
    assert "The server will preserve every other field from DRAFT_QUESTS" in prompt
    assert "quest_text_updates" in prompt
    assert "quest_plan" not in prompt
    assert "rewards" in prompt
    assert "Do not return objectives, clear_condition, rewards, or full quests" in prompt

def test_delivery_quest_fallback_honors_reward_options(
    context: AgentContext,
) -> None:
    agent = DeliveryQuestAgent()

    result = agent.fallback(
        {
            "quest_generation_options": {
                "count": 1,
                "reward_options": {
                    "reward_types": ["credits"],
                },
            },
            "progression": {
                "player_level": 11,
            },
            "item": "resource_circuit_board",
            "quantity": 2,
            "destination": "central_storage",
        },
        context,
    )

    quest = QuestResponse.model_validate(result.payload).quests[0]
    assert quest.domain == "delivery"
    assert len(quest.rewards) == 1
    assert quest.rewards[0].reward_type == "credits"
    assert quest.rewards[0].source_rule_id == "reward_daily_t3"
