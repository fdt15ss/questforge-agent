# Exploration Quest Generation 구현 계획

> **agent 작업자 참고:** 이 계획을 작업 단위로 실행할 때는 `superpowers:subagent-driven-development` 또는 `superpowers:executing-plans`를 사용한다. 각 단계는 진행 추적을 위해 체크박스(`- [ ]`) 형식을 사용한다.

**목표:** 백엔드 `quest_generator`가 production, delivery와 함께 exploration 퀘스트를 실제로 생성하고, 프론트 Quest Lab에서 `domain_counts.exploration` 요청 결과를 받을 수 있게 만든다.

**아키텍처:** 기존 production/delivery leaf agent 패턴을 유지하면서 `ExplorationQuestAgent`를 새 leaf agent로 추가한다. 상위 `QuestGeneratorAgent`는 세 도메인을 같은 방식으로 분배하고, LLM이 실패하거나 schema를 어기면 deterministic fallback으로 유효한 `QuestResponse`를 반환한다.

**기술 스택:** Python, FastAPI/WebSocket, Pydantic, LangGraph, pytest, 기존 `data/game` CSV repository.

---

## 현재 문제

프론트에서 다음처럼 요청해도:

```json
{
  "quest_generation_options": {
    "domain_counts": {
      "production": 1,
      "delivery": 1,
      "exploration": 1
    }
  }
}
```

현재 백엔드 `QUEST_DOMAINS`가 다음 두 값만 허용한다.

```python
QUEST_DOMAINS = ("production", "delivery")
```

그래서 `exploration`은 요청에서 필터링되어 사라지고, 결과 metadata에도 다음처럼 두 도메인만 남는다.

```json
{
  "domains": ["production", "delivery"]
}
```

또한 `QuestPlanDomainMix`와 `QuestPlanIntent.domain`도 production/delivery만 허용하므로, LLM이 exploration을 포함해도 `invalid_schema`로 fallback될 수 있다.

---

## 작업 1: QuestPlan schema를 세 도메인으로 확장

**파일:**
- 수정: `backend/src/agents/quest_generator/schemas.py`
- 수정: `backend/tests/test_quest_agent_service.py`

- [ ] `QuestPlanDomainMix`에 `exploration` 필드를 추가한다.

```python
class QuestPlanDomainMix(BaseModel):
    production: int = Field(ge=0)
    delivery: int = Field(ge=0)
    exploration: int = Field(default=0, ge=0)
```

- [ ] `QuestPlanIntent.domain`의 Literal에 `"exploration"`을 추가한다.

```python
domain: Literal["production", "delivery", "exploration"]
```

- [ ] schema 테스트를 추가한다.

테스트 이름:

```text
test_quest_plan_schema_accepts_exploration_domain
test_quest_plan_schema_counts_exploration_domain
```

검증 내용:

- `domain_mix.exploration`이 `1` 이상이어도 validation을 통과한다.
- `quest_intents[].domain`이 `"exploration"`이어도 validation을 통과한다.
- `"economy"` 같은 미지원 domain은 여전히 validation 실패한다.

실행 명령:

```powershell
cd backend
backend\.venv\Scripts\python.exe -m pytest tests\test_quest_agent_service.py -q
```

---

## 작업 2: ExplorationQuestAgent leaf 추가

**파일:**
- 생성: `backend/src/agents/quest_generator/exploration_quest.py`
- 수정: `backend/tests/test_agent_leaf_behaviors.py`

- [ ] `ExplorationQuestAgent` 클래스를 추가한다.

기본 구조:

```python
class ExplorationQuestAgent:
    agent_id = "quest_generator.exploration_quest"
    tools = ()
    response_schema = QuestResponse
```

- [ ] LangGraph 노드는 production leaf와 같은 흐름을 따른다.

```text
START
-> exploration.normalize_payload
-> exploration.retrieve_context
-> exploration.build_quests
-> exploration.validate_response
-> END
```

- [ ] 기본 생성 개수와 타입 상수를 둔다.

```python
DEFAULT_EXPLORATION_QUEST_COUNT = 5
MAX_EXPLORATION_QUEST_COUNT = 10
DEFAULT_QUEST_TYPES = ("daily", "weekly", "surprise")
```

- [ ] fallback은 LLM 없이도 유효한 `QuestResponse`를 만든다.

필수 결과:

- 모든 quest의 `domain`은 `"exploration"`이다.
- 모든 quest의 `type`은 `daily`, `weekly`, `surprise` 중 하나다.
- 모든 quest는 `objectives`, `clear_condition`, `rewards`를 가진다.
- non-resource 탐험 목표는 기본적으로 `manual` 완료 조건을 사용한다.

