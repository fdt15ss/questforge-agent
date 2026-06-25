# 로컬 QuestPlan 배치 처리 구현 계획

## 목표

로컬 LLM, 특히 `gemma4:e4b`가 `count: 5` 요청에서 긴 JSON을 한 번에 안정적으로 반환하지 못하는 문제를 줄인다. `quest_generator`가 compact/local 모드에서 퀘스트 5개를 한 번에 요구하지 않고 3개 이하의 작은 `quest_plan` 요청으로 나누어 호출한 뒤, 서버가 결과를 다시 하나의 `quest_plan`으로 합쳐 기존 검증/병합 로직을 그대로 사용한다.

## 배경

- OpenAI 모델에서는 `count: 5` QuestPlan 응답이 정상적으로 나오는 편이다.
- 로컬 e4b는 `count: 3`까지는 비교적 안정적이지만 `count: 5`에서 `empty_response`, `invalid_json`, `invalid_schema`가 발생했다.
- `QUESTFORGE_LLM_MAX_OUTPUT_TOKENS`를 12000 이상으로 늘려도 JSON schema가 흔들릴 수 있으므로, 출력 길이를 줄이는 구조적 대응이 필요하다.

## 설계

1. `QuestGeneratorAgent`에 `build_prompt_batches(payload, context, batch_size=3)`를 추가한다.
2. compact 모드이고 draft quest 수가 3개를 초과할 때만 batch prompt를 반환한다.
3. 각 batch prompt는 기존 compact prompt와 같은 `QuestPlan` 스키마를 사용하지만 `DRAFT_QUESTS`와 `OUTPUT_JSON`을 해당 batch subset으로 제한한다.
4. pipeline은 `promptBatches`가 있으면 같은 LLM slot으로 batch prompt를 순차 호출한다.
5. 각 batch 응답은 `QuestPlanEnvelope`로 1차 검증한다.
6. 모든 batch가 유효하면 `analysis`는 줄바꿈으로 합치고, `domain_mix`는 합산하고, `quest_intents`는 순서대로 이어 붙인 하나의 `quest_plan` JSON을 만든다.
7. 합쳐진 JSON은 기존 `_merge_quest_plan`으로 다시 검증되므로 최종 quest 수, id, domain, target item 검증은 그대로 유지된다.

## 변경 파일

- `backend/src/agents/quest_generator/agent.py`
  - compact prompt 생성 헬퍼 분리
  - `LOCAL_QUEST_PLAN_BATCH_SIZE = 3` 추가
  - `build_prompt_batches` 추가
- `backend/src/agents/pipeline/runtime.py`
  - batch LLM 호출 helper 추가
  - batch `quest_plan` 병합 helper 추가
  - build_prompt node에서 `promptBatches` state 저장
  - call_llm node에서 batch가 있으면 순차 호출
- `backend/src/agents/pipeline/state.py`
  - `promptBatches: list[str]` 추가
- `backend/tests/test_quest_agent_service.py`
  - local compact count 5가 3+2 prompt로 나뉘는지 검증
- `backend/tests/test_message_router.py`
  - pipeline이 batch별 `quest_plan`을 합쳐 최종 5개 퀘스트로 반환하는지 검증

## 기대 효과

- e4b가 한 번에 5개 quest intent를 생성하지 않아도 되므로 JSON 출력 실패 가능성이 낮아진다.
- 서버가 최종 schema와 quest 수를 계속 검증하므로 잘못된 batch 응답은 deterministic fallback으로 안전하게 처리된다.
- OpenAI/rich 모드의 기존 한 번 호출 흐름은 유지된다.

## 검증 항목

- `backend/tests/test_quest_agent_service.py::test_quest_generator_builds_local_compact_prompt_batches`
- `backend/tests/test_message_router.py::test_pipeline_merges_local_quest_plan_batches`
- `backend/tests/test_quest_agent_service.py backend/tests/test_message_router.py`
- `backend/tests`
- `ruff check` 대상 파일