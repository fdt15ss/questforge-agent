# Agent Request 구조

QuestForge agent 요청은 WebSocket으로 전송합니다.

```text
ws://127.0.0.1:18000/ws/agent
```

서버는 `agent.request` 메시지를 받고, 결과로 `agent.response` 또는
`agent.error`를 반환합니다.

## 상위 Quest 생성 요청

클라이언트가 production/delivery 두 도메인을 합쳐 퀘스트를 받고 싶을 때는
`quest_generator`를 상위 생성기로 사용합니다.

이 모드에서는 `payload.sub_agent`를 넣지 않습니다.

```json
{
  "type": "agent.request",
  "request_id": "quest-test-001",
  "session_id": "postman-session",
  "client_id": "postman-client",
  "agent": "quest_generator",
  "payload": {
    "quest_type": "daily",
    "quest_generation_options": {
      "count": 5
    },
    "progression": {
      "stage": "mid_automation",
      "player_level": 11
    },
    "game_state": {
      "inventory": {
        "resource_iron_ore": 110,
        "resource_copper_ore": 95,
        "resource_steel_beam": 14,
        "resource_circuit_board": 6
      },
      "unlocked_equipment": [
        "equipment_miner",
        "equipment_smelter",
        "equipment_assembler",
        "equipment_conveyor_belt",
        "equipment_splitter",
        "equipment_merger"
      ],
      "unlocked_recipes": [
        "recipe_smelt_iron",
        "recipe_smelt_copper",
        "recipe_craft_iron_plate",
        "recipe_craft_copper_wire",
        "recipe_craft_steel_beam",
        "recipe_craft_circuit_board"
      ]
    },
    "recent_events": [
      "강철 빔 생산 라인이 막 가동되었지만 철광석 공급이 부족하다.",
      "회로기판 제작 때문에 구리선 소비량이 늘었다."
    ]
  }
}
```

기본 동작은 다음과 같습니다.

- `quest_generation_options.count` 기본값은 `5`입니다.
- 기본 도메인은 `production`, `delivery`입니다.
- `count: 5`이면 production 퀘스트 3개, delivery 퀘스트 2개를 생성합니다.
- 응답 payload는 공통 `QuestResponse` 형태인 `{"quests": [...]}`를 사용합니다.

## 도메인별 생성 개수 지정

도메인별 퀘스트 개수를 직접 지정하려면
`quest_generation_options.domain_counts`를 사용합니다.

```json
{
  "type": "agent.request",
  "request_id": "quest-test-domain-counts",
  "session_id": "postman-session",
  "client_id": "postman-client",
  "agent": "quest_generator",
  "payload": {
    "quest_type": "daily",
    "quest_generation_options": {
      "domain_counts": {
        "production": 2,
        "delivery": 4
      }
    },
    "game_state": {
      "inventory": {
        "resource_iron_plate": 88,
        "resource_copper_wire": 120
      }
    }
  }
}
```

위 요청은 총 6개의 퀘스트를 반환합니다.

- production: 2개
- delivery: 4개

`domain_counts`가 있으면 `count`보다 `domain_counts`의 유효한 양수 값들이 우선됩니다.

## 특정 Leaf Agent만 강제하기

특정 도메인의 leaf agent만 실행하고 싶을 때만 `payload.sub_agent`를 사용합니다.

production만 생성:

```json
{
  "type": "agent.request",
  "request_id": "quest-test-production-only",
  "session_id": "postman-session",
  "client_id": "postman-client",
  "agent": "quest_generator",
  "payload": {
    "sub_agent": "quest_generator.production_quest",
    "quest_type": "daily",
    "quest_generation_options": {
      "count": 5
    },
    "game_state": {
      "inventory": {
        "resource_iron_ore": 55,
        "resource_copper_ore": 42
      }
    }
  }
}
```

delivery만 생성:

```json
{
  "type": "agent.request",
  "request_id": "quest-test-delivery-only",
  "session_id": "postman-session",
  "client_id": "postman-client",
  "agent": "quest_generator",
  "payload": {
    "sub_agent": "quest_generator.delivery_quest",
    "quest_generation_options": {
      "count": 3
    },
    "item": "resource_iron_plate",
    "quantity": 8,
    "destination": "central_storage"
  }
}
```

## 메인 퀘스트 연계 정보

`current_main_quest`는 상위 생성 요청이나 production 요청에 포함할 수 있습니다.
production 퀘스트는 메인 퀘스트의 부족한 objective를 기준으로
`main_quest_link`가 포함된 보조 퀘스트를 만들 수 있습니다.

