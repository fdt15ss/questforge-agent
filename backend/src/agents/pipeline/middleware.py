"""에이전트 실행 중간중간 남길 기록을 만드는 미들웨어 도우미입니다."""

from __future__ import annotations

import logging
from typing import Any

from agents.pipeline.state import AgentGraphState

LOGGER = logging.getLogger("agents.pipeline.runtime")


def append_middleware_log(
    state: AgentGraphState,
    node: str,
    event: str,
    details: dict[str, Any],
) -> AgentGraphState:
    """현재 그래프 상태를 받아 어떤 단계에서 무슨 일이 있었는지 기록으로 남깁니다."""

    LOGGER.info(
        "%s %s",
        node,
        event,
        extra={"middleware_node": node, "middleware_event": event},
    )
    return {
        "middlewareLogs": [
            *state.get("middlewareLogs", []),
            {
                "node": node,
                "event": event,
                "details": details,
            },
        ]
    }


def build_current_model_metadata(state: AgentGraphState) -> dict[str, str] | None:
    """마지막으로 사용한 LLM 정보를 응답 metadata에 넣기 위해 정리합니다."""

    slot = state.get("llmSlot")
    provider = state.get("llmProvider")
    if not slot or not provider:
        return None

    metadata = {
        "slot": slot,
        "provider": provider,
    }
    model = state.get("llmModel")
    if model:
        metadata["model"] = model
    return metadata
