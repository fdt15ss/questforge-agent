# 메인 퀘스트 연계형 한글 퀘스트 생성 설계

## 목표

퀘스트 생성기는 현재 연결된 LLM을 사용하더라도 서버가 통제 가능한 구조를 유지해야 한다.
응답의 `title`과 `description`은 기본적으로 한글로 생성되어야 하며, 요청 payload에 현재
메인 퀘스트가 들어오면 그 메인 퀘스트와 관련 있는 일일/주간/깜짝 퀘스트를 만들어야 한다.

이번 설계의 목표는 다음과 같다.

- `title`, `description`, `main_quest_link.reason`은 한글로 반환한다.
- payload에 `current_main_quest`가 있으면 결과 퀘스트에 `main_quest_link`를 포함한다.
- 요청에서 허용한 퀘스트 타입만 생성한다.
- 응답에서 각 퀘스트가 `daily`, `weekly`, `surprise` 중 무엇인지 명확히 알 수 있어야 한다.
- 기존 production quest 흐름을 유지하되, “생산 퀘스트”와 “일일/주간/깜짝” 개념을 분리한다.

## 추천안

가장 좋은 구조는 `Quest.type`을 `daily | weekly | surprise`로 바꾸고, 기존의 `production` 의미는
`domain` 필드로 분리하는 것이다.

```json
{
  "type": "daily",
  "domain": "production"
}
```

이 구조를 추천하는 이유는 두 가지다.

첫째, 사용자가 화면에서 보고 싶은 퀘스트 종류는 “생산 퀘스트”가 아니라 “일일 퀘스트인지,
주간 퀘스트인지, 깜짝 퀘스트인지”다. 따라서 UI badge와 완료 정책은 `type`을 보면 바로 알 수
있어야 한다.

둘째, `production`은 퀘스트의 운영 주기가 아니라 퀘스트의 내용 영역이다. 나중에 delivery,
exploration, economy 같은 영역이 생겨도 `domain`으로 확장하면 된다.

## 대안 비교

### 대안 A: `type`을 `daily | weekly | surprise`로 변경하고 `domain`을 추가한다

추천안이다.

```json
{
  "type": "weekly",
  "domain": "production"
}
```

장점:

- UI에서 badge를 바로 표시할 수 있다.
- 게임 로직에서 일일/주간/깜짝 완료 주기를 분리하기 쉽다.
- production, delivery 같은 내용 영역은 `domain`으로 확장 가능하다.

단점:

- 기존 `Quest.type == "production"`을 기대하던 테스트와 schema를 수정해야 한다.

### 대안 B: `type`은 `production`으로 유지하고 `cadence`를 추가한다

```json
{
  "type": "production",
  "cadence": "daily"
}
```

장점:

- 기존 schema 변경 폭이 작다.

단점:

- 사용자가 말하는 “무슨 퀘스트인지”는 `cadence`에 있고, `type`에는 없다.
- UI와 API에서 `type`이라는 이름이 계속 혼란스럽다.

### 대안 C: `quest_type`과 `domain`을 새로 두고 기존 `type`은 deprecated 처리한다

```json
{
  "type": "production",
  "quest_type": "daily",
  "domain": "production"
}
```

장점:

- 점진적 마이그레이션이 가능하다.

단점:

- 같은 의미의 필드가 여러 개라 API가 지저분해진다.
- 초반 프로젝트에서는 과한 호환성 비용이다.

## 최종 설계

대안 A를 채택한다.

`Quest.type`은 퀘스트 운영 타입을 뜻한다.

```python
Literal["daily", "weekly", "surprise"]
```

`Quest.domain`은 퀘스트 내용 영역을 뜻한다.

```python
Literal["production", "delivery", "exploration"] | None
```

초기 구현에서는 production quest generator만 다루므로 `domain`은 항상 `"production"`으로 둔다.

## Request 계약

WebSocket endpoint는 기존처럼 `/ws/agent`를 사용한다.

클라이언트는 `agent.request` envelope 안에 `payload`를 넣어 보낸다.

