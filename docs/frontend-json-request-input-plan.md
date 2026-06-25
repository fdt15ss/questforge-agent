# Quest Lab JSON 입력/전송 계획 문서

## 배경

현재 Quest Lab은 화면의 Quest Context 폼 값을 기반으로 `buildAgentRequest`가 `agent.request` payload를 만들고, Generate 버튼을 누르면 WebSocket으로 전송한다. 이 방식은 필드별 실험에는 편하지만, 백엔드 로그나 외부 문서에서 가져온 JSON을 그대로 붙여 넣어 재현하기에는 번거롭다.

사용자는 다음 두 가지 흐름을 원한다.

- 팝업 창에 JSON을 붙여 넣으면 Quest Context 폼에 반영된다.
- 폼 반영이 어렵거나 전체 request를 재현해야 할 때는 JSON을 그대로 WebSocket으로 전송한다.

## 목표

Quest Lab에 JSON 기반 입력 경로를 추가한다.

- Request JSON preview 근처에 `JSON 가져오기` 버튼을 둔다.
- 버튼을 누르면 모달/팝업이 열리고 JSON textarea가 표시된다.
- 사용자는 `agent.request` 전체 JSON 또는 `payload` JSON만 붙여 넣을 수 있다.
- JSON이 Quest Context 폼 구조로 변환 가능하면 현재 폼에 반영한다.
- 변환이 어렵더라도 유효한 `agent.request`라면 바로 전송할 수 있다.
- 파싱 오류, schema 오류, 전송 오류는 화면에서 명확하게 보여준다.

## 추천 MVP: 팝업에서 검증 후 선택

MVP는 하나의 팝업 안에서 두 액션을 제공한다.

```text
JSON 가져오기 버튼
-> JSON 입력 모달
-> JSON parse
-> payload 추출
-> [폼에 반영] 또는 [이 JSON 그대로 전송]
```

### 버튼 구성

- `폼에 반영`: JSON payload를 Quest Context 폼 상태로 변환한다.
- `그대로 전송`: 입력한 JSON을 WebSocket으로 바로 보낸다.
- `취소`: 팝업을 닫고 기존 폼 상태를 유지한다.

`폼에 반영`을 기본 추천 액션으로 둔다. 사용자가 생성 조건을 눈으로 확인하고 수정할 수 있기 때문이다. `그대로 전송`은 재현 테스트나 schema 검증용 우회 경로로 둔다.

## 입력 허용 형식

### 1. 전체 agent.request

