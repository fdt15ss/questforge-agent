# Quest Lab Context Panel 설계 문서

## 배경

기존 Quest Lab의 `Main quest context` 옵션은 체크하면 요청 payload에 샘플 `current_main_quest`를 넣고, 체크를 끄면 제외하는 토글에 가까웠다. 그래서 사용자는 현재 메인 퀘스트, 보유 자원, 해금 장비, 탐험 후보지를 직접 바꿔 보면서 퀘스트 생성 결과를 테스트할 수 없었다.

이번 MVP에서는 Quest Lab을 단순 호출 버튼이 아니라, 퀘스트 생성 컨텍스트를 직접 편집하고 요청 JSON으로 확인할 수 있는 실험 도구로 다룬다.

## 목표

Quest Lab 화면에서 다음 값을 직접 설정할 수 있게 한다.

- 진행 단계와 플레이어 레벨
- 인벤토리 자원 수량
- 해금된 장비와 레시피
- 최근 이벤트 목록
- 현행 메인 퀘스트의 id, 제목, 설명, 목표, 진행도
- 탐험 퀘스트 생성에 사용할 탐험 후보지

사용자가 값을 바꾸면 Request JSON preview와 WebSocket `agent.request` payload가 같은 값으로 갱신되어야 한다.

## 데이터 흐름

```text
Quest Context form state
-> buildAgentRequest
-> payload.progression
-> payload.game_state
-> payload.current_main_quest
-> payload.recent_events
-> payload.exploration_targets
-> WebSocket agent.request
```

프론트엔드는 별도 백엔드 저장 API 없이 로컬 폼 상태만 가진다. Generate 버튼을 누를 때 현재 폼 상태를 기반으로 agent request를 만든다.

## 입력 형식

MVP에서는 빠른 실험을 위해 복잡한 테이블 편집기 대신 textarea 기반 line format을 사용한다.

- Inventory: `resource_id=quantity`
- Main objectives: `resource_id=required/current`
- Unlocked equipment: 한 줄에 장비 id 하나
- Unlocked recipes: 한 줄에 레시피 id 하나
- Recent events: 한 줄에 이벤트 문장 하나
- Exploration targets: `id|label|target_kind|related_resource_id`

`related_resource_id`는 선택값이다. 비워 두면 해당 필드는 payload에서 제외한다.

## 생성 시 동작

1. 사용자가 Quest Context 패널에서 값을 편집한다.
2. `buildAgentRequest`가 문자열 입력을 구조화된 payload로 변환한다.
3. `current_main_quest` 체크가 켜져 있으면 메인 퀘스트 컨텍스트가 포함된다.
4. `exploration_targets` 체크가 켜져 있으면 탐험 후보지가 포함된다.
5. Request JSON preview에 실제 전송될 payload가 표시된다.
6. Generate 버튼을 누르면 동일한 payload가 WebSocket으로 전송된다.

## 탐험 퀘스트 처리

탐험 퀘스트는 `exploration_targets`를 핵심 입력으로 사용한다. 각 후보지는 탐험 대상 id, 표시 이름, 대상 종류, 관련 자원 id를 가진다. 백엔드는 이 정보를 바탕으로 신호 조사, 장소 수색, 자원 단서 확보 같은 탐험 목표를 생성할 수 있다.

프론트엔드는 탐험 퀘스트 결과를 production/delivery와 같은 카드로 보여주되, `action_id` 기반 목표는 `Exploration Objective`로 표시한다. 수동 클리어만 가능한 탐험 목표는 Mark Cleared 버튼으로 테스트할 수 있다.

## 테스트 범위

- `buildAgentRequest`가 편집된 Quest Context 값을 payload에 반영하는지 검증한다.
- 탐험 퀘스트의 수동 클리어 동작을 검증한다.
- 탐험 objective label이 깨지지 않고 표시되는지 검증한다.
- TypeScript 빌드로 React 컴포넌트 연결과 타입 오류를 검증한다.

## 향후 개선

- textarea를 표 형태 편집기로 교체한다.
- 장비/레시피 id를 백엔드 카탈로그에서 선택할 수 있게 한다.
- 메인 퀘스트 objective를 추가/삭제 가능한 row UI로 바꾼다.
- 탐험 후보지에 위험도, 권장 장비, 예상 보상 힌트를 추가한다.
