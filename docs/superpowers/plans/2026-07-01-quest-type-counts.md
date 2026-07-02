# Quest Lab 퀘스트 타입별 개수 지정 계획

## 배경

현재 Quest Lab은 도메인별 개수(`production`, `delivery`, `exploration`)는 숫자로 지정하지만, 퀘스트 타입은 `daily`, `weekly`, `surprise`의 포함 여부만 `quest_types` 배열로 전달한다. 이 방식은 총 5개 퀘스트를 요청할 때 일일 3개, 주간 1개, 돌발 1개처럼 타입별 수량을 명시하기 어렵다.

## 목표

- 프론트에서 일일/주간/돌발 퀘스트 개수를 직접 입력한다.
- 요청 payload에 `quest_generation_options.quest_type_counts`를 추가한다.
- 백엔드는 `quest_type_counts`가 있으면 기존 `quest_types` 배열보다 우선 사용한다.
- 기존 `quest_types`만 보내는 요청은 계속 동작하게 유지한다.

## 요청 형식

```json
{
  "quest_generation_options": {
    "domain_counts": {
      "production": 2,
      "delivery": 1,
      "exploration": 2
    },
    "quest_type_counts": {
      "daily": 3,
      "weekly": 1,
      "surprise": 1
    },
    "quest_types": ["daily", "weekly", "surprise"],
    "surprise_duration_minutes": 30
  }
}
```

`quest_types`는 하위 호환과 사람이 읽기 쉬운 미리보기 용도로 유지한다. 실제 타입 분배는 `quest_type_counts`가 우선한다.

## 프론트 구현

- `DEFAULT_QUEST_TYPE_COUNTS`를 추가한다.
- `App.tsx`에서 `questTypes` 체크 토글 대신 타입별 숫자 입력을 사용한다.
- `buildAgentRequest`는 `quest_type_counts`와 0보다 큰 타입에서 만든 `quest_types`를 함께 보낸다.
- JSON import 시 `quest_type_counts`가 있으면 폼에 복원한다.
- `quest_type_counts`가 없고 `quest_types`만 있으면 기존 방식으로 각 타입 1개로 복원한다.
- 도메인 총합과 타입 총합이 다른 경우 경고를 표시하고 Generate를 막는다.

## 백엔드 구현

- `quest_generation_options.quest_type_counts`를 읽어 타입 배열로 확장한다.
- 예: `{ daily: 3, weekly: 1, surprise: 1 }` -> `[daily, daily, daily, weekly, surprise]`
- `quest_type_counts`가 비어 있거나 유효하지 않으면 기존 `quest_types` 분배를 사용한다.
- 도메인 순서대로 확장된 타입 배열을 할당한다.

## 검증

- 프론트 테스트: 타입별 개수가 payload에 포함되는지 확인한다.
- 프론트 테스트: JSON import가 타입별 개수를 복원하는지 확인한다.
- 백엔드 테스트: 3/1/1 타입 개수가 실제 생성 결과에 반영되는지 확인한다.
- 기존 `quest_types` 기반 테스트는 유지한다.