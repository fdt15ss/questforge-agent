# LangGraph 기반 퀘스트 생성 구현 계획서

> **Agent 작업자 필수 지침:** 이 계획을 구현할 때는 `superpowers:subagent-driven-development` 또는 `superpowers:executing-plans`를 사용한다. 각 단계는 체크박스(`- [ ]`)로 추적한다.

**목표:** production quest 생성 방식을 고정 후보군 선택 방식에서 LangGraph 기반 직접 생성 방식으로 바꾼다. 기본적으로 퀘스트 5개를 생성하고, 요청 payload 값에 따라 생성 개수를 늘릴 수 있게 한다.

**아키텍처:** `ProductionQuestAgent` 내부에 작은 LangGraph를 둔다. 이 그래프는 payload 정규화, 퀘스트 개수 결정, `QuestDataRepository`를 통한 CSV 기반 structured context 조회, deterministic quest draft 생성, `QuestResponse` 검증을 담당한다. 기존처럼 LLM이 후보군 id를 고르는 방식은 제거하고, LLM은 서버가 만든 draft의 제목과 설명을 개선하는 역할만 맡는다.

**기술 스택:** Python 3.12, FastAPI, LangGraph, Pydantic, pytest, 기존 `backend/src/quest_data` CSV repository.

---

## 1. 변경 파일과 책임

- `backend/src/agents/quest_generator/production_quest.py`
  - production quest 생성용 LangGraph를 추가한다.
  - selection tool 의존성을 제거한다.
  - fallback도 같은 LangGraph 생성 흐름을 사용하게 한다.
  - 테스트를 위해 `describe_graph()`를 제공한다.

- `backend/src/agents/quest_generator/service.py`
  - `_EXAMPLE_QUESTS` 기반 production quest 결과 생성을 제거한다.
  - 필요하면 `ProductionQuestGenerationService`를 추가해 graph state를 `QuestResponse`로 바꾸는 책임을 둔다.
  - 기존 import 호환이 필요하면 `QuestAgentService`는 얇은 wrapper로만 남긴다.

- `backend/src/agents/pipeline/runtime.py`
  - production quest가 반드시 `quest_generator.select_production_quests` tool call을 성공해야 한다는 조건을 제거한다.
  - 일반 JSON 파싱과 response schema 검증은 유지한다.

- `backend/src/agents/quest_generator/tools.py`
  - production quest selection tool을 더 이상 agent에서 사용하지 않는다.
  - 참조가 완전히 없어지면 `ProductionQuestSelectionTool`을 삭제한다.

- `backend/tests/test_quest_agent_service.py`
  - `_EXAMPLE_QUESTS` id를 검증하던 테스트를 제거한다.
  - 기본 5개 생성, payload count override, schema 검증, payload resource 반영 테스트로 바꾼다.

- `backend/tests/test_agent_leaf_behaviors.py`
  - production agent가 LangGraph를 사용하는지 검증한다.
  - selection tool을 노출하지 않는지 검증한다.
  - prompt가 tool call이 아니라 직접 quest JSON 반환을 요구하는지 검증한다.

- `backend/tests/test_pipeline_edges.py` 또는 `backend/tests/test_agent_contracts.py`
  - production quest LLM 응답이 tool call 없이도 직접 valid quest JSON이면 accepted 되는지 검증한다.

- `README.md`, `docs/architecture-plan.md`
  - production quest가 고정 예시 후보군을 고르는 방식이라는 설명을 LangGraph + structured CSV context 기반 생성 방식으로 갱신한다.

---

## 2. 동작 계약

production quest 생성은 아래 규칙을 따른다.

- 기본 생성 개수는 정확히 `5개`다.
- `payload["quest_generation_options"]["count"]`가 정수면 이 값을 우선 사용한다.
- 위 값이 없고 `payload["quest_count"]`가 정수면 이 값을 사용한다.
- 허용 범위는 `1..10`이다.
- 범위를 벗어나거나 잘못된 값이면 기본값 `5`를 사용한다.
- 모든 결과는 `QuestResponse`로 검증되어야 한다.
- 모든 quest는 다음 필드를 가진다.
  - 양수 정수 `id`
  - `type == "production"`
  - 비어 있지 않은 `title`
  - 비어 있지 않은 `description`
  - 최소 1개 이상의 `objectives`
  - 각 objective는 `target_item_id`와 양수 `quantity`를 가진다.