```json
{
  "current_main_quest": {
    "id": "main_scale_modular_factory",
    "title": "모듈형 생산 단지 확장",
    "description": "전력과 물류를 분리한 모듈형 생산 구역을 구축한다.",
    "objectives": [
      {
        "target_item_id": "resource_steel_beam",
        "quantity": 40
      },
      {
        "target_item_id": "resource_circuit_board",
        "quantity": 25
      }
    ],
    "progress": {
      "resource_steel_beam": 14,
      "resource_circuit_board": 6
    }
  }
}
```

## 요청 reward_options 구조

모든 퀘스트 응답은 `rewards`를 반드시 포함합니다. 보상 종류는
`quest_generation_options.reward_options`로 선택할 수 있습니다.
하위 호환을 위해 `payload.reward_options`도 읽지만, 새 요청은
`quest_generation_options.reward_options`를 권장하며 두 위치가 모두 있으면
`quest_generation_options.reward_options`가 우선합니다.
XP와 credits 금액 기준은 `docs/quest-reward-criteria.md`를 따릅니다.

```json
{
  "quest_generation_options": {
    "count": 5,
    "reward_options": {
      "reward_types": ["resource"],
      "resource_ids": ["resource_copper_ingot"]
    }
  }
}
```

지원 필드:

- `reward_types`: 응답에 포함할 보상 타입 목록입니다. 허용값은 `"xp"`, `"credits"`, `"resource"`입니다.
- `resource_ids`: resource 보상 후보로 사용할 resource id 목록입니다. `resources.csv`에 있는 id만 사용됩니다.
- `resource_groups`: `resource_ids`가 없을 때 사용할 resource 그룹 후보입니다. 없으면 CSV reward rule의 `보상자원그룹`을 사용합니다. 이 값은 resource 보상 후보만 바꾸며, XP/credits 금액과 `source_rule_id`의 티어는 `quest_type`과 `progression.player_level` 기준으로 선택됩니다.

동작 규칙:

- `reward_types: ["resource"]`이면 XP/credits 없이 resource 보상만 반환합니다.
- `reward_types: ["xp", "credits"]`이면 resource 보상은 반환하지 않습니다.
- `reward_options`가 없으면 CSV reward rule의 기본 구성으로 XP/credits/resource 후보를 생성합니다.
- 선택 결과가 비어도 `rewards` 필수 조건을 지키기 위해 XP fallback 하나를 반환합니다.

## 응답 rewards 구조

아래 예시는 `reward_types`로 `resource`만 선택한 응답입니다.

```json
{
  "rewards": [
    {
      "reward_type": "resource",
      "resource_id": "resource_copper_ingot",
      "resource_name": "구리괴",
      "amount": 3,
      "source_rule_id": "reward_daily_t2",
      "description": "기초 가공 자원 보상"
    }
  ]
}
```

## Structured CSV RAG 동작

퀘스트 생성기는 요청 payload를 바로 LLM에 넘기지 않습니다. 먼저 `data/game` CSV를 authoritative game database로 보고, 요청과 관련된 row를 검색해 내부 prompt에 넣습니다.

검색에 사용하는 주요 신호는 다음과 같습니다.

- `current_main_quest.objectives[].target_item_id`
- `game_state.inventory`의 resource id
- `game_state.unlocked_recipes`의 recipe id
- `quest_type`, `quest_generation_options.quest_types`
- `recent_events`, `progression`, 메인 퀘스트 제목/설명

검색 결과는 LLM prompt의 `[RETRIEVED_GAME_CONTEXT]` 섹션에 들어갑니다. 이 섹션에는 `resources`, `recipes`, `scenario_contexts`, `reward_rules`가 포함됩니다.

### `[RETRIEVED_GAME_CONTEXT].semantic_matches`

ChromaDB Hybrid RAG가 사용 가능하면 `[RETRIEVED_GAME_CONTEXT]`에 `semantic_matches`가 추가됩니다. 이 값은 semantic index에서 찾은 game context이며, 내부 prompt 전용입니다.

```json
{
  "semantic_matches": [
    {
      "id": "resource_iron_plate::summary",
      "source_type": "resource",
      "source_id": "resource_iron_plate",
      "document": "Iron plate production context used by quest generation.",
      "distance": 0.1234
    }
  ]
}
```

필드 의미는 다음과 같습니다.

