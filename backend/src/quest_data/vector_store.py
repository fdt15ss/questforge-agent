"""Small local vector store used before the ChromaDB adapter exists."""

from __future__ import annotations

import hashlib
import math
import re
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


def create_local_vector_store(dimensions: int = 64) -> LocalVectorStore:
    return LocalVectorStore(HashingEmbeddingFunction(dimensions=dimensions))


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
