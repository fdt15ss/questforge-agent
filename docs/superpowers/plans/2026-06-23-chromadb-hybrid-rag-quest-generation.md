# ChromaDB Hybrid RAG Quest Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 현재 Structured CSV RAG 위에 ChromaDB semantic retrieval 계층을 추가해, 퀘스트 LLM prompt가 정확한 CSV rule과 의미 기반 시나리오/레시피 힌트를 함께 참고하게 만든다.

**Architecture:** 기존 `retrieve_game_context()`는 계속 exact/rule 기반 source of truth로 유지한다. 새 ChromaDB 계층은 `scenario_context.csv`, `recipes.csv`, `resources.csv`의 설명성 텍스트를 문서화해 local persistent collection에 색인하고, 요청 payload에서 만든 자연어 query로 semantic top-k를 찾는다. 병합 결과는 기존 `[RETRIEVED_GAME_CONTEXT]` 안의 `semantic_matches`에만 추가하며, objective/reward/quantity/clear_condition 결정권은 서버 deterministic layer가 계속 가진다.

**Tech Stack:** Python 3.12, ChromaDB, Pydantic/dataclass CSV rows, pytest, FastAPI/WebSocket agent pipeline, LangGraph quest agents.

---

## 현재 구조 요약

- `backend/src/quest_data/retrieval.py`가 Structured CSV RAG의 중심이다.
- `retrieve_game_context(payload, repository)`는 `resources`, `recipes`, `scenario_contexts`, `reward_rules`를 반환한다.
- 상위 `quest_generator`, `production_quest`, `delivery_quest`는 이미 prompt에 `[RETRIEVED_GAME_CONTEXT]`를 넣는다.
- LLM은 `quest_plan` 또는 `quest_text_updates`만 생성한다.
- 최종 `QuestResponse`의 목표, 수량, 보상, clear condition은 서버가 병합/검증한다.

## 설계 원칙

- ChromaDB는 semantic hint 전용이다.
- ChromaDB 검색 결과는 `semantic_matches`로만 들어간다.
- CSV exact id/rule retrieval 결과가 semantic 결과보다 우선한다.
- ChromaDB가 비어 있거나 장애가 나도 기존 Structured CSV RAG만으로 정상 동작해야 한다.
- 테스트 환경에서 외부 모델 다운로드나 API 호출이 발생하면 안 된다.
- 첫 구현은 deterministic local hashing embedding을 사용한다. 이후 OpenAI embedding이나 SentenceTransformer로 교체할 수 있게 인터페이스를 분리한다.

## 파일 구조

- Modify: `backend/pyproject.toml`
  - `chromadb` dependency 추가.
- Modify: `backend/uv.lock`
  - `uv sync` 또는 `uv lock`으로 dependency lock 반영.
- Create: `backend/src/quest_data/vector_documents.py`
  - CSV row를 Chroma document로 변환한다.
- Create: `backend/src/quest_data/vector_store.py`
  - ChromaDB client, collection, deterministic embedding function, upsert/query adapter를 담당한다.
- Create: `backend/src/quest_data/vector_retrieval.py`
  - payload query text 생성, vector query 실행, prompt-safe semantic match shape 생성.
- Modify: `backend/src/quest_data/retrieval.py`
  - 기존 Structured CSV RAG 결과에 optional `semantic_matches`를 병합한다.
- Create: `backend/tests/test_quest_data_vector_documents.py`
  - CSV row가 stable Chroma document로 변환되는지 검증한다.
- Create: `backend/tests/test_quest_data_vector_store.py`
  - fake/in-memory Chroma adapter 또는 temp persistent dir로 add/query 동작을 검증한다.
- Modify: `backend/tests/test_quest_data_retrieval.py`
  - `semantic_matches` 병합 및 Chroma 장애 시 fallback을 검증한다.
- Modify: `backend/tests/test_quest_agent_service.py`
  - parent prompt에 `semantic_matches`가 들어가는지 검증한다.
- Modify: `backend/tests/test_agent_leaf_behaviors.py`
  - production/delivery prompt에도 `semantic_matches`가 들어가는지 검증한다.
- Modify: `backend/tests/test_message_router.py`
  - 실제 pipeline prompt에 semantic context가 포함되는지 검증한다.
- Create: `backend/scripts/rebuild_chroma_index.py`
  - CSV에서 Chroma persistent index를 재생성하는 수동 스크립트.
