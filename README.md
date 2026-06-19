# QuestForge Agent

게임 상태 데이터를 입력으로 받아 생산/납품 퀘스트 후보를 생성하는 LangGraph 기반 AI 퀘스트 에이전트 백엔드입니다.

## 목표

- 게임 진행도, 보유 자원, 최근 이벤트를 바탕으로 구조화된 퀘스트 JSON을 생성합니다.
- FastAPI와 WebSocket으로 agent request 실행 경로를 제공합니다.
- LangGraph로 top-level routing, leaf agent 실행, LLM 호출, fallback, 응답 생성을 분리합니다.
- Pydantic schema와 pytest로 agent 입출력 계약을 검증합니다.

## 핵심 구성

- `backend/src/app.py`: FastAPI app factory, `/health`, agent connection manifest, WebSocket router
- `backend/src/websocket_gateway/`: WebSocket agent endpoint
- `backend/src/llm/`: OpenAI/Gemini/local OpenAI-compatible LLM adapter와 fallback 설정
- `backend/src/agents/pipeline/`: LangGraph 기반 공통 agent 실행 pipeline
- `backend/src/agents/quest_generator/`: production/delivery quest leaf agent와 schema
- `backend/src/quest_data/`: `data/game` CSV를 agent가 조회할 수 있게 만드는 repository 계층
- `data/game/`: 우주선 제작 목표에 맞춘 샘플 게임 CSV 데이터, 시나리오/레시피/룰/보상 참조 데이터
- `docs/architecture-plan.md`: 백엔드와 프론트엔드 구현 계획
- `docs/agent-request-structure.md`: WebSocket agent request 구조와 quest generator payload 예시
- `docs/main-quest-linked-quest-plan.md`: 메인 퀘스트 연계 일일/주간/깜짝 퀘스트 생성 계획

## 실행

```bash
cd backend
uv sync
uv run python scripts/run_server.py
```

기본 확인 주소:

```text
Health check: http://127.0.0.1:18000/health
Agent connection manifest: http://127.0.0.1:18000/api/v1/agent-connection
WebSocket: ws://127.0.0.1:18000/ws/agent
```

다른 포트로 실행:

```bash
uv run python scripts/run_server.py --port 18001
```

Production provider API로 실행:

```bash
cd backend
copy .env.prod.example .env.prod
# .env.prod에 GEMINI_API_KEY, GOOGLE_API_KEY, 또는 OPENAI_API_KEY를 입력
uv run python scripts/run_prod_server.py
```

`run_prod_server.py`는 `.env.prod`를 읽고 Ollama를 시작하지 않습니다.
`QUESTFORGE_LLM_DEFAULT_PROVIDER`를 비워두면 Gemini key가 있을 때 Gemini를 먼저 쓰고,
Gemini key가 없고 `OPENAI_API_KEY`가 있으면 OpenAI를 씁니다. 실제 응답 metadata의
`llmProvider`, `llmModel`, `llmSlot`으로 어떤 provider가 사용됐는지 확인할 수 있습니다.

## Smoke

LLM 없이 HTTP/WebSocket 기본 경로만 확인:

```bash
cd backend
uv run --env-file smoke-none.env.example python scripts/run_server.py
uv run --env-file smoke-none.env.example python scripts/smoke_agent_pipeline.py none
```

LLM provider를 연결한 뒤 quest 응답까지 확인:

```bash
cd backend
uv run python scripts/smoke_agent_pipeline.py local
```

## 검증

```bash
cd backend
uv run --extra dev pytest -q
```

## Production quest 생성

Production quest는 더 이상 고정된 예제 후보군에서 id를 고르는 방식으로 만들지 않습니다.
`ProductionQuestAgent`가 내부 LangGraph를 실행해 요청 payload를 정규화하고,
`QuestDataRepository`로 `data/game` CSV context를 조회한 뒤 `QuestResponse` schema에 맞는
quest draft를 직접 생성합니다.

기본 생성 개수는 5개입니다. 클라이언트는 `quest_generation_options.count` 또는
`quest_count`로 1개에서 10개까지 요청할 수 있습니다. LLM이 사용 가능하면 서버가 만든
draft의 `title`과 `description`만 다듬고, LLM이 실패하면 같은 LangGraph 결과를
deterministic fallback으로 반환합니다.

응답의 `type`은 `daily`, `weekly`, `surprise` 중 하나이며, 생산 계열 퀘스트라는 정보는
`domain: "production"`으로 분리됩니다. `current_main_quest`를 payload에 보내면
부족한 objective를 기준으로 `main_quest_link`가 포함된 연계 퀘스트를 만들 수 있습니다.
`game_state.inventory`가 있으면 기존 `resources`보다 우선 사용하고, `unlocked_equipment`와
`unlocked_recipes`는 퀘스트 설명 context에 반영됩니다.
