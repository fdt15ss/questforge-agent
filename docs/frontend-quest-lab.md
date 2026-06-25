# Quest Lab 프론트엔드 문서

## 개요

Quest Lab 프론트엔드는 QuestForge 백엔드가 생성한 퀘스트를 개발자가 빠르게 요청하고 검증하기 위한 React 기반 MVP입니다. 이 화면은 실제 플레이어용 퀘스트 보드라기보다, 퀘스트 생성 API의 요청 payload, 응답 JSON, 카드 렌더링, 완료 조건 시뮬레이션을 한 자리에서 확인하는 실험실 역할을 합니다.

현재 프론트엔드는 production, delivery, exploration 세 도메인을 모두 UI에서 다룰 수 있습니다. 다만 백엔드에는 아직 exploration leaf agent가 구현되지 않았으므로, 탐험 퀘스트 UI는 `Load Exploration Sample` 버튼으로 먼저 검증할 수 있게 되어 있습니다.

## 위치

프론트엔드 앱은 다음 경로에 있습니다.

```text
frontend/
```

주요 파일은 다음과 같습니다.

```text
frontend/src/App.tsx
frontend/src/components/QuestCard.tsx
frontend/src/lib/questLab.ts
frontend/src/lib/wsClient.ts
frontend/src/types/quest.ts
frontend/src/styles.css
```

## 실행 방법

프론트엔드만 실행하려면 다음 명령을 사용합니다.

```powershell
cd C:\potenup3\PJ-final\factory-space\.publish\questforge-agent\frontend
pnpm install
pnpm dev -- --port 5173
```

브라우저에서 아래 주소를 엽니다.

```text
http://127.0.0.1:5173/
```

만약 `pnpm` 명령이 잡히지 않는 환경이라면 Codex 번들 pnpm을 직접 사용할 수 있습니다.

```powershell
cd C:\potenup3\PJ-final\factory-space\.publish\questforge-agent\frontend
C:\Users\user\.cache\codex-runtimes\codex-primary-runtime\dependencies\bin\pnpm.cmd install
C:\Users\user\.cache\codex-runtimes\codex-primary-runtime\dependencies\bin\pnpm.cmd dev -- --port 5173
```

## 백엔드와 함께 실행하기

`Generate Quests` 버튼으로 실제 백엔드에 요청하려면 백엔드 서버도 실행해야 합니다.

다른 터미널에서 다음 명령을 실행합니다.

```powershell
cd C:\potenup3\PJ-final\factory-space\.publish\questforge-agent\backend
uv sync
uv run python scripts/run_server.py
```

기본 백엔드 WebSocket 주소는 다음과 같습니다.

```text
ws://127.0.0.1:18000/ws/agent
```

프론트의 `WebSocket URL` 입력값도 기본적으로 이 주소를 사용합니다.

## 화면 구성

### Request Builder

왼쪽 패널은 백엔드로 보낼 퀘스트 생성 요청을 구성합니다.

- `WebSocket URL`: 백엔드 WebSocket 주소입니다.
- `Domain Counts`: 도메인별 생성 개수입니다.
  - `production`
  - `delivery`
  - `exploration`
- `Quest Types`: 생성할 운영 타입입니다.
  - `daily`
  - `weekly`
  - `surprise`
- `Main quest context`: 메인 퀘스트 맥락을 payload에 포함할지 결정합니다.
- `Exploration target hints`: 탐험 후보 힌트를 payload에 포함할지 결정합니다.
- `Generate Quests`: 현재 설정으로 백엔드에 `agent.request`를 보냅니다.
- `Load Exploration Sample`: 백엔드 없이 탐험 퀘스트 카드 표시를 검증합니다.

### Quest Results

오른쪽 영역은 생성된 퀘스트를 카드로 보여줍니다.

각 카드에는 다음 정보가 표시됩니다.

- 도메인 badge
- 퀘스트 타입 badge
- 로컬 상태 badge
- 제목과 설명
- 메인 퀘스트 연결 이유
- 목표 목록
- 완료 조건
- 보상 목록

상단 필터로 도메인과 타입을 좁혀 볼 수 있습니다.

### Debug JSON

하단 영역은 디버깅용 JSON을 보여줍니다.

- `Request JSON`: 프론트가 만든 요청 payload입니다.
- `Response / Error JSON`: 백엔드 응답 또는 프론트 WebSocket 오류입니다.

Quest Lab에서 가장 중요한 영역입니다. 카드가 이상하게 보일 때 실제 JSON이 어떻게 내려왔는지 바로 확인할 수 있습니다.

## 퀘스트 데이터 처리 방식

프론트는 백엔드 응답 원본과 로컬 UI 상태를 분리합니다.

```ts
type QuestLabItem = {
  quest: QuestFromServer;
  status: "generated" | "testing" | "cleared";
  progress: Record<string, number>;
  selected: boolean;
  receivedAt: string;
};
```

`quest`는 백엔드가 내려준 원본 퀘스트입니다. 프론트는 이 값을 직접 바꾸지 않고, `status`와 `progress` 같은 로컬 상태만 덧붙입니다.