- Modify: `README.md`
  - Hybrid Structured + Chroma RAG 설명과 index 재생성 명령 추가.
- Modify: `docs/agent-request-structure.md`
  - `[RETRIEVED_GAME_CONTEXT].semantic_matches` 내부 계약 문서화.

---

### Task 1: Chroma Dependency와 설정 경계 추가

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/uv.lock`

- [ ] **Step 1: dependency 추가 전 확인**

Run:

```powershell
rg -n "chromadb" backend\pyproject.toml backend\uv.lock
```

Expected: 아무 결과가 없어야 한다.

- [ ] **Step 2: `backend/pyproject.toml`에 dependency 추가**

`dependencies`에 아래 항목을 추가한다.

```toml
"chromadb>=0.5.0,<1.0",
```

주의: 현재 `pytest`가 production dependency로 들어가 있다면, 이 작업과 분리해서 별도 정리 여부를 판단한다. Chroma 계획 구현 중 임의로 제거하지 않는다.

- [ ] **Step 3: lock 갱신**

Run:

```powershell
cd backend
uv lock
```

Expected: `backend/uv.lock`이 갱신되고 `chromadb` 관련 package가 포함된다.

- [ ] **Step 4: import smoke**

Run:

```powershell
cd backend
uv run python -c "import chromadb; print(chromadb.__name__)"
```

Expected:

```text
chromadb
```

- [ ] **Step 5: Commit**

```bash
git add backend/pyproject.toml backend/uv.lock
git commit -m "chore: add chromadb dependency"
```

---

### Task 2: Vector Document 변환 계층 추가

**Files:**
- Create: `backend/src/quest_data/vector_documents.py`
- Create: `backend/tests/test_quest_data_vector_documents.py`

- [ ] **Step 1: failing test 작성**

Create `backend/tests/test_quest_data_vector_documents.py`:

```python
from __future__ import annotations

from pathlib import Path

from quest_data.repository import QuestDataRepository
from quest_data.vector_documents import build_vector_documents


GAME_DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "game"


def test_build_vector_documents_creates_stable_ids_and_metadata() -> None:
    repository = QuestDataRepository(GAME_DATA_DIR)

    documents = build_vector_documents(repository)

    ids = [document["id"] for document in documents]
    circuit_recipe = next(
        document
        for document in documents
        if document["id"] == "recipe:recipe_make_circuit_board"
    )
    circuit_resource = next(
        document
        for document in documents
        if document["id"] == "resource:resource_circuit_board"
    )

    assert len(ids) == len(set(ids))
    assert "recipe:recipe_make_circuit_board" in ids
    assert "resource:resource_circuit_board" in ids
    assert "scenario:scenario_signal_tower_build" in ids
    assert circuit_recipe["metadata"]["source_type"] == "recipe"
    assert circuit_recipe["metadata"]["source_id"] == "recipe_make_circuit_board"
    assert circuit_recipe["metadata"]["tier"] == "T2"
    assert "회로기판" in circuit_recipe["document"]
    assert "resource_circuit_board" in circuit_resource["document"]


def test_build_vector_documents_is_deterministic() -> None:
    repository = QuestDataRepository(GAME_DATA_DIR)

    first = build_vector_documents(repository)
    second = build_vector_documents(repository)

    assert first == second
```

- [ ] **Step 2: test 실패 확인**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend\tests\test_quest_data_vector_documents.py -q
```

Expected: `ModuleNotFoundError: No module named 'quest_data.vector_documents'`

- [ ] **Step 3: 최소 구현 작성**

Create `backend/src/quest_data/vector_documents.py`:

