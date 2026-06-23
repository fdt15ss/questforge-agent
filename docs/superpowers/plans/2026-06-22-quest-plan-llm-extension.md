# Quest Plan LLM Extension Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `quest_text_updates` 호환을 유지하면서 LLM이 `quest_plan`으로 퀘스트 의도, 우선순위, 도메인 믹스, 제목/설명 개선안을 제안할 수 있게 만든다.

**Architecture:** 서버는 기존처럼 deterministic draft `QuestResponse`를 먼저 만든다. LLM은 `quest_plan`을 반환해 draft quest id별로 `domain`, `target_item_id`, `intent`, `reason`, `title`, `description`, `main_quest_link_reason`을 제안하고, runtime은 허용된 범위 안에서만 draft에 병합한다. 수량, 보상, 완료 조건, 최종 quest 개수는 계속 서버가 소유한다.

**Tech Stack:** Python, Pydantic v2, LangGraph, pytest, existing `AgentPipeline`, existing `QuestResponse` schema.

---

## 설계 요약

현재 구조는 LLM이 `quest_text_updates`만 반환해 제목/설명만 다듬는다. 이 계획은 LLM 출력 형식을 다음처럼 확장한다.

```json
{
  "quest_plan": {
    "analysis": "현재 메인 퀘스트 부족분과 최근 이벤트를 보면 철괴와 구리괴 확보가 우선이다.",
    "domain_mix": {
      "production": 3,
      "delivery": 2
    },
    "quest_intents": [
      {
        "id": 1,
        "domain": "production",
        "target_item_id": "resource_iron_ingot",
        "intent": "main_quest_deficit",
        "reason": "메인 퀘스트의 철괴 부족분을 먼저 보충한다.",
        "title": "철괴 생산 안정화",
        "description": "기초 생산 라인 복구를 위해 철괴 생산을 안정적으로 확보하세요.",
        "main_quest_link_reason": "메인 퀘스트의 철괴 부족분을 직접 보충합니다."
      }
    ]
  }
}
```

중요한 제한은 다음과 같다.

- LLM이 `quantity`, `rewards`, `clear_condition`을 반환해도 병합하지 않는다.
- `id`는 draft quest id와 일치해야 한다.
- `domain`은 draft quest의 domain과 같아야 한다. 2번 구현안에서는 LLM이 draft quest를 재배열하지 않는다.
- `target_item_id`는 해당 draft quest의 첫 objective target과 같아야 한다. 목표 교체는 다음 단계 기능으로 미룬다.
- `analysis`, `intent`, `reason`은 portfolio 설명과 metadata/debug 용도로 보존한다.
- 잘못된 `quest_plan`이면 기존 fallback 경로로 이동한다.
- 기존 `quest_text_updates` 응답은 계속 정상 병합한다.

## 파일 구조

- Modify: `backend/src/agents/quest_generator/schemas.py`
  - `QuestPlan`, `QuestPlanIntent`, `QuestPlanDomainMix` Pydantic 모델을 추가한다.
- Modify: `backend/src/agents/pipeline/runtime.py`
  - `quest_plan` payload 감지, 검증, draft 병합 함수를 추가한다.
  - 기존 `_merge_quest_text_updates`는 유지한다.
  - LLM 응답 처리 순서를 `quest_plan` 먼저, 그 다음 `quest_text_updates`, 그 다음 full `QuestResponse` 검증으로 정리한다.
- Modify: `backend/src/agents/quest_generator/agent.py`
  - 상위 `quest_generator` prompt를 `quest_plan` 출력 계약으로 변경한다.
  - `DRAFT_QUESTS`와 `REQUEST_PAYLOAD`를 보고 분석과 의도를 제안하라고 지시한다.
- Modify: `backend/src/agents/quest_generator/production_quest.py`
  - leaf prompt는 당장 `quest_text_updates`를 유지한다. 단, 문서 주석에 상위 generator가 `quest_plan`을 담당한다고 명확히 한다.
- Modify: `backend/src/agents/quest_generator/delivery_quest.py`
  - leaf prompt는 당장 `quest_text_updates`를 유지한다. 단, 문서 주석에 상위 generator가 `quest_plan`을 담당한다고 명확히 한다.
