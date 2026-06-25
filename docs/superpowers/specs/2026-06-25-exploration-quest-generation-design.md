# Exploration Quest Generation Design

## Summary

QuestForge can support exploration quests, but the backend does not currently generate them. The public `Quest` schema already allows `domain: "exploration"`, while the actual generator only routes and builds `production` and `delivery` quests. This design adds exploration as a first-class quest domain with its own leaf agent, deterministic fallback, top-level domain mixing, request documentation, and tests.

The MVP goal is not to build a full map or discovery system. The goal is to let `quest_generator` return valid `QuestResponse` items whose `domain` is `"exploration"` and whose objectives represent scouting, signal checks, anomaly investigation, resource survey, or route confirmation tasks that can be inspected in Quest Lab.

## Current State

The backend has these relevant pieces:

- `backend/src/agents/quest_generator/schemas.py`
  - `Quest.domain` already allows `"production"`, `"delivery"`, and `"exploration"`.
  - `QuestPlanIntent.domain` only allows `"production"` and `"delivery"`.
  - `QuestPlanDomainMix` only contains `production` and `delivery` counts.

- `backend/src/agents/quest_generator/agent.py`
  - `QUEST_SUB_AGENT_IDS` only includes `quest_generator.production_quest` and `quest_generator.delivery_quest`.
  - `QUEST_DOMAINS` only includes `production` and `delivery`.
  - `_build_combined_payload()` dispatches `production` to `ProductionQuestAgent`; everything else currently falls through to `DeliveryQuestAgent`.
  - Top-level prompt contracts and compact prompt contracts only model production and delivery.

- `backend/src/agents/router.py`
  - The default router registers only `QuestGeneratorAgent`, `ProductionQuestAgent`, and `DeliveryQuestAgent`.

- `backend/src/agent_connection/router.py`
  - The manifest exposes only production and delivery quest leaf agents.

- `backend/tests/test_scenario_harness.py`
  - `quest_generator.exploration_quest` is explicitly listed as a removed/rejected sub-agent.

- `docs/architecture-plan.md`
  - Mentions `exploration_quest` as a future extension and says it is not built yet.

This means frontend Quest Lab cannot create exploration quests just by sending `domain_counts: {"exploration": 1}`. The current backend filters that domain out before generation.

## Product Meaning

An exploration quest is a quest whose primary action is to learn, reveal, verify, or scout something about the factory world rather than produce or deliver an item.

For MVP, exploration quests should cover these intent families:

- `survey_resource`: inspect or confirm a resource source, deposit, or extraction route.
- `scan_signal`: check signal, communication, navigation, or anomaly readings.
- `inspect_site`: visit or inspect a crash, ruin, outpost, or build area.
- `verify_route`: confirm a transport, travel, or supply path is usable.
- `stabilize_area`: check environmental or magnetic storm risk before expansion.

The response still uses the existing `Quest` contract:

```json
{
  "id": 1,
  "type": "daily",
  "domain": "exploration",
  "title": "동쪽 광맥 신호 확인",
  "description": "새 생산 라인을 열기 전에 동쪽 광맥 신호를 조사해 확장 후보지를 확인하세요.",
  "objectives": [
    {
      "target_item_id": "exploration_signal_ping",
      "quantity": 1
    }
  ],
  "clear_condition": {
    "mode": "manual",
    "label": "탐사 확인 완료"
  },
  "rewards": [
    {
      "reward_type": "xp",
      "amount": 120,
      "resource_id": null,
      "resource_name": null,
      "source_rule_id": "reward_daily_t1",
      "description": "초기 탐사 퀘스트 경험치 보상"
    }
  ],
  "main_quest_link": {
    "main_quest_id": "main_restore_signal",
    "main_quest_title": "장거리 신호 복구",
    "relation_kind": "progress_support",
    "reason": "장거리 신호 복구 전에 주변 신호 간섭 원인을 확인합니다."
  }
}
```

The objective target may be a real resource id when the exploration task is about surveying a known resource. It may also be a server-defined exploration action id such as `exploration_signal_ping` when the task is not tied to inventory.

## Approaches Considered

