# 메인 퀘스트 연계 일일/주간/깜짝 퀘스트 생성 계획

## 1. 정정된 도메인 규칙

`서브퀘스트`는 별도의 퀘스트 타입이 아니다. 이 프로젝트에서 실제로 생성되는 퀘스트 타입은 다음 세 가지로 제한한다.

- `daily`: 일일 퀘스트
- `weekly`: 주간 퀘스트
- `surprise`: 깜짝 퀘스트

메인 퀘스트와 연결되는 경우에도 퀘스트 타입이 `subquest`가 되지는 않는다. 대신 일일/주간/깜짝 퀘스트 JSON 안에 “현재 진행 중인 메인 퀘스트와 관련이 있다”는 연결 정보를 넣는다. 즉, 서브퀘스트는 UI나 기획 문서에서 설명할 수 있는 **표시 양식**이고, 데이터 모델의 실제 퀘스트 종류는 아니다.

## 2. 목표

현재 진행 중인 메인 퀘스트 정보를 `agent.request.payload`에 넣으면, QuestForge Agent가 그 메인 퀘스트와 연결된 일일/주간/깜짝 퀘스트를 몇 개 생성한다. LLM은 퀘스트 구조 전체를 마음대로 만들기보다, 서버가 검증 가능한 퀘스트 후보와 schema를 제공한 상태에서 메인 퀘스트와 관련된 `description` 문장을 생성하는 역할을 맡는다.

핵심 목표는 다음과 같다.

- 메인 퀘스트의 목적, 진행 상태, 요구 자원을 agent 입력으로 받는다.
- 생성 결과는 항상 `daily`, `weekly`, `surprise` 중 하나다.
- 각 퀘스트는 선택적으로 `main_quest_link`를 가진다.
- LLM은 “왜 이 일일/주간/깜짝 퀘스트가 메인 퀘스트와 연결되는지”를 설명하는 description을 작성한다.
- LLM 실패 시에도 schema가 맞는 fallback 퀘스트를 반환한다.

## 3. 권장 접근

### 추천안: 서버 후보 생성 + LLM description 생성

서버가 샘플 CSV와 현재 메인 퀘스트 목표를 바탕으로 일일/주간/깜짝 퀘스트 후보를 만들고, LLM은 후보별 설명문만 생성한다.

장점:

- 퀘스트 타입을 `daily`, `weekly`, `surprise`로 강제할 수 있다.
- LLM이 `subquest` 같은 존재하지 않는 타입을 만들어내는 일을 막을 수 있다.
- objectives, reward, 기간 같은 게임 로직 필드는 서버가 검증할 수 있다.
- 기존 FastAPI/WebSocket/LLM adapter 구조를 크게 흔들지 않는다.

단점:

- 후보 생성 규칙을 서버에 구현해야 한다.
- LLM의 역할은 description 중심으로 제한된다.

초기 MVP에서는 이 방식을 사용한다.

참고 CSV:

- `recipes.csv`: 레시피별 진행티어, 권장레벨범위, 목표수량, 보상룰 참조
- `scenario_context.csv`: 메인 퀘스트와 관련된 세계관, 진행 구간, LLM 설명 힌트
- `troubleshooting_rules.csv`: 문제 상황별 진행티어, 권장퀘스트타입, 보상룰 참조
- `quest_reward_rules.csv`: 일일/주간/깜짝 퀘스트 보상 기준
- `quest_generation_rules.csv`: 타입/티어별 생성 조건과 LLM 설명 지침

### 보류안: LLM이 퀘스트 전체 생성

LLM이 type, title, description, objectives까지 모두 만드는 방식은 보류한다. 빠르게 보일 수는 있지만, 존재하지 않는 quest type이나 게임 데이터에 없는 item id가 섞일 가능성이 크다.

## 4. 요청 Payload 설계

기존 payload에 `current_main_quest`와 `quest_generation_options`를 추가한다.

```json
{
  "sub_agent": "quest_generator.production_quest",
  "current_main_quest": {
    "id": "main_restore_power_grid",
    "title": "전력망 복구",
    "description": "기지의 핵심 생산 라인을 다시 가동하기 위해 전력망을 복구한다.",
    "stage": "in_progress",
    "objectives": [
      {
        "target_item_id": "copper_ingot",
        "quantity": 10
      },
      {
        "target_item_id": "iron_ingot",
        "quantity": 8
      }
    ],
    "progress": {
      "copper_ingot": 4,
      "iron_ingot": 2
    }
  },
  "quest_generation_options": {
    "count": 3,
    "quest_types": ["daily", "weekly", "surprise"],
    "link_to_main_quest": true,
    "description_style": "main_quest_linked"
  },
  "resources": {
    "iron_ore": 12,
    "copper_ore": 5
  },
  "recent_events": ["power_grid_damaged", "smelter_unlocked"]
}
```

