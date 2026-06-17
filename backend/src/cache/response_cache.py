"""In-memory agent response cache."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ResponseCacheEntry:
    """Cached agent response payload and metadata."""

    payload: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ResponseCache:
    """Small in-memory response cache used by the local graph setup."""

    _items: dict[str, ResponseCacheEntry] = field(default_factory=dict)

    def get(self, key: str) -> dict[str, Any] | None:
        """Return a cached payload if one exists."""

        entry = self._items.get(key)
        if entry is None:
            return None
        return entry.payload

    def get_entry(self, key: str) -> ResponseCacheEntry | None:
        """Return a cached response entry if one exists."""

        return self._items.get(key)

    def set(
        self,
        key: str,
        payload: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Store a response payload."""

        self._items[key] = ResponseCacheEntry(
            payload=payload,
            metadata=metadata or {},
        )
