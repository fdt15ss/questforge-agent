# Quest Description Context Variation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 생산 퀘스트 description 앞 문장이 CSV 로딩 순서대로 반복되는 문제를 줄이고, LLM이 퀘스트 서사를 더 적극적으로 재구성하도록 만든다.

**Architecture:** 서버는 안전한 퀘스트 구조, 목표 아이템, 수량, 완료 조건을 유지하고, 관련 CSV context를 deterministic하게 섞어서 draft를 만든다. LLM은 `title`, `description`, `main_quest_link.reason`의 표현을 재구성하되 게임 로직 필드는 바꾸지 않는다.

**Tech Stack:** Python, LangGraph, Pydantic, pytest

---

## 구현 원칙

- 새로 추가하거나 수정하는 코드 주석과 docstring은 한글로 작성한다.
- LLM이 실패해도 fallback 품질이 개선되어야 한다.
- 랜덤은 쓰지 않는다. 같은 입력은 같은 결과를 내야 테스트와 디버깅이 쉽다.
- LLM은 문장 표현을 바꾸는 역할을 맡고, `id`, `type`, `domain`, `objectives`, `clear_condition`, `main_quest_link`의 구조적 값은 서버가 보호한다.
- unrelated refactor는 하지 않는다. 변경 범위는 production quest draft 생성과 그 테스트에 한정한다.

## 파일 구조

- Modify: `backend/src/agents/quest_generator/production_quest.py`
  - `_context_summary()`를 관련 resource 우선 + deterministic offset 방식으로 변경한다.
  - `build_quests()`에서 `target_item_id`, `quest_type`, `AgentContext`를 `_context_summary()`에 전달한다.
  - `ProductionQuestAgent.build_prompt()`에 LLM description rewrite 지시를 강화한다.
- Modify: `backend/tests/test_quest_agent_service.py`
  - fallback description 앞 문장이 CSV 순서대로 고정되지 않는지 검증한다.
  - 관련 resource가 있는 context가 우선 선택되는지 검증한다.
- Modify: `backend/tests/test_agent_leaf_behaviors.py`
  - production quest prompt가 LLM에게 description 재구성을 지시하는지 검증한다.

---

### Task 1: CSV 순서 반복을 실패 테스트로 고정

**Files:**
- Modify: `backend/tests/test_quest_agent_service.py`

- [ ] **Step 1: 실패 테스트 추가**

`test_production_quest_fallback_does_not_use_contexts_in_plain_csv_order`를 추가한다.

```python
def test_production_quest_fallback_does_not_use_contexts_in_plain_csv_order() -> None:
    agent = ProductionQuestAgent()

    result = agent.fallback(
        {
            "quest_generation_options": {
                "count": 5,
            },
            "resources": {
                "resource_iron_ore": 12,
                "resource_copper_ore": 5,
            },
        },
        _context(),
    )

    descriptions = [
        quest.description
        for quest in QuestResponse.model_validate(result.payload).quests
    ]

    assert "N-13에 추락한 개척팀장이" not in descriptions[0]
    assert "탈출 포드 잔해에서" not in descriptions[1]
```

- [ ] **Step 2: 실패 확인**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_quest_agent_service.py::test_production_quest_fallback_does_not_use_contexts_in_plain_csv_order -q
```

Expected:

```text
FAILED ... assert ...
```

현재 구현은 `contexts[index % len(contexts)]`로 CSV 순서를 그대로 쓰기 때문에 실패해야 한다.

---

### Task 2: 관련 resource 우선 context 선택 구현

**Files:**
- Modify: `backend/src/agents/quest_generator/production_quest.py`

- [ ] **Step 1: `_context_summary()` 시그니처 변경**

기존:

```python
def _context_summary(
    contexts: list[ScenarioContextRow],
    index: int,
    resource_name: str,
) -> str:
```

변경:

```python
def _context_summary(
    contexts: list[ScenarioContextRow],
    *,
    index: int,
    resource_name: str,
    target_item_id: str,
    quest_type: str,
    context: AgentContext,
) -> str:
```

- [ ] **Step 2: 한글 docstring 작성**

```python
    """현재 퀘스트와 관련 있는 CSV context를 우선 고르고, 고정 offset으로 순서를 섞습니다."""
```

- [ ] **Step 3: 관련 context 후보 선택**

```python
    if not contexts:
        return f"현재 공장 목표를 위해 {resource_name}이(가) 필요합니다."

    candidates = [
        row
        for row in contexts
        if target_item_id in row.related_resources
    ] or contexts
```

- [ ] **Step 4: deterministic offset 적용**

```python
    seed = (
        f"{target_item_id}:"
        f"{quest_type}:"
        f"{context.session_id}:"
        f"{context.client_id}"
    )
    offset = sum(ord(char) for char in seed) % len(candidates)
    selected = candidates[(index + offset) % len(candidates)]
    return selected.summary
```

- [ ] **Step 5: 호출부 변경**

`build_quests()` 안의 호출을 변경한다.

```python
            context_summary = _context_summary(
                contexts,
                index=index,
                resource_name=resource_name,
                target_item_id=target_item_id,
                quest_type=quest_type,
                context=state["context"],
            )
