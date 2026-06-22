# QuestForge Agent

QuestForge Agent는 게임 상태 데이터를 입력으로 받아 생산, 납품 퀘스트를 생성하는 FastAPI/WebSocket 기반 AI 에이전트 백엔드입니다.

LangGraph 실행 파이프라인, LLM provider fallback, CSV 기반 게임 데이터, Pydantic 응답 검증을 조합해 클라이언트가 바로 사용할 수 있는 `QuestResponse` JSON을 반환합니다.

## 주요 기능

- WebSocket `agent.request` 메시지 처리
- `quest_generator` 상위 생성기를 통한 production/delivery 퀘스트 혼합 생성
- `sub_agent` 지정 시 production 또는 delivery leaf agent 직접 실행
- `quest_generation_options.count` 기본 5개 생성
- `quest_generation_options.domain_counts`로 도메인별 생성 개수 지정
- `current_main_quest` 기반 보조 퀘스트 연결 정보 생성
- `data/game` CSV 기반 퀘스트, 보상, 리소스, 레시피 참조
- 모든 퀘스트에 필수 `rewards` 포함
- XP/credits 보상은 `quest_reward_rules.csv` 기준으로 검증
- resource 보상은 `resource_ids`, `resource_groups`, CSV 보상 그룹 순서로 후보 선택
- LLM 응답이 스키마, 개수, 보상 기준을 어기면 deterministic fallback으로 전환

## 디렉터리 구조

- `backend/src/app.py`: FastAPI app factory, `/health`, agent connection manifest, WebSocket router 등록
- `backend/src/websocket_gateway/`: WebSocket agent endpoint
- `backend/src/llm/`: OpenAI, Gemini, local OpenAI-compatible LLM adapter와 slot 설정
- `backend/src/agents/pipeline/`: LangGraph 기반 공통 agent 실행 pipeline
- `backend/src/agents/quest_generator/`: 상위 quest generator, production/delivery leaf agent, quest schema, reward 생성 로직
- `backend/src/quest_data/`: `data/game` CSV 조회 repository
- `data/game/`: 리소스, 레시피, 시나리오, 퀘스트 생성 룰, 보상 룰 CSV
- `docs/agent-request-structure.md`: WebSocket 요청 구조와 예시
- `docs/quest-reward-criteria.md`: XP/credits 보상 기준
- `docs/main-quest-linked-quest-plan.md`: 메인 퀘스트 연계 설계 문서

## 실행

개발용 기본 실행:

```bash
cd backend
uv sync
uv run python scripts/run_server.py
```

기본 주소:

```text
Health check: http://127.0.0.1:18000/health
Agent connection manifest: http://127.0.0.1:18000/api/v1/agent-connection
WebSocket: ws://127.0.0.1:18000/ws/agent
```

다른 포트로 실행:

```bash
cd backend
uv run python scripts/run_server.py --port 18001
```

OpenAI 운영 프로필 실행:

```bash
cd backend
copy .env.prod.openai.example .env.prod.openai
# .env.prod.openai에 OPENAI_API_KEY 등 필요한 값을 입력
uv run python scripts/run_prod_server_openai.py
```

Gemini 운영 프로필 실행:

```bash
cd backend
copy .env.prod.gemini.example .env.prod.gemini
# .env.prod.gemini에 GEMINI_API_KEY 또는 GOOGLE_API_KEY 등 필요한 값을 입력
uv run python scripts/run_prod_server_gemini.py
```

공통 운영 실행:

```bash
cd backend
copy .env.prod.example .env.prod
uv run python scripts/run_prod_server.py
```

운영 실행 시 서버는 현재 환경과 LLM slot 요약을 출력합니다.

```text
[QuestForge] ENVIRONMENT=production
[QuestForge] ENV_FILE=.env.prod.openai
[QuestForge] LLM slots: default:openai:gpt-4o-mini, fallback1:local:gemma4:e4b, fallback2:none:-
```

## WebSocket 요청 기본 구조

요청은 `ws://127.0.0.1:18000/ws/agent`로 전송합니다.

```json
{
  "type": "agent.request",
  "request_id": "quest-test-001",
  "session_id": "postman-session",
  "client_id": "postman-client",
  "agent": "quest_generator",
  "payload": {
    "quest_type": "daily",
    "quest_generation_options": {
      "count": 5
    },
    "progression": {
      "stage": "early_automation",
      "player_level": 6
    },
    "game_state": {
      "inventory": {
        "resource_iron_plate": 38,
        "resource_copper_wire": 24
      },
      "unlocked_equipment": [
        "equipment_miner",
        "equipment_smelter",
        "equipment_assembler"
      ],
      "unlocked_recipes": [
        "recipe_smelt_iron",
        "recipe_craft_iron_plate",
        "recipe_craft_copper_wire"
      ]
    },
    "recent_events": [
      "철판과 구리선 수요가 증가했다."
    ]
  }
}
```

응답 payload는 공통으로 `{"quests": [...]}` 형태입니다.

## 라우팅 규칙