### Approach A: Add a dedicated `ExplorationQuestAgent`

Create `backend/src/agents/quest_generator/exploration_quest.py` using the same LangGraph leaf pattern as production and delivery. The new leaf owns exploration-specific target selection, descriptions, clear conditions, and fallback payloads. Top-level `quest_generator` then treats exploration as a third domain.

Pros:

- Keeps domain behavior isolated and understandable.
- Lets exploration use manual clear conditions without bending production/delivery logic.
- Makes direct `payload.sub_agent: "quest_generator.exploration_quest"` possible.
- Scales cleanly when real map or discovery data arrives later.

Cons:

- Requires updates across router, top-level domain mixing, schemas, tests, docs, and manifest.
- Adds another generator path to maintain.

### Approach B: Reuse `ProductionQuestAgent` and set `domain: "exploration"`

Add a mode to production fallback that produces exploration-looking text and swaps the domain.

Pros:

- Fastest implementation.
- Minimal new files.

Cons:

- Blurs production and exploration behavior.
- Makes clear conditions awkward because exploration often does not have an inventory quantity.
- Makes future map/discovery integration harder.

### Approach C: Add new exploration data tables first

Introduce CSV files such as `exploration_sites.csv`, `exploration_signals.csv`, and `exploration_routes.csv`, then build a new agent around those tables.

Pros:

- Strongest long-term data model.
- Gives designers a direct place to author exploration content.

Cons:

- Too large for this MVP.
- Requires data design before the backend can return any exploration quest.

## Recommendation

Use Approach A for implementation, with a small data fallback that reuses current CSV and payload context. Do not add new CSV files in the first pass.

The first implementation should create a dedicated `ExplorationQuestAgent`, but it should source candidate targets from existing inputs:

- `payload.exploration_targets`, if provided.
- `payload.recent_events`, especially signal, anomaly, storm, route, outpost, crash, resource, or scouting language.
- `payload.current_main_quest`, especially title, description, objectives, and progress.
- `data/game/scenario_context.csv`, especially contexts about crash survival, signal towers, magnetic storms, intermoon resources, signal amplifiers, and scout spaceship.
- `data/game/resources.csv`, when exploration is about resource survey.

This keeps the backend useful immediately and leaves room for future `exploration_sites.csv`.

## Request Contract

### Top-Level Mixed Generation

Clients request mixed generation through the existing top-level agent:

```json
{
  "type": "agent.request",
  "request_id": "quest-exploration-mixed-001",
  "session_id": "quest-lab",
  "client_id": "quest-lab",
  "agent": "quest_generator",
  "payload": {
    "quest_generation_options": {
      "domain_counts": {
        "production": 1,
        "delivery": 1,
        "exploration": 2
      },
      "quest_types": ["daily", "weekly", "surprise"]
    },
    "progression": {
      "stage": "early_signal_recovery",
      "player_level": 6
    },
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
    "game_state": {
      "inventory": {
        "resource_iron_ore": 35,
        "resource_copper_wire": 12
      },
      "unlocked_equipment": [
        "equipment_miner",
        "equipment_smelter"
      ]
    },
    "recent_events": [
      "동쪽 절벽 너머에서 약한 구조 신호가 반복 감지됐다.",
      "자기 폭풍 이후 광맥 스캐너가 불안정하다."
    ]
  }
}
```

### Direct Leaf Generation

Clients can force only exploration generation:

```json
{
  "type": "agent.request",
  "request_id": "quest-exploration-only-001",
  "session_id": "quest-lab",
  "client_id": "quest-lab",
  "agent": "quest_generator",
  "payload": {
    "sub_agent": "quest_generator.exploration_quest",
    "quest_generation_options": {
      "count": 3,
      "quest_types": ["daily", "surprise"]
    },
    "exploration_targets": [
      {
        "id": "signal_east_ridge",
        "label": "동쪽 능선 신호",
        "target_kind": "signal",
        "related_resource_id": "resource_copper_ore"
      },
      {
        "id": "site_escape_pod_debris",
        "label": "탈출 포드 잔해",
        "target_kind": "site"
      }
    ],
    "recent_events": [
      "탈출 포드 잔해 주변에서 금속 반응이 확인됐다."
    ]
  }
}
```