```

- [ ] **Step 6: 테스트 통과 확인**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_quest_agent_service.py::test_production_quest_fallback_does_not_use_contexts_in_plain_csv_order -q
```

Expected:

```text
1 passed
```

---

### Task 3: 관련 resource 우선 선택 테스트 추가

**Files:**
- Modify: `backend/tests/test_quest_agent_service.py`

- [ ] **Step 1: 실패 테스트 추가**

`resource_scout_spaceship`처럼 CSV context와 강하게 연결된 resource를 넣고, description에 해당 resource 맥락이 반영되는지 확인한다.

```python
def test_production_quest_fallback_prefers_related_context_for_resource() -> None:
    agent = ProductionQuestAgent()

    result = agent.fallback(
        {
            "resources": {
                "resource_scout_spaceship": 1,
            },
            "recent_events": ["scout_spaceship_unlocked"],
        },
        _context(),
    )

    first_description = QuestResponse.model_validate(result.payload).quests[0].description
    assert "resource_scout_spaceship" in first_description
```

- [ ] **Step 2: 테스트 실행**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_quest_agent_service.py::test_production_quest_fallback_prefers_related_context_for_resource -q
```

Expected:

```text
1 passed
```

이미 유사 테스트가 있으면 새 테스트를 중복으로 만들지 말고 기존 테스트 이름과 assertion을 더 명확하게 조정한다.

---

### Task 4: LLM description rewrite 지시 강화

**Files:**
- Modify: `backend/src/agents/quest_generator/production_quest.py`
- Modify: `backend/tests/test_agent_leaf_behaviors.py`

- [ ] **Step 1: prompt 테스트 추가**

`test_production_quest_prompt_asks_llm_to_rewrite_descriptions`를 추가한다.

```python
def test_production_quest_prompt_asks_llm_to_rewrite_descriptions(
    context: AgentContext,
) -> None:
    agent = ProductionQuestAgent()

    prompt = agent.build_prompt(
        {
            "resources": {
                "resource_iron_ore": 12,
                "resource_copper_ore": 5,
            },
            "recent_events": ["first_factory_started"],
        },
        context,
    )

    assert "rewrite title and description" in prompt
    assert "Do not copy DRAFT_QUESTS descriptions verbatim" in prompt
    assert "Keep every quest id, type, domain" in prompt
    assert "objective target_item_id" in prompt
    assert "objective quantity" in prompt
```

- [ ] **Step 2: 실패 확인**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_agent_leaf_behaviors.py::test_production_quest_prompt_asks_llm_to_rewrite_descriptions -q
```

Expected:

```text
FAILED ... assert ...
```

- [ ] **Step 3: `ProductionQuestAgent.build_prompt()` 지시문 추가**

기존 구조 보존 문장 바로 뒤에 다음 지시를 추가한다.

```python
            "You SHOULD rewrite title and description instead of copying "
            "DRAFT_QUESTS descriptions verbatim. Use REQUEST_PAYLOAD, "
            "recent_events, game_state, and draft context as signals. "
            "Each description should open differently across quests. "
            "Do not preserve CSV context sentence order when it sounds repetitive. "
```

- [ ] **Step 4: 테스트 통과 확인**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_agent_leaf_behaviors.py::test_production_quest_prompt_asks_llm_to_rewrite_descriptions -q
```

Expected:

```text
1 passed
```

---

### Task 5: 회귀 테스트와 샘플 출력 확인

**Files:**
- No code changes

- [ ] **Step 1: production quest 테스트 실행**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_quest_agent_service.py backend/tests/test_agent_leaf_behaviors.py -q
```

Expected:

```text
passed
```

- [ ] **Step 2: 전체 backend 테스트 실행**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests -q
```

Expected:

```text
154 passed
```

테스트 수는 이후 테스트 추가에 따라 증가할 수 있다. 실패가 0개인지 확인한다.

- [ ] **Step 3: 샘플 fallback 출력 확인**

Run:

```powershell
backend\.venv\Scripts\python.exe -c "import sys; sys.path.insert(0, 'backend/src'); from agents.quest_generator.production_quest import ProductionQuestAgent; from agents.base import AgentContext; from agents.quest_generator.schemas import QuestResponse; ctx=AgentContext(request_id='r',session_id='session-a',client_id='client-a',metadata={}); result=ProductionQuestAgent().fallback({'resources': {'resource_iron_ore': 12, 'resource_copper_ore': 5}}, ctx); quests=QuestResponse.model_validate(result.payload).quests; [print(q.id, q.objectives[0].target_item_id, q.description) for q in quests]"
```

Expected:

```text
description 앞 문장이 CSV 첫 줄부터 순서대로 고정되어 보이지 않아야 한다.
```

---

## 완료 기준

- fallback description 앞 context가 CSV 로딩 순서대로만 나오지 않는다.
- 현재 quest의 `target_item_id`와 관련 있는 context가 우선 선택된다.
- LLM prompt가 description을 그대로 복사하지 말고 재구성하라고 명시한다.
- 게임 로직 필드인 `id`, `type`, `domain`, `objectives`, `clear_condition`은 계속 서버 draft를 유지한다.
- 새로 추가한 주석과 docstring은 한글이다.
- 전체 backend 테스트가 통과한다.