이 구조를 쓰는 이유는 다음과 같습니다.

- 백엔드 계약과 프론트 UI 상태가 섞이지 않습니다.
- Quest Lab에서 진행도와 완료 여부를 안전하게 시뮬레이션할 수 있습니다.
- 나중에 실제 플레이어용 Quest Board로 확장할 때 서버 저장 상태와 로컬 UI 상태를 분리하기 쉽습니다.

## 탐험 퀘스트 처리 방식

탐험 퀘스트는 다음 조건으로 판단합니다.

```ts
quest.domain === "exploration"
```

탐험 퀘스트는 생산/배송 퀘스트와 다르게 자원 수량을 모으는 목표가 아닐 수 있습니다. 그래서 프론트는 `exploration_`으로 시작하는 objective id를 자원명처럼 표시하지 않고 “탐사 목표”로 표시합니다.

예시:

```json
{
  "target_item_id": "exploration_signal_ping",
  "quantity": 1
}
```

Quest Lab에서는 이 목표를 다음처럼 취급합니다.

```text
탐사 목표: Signal Ping
```

탐험 퀘스트의 완료 조건은 MVP 기준으로 대부분 `manual`을 사용합니다.

```json
{
  "mode": "manual",
  "label": "탐사 확인 완료"
}
```

이 경우 카드에는 `완료 처리` 버튼이 표시됩니다. 버튼을 누르면 프론트 로컬 상태만 `cleared`로 바뀝니다. 실제 서버 저장이나 보상 지급은 아직 하지 않습니다.

## 완료 조건 처리

Quest Lab은 두 가지 완료 조건을 처리합니다.

### objective_count

특정 목표 수량이 요구량 이상이면 완료됩니다.

```json
{
  "mode": "objective_count",
  "target_item_id": "resource_iron_plate",
  "required_quantity": 5
}
```

카드에서는 `+1`, `최대치`, 초기화 버튼으로 진행도를 시뮬레이션합니다.

### manual

사용자가 직접 완료 버튼을 누르면 완료됩니다.

```json
{
  "mode": "manual",
  "label": "탐사 확인 완료"
}
```

탐험 퀘스트, 깜짝 상황, 조사형 목표에 적합합니다.

## 백엔드 exploration 미구현 상태

현재 프론트는 exploration 도메인을 지원하지만, 백엔드 생성기는 아직 production/delivery만 실제 생성합니다.

따라서 다음 요청을 보내도 백엔드 구현 전에는 exploration 퀘스트가 나오지 않을 수 있습니다.

```json
{
  "quest_generation_options": {
    "domain_counts": {
      "production": 1,
      "delivery": 1,
      "exploration": 1
    }
  }
}
```

탐험 퀘스트 UI를 먼저 확인하려면 `Load Exploration Sample` 버튼을 사용합니다.

백엔드 쪽 구현 계획은 다음 문서를 기준으로 합니다.

```text
docs/superpowers/specs/2026-06-25-exploration-quest-generation-design.md
```

## 테스트와 빌드

프론트엔드 테스트를 실행합니다.

```powershell
cd C:\potenup3\PJ-final\factory-space\.publish\questforge-agent\frontend
pnpm test
```

프로덕션 빌드를 확인합니다.

```powershell
pnpm build
```

현재 테스트는 `frontend/src/lib/questLab.test.ts`에 있으며 다음 동작을 검증합니다.

- 백엔드 퀘스트를 `QuestLabItem`으로 변환
- `objective_count` 완료 조건 처리
- `manual` 완료 조건 처리
- 탐험 action id를 “탐사 목표”로 표시

## 문제 해결

### pnpm 명령을 찾을 수 없음

번들 pnpm을 직접 실행합니다.

```powershell
C:\Users\user\.cache\codex-runtimes\codex-primary-runtime\dependencies\bin\pnpm.cmd install
```

### 백엔드 연결 실패

다음을 확인합니다.

- 백엔드 서버가 실행 중인지 확인합니다.
- 프론트의 `WebSocket URL`이 `ws://127.0.0.1:18000/ws/agent`인지 확인합니다.
- 백엔드 포트를 바꿨다면 프론트 입력값도 같은 포트로 바꿉니다.

### exploration 퀘스트가 생성되지 않음

아직 백엔드 exploration leaf agent가 구현되지 않았기 때문입니다. UI만 확인하려면 `Load Exploration Sample` 버튼을 사용합니다.

### esbuild build script 승인 오류

pnpm이 `esbuild` 빌드 승인을 요구할 수 있습니다.

```powershell
pnpm approve-builds
```

화면에서 `esbuild`를 선택하고 승인한 뒤 다시 실행합니다.

## 향후 작업

프론트 MVP 이후 자연스러운 다음 작업은 다음과 같습니다.

- 백엔드 `quest_generator.exploration_quest` 구현
- Quest Lab에서 `exploration_targets` JSON 직접 편집 기능 추가
- 응답 metadata 표시 개선
- backend manifest를 읽어 사용 가능한 leaf agent 자동 표시
- 실제 플레이어용 Quest Board와 Quest Lab 분리
