"""LLM provider slot settings."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

LLMProvider = Literal["none", "google", "openai", "local"]

_PROVIDERS: set[str] = {"none", "google", "openai", "local"}


@dataclass(frozen=True)
class LLMModelSlot:
    """One configured LLM provider slot."""

    name: str
    provider: LLMProvider
    model: str | None = None
    base_url: str | None = None
    api_key: str | None = None


@dataclass(frozen=True)
class LLMSettings:
    """LLM provider settings for LangGraph fallback slots."""

    default: LLMModelSlot
    fallback1: LLMModelSlot
    fallback2: LLMModelSlot
    timeout_ms: int = 20000
    max_output_tokens: int = 2048
    temperature: float = 0.2

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> LLMSettings:
        """Create settings from environment variables."""

        source = os.environ if env is None else env
        return cls(
            default=_slot_from_env(source, "default"),
            fallback1=_slot_from_env(source, "fallback1"),
            fallback2=_slot_from_env(source, "fallback2"),
            timeout_ms=_int_from_env(source, "QUESTFORGE_LLM_TIMEOUT_MS", 20000),
            max_output_tokens=_int_from_env(
                source,
                "QUESTFORGE_LLM_MAX_OUTPUT_TOKENS",
                2048,
            ),
            temperature=_float_from_env(source, "QUESTFORGE_LLM_TEMPERATURE", 0.2),
        )


def _slot_from_env(env: Mapping[str, str], slot: str) -> LLMModelSlot:
    prefix = f"QUESTFORGE_LLM_{slot.upper()}"
    provider = _provider_from_env(env, slot, prefix)
    model = _string_from_env(env, f"{prefix}_MODEL")
    base_url = _string_from_env(env, f"{prefix}_BASE_URL")
    api_key = _api_key_from_env(env, slot, prefix, provider)

    if provider == "none":
        return LLMModelSlot(name=slot, provider=provider)
    if provider == "google":
        _require(model, f"{prefix}_MODEL")
        return LLMModelSlot(
            name=slot,
            provider=provider,
            model=model,
            base_url=base_url,
            api_key=api_key,
        )
    if provider == "openai":
        _require(model, f"{prefix}_MODEL")
        return LLMModelSlot(
            name=slot,
            provider=provider,
            model=model,
            base_url=base_url,
            api_key=api_key,
        )
    _require(model, f"{prefix}_MODEL")
    _require(base_url, f"{prefix}_BASE_URL")
    return LLMModelSlot(
        name=slot,
        provider=provider,
        model=model,
        base_url=base_url,
        api_key=api_key,
    )


def _provider_from_env(
    env: Mapping[str, str],
    slot: str,
    prefix: str,
) -> LLMProvider:
    provider = _string_from_env(env, f"{prefix}_PROVIDER")
    if provider is None and slot == "default":
        environment = (_string_from_env(env, "ENVIRONMENT") or "").lower()
        if environment == "development":
            provider = "local"
    provider = provider or "none"
    if provider not in _PROVIDERS:
        raise ValueError(f"Unsupported LLM provider: {provider}")
    return provider  # type: ignore[return-value]


def _api_key_from_env(
    env: Mapping[str, str],
    slot: str,
    prefix: str,
    provider: LLMProvider,
) -> str | None:
    slot_key = _string_from_env(env, f"{prefix}_API_KEY")
    if provider == "google":
        return (
            slot_key
            or _string_from_env(env, "GEMINI_API_KEY")
            or _string_from_env(env, "GOOGLE_API_KEY")
        )
    if provider == "openai":
        return slot_key or _string_from_env(env, "OPENAI_API_KEY")
    if provider == "local":
        return slot_key
    return None


def _string_from_env(env: Mapping[str, str], key: str) -> str | None:
    value = env.get(key)
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _int_from_env(env: Mapping[str, str], key: str, default: int) -> int:
    value = _string_from_env(env, key)
    return default if value is None else int(value)


def _float_from_env(env: Mapping[str, str], key: str, default: float) -> float:
    value = _string_from_env(env, key)
    return default if value is None else float(value)


def _require(value: str | None, key: str) -> None:
    if value is None:
        raise ValueError(f"Provider requires {key}")
