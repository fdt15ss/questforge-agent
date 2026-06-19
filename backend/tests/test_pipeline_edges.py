from __future__ import annotations

import json
import logging
from typing import Any

import pytest

from agents.base import AgentContext, AgentRunResult
from agents.pipeline import AgentPipeline, run_agent_pipeline
from agents.pipeline.graph_edges import TOP_LEVEL_AGENT_BRANCHES
from agents.router import AgentRouter
from llm.settings import LLMModelSlot, LLMSettings
from tests.harness import (
    StubLLM,
    assert_agent_error,
    assert_agent_response,
    leaf_agent_decision,
    top_agent_decision,
)


class ErroringStubLLM(StubLLM):
    def __init__(
        self,
        responses: list[str | None],
        errors: list[dict[str, str] | None],
    ) -> None:
        super().__init__(responses)
        self.errors = errors
        self._last_error: dict[str, str] | None = None

    def invoke_messages(self, messages: list[dict[str, str]]) -> str | None:
        response = super().invoke_messages(messages)
        self._last_error = self.errors.pop(0) if self.errors else None
        return response

    def invoke(self, prompt: str) -> str | None:
        response = super().invoke(prompt)
        self._last_error = self.errors.pop(0) if self.errors else None
        return response

    def last_error(self) -> dict[str, str] | None:
        return self._last_error


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
QUEST_AGENT = "quest_generator"
QUEST_LEAF_AGENT = "quest_generator.delivery_quest"
OTHER_QUEST_LEAF_AGENT = "quest_generator.production_quest"
QUEST_PAYLOAD = {
    "sub_agent": QUEST_LEAF_AGENT,
    "progression": {"stage": "early"},
    "resources": {"iron_ore": 12},
}


def test_top_level_agent_branches_are_quest_only() -> None:
    assert TOP_LEVEL_AGENT_BRANCHES == {
        "quest_generator": "quest_generator.route_sub_agent",
    }


class BrokenFallbackAgent:
    agent_id = QUEST_LEAF_AGENT
    tools = ()

    def build_prompt(self, payload: dict[str, object], context: AgentContext) -> str:
        return "broken fallback prompt"

    def fallback(
        self,
        payload: dict[str, object],
        context: AgentContext,
    ) -> AgentRunResult:
        return AgentRunResult(agent=self.agent_id, payload=[])  # type: ignore[arg-type]


class EchoContextTool:
    name = "factory_context.echo"

    def invoke(
        self,
        payload: dict[str, Any],
        context: AgentContext,
        args: dict[str, Any] | None = None,
    ) -> object:
        return {
            "request_id": context.request_id,
            "machine_count": len(payload.get("machines", [])),
        }


class MachineLookupTool:
    name = "factory_context.machine_lookup"

    def invoke(
        self,
        payload: dict[str, Any],
        context: AgentContext,
        args: dict[str, Any] | None = None,
    ) -> object:
        machine_id = (args or {}).get("machine_id")
        machines = [
            machine
            for machine in payload.get("machines", [])
            if machine.get("id") == machine_id
        ]
        return {"machine_id": machine_id, "matches": machines}


class OtherAgentSecretTool:
    name = "factory_context.secret"

    def invoke(
        self,
        payload: dict[str, Any],
        context: AgentContext,
        args: dict[str, Any] | None = None,
    ) -> object:
        return {"secret": "must-not-run"}


class LargeContextTool:
    name = "factory_context.large"

    def invoke(
        self,
        payload: dict[str, Any],
        context: AgentContext,
        args: dict[str, Any] | None = None,
    ) -> object:
        return {"large": "x" * 6000}


class LargeContentBlockTool:
    name = "factory_context.large_blocks"

    def invoke(
        self,
        payload: dict[str, Any],
        context: AgentContext,
        args: dict[str, Any] | None = None,
    ) -> object:
        return [{"type": "text", "text": "y" * 6000}]


class RaisingContextTool:
    name = "factory_context.raises"

    def invoke(
        self,
        payload: dict[str, Any],
        context: AgentContext,
        args: dict[str, Any] | None = None,
    ) -> object:
        raise RuntimeError("sensitive internal failure details")


class ToolBackedProcessAgent:
    agent_id = QUEST_LEAF_AGENT
    tools = (
        EchoContextTool(),
        MachineLookupTool(),
        LargeContextTool(),
        LargeContentBlockTool(),
        RaisingContextTool(),
    )

    def build_prompt(self, payload: dict[str, Any], context: AgentContext) -> str:
        return "tool backed process prompt"

    def fallback(
        self,
        payload: dict[str, Any],
        context: AgentContext,
    ) -> AgentRunResult:
        return AgentRunResult(
            agent=self.agent_id,
            payload={"summary": "deterministic fallback"},
            metadata={"fallback": True},
        )


class ToolBackedMaterialAgent:
    agent_id = OTHER_QUEST_LEAF_AGENT
    tools = (OtherAgentSecretTool(),)

    def build_prompt(self, payload: dict[str, Any], context: AgentContext) -> str:
        return "tool backed material prompt"

    def fallback(
        self,
        payload: dict[str, Any],
        context: AgentContext,
    ) -> AgentRunResult:
        return AgentRunResult(
            agent=self.agent_id,
            payload={"summary": "material fallback"},
            metadata={"fallback": True},
        )


def test_pipeline_default_settings_without_api_returns_routing_unavailable() -> None:
    pipeline = AgentPipeline(
        llm_settings=LLMSettings(
            default=LLMModelSlot(name="default", provider="none"),
            fallback1=LLMModelSlot(name="fallback1", provider="none"),
            fallback2=LLMModelSlot(name="fallback2", provider="none"),
        )
    )

    response = pipeline.run(
        {
            "type": "agent.request",
            "request_id": "request-settings-no-api",
            "agent": QUEST_AGENT,
            "payload": {**QUEST_PAYLOAD, "machines": []},
        }
    )

    assert_agent_error(response, code="ROUTING_UNAVAILABLE")