- Modify: `backend/tests/test_message_router.py`
  - pipeline이 `quest_plan`을 draft에 병합하는 테스트를 추가한다.
  - 잘못된 domain 또는 target item이 들어오면 fallback되는 테스트를 추가한다.
  - 기존 `quest_text_updates` 테스트가 계속 통과하는지 유지한다.
- Modify: `backend/tests/test_agent_contracts.py`
  - 상위 `quest_generator` prompt가 `quest_plan` 계약을 안내하는지 검증한다.
- Modify: `backend/tests/test_agent_leaf_behaviors.py`
  - leaf prompt가 계속 `quest_text_updates` 계약을 유지하는지 검증한다.
- Modify: `docs/agent-request-structure.md`
  - LLM 출력 계약 섹션에 `quest_plan`과 `quest_text_updates`의 역할 차이를 기록한다.

---

### Task 1: Quest Plan Schema 추가

**Files:**
- Modify: `backend/src/agents/quest_generator/schemas.py`
- Test: `backend/tests/test_quest_agent_service.py`

- [ ] **Step 1: Write the failing schema tests**

Add these tests near the existing schema validation tests in `backend/tests/test_quest_agent_service.py`.

```python
def test_quest_plan_schema_accepts_llm_planning_fields() -> None:
    from agents.quest_generator.schemas import QuestPlanEnvelope

    plan = QuestPlanEnvelope.model_validate(
        {
            "quest_plan": {
                "analysis": "철괴와 구리괴 부족분이 초반 병목이다.",
                "domain_mix": {"production": 3, "delivery": 2},
                "quest_intents": [
                    {
                        "id": 1,
                        "domain": "production",
                        "target_item_id": "resource_iron_ingot",
                        "intent": "main_quest_deficit",
                        "reason": "메인 퀘스트 부족분을 보충한다.",
                        "title": "철괴 생산 안정화",
                        "description": "철괴 생산을 안정화해 다음 설비 제작을 준비하세요.",
                        "main_quest_link_reason": "메인 퀘스트의 철괴 부족분을 직접 보충합니다.",
                    }
                ],
            }
        }
    )

    assert plan.quest_plan.domain_mix.production == 3
    assert plan.quest_plan.domain_mix.delivery == 2
    assert plan.quest_plan.quest_intents[0].intent == "main_quest_deficit"


def test_quest_plan_schema_rejects_unknown_domain() -> None:
    from pydantic import ValidationError
    from agents.quest_generator.schemas import QuestPlanEnvelope

    try:
        QuestPlanEnvelope.model_validate(
            {
                "quest_plan": {
                    "analysis": "invalid domain",
                    "domain_mix": {"production": 1, "delivery": 0},
                    "quest_intents": [
                        {
                            "id": 1,
                            "domain": "exploration",
                            "target_item_id": "resource_iron_ingot",
                            "intent": "bad_domain",
                            "reason": "domain is not allowed",
                        }
                    ],
                }
            }
        )
    except ValidationError as exc:
        assert "domain" in str(exc)
    else:
        raise AssertionError("Expected ValidationError")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_quest_agent_service.py::test_quest_plan_schema_accepts_llm_planning_fields backend/tests/test_quest_agent_service.py::test_quest_plan_schema_rejects_unknown_domain -q
```

Expected: both tests fail because `QuestPlanEnvelope` does not exist.

- [ ] **Step 3: Add Pydantic models**

Add these models after `QuestResponse` in `backend/src/agents/quest_generator/schemas.py`.

```python
class QuestPlanDomainMix(BaseModel):
    """LLM이 요청 상황에 맞는 도메인 비율을 설명하기 위한 계획 필드입니다."""

    production: int = Field(ge=0)
    delivery: int = Field(ge=0)


class QuestPlanIntent(BaseModel):
    """LLM이 draft quest 하나에 부여하는 기획 의도입니다."""

    id: int = Field(gt=0)
    domain: Literal["production", "delivery"]
    target_item_id: str = Field(min_length=1)
    intent: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    title: str | None = Field(default=None, min_length=1)
    description: str | None = Field(default=None, min_length=1)
    main_quest_link_reason: str | None = Field(default=None, min_length=1)


class QuestPlan(BaseModel):
    """LLM이 서버 draft 위에 얹는 퀘스트 기획안입니다."""

    analysis: str = Field(min_length=1)
    domain_mix: QuestPlanDomainMix
    quest_intents: list[QuestPlanIntent] = Field(min_length=1)


class QuestPlanEnvelope(BaseModel):
    """LLM `quest_plan` 응답 envelope입니다."""

    quest_plan: QuestPlan
```

