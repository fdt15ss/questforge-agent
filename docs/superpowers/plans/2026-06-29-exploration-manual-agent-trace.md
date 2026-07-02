# 탐험 방문 완료형 전환 및 Agent Trace 패널 구현 계획

> **에이전트 작업자 안내:** 이 계획을 작업 단위로 실행할 때는 `superpowers:subagent-driven-development` 사용을 권장합니다. 대안으로 `superpowers:executing-plans`를 사용할 수 있습니다. 각 단계는 체크박스(`- [x]`) 형식으로 진행 상태를 추적합니다.

**목표:** 탐험 퀘스트를 방문 완료형 UX로 되돌리고, Quest Lab에 최근 agent 실행 trace 패널을 추가한다.

**아키텍처:** 백엔드는 exploration leaf agent의 `clear_condition`을 `manual` 모드와 방문/조사 완료 label로 생성한다. 프론트엔드는 exploration/manual 목표를 수량 카운터 대신 방문 목표로 렌더링한다. 또한 `agent.response`의 envelope metadata와 payload metadata를 요약하는 trace helper를 통해 Agent Trace 패널을 표시한다.

**기술 스택:** Python 3.12, Pydantic, pytest, TypeScript, React, Vitest, Vite.

---

### 작업 1: 탐험 퀘스트 방문 완료형 전환

**대상 파일:**
- 수정: `backend/src/agents/quest_generator/exploration_quest.py`
- 수정: `backend/tests/test_agent_leaf_behaviors.py`
- 수정: `frontend/src/lib/questLab.ts`
- 수정: `frontend/src/lib/questLab.test.ts`
- 수정: `frontend/src/components/QuestCard.tsx`

- [x] 탐험 퀘스트가 `clear_condition.mode == "manual"`을 사용하고, 구체적인 한국어 완료 label을 가지며, `required_quantity`에 의존하지 않는다는 백엔드 테스트를 작성한다.
- [x] `backend\.venv\Scripts\python.exe -m pytest backend\tests\test_agent_leaf_behaviors.py -q`를 실행해 RED 실패를 확인한다.
- [x] 탐험 payload 생성 로직이 방문/조사 완료형 `manual` label을 반환하도록 수정한다.
- [x] 대상 백엔드 테스트를 다시 실행해 GREEN 통과를 확인한다.
- [x] 탐험 manual 목표가 `0 / 1` 카운터 대신 방문 label로 표시되는지 검증하는 프론트 helper 테스트를 작성한다.
- [x] `pnpm.cmd test`를 실행해 RED 실패를 확인한다.
- [x] `QuestCard` 렌더링을 수정해 exploration/manual 목표를 방문 목표로 보여주고, 전용 완료 버튼 label을 사용한다.
- [x] 프론트 테스트를 다시 실행해 GREEN 통과를 확인한다.

### 작업 2: Agent Trace 패널 추가

**대상 파일:**
- 수정: `frontend/src/types/quest.ts`
- 수정: `frontend/src/lib/questLab.ts`
- 수정: `frontend/src/lib/questLab.test.ts`
- 수정: `frontend/src/App.tsx`
- 수정: `frontend/src/styles.css`

- [x] `AgentResponseEnvelope`를 trace summary로 변환하는 프론트 helper 테스트를 작성한다. summary에는 request id, agent, fallback 상태, provider/model, selected sub-agent, latency, raw metadata가 포함된다.
- [x] 프론트 테스트를 실행해 RED 실패를 확인한다.
- [x] envelope metadata 타입과 trace summary helper를 추가한다.
- [x] 퀘스트 생성, 샘플 로드, raw JSON 전송 응답 이후 App 상태에 최신 trace를 저장한다.
- [x] Quest Lab UI에 Agent Trace 패널을 추가한다.
- [x] 프론트 테스트와 빌드를 실행해 통과를 확인한다.

### 작업 3: 최종 검증

**대상 파일:**
- 새 production 파일 없음.

- [x] `backend\.venv\Scripts\python.exe -m pytest backend\tests -q`를 실행한다.
- [x] `frontend` 디렉터리에서 `C:\Users\user\.cache\codex-runtimes\codex-primary-runtime\dependencies\bin\pnpm.cmd test`를 실행한다.
- [x] `frontend` 디렉터리에서 `C:\Users\user\.cache\codex-runtimes\codex-primary-runtime\dependencies\bin\pnpm.cmd build`를 실행한다.
- [x] `git diff --stat`으로 변경 범위를 확인하고 요약한다.