"""Optional semantic vector-store context for quest prompts."""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

from quest_data.vector_store import create_chroma_vector_store

logger = logging.getLogger(__name__)


def _default_persist_dir() -> Path:
    repo_root = Path(__file__).resolve().parents[3]
    return repo_root / ".chroma" / "questforge_game_context"


@lru_cache(maxsize=1)
def default_vector_store() -> object | None:
    """Return the default persistent Chroma store when it is available."""

    persist_dir = _default_persist_dir()
    if not persist_dir.exists():
        return None

    try:
        return create_chroma_vector_store(persist_dir)
    except Exception:
        logger.warning(
            "Failed to create default Chroma vector store at %s",
            persist_dir,
            exc_info=True,
        )
        return None