# Local Compact Quest Prompt Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** local/e4b 모델에서 `quest_generator`의 LLM 입력을 짧게 만들어 `invalid_json` fallback 가능성을 낮춘다.

**Architecture:** OpenAI 등 원격 모델은 기존 rich prompt를 유지하고, default LLM provider가 `local`이면 compact prompt를 사용한다. Compact prompt는 서버가 이미 만든 draft quest, 현재 진행도, 메인 퀘스트 목표, 최근 이벤트, 압축된 RAG context만 포함하며 최종 출력 schema는 기존 `quest_plan` 계약을 유지한다.

**Tech Stack:** Python 3.12, LangGraph agent pipeline, Pydantic quest schemas, pytest, ruff

---

## 파일 구조

- Modify: `backend/src/agents/quest_generator/agent.py`
  - `QuestGeneratorAgent.build_prompt`에서 compact/rich prompt 분기
  - compact prompt 입력 요약 helper 추가
  - `QUESTFORGE_QUEST_PROMPT_MODE=compact|rich|auto` payload/env override 지원
- Test: `backend/tests/test_quest_agent_service.py`
  - local provider에서 compact prompt가 원본 payload 전체와 full RAG JSON을 생략하는지 검증
  - openai provider에서는 기존 rich prompt가 유지되는지 검증
- Create: `docs/superpowers/plans/2026-06-24-local-compact-quest-prompt.md`
  - 구현 계획과 검증 명령 기록

## Task 1: Compact Prompt 분기 테스트

**Files:**
- Modify: `backend/tests/test_quest_agent_service.py`

- [ ] **Step 1: Write the failing test**

`backend/tests/test_quest_agent_service.py`에 다음 테스트를 추가한다.

```python
def test_quest_generator_uses_compact_prompt_for_local_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QUESTFORGE_LLM_DEFAULT_PROVIDER", "local")
    monkeypatch.setenv("QUESTFORGE_LLM_DEFAULT_MODEL", "gemma4:e4b")
    monkeypatch.setenv("QUESTFORGE_LLM_DEFAULT_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.delenv("QUESTFORGE_QUEST_PROMPT_MODE", raising=False)

    prompt = QuestGeneratorAgent().build_prompt(
        {
            "quest_type": "daily",
            "quest_generation_options": {"count": 5},
            "current_main_quest": {
                "id": "main_expand_mid_factory",
                "title": "중급 자동화 생산망 확장",
                "description": "강철 기반 부품과 전자 부품 생산을 안정화한다.",
                "objectives": [
                    {
                        "target_item_id": "resource_steel_plate",
                        "required_quantity": 45,
                        "current_quantity": 18,
                    }
                ],
            },
            "game_state": {
                "inventory": {"resource_steel_plate": 18, "resource_copper_wire": 52},
                "unlocked_recipes": ["recipe_smelt_steel", "recipe_craft_electronic_circuit"],
            },
            "recent_events": ["전자 회로 수요가 늘어나면서 구리선 병목이 발생했다."],
        },
        AgentContext(request_id="compact-local"),
    )

    assert "[COMPACT_REQUEST]" in prompt
    assert "[REQUEST_PAYLOAD]" not in prompt
    assert "[COMPACT_GAME_CONTEXT]" in prompt
    assert '"game_state"' not in prompt
    assert '"unlocked_recipes"' not in prompt
    assert '"quest_plan"' in prompt
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
backend\.venv\Scripts\python.exe -m pytest backend\tests\test_quest_agent_service.py::test_quest_generator_uses_compact_prompt_for_local_provider -q
```

Expected: FAIL because current prompt always includes `[REQUEST_PAYLOAD]` and does not include `[COMPACT_REQUEST]`.

## Task 2: Compact Prompt 구현

**Files:**
- Modify: `backend/src/agents/quest_generator/agent.py`

- [ ] **Step 1: Add prompt mode helpers**

`agent.py`에 다음 helper를 추가한다.

