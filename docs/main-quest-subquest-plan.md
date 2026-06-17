# 진행 중인 메인 퀘스트 연계 서브퀘스트 생성 계획

## 1. 목표

현재 진행 중인 메인 퀘스트 정보를 `agent.request.payload`에 넣으면, QuestForge Agent가 그 메인 퀘스트와 이어지는 서브퀘스트를 여러 개 생성한다. LLM은 서브퀘스트의 전체 구조를 마음대로 만들기보다, 서버가 검증 가능한 후보와 schema를 제공한 상태에서 메인 퀘스트와 관련된 `description` 문장을 생성하는 역할을 맡는다.

핵심 목표는 다음과 같다.

- 메인 퀘스트의 목적, 진행 상태, 요구 자원을 agent 입력으로 받는다.
- 메인 퀘스트와 연관된 생산/납품 서브퀘스트를 2~5개 생성한다.
- 각 서브퀘스트 description은 “왜 이 일이 메인 퀘스트에 필요한지”를 설명한다.
- LLM 실패 시에도 schema가 맞는 fallback 서브퀘스트를 반환한다.

## 2. 권장 접근

### 추천안: 서버 후보 선택 + LLM description 생성

서버가 샘플 CSV와 기존 quest 후보를 바탕으로 서브퀘스트 후보를 만들고, LLM은 후보별 설명문만 생성한다.

장점:

- 퀘스트 id, type, objectives를 서버가 검증할 수 있다.
- LLM이 엉뚱한 item id나 수량을 만들어내는 위험이 줄어든다.
- 현재 `ProductionQuestAgent`와 `QuestAgentService` 구조를 크게 바꾸지 않아도 된다.
- fallback을 만들기 쉽다.

단점:

- LLM의 창의성은 description 중심으로 제한된다.
- 후보 생성 규칙을 서버에 직접 구현해야 한다.

초기 MVP에서는 이 방식을 사용한다.

### 보류안: LLM이 서브퀘스트 전체 생성

LLM이 title, description, objectives까지 모두 만든 뒤 Pydantic schema로 검증한다.

이 방식은 데모는 빠르지만, 존재하지 않는 자원 id나 게임 규칙에 맞지 않는 목표가 나올 수 있다. 프로젝트의 강점이 “게임 데이터 기반 agent”라는 점을 보여주기에는 추천하지 않는다.

## 3. 요청 Payload 설계