```python
from __future__ import annotations

from typing import Any, TypedDict

from quest_data.repository import QuestDataRepository


class VectorDocument(TypedDict):
    id: str
    document: str
    metadata: dict[str, str | int | float | bool]


def build_vector_documents(repository: QuestDataRepository) -> list[VectorDocument]:
    documents: list[VectorDocument] = []

    for resource in sorted(repository.list_resources(), key=lambda row: row.resource_id):
        documents.append(
            {
                "id": f"resource:{resource.resource_id}",
                "document": " ".join(
                    [
                        f"자원ID: {resource.resource_id}",
                        f"자원명: {resource.resource_name}",
                        f"종류: {resource.resource_type}",
                        f"획득방법: {resource.acquisition_method}",
                        f"사용처: {resource.usage}",
                    ]
                ),
                "metadata": {
                    "source_type": "resource",
                    "source_id": resource.resource_id,
                    "resource_type": resource.resource_type,
                },
            }
        )

    for recipe in sorted(repository.list_recipes(), key=lambda row: row.recipe_id):
        documents.append(
            {
                "id": f"recipe:{recipe.recipe_id}",
                "document": " ".join(
                    [
                        f"레시피ID: {recipe.recipe_id}",
                        f"레시피명: {recipe.recipe_name}",
                        f"입력자원: {', '.join(recipe.input_resources)}",
                        f"출력자원: {', '.join(recipe.output_resources)}",
                        f"진행티어: {recipe.tier}",
                        f"퀘스트태그: {', '.join(recipe.quest_tags)}",
                        f"설명힌트: {recipe.llm_prompt_hint}",
                    ]
                ),
                "metadata": {
                    "source_type": "recipe",
                    "source_id": recipe.recipe_id,
                    "tier": recipe.tier,
                },
            }
        )

    for scenario in sorted(
        repository.list_scenario_contexts(),
        key=lambda row: row.context_id,
    ):
        documents.append(
            {
                "id": f"scenario:{scenario.context_id}",
                "document": " ".join(
                    [
                        f"시나리오ID: {scenario.context_id}",
                        f"arc: {scenario.arc}",
                        f"theme: {scenario.theme}",
                        f"summary: {scenario.summary}",
                        f"quest_usage: {scenario.quest_usage}",
                        f"related_resources: {', '.join(scenario.related_resources)}",
                        f"related_recipes: {', '.join(scenario.related_recipes)}",
                        f"related_quest_types: {', '.join(scenario.related_quest_types)}",
                        f"설명힌트: {scenario.llm_prompt_hint}",
                    ]
                ),
                "metadata": {
                    "source_type": "scenario",
                    "source_id": scenario.context_id,
                    "arc": scenario.arc,
                    "theme": scenario.theme,
                },
            }
        )

    return documents
```

- [ ] **Step 4: test 통과 확인**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend\tests\test_quest_data_vector_documents.py -q
```

Expected:

```text
2 passed
```

- [ ] **Step 5: Commit**

```bash
git add backend/src/quest_data/vector_documents.py backend/tests/test_quest_data_vector_documents.py
git commit -m "feat: build chroma vector documents from quest csv"
```

---

### Task 3: Chroma Store Adapter 추가

**Files:**
- Create: `backend/src/quest_data/vector_store.py`
- Create: `backend/tests/test_quest_data_vector_store.py`

- [ ] **Step 1: failing test 작성**

Create `backend/tests/test_quest_data_vector_store.py`:

```python
from __future__ import annotations

from quest_data.vector_store import (
    HashingEmbeddingFunction,
    create_chroma_vector_store,
)


def test_hashing_embedding_function_is_deterministic() -> None:
    embedding_function = HashingEmbeddingFunction(dimensions=16)

    first = embedding_function(["회로기판 생산 병목"])
    second = embedding_function(["회로기판 생산 병목"])

    assert first == second
    assert len(first) == 1
    assert len(first[0]) == 16
    assert any(value != 0 for value in first[0])


def test_chroma_vector_store_indexes_and_queries_documents(tmp_path) -> None:
    store = create_chroma_vector_store(tmp_path)
    documents = [
        {
            "id": "recipe:recipe_make_circuit_board",
            "document": "회로기판 제작 공정 구리선 철판 전자 부품",
            "metadata": {
                "source_type": "recipe",
                "source_id": "recipe_make_circuit_board",
                "tier": "T2",
            },
        },
        {
            "id": "scenario:scenario_signal_tower_build",
            "document": "신호탑 건설 장거리 통신 회로기판 구리선",
            "metadata": {
                "source_type": "scenario",
                "source_id": "scenario_signal_tower_build",
                "arc": "초반",
            },
        },
    ]

    store.rebuild(documents)
    matches = store.query("회로기판으로 신호 설비를 준비한다", n_results=2)

    assert [match["id"] for match in matches] == [
        "recipe:recipe_make_circuit_board",
        "scenario:scenario_signal_tower_build",
    ]
    assert matches[0]["metadata"]["source_id"] == "recipe_make_circuit_board"
    assert matches[0]["distance"] >= 0