- [ ] **Step 4: Run the schema tests again**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_quest_agent_service.py::test_quest_plan_schema_accepts_llm_planning_fields backend/tests/test_quest_agent_service.py::test_quest_plan_schema_rejects_unknown_domain -q
```

Expected: `2 passed`.

- [ ] **Step 5: Commit**

```powershell
git add backend/src/agents/quest_generator/schemas.py backend/tests/test_quest_agent_service.py
git commit -m "feat: add quest plan schema"
```

---

### Task 2: Runtime에서 Quest Plan 병합 추가

**Files:**
- Modify: `backend/src/agents/pipeline/runtime.py`
- Test: `backend/tests/test_message_router.py`

- [ ] **Step 1: Write the failing merge test**

Add this test after `test_pipeline_merges_quest_text_updates_into_draft_response` in `backend/tests/test_message_router.py`.

```python
def test_pipeline_merges_quest_plan_into_draft_response() -> None:
    quest_plan_response = json.dumps(
        {
            "quest_plan": {
                "analysis": "철괴 부족분과 납품 루틴을 함께 정리해야 한다.",
                "domain_mix": {"production": 1, "delivery": 1},
                "quest_intents": [
                    {
                        "id": 1,
                        "domain": "production",
                        "target_item_id": "resource_iron_ingot",
                        "intent": "main_quest_deficit",
                        "reason": "메인 퀘스트의 철괴 부족분을 먼저 해결한다.",
                        "title": "철괴 생산 안정화",
                        "description": "철괴 생산을 안정화해 기초 생산 라인 복구를 앞당기세요.",
                        "main_quest_link_reason": "철괴 부족분을 직접 보충합니다.",
                    }
                ],
            }
        },
        ensure_ascii=False,
    )
    llm = StubLLMAdapter([json.dumps({"agent": "quest_generator"}), quest_plan_response])
    pipeline = AgentPipeline(llm_adapter=llm, cache=ResponseCache(enabled=False))

    response = pipeline.run(
        {
            "type": "agent.request",
            "request_id": "quest-plan-merge",
            "session_id": "test-session",
            "client_id": "test-client",
            "agent": "quest_generator",
            "payload": {
                "quest_generation_options": {
                    "count": 2,
                    "domain_counts": {"production": 1, "delivery": 1},
                },
                "current_main_quest": {
                    "id": "main_basic",
                    "title": "기초 생산 복구",
                    "objectives": [
                        {
                            "target_item_id": "resource_iron_ingot",
                            "required_quantity": 20,
                            "current_quantity": 6,
                        }
                    ],
                },
                "game_state": {
                    "inventory": {
                        "resource_iron_ore": 18,
                        "resource_iron_ingot": 6,
                    }
                },
            },
        }
    )

    assert response["type"] == "agent.response"
    quests = response["payload"]["quests"]
    assert len(quests) == 2
    assert quests[0]["title"] == "철괴 생산 안정화"
    assert quests[0]["metadata"]["llm_intent"] == "main_quest_deficit"
    assert quests[0]["metadata"]["llm_reason"] == "메인 퀘스트의 철괴 부족분을 먼저 해결한다."
    assert quests[0]["objectives"][0]["target_item_id"] == "resource_iron_ingot"
    assert "rewards" in quests[0]
    assert response["payload"]["metadata"]["quest_plan_analysis"] == "철괴 부족분과 납품 루틴을 함께 정리해야 한다."
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_message_router.py::test_pipeline_merges_quest_plan_into_draft_response -q
```

Expected: fail because `quest_plan` is not recognized or `metadata` is not present.

- [ ] **Step 3: Add quest metadata support to schema**

Modify `Quest` and `QuestResponse` in `backend/src/agents/quest_generator/schemas.py`.

```python
class Quest(BaseModel):
    ...
    main_quest_link: MainQuestLink | None = None
    metadata: dict[str, str] | None = None