`exploration_targets` is optional. The MVP accepts it as a best-effort hint, not as a required schema. Invalid items are ignored.

Recommended exploration target fields:

- `id`: stable target id used as an objective id when no resource id is better.
- `label`: Korean display label for title and description.
- `target_kind`: one of `resource_node`, `signal`, `site`, `route`, `anomaly`, or `area`.
- `related_resource_id`: optional resource id from `resources.csv`.
- `related_recipe_id`: optional recipe id from `recipes.csv`.

## Response Contract

Exploration quests use the existing `QuestResponse` shape.

Rules:

- `Quest.type` remains `daily`, `weekly`, or `surprise`.
- `Quest.domain` is always `"exploration"` for exploration leaf output.
- `objectives` must contain at least one item.
- `rewards` must contain at least one item.
- `clear_condition.mode` is usually `"manual"`.
- `clear_condition.mode` may be `"objective_count"` only when the objective target is a concrete resource id or future measurable exploration token.
- `main_quest_link` is optional and should be present when the request has `current_main_quest` and linking is not disabled.

For MVP, the recommended clear condition is manual:

```json
{
  "mode": "manual",
  "label": "탐사 확인 완료"
}
```

This makes Quest Lab validation possible before the game client has a real map visit, scanner, fog-of-war, or discovery event stream.

## Backend Design

### New Leaf Agent

Create `backend/src/agents/quest_generator/exploration_quest.py`.

It should follow the same high-level shape as the existing leaf agents:

- Constants:
  - `DEFAULT_EXPLORATION_QUEST_COUNT = 5`
  - `MAX_EXPLORATION_QUEST_COUNT = 10`
  - `DEFAULT_QUEST_TYPES = ("daily", "weekly", "surprise")`

- State:
  - `payload`
  - `context`
  - `quest_count`
  - `quest_types`
  - `main_quest`
  - `exploration_targets`
  - `retrieved_context`
  - `response_payload`

- Graph nodes:
  - `exploration.normalize_payload`
  - `exploration.retrieve_context`
  - `exploration.build_quests`
  - `exploration.validate_response`

- Public class:
  - `ExplorationQuestAgent`
  - `agent_id = "quest_generator.exploration_quest"`
  - `response_schema = QuestResponse`
  - `build_prompt()`
  - `fallback()`
  - `describe_graph()`

The leaf should generate deterministic draft quests first. LLM calls may rewrite only title, description, and optional `main_quest_link_reason`, matching the current leaf-agent contract.

### Candidate Target Selection

The exploration leaf should build a candidate list in this priority order:

1. Valid `payload.exploration_targets`.
2. Main quest title/description and recent events converted into generic signal/site/route/anomaly targets.
3. Scenario contexts whose themes or usage imply scouting, signal recovery, crash survival, magnetic storms, intermoon resources, or scout spaceship.
4. Resource ids from `game_state.inventory`, `current_main_quest.objectives`, or `resources.csv`, converted to `resource_node` survey targets.
5. Static fallback targets:
   - `exploration_signal_ping`
   - `exploration_crash_site_survey`
   - `exploration_resource_scan`
   - `exploration_route_check`
   - `exploration_anomaly_probe`

Candidate targets should be de-duplicated by id while preserving priority order.

### Quest Type Behavior

The exploration leaf should interpret cadence like this:

- `daily`: a short scouting task, usually one site, resource, or signal check.
- `weekly`: a broader survey task, usually a route, area, or multi-step preparation check.
- `surprise`: a reactive event such as anomaly spike, storm interference, signal burst, or suspicious resource reading.

The initial fallback can still return one objective per quest. The difference is in title, description, clear condition label, and main quest relation.

### Titles

Use deterministic title templates by target kind:

- `resource_node`: `{label} 매장지 조사`
- `signal`: `{label} 신호 확인`
- `site`: `{label} 현장 조사`
- `route`: `{label} 경로 확인`
- `anomaly`: `{label} 이상 반응 분석`
- `area`: `{label} 구역 정찰`