```

- [ ] **Step 2: test 실패 확인**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend\tests\test_quest_data_vector_store.py -q
```

Expected: `ModuleNotFoundError: No module named 'quest_data.vector_store'`

- [ ] **Step 3: Chroma adapter 구현**

Create `backend/src/quest_data/vector_store.py`:

```python
from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Protocol

import chromadb
from chromadb import Documents, EmbeddingFunction, Embeddings

from quest_data.vector_documents import VectorDocument


class VectorMatch(dict[str, Any]):
    pass


class VectorStore(Protocol):
    def rebuild(self, documents: list[VectorDocument]) -> None:
        ...

    def query(self, query_text: str, *, n_results: int) -> list[dict[str, Any]]:
        ...


class HashingEmbeddingFunction(EmbeddingFunction):
    def __init__(self, dimensions: int = 64) -> None:
        self.dimensions = dimensions

    def __call__(self, input: Documents) -> Embeddings:
        return [_embed_text(text, self.dimensions) for text in input]

    @staticmethod
    def name() -> str:
        return "questforge-hashing-embedding"

    def get_config(self) -> dict[str, Any]:
        return {"dimensions": self.dimensions}

    @staticmethod
    def build_from_config(config: dict[str, Any]) -> "HashingEmbeddingFunction":
        return HashingEmbeddingFunction(dimensions=int(config.get("dimensions", 64)))


def _embed_text(text: str, dimensions: int) -> list[float]:
    vector = [0.0 for _ in range(dimensions)]
    for token in text.lower().split():
        index = sum(ord(char) for char in token) % dimensions
        vector[index] += 1.0
    length = math.sqrt(sum(value * value for value in vector))
    if length == 0:
        return vector
    return [value / length for value in vector]


class ChromaVectorStore:
    def __init__(
        self,
        persist_directory: Path,
        *,
        collection_name: str = "questforge_game_context",
    ) -> None:
        self._client = chromadb.PersistentClient(path=str(persist_directory))
        self._collection_name = collection_name
        self._embedding_function = HashingEmbeddingFunction()
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            embedding_function=self._embedding_function,
        )

    def rebuild(self, documents: list[VectorDocument]) -> None:
        self._client.delete_collection(self._collection_name)
        self._collection = self._client.get_or_create_collection(
            name=self._collection_name,
            embedding_function=self._embedding_function,
        )
        if not documents:
            return
        self._collection.add(
            ids=[document["id"] for document in documents],
            documents=[document["document"] for document in documents],
            metadatas=[document["metadata"] for document in documents],
        )

    def query(self, query_text: str, *, n_results: int) -> list[dict[str, Any]]:
        if not query_text.strip() or n_results <= 0:
            return []
        result = self._collection.query(
            query_texts=[query_text],
            n_results=n_results,
            include=["documents", "metadatas", "distances"],
        )
        ids = result.get("ids", [[]])[0]
        documents = result.get("documents", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]
        return [
            {
                "id": match_id,
                "document": document,
                "metadata": metadata,
                "distance": distance,
            }
            for match_id, document, metadata, distance in zip(
                ids,
                documents,
                metadatas,
                distances,
            )
        ]


def create_chroma_vector_store(path: Path) -> ChromaVectorStore:
    return ChromaVectorStore(path)
```

- [ ] **Step 4: test 통과 확인**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend\tests\test_quest_data_vector_store.py -q
```

Expected:

```text
2 passed
```

- [ ] **Step 5: Commit**

```bash
git add backend/src/quest_data/vector_store.py backend/tests/test_quest_data_vector_store.py
git commit -m "feat: add chromadb vector store adapter"
```

---

### Task 4: Semantic Retrieval 계층 추가

**Files:**
- Create: `backend/src/quest_data/vector_retrieval.py`
- Create: `backend/tests/test_quest_data_vector_retrieval.py`

- [ ] **Step 1: fake store 기반 failing test 작성**

Create `backend/tests/test_quest_data_vector_retrieval.py`:

```python
from __future__ import annotations

from quest_data.vector_retrieval import retrieve_semantic_context


class FakeVectorStore:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def query(self, query_text: str, *, n_results: int):
        self.queries.append(query_text)
        return [
            {
                "id": "scenario:scenario_signal_tower_build",
                "document": "신호탑 건설 장거리 통신 회로기판 구리선",
                "metadata": {
                    "source_type": "scenario",
                    "source_id": "scenario_signal_tower_build",
                },
                "distance": 0.12,
            }
        ][:n_results]