class QuestResponse(BaseModel):
    ...
    quests: list[Quest] = Field(min_length=1)
    metadata: dict[str, str] | None = None
```

This metadata is intentionally string-only so LLM planning notes cannot smuggle nested game state into the client contract.

- [ ] **Step 4: Add quest plan helper functions**

Modify imports in `backend/src/agents/pipeline/runtime.py`.

```python
from agents.quest_generator.schemas import QuestPlanEnvelope, QuestResponse
```

Add these helpers near `_is_quest_text_update_payload`.

```python
def _is_quest_plan_payload(payload: dict[str, Any]) -> bool:
    return isinstance(payload.get("quest_plan"), dict)


def _merge_quest_plan(
    *,
    llm_payload: dict[str, Any],
    draft_payload: dict[str, Any],
) -> dict[str, Any]:
    plan = QuestPlanEnvelope.model_validate(llm_payload).quest_plan
    response = QuestResponse.model_validate(draft_payload)
    merged_payload = response.model_dump(mode="json")
    quests_by_id = {
        quest["id"]: quest
        for quest in merged_payload["quests"]
        if isinstance(quest.get("id"), int)
    }

    domain_total = plan.domain_mix.production + plan.domain_mix.delivery
    if domain_total != len(merged_payload["quests"]):
        raise ValueError("quest_plan domain_mix must match draft quest count")

    for intent in plan.quest_intents:
        quest = quests_by_id.get(intent.id)
        if quest is None:
            raise ValueError("quest_plan intent id must match a draft quest")
        if quest.get("domain") != intent.domain:
            raise ValueError("quest_plan intent domain must match draft quest")
        objectives = quest.get("objectives")
        if not isinstance(objectives, list) or not objectives:
            raise ValueError("draft quest must include objectives")
        first_objective = objectives[0]
        if not isinstance(first_objective, dict):
            raise ValueError("draft quest objective must be an object")
        if first_objective.get("target_item_id") != intent.target_item_id:
            raise ValueError("quest_plan target_item_id must match draft quest")

        if intent.title:
            quest["title"] = intent.title.strip()
        if intent.description:
            quest["description"] = intent.description.strip()

        metadata = quest.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
            quest["metadata"] = metadata
        metadata["llm_intent"] = intent.intent.strip()
        metadata["llm_reason"] = intent.reason.strip()

        main_quest_link = quest.get("main_quest_link")
        if (
            intent.main_quest_link_reason
            and isinstance(main_quest_link, dict)
        ):
            main_quest_link["reason"] = intent.main_quest_link_reason.strip()

    response_metadata = merged_payload.get("metadata")
    if not isinstance(response_metadata, dict):
        response_metadata = {}
        merged_payload["metadata"] = response_metadata
    response_metadata["quest_plan_analysis"] = plan.analysis.strip()
    response_metadata["quest_plan_domain_mix"] = (
        f"production:{plan.domain_mix.production},delivery:{plan.domain_mix.delivery}"
    )

    return QuestResponse.model_validate(merged_payload).model_dump(mode="json")
```

- [ ] **Step 5: Wire quest_plan into LLM response handling**

In `AgentPipeline` LLM response handling, replace:

```python
if _is_quest_text_update_payload(payload):
    draft = agent.fallback(state["typedPayload"], state["context"])
    payload = _merge_quest_text_updates(
        llm_payload=payload,
        draft_payload=draft.payload,
    )
```

with:

```python
if _is_quest_plan_payload(payload):
    draft = agent.fallback(state["typedPayload"], state["context"])
    payload = _merge_quest_plan(
        llm_payload=payload,
        draft_payload=draft.payload,
    )
elif _is_quest_text_update_payload(payload):
    draft = agent.fallback(state["typedPayload"], state["context"])
    payload = _merge_quest_text_updates(
        llm_payload=payload,
        draft_payload=draft.payload,
    )
```

- [ ] **Step 6: Run the merge test**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_message_router.py::test_pipeline_merges_quest_plan_into_draft_response -q
```

Expected: `1 passed`.

