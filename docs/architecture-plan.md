# QuestForge Agent 백엔드/프론트엔드 구현 계획

## 1. 제품 방향

QuestForge Agent는 게임 상태를 입력으로 받아 플레이어에게 줄 생산/납품 퀘스트를 생성하는 AI agent 프로젝트다. 포트폴리오 관점에서는 “LLM을 그냥 호출하는 서버”보다 “게임 도메인 데이터, LangGraph agent 흐름, 실시간 WebSocket UI가 함께 보이는 시스템”으로 만드는 것이 좋다.

우선순위는 다음 순서로 둔다.

1. 백엔드 agent 실행 계약을 안정화한다.
2. 프론트엔드는 agent를 체험하고 디버깅할 수 있는 Quest Lab으로 시작한다.
3. 이후 게임 클라이언트나 Unreal 연동이 필요해지면 같은 WebSocket 계약을 재사용한다.

## 2. 전체 아키텍처

```text
Frontend Quest Lab
  -> HTTP /health, /api/v1/agent-connection
  -> WebSocket /ws/agent

FastAPI Backend
  -> Protocol validation
  -> Agent connection/router
  -> LangGraph pipeline
  -> Quest generator agents
  -> LLM adapter and fallback
  -> Sample game data repository
```

핵심 원칙은 “transport, protocol, agent runtime, quest domain을 분리한다”이다. WebSocket payload가 바뀌어도 quest 선택 로직이 흔들리지 않고, LLM provider를 바꿔도 프론트엔드 계약이 유지되도록 만든다.

## 3. 백엔드 계획

### 3.1 기술 스택

- Python 3.12
- FastAPI
- WebSocket
- LangGraph
- Pydantic
- OpenAI/Gemini/local OpenAI-compatible LLM adapter
- pytest
- uv

### 3.2 디렉터리 구조

현재 구조를 유지하되, 역할을 더 명확하게 문서화하고 필요한 파일만 늘린다.

```text
backend/src/
  app.py
  protocol/
    messages.py
    errors.py
  websocket_gateway/
    connection.py
    gateway.py
  agent_connection/
    router.py
  llm/
    adapter.py
    settings.py
  agents/
    base.py
    router.py
    orchestrator.py
    pipeline/
    quest_generator/
```

추가하면 좋은 구조:

```text
backend/src/quest_data/
  repository.py
  csv_loader.py
  schemas.py
```

`quest_data`는 `data/game/*.csv`를 읽어서 agent가 쓰기 쉬운 Python object로 바꾸는 계층이다. 처음에는 CSV만 읽고, DB나 vector store는 넣지 않는다.

### 3.3 API 계약

유지할 HTTP endpoint:

- `GET /health`
- `GET /api/v1/agent-connection`

유지할 WebSocket endpoint:

- `WS /ws/agent`

요청 예시:

```json
{
  "type": "agent.request",
  "request_id": "request-001",
  "session_id": "session-001",
  "client_id": "quest-lab",
  "agent": "quest_generator",
  "payload": {
    "sub_agent": "quest_generator.production_quest",
    "progression": { "stage": "early" },
    "resources": { "iron_ore": 12, "copper_ore": 5 },
    "recent_events": ["first_factory_started"]
  }
}
```

응답은 `agent.response` 또는 `agent.error` 두 갈래로 유지한다. 프론트엔드는 이 두 타입만 알면 된다.

### 3.4 Agent 설계

현재 agent 구조는 계속 가져간다.

- `OrchestratorAgent`: top-level agent 선택
- `QuestGeneratorAgent`: quest leaf agent 선택
- `ProductionQuestAgent`: 생산 퀘스트 후보 생성
- `DeliveryQuestAgent`: 납품 퀘스트 생성
- `AgentPipeline`: LangGraph 실행, LLM 호출, tool call, fallback 처리

다음 단계에서 추가할 agent는 하나씩만 늘린다.

1. `quest_generator.production_quest`
2. `quest_generator.delivery_quest`
3. `quest_generator.tutorial_quest`

`economy_quest`, `exploration_quest` 같은 확장은 아직 만들지 않는다. 현재 포트폴리오 목표에는 생산/납품 흐름만 충분하다.

### 3.5 LLM Adapter 정책