def test_retrieve_semantic_context_builds_query_from_payload() -> None:
    store = FakeVectorStore()
    payload = {
        "quest_type": "daily",
        "current_main_quest": {
            "title": "신호 설비 부품 준비",
            "objectives": [
                {"target_item_id": "resource_circuit_board"},
            ],
        },
        "recent_events": ["장거리 통신 준비가 필요하다."],
    }

    matches = retrieve_semantic_context(payload, store, max_matches=1)

    assert store.queries
    assert "resource_circuit_board" in store.queries[0]
    assert "장거리 통신 준비가 필요하다." in store.queries[0]
    assert matches == [
        {
            "id": "scenario:scenario_signal_tower_build",
            "source_type": "scenario",
            "source_id": "scenario_signal_tower_build",
            "document": "신호탑 건설 장거리 통신 회로기판 구리선",
            "distance": 0.12,
        }
    ]


def test_retrieve_semantic_context_returns_empty_on_store_failure() -> None:
    class BrokenStore:
        def query(self, query_text: str, *, n_results: int):
            raise RuntimeError("chroma unavailable")

    matches = retrieve_semantic_context(
        {"recent_events": ["회로기판 병목"]},
        BrokenStore(),
        max_matches=3,
    )

    assert matches == []
```

- [ ] **Step 2: test 실패 확인**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend\tests\test_quest_data_vector_retrieval.py -q
```

Expected: `ModuleNotFoundError: No module named 'quest_data.vector_retrieval'`

- [ ] **Step 3: semantic retrieval 구현**

Create `backend/src/quest_data/vector_retrieval.py`:

```python
from __future__ import annotations

from typing import Any, Protocol, TypedDict


class SemanticMatch(TypedDict):
    id: str
    source_type: str
    source_id: str
    document: str
    distance: float


class QueryableVectorStore(Protocol):
    def query(self, query_text: str, *, n_results: int) -> list[dict[str, Any]]:
        ...


def retrieve_semantic_context(
    payload: dict[str, Any],
    store: QueryableVectorStore,
    *,
    max_matches: int = 5,
) -> list[SemanticMatch]:
    query_text = build_semantic_query(payload)
    try:
        matches = store.query(query_text, n_results=max_matches)
    except Exception:
        return []
    return [_semantic_match(match) for match in matches]


def build_semantic_query(payload: dict[str, Any]) -> str:
    parts: list[str] = []
    _collect_query_parts(payload, parts)
    return " ".join(part for part in parts if part)


def _collect_query_parts(value: Any, parts: list[str]) -> None:
    if isinstance(value, str):
        parts.append(value)
        return
    if isinstance(value, dict):
        for nested in value.values():
            _collect_query_parts(nested, parts)
        return
    if isinstance(value, list):
        for nested in value:
            _collect_query_parts(nested, parts)


def _semantic_match(match: dict[str, Any]) -> SemanticMatch:
    metadata = match.get("metadata") or {}
    return {
        "id": str(match.get("id", "")),
        "source_type": str(metadata.get("source_type", "")),
        "source_id": str(metadata.get("source_id", "")),
        "document": str(match.get("document", "")),
        "distance": float(match.get("distance", 0.0)),
    }
```

- [ ] **Step 4: test 통과 확인**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend\tests\test_quest_data_vector_retrieval.py -q
```

Expected:

```text
2 passed
```

- [ ] **Step 5: Commit**

```bash
git add backend/src/quest_data/vector_retrieval.py backend/tests/test_quest_data_vector_retrieval.py
git commit -m "feat: add semantic quest context retrieval"
```

---

### Task 5: Structured Retrieval과 Semantic Matches 병합

**Files:**
- Modify: `backend/src/quest_data/retrieval.py`
- Modify: `backend/tests/test_quest_data_retrieval.py`

- [ ] **Step 1: failing test 추가**

Append to `backend/tests/test_quest_data_retrieval.py`:

```python
class FakeVectorStore:
    def query(self, query_text: str, *, n_results: int):
        return [
            {
                "id": "scenario:scenario_signal_tower_build",
                "document": "신호탑 건설 장거리 통신 회로기판 구리선",
                "metadata": {
                    "source_type": "scenario",
                    "source_id": "scenario_signal_tower_build",
                },
                "distance": 0.12,
            }
        ]