- [ ] **Step 7: Commit**

```powershell
git add backend/src/agents/quest_generator/schemas.py backend/src/agents/pipeline/runtime.py backend/tests/test_message_router.py
git commit -m "feat: merge quest plan llm output"
```

---

### Task 3: Quest Plan 검증 실패 시 fallback 유지

**Files:**
- Modify: `backend/tests/test_message_router.py`
- Confirm: `backend/src/agents/pipeline/runtime.py`

- [ ] **Step 1: Write invalid domain fallback test**

Add this test in `backend/tests/test_message_router.py` near the quest plan merge test.

```python
def test_pipeline_falls_back_when_quest_plan_domain_mismatches_draft() -> None:
    invalid_plan_response = json.dumps(
        {
            "quest_plan": {
                "analysis": "도메인을 잘못 제안한다.",
                "domain_mix": {"production": 1, "delivery": 0},
                "quest_intents": [
                    {
                        "id": 1,
                        "domain": "delivery",
                        "target_item_id": "resource_iron_ingot",
                        "intent": "bad_domain",
                        "reason": "draft와 다른 도메인이다.",
                    }
                ],
            }
        },
        ensure_ascii=False,
    )
    llm = StubLLMAdapter([json.dumps({"agent": "quest_generator"}), invalid_plan_response])
    pipeline = AgentPipeline(llm_adapter=llm, cache=ResponseCache(enabled=False))

    response = pipeline.run(
        {
            "type": "agent.request",
            "request_id": "quest-plan-invalid-domain",
            "session_id": "test-session",
            "client_id": "test-client",
            "agent": "quest_generator",
            "payload": {
                "quest_generation_options": {
                    "count": 1,
                    "domain_counts": {"production": 1},
                },
                "game_state": {
                    "inventory": {
                        "resource_iron_ingot": 6,
                    }
                },
            },
        }
    )

    assert response["type"] == "agent.response"
    assert response["metadata"]["fallback"] is True
    assert response["metadata"]["fallbackReason"] == "invalid_llm_response"
    assert response["payload"]["quests"][0]["domain"] == "production"
```

- [ ] **Step 2: Write invalid target fallback test**

Add this test after the invalid domain test.

```python
def test_pipeline_falls_back_when_quest_plan_target_mismatches_draft() -> None:
    invalid_plan_response = json.dumps(
        {
            "quest_plan": {
                "analysis": "목표 아이템을 잘못 제안한다.",
                "domain_mix": {"production": 1, "delivery": 0},
                "quest_intents": [
                    {
                        "id": 1,
                        "domain": "production",
                        "target_item_id": "resource_titanium_ore",
                        "intent": "bad_target",
                        "reason": "draft 목표와 다른 target이다.",
                    }
                ],
            }
        },
        ensure_ascii=False,
    )
    llm = StubLLMAdapter([json.dumps({"agent": "quest_generator"}), invalid_plan_response])
    pipeline = AgentPipeline(llm_adapter=llm, cache=ResponseCache(enabled=False))

    response = pipeline.run(
        {
            "type": "agent.request",
            "request_id": "quest-plan-invalid-target",
            "session_id": "test-session",
            "client_id": "test-client",
            "agent": "quest_generator",
            "payload": {
                "quest_generation_options": {
                    "count": 1,
                    "domain_counts": {"production": 1},
                },
                "game_state": {
                    "inventory": {
                        "resource_iron_ingot": 6,
                    }
                },
            },
        }
    )

    assert response["type"] == "agent.response"
    assert response["metadata"]["fallback"] is True
    assert response["metadata"]["fallbackReason"] == "invalid_llm_response"
    assert response["payload"]["quests"][0]["objectives"][0]["target_item_id"] == "resource_iron_ingot"
```

