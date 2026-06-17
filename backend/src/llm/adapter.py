"""LLM provider adapters."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol

from google import genai
from google.genai import types
from openai import OpenAI

from llm.settings import LLMModelSlot

_OPENAI_BASE_URL = "https://api.openai.com/v1"

logger = logging.getLogger(__name__)


class LLMAdapter(Protocol):
    """Common contract for raw LLM text generation."""

    def invoke(self, prompt: str) -> str | None:
        """Return raw model output, or None when unavailable."""

    def invoke_messages(self, messages: list[dict[str, str]]) -> str | None:
        """Return raw model output for chat messages, or None when unavailable."""


class _GoogleModelsClient(Protocol):
    def generate_content(
        self,
        *,
        model: str,
        contents: str,
        config: object,
    ) -> object:
        """Generate content with the Google Gen AI SDK."""


class _GoogleClient(Protocol):
    models: _GoogleModelsClient


class _HttpResponse(Protocol):
    status_code: int
    body: object


class _HttpClient(Protocol):
    def post(
        self,
        *,
        url: str,
        headers: dict[str, str],
        json_body: dict[str, Any],
        timeout_ms: int,
    ) -> _HttpResponse:
        """Send JSON HTTP POST."""


class _OpenAiMessage(Protocol):
    content: str | None


class _OpenAiChoice(Protocol):
    message: _OpenAiMessage


class _OpenAiCompletion(Protocol):
    choices: list[_OpenAiChoice]


class _OpenAiChatCompletions(Protocol):
    def create(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        temperature: float,
        max_tokens: int | None = None,
        max_completion_tokens: int | None = None,
    ) -> _OpenAiCompletion:
        """Create chat completion."""


class _OpenAiChat(Protocol):
    completions: _OpenAiChatCompletions


class _OpenAiClient(Protocol):
    chat: _OpenAiChat


@dataclass(frozen=True)
class NoopLLMAdapter:
    """Disabled LLM adapter."""

    def invoke(self, prompt: str) -> str | None:
        """Return no output."""

        return None

    def invoke_messages(self, messages: list[dict[str, str]]) -> str | None:
        """Return no output."""

        return None


@dataclass(frozen=True)
class GoogleGenAiLLMAdapter:
    """Google Gen AI adapter."""

    slot: LLMModelSlot
    client: _GoogleClient | None = None
    timeout_ms: int = 20000
    max_output_tokens: int = 2048
    temperature: float = 0.2

    def invoke(self, prompt: str) -> str | None:
        """Return raw generated text from Google Gen AI."""

        return self._invoke_contents(prompt)

    def invoke_messages(self, messages: list[dict[str, str]]) -> str | None:
        """Return raw generated text from Google Gen AI chat messages."""

        return self._invoke_contents(_render_chat_messages(messages))

    def _invoke_contents(self, contents: str) -> str | None:
        """Return raw generated text from Google Gen AI contents."""

        if not self.slot.model:
            return None
        logger.info("Calling Google Gen AI LLM (model: %s)", self.slot.model)
        try:
            client = self.client or _create_google_client(self.slot.api_key)
            if client is None:
                return None
            response = client.models.generate_content(
                model=self.slot.model,
                contents=contents,
                config=_google_generate_config(
                    timeout_ms=self.timeout_ms,
                    max_output_tokens=self.max_output_tokens,
                    temperature=self.temperature,
                ),
            )
        except Exception as exc:
            logger.warning("Google Gen AI LLM call failed: %s", exc)
            return None

        text = getattr(response, "text", None)
        if not isinstance(text, str):
            return None
        if not text.strip():
            return None
        return text


@dataclass(frozen=True)
class OpenAILLMAdapter:
    """OpenAI Chat Completions adapter using the official SDK."""

    slot: LLMModelSlot
    client: _OpenAiClient | None = None
    timeout_ms: int = 20000
    max_output_tokens: int = 2048
    temperature: float = 0.2

    def invoke(self, prompt: str) -> str | None:
        """Return raw generated text from OpenAI."""

        return self.invoke_messages([_user_message(prompt)])

    def invoke_messages(self, messages: list[dict[str, str]]) -> str | None:
        """Return raw generated text from OpenAI chat messages."""

        if not self.slot.api_key:
            return None
        if not self.slot.model:
            return None
        logger.info("Calling OpenAI LLM (model: %s)", self.slot.model)
        try:
            client = self.client or _create_openai_client(
                api_key=self.slot.api_key,
                base_url=self.slot.base_url,
                timeout_ms=self.timeout_ms,
            )
            if client is None:
                return None

            completion = client.chat.completions.create(
                model=self.slot.model,
                messages=messages,
                temperature=self.temperature,
                **_openai_token_limit_kwargs(
                    self.slot.model,
                    self.max_output_tokens,
                ),
            )
        except Exception as exc:
            logger.warning("OpenAI LLM call failed: %s", exc)
            return None

        if completion is None:
            return None
        try:
            choices = completion.choices
            if not choices:
                return None
            message = choices[0].message
            content = message.content
            if not isinstance(content, str):
                return None
            if not content.strip():
                return None
            return content
        except (AttributeError, IndexError):
            return None


@dataclass(frozen=True)
class LocalLLMAdapter:
    """Local OpenAI-compatible Chat Completions adapter."""

    slot: LLMModelSlot
    http_client: _HttpClient | None = None
    timeout_ms: int = 20000
    max_output_tokens: int = 2048
    temperature: float = 0.2

    def invoke(self, prompt: str) -> str | None:
        """Return raw generated text from a local OpenAI-compatible endpoint."""

        return self.invoke_messages([_user_message(prompt)])

    def invoke_messages(self, messages: list[dict[str, str]]) -> str | None:
        """Return raw generated text from local chat messages."""

        if not self.slot.base_url:
            return None
        logger.info("Calling Local LLM (model: %s, url: %s)", self.slot.model, self.slot.base_url)
        return _invoke_openai_compatible(
            slot=self.slot,
            messages=messages,
            http_client=self.http_client,
            timeout_ms=self.timeout_ms,
            max_output_tokens=self.max_output_tokens,
            temperature=self.temperature,
            base_url=self.slot.base_url,
            api_key=self.slot.api_key,
        )


def create_llm_adapter(slot: LLMModelSlot) -> LLMAdapter:
    """Create an adapter for one configured LLM slot."""

    if slot.provider == "none":
        return NoopLLMAdapter()
    if slot.provider == "google":
        return GoogleGenAiLLMAdapter(slot)
    if slot.provider == "openai":
        return OpenAILLMAdapter(slot)
    return LocalLLMAdapter(slot)


def _user_message(prompt: str) -> dict[str, str]:
    return {"role": "user", "content": prompt}


def _render_chat_messages(messages: list[dict[str, str]]) -> str:
    return "\n\n".join(
        f"[{message.get('role', 'user').upper()}]\n{message.get('content', '')}"
        for message in messages
    )


def _openai_token_limit_kwargs(model: str, max_output_tokens: int) -> dict[str, int]:
    if model.startswith("gpt-5"):
        return {"max_completion_tokens": max_output_tokens}
    return {"max_tokens": max_output_tokens}


def _create_google_client(api_key: str | None) -> _GoogleClient | None:
    if not api_key:
        return None

    return genai.Client(api_key=api_key)


def _create_openai_client(
    api_key: str | None,
    base_url: str | None,
    timeout_ms: int,
) -> _OpenAiClient | None:
    if not api_key:
        return None

    return OpenAI(
        api_key=api_key,
        base_url=base_url or _OPENAI_BASE_URL,
        timeout=timeout_ms / 1000.0,
    )


def _google_generate_config(
    *,
    timeout_ms: int,
    max_output_tokens: int,
    temperature: float,
) -> object:
    return types.GenerateContentConfig(
        response_mime_type="text/plain",
        max_output_tokens=max_output_tokens,
        temperature=temperature,
        http_options=types.HttpOptions(timeout=timeout_ms),
    )


@dataclass(frozen=True)
class _HttpJsonResponse:
    status_code: int
    body: object


class _UrlLibHttpClient:
    def post(
        self,
        *,
        url: str,
        headers: dict[str, str],
        json_body: dict[str, Any],
        timeout_ms: int,
    ) -> _HttpJsonResponse:
        request = urllib.request.Request(
            url,
            data=json.dumps(json_body).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(
                request,
                timeout=timeout_ms / 1000,
            ) as response:
                body = json.loads(response.read().decode("utf-8"))
                return _HttpJsonResponse(status_code=response.status, body=body)
        except urllib.error.HTTPError as exc:
            return _HttpJsonResponse(status_code=exc.code, body={})


def _openai_chat_completions_url(base_url: str | None) -> str:
    return f"{(base_url or _OPENAI_BASE_URL).rstrip('/')}/chat/completions"


def _invoke_openai_compatible(
    *,
    slot: LLMModelSlot,
    messages: list[dict[str, str]],
    http_client: _HttpClient | None,
    timeout_ms: int,
    max_output_tokens: int,
    temperature: float,
    base_url: str,
    api_key: str | None,
) -> str | None:
    if not slot.model:
        return None
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        client = http_client or _UrlLibHttpClient()
        response = client.post(
            url=_openai_chat_completions_url(base_url),
            headers=headers,
            json_body={
                "model": slot.model,
                "messages": messages,
                "max_tokens": max_output_tokens,
                "temperature": temperature,
            },
            timeout_ms=timeout_ms,
        )
    except Exception as exc:
        logger.warning("Local LLM call failed: %s", exc)
        return None

    if response.status_code < 200 or response.status_code >= 300:
        return None
    return _extract_openai_message_content(response.body)


def _extract_openai_message_content(body: object) -> str | None:
    if not isinstance(body, dict):
        return None
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        return None
    message = first_choice.get("message")
    if not isinstance(message, dict):
        return None
    content = message.get("content")
    if not isinstance(content, str):
        return None
    if not content.strip():
        return None
    return content
