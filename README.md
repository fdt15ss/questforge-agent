# QuestForge Agent

QuestForge Agent는 공장 자동화 게임의 플레이 상태를 입력받아 `production`, `delivery`, `exploration` 퀘스트를 생성하는 AI Agent 기반 프로젝트입니다. 백엔드는 FastAPI/WebSocket과 LangGraph pipeline으로 agent 요청을 처리하고, 프론트엔드 Quest Lab은 생성 요청, JSON 재현, 완료 조건 시뮬레이션, Agent Trace 확인을 위한 React MVP입니다.

핵심 설계는 LLM이 모든 퀘스트 JSON을 직접 만들지 않게 하는 것입니다. 서버가 먼저 안전한 draft quest를 만들고, LLM은 `quest_plan` 또는 `quest_text_updates`로 제목, 설명, 의도만 보강합니다. 목표, 보상, 수량, 완료 조건, 만료 시간은 백엔드 deterministic layer가 통제합니다.

## 주요 기능

- WebSocket `agent.request` / `agent.response` 계약
- LangGraph 기반 agent pipeline, middleware log, fallback routing
- production, delivery, exploration leaf agent
- `domain_counts`로 도메인별 생성 개수 지정
- `quest_type_counts`로 daily, weekly, surprise 타입별 개수 지정
- surprise 퀘스트 제한 시간 설정
- exploration 퀘스트 manual 방문 완료형 처리
- `current_main_quest`, `game_state.inventory`, `unlocked_recipes`, `exploration_targets` 기반 context 반영
- CSV 기반 Structured RAG와 ChromaDB semantic retrieval
- Pydantic schema 검증과 deterministic fallback
- React Quest Lab, CSV catalog picker, Agent Trace 패널

## 구조

```text
backend/
  src/app.py                         FastAPI app factory
  src/websocket_gateway/             WebSocket endpoint
  src/agents/pipeline/               LangGraph 공통 agent runtime
  src/agents/quest_generator/        quest generator와 leaf agents
  src/quest_data/                    CSV repository, RAG, vector retrieval
  scripts/run_server.py              개발 서버 실행
  scripts/rebuild_chroma_index.py    Chroma index 재생성
frontend/
  src/App.tsx                        Quest Lab UI
  src/lib/questLab.ts                요청 빌더, alias parser, JSON import
  src/lib/wsClient.ts                WebSocket client
  package.json                       Vite/React scripts
data/game/                           게임 데이터 CSV
docs/                                설계 문서
portfolio.md                         포트폴리오 설명 문서
```

## 백엔드 실행

```bash
cd backend
uv sync
uv run python scripts/run_server.py
```

기본 주소:

```text
Health:    http://127.0.0.1:18000/health
Manifest:  http://127.0.0.1:18000/api/v1/agent-connection
WebSocket: ws://127.0.0.1:18000/ws/agent
```

다른 포트:

```bash
uv run python scripts/run_server.py --port 18001
```

LLM 없이 fallback 경로만 확인하려면:

```bash
uv run --env-file smoke-none.env.example python scripts/run_server.py
uv run --env-file smoke-none.env.example python scripts/smoke_agent_pipeline.py none
```

## 프론트엔드 실행

pnpm이 PATH에 없으면 이 프로젝트에서 사용하던 bundled pnpm 경로를 직접 실행할 수 있습니다.

```powershell
C:\Users\user\.cache\codex-runtimes\codex-primary-runtime\dependencies\bin\pnpm.cmd --dir frontend install
C:\Users\user\.cache\codex-runtimes\codex-primary-runtime\dependencies\bin\pnpm.cmd --dir frontend dev -- --port 5173
```

브라우저:

```text
http://127.0.0.1:5173/
```

Quest Lab의 기본 WebSocket URL은 `ws://127.0.0.1:18000/ws/agent`입니다.

## 요청 예시

```json
{
  "type": "agent.request",
  "request_id": "quest-lab-sample",
  "session_id": "quest-lab",
  "client_id": "quest-lab-frontend",
  "agent": "quest_generator",
  "payload": {
    "quest_generation_options": {
      "domain_counts": {
        "production": 3,
        "delivery": 1,
        "exploration": 1
      },
      "quest_type_counts": {
        "daily": 3,
        "weekly": 1,
        "surprise": 1
      },
      "surprise_duration_minutes": 30
    },
    "progression": {
      "stage": "early_signal_recovery",
      "player_level": 6
    },
    "game_state": {
      "inventory": {
        "resource_copper_wire": 12,
        "resource_oxygen": 1000,
        "resource_coal": 1000,
        "resource_iron_ore": 35
      },
      "unlocked_equipment": [
        "equipment_miner_machine",
        "equipment_smelter"
      ],
      "unlocked_recipes": [
        "recipe_smelt_iron",
        "recipe_smelt_copper",
        "recipe_draw_copper_wire"
      ]
    },
    "recent_events": [
      "동쪽 능선 너머에서 약한 구조 신호가 반복 감지됐다.",
      "자기 폭풍 이후 광맥 스캐너가 불안정하다."
    ],
    "current_main_quest": {
      "id": "main_restore_signal",
      "title": "장거리 신호 복구",
      "description": "기지 밖 신호 간섭을 조사하고 장거리 통신을 복구한다.",
      "objectives": [
        {
          "target_item_id": "resource_circuit_board",
          "quantity": 10
        }
      ],
      "progress": {
        "resource_circuit_board": 4
      }
    },
    "exploration_targets": [
      {
        "id": "signal_east_ridge",
        "label": "동쪽 능선 신호",
        "target_kind": "signal",
        "related_resource_id": "resource_copper_ore"
      }
    ]
  }
}
```