- [ ] **Step 3: Run invalid plan tests**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_message_router.py::test_pipeline_falls_back_when_quest_plan_domain_mismatches_draft backend/tests/test_message_router.py::test_pipeline_falls_back_when_quest_plan_target_mismatches_draft -q
```

Expected: `2 passed`. If either test returns `agent.error`, inspect `AgentPipeline` fallback handling around the `invalid_llm_response` path and ensure `_merge_quest_plan` exceptions are caught by the existing LLM validation exception handling.

- [ ] **Step 4: Commit**

```powershell
git add backend/tests/test_message_router.py backend/src/agents/pipeline/runtime.py
git commit -m "test: cover invalid quest plan fallback"
```

---

### Task 4: 상위 QuestGenerator Prompt를 quest_plan으로 변경

**Files:**
- Modify: `backend/src/agents/quest_generator/agent.py`
- Modify: `backend/tests/test_agent_contracts.py`
- Modify: `backend/tests/test_message_router.py`

- [ ] **Step 1: Update prompt contract tests**

In `backend/tests/test_agent_contracts.py`, update the assertion for `QuestGeneratorAgent().build_prompt(...)` so it expects `quest_plan` and no full `quests` contract.

```python
def test_quest_generator_prompt_requests_quest_plan_contract() -> None:
    agent = QuestGeneratorAgent()
    context = AgentContext(
        request_id="request-contract",
        session_id="session-contract",
        client_id="client-contract",
    )

    prompt = agent.build_prompt(
        {
            "quest_generation_options": {
                "count": 2,
                "domain_counts": {"production": 1, "delivery": 1},
            },
            "game_state": {
                "inventory": {
                    "resource_iron_ingot": 6,
                }
            },
        },
        context,
    )

    assert "quest_plan" in prompt
    assert "quest_intents" in prompt
    assert "domain_mix" in prompt
    assert "Do not return quests, objectives, clear_condition, rewards" in prompt
    assert '"quest_text_updates"' not in prompt
```

If a similarly named prompt contract test already exists, update that test instead of adding a duplicate.

- [ ] **Step 2: Update router prompt smoke assertion**

In `backend/tests/test_message_router.py`, update the existing prompt assertion near the top-level quest generator test.

Replace:

```python
assert "quest_text_updates" in llm.prompts[1]
```

with:

```python
assert "quest_plan" in llm.prompts[1]
assert "quest_intents" in llm.prompts[1]
```

- [ ] **Step 3: Update `QuestGeneratorAgent.build_prompt`**

Replace the `[TASK]` and `[OUTPUT_CONTRACT]` text in `backend/src/agents/quest_generator/agent.py` with this contract.

```python
"[TASK]\n"
f"Return exactly {quest_count} quest planning intents as one JSON object. "
"Use the QuestPlan schema. Analyze REQUEST_PAYLOAD and DRAFT_QUESTS, then decide "
"why each draft quest is useful right now. Each quest_intents item must reference "
"a draft quest id and must keep that draft quest's domain and target_item_id. "
"Do not return quests, objectives, clear_condition, rewards, quantity, metadata, "
"markdown, or explanations outside JSON. "
"The server will preserve quantity, rewards, clear_condition, and final quest count. "
"You may improve title, description, and main_quest_link_reason. "
"The analysis, reason, title, and description MUST be written in Korean.\n\n"
```

Use this output contract.

```python
"[OUTPUT_CONTRACT]\n"
"Return only one JSON object with this shape:\n"
'{"quest_plan":{"analysis":"...","domain_mix":{"production":3,"delivery":2},"quest_intents":[{"id":1,"domain":"production","target_item_id":"resource_iron_ingot","intent":"main_quest_deficit","reason":"...","title":"...","description":"...","main_quest_link_reason":"..."}]}}\n'
"Do not include quest_text_updates, quests, objectives, clear_condition, rewards, metadata, markdown, or explanations.\n"
```

- [ ] **Step 4: Run prompt tests**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_agent_contracts.py backend/tests/test_message_router.py::test_agent_request_routes_through_quest_generator -q
```

Expected: tests pass. If the router test name differs, run `backend\.venv\Scripts\python.exe -m pytest backend/tests/test_message_router.py -q` and update the assertion in the failing test.

- [ ] **Step 5: Commit**

```powershell
git add backend/src/agents/quest_generator/agent.py backend/tests/test_agent_contracts.py backend/tests/test_message_router.py
git commit -m "feat: request quest plan from generator llm"
```

---

### Task 5: Leaf Agent 호환 계약 고정