- payload에 `resources`가 있으면 objective의 `target_item_id`는 가능한 한 이 resource id를 우선 사용한다.
- payload resource가 CSV에 없거나 매핑되지 않아도 실패하지 않고 CSV fallback context를 사용한다.

---

## 3. 작업 순서

### Task 1: 기존 후보군 선택 테스트를 생성 테스트로 교체

**파일**

- 수정: `backend/tests/test_quest_agent_service.py`
- 실행: `uv run --extra dev pytest tests/test_quest_agent_service.py -q`

- [ ] 기본 5개 생성 테스트를 먼저 작성한다.
- [ ] `quest_generation_options.count`가 있으면 해당 개수만큼 생성되는 테스트를 작성한다.
- [ ] `quest_count`가 있으면 해당 개수만큼 생성되는 테스트를 작성한다.
- [ ] 잘못된 count는 기본값 5로 돌아가는 테스트를 작성한다.
- [ ] 테스트를 실행해서 실패하는지 확인한다.

예상 실패 이유: 아직 production quest가 `_EXAMPLE_QUESTS` 기반 random sample을 사용하고, payload count를 반영하지 않는다.

---

### Task 2: `ProductionQuestAgent`에 LangGraph skeleton 추가

**파일**

- 수정: `backend/src/agents/quest_generator/production_quest.py`
- 수정: `backend/tests/test_agent_leaf_behaviors.py`
- 실행: `uv run --extra dev pytest tests/test_agent_leaf_behaviors.py -q`

- [ ] `describe_graph()`가 아래 node들을 포함하는지 검증하는 테스트를 작성한다.
  - `production.normalize_payload`
  - `production.retrieve_context`
  - `production.build_quests`
  - `production.validate_response`
- [ ] production agent가 selection tool을 노출하지 않는다는 테스트로 기존 tool 노출 테스트를 교체한다.
- [ ] 테스트를 실행해서 실패하는지 확인한다.
- [ ] `ProductionQuestGraphState`를 추가한다.
- [ ] `build_production_quest_graph()`를 추가한다.
- [ ] `ProductionQuestAgent.tools = ()`로 바꾼다.
- [ ] `ProductionQuestAgent.__init__()`에서 graph를 compile한다.
- [ ] `describe_graph()`를 추가한다.
- [ ] 테스트를 다시 실행해서 통과하는지 확인한다.

초기 graph는 최소 구현으로 시작한다. count는 일단 5, context는 빈 dict, quest는 skeleton 데이터로 만들어도 된다.

---

### Task 3: 퀘스트 개수 결정 로직 추가

**파일**

- 수정: `backend/src/agents/quest_generator/production_quest.py`
- 테스트: `backend/tests/test_quest_agent_service.py`

- [ ] count 관련 테스트가 실패하는지 먼저 확인한다.
- [ ] `DEFAULT_PRODUCTION_QUEST_COUNT = 5`를 추가한다.
- [ ] `MAX_PRODUCTION_QUEST_COUNT = 10`을 추가한다.
- [ ] `_resolve_quest_count(payload)` helper를 추가한다.
- [ ] `normalize_payload` node에서 `_resolve_quest_count()`를 호출하게 한다.
- [ ] count 관련 테스트를 다시 실행해 통과하는지 확인한다.

count 우선순위는 다음과 같다.

1. `quest_generation_options.count`
2. `quest_count`
3. 기본값 `5`

---

### Task 4: CSV 기반 structured context 조회 연결

**파일**

- 수정: `backend/src/agents/quest_generator/production_quest.py`
- 수정: `backend/tests/test_quest_agent_service.py`
- 사용: `backend/src/quest_data/repository.py`

