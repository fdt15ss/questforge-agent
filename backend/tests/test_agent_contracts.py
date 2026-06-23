from __future__ import annotations

from typing import Any

from agents.agent_catalog import (
    AgentCatalogTool,
    RoutingToolResult,
    get_top_level_agent_capabilities,
)
from agents.base import AgentContext
from agents.orchestrator import TOP_LEVEL_AGENT_IDS, OrchestratorAgent
from agents.pipeline.graph_edges import TOP_LEVEL_AGENT_BRANCHES
from agents.quest_generator.agent import QuestGeneratorAgent
from agents.router import create_default_agent_router


class FakeRoutingSupportTool:
    name = "fake.routing_tool"

    def invoke(
        self,
        payload: dict[str, Any],
        context: AgentContext,
    ) -> RoutingToolResult:
        return RoutingToolResult(
            name=self.name,
            section="FAKE_ROUTING_SECTION",
            content=f"request={context.request_id}; keys={sorted(payload)}",
        )


def test_default_agent_router_contains_top_level_and_leaf_agents() -> None:
    router = create_default_agent_router()

    assert router.list_agent_ids() == [
        "quest_generator",
        "quest_generator.delivery_quest",
        "quest_generator.production_quest",
    ]


def test_agents_expose_tools_tuple() -> None:
    router = create_default_agent_router()
    agents = [
        *(router.get(agent_id) for agent_id in router.list_agent_ids()),
        OrchestratorAgent(),
        QuestGeneratorAgent(),
    ]

    for agent in agents:
        assert isinstance(agent.tools, tuple)


def test_top_level_agent_catalog_covers_orchestrator_choices() -> None:
    capabilities = get_top_level_agent_capabilities()

    assert tuple(capability.agent_id for capability in capabilities) == TOP_LEVEL_AGENT_IDS
    assert set(TOP_LEVEL_AGENT_IDS) == set(TOP_LEVEL_AGENT_BRANCHES)
    for capability in capabilities:
        assert capability.summary
        assert capability.when_to_use


def test_top_level_agent_catalog_is_quest_only() -> None:
    capabilities = get_top_level_agent_capabilities()

    assert TOP_LEVEL_AGENT_IDS == ("quest_generator",)
    assert [capability.agent_id for capability in capabilities] == ["quest_generator"]


def test_agent_catalog_tool_returns_routing_prompt_section() -> None:
    context = AgentContext(request_id="request-catalog-tool")

    result = AgentCatalogTool().invoke({}, context)

    assert result.name == "agent_catalog.get_capabilities"
    assert result.section == "AGENT_CAPABILITIES"
    for agent_id in TOP_LEVEL_AGENT_IDS:
        assert f"- {agent_id}:" in result.content


def test_orchestrator_routing_prompt_includes_agent_capabilities() -> None:
    orchestrator = OrchestratorAgent()
    context = AgentContext(
        request_id="request-orchestrator-contract",
        metadata={"screen": "factory-floor"},
    )

    prompt = orchestrator.build_routing_prompt(
        {"question": "create a delivery quest for a production bottleneck"},
        context,
        requested_agent="quest_generator",
    )

    assert "[AGENT_CAPABILITIES]" in prompt
    for agent_id in TOP_LEVEL_AGENT_IDS:
        assert f"- {agent_id}:" in prompt
    assert '{"agent":"quest_generator"}' in prompt
    assert "Return only one JSON object" in prompt


def test_orchestrator_calls_routing_support_tools() -> None:
    orchestrator = OrchestratorAgent(tools=(FakeRoutingSupportTool(),))
    context = AgentContext(request_id="request-fake-tool")

    prompt = orchestrator.build_routing_prompt({"question": "route me"}, context)

    assert "[FAKE_ROUTING_SECTION]" in prompt
    assert "request=request-fake-tool; keys=['question']" in prompt
    assert "[AGENT_CAPABILITIES]" not in prompt


def test_orchestrator_accepts_empty_tools_override() -> None:
    orchestrator = OrchestratorAgent(tools=())
    context = AgentContext(request_id="request-empty-tools")

    prompt = orchestrator.build_routing_prompt({"question": "route me"}, context)

    assert "[AGENT_CAPABILITIES]" not in prompt
    assert orchestrator.tools == ()


def test_sub_orchestrators_use_structured_prompt_id_contract() -> None:
    quest = QuestGeneratorAgent()
    context = AgentContext(
        request_id="request-contract",
        metadata={"screen": "factory-floor"},
    )

    quest_prompt = quest.build_routing_prompt(
        {"message": "create a production quest"},
        context,
    )

    assert "[ROLE]" in quest_prompt
    assert "[TASK]" in quest_prompt
    assert "[ALLOWED_LEAF_AGENT_IDS]" in quest_prompt
    assert "[REQUEST_CONTEXT]" in quest_prompt
    assert "[REQUEST_PAYLOAD]" in quest_prompt
    assert "[OUTPUT_CONTRACT]" in quest_prompt
    assert '{"sub_agent":"quest_generator.production_quest"}' in quest_prompt
    assert "Return only one JSON object" in quest_prompt
    assert "quest_generator.production_quest" in quest_prompt
    assert "quest_generator.delivery_quest" in quest_prompt
    assert "quest_generator.economy_quest" not in quest_prompt
    assert "quest_generator.tutorial_quest" not in quest_prompt
    assert "quest_generator.exploration_quest" not in quest_prompt


def test_quest_generator_prompt_requests_quest_plan_contract() -> None:
    agent = QuestGeneratorAgent()
    context = AgentContext(
        request_id="request-contract",
        session_id="session-contract",
        client_id="client-contract",
    )

    prompt = agent.build_prompt(
        {
            "quest_generation_options": {
                "count": 2,
                "domain_counts": {"production": 1, "delivery": 1},
            },
            "game_state": {
                "inventory": {
                    "resource_iron_ingot": 6,
                }
            },
        },
        context,
    )

    assert "quest_plan" in prompt
    assert "quest_intents" in prompt
    assert "domain_mix" in prompt
    assert '"domain_mix":{"production":1,"delivery":1}' in prompt
    assert '"domain_mix":{"production":3,"delivery":2}' not in prompt
    assert "Do not return quests, objectives, clear_condition, rewards" in prompt
    assert '"quest_text_updates"' not in prompt
