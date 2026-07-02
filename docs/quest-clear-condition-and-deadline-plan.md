# 퀘스트 완료 조건 및 마감 시간 개편 계획

## 배경

현재 생산 퀘스트의 `surprise` 타입은 완료 조건이 `manual`로 생성되며, 라벨은 `깜짝 상황 대응 완료`로 통일된다. 그래서 실제 목표가 `철광석 5개 수집`, `회로기판 3개 생산`처럼 수량 기반이어도 프론트에서는 사용자가 버튼을 눌러 완료 처리하는 형태가 된다.

반면 `daily`, `weekly`, `delivery` 계열은 대부분 `objective_count`를 사용해 `target_item_id`와 `required_quantity`를 기준으로 완료 여부를 판단한다. 이 차이 때문에 같은 생산/납품 계열 퀘스트인데도 타입에 따라 완료 판정 방식이 달라지고, 깜짝 퀘스트가 실제 게임 행동과 연결되지 않는 문제가 있다.

이번 개편의 목표는 다음과 같다.

- 깜짝 퀘스트도 일일/주간 퀘스트처럼 수량 기반 완료 조건을 사용한다.
- 퀘스트 타입별 차이는 완료 조건이 아니라 마감 시간으로 표현한다.
- 프론트엔드 Quest Lab에서 남은 시간을 확인하고 만료 상태를 테스트할 수 있게 한다.

## 정책 요약

| 타입 | 완료 조건 | 마감 시간 |
| --- | --- | --- |
| `surprise` | `objective_count` 기본 사용 | 생성 시각 기준 2시간 뒤 |
| `daily` | `objective_count` 기본 사용 | 생성일의 다음 0시, KST |
| `weekly` | `objective_count` 기본 사용 | 다음 주 월요일 0시, KST |

예를 들어 2026년 6월 29일 15:00 KST에 생성했다면 다음과 같이 계산한다.

- `surprise`: 2026-06-29T17:00:00+09:00
- `daily`: 2026-06-30T00:00:00+09:00
- `weekly`: 2026-07-06T00:00:00+09:00

## 완료 조건 개편

### 기존

production surprise 퀘스트:

```json
{
  "clear_condition": {
    "mode": "manual",
    "label": "깜짝 상황 대응 완료"
  }
}
```

### 변경 후

production surprise 퀘스트:

```json
{
  "objectives": [
    {
      "target_item_id": "resource_iron_ore",
      "quantity": 5
    }
  ],
  "clear_condition": {
    "mode": "objective_count",
    "target_item_id": "resource_iron_ore",
    "required_quantity": 5,
    "label": "철광석 5개 확보"
  }
}
```

핵심 원칙은 `objectives[0]`와 `clear_condition`이 같은 목표를 가리키게 하는 것이다.

- `target_item_id`는 첫 objective의 `target_item_id`를 사용한다.
- `required_quantity`는 첫 objective의 `quantity`를 사용한다.
- `label`은 선택값이지만, 가능하면 사람이 읽을 수 있는 완료 문구를 넣는다.

## 탐험 퀘스트 예외

탐험 퀘스트는 아직 실제 게임 이벤트나 지도 탐험 완료 토큰이 없기 때문에 모든 케이스를 즉시 `objective_count`로 바꾸기는 어렵다.

MVP에서는 다음 정책을 사용한다.

- 관련 자원이나 측정 가능한 목표가 있는 탐험 퀘스트는 `objective_count`를 사용할 수 있다.
- 순수 장소 조사, 신호 확인, 이상 징후 확인처럼 게임 내 수량 토큰이 없는 탐험 퀘스트는 당분간 `manual`을 유지한다.
- 장기적으로는 `exploration_signal_ping`, `site_north_relay_ruins` 같은 탐험 action id도 게임 이벤트 카운터와 연결해 `objective_count`처럼 처리한다.

즉 이번 변경의 1차 대상은 production/delivery 계열의 `surprise` 완료 조건 통일이다.

## 마감 시간 필드