- [ ] payload의 `resources`가 objective에 반영되는 테스트를 작성한다.
- [ ] 테스트를 실행해서 실패하는지 확인한다.
- [ ] `QuestDataRepository`를 import한다.
- [ ] `_payload_resource_ids(payload)` helper를 추가한다.
- [ ] `_fallback_resource_ids(repository)` helper를 추가한다.
- [ ] `retrieve_context` node에서 payload resource id를 추출한다.
- [ ] payload resource가 없으면 `scenario_context.csv` 기반 fallback resource id를 가져온다.
- [ ] `repository.find_scenario_contexts(...)`로 관련 scenario context를 조회한다.
- [ ] `build_quests` node가 retrieved resource id를 objective target으로 사용하게 한다.
- [ ] resource-aware 테스트를 다시 실행해 통과하는지 확인한다.

이 단계부터 `QuestDataRepository`가 실제 production quest 생성 흐름에 연결된다.

---

### Task 5: context 기반 title/description 생성

**파일**

- 수정: `backend/src/agents/quest_generator/production_quest.py`
- 수정: `backend/tests/test_quest_agent_service.py`

- [ ] placeholder 제목인 `Production Quest N`이 나오지 않는 테스트를 작성한다.
- [ ] description에 target resource 또는 context 정보가 반영되는지 테스트한다.
- [ ] 테스트를 실행해서 실패하는지 확인한다.
- [ ] `_quest_title(index, target_item_id)` helper를 추가한다.
- [ ] `_quest_description(...)` helper를 추가한다.
- [ ] retrieved scenario context의 `summary`를 description에 반영한다.
- [ ] 테스트를 다시 실행해 통과하는지 확인한다.

이 단계의 목표는 LLM이 없어도 UI에 보여줄 수 있는 수준의 deterministic quest 문장을 만드는 것이다.

---

### Task 6: production prompt를 직접 quest JSON 반환 방식으로 변경

**파일**

- 수정: `backend/src/agents/quest_generator/production_quest.py`
- 수정: `backend/tests/test_agent_leaf_behaviors.py`

- [ ] prompt가 `"quests"` JSON 응답을 요구하는지 테스트한다.
- [ ] prompt에 요청 count가 반영되는지 테스트한다.
- [ ] prompt에 `tool_call`, `selected_quest_ids`, `AVAILABLE_QUESTS`가 없는지 테스트한다.
- [ ] 테스트를 실행해서 실패하는지 확인한다.
- [ ] `build_prompt()`가 graph를 실행해 draft quest payload를 만든 뒤, LLM에 직접 `QuestResponse` JSON을 반환하라고 요청하게 한다.
- [ ] LLM에는 id, type, objective, quantity를 유지하고 title/description만 개선하라고 명시한다.
- [ ] 테스트를 다시 실행해 통과하는지 확인한다.

LLM의 책임은 “퀘스트 구조 생성”이 아니라 “서버가 만든 draft의 문장 개선”으로 제한한다.

---

### Task 7: pipeline에서 production tool call 강제 조건 제거

**파일**

- 수정: `backend/src/agents/pipeline/runtime.py`
- 수정: `backend/tests/test_pipeline_edges.py`

- [ ] LLM이 직접 valid production quest JSON을 반환하면 tool call 없이도 `agent.response`가 되는 테스트를 작성한다.
- [ ] 테스트를 실행해서 실패하는지 확인한다.
- [ ] `parse_llm_response` 안의 production-only tool call requirement branch를 제거한다.
- [ ] `PRODUCTION_QUEST_SELECTION_TOOL_NAME` import가 더 이상 필요 없으면 삭제한다.
- [ ] `_has_successful_tool_call`이 더 이상 사용되지 않으면 삭제한다.
- [ ] pipeline 테스트를 다시 실행해 통과하는지 확인한다.

이 작업 후 production quest는 selection tool을 거치지 않고도 직접 JSON 응답을 받을 수 있다.

---

### Task 8: selection tool 제거 또는 정리

