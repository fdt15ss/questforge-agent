from __future__ import annotations

from pathlib import Path

from quest_data.repository import QuestDataRepository
from quest_data.vector_documents import build_vector_documents


GAME_DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "game"


def test_build_vector_documents_creates_stable_ids_and_metadata() -> None:
    repository = QuestDataRepository(GAME_DATA_DIR)

    documents = build_vector_documents(repository)

    ids = [document["id"] for document in documents]
    assert len(ids) == len(set(ids))
    assert "recipe:recipe_make_circuit_board" in ids
    assert "resource:resource_circuit_board" in ids
    assert "scenario:scenario_signal_tower_build" in ids

    documents_by_id = {document["id"]: document for document in documents}
    recipe = documents_by_id["recipe:recipe_make_circuit_board"]
    resource = documents_by_id["resource:resource_circuit_board"]
    scenario = documents_by_id["scenario:scenario_signal_tower_build"]

    assert recipe["metadata"]["source_type"] == "recipe"
    assert recipe["metadata"]["source_id"] == "recipe_make_circuit_board"
    assert recipe["metadata"]["tier"] == "T2"
    assert resource["metadata"]["source_type"] == "resource"
    assert resource["metadata"]["source_id"] == "resource_circuit_board"
    assert "tier" in resource["metadata"]
    assert scenario["metadata"]["source_type"] == "scenario"
    assert scenario["metadata"]["source_id"] == "scenario_signal_tower_build"
    assert "tier" in scenario["metadata"]

    assert "회로기판" in resource["document"]
    assert "resource_circuit_board" in resource["document"]


def test_build_vector_documents_is_deterministic() -> None:
    repository = QuestDataRepository(GAME_DATA_DIR)

    first = build_vector_documents(repository)
    second = build_vector_documents(repository)

    assert first == second