def test_pipeline_default_constructor_without_api_returns_routing_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QUESTFORGE_LLM_DEFAULT_PROVIDER", "none")
    monkeypatch.setenv("QUESTFORGE_LLM_FALLBACK1_PROVIDER", "none")
    monkeypatch.setenv("QUESTFORGE_LLM_FALLBACK2_PROVIDER", "none")
    pipeline = AgentPipeline()

    response = pipeline.run(
        {
            "type": "agent.request",
            "request_id": "request-default-no-api",
            "agent": QUEST_AGENT,
            "payload": {**QUEST_PAYLOAD, "machines": []},
        }
    )

    assert_agent_error(response, code="ROUTING_UNAVAILABLE")


def test_pipeline_uses_settings_slot_adapters_before_deterministic_fallback() -> None:
    settings = LLMSettings(
        default=LLMModelSlot(name="default", provider="none"),
        fallback1=LLMModelSlot(
            name="fallback1",
            provider="openai",
            model="gpt-5.5",
            api_key="key",
        ),
        fallback2=LLMModelSlot(name="fallback2", provider="none"),
    )
    created_slots: list[str] = []
    adapters = {
        "default": StubLLM([top_agent_decision(QUEST_AGENT), None]),
        "fallback1": StubLLM(['{"summary":"from fallback1"}']),
        "fallback2": StubLLM(['{"summary":"should not be used"}']),
    }

    def create_stub_adapter(slot: LLMModelSlot) -> StubLLM:
        created_slots.append(slot.name)
        return adapters[slot.name]

    pipeline = AgentPipeline(
        llm_settings=settings,
        llm_adapter_factory=create_stub_adapter,
    )

    response = pipeline.run(
        {
            "type": "agent.request",
            "request_id": "request-settings-fallback1",
            "agent": QUEST_AGENT,
            "payload": {**QUEST_PAYLOAD, "machines": []},
        }
    )

    assert created_slots == ["default", "fallback1", "fallback2"]
    assert_agent_response(response, agent=QUEST_AGENT, sub_agent=QUEST_LEAF_AGENT)
    assert response["payload"]["summary"] == "from fallback1"
    assert response["payload"]["metadata"]["llm"] == "used"
    assert response["payload"]["metadata"]["llmSlot"] == "fallback1"
    assert response["payload"]["metadata"]["llmProvider"] == "openai"
    assert response["payload"]["metadata"]["llmModel"] == "gpt-5.5"
    assert response["payload"]["metadata"]["currentModel"] == {
        "slot": "fallback1",
        "provider": "openai",
        "model": "gpt-5.5",
    }
    assert len(adapters["default"].prompts) == 2
    assert len(adapters["fallback1"].prompts) == 1
    assert len(adapters["fallback2"].prompts) == 0


def test_pipeline_uses_fallback2_when_default_and_fallback1_fail() -> None:
    settings = LLMSettings(
        default=LLMModelSlot(name="default", provider="none"),
        fallback1=LLMModelSlot(
            name="fallback1",
            provider="openai",
            model="gpt-5.5",
            api_key="key",
        ),
        fallback2=LLMModelSlot(
            name="fallback2",
            provider="local",
            model="llama3.1:8b",
            base_url="http://localhost:11434/v1",
        ),
    )
    adapters = {
        "default": StubLLM([top_agent_decision(QUEST_AGENT), None]),
        "fallback1": StubLLM([None]),
        "fallback2": StubLLM(['{"summary":"from fallback2"}']),
    }

    pipeline = AgentPipeline(
        llm_settings=settings,
        llm_adapter_factory=lambda slot: adapters[slot.name],
    )

    response = pipeline.run(
        {
            "type": "agent.request",
            "request_id": "request-settings-fallback2",
            "agent": QUEST_AGENT,
            "payload": {**QUEST_PAYLOAD, "machines": []},
        }
    )

    assert_agent_response(response, agent=QUEST_AGENT, sub_agent=QUEST_LEAF_AGENT)
    assert response["payload"]["summary"] == "from fallback2"
    assert response["payload"]["metadata"]["llmSlot"] == "fallback2"
    assert response["payload"]["metadata"]["llmProvider"] == "local"
    assert response["payload"]["metadata"]["llmModel"] == "llama3.1:8b"
    assert len(adapters["default"].prompts) == 2
    assert len(adapters["fallback1"].prompts) == 1
    assert len(adapters["fallback2"].prompts) == 1


def test_pipeline_clears_stale_model_metadata_when_next_slot_has_no_model() -> None:
    settings = LLMSettings(
        default=LLMModelSlot(name="default", provider="none"),
        fallback1=LLMModelSlot(
            name="fallback1",
            provider="openai",
            model="gpt-5.5",
            api_key="key",
        ),
        fallback2=LLMModelSlot(name="fallback2", provider="none"),
    )
    adapters = {
        "default": StubLLM([top_agent_decision(QUEST_AGENT), None]),
        "fallback1": StubLLM([None]),
        "fallback2": StubLLM(['{"summary":"from fallback2 without model"}']),
    }
    pipeline = AgentPipeline(
        llm_settings=settings,
        llm_adapter_factory=lambda slot: adapters[slot.name],
    )

    response = pipeline.run(
        {
            "type": "agent.request",
            "request_id": "request-clear-stale-model",
            "agent": QUEST_AGENT,
            "payload": {**QUEST_PAYLOAD, "machines": []},
        }
    )

    assert_agent_response(response, agent=QUEST_AGENT, sub_agent=QUEST_LEAF_AGENT)
    metadata = response["payload"]["metadata"]
    assert metadata["llmSlot"] == "fallback2"
    assert metadata["llmProvider"] == "none"
    assert "llmModel" not in metadata
    assert metadata["currentModel"] == {
        "slot": "fallback2",
        "provider": "none",
    }


