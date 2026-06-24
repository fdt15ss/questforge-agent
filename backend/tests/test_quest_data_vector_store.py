from __future__ import annotations

from quest_data.vector_documents import VectorDocument
from quest_data.vector_store import HashingEmbeddingFunction, create_local_vector_store


def test_hashing_embedding_function_is_deterministic() -> None:
    embedding_function = HashingEmbeddingFunction(dimensions=16)

    first = embedding_function(["회로기판 resource_circuit_board"])[0]
    second = embedding_function(["회로기판 resource_circuit_board"])[0]

    assert first == second
    assert len(first) == 16
    assert any(value != 0 for value in first)


def test_local_vector_store_indexes_and_queries_documents() -> None:
    documents: list[VectorDocument] = [
        {
            "id": "recipe:recipe_make_circuit_board",
            "document": (
                "레시피 ID recipe_make_circuit_board 이름 회로기판 제작 공정 "
                "입력 resource_copper_wire resource_iron_plate 출력 "
                "resource_circuit_board"
            ),
            "metadata": {
                "source_type": "recipe",
                "source_id": "recipe_make_circuit_board",
                "tier": "T2",
            },
        },
        {
            "id": "scenario:scenario_signal_tower_build",
            "document": (
                "시나리오 ID scenario_signal_tower_build 주제 신호탑 건설 "
                "회로기판과 신호 설비 준비 resource_circuit_board"
            ),
            "metadata": {
                "source_type": "scenario",
                "source_id": "scenario_signal_tower_build",
                "tier": "",
            },
        },
    ]
    store = create_local_vector_store(dimensions=32)

    store.rebuild(documents)
    results = store.query("회로기판 신호 설비", n_results=2)

    assert [result["id"] for result in results] == [
        "scenario:scenario_signal_tower_build",
        "recipe:recipe_make_circuit_board",
    ]
    assert all(result["distance"] >= 0 for result in results)
