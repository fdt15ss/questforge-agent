# QuestForge Agent Backend Portfolio

## 프로젝트 개요

QuestForge Agent는 공장 자동화 게임의 플레이 상태를 바탕으로 생산, 납품, 탐험 퀘스트를 생성하는 AI Agent 기반 백엔드 실험 프로젝트입니다. 프론트엔드 Quest Lab에서 WebSocket 요청을 보내면 백엔드는 agent pipeline을 통해 요청을 라우팅하고, LLM이 사용할 수 있는 초안과 게임 컨텍스트를 만든 뒤, 최종 퀘스트 JSON을 반환합니다.

핵심 목표는 LLM이 자연스러운 제목과 의도를 보강하되, 퀘스트 완료 조건, 보상, 수량, 만료 시간처럼 게임 시스템이 소유해야 하는 필드는 서버가 안정적으로 통제하는 구조를 만드는 것이었습니다.

## 백엔드에서 AI Agent가 쓰이는 부분

- `quest_generator` 상위 agent가 요청 payload를 읽고 production, delivery, exploration 도메인별 퀘스트 생성을 조합합니다.
- leaf agent는 도메인별 초안을 deterministic하게 만들고, LLM은 `quest_plan` 또는 `quest_text_updates` 형태로 제목, 설명, 의도, 메인 퀘스트 연결 이유를 보강합니다.
- pipeline은 LLM 응답을 schema로 검증하고, 실패하면 deterministic fallback으로 안전한 퀘스트를 반환합니다.
- 응답 metadata에는 선택된 agent, leaf agent, LLM provider/model, fallback 여부, fallback reason, latency, middleware log를 담아 Agent Trace 패널에서 디버깅할 수 있게 했습니다.

## 시행착오 1: LLM이 퀘스트 전체 JSON을 망가뜨리는 문제

초기에는 LLM이 퀘스트 전체 구조를 직접 생성하거나 수정하는 방식에 가까웠습니다. 이 방식은 설명은 자연스러워질 수 있지만, `objectives`, `clear_condition`, `rewards` 같은 서버 소유 필드가 누락되거나 잘못된 schema로 반환되는 문제가 있었습니다. 실제로 local model이 일부 batch에서 `invalid_schema`를 내면서 전체 생성이 fallback으로 떨어지는 상황이 있었습니다.

이를 해결하기 위해 LLM의 권한을 줄였습니다. 서버가 먼저 안전한 draft quest를 만들고, LLM은 `quest_plan` 또는 `quest_text_updates`만 반환하도록 계약을 좁혔습니다. pipeline은 LLM 응답을 Pydantic schema로 검증하고, 유효한 batch만 병합하거나 실패 시 deterministic fallback을 사용합니다.

이 설계 덕분에 LLM 품질 문제는 trace에서 관찰 가능해졌고, 게임 시스템 필드는 항상 서버 규칙으로 보존됩니다. 포트폴리오에서는 이 부분을 "LLM을 생성 주체가 아니라 보강 주체로 제한해 안정성을 확보했다"고 설명할 수 있습니다.

## 시행착오 2: 탐험 퀘스트를 생산 퀘스트처럼 수량 목표로 처리한 문제

탐험 퀘스트를 처음에는 다른 퀘스트와 동일하게 `target_item_id`와 `0 / 1` 진행도로 보여주는 방식으로 처리했습니다. 하지만 탐험은 자원을 모으는 행동이 아니라 장소 방문, 신호 조사, 잔해 확인 같은 플레이어 액션에 가깝기 때문에 수량 카운터 모델과 맞지 않았습니다.

이를 해결하기 위해 exploration leaf agent의 완료 조건을 `objective_count`가 아니라 `manual` 방문 완료형으로 정리했습니다. 백엔드는 `clear_condition.mode = "manual"`과 한국어 완료 label을 내려주고, 프론트엔드는 이를 자원 카운터가 아니라 "방문 완료" 버튼으로 표시합니다.

이 시행착오는 도메인별 퀘스트의 의미를 하나의 schema에 억지로 맞추기보다, 공통 schema 안에서 완료 조건의 mode를 분리해야 한다는 판단으로 이어졌습니다.

## 시행착오 3: game_state 정보를 설명문에 그대로 노출한 문제

`game_state.unlocked_equipment`, `game_state.unlocked_recipes`를 생산 퀘스트 설명에 자연스럽게 섞으려다 보니, `equipment_miner_machine`, `recipe_smelt_copper` 같은 내부 id가 카드 설명에 노출되는 문제가 생겼습니다. 플레이어에게는 "이 설비를 바로 활용할 수 있고 제작법도 이미 확보되어 있습니다" 같은 문장이 설명 과잉으로 보였습니다.

이 문제는 game_state를 "플레이어에게 보여줄 문장"이 아니라 "생성 판단을 위한 내부 컨텍스트"로 분리하면서 해결했습니다. 해금 설비와 제작법은 요청 payload와 검색 컨텍스트에는 남기되, fallback description에는 직접 붙이지 않도록 했고, 회귀 테스트로 내부 id가 설명에 새지 않게 고정했습니다.

또한 납품 퀘스트에서는 인벤토리를 무시하고 기본 철괴만 생성하던 문제를 수정했습니다. `game_state.inventory`를 후보로 사용하고, 납품 수량도 단순히 5, 6, 7처럼 증가시키는 대신 퀘스트 타입별 비율로 계산하도록 바꿨습니다. 예를 들어 일일 퀘스트는 보유량의 10%, 주간 퀘스트는 25%, 돌발 퀘스트는 5%를 기준으로 삼아 더 의미 있는 목표가 나오게 했습니다.