### Descriptions

Descriptions should explain why the exploration task matters now. They should use recent events, main quest context, or scenario context when available.

Examples:

- `장거리 신호 복구 전에 동쪽 능선의 간섭 신호를 확인하세요.`
- `새 생산 라인을 확장하기 전에 구리 광맥 반응이 안정적인지 조사하세요.`
- `자기 폭풍 이후 장비 오작동 위험이 커졌습니다. 기지 외곽의 이상 반응을 먼저 확인하세요.`

### Main Quest Link

Exploration can reuse the existing `MainQuestLink.relation_kind` values.

Recommended mapping:

- `daily` -> `progress_support`
- `weekly` -> `progress_support`
- `surprise` -> `risk_buffer`

Do not add new `relation_kind` values in this MVP. Adding `"exploration_support"` would require client changes and more schema churn, while `progress_support` and `risk_buffer` already express the need.

### Rewards

Use existing `build_quest_rewards()` so exploration stays consistent with production and delivery.

When the exploration objective target is not a real resource id, pass a related resource id if available. If no related resource exists, pass the exploration target id and let reward fallback produce XP/credits/resource according to existing reward rules. If resource rewards require a real resource id, prefer `reward_options.resource_ids`, then scenario/resource context, then XP fallback.

The completion criterion is that every exploration quest still validates through `QuestResponse` and contains at least one reward.

## Top-Level Generator Changes

Update `backend/src/agents/quest_generator/agent.py`:

- Import `ExplorationQuestAgent`.
- Add `"quest_generator.exploration_quest"` to `QUEST_SUB_AGENT_IDS`.
- Add `"exploration"` to `QUEST_DOMAINS`.
- Instantiate `self.exploration_agent`.
- Update `_domain_mix()` to count exploration.
- Update `_build_combined_payload()` with explicit `elif domain == "delivery"` and `elif domain == "exploration"` branches.
- Update prompt text from production/delivery-only wording to production/delivery/exploration wording.
- Update compact prompt examples and contracts to include exploration.

The default `count: 5` distribution becomes:

- production: 2
- delivery: 2
- exploration: 1

This follows the existing equal-split-plus-remainder behavior when `QUEST_DOMAINS = ("production", "delivery", "exploration")`.

If a caller wants the old 3/2 production/delivery split, they can send:

```json
{
  "quest_generation_options": {
    "domain_counts": {
      "production": 3,
      "delivery": 2
    }
  }
}
```

## Schema Changes

Update `backend/src/agents/quest_generator/schemas.py`:

```python
class QuestPlanDomainMix(BaseModel):
    production: int = Field(ge=0)
    delivery: int = Field(ge=0)
    exploration: int = Field(default=0, ge=0)
```

```python
class QuestPlanIntent(BaseModel):
    domain: Literal["production", "delivery", "exploration"]
```

Using `default=0` for exploration keeps older LLM fixtures and tests easier to migrate, but final prompt contracts should include the exploration field whenever the draft payload contains exploration quests.

## Router And Manifest Changes

Update `backend/src/agents/router.py`:

- Import `ExplorationQuestAgent`.
- Register `ExplorationQuestAgent()` in `create_default_agent_router()`.

Update `backend/src/agent_connection/router.py`:

- The manifest will pick up the new leaf agent through `QUEST_SUB_AGENT_IDS`.
- Update sample request only if Quest Lab should default to exploration. Otherwise leave the production sample unchanged.

## Documentation Changes

Update `docs/agent-request-structure.md`:

- Replace production/delivery-only wording with production/delivery/exploration.
- Add `domain_counts` example including exploration.
- Add direct `quest_generator.exploration_quest` example.
- Update allowed `sub_agent` list.
- Clarify that `domain` is content category, while `type` remains `daily`, `weekly`, or `surprise`.
- Add `exploration_targets` as an optional hint section.

Update `README.md` only after implementation, because current README should reflect working behavior.

## Quest Lab Impact

Quest Lab should treat exploration as another domain filter and badge:

- Request Builder:
  - Add `exploration` to domain selection.
  - Allow `domain_counts.exploration`.
  - Optionally expose an `exploration_targets` JSON editor later.