```python
def _quest_prompt_mode(payload: dict[str, Any]) -> Literal["rich", "compact"]:
    options = payload.get("quest_generation_options")
    if isinstance(options, dict):
        override = options.get("prompt_mode")
        if override in {"rich", "compact"}:
            return override

    env_mode = os.getenv("QUESTFORGE_QUEST_PROMPT_MODE", "auto").strip().lower()
    if env_mode in {"rich", "compact"}:
        return cast(Literal["rich", "compact"], env_mode)

    settings = LLMSettings.from_env()
    return "compact" if settings.default.provider == "local" else "rich"
```

- [ ] **Step 2: Add compact request/context builders**

`agent.py`에 다음 helper를 추가한다.

```python
def _compact_request(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "quest_type": payload.get("quest_type", "daily"),
        "quest_generation_options": {
            "count": _safe_count(payload),
            "domain_counts": _compact_domain_counts(payload),
        },
        "progression": payload.get("progression", {}),
        "main_objectives": _compact_main_objectives(payload),
        "recent_events": _string_items(payload.get("recent_events"), limit=3),
    }
```

`_compact_game_context`는 `resources`, `recipes`, `scenario_contexts`, `reward_rules`, `semantic_matches`의 필드를 각각 3개 이하로 줄인다.

- [ ] **Step 3: Use compact prompt in `build_prompt`**

`build_prompt`에서 mode가 `compact`이면 `[COMPACT_REQUEST]`, `[COMPACT_GAME_CONTEXT]`만 포함한 prompt를 반환한다. 출력 계약은 기존 `quest_plan_contract`를 그대로 사용한다.

- [ ] **Step 4: Run focused test**

Run:

```bash
backend\.venv\Scripts\python.exe -m pytest backend\tests\test_quest_agent_service.py::test_quest_generator_uses_compact_prompt_for_local_provider -q
```

Expected: PASS.

## Task 3: Rich Prompt 유지 테스트

**Files:**
- Modify: `backend/tests/test_quest_agent_service.py`

- [ ] **Step 1: Write rich mode regression test**

```python
def test_quest_generator_keeps_rich_prompt_for_openai_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QUESTFORGE_LLM_DEFAULT_PROVIDER", "openai")
    monkeypatch.setenv("QUESTFORGE_LLM_DEFAULT_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.delenv("QUESTFORGE_QUEST_PROMPT_MODE", raising=False)

    prompt = QuestGeneratorAgent().build_prompt(
        {"quest_type": "daily", "quest_generation_options": {"count": 1}},
        AgentContext(request_id="rich-openai"),
    )

    assert "[REQUEST_PAYLOAD]" in prompt
    assert "[RETRIEVED_GAME_CONTEXT]" in prompt
    assert "[COMPACT_REQUEST]" not in prompt
```

- [ ] **Step 2: Run rich mode test**

Run:

```bash
backend\.venv\Scripts\python.exe -m pytest backend\tests\test_quest_agent_service.py::test_quest_generator_keeps_rich_prompt_for_openai_provider -q
```

Expected: PASS.

## Task 4: Verification

**Files:**
- Modify: `backend/src/agents/quest_generator/agent.py`
- Modify: `backend/tests/test_quest_agent_service.py`
- Create: `docs/superpowers/plans/2026-06-24-local-compact-quest-prompt.md`

- [ ] **Step 1: Run focused quest tests**

```bash
backend\.venv\Scripts\python.exe -m pytest backend\tests\test_quest_agent_service.py -q
```

Expected: all tests pass.

- [ ] **Step 2: Run routing/pipeline tests that inspect quest prompt**

```bash
backend\.venv\Scripts\python.exe -m pytest backend\tests\test_message_router.py::test_pipeline_includes_retrieved_game_context_in_quest_plan_prompt backend\tests\test_message_router.py::test_pipeline_merges_quest_plan_into_draft_response -q
```

Expected: both tests pass.

- [ ] **Step 3: Run ruff**

```bash
uv run --project backend --extra dev ruff check backend/src/agents/quest_generator/agent.py backend/tests/test_quest_agent_service.py
```

Expected: `All checks passed!`

- [ ] **Step 4: Commit**

```bash
git add backend/src/agents/quest_generator/agent.py backend/tests/test_quest_agent_service.py docs/superpowers/plans/2026-06-24-local-compact-quest-prompt.md
git commit -m "feat: add compact local quest prompt"
```