def test_pipeline_uses_deterministic_fallback_after_all_slots_fail() -> None:
    settings = LLMSettings(
        default=LLMModelSlot(name="default", provider="none"),
        fallback1=LLMModelSlot(name="fallback1", provider="none"),
        fallback2=LLMModelSlot(name="fallback2", provider="none"),
    )
    adapters = {
        "default": StubLLM([top_agent_decision(QUEST_AGENT), None]),
        "fallback1": StubLLM([None]),
        "fallback2": StubLLM([None]),
    }

    pipeline = AgentPipeline(
        llm_settings=settings,
        llm_adapter_factory=lambda slot: adapters[slot.name],
    )

    response = pipeline.run(
        {
            "type": "agent.request",
            "request_id": "request-settings-all-fail",
            "agent": QUEST_AGENT,
            "payload": {**QUEST_PAYLOAD, "machines": []},
        }
    )

    assert_agent_response(response, agent=QUEST_AGENT, sub_agent=QUEST_LEAF_AGENT)
    assert response["payload"]["metadata"]["fallback"] is True
    assert len(adapters["default"].prompts) == 2
    assert len(adapters["fallback1"].prompts) == 1
    assert len(adapters["fallback2"].prompts) == 1


def test_pipeline_deterministic_fallback_clears_stale_model_metadata() -> None:
    settings = LLMSettings(
        default=LLMModelSlot(name="default", provider="none"),
        fallback1=LLMModelSlot(
            name="fallback1",
            provider="openai",
            model="gpt-5.5",
            api_key="key",
        ),
        fallback2=LLMModelSlot(name="fallback2", provider="none"),
    )
    adapters = {
        "default": StubLLM([top_agent_decision(QUEST_AGENT), None]),
        "fallback1": StubLLM([None]),
        "fallback2": StubLLM([None]),
    }
    pipeline = AgentPipeline(
        llm_settings=settings,
        llm_adapter_factory=lambda slot: adapters[slot.name],
    )

    response = pipeline.run(
        {
            "type": "agent.request",
            "request_id": "request-fallback-clear-stale-model",
            "agent": QUEST_AGENT,
            "payload": {**QUEST_PAYLOAD, "machines": []},
        }
    )

    assert_agent_response(response, agent=QUEST_AGENT, sub_agent=QUEST_LEAF_AGENT)
    metadata = response["payload"]["metadata"]
    assert metadata["fallback"] is True
    assert metadata["currentModel"] == {
        "slot": "fallback2",
        "provider": "none",
    }


def test_pipeline_attaches_log_and_fallback_middleware_as_langgraph_nodes() -> None:
    graph = AgentPipeline(llm=StubLLM([])).graph.get_graph()

    assert "agent.middleware.before" in graph.nodes
    assert "agent.middleware.fallback" in graph.nodes
    assert "agent.middleware.after" in graph.nodes


def test_pipeline_attaches_tool_node_for_agent_tools() -> None:
    graph = AgentPipeline(llm=StubLLM([])).graph.get_graph()

    assert "agent.tool_node" in graph.nodes


def test_pipeline_executes_generation_tool_request_with_tool_node() -> None:
    llm = StubLLM(
        [
            top_agent_decision(QUEST_AGENT),
            '{"tool_call":{"name":"factory_context.echo","args":{}}}',
            '{"summary":"tool result used"}',
        ]
    )
    router = AgentRouter()
    router.register(ToolBackedProcessAgent())
    pipeline = AgentPipeline(router=router, llm=llm)

    response = pipeline.run(
        {
            "type": "agent.request",
            "request_id": "request-tool-node",
            "agent": QUEST_AGENT,
            "payload": {**QUEST_PAYLOAD, "machines": [{"id": "miner-1"}]},
        }
    )

    assert_agent_response(response, agent=QUEST_AGENT, sub_agent=QUEST_LEAF_AGENT)
    metadata = response["payload"]["metadata"]
    assert response["payload"]["summary"] == "tool result used"
    assert metadata["toolCalls"] == [
        {"name": "factory_context.echo", "ok": True},
    ]
    assert len(llm.prompts) == 3
    assert "machine_count" in llm.prompts[-1]
    assert "request-tool-node" in llm.prompts[-1]


def test_pipeline_passes_tool_call_args_to_agent_tool() -> None:
    llm = StubLLM(
        [
            top_agent_decision(QUEST_AGENT),
            '{"tool_call":{"name":"factory_context.machine_lookup","args":{"machine_id":"miner-1"}}}',
            '{"summary":"tool args used"}',
        ]
    )
    router = AgentRouter()
    router.register(ToolBackedProcessAgent())
    pipeline = AgentPipeline(router=router, llm=llm)

    response = pipeline.run(
        {
            "type": "agent.request",
            "request_id": "request-tool-args",
            "agent": QUEST_AGENT,
            "payload": {
                **QUEST_PAYLOAD,
                "machines": [
                    {"id": "miner-1", "status": "blocked"},
                    {"id": "smelter-1", "status": "idle"},
                ]
            },
        }
    )

    assert_agent_response(response, agent=QUEST_AGENT, sub_agent=QUEST_LEAF_AGENT)
    assert response["payload"]["summary"] == "tool args used"
    assert '"machine_id": "miner-1"' in llm.prompts[-1]
    assert '"status": "blocked"' in llm.prompts[-1]
    assert '"status": "idle"' not in llm.prompts[-1]


