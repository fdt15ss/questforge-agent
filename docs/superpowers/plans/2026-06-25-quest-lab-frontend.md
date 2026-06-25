# Quest Lab 프론트엔드 구현 계획

> **agent 작업자 참고:** 이 계획을 작업 단위로 실행할 때는 `superpowers:subagent-driven-development` 또는 `superpowers:executing-plans`를 사용한다. 각 단계는 진행 추적을 위해 체크박스(`- [ ]`) 형식을 사용한다.

**목표:** production, delivery, exploration 퀘스트를 요청하고, 표시하고, 필터링하고, 로컬에서 완료 조건을 시뮬레이션할 수 있는 React 기반 Quest Lab MVP를 만든다.

**아키텍처:** `frontend/` 아래에 독립 실행 가능한 Vite React 앱을 둔다. API 계약, 샘플 데이터, 퀘스트 상태 헬퍼, UI 컴포넌트를 분리해서 탐험 퀘스트 전용 렌더링이 카드 내부의 임시 분기보다 데이터 규칙을 통해 처리되게 한다.

**기술 스택:** React, TypeScript, Vite, Vitest, 일반 CSS, 브라우저 WebSocket API.

---

### 작업 1: 앱 기본 구조 만들기

**파일:**
- 생성: `frontend/package.json`
- 생성: `frontend/index.html`
- 생성: `frontend/tsconfig.json`
- 생성: `frontend/tsconfig.node.json`
- 생성: `frontend/vite.config.ts`
- 생성: `frontend/src/main.tsx`
- 생성: `frontend/src/App.tsx`
- 생성: `frontend/src/styles.css`

- [ ] `frontend/` 아래에 Vite React TypeScript 앱을 만든다.
- [ ] `dev`, `build`, `preview`, `test` 스크립트를 추가한다.
- [ ] 요청 빌더, 결과 영역, 디버그 영역을 가진 Quest Lab 기본 화면을 렌더링한다.

### 작업 2: 퀘스트 계약과 상태 헬퍼 만들기

**파일:**
- 생성: `frontend/src/types/quest.ts`
- 생성: `frontend/src/lib/questLab.ts`
- 생성: `frontend/src/lib/questLab.test.ts`

- [ ] `QuestFromServer`, `QuestLabItem`, 요청/응답 envelope, 도메인/타입 union을 정의한다.
- [ ] 서버 퀘스트를 `QuestLabItem`으로 변환하는 테스트를 작성한다.
- [ ] `objective_count`와 `manual` 완료 조건 시뮬레이션 테스트를 작성한다.
- [ ] exploration action id가 자원 목표가 아니라 탐험 목표로 표시되는지 테스트한다.

### 작업 3: 요청 빌더와 WebSocket 클라이언트 만들기

**파일:**
- 생성: `frontend/src/lib/wsClient.ts`
- 수정: `frontend/src/App.tsx`
- 수정: `frontend/src/styles.css`

- [ ] 도메인별 생성 개수, 퀘스트 타입, 메인 퀘스트 프리셋, 선택적 탐험 타겟 샘플을 payload 상태로 만든다.
- [ ] `agent.request`를 `ws://127.0.0.1:18000/ws/agent`로 전송한다.
- [ ] `agent.response`와 `agent.error`를 디버그 패널에 표시한다.
- [ ] 백엔드 exploration 생성기가 아직 구현되지 않은 동안에도 프론트 검증이 가능하도록 탐험 샘플 버튼을 유지한다.

### 작업 4: 퀘스트 결과 렌더링 만들기

**파일:**
- 생성: `frontend/src/components/QuestCard.tsx`
- 수정: `frontend/src/App.tsx`
- 수정: `frontend/src/styles.css`

- [ ] production, delivery, exploration 도메인 badge와 daily, weekly, surprise 타입 badge를 렌더링한다.
- [ ] exploration action objective는 인벤토리 자원이 아니라 “탐험 목표”로 표시한다.
- [ ] `main_quest_link.reason`을 눈에 잘 띄게 표시한다.
- [ ] `objective_count`용 로컬 진행도 조작 버튼과 exploration/manual 퀘스트용 수동 완료 버튼을 추가한다.
- [ ] 모든 도메인과 퀘스트 타입에 대한 필터를 추가한다.

### 작업 5: 검증

**파일:**
- 검증 중 결함이 발견될 때만 수정한다.

- [ ] 의존성이 없으면 `frontend/`에서 `pnpm install`을 실행한다.
- [ ] `pnpm test`를 실행한다.
- [ ] `pnpm build`를 실행한다.
- [ ] dev server를 시작한다.
- [ ] 로컬 dev URL에서 페이지가 열리는지 확인한다.
