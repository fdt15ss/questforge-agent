# Surprise Duration UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Quest Lab에서 돌발 퀘스트 제한 시간을 유동적으로 조절하고, 돌발 퀘스트 카드를 더 긴급하고 보기 좋게 표시한다.

**Architecture:** 백엔드는 `quest_generation_options.surprise_duration_minutes`를 읽어 surprise 타입의 `expires_at`만 생성 시각 기준 N분 뒤로 계산한다. 프론트엔드는 같은 옵션을 폼 상태와 JSON import/export에 연결하고, `QuestCard`는 surprise 타입일 때 전용 스타일과 시간 강조 배지를 사용한다.

**Tech Stack:** Python backend, Pydantic quest schema, React + TypeScript frontend, Vitest, Pytest.

---

### Task 1: Backend Surprise Deadline Option

**Files:**
- Modify: `backend/src/agents/quest_generator/deadlines.py`
- Modify: `backend/src/agents/quest_generator/production_quest.py`
- Modify: `backend/src/agents/quest_generator/delivery_quest.py`
- Modify: `backend/src/agents/quest_generator/exploration_quest.py`
- Test: `backend/tests/test_agent_leaf_behaviors.py`

- [ ] `quest_deadline("surprise", generated_at, surprise_duration_minutes=45)`가 45분 뒤를 반환하는 실패 테스트를 추가한다.
- [ ] leaf fallback payload의 `quest_generation_options.surprise_duration_minutes`가 production/delivery/exploration surprise `expires_at`에 반영되는 실패 테스트를 추가한다.
- [ ] `quest_deadline`에 `surprise_duration_minutes` 인자를 추가하고 1~1440분 범위로 보정한다.
- [ ] 각 leaf generator에서 payload options를 읽어 `quest_deadline`에 전달한다.

### Task 2: Frontend Request Option

**Files:**
- Modify: `frontend/src/lib/questLab.ts`
- Modify: `frontend/src/lib/questLab.test.ts`
- Modify: `frontend/src/App.tsx`

- [ ] `buildAgentRequest`가 `surprise_duration_minutes`를 payload에 포함하는 실패 테스트를 추가한다.
- [ ] `payloadToQuestContext`가 pasted JSON의 값을 폼 상태로 복원하는 실패 테스트를 추가한다.
- [ ] `QuestContextFormState`에 `surpriseDurationMinutes`를 추가하고 기본값 120을 둔다.
- [ ] Quest Lab 좌측 옵션 영역에 돌발 제한 시간 number input과 preset 버튼을 추가한다.

### Task 3: Surprise Card Visual Treatment

**Files:**
- Modify: `frontend/src/components/QuestCard.tsx`
- Modify: `frontend/src/styles.css`

- [ ] surprise 카드에 `is-surprise` 클래스를 추가한다.
- [ ] 카드 상단에 `긴급 대응` 배지를 추가한다.
- [ ] surprise 카드 배경, 테두리, 시간 배지를 별도 스타일로 강조한다.

### Task 4: Verification

**Files:**
- Test: `backend/tests/test_agent_leaf_behaviors.py`
- Test: `frontend/src/lib/questLab.test.ts`

- [ ] `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_agent_leaf_behaviors.py`를 통과시킨다.
- [ ] `pnpm --dir frontend test`를 통과시킨다.
- [ ] `pnpm --dir frontend build`를 통과시킨다.