"""LLM이 요청한 도구 호출을 LangGraph ToolNode가 이해하는 모양으로 바꾸는 파일입니다."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from typing import Annotated, Any

from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langgraph.prebuilt import InjectedState, ToolNode

from agents.base import AgentContext
from agents.pipeline.state import AgentGraphState
from agents.router import AgentRouter, UnknownAgentError

_TOOL_CALL_ID = "agent-tool-call-1"
_INVALID_TOOL_CALL_NAME = "_invalid_tool_call"
_TOOL_NOT_ALLOWED_NAME = "_tool_not_allowed"
_MAX_TOOL_NAME_CHARS = 128
_MAX_TOOL_RESULT_PROMPT_CHARS = 4000
_TOOL_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_.-]+$")
LOGGER = logging.getLogger(__name__)


def build_agent_tool_node(router: AgentRouter) -> ToolNode:
    """등록된 에이전트들의 도구 목록을 받아 LangGraph에서 실행할 ToolNode를 만듭니다."""

    return ToolNode(
        [
            *[
                _wrap_agent_tool(router, tool_name)
                for tool_name in _registered_tool_names(router)
            ],
            _invalid_tool_call(),
            _tool_not_allowed(),
        ],
        name="agent.tool_node",
    )


def is_tool_request(raw: str | None) -> bool:
    """LLM 원문 응답을 받아 tool_call JSON인지 True/False로 알려줍니다."""

    if not raw:
        return False
    parsed = _parse_json_object(raw)
    return parsed is not None and "tool_call" in parsed


def build_tool_node_input(
    router: AgentRouter,
) -> Callable[[AgentGraphState], AgentGraphState]:
    """도구 호출 JSON을 받아 ToolNode에 넘길 메시지와 도구 인자를 만드는 함수를 반환합니다."""

    def prepare(state: AgentGraphState) -> AgentGraphState:
        parsed = _parse_json_object(state.get("llmRaw"))
        if parsed is None:
            return {}

        invalid_reason = ""
        denied_reason = ""
        tool_call = parsed.get("tool_call")
        if set(parsed) != {"tool_call"}:
            invalid_reason = "Tool request must not include other top-level fields."
        elif not isinstance(tool_call, dict):
            invalid_reason = "tool_call must be an object."

        name = _INVALID_TOOL_CALL_NAME
        request_name = _INVALID_TOOL_CALL_NAME
        args: dict[str, Any] = {}
        if not invalid_reason and isinstance(tool_call, dict):
            requested_name = tool_call.get("name")
            requested_args = tool_call.get("args", {})
            if not isinstance(requested_name, str) or not requested_name:
                invalid_reason = "tool_call.name must be a non-empty string."
            elif not _is_valid_tool_name(requested_name):
                invalid_reason = "tool_call.name has an invalid format."
            elif not isinstance(requested_args, dict):
                invalid_reason = "tool_call.args must be an object."
                request_name = requested_name
            elif not _tool_allowed_for_selected_agent(router, state, requested_name):
                denied_reason = "Requested tool is not available to the selected agent."
                name = _TOOL_NOT_ALLOWED_NAME
                request_name = requested_name
                args = requested_args
            else:
                name = requested_name
                request_name = requested_name
                args = requested_args

        tool_node_args = {"tool_args": args}
        if invalid_reason:
            tool_node_args = {"tool_args": {"reason": invalid_reason}}
        if denied_reason:
            tool_node_args = {
                "tool_args": {
                    "requested_name": request_name,
                    "reason": denied_reason,
                }
            }

        return {
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": name,
                            "args": tool_node_args,
                            "id": _TOOL_CALL_ID,
                        }
                    ],
                )
            ],
            "toolCallRequest": {"name": request_name, "args": args},
        }

    return prepare


def build_tool_followup_prompt(state: AgentGraphState) -> AgentGraphState:
    """도구 실행 결과를 받아 LLM이 최종 답변을 만들 수 있는 후속 프롬프트를 만듭니다."""

    tool_messages = [
        message
        for message in state.get("messages", [])
        if isinstance(message, ToolMessage)
    ]
    if not tool_messages:
        return {}

    tool_message = tool_messages[-1]
    tool_name = state.get("toolCallRequest", {}).get("name", "") or tool_message.name
    return {
        "toolCalls": [
            *state.get("toolCalls", []),
            {
                "name": tool_name,
                "ok": not _is_tool_error(tool_message.content),
            },
        ],
        "toolFollowupPrompt": (
            f"{state['prompt']}\n\n"
            "[TOOL_RESULT]\n"
            f"name: {tool_name}\n"
            f"content: {_truncate_tool_content(tool_message.content)}\n\n"
            "[OUTPUT_CONTRACT]\n"
            "도구 결과를 반영해 최종 Agent response JSON object만 반환한다. "
            "tool_call은 다시 반환하지 않는다."
        ),
    }


def append_tool_metadata(state: AgentGraphState) -> dict[str, Any]:
    """완료된 도구 호출 목록을 응답 metadata에 넣을 dict 형태로 반환합니다."""

    tool_calls = state.get("toolCalls")
    if not tool_calls:
        return {}
    return {"toolCalls": tool_calls}


def _registered_tool_names(router: AgentRouter) -> list[str]:
    return sorted(
        {
            tool.name
            for agent_id in router.list_agent_ids()
            for tool in router.get(agent_id).tools
        }
    )


def _tool_allowed_for_selected_agent(
    router: AgentRouter,
    state: AgentGraphState,
    tool_name: str,
) -> bool:
    try:
        agent = router.get(state.get("selectedLeafAgent", ""))
    except UnknownAgentError:
        return False
    return any(tool.name == tool_name for tool in agent.tools)


def _wrap_agent_tool(router: AgentRouter, tool_name: str) -> StructuredTool:
    def invoke_agent_tool(
        state: Annotated[AgentGraphState, InjectedState],
        tool_args: dict[str, Any] | None = None,
    ) -> object:
        """현재 선택된 에이전트와 도구 인자를 받아 실제 에이전트 도구를 실행합니다."""

        agent = router.get(state.get("selectedLeafAgent", ""))
        agent_tool = next(
            (tool for tool in agent.tools if tool.name == tool_name),
            None,
        )
        if agent_tool is None:
            return {
                "status": "error",
                "code": "TOOL_NOT_ALLOWED",
                "message": "Requested tool is not available to the selected agent.",
            }

        try:
            return agent_tool.invoke(
                state.get("typedPayload", {}),
                state.get("context", AgentContext(request_id="unknown")),
                tool_args or {},
            )
        except Exception as exc:
            LOGGER.info(
                "Agent tool execution failed.",
                extra={
                    "tool_name": tool_name,
                    "selected_leaf_agent": state.get("selectedLeafAgent", ""),
                    "exception_type": type(exc).__name__,
                },
            )
            return {
                "status": "error",
                "code": "TOOL_EXECUTION_FAILED",
                "message": "Tool execution failed.",
            }

    return StructuredTool.from_function(
        func=invoke_agent_tool,
        name=tool_name,
        description=f"에이전트가 참고 자료나 DB 조회처럼 읽기 용도로 사용하는 도구입니다: {tool_name}",
    )


def _invalid_tool_call() -> StructuredTool:
    def invoke_invalid_tool_call(
        state: Annotated[AgentGraphState, InjectedState],
        tool_args: dict[str, Any] | None = None,
    ) -> object:
        """잘못된 도구 호출을 받아 모든 에이전트가 이해할 수 있는 오류 dict로 바꿉니다."""

        return {
            "status": "error",
            "code": "INVALID_TOOL_CALL",
            "message": (tool_args or {}).get("reason", "Invalid tool call."),
        }

    return StructuredTool.from_function(
        func=invoke_invalid_tool_call,
        name=_INVALID_TOOL_CALL_NAME,
        description="잘못된 tool_call 요청을 표준 오류 응답으로 바꿉니다.",
    )


def _tool_not_allowed() -> StructuredTool:
    def invoke_tool_not_allowed(
        state: Annotated[AgentGraphState, InjectedState],
        tool_args: dict[str, Any] | None = None,
    ) -> object:
        """허용되지 않은 도구 요청을 받아 표준 권한 오류 dict로 바꿉니다."""

        return {
            "status": "error",
            "code": "TOOL_NOT_ALLOWED",
            "message": (tool_args or {}).get(
                "reason",
                "Requested tool is not available to the selected agent.",
            ),
        }

    return StructuredTool.from_function(
        func=invoke_tool_not_allowed,
        name=_TOOL_NOT_ALLOWED_NAME,
        description="선택된 에이전트가 사용할 수 없는 도구 요청을 표준 오류 응답으로 바꿉니다.",
    )


def _parse_json_object(raw: str | None) -> dict[str, Any] | None:
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def _is_valid_tool_name(tool_name: str) -> bool:
    return (
        len(tool_name) <= _MAX_TOOL_NAME_CHARS
        and _TOOL_NAME_PATTERN.fullmatch(tool_name) is not None
    )


def _is_tool_error(content: str | list[Any]) -> bool:
    if not isinstance(content, str):
        return False
    parsed = _parse_json_object(content)
    return (
        (isinstance(parsed, dict) and parsed.get("status") == "error")
        or content.startswith("Error:")
    )


def _truncate_tool_content(content: str | list[Any]) -> str:
    rendered_content = (
        content
        if isinstance(content, str)
        else json.dumps(content, ensure_ascii=False, default=str)
    )
    if len(rendered_content) <= _MAX_TOOL_RESULT_PROMPT_CHARS:
        return rendered_content
    return f"{rendered_content[:_MAX_TOOL_RESULT_PROMPT_CHARS]}... [truncated]"
