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