def test_pipeline_blocks_tool_not_owned_by_selected_leaf_agent() -> None:
    llm = StubLLM(
        [
            top_agent_decision(QUEST_AGENT),
            '{"tool_call":{"name":"factory_context.secret","args":{}}}',
            '{"summary":"tool denied"}',
        ]
    )
    router = AgentRouter()
    router.register(ToolBackedProcessAgent())
    router.register(ToolBackedMaterialAgent())
    pipeline = AgentPipeline(router=router, llm=llm)

    response = pipeline.run(
        {
            "type": "agent.request",
            "request_id": "request-tool-denied",
            "agent": QUEST_AGENT,
            "payload": {**QUEST_PAYLOAD, "machines": []},
        }
    )

    assert_agent_response(response, agent=QUEST_AGENT, sub_agent=QUEST_LEAF_AGENT)
    assert response["payload"]["summary"] == "tool denied"
    assert response["payload"]["metadata"]["toolCalls"] == [
        {"name": "factory_context.secret", "ok": False},
    ]
    assert "TOOL_NOT_ALLOWED" in llm.prompts[-1]
    assert "must-not-run" not in llm.prompts[-1]


def test_pipeline_blocks_unknown_tool_without_exposing_global_tool_names() -> None:
    llm = StubLLM(
        [
            top_agent_decision(QUEST_AGENT),
            '{"tool_call":{"name":"factory_context.unknown","args":{}}}',
            '{"summary":"unknown tool denied"}',
        ]
    )
    router = AgentRouter()
    router.register(ToolBackedProcessAgent())
    router.register(ToolBackedMaterialAgent())
    pipeline = AgentPipeline(router=router, llm=llm)

    response = pipeline.run(
        {
            "type": "agent.request",
            "request_id": "request-unknown-tool-denied",
            "agent": QUEST_AGENT,
            "payload": {**QUEST_PAYLOAD, "machines": []},
        }
    )

    assert_agent_response(response, agent=QUEST_AGENT, sub_agent=QUEST_LEAF_AGENT)
    assert response["payload"]["summary"] == "unknown tool denied"
    assert response["payload"]["metadata"]["toolCalls"] == [
        {"name": "factory_context.unknown", "ok": False},
    ]
    assert "TOOL_NOT_ALLOWED" in llm.prompts[-1]
    assert "factory_context.secret" not in llm.prompts[-1]


def test_pipeline_treats_mixed_tool_call_output_as_invalid_tool_request() -> None:
    llm = StubLLM(
        [
            top_agent_decision(QUEST_AGENT),
            '{"tool_call":{"name":"factory_context.echo","args":{}},"summary":"mixed"}',
            '{"summary":"mixed recovered"}',
        ]
    )
    router = AgentRouter()
    router.register(ToolBackedProcessAgent())
    pipeline = AgentPipeline(router=router, llm=llm)

    response = pipeline.run(
        {
            "type": "agent.request",
            "request_id": "request-mixed-tool-call",
            "agent": QUEST_AGENT,
            "payload": {**QUEST_PAYLOAD, "machines": []},
        }
    )

    assert_agent_response(response, agent=QUEST_AGENT, sub_agent=QUEST_LEAF_AGENT)
    assert response["payload"]["summary"] == "mixed recovered"
    assert response["payload"]["metadata"]["toolCalls"] == [
        {"name": "_invalid_tool_call", "ok": False},
    ]
    assert "INVALID_TOOL_CALL" in llm.prompts[-1]


def test_pipeline_truncates_large_tool_result_in_followup_prompt() -> None:
    llm = StubLLM(
        [
            top_agent_decision(QUEST_AGENT),
            '{"tool_call":{"name":"factory_context.large","args":{}}}',
            '{"summary":"large tool result used"}',
        ]
    )
    router = AgentRouter()
    router.register(ToolBackedProcessAgent())
    pipeline = AgentPipeline(router=router, llm=llm)

    response = pipeline.run(
        {
            "type": "agent.request",
            "request_id": "request-large-tool-result",
            "agent": QUEST_AGENT,
            "payload": {**QUEST_PAYLOAD, "machines": []},
        }
    )

    assert_agent_response(response, agent=QUEST_AGENT, sub_agent=QUEST_LEAF_AGENT)
    assert response["payload"]["summary"] == "large tool result used"
    assert "[truncated]" in llm.prompts[-1]
    assert "x" * 5000 not in llm.prompts[-1]


def test_pipeline_truncates_content_block_tool_result_in_followup_prompt() -> None:
    llm = StubLLM(
        [
            top_agent_decision(QUEST_AGENT),
            '{"tool_call":{"name":"factory_context.large_blocks","args":{}}}',
            '{"summary":"large content block result used"}',
        ]
    )
    router = AgentRouter()
    router.register(ToolBackedProcessAgent())
    pipeline = AgentPipeline(router=router, llm=llm)

    response = pipeline.run(
        {
            "type": "agent.request",
            "request_id": "request-large-block-tool-result",
            "agent": QUEST_AGENT,
            "payload": {**QUEST_PAYLOAD, "machines": []},
        }
    )

    assert_agent_response(response, agent=QUEST_AGENT, sub_agent=QUEST_LEAF_AGENT)
    assert response["payload"]["summary"] == "large content block result used"
    assert "[truncated]" in llm.prompts[-1]
    assert "y" * 5000 not in llm.prompts[-1]