def test_retrieve_game_context_includes_optional_semantic_matches() -> None:
    repository = QuestDataRepository(GAME_DATA_DIR)

    context = retrieve_game_context(
        _payload(),
        repository,
        vector_store=FakeVectorStore(),
        max_semantic_matches=1,
    )

    assert context["semantic_matches"] == [
        {
            "id": "scenario:scenario_signal_tower_build",
            "source_type": "scenario",
            "source_id": "scenario_signal_tower_build",
            "document": "신호탑 건설 장거리 통신 회로기판 구리선",
            "distance": 0.12,
        }
    ]
```

- [ ] **Step 2: test 실패 확인**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend\tests\test_quest_data_retrieval.py::test_retrieve_game_context_includes_optional_semantic_matches -q
```

Expected: `TypeError: retrieve_game_context() got an unexpected keyword argument 'vector_store'`

- [ ] **Step 3: `retrieval.py` 타입과 signature 수정**

`RetrievedGameContext`에 필드를 추가한다.

```python
semantic_matches: list[dict[str, Any]]
```

`retrieve_game_context` signature를 아래처럼 확장한다.

```python
def retrieve_game_context(
    payload: dict[str, Any],
    repository: QuestDataRepository,
    *,
    max_resources: int = 8,
    max_recipes: int = 6,
    max_scenarios: int = 5,
    max_reward_rules: int = 3,
    vector_store: Any | None = None,
    max_semantic_matches: int = 5,
) -> RetrievedGameContext:
```

return 직전에 semantic matches를 계산한다.

```python
    semantic_matches = []
    if vector_store is not None:
        from quest_data.vector_retrieval import retrieve_semantic_context

        semantic_matches = retrieve_semantic_context(
            payload,
            vector_store,
            max_matches=max_semantic_matches,
        )
```

return dict에 아래 항목을 추가한다.

```python
"semantic_matches": semantic_matches,
```