Quest schema에 마감 시간 필드를 추가한다.

```python
class Quest(BaseModel):
    ...
    generated_at: str | None = None
    expires_at: str | None = None
```

또는 더 명확하게 `deadline_at`을 사용할 수 있다. 추천은 `expires_at`이다. 프론트엔드에서 “만료” 상태를 표현하기 쉽고, 서버 응답에서도 의미가 짧고 분명하다.

시간 값은 ISO 8601 문자열로 내려준다.

```json
{
  "generated_at": "2026-06-29T15:00:00+09:00",
  "expires_at": "2026-06-29T17:00:00+09:00"
}
```

## 마감 계산 규칙

서버는 `Asia/Seoul` 기준으로 마감 시간을 계산한다.

### surprise

생성 시각에서 2시간을 더한다.

```text
expires_at = generated_at + 2 hours
```

### daily

생성일의 다음 0시를 사용한다.

```text
expires_at = next local midnight
```

2026-06-29 15:00 KST 생성이면 2026-06-30 00:00 KST가 마감이다.

### weekly

다음 주 월요일 0시를 사용한다.

```text
expires_at = next Monday 00:00 KST
```

월요일에 생성된 주간 퀘스트도 같은 날 0시가 아니라 다음 주 월요일 0시를 사용한다. 예를 들어 2026-06-29 월요일 15:00 KST 생성이면 2026-07-06 00:00 KST가 마감이다.

## 백엔드 변경 계획

### 1. 공통 마감 계산 유틸 추가

새 파일 후보:

```text
backend/src/agents/quest_generator/deadlines.py
```

제공 함수:

```python
def quest_deadline(
    quest_type: str,
    generated_at: datetime | None = None,
    timezone_name: str = "Asia/Seoul",
) -> tuple[str, str]:
    ...
```

반환값:

- `generated_at_iso`
- `expires_at_iso`

테스트하기 쉽도록 `generated_at`을 주입 가능하게 만든다.

### 2. Quest schema 확장

`backend/src/agents/quest_generator/schemas.py`의 `Quest` 모델에 필드를 추가한다.

```python
generated_at: str | None = None
expires_at: str | None = None
```

초기에는 `str`로 두고, 별도 validator는 추가하지 않는다. 기존 응답과 하위 호환을 유지하기 위해 optional로 시작한다.

### 3. production surprise 완료 조건 변경

`production_quest.py`의 `_clear_condition()`에서 surprise 분기를 제거한다.

기존:

```python
if quest_type == "surprise":
    return {
        "mode": "manual",
        "label": "깜짝 상황 대응 완료",
    }
```

변경:

```python
return {
    "mode": "objective_count",
    "target_item_id": target_item_id,
    "required_quantity": quantity,
}
```

필요하면 `label`을 추가한다.

```python
"label": f"{target_item_id} {quantity}개 확보"
```

### 4. 각 퀘스트 생성기에 마감 필드 주입

다음 생성기에 `generated_at`, `expires_at`을 넣는다.

- `production_quest.py`
- `delivery_quest.py`
- `exploration_quest.py`

모든 퀘스트 타입은 `daily`, `weekly`, `surprise` 중 하나이므로 같은 유틸을 공유할 수 있다.

### 5. LLM prompt 보호 문구 업데이트

현재 prompt는 서버가 `objectives`, `clear_condition`, `rewards`를 소유한다고 안내한다. 여기에 `generated_at`, `expires_at`도 서버 소유 필드라고 명시한다.

```text
Server owns objectives, clear_condition, rewards, generated_at, expires_at, quantities, and final count.
```

LLM은 제목/설명만 수정하고 마감 시간은 수정하지 못하게 한다.

## 프론트엔드 변경 계획

### 1. 타입 확장

`frontend/src/types/quest.ts`의 `QuestFromServer`에 필드를 추가한다.

```ts
generated_at?: string | null;
expires_at?: string | null;
```

### 2. QuestCard에 마감 표시

퀘스트 카드에 타입 badge 근처 또는 완료 조건 섹션에 마감 시간을 표시한다.