def test_pipeline_normalizes_tool_execution_exception(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="agents.pipeline.tool_node")
    llm = StubLLM(
        [
            top_agent_decision(QUEST_AGENT),
            '{"tool_call":{"name":"factory_context.raises","args":{}}}',
            '{"summary":"tool exception handled"}',
        ]
    )
    router = AgentRouter()
    router.register(ToolBackedProcessAgent())
    pipeline = AgentPipeline(router=router, llm=llm)

    response = pipeline.run(
        {
            "type": "agent.request",
            "request_id": "request-tool-exception",
            "agent": QUEST_AGENT,
            "payload": {**QUEST_PAYLOAD, "machines": []},
        }
    )

    assert_agent_response(response, agent=QUEST_AGENT, sub_agent=QUEST_LEAF_AGENT)
    assert response["payload"]["summary"] == "tool exception handled"
    assert response["payload"]["metadata"]["toolCalls"] == [
        {"name": "factory_context.raises", "ok": False},
    ]
    assert "TOOL_EXECUTION_FAILED" in llm.prompts[-1]
    assert "sensitive internal failure details" not in llm.prompts[-1]
    assert "Agent tool execution failed." in caplog.messages
    assert "sensitive internal failure details" not in caplog.text


def test_pipeline_rejects_oversized_tool_name_before_followup_prompt() -> None:
    oversized_tool_name = f"factory_context.{'x' * 300}"
    llm = StubLLM(
        [
            top_agent_decision(QUEST_AGENT),
            f'{{"tool_call":{{"name":"{oversized_tool_name}","args":{{}}}}}}',
            '{"summary":"oversized tool name rejected"}',
        ]
    )
    router = AgentRouter()
    router.register(ToolBackedProcessAgent())
    pipeline = AgentPipeline(router=router, llm=llm)

    response = pipeline.run(
        {
            "type": "agent.request",
            "request_id": "request-oversized-tool-name",
            "agent": QUEST_AGENT,
            "payload": {**QUEST_PAYLOAD, "machines": []},
        }
    )

    assert_agent_response(response, agent=QUEST_AGENT, sub_agent=QUEST_LEAF_AGENT)
    assert response["payload"]["summary"] == "oversized tool name rejected"
    assert response["payload"]["metadata"]["toolCalls"] == [
        {"name": "_invalid_tool_call", "ok": False},
    ]
    assert "INVALID_TOOL_CALL" in llm.prompts[-1]
    assert oversized_tool_name not in llm.prompts[-1]


def test_pipeline_preserves_tool_metadata_when_tool_followup_falls_back() -> None:
    llm = StubLLM(
        [
            top_agent_decision(QUEST_AGENT),
            '{"tool_call":{"name":"factory_context.echo","args":{}}}',
            None,
        ]
    )
    router = AgentRouter()
    router.register(ToolBackedProcessAgent())
    pipeline = AgentPipeline(router=router, llm=llm)

    response = pipeline.run(
        {
            "type": "agent.request",
            "request_id": "request-tool-followup-fallback",
            "agent": QUEST_AGENT,
            "payload": {**QUEST_PAYLOAD, "machines": []},
        }
    )

    assert_agent_response(response, agent=QUEST_AGENT, sub_agent=QUEST_LEAF_AGENT)
    assert response["payload"]["summary"] == "deterministic fallback"
    assert response["payload"]["metadata"]["fallback"] is True
    assert response["payload"]["metadata"]["toolCalls"] == [
        {"name": "factory_context.echo", "ok": True},
    ]


def test_pipeline_records_middleware_logs_and_current_model(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="agents.pipeline.runtime")
    settings = LLMSettings(
        default=LLMModelSlot(name="default", provider="none"),
        fallback1=LLMModelSlot(name="fallback1", provider="none"),
        fallback2=LLMModelSlot(name="fallback2", provider="none"),
    )
    adapters = {
        "default": StubLLM([top_agent_decision(QUEST_AGENT), None]),
        "fallback1": StubLLM([None]),
        "fallback2": StubLLM([None]),
    }
    pipeline = AgentPipeline(
        llm_settings=settings,
        llm_adapter_factory=lambda slot: adapters[slot.name],
    )

    response = pipeline.run(
        {
            "type": "agent.request",
            "request_id": "request-middleware-log",
            "agent": QUEST_AGENT,
            "payload": {**QUEST_PAYLOAD, "machines": []},
        }
    )

    assert_agent_response(response, agent=QUEST_AGENT, sub_agent=QUEST_LEAF_AGENT)
    metadata = response["payload"]["metadata"]
    assert metadata["currentModel"] == {
        "slot": "fallback2",
        "provider": "none",
    }
    assert [
        log["node"] for log in metadata["middlewareLogs"]
    ] == [
        "agent.middleware.before",
        "agent.middleware.fallback",
        "agent.middleware.after",
    ]
    assert [
        log["event"] for log in metadata["middlewareLogs"]
    ] == ["agent_started", "deterministic_fallback", "agent_finished"]
    assert "agent.middleware.before agent_started" in caplog.messages
    assert "agent.middleware.fallback deterministic_fallback" in caplog.messages
    assert "agent.middleware.after agent_finished" in caplog.messages


def test_pipeline_uses_valid_llm_json_response_without_fallback() -> None:
    pipeline = AgentPipeline(
        llm=StubLLM(
            [
                top_agent_decision(QUEST_AGENT),
                '{"summary":"from model"}',
            ]
        )
    )

    response = pipeline.run(
        {
            "type": "agent.request",
            "request_id": "request-llm-json",
            "agent": QUEST_AGENT,
            "payload": {**QUEST_PAYLOAD, "machines": []},
        }
    )

    assert_agent_response(response, agent=QUEST_AGENT, sub_agent=QUEST_LEAF_AGENT)
    assert response["payload"]["summary"] == "from model"
    assert response["payload"]["metadata"]["llm"] == "used"
    assert response["payload"]["metadata"]["currentModel"] == {
        "slot": "injected",
        "provider": "injected",
    }
    assert [
        log["node"] for log in response["payload"]["metadata"]["middlewareLogs"]
    ] == [
        "agent.middleware.before",
        "agent.middleware.after",
    ]