**Files:**
- Modify: `backend/src/agents/quest_generator/production_quest.py`
- Modify: `backend/src/agents/quest_generator/delivery_quest.py`
- Modify: `backend/tests/test_agent_leaf_behaviors.py`

- [ ] **Step 1: Update leaf prompt comments only**

In `backend/src/agents/quest_generator/production_quest.py`, update the `build_prompt` docstring to clarify that leaf agents remain text-update focused.

```python
"""LLM에게 보낼 prompt를 만듭니다.

상위 `quest_generator`는 `quest_plan`으로 기획 의도를 받습니다.
leaf agent는 특정 도메인 draft가 이미 확정된 뒤 실행되므로 기존처럼
`quest_text_updates`만 받아 제목/설명 품질을 보강합니다.
"""
```

In `backend/src/agents/quest_generator/delivery_quest.py`, update the `build_prompt` docstring with the same policy.

```python
"""납품 퀘스트 JSON 하나를 만들도록 LLM에 전달할 프롬프트를 반환합니다.

상위 `quest_generator`는 `quest_plan`으로 기획 의도를 받습니다.
leaf agent는 특정 도메인 draft가 이미 확정된 뒤 실행되므로 기존처럼
`quest_text_updates`만 받아 제목/설명 품질을 보강합니다.
"""
```

- [ ] **Step 2: Strengthen leaf behavior test**

In `backend/tests/test_agent_leaf_behaviors.py`, keep the existing `QuestTextUpdate schema` assertions and add:

```python
assert "quest_text_updates" in prompt
assert "quest_plan" not in prompt
```

Apply this to production and delivery prompt tests where each leaf prompt is inspected.

- [ ] **Step 3: Run leaf behavior tests**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_agent_leaf_behaviors.py -q
```

Expected: all tests pass.

- [ ] **Step 4: Commit**

```powershell
git add backend/src/agents/quest_generator/production_quest.py backend/src/agents/quest_generator/delivery_quest.py backend/tests/test_agent_leaf_behaviors.py
git commit -m "docs: clarify leaf quest text update contract"
```

---

### Task 6: Request 구조 문서 업데이트

**Files:**
- Modify: `docs/agent-request-structure.md`

- [ ] **Step 1: Add LLM output contract section**

Add this section after the current request example section in `docs/agent-request-structure.md`.

````markdown
## LLM 출력 계약

최종 클라이언트 응답은 항상 서버가 검증한 `QuestResponse`입니다. LLM 응답은 클라이언트로 직접 전달되지 않고, 서버 draft에 병합됩니다.

### 상위 quest_generator

상위 `quest_generator`는 `quest_plan`을 요청합니다.

```json
{
  "quest_plan": {
    "analysis": "현재 게임 상태 분석",
    "domain_mix": {
      "production": 3,
      "delivery": 2
    },
    "quest_intents": [
      {
        "id": 1,
        "domain": "production",
        "target_item_id": "resource_iron_ingot",
        "intent": "main_quest_deficit",
        "reason": "왜 이 퀘스트가 지금 필요한지",
        "title": "퀘스트 제목",
        "description": "퀘스트 설명",
        "main_quest_link_reason": "메인 퀘스트와 연결되는 이유"
      }
    ]
  }
}
```

서버는 `quest_plan`에서 `title`, `description`, `main_quest_link_reason`, `intent`, `reason`, `analysis`만 반영합니다. 수량, 보상, 완료 조건은 서버가 기존 draft와 CSV 규칙으로 유지합니다.

### leaf agent

`production_quest`, `delivery_quest` leaf agent는 기존 `quest_text_updates`를 유지합니다.

```json
{
  "quest_text_updates": [
    {
      "id": 1,
      "title": "퀘스트 제목",
      "description": "퀘스트 설명",
      "main_quest_link_reason": "메인 퀘스트 연결 사유"
    }
  ]
}
```

이 호환 경로는 로컬 LLM이 `quest_plan`을 안정적으로 만들지 못하는 경우에도 기존 안전장치를 유지하기 위한 것입니다.
```
````

- [ ] **Step 2: Run markdown sanity check**

Run:

```powershell
rg "quest_plan|quest_text_updates|LLM 출력 계약" docs/agent-request-structure.md -n
```

