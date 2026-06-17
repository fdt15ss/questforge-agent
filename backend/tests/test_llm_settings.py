from __future__ import annotations

import pytest

from llm.settings import LLMSettings


def test_llm_settings_defaults_to_disabled_slots(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("QUESTFORGE_LLM_DEFAULT_PROVIDER", "google")

    settings = LLMSettings.from_env({})

    assert settings.default.provider == "none"
    assert settings.fallback1.provider == "none"
    assert settings.fallback2.provider == "none"
    assert settings.timeout_ms == 20000
    assert settings.max_output_tokens == 2048
    assert settings.temperature == 0.2


def test_llm_settings_uses_local_default_slot_in_development() -> None:
    settings = LLMSettings.from_env(
        {
            "ENVIRONMENT": "development",
            "QUESTFORGE_LLM_DEFAULT_MODEL": "llama3.1:8b",
            "QUESTFORGE_LLM_DEFAULT_BASE_URL": "http://localhost:11434/v1",
        }
    )

    assert settings.default.provider == "local"
    assert settings.default.model == "llama3.1:8b"
    assert settings.default.base_url == "http://localhost:11434/v1"
    assert settings.fallback1.provider == "none"
    assert settings.fallback2.provider == "none"


def test_llm_settings_rejects_unknown_provider() -> None:
    with pytest.raises(ValueError, match="Unsupported LLM provider"):
        LLMSettings.from_env({"QUESTFORGE_LLM_DEFAULT_PROVIDER": "unknown"})


def test_llm_settings_uses_google_default_model_and_key_priority() -> None:
    settings = LLMSettings.from_env(
        {
            "QUESTFORGE_LLM_DEFAULT_PROVIDER": "google",
            "QUESTFORGE_LLM_DEFAULT_MODEL": "gemini-2.5-flash",
            "QUESTFORGE_LLM_DEFAULT_API_KEY": "slot-key",
            "GEMINI_API_KEY": "gemini-key",
            "GOOGLE_API_KEY": "google-key",
        }
    )

    assert settings.default.model == "gemini-2.5-flash"
    assert settings.default.api_key == "slot-key"

    settings = LLMSettings.from_env(
        {
            "QUESTFORGE_LLM_DEFAULT_PROVIDER": "google",
            "QUESTFORGE_LLM_DEFAULT_MODEL": "gemini-2.5-flash",
            "GEMINI_API_KEY": "gemini-key",
            "GOOGLE_API_KEY": "google-key",
        }
    )

    assert settings.default.api_key == "gemini-key"


def test_llm_settings_requires_google_model() -> None:
    with pytest.raises(ValueError, match="requires QUESTFORGE_LLM_DEFAULT_MODEL"):
        LLMSettings.from_env(
            {
                "QUESTFORGE_LLM_DEFAULT_PROVIDER": "google",
                "GEMINI_API_KEY": "gemini-key",
            }
        )


def test_llm_settings_requires_openai_model_and_uses_openai_key() -> None:
    with pytest.raises(ValueError, match="requires QUESTFORGE_LLM_DEFAULT_MODEL"):
        LLMSettings.from_env(
            {
                "QUESTFORGE_LLM_DEFAULT_PROVIDER": "openai",
                "OPENAI_API_KEY": "openai-key",
            }
        )

    settings = LLMSettings.from_env(
        {
            "QUESTFORGE_LLM_DEFAULT_PROVIDER": "openai",
            "QUESTFORGE_LLM_DEFAULT_MODEL": "gpt-5.5",
            "OPENAI_API_KEY": "openai-key",
        }
    )

    assert settings.default.model == "gpt-5.5"
    assert settings.default.api_key == "openai-key"


def test_llm_settings_requires_local_model_and_base_url() -> None:
    with pytest.raises(ValueError, match="requires QUESTFORGE_LLM_DEFAULT_MODEL"):
        LLMSettings.from_env({"QUESTFORGE_LLM_DEFAULT_PROVIDER": "local"})

    with pytest.raises(ValueError, match="requires QUESTFORGE_LLM_DEFAULT_BASE_URL"):
        LLMSettings.from_env(
            {
                "QUESTFORGE_LLM_DEFAULT_PROVIDER": "local",
                "QUESTFORGE_LLM_DEFAULT_MODEL": "llama3.1:8b",
            }
        )

    settings = LLMSettings.from_env(
        {
            "QUESTFORGE_LLM_DEFAULT_PROVIDER": "local",
            "QUESTFORGE_LLM_DEFAULT_MODEL": "llama3.1:8b",
            "QUESTFORGE_LLM_DEFAULT_BASE_URL": "http://localhost:11434/v1",
        }
    )

    assert settings.default.model == "llama3.1:8b"
    assert settings.default.base_url == "http://localhost:11434/v1"
    assert settings.default.api_key is None