```json
{
  "type": "agent.request",
  "request_id": "quest-lab-...",
  "session_id": "quest-lab",
  "client_id": "quest-lab-frontend",
  "agent": "quest_generator",
  "payload": {
    "quest_generation_options": {
      "domain_counts": {
        "production": 1,
        "delivery": 1,
        "exploration": 1
      },
      "quest_types": ["daily", "weekly", "surprise"]
    },
    "progression": {
      "stage": "early_signal_recovery",
      "player_level": 6
    },
    "game_state": {
      "inventory": {
        "resource_iron_ore": 35,
        "resource_copper_wire": 12
      },
      "unlocked_equipment": ["equipment_miner", "equipment_smelter"],
      "unlocked_recipes": ["recipe_smelt_iron"]
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

### 2. payload만 입력

```json
{
  "quest_generation_options": {
    "domain_counts": {
      "production": 1,
      "delivery": 1,
      "exploration": 1
    },
    "quest_types": ["daily", "weekly", "surprise"]
  },
  "progression": {
    "stage": "early_signal_recovery",
    "player_level": 6
  },
  "game_state": {
    "inventory": {
      "resource_iron_ore": 35,
      "resource_copper_wire": 12
    },
    "unlocked_equipment": ["equipment_miner", "equipment_smelter"]
  },
  "recent_events": [
    "동쪽 능선 너머에서 약한 구조 신호가 반복 감지됐다."
  ]
}
```

payload만 입력한 경우 프론트엔드는 현재 WebSocket URL, `session_id`, `client_id`, `agent` 값을 사용해서 전체 `agent.request`를 만든다.

## 폼 반영 매핑 규칙

JSON payload를 Quest Context 폼으로 변환할 때 다음 규칙을 사용한다.

| payload 필드 | 프론트엔드 상태 |
| --- | --- |
| `quest_generation_options.domain_counts` | `domainCounts` |
| `quest_generation_options.quest_types` | `questTypes` |
| `progression.stage` | `questContext.progression.stage` |
| `progression.player_level` | `questContext.progression.playerLevel` |
| `game_state.inventory` | `inventoryText`, `resource_id=quantity` 라인 |
| `game_state.unlocked_equipment` | `unlockedEquipmentText`, 한 줄에 하나 |
| `game_state.unlocked_recipes` | `unlockedRecipesText`, 한 줄에 하나 |
| `recent_events` | `recentEventsText`, 한 줄에 하나 |
| `current_main_quest` | `mainQuestEnabled=true`, `mainQuest` |
| `current_main_quest.objectives + progress` | `objectivesText`, `resource_id=required/current` 라인 |
| `exploration_targets` | `explorationTargetsEnabled=true`, `explorationTargetsText` |

`current_main_quest`가 없으면 `mainQuestEnabled=false`로 설정한다. `exploration_targets`가 없으면 `explorationTargetsEnabled=false`로 설정한다.

## objectives 호환 규칙

현재 예시와 백엔드 schema가 섞일 수 있으므로 objective 수량은 다음 순서로 읽는다.

1. `required_quantity`
2. `quantity`
3. 값이 없으면 해당 objective는 폼 반영에서 제외

현재 진행도는 `current_quantity`가 있으면 우선 사용하고, 없으면 `current_main_quest.progress[target_item_id]`를 사용한다. 둘 다 없으면 `0`으로 본다.

## 그대로 전송 규칙

`그대로 전송`은 입력 JSON을 가능한 한 적게 변형한다.

- 전체 `agent.request`이면 `websocketUrl`만 현재 화면 값을 사용하고 body는 그대로 보낸다.
- payload만 입력하면 현재 Quest Lab 기본 envelope를 씌워 전송한다.
- `request_id`가 없으면 `quest-lab-${Date.now()}` 형태로 생성한다.
- `type`, `session_id`, `client_id`, `agent`가 없으면 Quest Lab 기본값을 채운다.

전송 전 최소 검증은 수행한다.

- JSON parse 가능 여부
- `payload` 존재 여부
- `payload.quest_generation_options` 존재 여부
- `domain_counts` 또는 `quest_types` 중 하나 이상 존재 여부

엄격한 백엔드 schema 검증은 서버 응답에 맡긴다. 프론트엔드는 사용자가 빠르게 실패를 재현할 수 있도록 전송 경로를 막지 않는다.

## 오류 처리

팝업 안에서 오류를 단계별로 표시한다.

- JSON parse 오류: `JSON 형식이 올바르지 않습니다.`
- payload 없음: `agent.request 전체 JSON이거나 payload JSON이어야 합니다.`
- Quest Generator 요청이 아님: `agent가 quest_generator가 아닙니다. 그대로 전송은 가능하지만 폼 반영은 제한됩니다.`
- 폼 반영 실패: `일부 필드를 Quest Context 폼으로 변환하지 못했습니다.`
- WebSocket 오류: 기존 `FRONTEND_WEBSOCKET_ERROR` 표시를 사용한다.

폼 반영 중 일부 필드만 실패하면 가능한 필드는 반영하고, 실패한 필드 목록을 warning으로 보여준다.

## UI 배치

Request JSON 영역 상단에 작은 액션 바를 둔다.

```text
요청 JSON
[JSON 가져오기] [현재 JSON 복사]
```

`JSON 가져오기`를 누르면 모달을 띄운다.

```text
JSON 가져오기
┌──────────────────────────────┐
│ textarea                     │
│                              │
└──────────────────────────────┘
[폼에 반영] [그대로 전송] [취소]
```

MVP에서는 별도 파일 업로드는 지원하지 않는다. 붙여넣기만 지원한다.

## 구현 단계

1. `frontend/src/lib/questLab.ts`에 JSON normalize/helper 함수를 추가한다.
   - `extractQuestRequestInput(jsonText)`
   - `payloadToQuestContext(payload)`
   - `buildAgentRequestFromRawJson(jsonText, websocketUrl)`
2. `frontend/src/lib/questLab.test.ts`에 변환 테스트를 추가한다.
   - 전체 `agent.request` 입력
   - payload만 입력
   - `quantity` objective 호환
   - 잘못된 JSON 오류
3. `frontend/src/App.tsx`에 JSON 입력 모달 상태를 추가한다.
   - `isJsonModalOpen`
   - `jsonDraft`
   - `jsonImportError`
4. `폼에 반영` 액션을 구현한다.
   - `domainCounts`, `questTypes`, `questContext`를 한 번에 갱신한다.
5. `그대로 전송` 액션을 구현한다.
   - 현재 `handleGenerate`와 같은 전송/응답 처리 흐름을 재사용한다.
6. 스타일을 추가한다.
   - 모달, textarea, 오류 메시지, 액션 버튼
7. `pnpm test`, `pnpm build`로 검증한다.

## 테스트 범위

- payload JSON이 Quest Context 폼 상태로 변환된다.
- 전체 `agent.request` JSON에서 payload를 추출한다.
- `objectives[].quantity`와 `objectives[].required_quantity`를 모두 처리한다.
- `current_main_quest.progress`가 `objectivesText`의 current 값으로 반영된다.
- `exploration_targets`가 `id|label|target_kind|related_resource_id` 형식으로 변환된다.
- 잘못된 JSON을 넣으면 사용자에게 오류가 표시된다.
- `그대로 전송`은 현재 WebSocket URL을 사용한다.

## 결정 사항

MVP에서는 팝업 입력 방식을 우선 구현한다. 다만 팝업 안에 `그대로 전송` 버튼을 같이 두어, 폼 변환이 어려운 JSON도 즉시 재현 테스트할 수 있게 한다.

이 방식은 사용자가 JSON을 붙여 넣고 결과를 보는 속도를 보장하면서도, 정상적인 실험은 Quest Context 폼과 Request JSON preview를 통해 눈으로 확인할 수 있게 해준다.