**파일**

- 수정: `backend/src/agents/quest_generator/tools.py`
- 수정: selection tool을 import하는 테스트 파일

- [ ] 아래 검색으로 남은 참조를 확인한다.

```bash
rg "PRODUCTION_QUEST_SELECTION_TOOL_NAME|ProductionQuestSelectionTool|select_production_quests"
```

- [ ] runtime 참조가 없으면 `ProductionQuestSelectionTool`을 삭제한다.
- [ ] generic tool-node 테스트가 이 production-specific tool에 의존하면, 테스트 전용 fixture tool로 마이그레이션한다.
- [ ] 관련 테스트를 실행해 통과하는지 확인한다.

---

### Task 9: 문서 갱신

**파일**

- 수정: `README.md`
- 수정: `docs/architecture-plan.md`

- [ ] README에서 quest generator 설명을 LangGraph 기반 생성 방식으로 갱신한다.
- [ ] README에서 quest data repository 설명을 structured quest context 조회 계층으로 갱신한다.
- [ ] architecture plan에서 production quest가 prepared example을 선택한다는 설명을 제거한다.
- [ ] architecture plan에 아래 흐름을 문서화한다.

```text
1. payload 정규화
2. 기본 5개, 최대 10개 범위에서 quest count 결정
3. QuestDataRepository로 structured context 조회
4. production quest draft 생성
5. LLM 사용 가능 시 title/description 개선
6. LLM 실패 시 deterministic fallback 반환
```

- [ ] docs-adjacent 테스트를 실행해 통과하는지 확인한다.

---

### Task 10: 최종 검증

**파일**

- 수정된 모든 파일

- [ ] quest 관련 테스트를 실행한다.

```bash
cd backend
uv run --extra dev pytest tests/test_quest_agent_service.py tests/test_agent_leaf_behaviors.py tests/test_quest_data_repository.py -q
```

- [ ] pipeline 관련 테스트를 실행한다.

```bash
cd backend
uv run --extra dev pytest tests/test_pipeline_edges.py tests/test_protocol_and_router.py tests/test_websocket_endpoint.py -q
```

- [ ] 전체 backend 테스트를 실행한다.

```bash
cd backend
uv run --extra dev pytest -q
```

- [ ] diff를 확인한다.

```bash
git diff -- backend/src/agents/quest_generator/production_quest.py backend/src/agents/quest_generator/service.py backend/src/agents/pipeline/runtime.py backend/src/agents/quest_generator/tools.py backend/tests/test_quest_agent_service.py backend/tests/test_agent_leaf_behaviors.py backend/tests/test_pipeline_edges.py README.md docs/architecture-plan.md
```

- [ ] 구현 변경을 커밋한다.

```bash
git add backend/src/agents/quest_generator/production_quest.py backend/src/agents/quest_generator/service.py backend/src/agents/pipeline/runtime.py backend/src/agents/quest_generator/tools.py backend/tests/test_quest_agent_service.py backend/tests/test_agent_leaf_behaviors.py backend/tests/test_pipeline_edges.py README.md docs/architecture-plan.md
git commit -m "feat: generate production quests with langgraph"
```

---

## 4. 범위 밖

이번 계획에는 아래 항목을 포함하지 않는다.

- PostgreSQL 도입
- 플레이어별 quest progress 저장
- quest 완료 이력 저장
- reward 지급 처리
- frontend UI 변경
- delivery quest 생성 방식 변경
- vector DB/RAG 도입

---

## 5. 자체 검토

- 요구사항 반영: 후보군 선택 제거, LangGraph 활용, 기본 5개 생성, payload 기반 개수 증가, structured CSV repository 연결을 모두 포함했다.
- 모호성 제거: count 우선순위와 허용 범위, fallback 동작을 명시했다.
- 테스트 우선: 각 기능 변경은 먼저 실패 테스트를 작성하고, 그 뒤 구현하도록 구성했다.
- 범위 제한: production quest 생성 방식만 바꾸며, DB나 frontend는 건드리지 않는다.