- [ ] 탐험 target 후보는 다음 순서로 만든다.

1. `payload.exploration_targets`
2. `recent_events`
3. `current_main_quest.title` / `current_main_quest.description`
4. `scenario_context.csv`
5. 정적 fallback target

정적 fallback target:

```python
[
    "exploration_signal_ping",
    "exploration_crash_site_survey",
    "exploration_resource_scan",
    "exploration_route_check",
    "exploration_anomaly_probe",
]
```

- [ ] leaf agent 테스트를 추가한다.

테스트 이름:

```text
test_exploration_quest_fallback_returns_five_generated_quests
test_exploration_quest_fallback_honors_nested_count_override
test_exploration_quest_fallback_uses_requested_quest_types
test_exploration_quest_fallback_uses_manual_clear_for_action_targets
test_exploration_quest_fallback_uses_exploration_targets
test_exploration_quest_prompt_includes_retrieved_game_context
```

실행 명령:

```powershell
cd backend
backend\.venv\Scripts\python.exe -m pytest tests\test_agent_leaf_behaviors.py -q
```

---

## 작업 3: agent router에 exploration leaf 등록

**파일:**
- 수정: `backend/src/agents/router.py`
- 수정: `backend/tests/test_protocol_and_router.py`
- 수정: `backend/tests/test_agent_connection_router.py`
- 수정: `backend/tests/test_scenario_harness.py`

- [ ] `ExplorationQuestAgent`를 import한다.

```python
from agents.quest_generator.exploration_quest import ExplorationQuestAgent
```

- [ ] `create_default_agent_router()`에 등록한다.

```python
for agent in (
    QuestGeneratorAgent(),
    ProductionQuestAgent(),
    DeliveryQuestAgent(),
    ExplorationQuestAgent(),
):
    router.register(agent)
```

- [ ] `test_removed_quest_sub_agents_are_rejected`에서 `quest_generator.exploration_quest`를 제거한다.

이전에는 exploration이 제거된 leaf였지만, 이 구현 이후에는 허용되는 leaf가 된다.

- [ ] 직접 leaf 요청 테스트를 추가한다.

요청 예:

```json
{
  "type": "agent.request",
  "request_id": "request-exploration",
  "agent": "quest_generator",
  "payload": {
    "sub_agent": "quest_generator.exploration_quest",
    "quest_generation_options": {
      "count": 1
    }
  }
}
```

기대 결과:

- `type == "agent.response"`
- `payload.metadata.selectedLeafAgent == "quest_generator.exploration_quest"`
- `payload.quests[0].domain == "exploration"`

실행 명령:

```powershell
cd backend
backend\.venv\Scripts\python.exe -m pytest tests\test_protocol_and_router.py tests\test_agent_connection_router.py tests\test_scenario_harness.py -q
```

---

## 작업 4: 상위 QuestGeneratorAgent를 세 도메인으로 확장

**파일:**
- 수정: `backend/src/agents/quest_generator/agent.py`
- 수정: `backend/tests/test_quest_agent_service.py`
- 수정: `backend/tests/test_message_router.py`
- 수정: `backend/tests/test_agent_contracts.py`

- [ ] `QUEST_SUB_AGENT_IDS`에 exploration leaf를 추가한다.

```python
QUEST_SUB_AGENT_IDS = (
    "quest_generator.production_quest",
    "quest_generator.delivery_quest",
    "quest_generator.exploration_quest",
)
```

- [ ] `QUEST_DOMAINS`에 exploration을 추가한다.

```python
QUEST_DOMAINS = ("production", "delivery", "exploration")
```

- [ ] `QuestGeneratorAgent.__init__()`에서 exploration agent를 만든다.

```python
self.exploration_agent = ExplorationQuestAgent()
```

- [ ] `_domain_mix()`가 exploration을 세도록 변경한다.

```python
def _domain_mix(quests: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "production": sum(1 for quest in quests if quest["domain"] == "production"),
        "delivery": sum(1 for quest in quests if quest["domain"] == "delivery"),
        "exploration": sum(1 for quest in quests if quest["domain"] == "exploration"),
    }
```

- [ ] `_build_combined_payload()` dispatch를 명시적으로 분기한다.

```python
if domain == "production":
    result = self.production_agent.fallback(domain_payload, context)
elif domain == "delivery":
    result = self.delivery_agent.fallback(domain_payload, context)
elif domain == "exploration":
    result = self.exploration_agent.fallback(domain_payload, context)
else:
    continue
```

- [ ] top-level prompt 문구에서 production/delivery 전용 표현을 production/delivery/exploration으로 바꾼다.

- [ ] compact prompt의 `domain_counts`, `domain_mix`, output contract에 exploration이 포함되게 한다.