### 필드 의미

| 필드 | 의미 |
| --- | --- |
| `current_main_quest.id` | 메인 퀘스트를 추적할 안정적인 id |
| `current_main_quest.title` | description 생성 시 중심 주제 |
| `current_main_quest.objectives` | 메인 퀘스트에 필요한 자원과 수량 |
| `current_main_quest.progress` | 이미 확보한 수량 |
| `quest_generation_options.count` | 생성할 퀘스트 개수 |
| `quest_generation_options.quest_types` | 허용할 실제 퀘스트 타입 |
| `quest_generation_options.link_to_main_quest` | 메인 퀘스트 연결 정보 포함 여부 |
| `quest_generation_options.description_style` | 설명문 생성 스타일 |

`current_main_quest`가 없으면 메인 퀘스트 연계 없이 일반 일일/주간/깜짝 퀘스트를 생성한다.

## 5. 응답 JSON 설계

응답 퀘스트의 `type`은 항상 `daily`, `weekly`, `surprise` 중 하나다.

```json
{
  "quests": [
    {
      "id": 101,
      "type": "daily",
      "title": "구리괴 6개 제련",
      "description": "전력망 복구에 필요한 전도성 부품을 만들기 위해 오늘은 부족한 구리괴를 먼저 확보하세요.",
      "objectives": [
        {
          "target_item_id": "copper_ingot",
          "quantity": 6
        }
      ],
      "clear_condition": {
        "mode": "objective_count",
        "target_item_id": "copper_ingot",
        "required_quantity": 6
      },
      "main_quest_link": {
        "main_quest_id": "main_restore_power_grid",
        "main_quest_title": "전력망 복구",
        "relation_kind": "required_material",
        "reason": "메인 퀘스트 목표 copper_ingot의 부족분을 채우기 위한 일일 퀘스트"
      }
    },
    {
      "id": 102,
      "type": "surprise",
      "title": "예비 전선 재료 확보",
      "description": "전력망 복구 도중 추가 손상이 발견될 수 있으니, 즉시 사용할 구리 재료를 조금 더 확보하세요.",
      "objectives": [
        {
          "target_item_id": "copper_ore",
          "quantity": 5
        }
      ],
      "clear_condition": {
        "mode": "manual",
        "label": "깜짝 상황 대응 완료"
      },
      "main_quest_link": {
        "main_quest_id": "main_restore_power_grid",
        "main_quest_title": "전력망 복구",
        "relation_kind": "risk_buffer",
        "reason": "최근 이벤트를 반영한 깜짝 퀘스트"
      }
    }
  ],
  "metadata": {
    "main_quest_id": "main_restore_power_grid",
    "generated_quest_types": ["daily", "surprise"],
    "description_source": "llm"
  }
}
```

## 6. 약식 클리어 조건

프론트엔드 MVP에서는 실제 게임 인벤토리나 서버 저장소와 연결하지 않고, 퀘스트 JSON에 들어 있는 `clear_condition`을 기준으로 로컬에서 완료 여부를 판정한다. 이 값은 데모와 UI 검증을 위한 약식 조건이며, 정식 게임 연동 단계에서 서버 판정이나 게임 클라이언트 이벤트로 대체할 수 있다.

초기 clear condition은 두 가지만 둔다.

| mode | 의미 | 프론트엔드 처리 |
| --- | --- | --- |
| `objective_count` | 특정 아이템 수량을 채우면 완료 | 사용자가 진행 수량을 입력하거나 `+1` 버튼으로 수량을 올림 |
| `manual` | 사용자가 완료 버튼을 누르면 완료 | `완료 처리` 버튼을 누르면 즉시 cleared |

예시:

```json
{
  "clear_condition": {
    "mode": "objective_count",
    "target_item_id": "copper_ingot",
    "required_quantity": 6
  }
}
```

```json
{
  "clear_condition": {
    "mode": "manual",
    "label": "깜짝 상황 대응 완료"
  }
}
```

프론트엔드는 다음 상태만 관리한다.

```json
{
  "quest_id": 101,
  "status": "in_progress",
  "progress": {
    "copper_ingot": 4
  },
  "cleared_at": null
}
```

완료 판정:

- `objective_count`: `progress[target_item_id] >= required_quantity`이면 `cleared`
- `manual`: 사용자가 완료 버튼을 누르면 `cleared`

초기 버전에서는 완료 상태를 브라우저 메모리나 `localStorage`에만 저장한다. 백엔드 DB 저장, 보상 지급, 계정별 진행도 동기화는 넣지 않는다.

## 7. Schema 변경안

