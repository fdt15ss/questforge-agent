"""LLM slot handling for the agent pipeline."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from agents.pipeline.state import AgentGraphState
from llm.adapter import LLMAdapter, NoopLLMAdapter
from llm.settings import LLMModelSlot, LLMSettings


@dataclass(frozen=True)
class LLMCallSlot:
    name: str
    provider: str
    model: str | None
    adapter: LLMAdapter


def build_llm_call_slots(
    *,
    llm: LLMAdapter | None,
    settings: LLMSettings | None,
    adapter_factory: Callable[[LLMModelSlot], LLMAdapter],
) -> tuple[LLMCallSlot, LLMCallSlot, LLMCallSlot]:
    if llm is not None:
        noop = NoopLLMAdapter()
        return (
            LLMCallSlot("injected", "injected", None, llm),
            LLMCallSlot("fallback1", "none", None, noop),
            LLMCallSlot("fallback2", "none", None, noop),
        )

    resolved_settings = settings or LLMSettings.from_env()
    return (
        _slot_adapter(resolved_settings.default, adapter_factory),
        _slot_adapter(resolved_settings.fallback1, adapter_factory),
        _slot_adapter(resolved_settings.fallback2, adapter_factory),
    )


def invoke_llm_call_slot(
    slot: LLMCallSlot,
    prompt: str,
    prompt_messages: list[dict[str, str]] | None = None,
) -> AgentGraphState:
    raw = (
        slot.adapter.invoke_messages(prompt_messages)
        if prompt_messages is not None
        else slot.adapter.invoke(prompt)
    )
    output: AgentGraphState = {
        "llmRaw": raw,
        "llmSlot": slot.name,
        "llmProvider": slot.provider,
        "llmModel": slot.model or "",
    }
    return output


def _slot_adapter(
    slot: LLMModelSlot,
    adapter_factory: Callable[[LLMModelSlot], LLMAdapter],
) -> LLMCallSlot:
    return LLMCallSlot(
        name=slot.name,
        provider=slot.provider,
        model=slot.model,
        adapter=adapter_factory(slot),
    )
