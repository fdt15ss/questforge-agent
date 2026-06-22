# 퀘스트 XP/credits 보상 기준

퀘스트의 XP와 credits 보상은 LLM이 임의로 정하지 않습니다. 서버는 `data/game/quest_reward_rules.csv`를 기준으로 퀘스트 타입과 플레이어 진행 티어를 결정하고, 해당 row의 `기본XP`, `기본크레딧`을 그대로 사용합니다.

## 기준 데이터

- 기준 파일: `data/game/quest_reward_rules.csv`
- 매칭 키: `퀘스트타입` + `진행티어`
- 응답 필드:
  - XP: `reward_type: "xp"`, `amount: 기본XP`
  - credits: `reward_type: "credits"`, `amount: 기본크레딧`
  - `source_rule_id`: 적용된 `보상룰ID`
  - `description`: 적용된 row의 `LLM보상설명힌트`

## 진행 티어 산정

`payload.progression.player_level`을 기준으로 티어를 정합니다.

| player_level | 진행티어 |
| ---: | --- |
| 없음 또는 1-5 | T1 |
| 6-10 | T2 |
| 11-15 | T3 |
| 16 이상 | T4 |

## XP/credits 테이블

| 퀘스트 타입 | 티어 | 보상룰ID | XP | credits |
| --- | --- | --- | ---: | ---: |
| daily | T1 | reward_daily_t1 | 80 | 20 |
| daily | T2 | reward_daily_t2 | 120 | 35 |
| daily | T3 | reward_daily_t3 | 170 | 55 |
| daily | T4 | reward_daily_t4 | 230 | 80 |
| weekly | T1 | reward_weekly_t1 | 300 | 90 |
| weekly | T2 | reward_weekly_t2 | 460 | 140 |
| weekly | T3 | reward_weekly_t3 | 650 | 210 |
| weekly | T4 | reward_weekly_t4 | 900 | 320 |
| surprise | T1 | reward_surprise_t1 | 60 | 15 |
| surprise | T2 | reward_surprise_t2 | 95 | 25 |
| surprise | T3 | reward_surprise_t3 | 135 | 40 |
| surprise | T4 | reward_surprise_t4 | 185 | 60 |

## reward_options와의 관계

요청에서 `quest_generation_options.reward_options.reward_types`를 지정하면, 선택된 타입만 응답에 포함합니다.

```json
{
  "quest_generation_options": {
    "count": 5,
    "reward_options": {
      "reward_types": ["xp", "credits"]
    }
  },
  "progression": {
    "player_level": 6
  }
}
```

위 요청에서 daily 퀘스트는 T2 기준을 사용하므로 다음 보상을 받습니다.

```json
[
  {
    "reward_type": "xp",
    "amount": 120,
    "source_rule_id": "reward_daily_t2",
    "description": "중반 진입 일일 퀘스트는 생산 라인 보강에 도움이 되는 보상으로 안내한다."
  },
  {
    "reward_type": "credits",
    "amount": 35,
    "source_rule_id": "reward_daily_t2",
    "description": "중반 진입 일일 퀘스트는 생산 라인 보강에 도움이 되는 보상으로 안내한다."
  }
]
```

## 검증 규칙

서버는 LLM이 반환한 `quests[]`도 다시 검증합니다.

- `xp` 보상의 `amount`는 CSV의 `기본XP`와 같아야 합니다.
- `credits` 보상의 `amount`는 CSV의 `기본크레딧`과 같아야 합니다.
- `source_rule_id`는 적용된 CSV row의 `보상룰ID`와 같아야 합니다.
- 요청에서 `reward_types`가 `credits`만 선택되었으면 XP 보상은 포함되면 안 됩니다.
- 요청에서 `reward_types`가 `xp`만 선택되었으면 credits 보상은 포함되면 안 됩니다.
- LLM 응답이 이 기준과 다르면 서버는 `invalid_llm_response`로 간주하고 deterministic fallback 퀘스트를 반환합니다.

## fallback 규칙

`reward_options.reward_types`가 비어 있거나 유효한 값이 없으면 `rewards` 필수 조건을 지키기 위해 XP 보상 하나를 fallback으로 지급합니다. 이때 XP 값도 위 CSV 기준을 그대로 사용합니다.