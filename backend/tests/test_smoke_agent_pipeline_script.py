from __future__ import annotations

import asyncio

import pytest

from scripts import smoke_agent_pipeline as smoke


def test_none_profile_contains_no_external_api_cases() -> None:
    profile = smoke.build_profile("none")

    assert profile.name == "none"
    assert [case.name for case in profile.cases] == [
        "health",
        "agent_connection_manifest",
        "invalid_json",
        "invalid_envelope",
        "routing_unavailable",
    ]
    assert profile.requires_external_opt_in is False


def test_local_profile_exercises_all_agent_paths() -> None:
    profile = smoke.build_profile("local")

    assert profile.name == "local"
    assert [case.expected_agent for case in profile.cases] == [
        "quest_generator",
    ]
    assert [case.expected_sub_agent for case in profile.cases] == [
        "quest_generator.production_quest",
    ]
    quest_case = profile.cases[0]
    assert quest_case.expected_quest_count == 5
    assert isinstance(quest_case.message, dict)
    assert quest_case.message["payload"]["sub_agent"] == (
        "quest_generator.production_quest"
    )


def test_provider_profile_requires_explicit_opt_in() -> None:
    profile = smoke.build_profile("providers")

    assert profile.name == "providers"
    assert profile.requires_external_opt_in is True
    assert [case.expected_agent for case in profile.cases] == [
        "quest_generator",
    ]


def test_provider_profile_skips_without_explicit_opt_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(smoke.EXTERNAL_PROVIDER_OPT_IN, raising=False)

    exit_code = asyncio.run(
        smoke.run_profile(
            smoke.build_profile("providers"),
            smoke.DEFAULT_BASE_URL,
            smoke.DEFAULT_WS_PATH,
        )
    )

    assert exit_code == 0


def test_websocket_url_is_derived_from_http_base_url() -> None:
    assert (
        smoke.build_websocket_url("http://127.0.0.1:18000", "/ws/agent")
        == "ws://127.0.0.1:18000/ws/agent"
    )
    assert (
        smoke.build_websocket_url("https://example.test/api", "ws/agent")
        == "wss://example.test/api/ws/agent"
    )


def test_agent_connection_manifest_check_validates_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requested_urls: list[str] = []

    class FakeResponse:
        def __enter__(self) -> FakeResponse:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return (
                b'{"status":"ok","websocket_path":"/ws/agent",'
                b'"request_type":"agent.request",'
                b'"response_types":["agent.response","agent.error"],'
                b'"top_level_agents":["quest_generator"]}'
            )

    def fake_urlopen(url: str, timeout: int) -> FakeResponse:
        requested_urls.append(url)
        assert timeout == 5
        return FakeResponse()

    monkeypatch.setattr(smoke.urllib.request, "urlopen", fake_urlopen)

    response = smoke.check_agent_connection_manifest("http://127.0.0.1:18000")

    assert requested_urls == ["http://127.0.0.1:18000/api/v1/agent-connection"]
    assert response == {"type": None}


def test_response_validation_accepts_expected_agent_response() -> None:
    case = smoke.SmokeCase(
        name="quest",
        message={
            "type": "agent.request",
            "request_id": "request-smoke",
            "agent": "quest_generator",
            "payload": {"sub_agent": "quest_generator.production_quest"},
        },
        expected_type="agent.response",
        expected_agent="quest_generator",
        expected_sub_agent="quest_generator.production_quest",
    )

    smoke.validate_case_response(
        case,
        {
            "type": "agent.response",
            "agent": "quest_generator",
            "payload": {
                "metadata": {
                    "selectedLeafAgent": "quest_generator.production_quest",
                }
            },
        },
    )


def test_response_validation_rejects_wrong_error_code() -> None:
    case = smoke.SmokeCase(
        name="routing unavailable",
        message={
            "type": "agent.request",
            "request_id": "request-smoke",
            "agent": "quest_generator",
            "payload": {"sub_agent": "quest_generator.production_quest"},
        },
        expected_type="agent.error",
        expected_agent="quest_generator",
        expected_error_code="ROUTING_UNAVAILABLE",
    )

    try:
        smoke.validate_case_response(
            case,
            {
                "type": "agent.error",
                "agent": "quest_generator",
                "error": {"code": "INVALID_PAYLOAD"},
            },
        )
    except smoke.SmokeError as exc:
        assert "ROUTING_UNAVAILABLE" in str(exc)
    else:
        raise AssertionError("Expected SmokeError")


def test_response_validation_rejects_wrong_quest_count() -> None:
    case = smoke.SmokeCase(
        name="quest",
        message={
            "type": "agent.request",
            "request_id": "request-smoke",
            "agent": "quest_generator",
        },
        expected_type="agent.response",
        expected_agent="quest_generator",
        expected_quest_count=5,
    )

    try:
        smoke.validate_case_response(
            case,
            {
                "type": "agent.response",
                "agent": "quest_generator",
                "payload": {"quests": [{"id": 1}]},
            },
        )
    except smoke.SmokeError as exc:
        assert "expected 5 quests" in str(exc)
    else:
        raise AssertionError("Expected SmokeError")
