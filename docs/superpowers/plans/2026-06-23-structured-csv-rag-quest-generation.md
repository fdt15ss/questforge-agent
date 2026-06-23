# Structured CSV RAG 퀘스트 생성 구현 계획

> 에이전트 작업자 필수 지침: 이 계획을 구현할 때는 superpowers:subagent-driven-development 사용을 권장합니다. 대안으로 superpowers:executing-plans를 사용할 수 있습니다. 각 단계는 체크박스 형식으로 진행 상태를 추적합니다.

목표: CSV 게임 데이터를 authoritative knowledge base로 사용해 LLM 퀘스트 기획 전에 관련 게임 정보를 먼저 검색하고, 목표/보상/수량/클리어 조건은 서버 deterministic layer가 계속 소유하게 만든다.

아키텍처: 현재 데이터는 resources.csv, recipes.csv, scenario_context.csv, quest_reward_rules.csv처럼 정형 CSV로 관리된다. 따라서 벡터DB 기반 RAG가 아니라 Structured CSV RAG를 적용한다. 요청 payload에서 resource id, recipe id, quest type, progression, recent_events 신호를 추출하고, CSV row를 exact id match와 간단한 keyword overlap으로 점수화한다. 검색 결과는 RETRIEVED_GAME_CONTEXT 섹션으로 LLM prompt에 제공한다.

기술 스택: Python 3.12, Pydantic, pytest, LangGraph agent pipeline, CSV game data repository.

## 구현 원칙

- CSV는 source of truth로 유지한다.
- LLM은 retrieved context를 참고하지만 게임 데이터를 새로 만들어내지 않는다.
- reward rule, reward amount, objective quantity, clear condition은 서버가 결정한다.
- LLM 응답이 서버 소유 필드를 바꾸면 기존처럼 invalid_llm_response fallback으로 처리한다.
- 외부 vector DB, embedding, async indexing은 이번 범위에서 제외한다.

## 파일 구조

- backend/src/quest_data/retrieval.py: 새 Structured CSV RAG 모듈. signal extraction, scoring, top-k retrieval, prompt-safe serialization 담당.
- backend/src/quest_data/repository.py: list_recipes 메서드 추가.
- backend/tests/test_quest_data_retrieval.py: retriever 단위 테스트 추가.
- backend/src/agents/quest_generator/agent.py: parent quest_generator prompt에 RETRIEVED_GAME_CONTEXT 추가.
- backend/src/agents/quest_generator/production_quest.py: production leaf prompt에 RETRIEVED_GAME_CONTEXT 추가.
- backend/src/agents/quest_generator/delivery_quest.py: delivery leaf prompt에 RETRIEVED_GAME_CONTEXT 추가.
- backend/tests/test_quest_agent_service.py: parent prompt 검증 추가.
- backend/tests/test_agent_leaf_behaviors.py: leaf prompt 검증 추가.
- backend/tests/test_message_router.py: pipeline prompt 검증 추가.
- docs/agent-request-structure.md: Structured CSV RAG 요청 계약 문서화.
- README.md: 포트폴리오 설명용 Hybrid Deterministic + Structured RAG 문단 추가.

## Task 1: Repository에 Recipe 목록 조회 추가

목적: retrieval 모듈이 private _load_recipes에 직접 접근하지 않도록 공개 조회 API를 추가한다.

수정 파일:
- backend/src/quest_data/repository.py
- backend/tests/test_quest_data_repository.py

구현 단계:
1. test_repository_lists_recipe_rows 테스트를 추가한다.
2. 테스트가 AttributeError로 실패하는지 확인한다.
3. QuestDataRepository에 list_recipes 메서드를 추가한다.
4. 테스트가 통과하는지 확인한다.
5. 변경사항을 커밋한다.

테스트 핵심 검증:
- list_recipes가 비어 있지 않다.
- recipe_make_circuit_board가 포함된다.
- 모든 recipe_id가 recipe_ prefix를 가진다.

예상 커밋 메시지: feat: expose recipe listing for quest retrieval

## Task 2: Structured CSV RAG Retriever 추가

목적: payload에서 query signal을 추출하고 CSV row를 점수화해 LLM prompt에 넣을 compact context를 만든다.

생성 파일:
- backend/src/quest_data/retrieval.py
- backend/tests/test_quest_data_retrieval.py

