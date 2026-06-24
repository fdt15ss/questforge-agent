"""Rebuild the persistent Chroma index for quest game-data retrieval."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from quest_data.repository import QuestDataRepository
from quest_data.vector_documents import build_vector_documents
from quest_data.vector_store import create_chroma_vector_store


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rebuild the QuestForge game-data Chroma index."
    )
    parser.add_argument(
        "--persist-dir",
        type=Path,
        default=Path(".chroma/questforge_game_context"),
        help="Directory where the Chroma PersistentClient stores the index.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    repository = QuestDataRepository()
    documents = build_vector_documents(repository)
    store = create_chroma_vector_store(args.persist_dir)

    store.rebuild(documents)

    print(
        f"Indexed {len(documents)} quest game-data documents into {args.persist_dir}"
    )


if __name__ == "__main__":
    main()