- [ ] 상위 fallback 테스트를 추가한다.

테스트 이름:

```text
test_quest_generator_fallback_uses_exploration_domain_counts
test_quest_generator_fallback_mixes_three_domains
test_quest_generator_prompt_contract_includes_exploration_domain_mix
test_pipeline_falls_back_when_exploration_quest_plan_mismatches_draft
```

검증 내용:

- `domain_counts: {"exploration": 2}` 요청 시 exploration 2개가 반환된다.
- `domain_counts: {"production": 1, "delivery": 1, "exploration": 1}` 요청 시 세 도메인이 각각 1개씩 반환된다.
- prompt contract의 `domain_mix`에 exploration이 포함된다.
- LLM plan이 exploration draft와 불일치하면 deterministic fallback으로 유효한 응답을 반환한다.

실행 명령:

```powershell
cd backend
backend\.venv\Scripts\python.exe -m pytest tests\test_quest_agent_service.py tests\test_message_router.py tests\test_agent_contracts.py -q
```

---

## 작업 5: 요청 문서와 README 갱신

**파일:**
- 수정: `docs/agent-request-structure.md`
- 수정: `README.md`
- 참고: `docs/superpowers/specs/2026-06-25-exploration-quest-generation-design.md`

- [ ] `docs/agent-request-structure.md`의 허용 leaf agent 목록에 exploration을 추가한다.

```text
quest_generator.exploration_quest
```

- [ ] `domain_counts` 예시에 exploration을 추가한다.

```json
{
  "quest_generation_options": {
    "domain_counts": {
      "production": 1,
      "delivery": 1,
      "exploration": 1
    }
  }
}
```

- [ ] 직접 exploration leaf 호출 예시를 추가한다.

```json
{
  "type": "agent.request",
  "request_id": "quest-exploration-only",
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
      }
    ]
  }
}
```

- [ ] `README.md`에는 구현 완료 후 실제 동작 기준으로 다음 내용을 반영한다.

반영 내용:

- 기본 도메인이 production, delivery, exploration임을 명시한다.
- `domain_counts.exploration` 사용 예시를 추가한다.
- Quest Lab에서 exploration 결과를 확인할 수 있다고 설명한다.

---

## 작업 6: 최종 검증

**파일:**
- 검증 실패가 발생한 파일만 수정한다.

- [ ] schema/leaf/router/top-level 테스트를 먼저 실행한다.

```powershell
cd backend
backend\.venv\Scripts\python.exe -m pytest tests\test_quest_agent_service.py tests\test_agent_leaf_behaviors.py tests\test_protocol_and_router.py tests\test_agent_connection_router.py tests\test_scenario_harness.py tests\test_message_router.py tests\test_agent_contracts.py -q
```

- [ ] 백엔드 전체 테스트를 실행한다.

```powershell
cd backend
backend\.venv\Scripts\python.exe -m pytest tests -q
```

- [ ] 서버를 실행한다.

```powershell
cd backend
uv run python scripts/run_server.py
```

- [ ] 프론트 Quest Lab에서 다음 요청을 보낸다.

```json
{
  "quest_generation_options": {
    "domain_counts": {
      "production": 1,
      "delivery": 1,
      "exploration": 1
    },
    "quest_types": ["daily", "weekly", "surprise"]
  }
}
```

- [ ] 응답에서 다음을 확인한다.

```text
quests 중 domain == "exploration"인 항목이 1개 이상 존재한다.
payload.metadata.domains에 "exploration"이 포함된다.
Quest Lab 카드에서 탐험 badge와 수동 완료 버튼이 표시된다.
```

---

## 완료 기준

- [ ] `payload.sub_agent: "quest_generator.exploration_quest"` 요청이 `agent.response`를 반환한다.
- [ ] `quest_generation_options.domain_counts.exploration`이 상위 `quest_generator`에서 동작한다.
- [ ] exploration 퀘스트가 `QuestResponse` validation을 통과한다.
- [ ] 모든 exploration 퀘스트에 `rewards`가 포함된다.
- [ ] agent connection manifest에 `quest_generator.exploration_quest`가 표시된다.
- [ ] 기존 production/delivery 테스트가 깨지지 않는다.
- [ ] Quest Lab에서 exploration 퀘스트를 별도 응답 shape 없이 표시할 수 있다.

## 이번 MVP에서 제외하는 것

- 실제 맵, fog-of-war, scanner, discovery event system
- 서버 DB 기반 탐험 완료 저장
- 보상 지급 처리
- 새 `Quest.clear_condition.mode`
- 새 `MainQuestLink.relation_kind`
- 새 exploration CSV 테이블
- 플레이어별 탐험 기록 동기화