```json
{
  "type": "agent.request",
  "request_id": "request-quest-001",
  "session_id": "session-001",
  "client_id": "quest-lab",
  "agent": "quest_generator",
  "payload": {
    "sub_agent": "quest_generator.production_quest",
    "locale": "ko-KR",
    "current_main_quest": {
      "id": "main_restore_power_grid",
      "title": "전력망 복구",
      "description": "기지의 핵심 생산 라인을 다시 가동하기 위해 전력망을 복구한다.",
      "stage": "in_progress",
      "objectives": [
        {
          "target_item_id": "resource_copper_ingot",
          "quantity": 10
        },
        {
          "target_item_id": "resource_iron_ingot",
          "quantity": 8
        }
      ],
      "progress": {
        "resource_copper_ingot": 4,
        "resource_iron_ingot": 2
      }
    },
    "quest_generation_options": {
      "count": 5,
      "quest_types": ["daily", "weekly", "surprise"],
      "link_to_main_quest": true
    },
    "game_state": {
      "stage": "early",
      "inventory": {
        "resource_iron_ore": 12,
        "resource_copper_ore": 5,
        "resource_copper_ingot": 4
      },
      "unlocked_equipment": [
        "equipment_miner_machine",
        "equipment_smelter"
      ],
      "unlocked_recipes": [
        "recipe_smelt_iron",
        "recipe_smelt_copper"
      ],
      "active_equipment": [
        {
          "instance_id": "smelter-01",
          "equipment_id": "equipment_smelter",
          "status": "running",
          "recipe_id": "recipe_smelt_copper"
        }
      ]
    },
    "recent_events": ["power_grid_damaged", "smelter_unlocked"]
  }
}
```

### Request 필드 설명

`locale`

- 기본값은 `"ko-KR"`이다.
- `title`, `description`, `main_quest_link.reason`을 한글로 만들라는 신호다.
- 초기 구현에서는 다른 locale을 받더라도 한글 생성을 기본으로 유지한다.

`current_main_quest`

- 현재 진행 중인 메인 퀘스트 정보다.
- 이 값이 있으면 응답 퀘스트는 가능한 한 메인 퀘스트 objective, progress, description과 연결된다.

`quest_generation_options.count`

- 생성할 퀘스트 개수다.
- 기본값은 5다.
- 허용 범위는 1~10이다.

`quest_generation_options.quest_types`

- 생성 허용 타입 목록이다.
- 허용 값은 `"daily"`, `"weekly"`, `"surprise"`다.
- 값이 없으면 기본값은 `["daily", "weekly", "surprise"]`다.

`quest_generation_options.link_to_main_quest`

- `true`이면 응답에 `main_quest_link`를 포함한다.
- `current_main_quest`가 없으면 이 값이 `true`여도 `main_quest_link`는 생략될 수 있다.

`game_state`

- 선택 입력이다. 없으면 기존 `resources` 또는 backend CSV fallback context로 퀘스트를 만들 수 있어야 한다.
- 있으면 `game_state.inventory`를 현재 보유 아이템의 정식 위치로 사용한다.
- `resources`와 `game_state.inventory`가 둘 다 있으면 `game_state.inventory`를 우선한다.
- `unlocked_equipment`는 플레이어가 사용할 수 있는 설비 목록이다.
- `unlocked_recipes`는 플레이어가 사용할 수 있는 제작법 목록이다.
- `active_equipment`는 실제 배치되어 동작 중이거나 멈춘 설비 instance 목록이다.
- 생성기는 아직 모든 설비 상태를 복잡하게 시뮬레이션하지 않더라도, 최소한 해금 설비와 recipe 정보를 prompt/context에 포함해야 한다.

`resources`

- 이전 MVP payload와의 호환을 위한 legacy 필드다.
- 새 클라이언트는 `game_state.inventory`를 사용하는 것을 권장한다.

## Response 계약

응답 payload는 `quests` 배열과 `metadata`를 가진다.