- Quest Results:
  - Render `domain: exploration` as a distinct badge.
  - Manual clear condition should show a single completion button.
  - Objective ids like `exploration_signal_ping` should be shown as action/objective identifiers, not inventory resources.

No frontend change is required to the `Quest` shape if it already trusts the backend schema.

## Error Handling

Invalid exploration inputs should degrade to deterministic fallback rather than returning partial invalid quests.

Rules:

- Unknown `exploration_targets` fields are ignored.
- Empty `exploration_targets` falls back to recent events, scenario context, resources, and static targets.
- Invalid `quest_generation_options.domains` entries are ignored, matching current behavior.
- Invalid direct `payload.sub_agent` still returns `INVALID_SUB_AGENT`; after implementation, `quest_generator.exploration_quest` must no longer be invalid.
- If LLM text updates are malformed, preserve deterministic exploration draft quests.
- If top-level `quest_plan` omits or mismatches exploration intents, use deterministic combined fallback.

## Testing Plan

Add or update backend tests before implementation.

### Schema Tests

- `QuestPlanEnvelope` accepts `domain_mix.exploration`.
- `QuestPlanIntent.domain` accepts `"exploration"`.
- Invalid domains are still rejected.

### Leaf Agent Tests

- `ExplorationQuestAgent.fallback()` returns five quests by default.
- All fallback quests have `domain == "exploration"`.
- All fallback quests have `type` in `daily | weekly | surprise`.
- All fallback quests include `objectives`, `clear_condition`, and `rewards`.
- Manual clear conditions are used for non-resource exploration targets.
- Nested `quest_generation_options.count` is honored.
- Requested `quest_types` are honored.
- `current_main_quest` creates optional `main_quest_link`.
- `exploration_targets` influence objective ids, titles, or descriptions.
- `build_prompt()` includes `[RETRIEVED_GAME_CONTEXT]`.

### Router And Pipeline Tests

- Default router lists `quest_generator.exploration_quest`.
- Direct `payload.sub_agent: "quest_generator.exploration_quest"` returns `agent.response`.
- The old removed-sub-agent test no longer expects exploration to be rejected.
- Top-level fallback with `domain_counts: {"exploration": 2}` returns two exploration quests.
- Top-level fallback with mixed `production`, `delivery`, and `exploration` returns the requested counts.
- Top-level prompt includes exploration in `domain_mix`.
- Malformed LLM plan for exploration falls back safely.

### Documentation/Manifest Tests

- Agent connection manifest includes `quest_generator.exploration_quest`.
- Any contract tests that assert allowed leaf agents are updated.

## Implementation Order

1. Update schema tests for `QuestPlanDomainMix` and `QuestPlanIntent`.
2. Implement schema changes.
3. Add failing tests for direct exploration leaf routing.
4. Create `exploration_quest.py` with deterministic fallback and prompt generation.
5. Register `ExplorationQuestAgent` in the default router.
6. Update top-level `QUEST_DOMAINS`, `QUEST_SUB_AGENT_IDS`, domain mixing, and combined payload dispatch.
7. Add mixed top-level fallback tests.
8. Update prompt contract tests.
9. Update request documentation.
10. Run targeted tests, then the full backend test suite.

## Acceptance Criteria

The feature is complete when:

- `payload.sub_agent: "quest_generator.exploration_quest"` returns valid `agent.response`.
- `quest_generation_options.domain_counts.exploration` works in top-level generation.
- Generated exploration quests validate as `QuestResponse`.
- Generated exploration quests include rewards.
- Quest Lab can display exploration quests without a new response shape.
- The agent connection manifest lists the exploration leaf agent.
- Tests that previously rejected exploration are intentionally updated.

## Non-Goals

This MVP does not add:

- A real map, fog-of-war, scanner, or discovery event system.
- Server-side persistence of exploration completion.
- New `Quest.clear_condition.mode` values.
- New `MainQuestLink.relation_kind` values.
- New exploration CSV tables.
- Actual reward claiming or game inventory mutation.

Those should be planned after Quest Lab can generate and inspect exploration quests end to end.