- 퀘스트 생성 요청의 top-level `agent`는 `"quest_generator"`를 사용합니다.
- `payload.sub_agent`가 없으면 `quest_generator`가 상위 생성기로 동작해 production/delivery 퀘스트를 합쳐 생성합니다.
- 상위 생성기 기본값은 총 5개이며, 기본 분배는 production 3개, delivery 2개입니다.
- `payload.sub_agent`를 넣으면 해당 leaf agent만 실행합니다.
- 허용되는 `sub_agent` 값은 `"quest_generator.production_quest"`, `"quest_generator.delivery_quest"`입니다.
- `quest_domain: "production"`은 라우팅 키가 아닙니다.
- 상위 라우팅에 필요한 LLM 결정이 실패하면 `ROUTING_UNAVAILABLE` 에러가 반환될 수 있습니다.

leaf agent를 직접 실행하는 예:

```json
{
  "type": "agent.request",
  "request_id": "quest-test-production-only",
  "session_id": "postman-session",
  "client_id": "postman-client",
  "agent": "quest_generator",
  "payload": {
    "sub_agent": "quest_generator.production_quest",
    "quest_type": "daily",
    "quest_generation_options": {
      "count": 5
    },
    "game_state": {
      "inventory": {
        "resource_iron_ore": 55,
        "resource_copper_ore": 42
      }
    }
  }
}
```

## 생성 개수 지정

총 개수만 지정:

```json
{
  "quest_generation_options": {
    "count": 5
  }
}
```

도메인별 개수 지정:

```json
{
  "quest_generation_options": {
    "domain_counts": {
      "production": 2,
      "delivery": 4
    }
  }
}
```

`domain_counts`가 있으면 `count`보다 우선합니다. 위 예시는 총 6개의 퀘스트를 반환합니다.

## 보상 구조

모든 퀘스트 응답에는 `rewards`가 반드시 포함됩니다.

지원 보상 타입:

- `xp`
- `credits`
- `resource`

보상 선택은 `quest_generation_options.reward_options`로 지정합니다.

```json
{
  "quest_generation_options": {
    "count": 5,
    "reward_options": {
      "reward_types": ["xp", "credits", "resource"],
      "resource_groups": ["tier3"]
    }
  },
  "progression": {
    "player_level": 12
  }
}
```

`resource_groups`는 CSV 보상 그룹명 또는 티어 별칭을 사용할 수 있습니다.

- `tier1`, `t1`: 원재료
- `tier2`, `t2`: 기초 가공 자원
- `tier3`, `t3`: 중급 가공 자원
- `tier4`, `t4`: 고급 핵심 모듈

특정 resource를 직접 후보로 지정할 수도 있습니다.

```json
{
  "quest_generation_options": {
    "reward_options": {
      "reward_types": ["resource"],
      "resource_ids": ["resource_copper_ingot"]
    }
  }
}
```

XP/credits 보상은 `data/game/quest_reward_rules.csv`의 `기본XP`, `기본크레딧` 값을 그대로 사용합니다. 진행 티어는 `payload.progression.player_level` 기준입니다.

| player_level | tier |
| ---: | --- |
| 없음 또는 1-5 | T1 |
| 6-10 | T2 |
| 11-15 | T3 |
| 16 이상 | T4 |

자세한 기준은 `docs/quest-reward-criteria.md`를 참고하세요.

## 응답 예시

```json
{
  "quests": [
    {
      "id": 1,
      "type": "daily",
      "domain": "production",
      "title": "철판 생산 병목 해소",
      "description": "자동화 라인의 철판 공급을 안정화한다.",
      "objectives": [
        {
          "target_item_id": "resource_iron_plate",
          "quantity": 20
        }
      ],
      "clear_condition": {
        "mode": "objective_count",
        "target_item_id": "resource_iron_plate",
        "required_quantity": 20,
        "label": "철판 20개 확보"
      },
      "rewards": [
        {
          "reward_type": "xp",
          "amount": 170,
          "resource_id": null,
          "resource_name": null,
          "source_rule_id": "reward_daily_t3",
          "description": "중급 일일 퀘스트는 병목 해소와 다음 제작 준비를 보상 문맥에 넣는다."
        },
        {
          "reward_type": "resource",
          "amount": 2,
          "resource_id": "resource_titanium_alloy",
          "resource_name": "티타늄 합금",
          "source_rule_id": "reward_daily_t3",
          "description": "중급 가공 자원 보상"
        }
      ],
      "main_quest_link": null
    }
  ]
}
```

## Smoke 테스트

LLM 없이 HTTP/WebSocket 기본 경로 확인:

```bash
cd backend
uv run --env-file smoke-none.env.example python scripts/run_server.py
uv run --env-file smoke-none.env.example python scripts/smoke_agent_pipeline.py none
```

LLM provider를 연결한 quest 응답 확인:

```bash
cd backend
uv run python scripts/smoke_agent_pipeline.py local
```

## 테스트

```bash
cd backend
uv run --extra dev python -m pytest tests -q
```

최근 기준 전체 테스트는 `173 passed`입니다.

## 참고 문서

- `docs/agent-request-structure.md`: 요청 JSON 상세 구조
- `docs/quest-reward-criteria.md`: XP/credits 보상 기준
- `docs/architecture-plan.md`: 전체 아키텍처 계획
- `docs/main-quest-linked-quest-plan.md`: 메인 퀘스트 연계 계획
