"""Agent protocol error models."""

from __future__ import annotations

from typing import Any


def build_error_payload(
    code: str,
    message: str,
    *,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a stable protocol error payload."""

    return {
        "code": code,
        "message": message,
        "details": details or {},
    }
