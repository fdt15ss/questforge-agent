from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agents.pipeline import AgentPipeline


class StubLLM:
    """Small LLM stub that only answers routing prompts."""

    def __init__(self, responses: list[str | None]) -> None:
        self.responses = responses
        self.prompts: list[str] = []
        self.prompt_messages: list[list[dict[str, str]]] = []

    def invoke(self, prompt: str) -> str | None:
        self.prompts.append(prompt)
        if not self.responses:
            return None
        return self.responses.pop(0)

    def invoke_messages(self, messages: list[dict[str, str]]) -> str | None:
        self.prompt_messages.append(messages)
        if not self.responses:
            return None
        return self.responses.pop(0)


def top_agent_decision(agent: str) -> str:
    """Build a top-level routing decision for tests."""

    return agent


def leaf_agent_decision(leaf_agent: str) -> str:
    """Build a leaf agent routing decision for tests."""

    return leaf_agent


@dataclass(frozen=True)
class PipelineScenario:
    """Reusable input for an agent pipeline scenario."""

    name: str
    agent: str | None
    payload: dict[str, Any]
    request_id: str = "request-harness"
    context: dict[str, Any] = field(default_factory=dict)
    llm_responses: list[str | None] = field(default_factory=list)


def run_pipeline_scenario(scenario: PipelineScenario) -> tuple[dict[str, Any], StubLLM]:
    """Run one scenario through the real LangGraph-backed pipeline."""

    llm = StubLLM(list(scenario.llm_responses))
    pipeline = AgentPipeline(llm=llm)
    response = pipeline.run(
        {
            "type": "agent.request",
            "request_id": scenario.request_id,
            "agent": scenario.agent,
            "payload": scenario.payload,
            "context": scenario.context,
        }
    )
    return response, llm


def assert_agent_response(
    response: dict[str, Any],
    *,
    agent: str,
    sub_agent: str | None = None,
) -> None:
    """Assert the common agent.response shape."""

    assert response["type"] == "agent.response"
    assert response["agent"] == agent
    assert isinstance(response["payload"], dict)
    assert isinstance(response["payload"]["metadata"], dict)
    assert response["payload"]["metadata"]["selectedAgent"] == agent
    assert response["payload"]["metadata"]["selectedLeafAgent"] == (sub_agent or agent)
    assert "selectedSubAgent" not in response["payload"]["metadata"]


def assert_agent_error(
    response: dict[str, Any],
    *,
    code: str,
) -> None:
    """Assert the common agent.error shape."""

    assert response["type"] == "agent.error"
    assert response["error"]["code"] == code