- [ ] **Step 4: 기존 retrieval test 전체 통과 확인**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend\tests\test_quest_data_retrieval.py -q
```

Expected:

```text
3 passed
```

- [ ] **Step 5: Commit**

```bash
git add backend/src/quest_data/retrieval.py backend/tests/test_quest_data_retrieval.py
git commit -m "feat: merge semantic matches into quest retrieval context"
```

---

### Task 6: Chroma Index Rebuild Script 추가

**Files:**
- Create: `backend/scripts/rebuild_chroma_index.py`
- Create or Modify: `backend/tests/test_chroma_index_script.py`

- [ ] **Step 1: script test 작성**

Create `backend/tests/test_chroma_index_script.py`:

```python
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_rebuild_chroma_index_script_creates_index(tmp_path) -> None:
    script = Path(__file__).resolve().parents[1] / "scripts" / "rebuild_chroma_index.py"

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--persist-dir",
            str(tmp_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "Indexed" in result.stdout
    assert any(tmp_path.iterdir())
```

- [ ] **Step 2: test 실패 확인**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend\tests\test_chroma_index_script.py -q
```

Expected: script file not found.

- [ ] **Step 3: rebuild script 구현**

Create `backend/scripts/rebuild_chroma_index.py`:

```python
from __future__ import annotations

import argparse
from pathlib import Path

from quest_data.repository import QuestDataRepository
from quest_data.vector_documents import build_vector_documents
from quest_data.vector_store import create_chroma_vector_store


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--persist-dir",
        default=".chroma/questforge_game_context",
    )
    args = parser.parse_args()

    repository = QuestDataRepository()
    documents = build_vector_documents(repository)
    store = create_chroma_vector_store(Path(args.persist_dir))
    store.rebuild(documents)
    print(f"Indexed {len(documents)} quest game-data documents into {args.persist_dir}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: script test 통과 확인**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend\tests\test_chroma_index_script.py -q
```

Expected:

```text
1 passed
```

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/rebuild_chroma_index.py backend/tests/test_chroma_index_script.py
git commit -m "feat: add chroma quest index rebuild script"
```

---

### Task 7: Agents가 Chroma Semantic Context를 사용할 수 있게 연결

**Files:**
- Modify: `backend/src/agents/quest_generator/agent.py`
- Modify: `backend/src/agents/quest_generator/production_quest.py`
- Modify: `backend/src/agents/quest_generator/delivery_quest.py`
- Modify: `backend/tests/test_quest_agent_service.py`
- Modify: `backend/tests/test_agent_leaf_behaviors.py`
- Modify: `backend/tests/test_message_router.py`

- [ ] **Step 1: prompt test 기대값 추가**

기존 prompt tests에 아래 assertion을 추가한다.

```python
assert "semantic_matches" in prompt
```

대상 tests:

- `test_quest_generator_prompt_includes_retrieved_game_context`
- `test_production_quest_prompt_includes_retrieved_game_context`
- `test_delivery_quest_prompt_includes_retrieved_game_context`
- `test_pipeline_includes_retrieved_game_context_in_quest_plan_prompt`

- [ ] **Step 2: tests 실패 확인**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend\tests\test_quest_agent_service.py::test_quest_generator_prompt_includes_retrieved_game_context backend\tests\test_agent_leaf_behaviors.py::test_production_quest_prompt_includes_retrieved_game_context backend\tests\test_agent_leaf_behaviors.py::test_delivery_quest_prompt_includes_retrieved_game_context backend\tests\test_message_router.py::test_pipeline_includes_retrieved_game_context_in_quest_plan_prompt -q
```

Expected: `"semantic_matches" not in prompt`로 실패한다.

- [ ] **Step 3: agent별 Chroma store factory 추가**

각 agent 파일에서 `retrieve_game_context(payload, QuestDataRepository())` 호출을 아래 helper를 통해 바꾼다.

```python
from pathlib import Path

from quest_data.vector_store import create_chroma_vector_store


def _default_vector_store():
    repo_root = Path(__file__).resolve().parents[4]
    persist_dir = repo_root / ".chroma" / "questforge_game_context"
    if not persist_dir.exists():
        return None
    return create_chroma_vector_store(persist_dir)
```

호출부:

```python
retrieved_game_context = retrieve_game_context(
    payload,
    QuestDataRepository(),
    vector_store=_default_vector_store(),
)
```

주의: `persist_dir`가 없으면 기존 Structured CSV RAG만 동작한다. 테스트에서는 index가 없어도 `semantic_matches: []`가 prompt에 들어가야 한다.

- [ ] **Step 4: tests 통과 확인**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend\tests\test_quest_agent_service.py::test_quest_generator_prompt_includes_retrieved_game_context backend\tests\test_agent_leaf_behaviors.py::test_production_quest_prompt_includes_retrieved_game_context backend\tests\test_agent_leaf_behaviors.py::test_delivery_quest_prompt_includes_retrieved_game_context backend\tests\test_message_router.py::test_pipeline_includes_retrieved_game_context_in_quest_plan_prompt -q
```

Expected:

```text
4 passed
```

- [ ] **Step 5: Commit**

```bash
git add backend/src/agents/quest_generator/agent.py backend/src/agents/quest_generator/production_quest.py backend/src/agents/quest_generator/delivery_quest.py backend/tests/test_quest_agent_service.py backend/tests/test_agent_leaf_behaviors.py backend/tests/test_message_router.py
git commit -m "feat: include chroma semantic context in quest prompts"
```

---

### Task 8: Documentation 업데이트

**Files:**
- Modify: `README.md`
- Modify: `docs/agent-request-structure.md`

- [ ] **Step 1: README에 Hybrid RAG 설명 추가**

`README.md`의 `Structured CSV RAG` 섹션을 아래 내용으로 확장한다.

```markdown
### ChromaDB Semantic Layer

`data/game` CSV는 계속 source of truth입니다. 서버는 먼저 exact id/rule 기반 Structured CSV RAG를 수행하고, 선택적으로 `.chroma/questforge_game_context`에 저장된 ChromaDB index에서 semantic matches를 조회합니다.

Index 재생성:

```bash
cd backend
uv run python scripts/rebuild_chroma_index.py --persist-dir ../.chroma/questforge_game_context
```

ChromaDB 결과는 prompt 내부 `[RETRIEVED_GAME_CONTEXT].semantic_matches`에만 들어갑니다. rewards, objectives, quantities, clear conditions는 semantic search 결과로 결정하지 않습니다.
```

- [ ] **Step 2: request structure 문서에 내부 contract 추가**

`docs/agent-request-structure.md`의 `Structured CSV RAG 동작` 섹션에 아래 내용을 추가한다.

```markdown
ChromaDB index가 준비되어 있으면 `[RETRIEVED_GAME_CONTEXT]`에 `semantic_matches`가 추가됩니다.

```json
{
  "semantic_matches": [
    {
      "id": "scenario:scenario_signal_tower_build",
      "source_type": "scenario",
      "source_id": "scenario_signal_tower_build",
      "document": "신호탑 건설 장거리 통신 회로기판 구리선",
      "distance": 0.12
    }
  ]
}
```

이 값은 내부 prompt context입니다. 클라이언트 응답 schema에는 직접 노출하지 않습니다.
```

- [ ] **Step 3: 문서 검색 확인**

Run:

```powershell
rg -n "ChromaDB|semantic_matches|rebuild_chroma_index" README.md docs\agent-request-structure.md
```

Expected: 두 문서 모두에서 관련 키워드가 나온다.

- [ ] **Step 4: Commit**

```bash
git add README.md docs/agent-request-structure.md
git commit -m "docs: explain chromadb hybrid rag quest context"
```

---

### Task 9: 전체 검증

**Files:**
- All touched files.

- [ ] **Step 1: focused tests 실행**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend\tests\test_quest_data_vector_documents.py backend\tests\test_quest_data_vector_store.py backend\tests\test_quest_data_vector_retrieval.py backend\tests\test_quest_data_retrieval.py backend\tests\test_quest_agent_service.py backend\tests\test_agent_leaf_behaviors.py backend\tests\test_message_router.py -q
```

Expected: 모든 selected tests pass.

- [ ] **Step 2: 전체 backend tests 실행**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend\tests -q
```

Expected: 모든 tests pass.

- [ ] **Step 3: whitespace check**

Run:

```powershell
git diff --check
```

Expected: trailing whitespace error가 없어야 한다. CRLF 경고는 Windows 작업환경에서 나올 수 있으나 diff check 실패가 아니면 허용한다.

- [ ] **Step 4: 실제 index rebuild smoke**

Run:

```powershell
cd backend
uv run python scripts/rebuild_chroma_index.py --persist-dir ..\.chroma\questforge_game_context
```

Expected:

```text
Indexed <N> quest game-data documents into ..\.chroma\questforge_game_context
```

- [ ] **Step 5: prompt smoke**

Run:

```powershell
cd backend
uv run python -c "from agents.base import AgentContext; from agents.quest_generator.agent import QuestGeneratorAgent; payload={'quest_type':'daily','quest_generation_options':{'count':1,'domain_counts':{'production':1}},'current_main_quest':{'objectives':[{'target_item_id':'resource_circuit_board','required_quantity':10,'current_quantity':2}]},'game_state':{'inventory':{'resource_circuit_board':2},'unlocked_recipes':['recipe_make_circuit_board']},'recent_events':['장거리 통신 준비가 필요하다.']}; prompt=QuestGeneratorAgent().build_prompt(payload, AgentContext(request_id='smoke', session_id='s', client_id='c', metadata={})); print('[RETRIEVED_GAME_CONTEXT]' in prompt, 'semantic_matches' in prompt, 'resource_circuit_board' in prompt)"
```

Expected:

```text
True True True
```

- [ ] **Step 6: final commit**

If any verification fix was needed:

```bash
git add .
git commit -m "fix: stabilize chromadb hybrid rag integration"
```

If no verification fix was needed, do not create an empty commit.

---

## Self-Review

**Spec coverage:** ChromaDB 사용, 현재 CSV RAG와 결합, 보상/목표 결정권 유지, prompt 주입, index rebuild, tests, docs까지 모두 task로 분리했다.

**Placeholder scan:** TBD/TODO/fill later 없이 파일, 함수명, test code, 명령, expected output을 명시했다.

**Type consistency:** `VectorDocument`, `HashingEmbeddingFunction`, `ChromaVectorStore`, `retrieve_semantic_context`, `semantic_matches` 명칭을 전 task에서 동일하게 사용했다.

**Risk notes:** ChromaDB default embedding은 모델 자동 다운로드가 발생할 수 있으므로 첫 구현은 custom deterministic hashing embedding을 사용한다. 포트폴리오에서 “semantic vector DB” 효과를 더 강하게 보여주려면 후속 작업으로 OpenAI `text-embedding-3-small` 또는 SentenceTransformer embedding function을 선택 옵션으로 추가한다.