def test_pipeline_accepts_llm_json_object_inside_markdown_text() -> None:
    pipeline = AgentPipeline(
        llm=StubLLM(
            [
                top_agent_decision(QUEST_AGENT),
                '아래 JSON을 사용하세요.\n```json\n{"summary":"from fenced model"}\n```\n완료했습니다.',
            ]
        )
    )

    response = pipeline.run(
        {
            "type": "agent.request",
            "request_id": "request-llm-json-fenced-text",
            "agent": QUEST_AGENT,
            "payload": {**QUEST_PAYLOAD, "machines": []},
        }
    )

    assert_agent_response(response, agent=QUEST_AGENT, sub_agent=QUEST_LEAF_AGENT)
    assert response["payload"]["summary"] == "from fenced model"
    assert response["payload"]["metadata"]["llm"] == "used"


def test_pipeline_falls_back_for_non_json_llm_response() -> None:
    pipeline = AgentPipeline(
        llm=StubLLM([top_agent_decision(QUEST_AGENT), "not json"])
    )

    response = pipeline.run(
        {
            "type": "agent.request",
            "request_id": "request-invalid-llm",
            "agent": QUEST_AGENT,
            "payload": {**QUEST_PAYLOAD, "machines": []},
        }
    )

    assert_agent_response(response, agent=QUEST_AGENT, sub_agent=QUEST_LEAF_AGENT)
    assert response["payload"]["metadata"]["fallback"] is True
    assert response["payload"]["metadata"]["fallbackReason"] == "invalid_llm_response"


def test_pipeline_tries_fallback1_after_default_returns_invalid_json() -> None:
    settings = LLMSettings(
        default=LLMModelSlot(
            name="default",
            provider="google",
            model="gemini-2.5-flash",
            api_key="key",
        ),
        fallback1=LLMModelSlot(
            name="fallback1",
            provider="local",
            model="gemma4:e4b",
            base_url="http://127.0.0.1:11434/v1",
        ),
        fallback2=LLMModelSlot(name="fallback2", provider="none"),
    )
    adapters = {
        "default": StubLLM([top_agent_decision(QUEST_AGENT), "not json"]),
        "fallback1": StubLLM(['{"summary":"from local fallback"}']),
        "fallback2": StubLLM(['{"summary":"should not be used"}']),
    }

    pipeline = AgentPipeline(
        llm_settings=settings,
        llm_adapter_factory=lambda slot: adapters[slot.name],
    )

    response = pipeline.run(
        {
            "type": "agent.request",
            "request_id": "request-invalid-json-tries-local",
            "agent": QUEST_AGENT,
            "payload": {**QUEST_PAYLOAD, "machines": []},
        }
    )

    assert_agent_response(response, agent=QUEST_AGENT, sub_agent=QUEST_LEAF_AGENT)
    assert response["payload"]["summary"] == "from local fallback"
    assert response["payload"]["metadata"]["llmSlot"] == "fallback1"
    assert response["payload"]["metadata"]["llmProvider"] == "local"
    assert response["payload"]["metadata"]["llmModel"] == "gemma4:e4b"
    assert len(adapters["default"].prompts) == 2
    assert len(adapters["fallback1"].prompts) == 1
    assert len(adapters["fallback2"].prompts) == 0


def test_pipeline_tries_fallback2_after_default_and_fallback1_return_invalid_json() -> None:
    settings = LLMSettings(
        default=LLMModelSlot(
            name="default",
            provider="google",
            model="gemini-2.5-flash",
            api_key="key",
        ),
        fallback1=LLMModelSlot(
            name="fallback1",
            provider="local",
            model="gemma4:e4b",
            base_url="http://127.0.0.1:11434/v1",
        ),
        fallback2=LLMModelSlot(
            name="fallback2",
            provider="openai",
            model="gpt-4o-mini",
            api_key="key",
        ),
    )
    adapters = {
        "default": StubLLM([top_agent_decision(QUEST_AGENT), "not json"]),
        "fallback1": StubLLM(["still not json"]),
        "fallback2": StubLLM(['{"summary":"from fallback2"}']),
    }

    pipeline = AgentPipeline(
        llm_settings=settings,
        llm_adapter_factory=lambda slot: adapters[slot.name],
    )

    response = pipeline.run(
        {
            "type": "agent.request",
            "request_id": "request-invalid-json-tries-fallback2",
            "agent": QUEST_AGENT,
            "payload": {**QUEST_PAYLOAD, "machines": []},
        }
    )

    assert_agent_response(response, agent=QUEST_AGENT, sub_agent=QUEST_LEAF_AGENT)
    assert response["payload"]["summary"] == "from fallback2"
    assert response["payload"]["metadata"]["llmSlot"] == "fallback2"
    assert response["payload"]["metadata"]["llmProvider"] == "openai"
    assert len(adapters["default"].prompts) == 2
    assert len(adapters["fallback1"].prompts) == 1
    assert len(adapters["fallback2"].prompts) == 1