Expected: the new section appears and both output shapes are documented.

- [ ] **Step 3: Commit**

```powershell
git add docs/agent-request-structure.md
git commit -m "docs: document quest plan llm contract"
```

---

### Task 7: 전체 검증과 OpenAI smoke

**Files:**
- Confirm: all modified files

- [ ] **Step 1: Run focused tests**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_message_router.py backend/tests/test_agent_contracts.py backend/tests/test_agent_leaf_behaviors.py backend/tests/test_quest_agent_service.py -q
```

Expected: all tests pass.

- [ ] **Step 2: Run full backend tests**

Run from `backend`:

```powershell
uv run --extra dev python -m pytest tests -q
```

Expected: all backend tests pass.

- [ ] **Step 3: Run OpenAI quest_plan smoke**

Run from `backend` with `.env.prod.openai`.

```powershell
uv run --env-file .env.prod.openai python -c "import json; from agents.pipeline.runtime import AgentPipeline; p=AgentPipeline(); r=p.run({'type':'agent.request','request_id':'quest-plan-smoke','session_id':'smoke-session','client_id':'smoke-client','agent':'quest_generator','payload':{'quest_generation_options':{'count':2,'domain_counts':{'production':1,'delivery':1}},'progression':{'stage':'early_factory','player_level':3},'current_main_quest':{'id':'main_basic','title':'기초 생산 라인 복구','objectives':[{'target_item_id':'resource_iron_ingot','required_quantity':20,'current_quantity':6}]},'game_state':{'inventory':{'resource_iron_ore':18,'resource_iron_ingot':6}}}}); print(json.dumps({'type':r.get('type'),'count':len(r.get('payload',{}).get('quests',[])),'fallback':r.get('metadata',{}).get('fallback'),'provider':r.get('metadata',{}).get('llmProvider'),'has_plan_analysis':'quest_plan_analysis' in r.get('payload',{}).get('metadata',{})}, ensure_ascii=False))"
```

Expected:

```json
{"type":"agent.response","count":2,"fallback":null,"provider":"openai","has_plan_analysis":true}
```

If `fallback` is `true`, inspect `metadata.llmAttempts[0].rawPreview` and adjust prompt wording without relaxing runtime validation.

- [ ] **Step 4: Run local LLM fallback smoke**

Run the same command with the local server environment used for `run_server.py`.

Expected outcomes:

- If local LLM returns valid `quest_plan`, response includes `payload.metadata.quest_plan_analysis`.
- If local LLM returns invalid schema, response is still `agent.response` with `metadata.fallback == true`.
- It must not return `agent.error` for invalid LLM shape.

- [ ] **Step 5: Final diff check**

Run:

```powershell
git diff --check
git status -sb
```

Expected: no whitespace errors. Status should show only files changed by this plan.

- [ ] **Step 6: Final commit**

```powershell
git add backend/src/agents/quest_generator/schemas.py backend/src/agents/pipeline/runtime.py backend/src/agents/quest_generator/agent.py backend/src/agents/quest_generator/production_quest.py backend/src/agents/quest_generator/delivery_quest.py backend/tests/test_message_router.py backend/tests/test_agent_contracts.py backend/tests/test_agent_leaf_behaviors.py backend/tests/test_quest_agent_service.py docs/agent-request-structure.md
git commit -m "feat: support llm quest planning contract"
```

## Self-Review

- Spec coverage: `quest_plan` 추가 지원, 기존 `quest_text_updates` 호환 유지, 서버 검증 및 fallback, 문서화, OpenAI/local smoke가 모두 Task 1-7에 포함되어 있다.
- Placeholder scan: 실행자가 채워야 하는 빈 항목 없이 테스트 코드, 구현 코드, 실행 명령, 예상 결과를 명시했다.
- Type consistency: `QuestPlanEnvelope`, `QuestPlan`, `QuestPlanIntent`, `QuestPlanDomainMix`, `_is_quest_plan_payload`, `_merge_quest_plan` 이름을 전 task에서 동일하게 사용한다.
- Scope check: LLM이 목표를 재배열하거나 새 target으로 교체하는 기능은 이번 범위에서 제외하고, draft와 일치하는 계획 의도만 반영한다.