## LangGraph 적용 위치

이 프로젝트에서 LangGraph는 단순히 LLM 호출을 감싸는 용도가 아니라, 백엔드 agent pipeline의 실행 흐름을 명시적으로 관리하는 데 사용했습니다.

첫 번째 적용 지점은 전체 agent pipeline입니다. 요청이 들어오면 `build_context`, `validate_envelope`, `route_top_agent`, `quest_generator.route_sub_agent`, `cache_lookup`, `build_prompt`, `call_llm.default`, `call_llm.fallback1`, `call_llm.fallback2`, `parse_llm_response`, `agent.middleware.fallback`, `validate_response_schema`, `cache_write`, `build_agent_response` 같은 노드를 LangGraph `StateGraph`로 연결했습니다. 덕분에 LLM 응답 실패, schema 검증 실패, fallback 전환, middleware log 기록을 하나의 실행 그래프로 추적할 수 있었습니다.

두 번째 적용 지점은 production, delivery, exploration leaf agent입니다. 예를 들어 production leaf는 `normalize_payload -> retrieve_context -> build_quests -> validate_response` 흐름을 갖고, delivery leaf는 `normalize_payload -> select_goal -> build_prompt/build_fallback` 흐름을 갖습니다. exploration leaf 역시 payload 정규화, 컨텍스트 조회, 퀘스트 생성, 응답 검증을 그래프 단계로 분리했습니다.

포트폴리오에서는 이 부분을 "agent의 처리 단계를 함수 호출 체인으로 숨기지 않고, LangGraph 노드로 나누어 fallback과 trace가 가능한 구조로 만들었다"고 설명할 수 있습니다.

## Vector DB / Semantic Retrieval 적용 위치

게임 데이터는 `data/game` CSV를 source of truth로 두고, 벡터 검색은 LLM prompt 품질을 높이는 보조 컨텍스트로만 사용했습니다. 즉, 벡터 검색 결과가 퀘스트 목표, 보상, 수량, 완료 조건을 직접 결정하지 않습니다. 이 필드들은 백엔드 deterministic layer가 계속 통제합니다.

구조는 hybrid RAG에 가깝습니다. 먼저 `retrieve_game_context()`가 resource, recipe, scenario, reward rule을 exact/rule 기반으로 가져옵니다. 여기에 선택적으로 vector store를 연결해 `semantic_matches`를 추가합니다. production, delivery, exploration agent와 상위 `quest_generator`는 `default_vector_store()`를 통해 Chroma 기반 persistent vector store를 가져오고, 인덱스가 없거나 생성에 실패하면 semantic match 없이 CSV 기반 검색만으로 계속 동작합니다.

벡터 DB에 넣는 문서는 `resources.csv`, `recipes.csv`, `scenario_context.csv` 같은 게임 데이터를 검색용 텍스트 문서로 변환해 구성했습니다. ChromaDB adapter가 준비되어 있으면 persistent collection에서 의미 기반 top-k를 조회하고, 로컬 테스트에서는 deterministic hashing 기반 local vector store로 같은 계약을 검증할 수 있게 했습니다.

중요한 설계 포인트는 `semantic_matches`를 prompt 내부 참고자료로만 전달한다는 점입니다. LLM은 이를 보고 제목, 설명, quest_plan 의도를 더 자연스럽게 만들 수 있지만, 서버 소유 필드는 바꿀 수 없습니다. 이 분리는 RAG를 붙이면서도 게임 규칙의 안정성을 유지하기 위한 장치였습니다.

## 안정성을 위해 만든 장치

- Pydantic schema 검증으로 LLM 응답 shape를 강제했습니다.
- deterministic fallback을 유지해 LLM 장애, 빈 응답, invalid schema 상황에서도 퀘스트 생성이 끊기지 않게 했습니다.
- `quest_type_counts`, `domain_counts`로 총 퀘스트 개수와 타입 분배를 명시할 수 있게 했습니다.
- production, delivery, exploration leaf agent별 테스트를 두어 도메인별 완료 조건과 deadline이 깨지지 않게 했습니다.
- Agent Trace metadata를 응답에 포함해 fallback 원인과 LLM 시도 내역을 프론트에서 바로 확인할 수 있게 했습니다.

## 포트폴리오 설명 포인트

이 프로젝트는 단순히 LLM에게 JSON을 만들게 한 것이 아니라, 게임 서버가 책임져야 하는 규칙과 LLM이 잘하는 자연어 보강을 분리한 구조입니다. LLM은 퀘스트의 의도와 설명 품질을 높이고, 백엔드는 schema, 완료 조건, 수량, 보상, 만료 시간, fallback을 통제합니다.

면접이나 포트폴리오에서는 다음처럼 설명할 수 있습니다.

> LLM이 생성한 결과를 그대로 신뢰하지 않고, 서버가 먼저 deterministic draft를 만든 뒤 LLM은 제한된 schema로 제목과 의도만 보강하게 했습니다. invalid schema나 빈 응답이 와도 deterministic fallback으로 퀘스트를 유지했고, Agent Trace로 어떤 모델과 fallback 경로가 쓰였는지 확인할 수 있게 설계했습니다.

