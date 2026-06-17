"""FastAPI connection manifest for Unreal agent clients."""

from __future__ import annotations

from fastapi import APIRouter

from agents.orchestrator import TOP_LEVEL_AGENT_IDS
from agents.quest_generator.agent import QUEST_SUB_AGENT_IDS

router = APIRouter(prefix="/api/v1/agent-connection", tags=["agent-connection"])


@router.get("")
async def get_agent_connection_manifest() -> dict[str, object]:
    """Return the stable backend connection contract for Unreal clients."""

    return {
        "status": "ok",
        "health_path": "/health",
        "websocket_path": "/ws/agent",
        "request_type": "agent.request",
        "response_types": ["agent.response", "agent.error"],
        "top_level_agents": list(TOP_LEVEL_AGENT_IDS),
        "leaf_agents": {
            "quest_generator": list(QUEST_SUB_AGENT_IDS),
        },
        "sample_request": {
            "type": "agent.request",
            "request_id": "quest-smoke-1",
            "session_id": "dev-session",
            "client_id": "portfolio-client",
            "agent": "quest_generator",
            "payload": {
                "sub_agent": "quest_generator.production_quest",
                "progression": {"stage": "early"},
                "resources": {"iron_ore": 12, "copper_ore": 5},
                "recent_events": ["first_factory_started"],
            },
        },
    }
