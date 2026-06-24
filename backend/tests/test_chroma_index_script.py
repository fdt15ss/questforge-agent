from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from quest_data import vector_context
from quest_data.vector_documents import VectorDocument
from quest_data.vector_store import ChromaVectorStore, HashingEmbeddingFunction
from scripts import rebuild_chroma_index


def test_chroma_vector_store_rebuild_replaces_collection(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake_client = FakeChromaClient(str(tmp_path))
    fake_module = SimpleNamespace(PersistentClient=lambda path: fake_client)
    monkeypatch.setitem(sys.modules, "chromadb", fake_module)
    documents: list[VectorDocument] = [
        {
            "id": "resource:resource_copper_wire",
            "document": "copper wire",
            "metadata": {"source_type": "resource", "source_id": "resource_copper_wire"},
        }
    ]

    store = ChromaVectorStore(tmp_path)
    store.rebuild(documents)

    assert fake_client.path == str(tmp_path)
    assert fake_client.deleted == ["questforge_game_context"]
    assert fake_client.collections["questforge_game_context"].added == [
        {
            "ids": ["resource:resource_copper_wire"],
            "documents": ["copper wire"],
            "metadatas": [
                {"source_type": "resource", "source_id": "resource_copper_wire"}
            ],
        }
    ]


def test_chroma_vector_store_query_flattens_chroma_results(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake_client = FakeChromaClient(str(tmp_path))
    fake_collection = fake_client.get_or_create_collection(
        name="questforge_game_context",
        embedding_function=HashingEmbeddingFunction(),
    )
    fake_collection.query_result = {
        "ids": [["scenario:signal", "recipe:circuit"]],
        "documents": [["signal tower context", "circuit board recipe"]],
        "metadatas": [[{"source_type": "scenario"}, {"source_type": "recipe"}]],
        "distances": [[0.12, 0.34]],
    }
    fake_module = SimpleNamespace(PersistentClient=lambda path: fake_client)
    monkeypatch.setitem(sys.modules, "chromadb", fake_module)

    store = ChromaVectorStore(tmp_path)

    assert store.query("", n_results=3) == []
    assert store.query("signal", n_results=0) == []
    assert store.query("signal", n_results=2) == [
        {
            "id": "scenario:signal",
            "document": "signal tower context",
            "metadata": {"source_type": "scenario"},
            "distance": 0.12,
        },
        {
            "id": "recipe:circuit",
            "document": "circuit board recipe",
            "metadata": {"source_type": "recipe"},
            "distance": 0.34,
        },
    ]
    assert fake_collection.queries == [
        {
            "query_texts": ["signal"],
            "n_results": 2,
            "include": ["documents", "metadatas", "distances"],
        }
    ]


def test_rebuild_chroma_index_script_rebuilds_store(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    documents: list[VectorDocument] = [
        {"id": "resource:one", "document": "one", "metadata": {"source_type": "resource"}},
        {"id": "recipe:two", "document": "two", "metadata": {"source_type": "recipe"}},
    ]
    fake_store = FakeStore()
    created_paths: list[Path] = []

    monkeypatch.setattr(
        rebuild_chroma_index,
        "QuestDataRepository",
        lambda: object(),
    )
    monkeypatch.setattr(
        rebuild_chroma_index,
        "build_vector_documents",
        lambda repository: documents,
    )
    monkeypatch.setattr(
        rebuild_chroma_index,
        "create_chroma_vector_store",
        lambda path: created_paths.append(path) or fake_store,
    )

    rebuild_chroma_index.main(["--persist-dir", str(tmp_path)])

    assert created_paths == [tmp_path]
    assert fake_store.rebuilt_documents == documents
    assert capsys.readouterr().out == (
        f"Indexed 2 quest game-data documents into {tmp_path}\n"
    )


def test_rebuild_chroma_index_parse_args_defaults_to_repo_chroma_dir() -> None:
    args = rebuild_chroma_index.parse_args([])

    assert args.persist_dir == (
        Path(rebuild_chroma_index.__file__).resolve().parents[2]
        / ".chroma"
        / "questforge_game_context"
    )


def test_default_vector_store_caches_created_store(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    vector_context.default_vector_store.cache_clear()
    sentinel_store = object()
    created_paths: list[Path] = []

    def fake_create_chroma_vector_store(persist_dir: Path) -> object:
        created_paths.append(persist_dir)
        return sentinel_store

    monkeypatch.setattr(vector_context, "_default_persist_dir", lambda: tmp_path)
    monkeypatch.setattr(
        vector_context,
        "create_chroma_vector_store",
        fake_create_chroma_vector_store,
    )

    assert vector_context.default_vector_store() is sentinel_store
    assert vector_context.default_vector_store() is sentinel_store
    assert created_paths == [tmp_path]


def test_default_vector_store_caches_none_when_directory_absent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    vector_context.default_vector_store.cache_clear()
    missing_persist_dir = tmp_path / "missing"
    created_paths: list[Path] = []

    def fake_create_chroma_vector_store(persist_dir: Path) -> object:
        created_paths.append(persist_dir)
        raise AssertionError("store should not be created for absent directory")

    monkeypatch.setattr(
        vector_context,
        "_default_persist_dir",
        lambda: missing_persist_dir,
    )
    monkeypatch.setattr(
        vector_context,
        "create_chroma_vector_store",
        fake_create_chroma_vector_store,
    )

    assert vector_context.default_vector_store() is None
    missing_persist_dir.mkdir()
    assert vector_context.default_vector_store() is None
    assert created_paths == []


def test_default_vector_store_caches_none_after_creation_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    vector_context.default_vector_store.cache_clear()
    created_paths: list[Path] = []

    def fake_create_chroma_vector_store(persist_dir: Path) -> object:
        created_paths.append(persist_dir)
        raise RuntimeError("chroma unavailable")

    monkeypatch.setattr(vector_context, "_default_persist_dir", lambda: tmp_path)
    monkeypatch.setattr(
        vector_context,
        "create_chroma_vector_store",
        fake_create_chroma_vector_store,
    )

    assert vector_context.default_vector_store() is None
    assert vector_context.default_vector_store() is None
    assert created_paths == [tmp_path]


def test_fake_chroma_client_rejects_wrong_embedding_function(tmp_path: Path) -> None:
    fake_client = FakeChromaClient(str(tmp_path))

    with pytest.raises(AssertionError, match="HashingEmbeddingFunction"):
        fake_client.get_or_create_collection(
            name="questforge_game_context",
            embedding_function=object(),  # type: ignore[arg-type]
        )


def test_fake_chroma_collection_validates_query_contract() -> None:
    fake_collection = FakeChromaCollection(HashingEmbeddingFunction())

    with pytest.raises(AssertionError, match="query_texts"):
        fake_collection.query(
            query_texts=("signal",),  # type: ignore[arg-type]
            n_results=2,
            include=["documents", "metadatas", "distances"],
        )

    with pytest.raises(AssertionError, match="n_results"):
        fake_collection.query(
            query_texts=["signal"],
            n_results=True,  # type: ignore[arg-type]
            include=["documents", "metadatas", "distances"],
        )

    with pytest.raises(AssertionError, match="include"):
        fake_collection.query(
            query_texts=["signal"],
            n_results=2,
            include=["documents", "distances", "metadatas"],
        )


def test_fake_chroma_collection_validates_add_lengths() -> None:
    fake_collection = FakeChromaCollection(HashingEmbeddingFunction())

    with pytest.raises(AssertionError, match="same length"):
        fake_collection.add(
            ids=["resource:one"],
            documents=["one", "two"],
            metadatas=[{"source_type": "resource"}],
        )

class FakeStore:
    def __init__(self) -> None:
        self.rebuilt_documents: list[VectorDocument] = []

    def rebuild(self, documents: list[VectorDocument]) -> None:
        self.rebuilt_documents = documents


class FakeChromaClient:
    def __init__(self, path: str) -> None:
        self.path = path
        self.deleted: list[str] = []
        self.collections: dict[str, FakeChromaCollection] = {}

    def delete_collection(self, name: str) -> None:
        self.deleted.append(name)
        self.collections.pop(name, None)

    def get_or_create_collection(
        self,
        *,
        name: str,
        embedding_function: HashingEmbeddingFunction,
    ) -> FakeChromaCollection:
        _assert_hashing_embedding_function_contract(embedding_function)
        collection = self.collections.get(name)
        if collection is None:
            collection = FakeChromaCollection(embedding_function)
            self.collections[name] = collection
        return collection


class FakeChromaCollection:
    def __init__(self, embedding_function: HashingEmbeddingFunction) -> None:
        self.embedding_function = embedding_function
        self.added: list[dict[str, object]] = []
        self.queries: list[dict[str, object]] = []
        self.query_result: dict[str, list[list[object]]] = {
            "ids": [[]],
            "documents": [[]],
            "metadatas": [[]],
            "distances": [[]],
        }

    def add(
        self,
        *,
        ids: list[str],
        documents: list[str],
        metadatas: list[dict[str, object]],
    ) -> None:
        assert len(ids) == len(documents) == len(metadatas), (
            "ids, documents, and metadatas must have the same length"
        )
        self.added.append(
            {"ids": ids, "documents": documents, "metadatas": metadatas}
        )

    def query(
        self,
        *,
        query_texts: list[str],
        n_results: int,
        include: list[str],
    ) -> dict[str, list[list[object]]]:
        assert isinstance(query_texts, list) and all(
            isinstance(query_text, str) for query_text in query_texts
        ), "query_texts must be list[str]"
        assert type(n_results) is int, "n_results must be int"
        assert include == ["documents", "metadatas", "distances"], (
            "include must be exactly ['documents', 'metadatas', 'distances']"
        )
        self.queries.append(
            {
                "query_texts": query_texts,
                "n_results": n_results,
                "include": include,
            }
        )
        return self.query_result


def _assert_hashing_embedding_function_contract(
    embedding_function: HashingEmbeddingFunction,
) -> None:
    assert isinstance(embedding_function, HashingEmbeddingFunction), (
        "embedding_function must be a HashingEmbeddingFunction"
    )
    for attribute_name in ("__call__", "name", "get_config", "build_from_config"):
        if hasattr(HashingEmbeddingFunction, attribute_name) or hasattr(
            embedding_function,
            attribute_name,
        ):
            assert callable(getattr(embedding_function, attribute_name, None)), (
                f"embedding_function.{attribute_name} must be callable"
            )