def test_pipeline_preserves_invalid_json_reason_when_later_slots_are_unavailable() -> None:
    settings = LLMSettings(
        default=LLMModelSlot(
            name="default",
            provider="google",
            model="gemini-2.5-flash",
            api_key="key",
        ),
        fallback1=LLMModelSlot(
            name="fallback1",
            provider="local",
            model="gemma4:e4b",
            base_url="http://127.0.0.1:11434/v1",
        ),
        fallback2=LLMModelSlot(name="fallback2", provider="none"),
    )
    adapters = {
        "default": StubLLM([top_agent_decision(QUEST_AGENT), "not json"]),
        "fallback1": StubLLM([None]),
        "fallback2": StubLLM([None]),
    }

    pipeline = AgentPipeline(
        llm_settings=settings,
        llm_adapter_factory=lambda slot: adapters[slot.name],
    )

    response = pipeline.run(
        {
            "type": "agent.request",
            "request_id": "request-invalid-json-preserves-reason",
            "agent": QUEST_AGENT,
            "payload": {**QUEST_PAYLOAD, "machines": []},
        }
    )

    assert_agent_response(response, agent=QUEST_AGENT, sub_agent=QUEST_LEAF_AGENT)
    assert response["payload"]["metadata"]["fallback"] is True
    assert response["payload"]["metadata"]["fallbackReason"] == "invalid_llm_response"
    assert response["payload"]["metadata"]["currentModel"] == {
        "slot": "fallback2",
        "provider": "none",
    }
    assert response["payload"]["metadata"]["llmAttempts"] == [
        {
            "slot": "default",
            "provider": "google",
            "model": "gemini-2.5-flash",
            "status": "invalid_json",
            "rawPreview": "not json",
        },
        {
            "slot": "fallback1",
            "provider": "local",
            "model": "gemma4:e4b",
            "status": "empty_response",
        },
        {
            "slot": "fallback2",
            "provider": "none",
            "status": "empty_response",
        },
    ]


def test_pipeline_includes_llm_attempt_error_details_for_empty_response() -> None:
    settings = LLMSettings(
        default=LLMModelSlot(
            name="default",
            provider="google",
            model="gemini-2.5-flash",
            api_key="key",
        ),
        fallback1=LLMModelSlot(
            name="fallback1",
            provider="local",
            model="gemma4:e4b",
            base_url="http://127.0.0.1:11434/v1",
        ),
        fallback2=LLMModelSlot(name="fallback2", provider="none"),
    )
    adapters = {
        "default": ErroringStubLLM(
            [top_agent_decision(QUEST_AGENT), None],
            [None, {"type": "TimeoutError", "message": "google timed out"}],
        ),
        "fallback1": ErroringStubLLM(
            [None],
            [{"type": "TimeoutError", "message": "local timed out"}],
        ),
        "fallback2": ErroringStubLLM([None], [None]),
    }

    pipeline = AgentPipeline(
        llm_settings=settings,
        llm_adapter_factory=lambda slot: adapters[slot.name],
    )

    response = pipeline.run(
        {
            "type": "agent.request",
            "request_id": "request-llm-attempt-error-details",
            "agent": QUEST_AGENT,
            "payload": {**QUEST_PAYLOAD, "machines": []},
        }
    )

    assert_agent_response(response, agent=QUEST_AGENT, sub_agent=QUEST_LEAF_AGENT)
    attempts = response["payload"]["metadata"]["llmAttempts"]
    assert attempts[0]["status"] == "empty_response"
    assert attempts[0]["errorType"] == "TimeoutError"
    assert attempts[0]["errorMessage"] == "google timed out"
    assert attempts[1]["status"] == "empty_response"
    assert attempts[1]["errorType"] == "TimeoutError"
    assert attempts[1]["errorMessage"] == "local timed out"


def test_pipeline_falls_back_for_non_object_llm_response() -> None:
    pipeline = AgentPipeline(
        llm=StubLLM([top_agent_decision(QUEST_AGENT), '["not", "object"]'])
    )

    response = pipeline.run(
        {
            "type": "agent.request",
            "request_id": "request-invalid-llm-list",
            "agent": QUEST_AGENT,
            "payload": {**QUEST_PAYLOAD, "machines": []},
        }
    )

    assert_agent_response(response, agent=QUEST_AGENT, sub_agent=QUEST_LEAF_AGENT)
    assert response["payload"]["metadata"]["fallback"] is True
    assert response["payload"]["metadata"]["fallbackReason"] == "invalid_llm_response"


def test_pipeline_returns_routing_unavailable_for_invalid_explicit_agent_without_model_decision() -> None:
    pipeline = AgentPipeline(llm=StubLLM([]))

    response = pipeline.run(
        {
            "type": "agent.request",
            "request_id": "request-unknown-agent",
            "agent": "unknown",
            "payload": QUEST_PAYLOAD,
        }
    )

    assert_agent_error(response, code="ROUTING_UNAVAILABLE")
    assert response["agent"] == "unknown"


def test_pipeline_rejects_removed_non_quest_top_level_decision() -> None:
    llm = StubLLM([top_agent_decision("legacy_agent")])
    pipeline = AgentPipeline(llm=llm)

    response = pipeline.run(
        {
            "type": "agent.request",
            "request_id": "request-edge-legacy-agent-decision",
            "agent": QUEST_AGENT,
            "payload": QUEST_PAYLOAD,
        }
    )

    assert_agent_error(response, code="ROUTING_UNAVAILABLE")
    assert response["agent"] == QUEST_AGENT
    assert len(llm.prompts) == 1


def test_pipeline_accepts_direct_production_quest_json_without_tool_call() -> None:
    llm = StubLLM(
        [
            top_agent_decision("quest_generator"),
            leaf_agent_decision("quest_generator.production_quest"),
            PRODUCTION_QUEST_RESPONSE,
        ]
    )
    pipeline = AgentPipeline(llm=llm)

    response = pipeline.run(
        {
            "type": "agent.request",
            "request_id": "request-edge-production-quest-decision",
            "payload": {"message": "Create the next production objective."},
        }
    )

    assert_agent_response(
        response,
        agent="quest_generator",
        sub_agent="quest_generator.production_quest",
    )
    assert len(response["payload"]["quests"]) == 1
    assert response["payload"]["quests"][0]["type"] == "daily"
    assert response["payload"]["quests"][0]["domain"] == "production"
    assert response["payload"]["quests"][0]["id"] == 1
    assert response["payload"]["metadata"]["llm"] == "used"
    assert "[ALLOWED_LEAF_AGENT_IDS]" in llm.prompts[1]
    assert "[TOOL_RESULT]" not in llm.prompts[-1]


