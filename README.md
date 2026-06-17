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
- `data/game/`: 데모와 테스트에 사용할 샘플 게임 CSV 데이터
- `docs/architecture-plan.md`: 백엔드와 프론트엔드 구현 계획

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
