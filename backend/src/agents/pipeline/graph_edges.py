"""LangGraph edge wiring and routing predicates."""

from __future__ import annotations

from typing import Literal

from langgraph.graph import END, START, StateGraph

from agents.orchestrator import TOP_LEVEL_AGENT_IDS
from agents.pipeline.state import AgentGraphState, TopRoute
from agents.pipeline.tool_node import is_tool_request
from agents.quest_generator.agent import QUEST_SUB_AGENT_IDS

TOP_LEVEL_AGENT_BRANCHES = {
    "quest_generator": "quest_generator.route_sub_agent",
}


def wire_agent_graph(graph: StateGraph) -> None:
    graph.add_edge(START, "build_context")
    graph.add_edge("build_context", "validate_envelope")
    graph.add_edge("validate_envelope", "route_top_agent")
    graph.add_conditional_edges(
        "route_top_agent",
        route_selected_agent,
        {
            **TOP_LEVEL_AGENT_BRANCHES,
            "error": "build_agent_error",
        },
    )
    for node in ("quest_generator.route_sub_agent",):
        graph.add_conditional_edges(
            node,
            route_selected_leaf_agent,
            {
                "valid": "cache_lookup",
                "error": "build_agent_error",
            },
        )
    graph.add_conditional_edges(
        "cache_lookup",
        route_cache_result,
        {
            "hit": "build_cached_response",
            "miss": "agent.middleware.before",
        },
    )
    graph.add_edge("build_cached_response", "build_agent_response")
    graph.add_edge("agent.middleware.before", "build_prompt")
    graph.add_edge("build_prompt", "call_llm.default")
    graph.add_conditional_edges(
        "call_llm.default",
        route_llm_result,
        {
            "valid": "parse_llm_response",
            "tool": "prepare_tool_call",
            "fallback": "call_llm.fallback1",
            "error": "build_agent_error",
        },
    )
    graph.add_conditional_edges(
        "call_llm.fallback1",
        route_llm_result,
        {
            "valid": "parse_llm_response",
            "tool": "prepare_tool_call",
            "fallback": "call_llm.fallback2",
            "error": "build_agent_error",
        },
    )
    graph.add_conditional_edges(
        "call_llm.fallback2",
        route_llm_result,
        {
            "valid": "parse_llm_response",
            "tool": "prepare_tool_call",
            "fallback": "agent.middleware.fallback",
            "error": "build_agent_error",
        },
    )
    graph.add_edge("prepare_tool_call", "agent.tool_node")
    graph.add_edge("agent.tool_node", "build_tool_followup_prompt")
    graph.add_edge("build_tool_followup_prompt", "call_llm.tool_followup")
    graph.add_conditional_edges(
        "call_llm.tool_followup",
        route_tool_followup_result,
        {
            "valid": "parse_llm_response",
            "fallback": "agent.middleware.fallback",
            "error": "build_agent_error",
        },
    )
    graph.add_conditional_edges(
        "parse_llm_response",
        route_parse_result,
        {
            "valid": "validate_response_schema",
            "fallback1": "call_llm.fallback1",
            "fallback2": "call_llm.fallback2",
            "fallback": "agent.middleware.fallback",
            "error": "build_agent_error",
        },
    )
    graph.add_edge("agent.middleware.fallback", "validate_response_schema")
    graph.add_conditional_edges(
        "validate_response_schema",
        route_response_validation,
        {
            "valid": "cache_write",
            "error": "build_agent_error",
        },
    )
    graph.add_edge("cache_write", "agent.middleware.after")
    graph.add_edge("agent.middleware.after", "build_agent_response")
    graph.add_edge("build_agent_response", END)
    graph.add_edge("build_agent_error", END)


def route_selected_agent(state: AgentGraphState) -> TopRoute:
    if state.get("error"):
        return "error"
    selected_agent = state.get("selectedAgent")
    if selected_agent in TOP_LEVEL_AGENT_IDS:
        return selected_agent  # type: ignore[return-value]
    return "error"


def route_cache_result(state: AgentGraphState) -> Literal["hit", "miss"]:
    return "hit" if state.get("cachedPayload") is not None else "miss"


def route_selected_leaf_agent(
    state: AgentGraphState,
) -> Literal["valid", "error"]:
    if state.get("error"):
        return "error"

    selected_agent = state.get("selectedAgent")
    selected_leaf_agent = state.get("selectedLeafAgent")
    allowed_leaf_agent_ids = {
        "quest_generator": ("quest_generator", *QUEST_SUB_AGENT_IDS),
    }.get(selected_agent, ())
    if selected_leaf_agent in allowed_leaf_agent_ids:
        return "valid"
    return "error"


def route_llm_result(
    state: AgentGraphState,
) -> Literal["valid", "tool", "fallback", "error"]:
    if state.get("error"):
        return "error"
    if is_tool_request(state.get("llmRaw")):
        return "tool"
    return "valid" if state.get("llmRaw") else "fallback"


def route_tool_followup_result(
    state: AgentGraphState,
) -> Literal["valid", "fallback", "error"]:
    if state.get("error"):
        return "error"
    if not state.get("llmRaw") or is_tool_request(state.get("llmRaw")):
        return "fallback"
    return "valid"


def route_parse_result(
    state: AgentGraphState,
) -> Literal["valid", "fallback1", "fallback2", "fallback", "error"]:
    if state.get("error"):
        return "error"
    if state.get("llmParseFailed"):
        if state.get("llmSlot") == "default":
            return "fallback1"
        if state.get("llmSlot") == "fallback1":
            return "fallback2"
        return "fallback"
    return "valid"


def route_response_validation(state: AgentGraphState) -> Literal["valid", "error"]:
    return "error" if state.get("error") else "valid"