retrieval 입력:
- payload
- QuestDataRepository
- max_resources 기본값 8
- max_recipes 기본값 6
- max_scenarios 기본값 5
- max_reward_rules 기본값 3

retrieval query signal:
- current_main_quest.objectives의 target_item_id
- game_state.inventory의 resource id
- game_state.unlocked_recipes의 recipe id
- quest_type과 quest_generation_options.quest_types
- recent_events, progression, current_main_quest title/description에서 추출한 text token

retrieval 출력 shape:
- query: resource_ids, recipe_ids, quest_types, text_tokens
- resources: resource_id, resource_name, resource_type, usage, acquisition_method
- recipes: recipe_id, recipe_name, input_resources, output_resources, tier, quest_tags, llm_prompt_hint
- scenario_contexts: context_id, arc, theme, related_resources, related_recipes, related_quest_types, llm_prompt_hint
- reward_rules: reward_rule_id, quest_type, tier, base_xp, base_credits, resource_group, llm_reward_hint

점수화 규칙:
- exact resource id match는 높은 점수로 처리한다.
- exact recipe id match는 높은 점수로 처리한다.
- recipe input/output resource가 query resource와 겹치면 가산점 부여한다.
- scenario related_resources, related_recipes, related_quest_types가 query와 겹치면 가산점 부여한다.
- reward rule quest_type이 query quest_type과 맞으면 가산점 부여한다.
- 동일 점수에서는 id 기준 정렬로 deterministic order를 보장한다.

테스트:
1. 메인 퀘스트와 inventory signal로 resource_circuit_board와 recipe_make_circuit_board가 검색되는지 확인한다.
2. 같은 payload로 두 번 호출했을 때 결과가 동일한지 확인한다.
3. resources, recipes, scenario_contexts, reward_rules가 각각 top-k 제한을 넘지 않는지 확인한다.

예상 커밋 메시지: feat: add structured csv quest retrieval

## Task 3: Parent Quest Planner Prompt에 Retrieved Context 추가

목적: 상위 quest_generator가 quest_plan을 만들 때 CSV 검색 결과를 참고하게 한다.

수정 파일:
- backend/src/agents/quest_generator/agent.py
- backend/tests/test_quest_agent_service.py

구현 단계:
1. QuestGeneratorAgent.build_prompt 테스트를 추가한다.
2. prompt에 RETRIEVED_GAME_CONTEXT가 없어 실패하는지 확인한다.
3. agent.py에서 QuestDataRepository와 retrieve_game_context를 import한다.
4. draft_payload 생성 후 retrieve_game_context를 호출한다.
5. REQUEST_PAYLOAD와 OUTPUT_CONTRACT 사이에 RETRIEVED_GAME_CONTEXT 섹션을 추가한다.
6. TASK instruction에 retrieved context는 authoritative game knowledge지만 rewards, quantities, objectives, clear conditions를 invent하지 말라는 문장을 추가한다.
7. 테스트 통과를 확인한다.

테스트 핵심 검증:
- prompt에 RETRIEVED_GAME_CONTEXT 섹션이 있다.
- prompt에 resource_circuit_board가 있다.
- prompt에 recipe_make_circuit_board가 있다.
- prompt에 reward_rules가 있다.

예상 커밋 메시지: feat: include retrieved csv context in quest planner prompt

## Task 4: Leaf Text-Update Prompt에 Retrieved Context 추가

목적: production_quest와 delivery_quest leaf agent가 title/description을 다듬을 때도 검색된 CSV context를 참고하게 한다.

수정 파일:
- backend/src/agents/quest_generator/production_quest.py
- backend/src/agents/quest_generator/delivery_quest.py
- backend/tests/test_agent_leaf_behaviors.py

구현 단계:
1. production prompt에 RETRIEVED_GAME_CONTEXT가 들어가는지 확인하는 실패 테스트를 추가한다.
2. delivery prompt에 RETRIEVED_GAME_CONTEXT가 들어가는지 확인하는 실패 테스트를 추가한다.
3. production_quest.py에서 retrieve_game_context를 호출하고 prompt section을 추가한다.
4. delivery_quest.py에서 QuestDataRepository와 retrieve_game_context를 import하고 prompt section을 추가한다.
5. leaf prompt 테스트가 통과하는지 확인한다.

테스트 핵심 검증:
- production prompt에 RETRIEVED_GAME_CONTEXT가 있다.
- delivery prompt에 RETRIEVED_GAME_CONTEXT가 있다.
- 두 prompt 모두 resource_circuit_board와 recipe_make_circuit_board를 포함한다.