LLM provider는 환경변수 prefix를 `QUESTFORGE_LLM_`로 유지한다.

권장 provider 순서:

1. local OpenAI-compatible endpoint
2. OpenAI
3. Gemini
4. none fallback

LLM 호출 실패 시 정책:

- provider timeout: 다음 fallback slot 시도
- 모든 provider 실패: deterministic fallback quest 반환
- malformed tool call: `agent.error`가 아니라 fallback quest 반환
- protocol validation 실패: `agent.error` 반환

### 3.6 샘플 데이터 사용 방식

`data/game` CSV는 유지한다.

- `resources.csv`: 우주선 제작 체인에 필요한 원재료, 중간재, 모듈, 완성품 자원
- `recipes.csv`: 원재료 채굴 이후 부품, 모듈, 정찰 우주선까지 이어지는 제작/가공 관계
- `equipment.csv`: 장비 역할
- `action_policy.csv`: 설명/추천 액션
- `troubleshooting_rules.csv`: 병목/문제 상황
- `quest_reward_rules.csv`: 일일/주간/깜짝 퀘스트 보상 스케일
- `quest_generation_rules.csv`: 레벨/티어별 퀘스트 생성 기준

처음에는 quest generation prompt에 필요한 부분만 repository에서 읽는다. 전체 CSV를 프롬프트에 밀어 넣지 않고, payload와 관련된 row만 추려서 넣는다.

### 3.7 백엔드 구현 순서

1. README와 docs를 기준으로 현재 계약을 고정한다.
2. `quest_data` CSV repository를 추가한다.
3. Production quest agent가 repository에서 후보 quest context를 가져오게 한다.
4. Delivery quest agent fallback payload를 schema 기준으로 더 엄격하게 만든다.
5. WebSocket smoke test에 정상 quest generation case를 추가한다.
6. LLM provider별 설정 문서를 추가한다.

### 3.8 백엔드 검증

필수 검증:

```bash
cd backend
uv run --extra dev pytest -q
```

smoke 검증:

```bash
cd backend
uv run --env-file smoke-none.env.example python scripts/run_server.py
uv run --env-file smoke-none.env.example python scripts/smoke_agent_pipeline.py none
```

테스트 기준:

- protocol validation 실패는 항상 `agent.error`
- LLM이 없어도 fallback 응답은 schema를 통과
- WebSocket 연결은 invalid JSON, invalid envelope, routing unavailable을 구분
- agent metadata에는 선택된 leaf agent가 남음

## 4. 프론트엔드 계획

### 4.1 기술 스택

처음 프론트엔드는 React + Vite + TypeScript를 권장한다.

이유:

- SSR이 필요 없다.
- WebSocket 기반 실시간 UI에 단순하다.
- 포트폴리오 데모를 빠르게 만들 수 있다.
- 배포도 정적 파일 hosting으로 충분하다.

권장 구성:

- React
- Vite
- TypeScript
- Zustand 또는 React state
- Vitest
- Playwright
- CSS Modules 또는 Tailwind CSS

상태 관리가 복잡해지기 전까지 Redux는 쓰지 않는다.

### 4.2 프론트엔드 디렉터리 구조

```text
frontend/
  package.json
  index.html
  src/
    main.tsx
    app/
      App.tsx
      routes.ts
    api/
      agentConnection.ts
      websocketClient.ts
    features/
      quest-lab/
        QuestLabPage.tsx
        QuestRequestForm.tsx
        QuestResponsePanel.tsx
        AgentTracePanel.tsx
        samplePayloads.ts
      settings/
        SettingsPage.tsx
    shared/
      components/
      types/
      styles/
```

처음 화면은 landing page가 아니라 바로 Quest Lab이다.

### 4.3 화면 구성

첫 버전 화면은 3분할 구성이 좋다.

```text
왼쪽: 요청 입력
  - agent 선택
  - sub_agent 선택
  - progression stage
  - resources JSON
  - recent events
  - Send 버튼

가운데: 퀘스트 결과
  - title
  - description/objective
  - clear condition
  - local progress
  - reward
  - selected quest ids
  - complete button
  - raw JSON 접기/펼치기

오른쪽: 실행 상태
  - WebSocket 연결 상태
  - request_id
  - selected leaf agent
  - latency
  - error code/message
```

