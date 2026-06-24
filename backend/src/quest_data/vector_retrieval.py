"""Semantic vector retrieval helpers for quest-generation prompts."""

from __future__ import annotations

import logging
from typing import Any, Protocol, TypedDict


MAX_SEMANTIC_DOCUMENT_CHARS = 500

_LOGGER = logging.getLogger(__name__)


class SemanticMatch(TypedDict):
    id: str
    source_type: str
    source_id: str
    document: str
    distance: float


class QueryableVectorStore(Protocol):
    def query(self, query_text: str, n_results: int) -> list[dict[str, Any]]: ...


def build_semantic_query(payload: dict[str, Any]) -> str:
    """Return a compact text query from quest payload strings and IDs."""

    return " ".join(_unique(_collect_strings(payload)))


def retrieve_semantic_context(
    payload: dict[str, Any],
    store: QueryableVectorStore,
    max_matches: int = 5,
) -> list[SemanticMatch]:
    """Return prompt-safe semantic matches, or an empty list if search fails."""

    if max_matches <= 0:
        return []

    query_text = build_semantic_query(payload)
    if not query_text:
        return []

    try:
        matches = store.query(query_text, n_results=max_matches)
        if not isinstance(matches, list) or not all(
            isinstance(match, dict) for match in matches
        ):
            return []
        return [_semantic_match(match) for match in matches]
    except Exception:
        _LOGGER.warning("Semantic vector retrieval failed", exc_info=True)
        return []


def _semantic_match(match: dict[str, Any]) -> SemanticMatch:
    metadata = match.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}

    document = str(match.get("document", ""))
    if len(document) > MAX_SEMANTIC_DOCUMENT_CHARS:
        document = document[:MAX_SEMANTIC_DOCUMENT_CHARS]

    return {
        "id": str(match.get("id", "")),
        "source_type": str(metadata.get("source_type", "")),
        "source_id": str(metadata.get("source_id", "")),
        "document": document,
        "distance": _float(match.get("distance", 0.0)),
    }


def _collect_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        strings: list[str] = []
        for key, nested in value.items():
            strings.extend(_collect_strings(key))
            strings.extend(_collect_strings(nested))
        return strings
    if isinstance(value, list):
        strings = []
        for nested in value:
            strings.extend(_collect_strings(nested))
        return strings
    return []


def _unique(values: list[str]) -> list[str]:
    unique_values: list[str] = []
    for value in values:
        if value and value not in unique_values:
            unique_values.append(value)
    return unique_values


def _float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0