예상 커밋 메시지: feat: include retrieved csv context in leaf prompts

## Task 5: Pipeline Regression Test 추가

목적: 실제 AgentPipeline 실행 경로에서 quest_generator prompt에 retrieved context가 들어가는지 검증한다.

수정 파일:
- backend/tests/test_message_router.py

구현 단계:
1. StubLLM으로 top_agent_decision과 quest_plan_response를 준비한다.
2. payload에는 quest_generation_options count 2, domain_counts production 1 delivery 1을 넣는다.
3. current_main_quest objective에는 resource_circuit_board를 넣는다.
4. game_state에는 inventory resource_circuit_board와 unlocked_recipes recipe_make_circuit_board를 넣는다.
5. pipeline.run 결과가 agent.response인지 확인한다.
6. llm.prompts[1]에 RETRIEVED_GAME_CONTEXT, resource_circuit_board, recipe_make_circuit_board가 포함됐는지 확인한다.
7. metadata.quest_plan_analysis가 유지되는지 확인한다.

예상 커밋 메시지: test: cover retrieved csv context in quest pipeline

## Task 6: Structured CSV RAG 문서화

목적: 백엔드 계약 문서와 README에 포트폴리오용 설명을 추가한다.

수정 파일:
- docs/agent-request-structure.md
- README.md

agent-request-structure.md에 추가할 내용:
- 퀘스트 생성기는 요청 payload를 바로 LLM에 넘기지 않고 CSV game database에서 관련 row를 먼저 조회한다.
- 조회 신호는 current_main_quest objectives, game_state inventory, unlocked_recipes, quest_type, recent_events, progression, 메인 퀘스트 제목/설명이다.
- 조회 결과는 LLM prompt의 RETRIEVED_GAME_CONTEXT 섹션에 들어간다.
- 이 context는 title, description, quest_plan reason 품질 개선용이다.
- objectives, clear_condition, rewards, quantity는 서버 deterministic layer가 소유한다.

README에 추가할 포트폴리오 문단:
Hybrid Deterministic + Structured RAG Quest Generation 구조를 설명한다. CSV game data를 authoritative knowledge base로 쓰고, LLM은 검색된 context 위에서 기획 의도와 한국어 설명을 생성하지만, quest count, objectives, clear conditions, reward rules, schema validation은 서버가 담당한다는 점을 강조한다.

예상 커밋 메시지: docs: explain structured csv rag quest generation

## Task 7: 전체 검증

목적: retrieval, prompt integration, pipeline integration이 기존 퀘스트 생성 동작을 깨지 않는지 확인한다.

검증 명령:
1. Focused tests 실행
uv run --project ..\.worktrees\codex-quest-plan-llm-extension\backend python -m pytest tests/test_quest_data_repository.py tests/test_quest_data_retrieval.py tests/test_quest_agent_service.py tests/test_agent_leaf_behaviors.py tests/test_message_router.py

예상 결과: 선택한 테스트가 모두 통과한다.

2. 전체 backend tests 실행
uv run --project ..\.worktrees\codex-quest-plan-llm-extension\backend python -m pytest

예상 결과: 전체 테스트가 통과한다.

3. Whitespace diff check 실행
git diff --check

예상 결과: 출력이 없어야 한다.

4. Prompt smoke check 실행
QuestGeneratorAgent.build_prompt를 직접 호출해 prompt에 RETRIEVED_GAME_CONTEXT, resource_circuit_board, recipe_make_circuit_board가 모두 들어가는지 확인한다.

예상 결과: True True True

검증 중 수정이 필요하면 아래 메시지로 최종 커밋한다.
fix: stabilize structured csv rag integration

## 자체 리뷰

요구사항 반영: CSV retrieval, prompt integration, validation boundary, tests, docs를 모두 task로 분리했다.

Placeholder scan: TBD/TODO 없이 구현자가 그대로 따라갈 수 있는 test intent, implementation detail, command, expected output을 명시했다.

타입 일관성: retrieve_game_context, RetrievedGameContext, list_recipes, RETRIEVED_GAME_CONTEXT 명칭을 전 task에서 동일하게 사용한다.

범위 점검: vector DB, embedding, async indexing, 외부 서비스는 포함하지 않는다. 첫 버전은 현재 CSV에 대한 structured RAG만 구현한다.
