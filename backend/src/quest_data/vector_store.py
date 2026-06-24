"""Small local vector store used before the ChromaDB adapter exists."""

from __future__ import annotations

import hashlib
import importlib
import math
import re
from pathlib import Path
from typing import Any

from quest_data.vector_documents import VectorDocument

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[가-힣]+")
_HANGUL_RE = re.compile(r"^[가-힣]+$")


Documents = list[str]
Embeddings = list[list[float]]


class HashingEmbeddingFunction:
    """Deterministic bag-of-token hashing embedding with L2 normalization."""

    def __init__(self, dimensions: int = 64) -> None:
        if dimensions <= 0:
            raise ValueError("dimensions must be positive")
        self.dimensions = dimensions

    def __call__(self, input: Documents) -> Embeddings:
        return [self._embed(text) for text in input]

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in _tokens(text):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            value = int.from_bytes(digest, "big", signed=False)
            index = value % self.dimensions
            sign = 1.0 if ((value >> 63) & 1) == 0 else -1.0
            vector[index] += sign

        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]


class LocalVectorStore:
    def __init__(self, embedding_function: HashingEmbeddingFunction) -> None:
        self._embedding_function = embedding_function
        self._documents: list[VectorDocument] = []
        self._embeddings: list[list[float]] = []

    def rebuild(self, documents: list[VectorDocument]) -> None:
        self._documents = list(documents)
        self._embeddings = self._embedding_function(
            [document["document"] for document in self._documents]
        )

    def query(self, query_text: str, n_results: int) -> list[dict[str, Any]]:
        if n_results <= 0:
            return []

        query_embedding = self._embedding_function([query_text])[0]
        scored = [
            (
                1.0 - _cosine_similarity(query_embedding, embedding),
                document["id"],
                document,
            )
            for document, embedding in zip(self._documents, self._embeddings, strict=True)
        ]
        scored.sort(key=lambda item: (item[0], item[1]))

        return [
            {
                "id": document["id"],
                "document": document["document"],
                "metadata": document["metadata"],
                "distance": max(distance, 0.0),
            }
            for distance, _document_id, document in scored[:n_results]
        ]


_CHROMA_NOT_FOUND_ERROR_NAMES = {
    "InvalidCollectionException",
    "NotFoundError",
}


class ChromaVectorStore:
    def __init__(
        self,
        persist_directory: Path,
        collection_name: str = "questforge_game_context",
    ) -> None:
        chromadb = importlib.import_module("chromadb")
        self._persist_directory = persist_directory
        self._collection_name = collection_name
        self._client = chromadb.PersistentClient(path=str(persist_directory))
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            embedding_function=HashingEmbeddingFunction(),
        )

    def rebuild(self, documents: list[VectorDocument]) -> None:
        self._delete_collection_if_present()
        self._collection = self._client.get_or_create_collection(
            name=self._collection_name,
            embedding_function=HashingEmbeddingFunction(),
        )
        if not documents:
            return

        self._collection.add(
            ids=[document["id"] for document in documents],
            documents=[document["document"] for document in documents],
            metadatas=[document["metadata"] for document in documents],
        )

    def query(self, query_text: str, n_results: int) -> list[dict[str, Any]]:
        if not query_text.strip() or n_results <= 0:
            return []

        result = self._collection.query(
            query_texts=[query_text],
            n_results=n_results,
            include=["documents", "metadatas", "distances"],
        )
        return _flatten_chroma_query_result(result)

    def _delete_collection_if_present(self) -> None:
        try:
            self._client.delete_collection(name=self._collection_name)
        except Exception as exc:
            message = str(exc).lower()
            is_missing_collection = (
                exc.__class__.__name__ in _CHROMA_NOT_FOUND_ERROR_NAMES
                or "does not exist" in message
                or "not found" in message
            )
            if not is_missing_collection:
                raise


def create_chroma_vector_store(
    path: Path,
    collection_name: str = "questforge_game_context",
) -> ChromaVectorStore:
    return ChromaVectorStore(path, collection_name=collection_name)


def create_local_vector_store(dimensions: int = 64) -> LocalVectorStore:
    return LocalVectorStore(HashingEmbeddingFunction(dimensions=dimensions))


def _flatten_chroma_query_result(result: dict[str, Any]) -> list[dict[str, Any]]:
    ids = _first_chroma_result_row(result.get("ids"))
    documents = _first_chroma_result_row(result.get("documents"))
    metadatas = _first_chroma_result_row(result.get("metadatas"))
    distances = _first_chroma_result_row(result.get("distances"))

    flattened: list[dict[str, Any]] = []
    for index, document_id in enumerate(ids):
        metadata = metadatas[index] if index < len(metadatas) else {}
        flattened.append(
            {
                "id": document_id,
                "document": documents[index] if index < len(documents) else "",
                "metadata": metadata or {},
                "distance": distances[index] if index < len(distances) else None,
            }
        )
    return flattened


def _first_chroma_result_row(value: object) -> list[object]:
    if not value:
        return []
    first = value[0]
    if first is None:
        return []
    return list(first)


def _tokens(text: str) -> list[str]:
    tokens: list[str] = []
    for match in _TOKEN_RE.finditer(text.lower()):
        token = match.group(0)
        tokens.append(token)
        if _HANGUL_RE.match(token):
            tokens.extend(_character_ngrams(token, 2))
            tokens.extend(_character_ngrams(token, 3))
    return tokens


def _character_ngrams(token: str, size: int) -> list[str]:
    if len(token) <= size:
        return []
    return [token[index : index + size] for index in range(len(token) - size + 1)]


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    return sum(left_value * right_value for left_value, right_value in zip(left, right))
