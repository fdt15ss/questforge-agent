"""WebSocket gateway for agent requests."""

from __future__ import annotations

import json
import logging
from typing import cast

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from agents.pipeline import AgentPipeline
from protocol.errors import build_error_payload

router = APIRouter()
LOGGER = logging.getLogger("uvicorn.error")
SENSITIVE_LOG_KEYS = frozenset(
    {
        "api_key",
        "authorization",
        "password",
        "secret",
        "token",
    }
)


def get_agent_pipeline(websocket: WebSocket) -> AgentPipeline:
    """Return the application-scoped agent pipeline."""

    app = websocket.scope["app"]
    return cast(AgentPipeline, app.state.agent_pipeline)


def sanitize_for_log(value: object) -> object:
    """Return a log-safe copy of a JSON-compatible value."""

    if isinstance(value, dict):
        sanitized: dict[str, object] = {}
        for raw_key, raw_value in value.items():
            key = str(raw_key)
            if key.lower() in SENSITIVE_LOG_KEYS:
                sanitized[key] = "[redacted]"
            else:
                sanitized[key] = sanitize_for_log(raw_value)
        return sanitized
    if isinstance(value, list):
        return [sanitize_for_log(item) for item in value]
    return value


async def send_agent_json(websocket: WebSocket, message: dict[str, object]) -> None:
    """Log and send an agent WebSocket message."""

    LOGGER.info(
        "QuestForge agent WebSocket sending: %s",
        json.dumps(sanitize_for_log(message), ensure_ascii=False, sort_keys=True),
    )
    await websocket.send_json(message)


@router.websocket("/ws/agent")
async def agent_websocket(websocket: WebSocket) -> None:
    """Accept the agent WebSocket connection."""

    await websocket.accept()
    pipeline = get_agent_pipeline(websocket)
    try:
        while True:
            raw_message = await websocket.receive_text()
            try:
                message = json.loads(raw_message)
            except json.JSONDecodeError:
                await send_agent_json(
                    websocket,
                    {
                        "type": "agent.error",
                        "error": build_error_payload(
                            "INVALID_JSON",
                            "WebSocket message must be valid JSON.",
                        ),
                    }
                )
                continue

            await send_agent_json(websocket, pipeline.run(message))
    except WebSocketDisconnect:
        return
