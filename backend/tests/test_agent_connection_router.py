from __future__ import annotations

from fastapi.testclient import TestClient

from app import create_app


def test_agent_connection_manifest_exposes_unreal_connection_contract() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/api/v1/agent-connection")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["health_path"] == "/health"
    assert body["websocket_path"] == "/ws/agent"
    assert body["request_type"] == "agent.request"
    assert body["response_types"] == ["agent.response", "agent.error"]
    assert body["sample_request"] == {
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
    }


def test_agent_connection_manifest_lists_supported_agent_ids() -> None:
    with TestClient(create_app()) as client:
        body = client.get("/api/v1/agent-connection").json()

    assert body["top_level_agents"] == ["quest_generator"]
    assert body["leaf_agents"] == {
        "quest_generator": [
            "quest_generator.production_quest",
            "quest_generator.delivery_quest",
            "quest_generator.exploration_quest",
        ],
    }