```json
{
  "type": "agent.response",
  "request_id": "request-quest-001",
  "session_id": "session-001",
  "client_id": "quest-lab",
  "agent": "quest_generator",
  "payload": {
    "quests": [
      {
        "id": 1,
        "type": "daily",
        "domain": "production",
        "title": "구리괴 6개 제련",
        "description": "전력망 복구에 필요한 전도성 부품을 확보하기 위해 오늘은 부족한 구리괴 6개를 먼저 제련하세요.",
        "objectives": [
          {
            "target_item_id": "resource_copper_ingot",
            "quantity": 6
          }
        ],
        "clear_condition": {
          "mode": "objective_count",
          "target_item_id": "resource_copper_ingot",
          "required_quantity": 6
        },
        "main_quest_link": {
          "main_quest_id": "main_restore_power_grid",
          "main_quest_title": "전력망 복구",
          "relation_kind": "required_material",
          "reason": "메인 퀘스트의 구리괴 목표가 아직 부족하므로, 이 일일 퀘스트는 전력망 복구 재료 확보를 직접 돕습니다."
        }
      },
      {
        "id": 2,
        "type": "weekly",
        "domain": "production",
        "title": "전력망 복구 자재 묶음 확보",
        "description": "이번 주에는 전력망 복구에 필요한 철괴와 구리괴를 함께 확보해 기지의 생산 라인을 안정화하세요.",
        "objectives": [
          {
            "target_item_id": "resource_iron_ingot",
            "quantity": 8
          },
          {
            "target_item_id": "resource_copper_ingot",
            "quantity": 10
          }
        ],
        "clear_condition": {
          "mode": "objective_count",
          "target_item_id": "resource_iron_ingot",
          "required_quantity": 8
        },
        "main_quest_link": {
          "main_quest_id": "main_restore_power_grid",
          "main_quest_title": "전력망 복구",
          "relation_kind": "progress_support",
          "reason": "여러 재료를 한 번에 모으는 주간 목표로 메인 퀘스트 진행 속도를 높입니다."
        }
      },
      {
        "id": 3,
        "type": "surprise",
        "domain": "production",
        "title": "손상된 전선 긴급 보강",
        "description": "최근 전력망 손상 이벤트가 발생했습니다. 예비 구리 광석을 확보해 갑작스러운 수리 상황에 대비하세요.",
        "objectives": [
          {
            "target_item_id": "resource_copper_ore",
            "quantity": 5
          }
        ],
        "clear_condition": {
          "mode": "manual",
          "label": "긴급 보강 완료"
        },
        "main_quest_link": {
          "main_quest_id": "main_restore_power_grid",
          "main_quest_title": "전력망 복구",
          "relation_kind": "risk_buffer",
          "reason": "최근 이벤트를 반영해 전력망 복구 중 발생할 수 있는 추가 손상에 대비합니다."
        }
      }
    ],
    "metadata": {
      "generatedQuestTypes": ["daily", "weekly", "surprise"],
      "locale": "ko-KR",
      "mainQuestLinked": true,
      "llm": "used",
      "selectedAgent": "quest_generator",
      "selectedLeafAgent": "quest_generator.production_quest"
    }
  },
  "streams": []
}
```

## Quest schema 변경안

```python
class QuestClearCondition(BaseModel):
    mode: Literal["objective_count", "manual"]
    target_item_id: str | None = None
    required_quantity: int | None = Field(default=None, gt=0)
    label: str | None = None


class MainQuestLink(BaseModel):
    main_quest_id: str = Field(min_length=1)
    main_quest_title: str = Field(min_length=1)
    relation_kind: Literal[
        "required_material",
        "progress_support",
        "risk_buffer",
        "delivery_support",
    ]
    reason: str = Field(min_length=1)


class Quest(BaseModel):
    id: int = Field(gt=0)
    type: Literal["daily", "weekly", "surprise"]
    domain: Literal["production", "delivery", "exploration"] | None = None
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    objectives: list[QuestObjective] = Field(min_length=1)
    clear_condition: QuestClearCondition
    main_quest_link: MainQuestLink | None = None
```

## 생성 규칙

### 타입 선택

`quest_generation_options.quest_types`가 있으면 그 안에서만 생성한다.

예를 들어 요청이 아래와 같으면:

```json
{
  "quest_generation_options": {
    "count": 3,
    "quest_types": ["daily"]
  }
}
```

응답의 모든 퀘스트는 `"type": "daily"`여야 한다.

요청이 아래와 같으면:

```json
{
  "quest_generation_options": {
    "count": 4,
    "quest_types": ["weekly", "surprise"]
  }
}
```

응답은 `weekly`와 `surprise`만 사용한다.

### 기본 분배

`count`가 5이고 `quest_types`가 `["daily", "weekly", "surprise"]`이면 기본 분배는 다음을 권장한다.

- daily 2개
- weekly 2개
- surprise 1개

`count`가 3이면 다음을 권장한다.

- daily 1개
- weekly 1개
- surprise 1개

이 분배는 고정 규칙이 아니라 기본 정책이다. 메인 퀘스트 진행 상황과 recent event에 따라 surprise를
늘릴 수 있다.

### 메인 퀘스트 연계

`current_main_quest.objectives`와 `current_main_quest.progress`를 비교해 부족한 재료를 계산한다.

예:

```json
{
  "objectives": [
    {
      "target_item_id": "resource_copper_ingot",
      "quantity": 10
    }
  ],
  "progress": {
    "resource_copper_ingot": 4
  }
}
```