현재 `Quest.type`은 `production`, `tutorial`, `exploration`, `delivery`로 되어 있다. 새 방향에서는 이 값을 퀘스트의 실행 타입이 아니라 노출/운영 타입으로 바꾼다.

변경할 모델:

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
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    objectives: list[QuestObjective] = Field(min_length=1)
    clear_condition: QuestClearCondition
    main_quest_link: MainQuestLink | None = None
```

선택적으로 내부 분류가 필요하면 `domain` 필드를 따로 둔다.

```python
domain: Literal["production", "delivery"] | None = None
```

이렇게 하면 “일일 퀘스트이면서 생산 목표를 가진다”처럼 운영 타입과 게임 목표 성격을 분리할 수 있다.

## 8. Agent 흐름

```text
agent.request
  -> protocol validation
  -> QuestGeneratorAgent
  -> DailyWeeklySurpriseQuestBuilder
  -> MainQuestLink 생성
  -> clear_condition 생성
  -> LLM description generation
  -> QuestResponse schema validation
  -> agent.response
```

기존 `ProductionQuestAgent`, `DeliveryQuestAgent`는 내부 domain 처리 용도로 남길 수 있지만, 최종 응답의 `type`은 `daily`, `weekly`, `surprise`만 사용한다.

## 9. 후보 생성 규칙

`DailyWeeklySurpriseQuestBuilder`를 새 서비스로 둔다.

역할:

- 메인 퀘스트 objective의 부족분을 계산한다.
- 부족분과 최근 이벤트를 바탕으로 후보 목표를 만든다.
- `recipes.csv`의 `진행티어`, `일일목표수량`, `주간목표수량`, `깜짝목표수량`을 참고한다.
- 우주선 제작 메인 퀘스트에서는 원재료에서 `resource_scout_spaceship`까지 이어지는 선행 레시피 체인을 따라 후보를 고른다.
- `scenario_context.csv`에서 진행 구간, 주제, 관련 자원, 관련 레시피가 맞는 행을 골라 description context로 붙인다.
- `quest_generation_rules.csv`로 어떤 타입의 퀘스트를 만들지 고른다.
- `quest_reward_rules.csv`로 보상 규모를 결정한다.
- 후보마다 `daily`, `weekly`, `surprise` 중 하나를 부여한다.
- `main_quest_link`를 생성한다.
- `clear_condition`을 생성한다.
- LLM에게 넘길 description context를 만든다.

초기 규칙:

| 조건 | 생성 타입 | 예시 |
| --- | --- | --- |
| 부족분이 작고 즉시 처리 가능 | `daily` | 오늘 필요한 구리괴 6개 제련 |
| 부족분이 크거나 여러 objective를 묶어야 함 | `weekly` | 이번 주 전력망 복구 재료 3종 확보 |
| 최근 이벤트가 위험/기회 상황을 나타냄 | `surprise` | 갑작스런 전력 불안정 대응 재료 확보 |

`count`가 3이면 기본 비율은 다음처럼 둔다.

- daily 1개
- weekly 1개
- surprise 1개

사용자가 `quest_types`를 제한하면 허용된 타입 안에서만 생성한다.

## 10. LLM Prompt 정책

LLM에게는 구조 생성이 아니라 description 생성만 요청한다.

입력:

- main quest summary
- generated quest id/type/title/objectives
- main_quest_link relation kind/reason
- recent events

출력:

```json
{
  "descriptions": [
    {
      "quest_id": 101,
      "description": "전력망 복구에 필요한 전도성 부품을 만들기 위해 오늘은 부족한 구리괴를 먼저 확보하세요."
    }
  ]
}
```

프롬프트 규칙:

- JSON object만 반환
- quest_id는 서버가 준 id만 사용
- type/title/objectives/main_quest_link는 수정하지 않음
- clear_condition은 수정하지 않음
- description은 한국어 한 문장
- 메인 퀘스트 title 또는 목적과 연결되는 이유를 포함
- `서브퀘스트`라는 단어를 type처럼 쓰지 않음

## 11. Fallback 정책

LLM이 실패하면 서버가 deterministic description을 만든다.

예시:

```text
{main_quest_title} 진행에 필요한 {target_item_id} {quantity}개를 확보하기 위한 {quest_type_label}입니다.
```

타입별 label:

- `daily`: 일일 퀘스트
- `weekly`: 주간 퀘스트
- `surprise`: 깜짝 퀘스트

fallback metadata:

```json
{
  "description_source": "fallback",
  "fallback": true
}
```

## 12. 프론트엔드 반영

Quest Lab 요청 폼에 다음 입력을 추가한다.

- Main Quest preset 선택
- Main Quest JSON 편집 영역
- 생성 개수 선택
- 생성 타입 체크박스: 일일, 주간, 깜짝
- “메인 퀘스트와 연결” 토글
- 약식 클리어 방식 선택: 목표 수량 / 수동 완료

결과 패널에는 다음 정보를 표시한다.

- 퀘스트 타입 badge: 일일/주간/깜짝
- 메인 퀘스트 title
- `main_quest_link.reason`
- 클리어 조건과 진행 상태
- `+1`, `최대치`, `완료 처리` 같은 데모용 버튼
- LLM description
- fallback 여부

UI 문구에서는 필요하면 “메인 퀘스트 연계 퀘스트”라고 표현한다. 데이터 타입이나 API field에서는 `subquest`를 쓰지 않는다.

## 13. 구현 순서

### 1단계: Schema 정리

- `Quest.type`을 `daily`, `weekly`, `surprise`로 변경
- `MainQuestLink` 모델 추가
- `QuestClearCondition` 모델 추가
- `domain`이 필요하면 optional field로 분리
- 기존 테스트를 새 타입 기준으로 갱신

완료 기준:

- `daily`, `weekly`, `surprise` 외 타입은 validation 실패
- `main_quest_link`가 없어도 기존 일반 퀘스트 응답 가능
- `clear_condition.mode`가 `objective_count` 또는 `manual`이 아니면 validation 실패

### 2단계: 요청 옵션 모델 추가

- `MainQuestContext` 모델 추가
- `QuestGenerationOptions` 모델 추가
- count 범위는 1~5로 제한
- `quest_types`는 `daily`, `weekly`, `surprise`만 허용

완료 기준:

- 올바른 main quest payload validation 통과
- `subquest` type 입력 시 validation 실패

### 3단계: 후보 생성 서비스 추가

- `DailyWeeklySurpriseQuestBuilder` 추가
- 메인 퀘스트 objective와 progress로 부족분 계산
- daily/weekly/surprise 후보 생성
- `main_quest_link` 생성
- `clear_condition` 생성

완료 기준:

- 메인 퀘스트 입력 1개에서 요청 count만큼 퀘스트 생성
- 모든 결과 type이 `daily`, `weekly`, `surprise` 중 하나
- 모든 결과에 약식 클리어 조건 포함

### 4단계: LLM description 생성

- description 생성 prompt 추가
- LLM 응답 JSON 파싱
- quest_id 기준으로 description 병합
- 실패 시 fallback description 사용

완료 기준:

- LLM 정상 응답이면 `description_source=llm`
- LLM 실패면 `description_source=fallback`
- LLM이 반환한 임의 type은 무시

### 5단계: Agent 연결

- `current_main_quest`가 있을 때 메인 퀘스트 연계 흐름 사용
- 없을 때는 일반 일일/주간/깜짝 퀘스트 생성
- WebSocket smoke payload에 main quest linked case 추가

완료 기준:

- 일반 퀘스트 smoke 통과
- 메인 퀘스트 연계 퀘스트 smoke 통과

### 6단계: 프론트엔드 Quest Lab 반영

- Main Quest preset 추가
- 일일/주간/깜짝 체크박스 추가
- 결과 카드에 type badge와 main quest link 표시
- 결과 카드에 약식 클리어 UI 추가

완료 기준:

- UI에서 main quest payload를 보내고 관련 일일/주간/깜짝 퀘스트 확인
- UI에서 목표 수량 또는 수동 완료로 퀘스트 cleared 상태 확인

## 14. 테스트 계획

백엔드 테스트:

- `Quest.type` 허용값 테스트
- `MainQuestLink` schema validation
- `QuestGenerationOptions.quest_types` validation
- 부족분 계산 테스트
- daily/weekly/surprise 후보 생성 테스트
- clear condition 생성 테스트
- LLM description 병합 테스트
- LLM 실패 fallback 테스트
- WebSocket main quest linked request/response 테스트

프론트엔드 테스트:

- main quest preset 선택
- quest type checkbox 변경
- response card에 일일/주간/깜짝 badge 표시
- main quest link 표시
- objective_count 진행도 증가 시 cleared 표시
- manual 완료 버튼 클릭 시 cleared 표시
- fallback badge 표시

## 15. 범위 제외

초기 버전에서는 다음을 하지 않는다.

- `subquest`라는 실제 quest type 추가
- 메인 퀘스트 DB 저장
- 플레이어별 진행도 저장
- 서버 기반 퀘스트 클리어 판정
- 보상 지급 처리
- 여러 메인 퀘스트 동시 최적화
- LLM이 objectives를 새로 만드는 기능
- LLM이 quest type을 결정하는 기능

이 기능의 첫 목표는 “현재 진행 중인 메인 퀘스트와 자연스럽게 연결된 일일/주간/깜짝 퀘스트 목록”을 안정적으로 반환하는 것이다.
