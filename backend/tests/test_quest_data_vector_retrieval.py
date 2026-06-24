from __future__ import annotations

import logging
from typing import Any

from quest_data.vector_retrieval import (
    MAX_SEMANTIC_DOCUMENT_CHARS,
    retrieve_semantic_context,
)


class FakeVectorStore:
    def __init__(self) -> None:
        self.query_text = ""
        self.n_results = 0

    def query(self, query_text: str, n_results: int) -> list[dict[str, Any]]:
        self.query_text = query_text
        self.n_results = n_results
        return [
            {
                "id": "resource:resource_circuit_board",
                "document": "Resource: circuit board",
                "metadata": {
                    "source_type": "resource",
                    "source_id": "resource_circuit_board",
                },
                "distance": 0.12,
            }
        ]


class BrokenStore:
    def query(self, query_text: str, n_results: int) -> list[dict[str, Any]]:
        raise RuntimeError("vector store unavailable")


class MalformedStore:
    def query(self, query_text: str, n_results: int) -> dict[str, list[list[str]]]:
        return {"ids": [["x"]]}


class LongDocumentStore:
    def query(self, query_text: str, n_results: int) -> list[dict[str, Any]]:
        return [
            {
                "id": "resource:long_document",
                "document": "x" * (MAX_SEMANTIC_DOCUMENT_CHARS + 20),
                "metadata": {
                    "source_type": "resource",
                    "source_id": "resource_long_document",
                },
                "distance": 0.3,
            }
        ]


def _payload() -> dict[str, Any]:
    return {
        "current_main_quest": {
            "title": "Restore circuit board production line",
            "description": "Use copper wire and iron plates to rebuild circuit boards.",
            "objectives": [
                {
                    "target_item_id": "resource_circuit_board",
                    "required_quantity": 10,
                }
            ],
        },
        "game_state": {
            "inventory": {
                "resource_copper_wire": 18,
                "resource_circuit_board": 2,
            },
            "unlocked_recipes": ["recipe_make_circuit_board"],
        },
        "recent_events": ["Operators found a circuit board bottleneck."],
        "progression": {"stage": "electronics"},
    }


def test_retrieve_semantic_context_builds_query_from_payload() -> None:
    store = FakeVectorStore()

    matches = retrieve_semantic_context(_payload(), store, max_matches=3)

    assert "resource_circuit_board" in store.query_text
    assert "Operators found a circuit board bottleneck." in store.query_text
    assert store.n_results == 3
    assert matches == [
        {
            "id": "resource:resource_circuit_board",
            "source_type": "resource",
            "source_id": "resource_circuit_board",
            "document": "Resource: circuit board",
            "distance": 0.12,
        }
    ]


def test_retrieve_semantic_context_returns_empty_on_store_failure(caplog) -> None:
    caplog.set_level(logging.WARNING)

    assert retrieve_semantic_context(_payload(), BrokenStore()) == []
    assert "Semantic vector retrieval failed" in caplog.text


def test_retrieve_semantic_context_returns_empty_for_malformed_store_result() -> None:
    assert retrieve_semantic_context(_payload(), MalformedStore()) == []


def test_retrieve_semantic_context_truncates_prompt_document() -> None:
    matches = retrieve_semantic_context(_payload(), LongDocumentStore())

    assert len(matches) == 1
    assert len(matches[0]["document"]) == MAX_SEMANTIC_DOCUMENT_CHARS