def test_pipeline_rejects_json_top_level_routing_decision_in_edges() -> None:
    llm = StubLLM(['{"agent":"legacy_agent","reason":"old contract"}'])
    pipeline = AgentPipeline(llm=llm)

    response = pipeline.run(
        {
            "type": "agent.request",
            "request_id": "request-edge-json-top-level-routing",
            "agent": QUEST_AGENT,
            "payload": QUEST_PAYLOAD,
        }
    )

    assert_agent_error(response, code="ROUTING_UNAVAILABLE")
    assert response["agent"] == QUEST_AGENT
    assert len(llm.prompts) == 1


def test_pipeline_accepts_json_sub_agent_routing_decision_in_edges() -> None:
    llm = StubLLM(
        [
            top_agent_decision("quest_generator"),
            '{"sub_agent":"quest_generator.production_quest","reason":"old contract"}',
            PRODUCTION_QUEST_RESPONSE,
        ]
    )
    pipeline = AgentPipeline(llm=llm)

    response = pipeline.run(
        {
            "type": "agent.request",
            "request_id": "request-edge-json-leaf-routing",
            "payload": {"message": "Create the next production objective."},
        }
    )

    assert_agent_response(
        response,
        agent="quest_generator",
        sub_agent="quest_generator.production_quest",
    )
    assert len(response["payload"]["quests"]) == 1
    assert len(llm.prompts) == 3


def test_pipeline_rejects_invalid_fallback_payload_shape() -> None:
    router = AgentRouter()
    router.register(BrokenFallbackAgent())
    pipeline = AgentPipeline(
        router=router,
        llm=StubLLM([top_agent_decision(QUEST_AGENT), None]),
    )

    response = pipeline.run(
        {
            "type": "agent.request",
            "request_id": "request-invalid-fallback",
            "agent": QUEST_AGENT,
            "payload": QUEST_PAYLOAD,
        }
    )

    assert_agent_error(response, code="INVALID_AGENT_RESPONSE")


def test_pipeline_cache_hit_skips_second_llm_call() -> None:
    llm = StubLLM(
        [
            top_agent_decision(QUEST_AGENT),
            '{"summary":"first"}',
            top_agent_decision(QUEST_AGENT),
        ]
    )
    pipeline = AgentPipeline(llm=llm)
    message = {
        "type": "agent.request",
        "request_id": "request-cache-first",
        "agent": QUEST_AGENT,
        "payload": {**QUEST_PAYLOAD, "machines": [{"id": "m-1"}]},
        "context": {"site": "a"},
    }

    first = pipeline.run(message)
    second = pipeline.run({**message, "request_id": "request-cache-second"})

    assert first["payload"]["summary"] == "first"
    assert second["payload"]["summary"] == "first"
    assert second["payload"]["metadata"]["cache"] == "hit"
    assert "middlewareLogs" not in second["payload"]["metadata"]
    assert_agent_response(first, agent=QUEST_AGENT, sub_agent=QUEST_LEAF_AGENT)
    assert_agent_response(second, agent=QUEST_AGENT, sub_agent=QUEST_LEAF_AGENT)
    assert len(llm.prompts) == 3


def test_pipeline_cache_hit_preserves_original_response_metadata() -> None:
    llm = StubLLM(
        [
            top_agent_decision(QUEST_AGENT),
            '{"summary":"first"}',
            top_agent_decision(QUEST_AGENT),
        ]
    )
    pipeline = AgentPipeline(llm=llm)
    message = {
        "type": "agent.request",
        "request_id": "request-cache-metadata-first",
        "agent": QUEST_AGENT,
        "payload": {**QUEST_PAYLOAD, "machines": [{"id": "m-1"}]},
    }

    first = pipeline.run(message)
    second = pipeline.run({**message, "request_id": "request-cache-metadata-second"})

    assert first["payload"]["metadata"]["llm"] == "used"
    assert second["payload"]["metadata"]["llm"] == "used"
    assert second["payload"]["metadata"]["cache"] == "hit"
    assert "middlewareLogs" not in second["payload"]["metadata"]


def test_agent_pipeline_builds_compiled_graph() -> None:
    graph = AgentPipeline(llm=StubLLM([])).graph

    assert callable(graph.invoke)


def test_run_agent_pipeline_returns_validation_error_for_bad_envelope() -> None:
    response = run_agent_pipeline(
        {
            "type": "wrong.type",
            "request_id": "request-run-agent-invalid",
            "payload": QUEST_PAYLOAD,
        }
    )

    assert_agent_error(response, code="INVALID_ENVELOPE")


def test_pipeline_validation_error_preserves_raw_correlation_fields() -> None:
    response = run_agent_pipeline(
        {
            "type": "wrong.type",
            "request_id": "request-invalid-correlated",
            "session_id": "session-1",
            "client_id": "client-1",
            "agent": QUEST_AGENT,
            "payload": QUEST_PAYLOAD,
        }
    )

    assert_agent_error(response, code="INVALID_ENVELOPE")
    assert response["request_id"] == "request-invalid-correlated"
    assert response["session_id"] == "session-1"
    assert response["client_id"] == "client-1"
    assert response["agent"] == QUEST_AGENT