기존 payload에 `current_main_quest`와 `subquest_options`를 추가한다.

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
  "subquest_options": {
    "count": 3,
    "types": ["production", "delivery"],
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
| `current_main_quest.objectives` | 필요한 자원과 수량 |
| `current_main_quest.progress` | 이미 확보한 수량 |
| `subquest_options.count` | 생성할 서브퀘스트 개수 |
| `subquest_options.types` | 허용할 서브퀘스트 타입 |
| `subquest_options.description_style` | 설명문 생성 스타일 |

`current_main_quest`가 없으면 기존 production/delivery quest 생성 흐름을 그대로 사용한다.

## 4. 응답 JSON 설계

기존 `Quest` schema에 메인 퀘스트 연결 정보를 추가한다.

```json
{
  "quests": [
    {
      "id": 101,
      "type": "production",
      "title": "구리괴 6개 제련",
      "description": "전력망 복구에 필요한 전도성 부품을 만들기 위해 부족한 구리괴를 먼저 확보하세요.",
      "objectives": [
        {
          "target_item_id": "copper_ingot",
          "quantity": 6
        }
      ],
      "parent_quest_id": "main_restore_power_grid",
      "relation": {
        "kind": "required_material",
        "reason": "메인 퀘스트 목표 copper_ingot의 부족분을 채우기 위한 서브퀘스트"
      }
    }
  ],
  "metadata": {
    "main_quest_id": "main_restore_power_grid",
    "subquest_count": 3,
    "description_source": "llm"
  }
}
```

### Schema 변경

`Quest`에 다음 optional field를 추가한다.

- `parent_quest_id: str | None`
- `relation: QuestRelation | None`

새 모델:

- `MainQuestContext`
- `SubquestOptions`
- `QuestRelation`

초기에는 기존 클라이언트 호환성을 위해 새 필드를 optional로 둔다.

## 5. Agent 흐름

```text
agent.request
  -> protocol validation
  -> QuestGeneratorAgent
  -> ProductionQuestAgent 또는 DeliveryQuestAgent
  -> MainQuestContext 추출
  -> SubquestCandidateBuilder
  -> LLM description generation
  -> QuestResponse schema validation
  -> agent.response
```

### SubquestCandidateBuilder

새로운 작은 서비스로 둔다.

역할:

- 메인 퀘스트 objective의 부족분을 계산한다.
- `resources`, `recipes.csv`, `equipment.csv`를 참고해 필요한 생산/납품 후보를 만든다.
- `subquest_options.count`만큼 후보를 고른다.
- title/objectives/relation은 서버가 만든다.
- description은 LLM에 맡긴다.

처음에는 복잡한 recipe graph를 만들지 않고, 다음 규칙만 사용한다.

1. 메인 퀘스트 objective에 있는 item을 우선 선택한다.
2. progress가 있으면 부족한 수량만 계산한다.
3. 사용자가 이미 가진 resources가 부족하면 생산 퀘스트로 만든다.
4. 납품 위치가 payload에 있으면 delivery 퀘스트로 만든다.

## 6. LLM Prompt 정책

LLM에게는 구조 생성이 아니라 description 생성만 요청한다.

입력:

- main quest summary
- selected subquest title
- selected subquest objective
- relation kind/reason
- recent events

출력:

```json
{
  "descriptions": [
    {
      "quest_id": 101,
      "description": "전력망 복구에 필요한 전도성 부품을 만들기 위해 부족한 구리괴를 먼저 확보하세요."
    }
  ]
}
```

프롬프트 규칙:

- JSON object만 반환
- quest_id는 서버가 준 id만 사용
- title/objectives는 수정하지 않음
- description은 한국어 한 문장
- 메인 퀘스트 title 또는 목적과 연결되는 이유를 포함

## 7. Fallback 정책

LLM이 실패하면 서버가 deterministic description을 만든다.

예시:

```text
{main_quest_title} 진행에 필요한 {target_item_id} {quantity}개를 확보하기 위한 서브퀘스트입니다.
```

fallback 응답 metadata:

```json
{
  "description_source": "fallback",
  "fallback": true
}
```

## 8. 프론트엔드 반영

Quest Lab 요청 폼에 다음 입력을 추가한다.

- Main Quest preset 선택
- Main Quest JSON 편집 영역
- 서브퀘스트 개수 선택
- production/delivery 타입 체크박스

결과 패널에는 다음 정보를 표시한다.

- 메인 퀘스트 title
- 서브퀘스트 카드 목록
- 각 카드의 `parent_quest_id`
- relation reason
- LLM description
- fallback 여부

## 9. 구현 순서

### 1단계: Schema 확장

- `MainQuestContext`, `SubquestOptions`, `QuestRelation` 모델 추가
- `Quest`에 `parent_quest_id`, `relation` optional field 추가
- 기존 테스트가 깨지지 않는지 확인

완료 기준:

- 기존 quest response 테스트 통과
- 새 schema validation 테스트 추가

### 2단계: 후보 생성 서비스 추가

- `SubquestCandidateBuilder` 추가
- 메인 퀘스트 objective와 progress로 부족분 계산
- production subquest 후보 생성

완료 기준:

- 메인 퀘스트 입력 1개에서 서브퀘스트 3개 생성
- `parent_quest_id`가 모든 서브퀘스트에 들어감

### 3단계: LLM description 생성

- description 생성 prompt 추가
- LLM 응답 JSON 파싱
- quest_id 기준으로 description 병합
- 실패 시 fallback description 사용

완료 기준:

- LLM 정상 응답이면 `description_source=llm`
- LLM 실패면 `description_source=fallback`

### 4단계: Agent 연결

- `ProductionQuestAgent`가 `current_main_quest`가 있을 때 새 subquest 흐름을 사용
- `current_main_quest`가 없으면 기존 흐름 유지
- WebSocket smoke payload에 main quest case 추가

완료 기준:

- 기존 production quest smoke 통과
- main quest linked subquest smoke 통과

### 5단계: 프론트엔드 Quest Lab 반영

- Main Quest preset 추가
- 서브퀘스트 개수 입력 추가
- 결과 카드에 relation 정보 표시

완료 기준:

- UI에서 main quest payload를 보내고 관련 서브퀘스트를 확인

## 10. 테스트 계획

백엔드 테스트:

- `MainQuestContext` schema validation
- `SubquestOptions.count` 범위 검증
- 부족분 계산 테스트
- 후보 생성 테스트
- LLM description 병합 테스트
- LLM 실패 fallback 테스트
- WebSocket main quest request/response 테스트

프론트엔드 테스트:

- main quest preset 선택
- subquest count 변경
- response card에 parent quest 표시
- fallback badge 표시

## 11. 범위 제외

초기 버전에서는 다음을 하지 않는다.

- 메인 퀘스트 DB 저장
- 플레이어별 진행도 저장
- 복잡한 dependency graph 자동 생성
- 여러 메인 퀘스트 동시 최적화
- LLM이 objectives를 새로 만드는 기능

이 기능의 첫 목표는 “진행 중인 메인 퀘스트와 연결된 설명문이 붙은 서브퀘스트 목록”을 안정적으로 반환하는 것이다.