- `id`: ChromaDB document id입니다.
- `source_type`: 원본 game data 타입입니다. 예: `resource`, `recipe`, `scenario_context`, `reward_rule`.
- `source_id`: 원본 CSV row 또는 game data id입니다.
- `document`: semantic search에 사용된 text chunk입니다.
- `distance`: query와 match 사이의 vector distance입니다. 낮을수록 더 가까운 match입니다.

`semantic_matches`는 LLM이 `quest_plan`의 분석, 의도, 제목, 설명을 게임 데이터에 맞게 작성하도록 돕는 내부 정보입니다. 최종 클라이언트 응답 payload에는 직접 노출되지 않습니다.

ChromaDB를 사용할 수 없거나 repo-root `.chroma/questforge_game_context` index가 없으면 `semantic_matches`는 빈 배열 `[]`입니다. 이 경우에도 CSV 기반 `resources`, `recipes`, `scenario_contexts`, `reward_rules` context와 deterministic server layer는 계속 동작합니다.

이 context는 LLM이 `quest_plan`의 분석, 의도, 제목, 설명을 게임 데이터에 맞게 작성하도록 돕기 위한 내부 정보입니다. 클라이언트 응답 payload에는 그대로 노출되지 않습니다.

서버가 계속 소유하는 필드는 다음과 같습니다.

- 생성 개수(`count`)와 도메인 분배
- `objectives`
- `clear_condition`
- `rewards`
- objective `quantity` / reward `amount`
- 최종 `QuestResponse` schema validation

따라서 LLM은 검색 context를 참고할 수 있지만, 보상 룰이나 목표 수량 같은 서버 소유 값을 새로 만들어 최종 응답을 바꿀 수 없습니다.
## LLM 출력 계약

최종 클라이언트 응답은 항상 서버가 검증한 `QuestResponse`입니다. LLM 응답은 클라이언트로 직접 전달되지 않고, 서버 draft에 병합됩니다.

### 상위 quest_generator

상위 `quest_generator`는 `quest_plan`을 요청합니다.

```json
{
  "quest_plan": {
    "analysis": "현재 게임 상태 분석",
    "domain_mix": {
      "production": 3,
      "delivery": 2
    },
    "quest_intents": [
      {
        "id": 1,
        "domain": "production",
        "target_item_id": "resource_iron_ingot",
        "intent": "main_quest_deficit",
        "reason": "왜 이 퀘스트가 지금 필요한지",
        "title": "퀘스트 제목",
        "description": "퀘스트 설명",
        "main_quest_link_reason": "메인 퀘스트와 연결되는 이유"
      }
    ]
  }
}
```

서버는 `quest_plan`에서 `title`, `description`, `main_quest_link_reason`, `intent`, `reason`, `analysis`만 반영합니다. 수량, 보상, 완료 조건은 서버가 기존 draft와 CSV 규칙으로 유지합니다. `id`, `domain`, `target_item_id`가 draft와 맞지 않거나 `domain_mix`와 `quest_intents`가 서로 맞지 않으면 deterministic fallback 응답을 사용합니다.

### leaf agent

`production_quest`, `delivery_quest` leaf agent는 기존 `quest_text_updates`를 유지합니다.

```json
{
  "quest_text_updates": [
    {
      "id": 1,
      "title": "퀘스트 제목",
      "description": "퀘스트 설명",
      "main_quest_link_reason": "메인 퀘스트 연결 사유"
    }
  ]
}
```

이 호환 경로는 로컬 LLM이 `quest_plan`을 안정적으로 만들지 못하는 경우에도 기존 안전장치를 유지하기 위한 것입니다.

## 라우팅 규칙

- 퀘스트 생성 요청의 `agent`는 `"quest_generator"`를 사용합니다.
- `payload.sub_agent`는 선택 값입니다.
- `payload.sub_agent`가 없으면 `quest_generator`가 상위 생성기로 동작합니다.
- 상위 생성기는 production/delivery 퀘스트를 합쳐 `quests[]`로 반환합니다.
- `payload.sub_agent`를 넣으면 해당 leaf agent만 실행합니다.
- 허용되는 `sub_agent` 값은 다음 둘입니다.
  - `"quest_generator.production_quest"`
  - `"quest_generator.delivery_quest"`
- `quest_domain: "production"`은 라우팅 키가 아닙니다.
- 특정 leaf를 강제하려면 `sub_agent`를 사용하고, 두 도메인을 합쳐 생성하려면 `sub_agent`를 빼야 합니다.
- top-level 라우팅에는 사용 가능한 LLM provider가 필요합니다.
- top-level 라우팅 결정이 실패하면 서버는 `ROUTING_UNAVAILABLE`을 반환합니다.