예시:

```text
마감: 오늘 17:00
남은 시간: 1시간 42분
```

만료된 경우:

```text
만료됨
```

### 3. 만료 상태 처리

MVP에서는 별도 `expired` status를 추가하지 않고 UI badge만 표시한다.

현재 상태:

```ts
type QuestStatus = "generated" | "testing" | "cleared";
```

1차 구현에서는 status를 늘리지 않는다. `expires_at`이 현재 시각보다 과거면 카드에 `만료됨` 표시만 한다.

후속 구현에서 필요하면 다음처럼 확장한다.

```ts
type QuestStatus = "generated" | "testing" | "cleared" | "expired";
```

### 4. Quest Lab 테스트

프론트 테스트는 다음을 검증한다.

- `expires_at`이 있으면 카드에 마감 시간이 표시된다.
- 과거 시간이면 `만료됨`이 표시된다.
- `objective_count` surprise 퀘스트도 `+1`, `채우기` 버튼으로 완료할 수 있다.

## 테스트 계획

### 백엔드 테스트

1. production surprise가 `objective_count`를 사용한다.
2. production surprise의 `required_quantity`가 objective quantity와 같다.
3. delivery daily/weekly/surprise에 `expires_at`이 포함된다.
4. exploration daily/weekly/surprise에 `expires_at`이 포함된다.
5. `surprise` 마감은 생성 시각 + 2시간이다.
6. `daily` 마감은 다음 로컬 자정이다.
7. `weekly` 마감은 다음 주 월요일 0시다.
8. LLM prompt에 `generated_at`, `expires_at`을 반환하지 말라는 문구가 포함된다.

### 프론트엔드 테스트

1. `QuestFromServer`에 `expires_at`이 있어도 렌더링이 깨지지 않는다.
2. 마감 시간이 미래면 남은 시간이 표시된다.
3. 마감 시간이 과거면 `만료됨`이 표시된다.
4. surprise + `objective_count` 조합이 기존 일일/주간과 같은 방식으로 완료 처리된다.

## 마이그레이션 영향

### 호환성

`generated_at`, `expires_at`은 optional로 시작하므로 기존 클라이언트는 깨지지 않는다.

`surprise` 완료 조건은 `manual`에서 `objective_count`로 바뀌므로 프론트엔드가 이미 `objective_count`를 지원해야 한다. 현재 Quest Lab은 `objective_count`와 `manual`을 모두 지원하므로 큰 UI 변경 없이 받을 수 있다.

### 문서 업데이트

다음 문서를 함께 갱신한다.

- `docs/main-quest-linked-quest-plan.md`
- `docs/frontend-quest-lab.md`
- `docs/agent-request-structure.md`

특히 기존 문서에 있는 “surprise는 manual 완료” 예시는 새 정책에 맞게 바꿔야 한다.

## 구현 순서 추천

1. 백엔드 deadline 유틸과 테스트 작성
2. `Quest` schema에 `generated_at`, `expires_at` optional 필드 추가
3. production surprise 완료 조건을 `objective_count`로 변경
4. production/delivery/exploration 생성 결과에 마감 필드 추가
5. 프론트 타입과 QuestCard 마감 표시 추가
6. Quest Lab에서 surprise objective_count 완료 흐름 확인
7. 관련 문서 예시 업데이트

## 결정 사항

MVP에서는 `clear_condition.mode`를 새로 추가하지 않는다. `objective_count`와 `manual`만 유지한다.

깜짝 퀘스트의 차별점은 “수동 완료”가 아니라 “짧은 제한 시간”으로 표현한다. 따라서 production/delivery surprise는 일일/주간과 같은 목표 수량 기반 완료 조건을 사용하고, `expires_at`을 생성 시각 기준 2시간 뒤로 설정한다.

탐험 퀘스트는 측정 가능한 탐험 이벤트가 생기기 전까지 일부 `manual`을 허용하되, 모든 타입에 마감 시간은 동일하게 부여한다.