부족분은 `resource_copper_ingot` 6개다. daily quest는 이 부족분 일부 또는 전부를 직접 목표로 삼을 수 있다.
weekly quest는 여러 부족분을 묶을 수 있다. surprise quest는 recent event와 연결해 예비 자재, 긴급 수리,
위험 완충 목표를 만들 수 있다.

## LLM 역할

LLM은 전체 구조를 마음대로 만들지 않는다.

서버가 먼저 다음 값을 결정한다.

- quest count
- quest type
- domain
- objective target_item_id
- quantity
- clear_condition
- main_quest_link 기본 구조

LLM은 아래 값만 개선한다.

- title
- description
- main_quest_link.reason

LLM prompt에는 다음 조건을 명시한다.

- 한국어로 작성한다.
- JSON object만 반환한다.
- `id`, `type`, `domain`, `objectives`, `clear_condition`은 바꾸지 않는다.
- 요청에서 허용하지 않은 quest type을 만들지 않는다.
- `current_main_quest`가 있으면 description과 reason에 연결성을 설명한다.

## Fallback 규칙

LLM이 없거나 응답이 잘못되면 서버가 deterministic fallback을 반환한다.

fallback도 반드시 한글 title/description을 사용한다.

예:

```json
{
  "id": 1,
  "type": "daily",
  "domain": "production",
  "title": "구리괴 6개 확보",
  "description": "전력망 복구 진행에 필요한 resource_copper_ingot 6개를 확보하세요.",
  "objectives": [
    {
      "target_item_id": "resource_copper_ingot",
      "quantity": 6
    }
  ],
  "clear_condition": {
    "mode": "objective_count",
    "target_item_id": "resource_copper_ingot",
    "required_quantity": 6
  },
  "main_quest_link": {
    "main_quest_id": "main_restore_power_grid",
    "main_quest_title": "전력망 복구",
    "relation_kind": "required_material",
    "reason": "메인 퀘스트 진행에 필요한 부족 재료를 보충하는 퀘스트입니다."
  }
}
```

## 구현 계획

1. `schemas.py`에 `QuestClearCondition`, `MainQuestLink`를 추가한다.
2. `Quest.type`을 `daily | weekly | surprise`로 바꾸고 `domain`을 추가한다.
3. production quest graph의 count/type 결정 node를 확장한다.
4. `game_state.inventory`를 우선 읽고, 없으면 legacy `resources`를 읽는 helper를 추가한다.
5. `game_state.unlocked_equipment`, `game_state.unlocked_recipes`, `game_state.active_equipment`를 structured context로 정리한다.
6. `current_main_quest`를 읽어 부족분 계산 helper를 추가한다.
7. daily/weekly/surprise 분배 helper를 추가한다.
8. fallback title/description을 한글로 바꾼다.
9. LLM prompt를 한국어 응답과 메인퀘 연계 설명 중심으로 바꾼다.
10. response metadata에 `generatedQuestTypes`, `locale`, `mainQuestLinked`를 추가한다.
11. 기존 테스트를 새 schema에 맞게 갱신한다.
12. WebSocket smoke payload에 메인 퀘스트 연계 예시를 추가한다.

## 테스트 계획

- `Quest.type`이 `daily`, `weekly`, `surprise` 외 값이면 validation 실패
- 요청한 `quest_types` 밖의 타입이 응답에 나오면 실패
- `current_main_quest`가 있으면 `main_quest_link`가 생성됨
- `current_main_quest`가 없으면 일반 퀘스트 생성 가능
- `game_state`가 없어도 일반 퀘스트 생성 가능
- `game_state.inventory`가 있으면 legacy `resources`보다 우선 사용
- `game_state.unlocked_equipment`가 있으면 prompt/context에 반영
- fallback title/description이 한글 문장으로 생성됨
- LLM이 잘못된 타입을 반환하면 서버 fallback 또는 validation error 처리
- `count=5`, `quest_types=["daily", "weekly", "surprise"]`일 때 세 타입이 모두 포함됨
- `quest_types=["daily"]`일 때 모든 결과가 daily

## 자체 검토

- 메인 퀘스트 연계 요구사항을 `current_main_quest`와 `main_quest_link`로 반영했다.
- 일일/주간/깜짝 타입 요구사항을 `Quest.type`으로 명확히 반영했다.
- production이라는 기존 의미는 `domain`으로 옮겨 혼란을 줄였다.
- 한글 응답 요구사항을 LLM prompt와 fallback 규칙 양쪽에 반영했다.
- PostgreSQL, frontend UI, reward 지급, player progress 저장은 이번 범위에 포함하지 않았다.
