# Quest Reward Response Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 모든 생성 퀘스트 응답에 CSV 보상룰 기반의 필수 보상 정보를 포함한다.

**Architecture:** `data/game/quest_reward_rules.csv`를 `QuestDataRepository`에서 읽고, quest type과 진행 티어/player level에 맞는 reward rule을 선택한다. production/delivery leaf agent는 draft quest 생성 시 `rewards` 필드를 붙이고, parent `quest_generator`는 leaf 결과를 병합할 때 보상을 그대로 보존한다. LLM은 보상 구조를 절대 바꾸지 않고 제목/설명만 다듬는다.

**Tech Stack:** Python, Pydantic, LangGraph, CSV data repository, pytest

---

## 현재 분석

현재 `Quest` schema에는 보상 필드가 없습니다.

```python
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

보상 데이터는 이미 CSV에 있습니다.

- `data/game/quest_reward_rules.csv`
  - `보상룰ID`
  - `퀘스트타입`
  - `진행티어`
  - `권장레벨범위`
  - `기본XP`
  - `기본크레딧`
  - `보상자원그룹`
  - `보상자원수량범위`
  - `보상스케일링`
  - `LLM보상설명힌트`
- `data/game/quest_generation_rules.csv`
  - `보상룰ID`를 생성룰과 연결합니다.
- `data/game/recipes.csv`
  - 각 recipe row에도 `reward_daily_t1; reward_weekly_t1; reward_surprise_t1` 같은 보상룰ID 목록이 들어 있습니다.
- `data/game/troubleshooting_rules.csv`
  - troubleshooting 계열도 `보상룰ID목록`을 가지고 있습니다.

현재 `QuestDataRepository`는 `scenario_context.csv`, `resources.csv`, `recipes.csv`만 읽습니다. 따라서 reward row schema와 repository API를 추가해야 합니다.

## 결정 사항

- 응답 필드는 `rewards`로 둡니다.
- `rewards`는 퀘스트마다 필수이며 최소 1개 이상이어야 합니다.
- 기본 보상은 항상 XP와 credits를 포함합니다.
- CSV의 `보상자원그룹`을 해석할 수 있으면 resource 보상도 추가합니다.
- LLM은 `rewards`를 변경할 수 없습니다.
- CSV 룰 선택은 deterministic해야 합니다.
- 같은 요청은 같은 reward resource와 amount를 반환해야 합니다.
- reward rule을 찾지 못하면 quest type과 player level 기반 기본 룰로 fallback합니다.
- 그래도 실패하면 `reward_daily_t1`을 마지막 fallback으로 사용합니다.

## 응답 예시

```json
{
  "id": 1,
  "type": "daily",
  "domain": "production",
  "title": "철판 생산 안정화",
  "description": "철판 생산량을 보강해 다음 조립 공정을 준비하세요.",
  "objectives": [
    {
      "target_item_id": "resource_iron_plate",
      "quantity": 8
    }
  ],
  "clear_condition": {
    "mode": "objective_count",
    "target_item_id": "resource_iron_plate",
    "required_quantity": 8
  },
  "rewards": [
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
    },
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

---

## 파일 구조

- Modify: `backend/src/agents/quest_generator/schemas.py`
  - `QuestReward` 모델을 추가한다.
  - `Quest.rewards`를 필수 필드로 추가한다.
- Modify: `backend/src/quest_data/schemas.py`
  - `QuestRewardRuleRow` 모델을 추가한다.
  - `보상자원수량범위`의 `2-4` 형식을 `resource_quantity_min`, `resource_quantity_max`로 파싱한다.
- Modify: `backend/src/quest_data/repository.py`
  - `quest_reward_rules.csv` 로딩 캐시를 추가한다.
  - reward rule 조회 API를 추가한다.
  - resource group을 resource 후보로 변환하는 API를 추가한다.
- Create: `backend/src/agents/quest_generator/rewards.py`
  - reward rule 선택과 `rewards` payload 생성을 담당한다.
- Modify: `backend/src/agents/quest_generator/production_quest.py`
  - production draft quest 생성 시 `rewards`를 붙인다.
  - LLM prompt에 `rewards` 보존 지시를 추가한다.
- Modify: `backend/src/agents/quest_generator/delivery_quest.py`
  - delivery draft quest 생성 시 `rewards`를 붙인다.
  - LLM prompt에 `rewards` 보존 지시를 추가한다.
- Modify: `backend/src/agents/quest_generator/agent.py`
  - parent generator prompt에 `rewards` 보존 지시를 추가한다.
- Modify: `backend/tests/test_quest_agent_service.py`
  - production/parent reward 생성 테스트를 추가한다.
  - schema 필수 reward 테스트를 추가한다.
- Modify: `backend/tests/test_agent_leaf_behaviors.py`
  - prompt가 reward 보존을 지시하는지 검증한다.
  - delivery fallback reward 생성 테스트를 추가한다.
- Modify: `backend/tests/test_message_router.py`
  - LLM fixture JSON에 `rewards`를 추가한다.
- Modify: `backend/tests/test_pipeline_edges.py`
  - production quest fixture JSON에 `rewards`를 추가한다.

---

### Task 1: Quest schema에 필수 rewards 추가

**Files:**
- Modify: `backend/src/agents/quest_generator/schemas.py`
- Test: `backend/tests/test_quest_agent_service.py`

- [ ] **Step 1: failing schema test 추가**

`backend/tests/test_quest_agent_service.py`에 다음 테스트를 추가한다.

```python
def test_quest_response_requires_rewards() -> None:
    invalid_response = {
        "quests": [
            {
                "id": 1,
                "type": "daily",
                "domain": "production",
                "title": "reward missing",
                "description": "reward missing",
                "objectives": [
                    {
                        "target_item_id": "resource_iron_ore",
                        "quantity": 1,
                    }
                ],
                "clear_condition": {
                    "mode": "objective_count",
                    "target_item_id": "resource_iron_ore",
                    "required_quantity": 1,
                },
            }
        ]
    }

    try:
        QuestResponse.model_validate(invalid_response)
    except ValidationError as exc:
        assert "rewards" in str(exc)
    else:
        raise AssertionError("Expected ValidationError")
```

- [ ] **Step 2: RED 확인**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_quest_agent_service.py::test_quest_response_requires_rewards -q
```

Expected:

```text
FAILED ... Expected ValidationError
```

- [ ] **Step 3: `QuestReward` schema 추가**

`backend/src/agents/quest_generator/schemas.py`에서 `MainQuestLink` 아래에 추가한다.

```python
class QuestReward(BaseModel):
    """퀘스트 완료 시 지급할 보상 한 줄입니다."""

    reward_type: Literal["xp", "credits", "resource"]
    amount: int = Field(gt=0)
    resource_id: str | None = None
    resource_name: str | None = None
    source_rule_id: str = Field(min_length=1)
    description: str = Field(min_length=1)
```

- [ ] **Step 4: `Quest.rewards` 필수 필드 추가**

`Quest` 모델에 다음 필드를 추가한다.

```python
    rewards: list[QuestReward] = Field(min_length=1)
```

- [ ] **Step 5: schema test GREEN 확인**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_quest_agent_service.py::test_quest_response_requires_rewards -q
```

Expected:

```text
1 passed
```

---

### Task 2: reward CSV row schema와 repository API 추가

**Files:**
- Modify: `backend/src/quest_data/schemas.py`
- Modify: `backend/src/quest_data/repository.py`
- Test: `backend/tests/test_quest_agent_service.py`

- [ ] **Step 1: repository failing test 추가**

`backend/tests/test_quest_agent_service.py`에 다음 테스트를 추가한다.

```python
def test_repository_loads_reward_rules_from_csv() -> None:
    repository = QuestDataRepository()

    rule = repository.get_reward_rule("reward_daily_t2")

    assert rule.reward_rule_id == "reward_daily_t2"
    assert rule.quest_type == "daily"
    assert rule.tier == "T2"
    assert rule.base_xp == 120
    assert rule.base_credits == 35
    assert rule.resource_group == "기초 가공 자원"
    assert rule.resource_quantity_min == 2
    assert rule.resource_quantity_max == 4
    assert rule.llm_reward_hint
```

- [ ] **Step 2: RED 확인**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_quest_agent_service.py::test_repository_loads_reward_rules_from_csv -q
```

Expected:

```text
FAILED ... AttributeError: 'QuestDataRepository' object has no attribute 'get_reward_rule'
```

- [ ] **Step 3: reward range parser 추가**

`backend/src/quest_data/schemas.py`에 추가한다.

```python
def _parse_int_range(value: str) -> tuple[int, int]:
    parts = [part.strip() for part in value.split("-", 1)]
    if len(parts) != 2:
        return (1, 1)
    try:
        minimum = int(parts[0])
        maximum = int(parts[1])
    except ValueError:
        return (1, 1)
    if minimum <= 0 or maximum < minimum:
        return (1, 1)
    return (minimum, maximum)
```

- [ ] **Step 4: `QuestRewardRuleRow` 추가**

`backend/src/quest_data/schemas.py`에 추가한다.

```python
@dataclass(frozen=True)
class QuestRewardRuleRow:
    reward_rule_id: str
    quest_type: str
    tier: str
    recommended_level_range: str
    base_xp: int
    base_credits: int
    resource_group: str
    resource_quantity_min: int
    resource_quantity_max: int
    scaling: str
    llm_reward_hint: str

    @classmethod
    def from_csv_row(cls, row: dict[str, str]) -> QuestRewardRuleRow:
        quantity_min, quantity_max = _parse_int_range(row["보상자원수량범위"])
        return cls(
            reward_rule_id=row["보상룰ID"],
            quest_type=row["퀘스트타입"],
            tier=row["진행티어"],
            recommended_level_range=row["권장레벨범위"],
            base_xp=int(row["기본XP"]),
            base_credits=int(row["기본크레딧"]),
            resource_group=row["보상자원그룹"],
            resource_quantity_min=quantity_min,
            resource_quantity_max=quantity_max,
            scaling=row["보상스케일링"],
            llm_reward_hint=row["LLM보상설명힌트"],
        )
```

- [ ] **Step 5: repository import와 cache 추가**

`backend/src/quest_data/repository.py` import를 변경한다.

```python
from quest_data.schemas import (
    QuestRewardRuleRow,
    RecipeRow,
    ResourceRow,
    ScenarioContextRow,
)
```

`__init__`에 cache를 추가한다.

```python
        self._reward_rules: dict[str, QuestRewardRuleRow] | None = None
```

- [ ] **Step 6: repository API 추가**

`QuestDataRepository`에 추가한다.

```python
    def list_reward_rules(self) -> list[QuestRewardRuleRow]:
        return list(self._load_reward_rules().values())

    def get_reward_rule(self, reward_rule_id: str) -> QuestRewardRuleRow:
        reward_rules = self._load_reward_rules()
        try:
            return reward_rules[reward_rule_id]
        except KeyError as exc:
            raise KeyError(reward_rule_id) from exc

    def find_reward_rule(
        self,
        *,
        quest_type: str,
        tier: str,
    ) -> QuestRewardRuleRow:
        reward_rule_id = f"reward_{quest_type.lower()}_{tier.lower()}"
        try:
            return self.get_reward_rule(reward_rule_id)
        except KeyError:
            return self.get_reward_rule("reward_daily_t1")

    def list_resources(self) -> list[ResourceRow]:
        return list(self._load_resources().values())

    def find_reward_resource_candidates(self, resource_group: str) -> list[ResourceRow]:
        resources = self.list_resources()
        if "원재료" in resource_group or "보급품" in resource_group:
            return [resource for resource in resources if resource.resource_type == "원재료"]
        if "기초 가공" in resource_group or "긴급 가공" in resource_group:
            return [resource for resource in resources if resource.resource_type == "가공 자원"]
        if "중급" in resource_group:
            return [resource for resource in resources if resource.resource_type == "중간 부품"]
        if "고급" in resource_group:
            return [resource for resource in resources if resource.resource_type == "핵심 모듈"]
        return []
```

`_load_reward_rules()`를 추가한다.

```python
    def _load_reward_rules(self) -> dict[str, QuestRewardRuleRow]:
        if self._reward_rules is None:
            rows = load_csv_rows(self._game_data_dir / "quest_reward_rules.csv")
            reward_rules = [QuestRewardRuleRow.from_csv_row(row) for row in rows]
            self._reward_rules = {
                reward_rule.reward_rule_id: reward_rule
                for reward_rule in reward_rules
            }
        return self._reward_rules
```

- [ ] **Step 7: repository test GREEN 확인**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_quest_agent_service.py::test_repository_loads_reward_rules_from_csv -q
```

Expected:

```text
1 passed
```

---

### Task 3: reward payload builder 추가

**Files:**
- Create: `backend/src/agents/quest_generator/rewards.py`
- Test: `backend/tests/test_quest_agent_service.py`

- [ ] **Step 1: failing reward builder test 추가**

`backend/tests/test_quest_agent_service.py`에 추가한다.

```python
def test_build_quest_rewards_uses_quest_type_and_player_level() -> None:
    from agents.quest_generator.rewards import build_quest_rewards

    rewards = build_quest_rewards(
        quest_type="daily",
        target_item_id="resource_iron_plate",
        payload={"progression": {"player_level": 6}},
        context=_context(),
        repository=QuestDataRepository(),
    )

    assert rewards[0] == {
        "reward_type": "xp",
        "amount": 120,
        "source_rule_id": "reward_daily_t2",
        "description": "중반 진입 일일 퀘스트는 생산 라인 보강에 도움이 되는 보상으로 안내한다.",
    }
    assert rewards[1] == {
        "reward_type": "credits",
        "amount": 35,
        "source_rule_id": "reward_daily_t2",
        "description": "중반 진입 일일 퀘스트는 생산 라인 보강에 도움이 되는 보상으로 안내한다.",
    }
    assert rewards[2]["reward_type"] == "resource"
    assert rewards[2]["source_rule_id"] == "reward_daily_t2"
    assert 2 <= rewards[2]["amount"] <= 4
```

- [ ] **Step 2: RED 확인**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_quest_agent_service.py::test_build_quest_rewards_uses_quest_type_and_player_level -q
```

Expected:

```text
FAILED ... ModuleNotFoundError: No module named 'agents.quest_generator.rewards'
```

- [ ] **Step 3: `rewards.py` 생성**

`backend/src/agents/quest_generator/rewards.py`를 만든다.

```python
"""퀘스트 보상 payload를 CSV 보상룰에서 생성합니다."""

from __future__ import annotations

from typing import Any

from agents.base import AgentContext
from quest_data.repository import QuestDataRepository
from quest_data.schemas import QuestRewardRuleRow, ResourceRow


def _tier_from_payload(payload: dict[str, Any]) -> str:
    progression = payload.get("progression")
    player_level = None
    if isinstance(progression, dict):
        raw_level = progression.get("player_level")
        if isinstance(raw_level, int):
            player_level = raw_level
    if player_level is None:
        return "T1"
    if player_level <= 5:
        return "T1"
    if player_level <= 10:
        return "T2"
    if player_level <= 15:
        return "T3"
    return "T4"


def _deterministic_index(seed: str, length: int) -> int:
    if length <= 0:
        return 0
    return sum(ord(char) for char in seed) % length


def _deterministic_amount(
    *,
    rule: QuestRewardRuleRow,
    seed: str,
) -> int:
    spread = rule.resource_quantity_max - rule.resource_quantity_min
    if spread <= 0:
        return rule.resource_quantity_min
    return rule.resource_quantity_min + (sum(ord(char) for char in seed) % (spread + 1))


def _select_reward_resource(
    *,
    candidates: list[ResourceRow],
    target_item_id: str,
    quest_type: str,
    context: AgentContext,
) -> ResourceRow | None:
    if not candidates:
        return None
    seed = f"{target_item_id}:{quest_type}:{context.session_id}:{context.client_id}"
    return candidates[_deterministic_index(seed, len(candidates))]


def build_quest_rewards(
    *,
    quest_type: str,
    target_item_id: str,
    payload: dict[str, Any],
    context: AgentContext,
    repository: QuestDataRepository,
) -> list[dict[str, Any]]:
    """quest type과 진행도에 맞는 보상을 생성합니다."""

    tier = _tier_from_payload(payload)
    rule = repository.find_reward_rule(quest_type=quest_type, tier=tier)
    rewards: list[dict[str, Any]] = [
        {
            "reward_type": "xp",
            "amount": rule.base_xp,
            "source_rule_id": rule.reward_rule_id,
            "description": rule.llm_reward_hint,
        },
        {
            "reward_type": "credits",
            "amount": rule.base_credits,
            "source_rule_id": rule.reward_rule_id,
            "description": rule.llm_reward_hint,
        },
    ]

    candidates = repository.find_reward_resource_candidates(rule.resource_group)
    reward_resource = _select_reward_resource(
        candidates=candidates,
        target_item_id=target_item_id,
        quest_type=quest_type,
        context=context,
    )
    if reward_resource is not None:
        rewards.append(
            {
                "reward_type": "resource",
                "resource_id": reward_resource.resource_id,
                "resource_name": reward_resource.resource_name,
                "amount": _deterministic_amount(
                    rule=rule,
                    seed=f"{target_item_id}:{quest_type}:{rule.reward_rule_id}",
                ),
                "source_rule_id": rule.reward_rule_id,
                "description": f"{rule.resource_group} 보상",
            }
        )
    return rewards
```

- [ ] **Step 4: reward builder test GREEN 확인**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_quest_agent_service.py::test_build_quest_rewards_uses_quest_type_and_player_level -q
```

Expected:

```text
1 passed
```

---

### Task 4: production quest에 rewards 붙이기

**Files:**
- Modify: `backend/src/agents/quest_generator/production_quest.py`
- Test: `backend/tests/test_quest_agent_service.py`

- [ ] **Step 1: failing production test 추가**

`backend/tests/test_quest_agent_service.py`에 추가한다.

```python
def test_production_quest_fallback_attaches_required_rewards() -> None:
    agent = ProductionQuestAgent()

    result = agent.fallback(
        {
            "quest_generation_options": {
                "count": 1,
            },
            "progression": {
                "player_level": 6,
            },
            "resources": {
                "resource_iron_plate": 12,
            },
        },
        _context(),
    )

    quest = QuestResponse.model_validate(result.payload).quests[0]
    assert len(quest.rewards) >= 2
    assert quest.rewards[0].reward_type == "xp"
    assert quest.rewards[0].source_rule_id == "reward_daily_t2"
    assert quest.rewards[1].reward_type == "credits"
    assert quest.rewards[1].source_rule_id == "reward_daily_t2"
```

- [ ] **Step 2: RED 확인**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_quest_agent_service.py::test_production_quest_fallback_attaches_required_rewards -q
```

Expected:

```text
FAILED ... rewards
```

- [ ] **Step 3: production import 추가**

`backend/src/agents/quest_generator/production_quest.py`에 추가한다.

```python
from agents.quest_generator.rewards import build_quest_rewards
```

- [ ] **Step 4: production quest dict에 rewards 추가**

`build_quests()` 안에서 `quest = { ... }`를 만들 때 `clear_condition` 뒤에 추가한다.

```python
                "rewards": build_quest_rewards(
                    quest_type=quest_type,
                    target_item_id=target_item_id,
                    payload=state.get("payload", {}),
                    context=state["context"],
                    repository=repository,
                ),
```

- [ ] **Step 5: production prompt 보존 지시 추가**

`ProductionQuestAgent.build_prompt()`의 keep list에 `rewards`를 추가한다.

```python
            "objective target_item_id, objective quantity, clear_condition, "
            "rewards, and main_quest_link exactly as shown in DRAFT_QUESTS. "
```

`OUTPUT_CONTRACT` 예시에도 `rewards`를 추가한다.

```python
            '"quantity":1}],"clear_condition":{"mode":"objective_count",'
            '"target_item_id":"...","required_quantity":1},'
            '"rewards":[{"reward_type":"xp","amount":80,'
            '"source_rule_id":"reward_daily_t1","description":"..."}]}]}\n'
```

- [ ] **Step 6: production reward test GREEN 확인**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_quest_agent_service.py::test_production_quest_fallback_attaches_required_rewards -q
```

Expected:

```text
1 passed
```

---

### Task 5: delivery quest에 rewards 붙이기

**Files:**
- Modify: `backend/src/agents/quest_generator/delivery_quest.py`
- Test: `backend/tests/test_agent_leaf_behaviors.py`

- [ ] **Step 1: failing delivery test 추가**

`backend/tests/test_agent_leaf_behaviors.py`에 추가한다.

```python
def test_delivery_quest_fallback_attaches_required_rewards(
    context: AgentContext,
) -> None:
    agent = DeliveryQuestAgent()

    result = agent.fallback(
        {
            "quest_generation_options": {
                "count": 1,
            },
            "progression": {
                "player_level": 11,
            },
            "item": "resource_circuit_board",
            "quantity": 2,
            "destination": "central_storage",
        },
        context,
    )

    quest = QuestResponse.model_validate(result.payload).quests[0]
    assert quest.domain == "delivery"
    assert quest.rewards[0].reward_type == "xp"
    assert quest.rewards[0].source_rule_id == "reward_daily_t3"
    assert quest.rewards[1].reward_type == "credits"
```

- [ ] **Step 2: RED 확인**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_agent_leaf_behaviors.py::test_delivery_quest_fallback_attaches_required_rewards -q
```

Expected:

```text
FAILED ... rewards
```

- [ ] **Step 3: delivery imports 추가**

`backend/src/agents/quest_generator/delivery_quest.py`에 추가한다.

```python
from agents.quest_generator.rewards import build_quest_rewards
from quest_data.repository import QuestDataRepository
```

- [ ] **Step 4: `_build_delivery_payload()`에서 repository 생성**

함수 안에 추가한다.

```python
    repository = QuestDataRepository()
```

- [ ] **Step 5: delivery quest dict에 rewards 추가**

`quests.append({ ... })` dict에서 `clear_condition` 뒤에 추가한다.

```python
                "rewards": build_quest_rewards(
                    quest_type=quest_type,
                    target_item_id=item,
                    payload=state.get("payload", {}),
                    context=state["context"],
                    repository=repository,
                ),
```

- [ ] **Step 6: delivery prompt 보존 지시 추가**

`DeliveryQuestAgent.build_prompt()` 지시문에 `rewards`를 추가한다.

```python
                "objective target_item_id, objective quantity, clear_condition, "
                "and rewards exactly as shown in DRAFT_QUESTS. You may improve only title "
```

`OUTPUT_CONTRACT` 예시에도 rewards를 추가한다.

```python
                '"quantity":1}],"clear_condition":{"mode":"objective_count",'
                '"target_item_id":"...","required_quantity":1},'
                '"rewards":[{"reward_type":"xp","amount":80,'
                '"source_rule_id":"reward_daily_t1","description":"..."}]}]}\n'
```

- [ ] **Step 7: delivery reward test GREEN 확인**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_agent_leaf_behaviors.py::test_delivery_quest_fallback_attaches_required_rewards -q
```

Expected:

```text
1 passed
```

---

### Task 6: parent generator와 LLM fixtures 갱신

**Files:**
- Modify: `backend/src/agents/quest_generator/agent.py`
- Modify: `backend/tests/test_message_router.py`
- Modify: `backend/tests/test_pipeline_edges.py`

- [ ] **Step 1: parent reward preservation test 추가**

`backend/tests/test_quest_agent_service.py`에 추가한다.

```python
def test_quest_generator_fallback_preserves_child_rewards() -> None:
    agent = QuestGeneratorAgent()

    result = agent.fallback(
        {
            "quest_generation_options": {
                "count": 2,
            },
            "progression": {
                "player_level": 6,
            },
            "game_state": {
                "inventory": {
                    "resource_iron_plate": 12,
                }
            },
        },
        _context(),
    )

    quests = QuestResponse.model_validate(result.payload).quests
    assert len(quests) == 2
    assert all(quest.rewards for quest in quests)
    assert {quest.domain for quest in quests} == {"production", "delivery"}
```

- [ ] **Step 2: parent prompt rewards 보존 지시 추가**

`backend/src/agents/quest_generator/agent.py`의 `build_prompt()` keep list에 `rewards`를 추가한다.

```python
            "objective target_item_id, objective quantity, clear_condition, "
            "rewards, and main_quest_link exactly as shown in DRAFT_QUESTS. "
```

- [ ] **Step 3: LLM fixture helper 추가**

`backend/tests/test_message_router.py`와 `backend/tests/test_pipeline_edges.py`에서 반복 JSON fixture에 다음 reward payload를 넣는다.

```python
"rewards": [
    {
        "reward_type": "xp",
        "amount": 80,
        "source_rule_id": "reward_daily_t1",
        "description": "초반 일일 퀘스트는 빠르게 완료 가능한 보상으로 안내한다.",
    },
    {
        "reward_type": "credits",
        "amount": 20,
        "source_rule_id": "reward_daily_t1",
        "description": "초반 일일 퀘스트는 빠르게 완료 가능한 보상으로 안내한다.",
    },
],
```

- [ ] **Step 4: 관련 테스트 실행**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests/test_message_router.py backend/tests/test_pipeline_edges.py backend/tests/test_quest_agent_service.py -q
```

Expected:

```text
passed
```

---

### Task 7: 기존 tests 전체를 reward 필수 계약에 맞게 정리

**Files:**
- Modify: `backend/tests/test_agent_leaf_behaviors.py`
- Modify: `backend/tests/test_message_router.py`
- Modify: `backend/tests/test_pipeline_edges.py`
- Modify: `backend/tests/test_quest_agent_service.py`
- Modify: `backend/tests/test_smoke_agent_pipeline_script.py` if needed

- [ ] **Step 1: 전체 테스트 실행으로 누락 fixture 찾기**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests -q
```

Expected:

```text
FAIL ... rewards Field required
```

이 실패는 아직 reward fixture를 추가하지 않은 테스트를 알려주므로 정상입니다.

- [ ] **Step 2: 모든 QuestResponse fixture에 rewards 추가**

테스트 fixture의 quest dict마다 최소 보상을 추가한다.

```python
"rewards": [
    {
        "reward_type": "xp",
        "amount": 80,
        "source_rule_id": "reward_daily_t1",
        "description": "초반 일일 퀘스트는 빠르게 완료 가능한 보상으로 안내한다.",
    }
],
```

- [ ] **Step 3: invalid quantity 테스트 갱신**

`test_quest_response_rejects_invalid_quantity`의 invalid response에도 `rewards`를 추가해 quantity validation이 먼저 드러나게 한다.

```python
"rewards": [
    {
        "reward_type": "xp",
        "amount": 80,
        "source_rule_id": "reward_daily_t1",
        "description": "초반 일일 퀘스트는 빠르게 완료 가능한 보상으로 안내한다.",
    }
],
```

- [ ] **Step 4: 전체 테스트 GREEN 확인**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests -q
```

Expected:

```text
passed
```

---

### Task 8: 요청 구조 문서에 rewards 응답 예시 추가

**Files:**
- Modify: `docs/agent-request-structure.md`

- [ ] **Step 1: 응답 예시 섹션 추가**

`docs/agent-request-structure.md`에 `## 응답 rewards 구조` 섹션을 추가한다.

````markdown
## 응답 rewards 구조

모든 퀘스트는 `rewards`를 반드시 포함합니다.

```json
{
  "rewards": [
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
    },
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
````

- [ ] **Step 2: 문서 diff 확인**

Run:

```powershell
git diff -- docs/agent-request-structure.md
```

Expected:

```text
응답 rewards 구조 섹션이 추가되어 있어야 한다.
```

---

### Task 9: 최종 검증과 커밋

**Files:**
- All modified files

- [ ] **Step 1: 전체 테스트 실행**

Run:

```powershell
backend\.venv\Scripts\python.exe -m pytest backend/tests -q
```

Expected:

```text
0 failed
```

- [ ] **Step 2: 샘플 출력 확인**

Run:

```powershell
backend\.venv\Scripts\python.exe -c "import sys; sys.path.insert(0, 'backend/src'); from agents.quest_generator.agent import QuestGeneratorAgent; from agents.base import AgentContext; from agents.quest_generator.schemas import QuestResponse; ctx=AgentContext(request_id='r', session_id='s', client_id='c'); payload={'quest_generation_options': {'count': 2}, 'progression': {'player_level': 6}, 'game_state': {'inventory': {'resource_iron_plate': 12}}}; result=QuestGeneratorAgent().fallback(payload, ctx); quests=QuestResponse.model_validate(result.payload).quests; [print(q.id, q.domain, [(r.reward_type, r.amount, r.source_rule_id) for r in q.rewards]) for q in quests]"
```

Expected:

```text
각 quest마다 xp/credits/resource reward가 출력되어야 한다.
```

- [ ] **Step 3: staged 파일 확인**

Run:

```powershell
git status --short
```

Expected:

```text
reward 구현 관련 파일만 변경되어 있어야 한다.
```

- [ ] **Step 4: 커밋**

Run:

```powershell
git add backend/src/agents/quest_generator/schemas.py backend/src/quest_data/schemas.py backend/src/quest_data/repository.py backend/src/agents/quest_generator/rewards.py backend/src/agents/quest_generator/production_quest.py backend/src/agents/quest_generator/delivery_quest.py backend/src/agents/quest_generator/agent.py backend/tests/test_quest_agent_service.py backend/tests/test_agent_leaf_behaviors.py backend/tests/test_message_router.py backend/tests/test_pipeline_edges.py docs/agent-request-structure.md
git commit -m "feat: 퀘스트 응답에 CSV 기반 보상 추가"
```

---

## 완료 기준

- 모든 `Quest` 응답에 `rewards`가 필수로 포함된다.
- production, delivery, parent generator 응답 모두 rewards를 포함한다.
- rewards는 `quest_reward_rules.csv`의 quest type/tier/player level 기반 룰을 사용한다.
- XP와 credits는 항상 포함된다.
- resource group을 해석할 수 있으면 resource reward도 포함된다.
- LLM prompt는 rewards를 변경하지 말라고 명시한다.
- `QuestResponse` schema가 rewards 없는 quest를 거부한다.
- 전체 backend 테스트가 통과한다.