응답 payload는 공통으로 `{"quests": [...]}` 형태입니다. LLM 사용 여부, fallback 여부, 선택 agent, provider/model, latency는 응답 metadata와 Quest Lab의 Agent Trace에서 확인할 수 있습니다.

## 퀘스트 생성 규칙

### 도메인

- `production`: 자원 생산 목표
- `delivery`: 인벤토리 기반 납품 목표
- `exploration`: 장소 방문, 신호 조사, 잔해 확인 같은 manual 목표

### 타입과 만료

- `surprise`: 생성 시각 기준 N분 뒤 만료. `surprise_duration_minutes`로 조정
- `daily`: 다음 자정까지
- `weekly`: 다음 월요일 자정까지

### 완료 조건

- 생산/납품: `objective_count`
- 탐험: `manual`

탐험 퀘스트는 `0 / 1` 카운터 대신 방문 완료형 label을 사용합니다.

## LangGraph

LangGraph는 두 층에서 사용됩니다.

첫 번째는 전체 agent pipeline입니다. 요청 검증, top agent 라우팅, leaf agent 선택, 캐시 조회, prompt 생성, LLM 호출, fallback slot 시도, schema 검증, cache write, response build를 `StateGraph` 노드로 연결합니다.

두 번째는 leaf agent 내부입니다. production은 `normalize_payload -> retrieve_context -> build_quests -> validate_response`, delivery는 `normalize_payload -> select_goal -> build_prompt/build_fallback`, exploration은 `normalize_payload -> retrieve_context -> build_quests -> validate_response` 흐름을 가집니다.

이 구조 덕분에 실패 지점과 fallback 경로를 Agent Trace에서 추적할 수 있습니다.

## RAG와 Vector DB

게임 데이터의 source of truth는 `data/game` CSV입니다. 백엔드는 먼저 Structured CSV RAG로 resource, recipe, scenario, reward rule을 찾습니다.

선택적으로 ChromaDB semantic layer를 붙입니다. `backend/src/quest_data/vector_context.py`는 기본 `.chroma/questforge_game_context` index를 사용하고, `retrieve_game_context()`는 semantic 검색 결과를 `semantic_matches`로 prompt에 추가합니다.

중요한 점은 vector search 결과가 퀘스트 목표, 수량, 보상, 완료 조건을 직접 결정하지 않는다는 것입니다. `semantic_matches`는 LLM이 제목, 설명, 의도를 더 잘 쓰기 위한 참고자료입니다.

Chroma index 재생성:

```bash
cd backend
uv run python scripts/rebuild_chroma_index.py
```

## Alias CSV와 Quest Lab 입력

프론트엔드 Quest Lab은 `data/game/resources.csv`, `equipment.csv`, `recipes.csv`, `quest_input_aliases.csv`를 사용해 한글 입력을 canonical id로 변환합니다.

예를 들어 `철광석=35`, `구리선=12`, `채굴기`, `철괴 제작 공정`처럼 입력해도 요청 payload에는 `resource_iron_ore`, `resource_copper_wire`, `equipment_miner_machine`, `recipe_smelt_iron` 같은 id가 들어갑니다.

## 테스트

백엔드:

```bash
cd backend
uv run --extra dev python -m pytest tests -q
```

프론트엔드:

```powershell
C:\Users\user\.cache\codex-runtimes\codex-primary-runtime\dependencies\bin\pnpm.cmd --dir frontend test
C:\Users\user\.cache\codex-runtimes\codex-primary-runtime\dependencies\bin\pnpm.cmd --dir frontend build
```

## 참고 문서

- [portfolio.md](portfolio.md): 포트폴리오용 백엔드 설명
- [docs/agent-request-structure.md](docs/agent-request-structure.md): 요청 JSON 상세
- [docs/frontend-quest-lab.md](docs/frontend-quest-lab.md): Quest Lab 사용법
- [docs/quest-reward-criteria.md](docs/quest-reward-criteria.md): 보상 기준
- [docs/architecture-plan.md](docs/architecture-plan.md): 아키텍처 계획
