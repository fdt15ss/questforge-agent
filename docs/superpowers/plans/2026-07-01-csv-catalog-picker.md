# CSV Catalog Picker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Quest Lab의 인벤토리, 해금 장비, 해금 레시피 입력을 CSV 기준 선택 팝업으로 채울 수 있게 만든다.

**Architecture:** 기존 `data/game/quest_input_aliases.csv` raw import와 alias parser를 재사용한다. `questLab.ts`는 CSV 선택지를 제공하고 현재 textarea 값을 canonical id로 파싱하는 순수 함수를 노출한다. `App.tsx`는 선택 모달 상태를 관리하고 적용 시 기존 textarea 값을 CSV display name 기준 텍스트로 갱신한다.

**Tech Stack:** React 19, TypeScript, Vite raw CSV import, Vitest.

---

### Task 1: CSV catalog helper

**Files:**
- Modify: `frontend/src/lib/questLab.ts`
- Test: `frontend/src/lib/questLab.test.ts`

- [ ] `getQuestInputCatalogOptions(kind)`가 CSV의 `display_name`, `canonical_id`를 중복 없이 반환하는 실패 테스트를 추가한다.
- [ ] `parseInventoryText`, `parseListText`, `displayQuestInputAlias`를 UI에서 쓸 수 있도록 export하고 테스트를 통과시킨다.

### Task 2: Selection modal UI

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`
- Test: `frontend/src/App.test.tsx`

- [ ] App 렌더링 테스트에 인벤토리/장비/레시피 선택 버튼과 선택 모달 관련 class/label 기대값을 추가한다.
- [ ] 각 입력 영역의 라벨 줄에 `선택` 버튼을 추가한다.
- [ ] 모달에는 검색 입력, CSV 항목 목록, 인벤토리 수량 입력, 선택 적용/닫기 버튼을 제공한다.
- [ ] 적용 시 인벤토리는 `이름=수량`, 장비/레시피는 줄 단위 이름으로 textarea를 갱신한다.

### Task 3: Verification

**Files:**
- Test only.

- [ ] `pnpm --dir frontend test`를 실행해 모든 테스트가 통과하는지 확인한다.
- [ ] `pnpm --dir frontend build`를 실행해 타입스크립트와 번들이 통과하는지 확인한다.
- [ ] `git diff --check`로 공백 오류를 확인한다.