초기 버전에서는 계정, 저장, 히스토리 DB를 만들지 않는다. 브라우저 session memory에 최근 요청 5개만 남긴다.

### 4.4 프론트엔드 데이터 흐름

1. 앱 시작 시 `GET /api/v1/agent-connection` 호출
2. manifest에서 WebSocket path와 지원 agent 목록을 읽음
3. 사용자가 payload를 편집하고 Send 클릭
4. `agent.request` envelope 생성
5. WebSocket으로 전송
6. `agent.response`면 결과 패널 업데이트
7. `agent.error`면 오류 패널 업데이트

프론트엔드는 LLM provider를 직접 알지 않는다. provider 설정은 백엔드 `.env`에서만 관리한다.

### 4.5 UI 원칙

- 첫 화면은 실제 사용 가능한 Quest Lab으로 시작한다.
- 큰 hero나 마케팅 문구는 넣지 않는다.
- 버튼은 명확한 명령만 둔다.
- 응답 JSON은 숨길 수 있게 한다.
- 오류는 개발자가 바로 볼 수 있도록 code/message/context를 보여준다.
- 모바일에서는 입력, 결과, trace를 탭으로 나눈다.

### 4.6 프론트엔드 구현 순서

1. Vite React TypeScript 프로젝트 생성
2. backend base URL 설정 추가
3. agent manifest fetch 구현
4. WebSocket client 구현
5. Quest request form 구현
6. Quest response panel 구현
7. Error/trace panel 구현
8. Playwright smoke test 추가

### 4.7 프론트엔드 검증

필수 테스트:

- manifest를 읽어서 agent option이 표시됨
- Send 클릭 시 `agent.request`가 전송됨
- `agent.response` 수신 시 quest card가 표시됨
- `agent.error` 수신 시 error panel이 표시됨
- WebSocket 연결 실패 시 재시도 버튼이 표시됨
- 약식 클리어 버튼 또는 진행 수량 입력으로 quest card가 cleared 상태로 바뀜

권장 smoke:

```bash
cd backend
uv run --env-file smoke-none.env.example python scripts/run_server.py

cd frontend
npm run test
npm run test:e2e
```

## 5. 작업 마일스톤

### Milestone 1: 백엔드 계약 고정

목표:

- README와 architecture plan을 최신 상태로 유지
- `QUESTFORGE_LLM_` 환경변수 문서화
- 현재 pytest와 smoke test 통과

완료 기준:

- `125 passed`
- WebSocket smoke `none` profile 통과

### Milestone 2: Quest Data Repository

목표:

- CSV loading 계층 추가
- agent가 샘플 데이터를 직접 읽지 않고 repository를 통해 사용

완료 기준:

- CSV row parsing test 통과
- production quest 후보 생성 test 통과

### Milestone 3: Frontend Quest Lab MVP

목표:

- React UI에서 WebSocket으로 quest request 전송
- 응답 퀘스트와 오류를 화면에서 확인

완료 기준:

- 로컬 백엔드와 연동 가능
- Playwright smoke에서 request/response 화면 확인

### Milestone 4: Agent Trace와 데모 품질

목표:

- 선택된 leaf agent, latency, fallback 여부 표시
- README에 데모 실행 순서 추가

완료 기준:

- 처음 보는 사람이 5분 안에 backend + frontend를 실행할 수 있음

## 6. 하지 않을 것

초기 버전에서는 다음을 넣지 않는다.

- 로그인/회원 기능
- DB 저장
- vector DB/RAG
- 관리자 페이지
- Unreal 클라이언트 코드
- 복잡한 quest editor
- 다국어 UI

이 항목들은 “동작하는 agent 데모”가 완성된 뒤에 판단한다.

## 7. 권장 다음 작업

바로 다음 작업은 `frontend/`를 새로 만들기보다, 백엔드 `quest_data` repository를 먼저 추가하는 것이다. 그래야 프론트엔드가 보여줄 데이터와 agent context가 안정된다.

그 다음 React Quest Lab을 붙이면, 백엔드와 프론트엔드가 같은 WebSocket 계약을 기준으로 자연스럽게 연결된다.
