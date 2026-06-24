"""Build text documents for local and future vector retrieval."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, TypedDict

from quest_data.repository import QuestDataRepository


class VectorDocument(TypedDict):
    id: str
    document: str
    metadata: dict[str, Any]


def build_vector_documents(repository: QuestDataRepository) -> list[VectorDocument]:
    """Return deterministic vector documents for searchable quest data rows."""

    documents: list[VectorDocument] = []

    for resource in sorted(repository.list_resources(), key=lambda row: row.resource_id):
        fields = asdict(resource)
        documents.append(
            {
                "id": f"resource:{resource.resource_id}",
                "document": _format_document("자원", fields, _RESOURCE_FIELD_LABELS),
                "metadata": {
                    "source_type": "resource",
                    "source_id": resource.resource_id,
                    "tier": "",
                },
            }
        )

    for recipe in sorted(repository.list_recipes(), key=lambda row: row.recipe_id):
        fields = asdict(recipe)
        documents.append(
            {
                "id": f"recipe:{recipe.recipe_id}",
                "document": _format_document("레시피", fields, _RECIPE_FIELD_LABELS),
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
        fields = asdict(scenario)
        documents.append(
            {
                "id": f"scenario:{scenario.context_id}",
                "document": _format_document("시나리오", fields, _SCENARIO_FIELD_LABELS),
                "metadata": {
                    "source_type": "scenario",
                    "source_id": scenario.context_id,
                    "tier": "",
                },
            }
        )

    return documents


def _format_document(
    source_label: str,
    fields: dict[str, Any],
    field_labels: dict[str, str],
) -> str:
    parts = [source_label]
    for field_name, value in fields.items():
        label = field_labels.get(field_name, field_name)
        parts.append(f"{label}: {_format_value(value)}")
    return "\n".join(parts)


def _format_value(value: Any) -> str:
    if isinstance(value, list):
        return "; ".join(str(item) for item in value)
    return str(value)


_RESOURCE_FIELD_LABELS = {
    "resource_id": "자원 ID",
    "resource_name": "자원명",
    "resource_type": "자원 유형",
    "acquisition_method": "획득 방법",
    "usage": "사용처",
}

_RECIPE_FIELD_LABELS = {
    "recipe_id": "레시피 ID",
    "recipe_name": "레시피명",
    "input_resources": "입력 자원",
    "output_resources": "출력 자원",
    "tier": "진행 티어",
    "quest_tags": "퀘스트 태그",
    "llm_prompt_hint": "LLM 설명 힌트",
}

_SCENARIO_FIELD_LABELS = {
    "context_id": "시나리오 ID",
    "arc": "스토리 구간",
    "theme": "테마",
    "summary": "요약",
    "quest_usage": "퀘스트 사용처",
    "related_resources": "관련 자원",
    "related_recipes": "관련 레시피",
    "related_quest_types": "관련 퀘스트 유형",
    "llm_prompt_hint": "LLM 프롬프트 힌트",
    "source_section": "출처",
}
