import { describe, expect, it } from "vitest";
import {
  DEFAULT_QUEST_CONTEXT,
  DEFAULT_QUEST_TYPE_COUNTS,
  appendQuestLabItems,
  applyProgressDelta,
  buildAgentRequest,
  buildAgentRequestFromRawJson,
  buildAgentTraceSummary,
  completeManualQuest,
  createQuestLabItems,
  getManualCompletionActionLabel,
  getQuestInputCatalogOptions,
  getObjectiveDisplay,
  getObjectiveProgressText,
  formatObjectiveId,
  formatQuestRemainingTime,
  localizeResourceTerms,
  isQuestCleared,
  isQuestExpired,
  normalizeQuestContextDefaults,
  parseInventoryText,
  parseListText,
  payloadToQuestContext,
} from "./questLab";
import type { QuestFromServer } from "../types/quest";

const baseQuest: QuestFromServer = {
  id: 1,
  type: "daily",
  domain: "exploration",
  title: "동쪽 능선 신호 확인",
  description: "장거리 통신을 복구하기 전에 신호를 확인한다.",
  objectives: [{ target_item_id: "exploration_signal_ping", quantity: 1 }],
  clear_condition: {
    mode: "manual",
    label: "신호 확인 완료",
  },
  rewards: [
    {
      reward_type: "xp",
      amount: 120,
      source_rule_id: "reward_daily_t1",
      description: "탐험 경험치.",
    },
  ],
};

describe("quest lab state helpers", () => {
  it("wraps server quests with local lab state", () => {
    const [item] = createQuestLabItems([baseQuest], "2026-06-25T00:00:00.000Z");

    expect(item.quest).toEqual(baseQuest);
    expect(item.status).toBe("generated");
    expect(item.progress).toEqual({ exploration_signal_ping: 0 });
    expect(item.receivedAt).toBe("2026-06-25T00:00:00.000Z");
  });

  it("prepends newly generated quests without dropping existing cards", () => {
    const existing = createQuestLabItems(
      [
        {
          ...baseQuest,
          id: 11,
          title: "existing quest",
        },
      ],
      "2026-06-25T00:00:00.000Z",
    );

    const merged = appendQuestLabItems(
      existing,
      [
        {
          ...baseQuest,
          id: 22,
          title: "new quest",
        },
      ],
      "2026-06-25T00:01:00.000Z",
    );

    expect(merged.map((item) => item.quest.title)).toEqual([
      "new quest",
      "existing quest",
    ]);
    expect(merged.map((item) => item.receivedAt)).toEqual([
      "2026-06-25T00:01:00.000Z",
      "2026-06-25T00:00:00.000Z",
    ]);
  });
  it("clears objective_count quests when progress reaches the required quantity", () => {
    const [item] = createQuestLabItems([
      {
        ...baseQuest,
        domain: "production",
        objectives: [{ target_item_id: "resource_iron_plate", quantity: 5 }],
        clear_condition: {
          mode: "objective_count",
          target_item_id: "resource_iron_plate",
          required_quantity: 5,
        },
      },
    ]);

    const almost = applyProgressDelta(item, "resource_iron_plate", 4);
    expect(isQuestCleared(almost)).toBe(false);

    const cleared = applyProgressDelta(almost, "resource_iron_plate", 1);
    expect(isQuestCleared(cleared)).toBe(true);
    expect(cleared.status).toBe("cleared");
  });

  it("clears manual exploration quests through the explicit completion action", () => {
    const [item] = createQuestLabItems([baseQuest]);

    expect(isQuestCleared(item)).toBe(false);
    expect(completeManualQuest(item).status).toBe("cleared");
  });

  it("detects quests whose expires_at is in the past", () => {
    expect(
      isQuestExpired(
        {
          ...baseQuest,
          expires_at: "2026-06-29T11:59:59+09:00",
        },
        Date.parse("2026-06-29T12:00:00+09:00"),
      ),
    ).toBe(true);
  });

  it("keeps quests without a valid expires_at visible", () => {
    expect(isQuestExpired(baseQuest, Date.parse("2026-06-29T12:00:00+09:00"))).toBe(false);
    expect(
      isQuestExpired(
        {
          ...baseQuest,
          expires_at: "not-a-date",
        },
        Date.parse("2026-06-29T12:00:00+09:00"),
      ),
    ).toBe(false);
  });

  it("formats quest remaining time from expires_at", () => {
    const now = Date.parse("2026-06-29T12:00:00+09:00");

    expect(
      formatQuestRemainingTime(
        {
          ...baseQuest,
          expires_at: "2026-06-29T14:30:00+09:00",
        },
        now,
      ),
    ).toBe("2시간 30분 남음");
    expect(
      formatQuestRemainingTime(
        {
          ...baseQuest,
          expires_at: "2026-07-01T12:00:00+09:00",
        },
        now,
      ),
    ).toBe("2일 남음");
    expect(formatQuestRemainingTime(baseQuest, now)).toBeNull();
  });
  it("formats known resource ids with Korean item names", () => {
    expect(formatObjectiveId("resource_iron_ore")).toBe("철광석");
    expect(formatObjectiveId("resource_iron_ingot")).toBe("철괴");
    expect(formatObjectiveId("resource_circuit_board")).toBe("회로기판");
  });
  it("localizes English resource terms inside display text", () => {
    expect(localizeResourceTerms("Collect 5 Iron Ore and craft a Circuit Board."))
      .toBe("Collect 5 철광석 and craft a 회로기판.");
    expect(localizeResourceTerms("deliver iron ingot before midnight"))
      .toBe("deliver 철괴 before midnight");
  });
  it("localizes English exploration target terms inside display text", () => {
    expect(localizeResourceTerms("Visit Signal East Ridge and Escape Pod Debris."))
      .toBe("Visit 동쪽 능선 신호 and 탈출 포드 잔해.");
    expect(localizeResourceTerms("Check East Ridge Signal before the next expedition."))
      .toBe("Check 동쪽 능선 신호 before the next expedition.");
  });
  it("labels exploration action ids as exploration objectives", () => {
    expect(getObjectiveDisplay(baseQuest.objectives[0], baseQuest.domain)).toEqual({
      kind: "탐험 목표",
      label: "Signal Ping",
      quantity: 1,
    });
  });
  it("hides numeric progress for manual exploration visit objectives", () => {
    const [item] = createQuestLabItems([baseQuest]);

    expect(getObjectiveProgressText(item, baseQuest.objectives[0])).toBeNull();
    expect(getManualCompletionActionLabel(baseQuest)).toBe("방문 완료");
  });
});

describe("quest context request builder", () => {
  it("shows default inventory, equipment, recipes, and objectives as Korean aliases", () => {
    expect(DEFAULT_QUEST_CONTEXT.inventoryText).toBe("철광석=35\n구리선=12");
    expect(DEFAULT_QUEST_CONTEXT.unlockedEquipmentText).toBe("채굴기\n제련기");
    expect(DEFAULT_QUEST_CONTEXT.unlockedRecipesText).toBe("철괴 제작 공정\n구리선 인발 공정");
    expect(DEFAULT_QUEST_CONTEXT.mainQuest.objectivesText).toBe("회로기판=10/4");
  });

  it("includes explicit quest type counts in agent requests", () => {
    const request = buildAgentRequest({
      websocketUrl: "ws://example/ws",
      domainCounts: { production: 3, delivery: 1, exploration: 1 },
      questTypes: ["daily", "weekly", "surprise"],
      questTypeCounts: { daily: 3, weekly: 1, surprise: 1 },
      context: DEFAULT_QUEST_CONTEXT,
    });

    expect(request.payload.quest_generation_options).toMatchObject({
      quest_types: ["daily", "weekly", "surprise"],
      quest_type_counts: { daily: 3, weekly: 1, surprise: 1 },
    });
  });
  it("includes the configurable surprise duration in agent requests", () => {
    const request = buildAgentRequest({
      websocketUrl: "ws://example/ws",
      domainCounts: { production: 0, delivery: 0, exploration: 1 },
      questTypes: ["surprise"],
      context: {
        ...DEFAULT_QUEST_CONTEXT,
        surpriseDurationMinutes: 45,
      } as any,
    });

    expect(request.payload.quest_generation_options).toMatchObject({
      surprise_duration_minutes: 45,
    });
  });

  it("uses source game CSVs for complete picker catalogs", () => {
    expect(getQuestInputCatalogOptions("resource")).toHaveLength(36);
    expect(getQuestInputCatalogOptions("equipment")).toHaveLength(12);
    expect(getQuestInputCatalogOptions("recipe")).toHaveLength(26);
    expect(getQuestInputCatalogOptions("resource")).toContainEqual({
      canonicalId: "resource_aluminum_ore",
      displayName: "\uC54C\uB8E8\uBBF8\uB284\uAD11\uC11D",
    });
    expect(getQuestInputCatalogOptions("recipe")).toContainEqual({
      canonicalId: "recipe_smelt_aluminum",
      displayName: "\uC54C\uB8E8\uBBF8\uB284\uAD34 \uC81C\uC791 \uACF5\uC815",
    });
  });
  it("exposes CSV catalog options for picker modals", () => {
    expect(getQuestInputCatalogOptions("resource")).toContainEqual({
      canonicalId: "resource_iron_ore",
      displayName: "철광석",
    });
    expect(getQuestInputCatalogOptions("equipment")).toContainEqual({
      canonicalId: "equipment_miner_machine",
      displayName: "채굴기",
    });
    expect(getQuestInputCatalogOptions("recipe")).toContainEqual({
      canonicalId: "recipe_smelt_iron",
      displayName: "철괴 제작 공정",
    });
    expect(parseInventoryText("철광석=7")).toEqual({
      resource_iron_ore: 7,
    });
    expect(parseListText("채굴기", "equipment")).toEqual([
      "equipment_miner_machine",
    ]);
  });
  it("resolves Korean aliases for inventory and unlocked equipment", () => {
    const request = buildAgentRequest({
      websocketUrl: "ws://example/ws",
      domainCounts: { production: 1, delivery: 0, exploration: 0 },
      questTypes: ["daily"],
      context: {
        ...DEFAULT_QUEST_CONTEXT,
        inventoryText: "\ucca0\uad11\uc11d=35\n\uad6c\ub9ac\uc120=12\n\ud68c\ub85c\uae30\ud310=4",
        unlockedEquipmentText: "\ucc44\uad74\uae30\n\uc81c\ub828\uae30\n\ubd84\uc1c4\uae30",
        unlockedRecipesText: "\ucca0\uad34 \uc81c\uc791 \uacf5\uc815",
        mainQuestEnabled: false,
        explorationTargetsEnabled: false,
      },
    });

    expect(request.payload.game_state).toMatchObject({
      inventory: {
        resource_iron_ore: 35,
        resource_copper_wire: 12,
        resource_circuit_board: 4,
      },
      unlocked_equipment: [
        "equipment_miner_machine",
        "equipment_smelter",
        "equipment_grinder",
      ],
      unlocked_recipes: ["recipe_smelt_iron"],
    });
  });

  it("builds agent requests from editable quest context", () => {
    const request = buildAgentRequest({
      websocketUrl: "ws://example/ws",
      domainCounts: { production: 1, delivery: 0, exploration: 1 },
      questTypes: ["daily", "surprise"],
      context: {
        ...DEFAULT_QUEST_CONTEXT,
        progression: {
          stage: "mid_factory_expansion",
          playerLevel: 9,
        },
        inventoryText: "resource_iron_plate=20\nresource_copper_wire=7",
        unlockedEquipmentText: "equipment_miner\nequipment_assembler",
        unlockedRecipesText: "recipe_craft_iron_plate",
        recentEventsText: "스캐너가 안정화됐다\n새 신호가 발견됐다",
        mainQuestEnabled: true,
        mainQuest: {
          id: "main_custom_signal",
          title: "사용자 지정 신호 복구",
          description: "사용자 지정 신호 체계를 복구한다.",
          objectivesText: "회로기판=10/4\n구리선=12/7",
        },
        explorationTargetsEnabled: true,
        explorationTargetsText:
          "signal_east_ridge|동쪽 능선 신호|signal|구리광석\nsite_escape_pod_debris|탈출 포드 잔해|site|",
      },
    });

    expect(request.websocketUrl).toBe("ws://example/ws");
    expect(request.payload.quest_generation_options).toEqual({
      domain_counts: { production: 1, exploration: 1 },
      quest_types: ["daily", "surprise"],
      quest_type_counts: { daily: 1, weekly: 0, surprise: 1 },
      surprise_duration_minutes: 120,
    });
    expect(request.payload.progression).toEqual({
      stage: "mid_factory_expansion",
      player_level: 9,
    });
    expect(request.payload.game_state).toEqual({
      inventory: {
        resource_iron_plate: 20,
        resource_copper_wire: 7,
      },
      unlocked_equipment: ["equipment_miner_machine", "equipment_assembler"],
      unlocked_recipes: ["recipe_craft_iron_plate"],
    });
    expect(request.payload.current_main_quest).toEqual({
      id: "main_custom_signal",
      title: "사용자 지정 신호 복구",
      description: "사용자 지정 신호 체계를 복구한다.",
      objectives: [
        {
          target_item_id: "resource_circuit_board",
          required_quantity: 10,
          current_quantity: 4,
        },
        {
          target_item_id: "resource_copper_wire",
          required_quantity: 12,
          current_quantity: 7,
        },
      ],
      progress: {
        resource_circuit_board: 4,
        resource_copper_wire: 7,
      },
    });
    expect(request.payload.recent_events).toEqual([
      "스캐너가 안정화됐다",
      "새 신호가 발견됐다",
    ]);
    expect(request.payload.exploration_targets).toEqual([
      {
        id: "signal_east_ridge",
        label: "동쪽 능선 신호",
        target_kind: "signal",
        related_resource_id: "resource_copper_ore",
      },
      {
        id: "site_escape_pod_debris",
        label: "탈출 포드 잔해",
        target_kind: "site",
      },
    ]);
  });

  it("normalizes legacy English default context text to Korean", () => {
    const normalized = normalizeQuestContextDefaults({
      ...DEFAULT_QUEST_CONTEXT,
      recentEventsText:
        "Weak rescue signal repeats beyond the east ridge.\nOre scanners became unstable after the magnetic storm.",
      mainQuest: {
        ...DEFAULT_QUEST_CONTEXT.mainQuest,
        title: "Restore Long Range Signal",
        description:
          "Investigate signal interference outside the base and restore long range communication.",
      },
      explorationTargetsText:
        "signal_east_ridge|East Ridge Signal|signal|구리광석\nsite_escape_pod_debris|Escape Pod Debris|site|",
    });

    expect(normalized.recentEventsText).toBe(DEFAULT_QUEST_CONTEXT.recentEventsText);
    expect(normalized.mainQuest.title).toBe("장거리 신호 복구");
    expect(normalized.mainQuest.description).toBe(
      "기지 밖 신호 간섭을 조사하고 장거리 통신을 복구한다.",
    );
    expect(normalized.explorationTargetsText).toBe(
      DEFAULT_QUEST_CONTEXT.explorationTargetsText,
    );
  });
  it("keeps the default sample context in Korean", () => {
    expect(DEFAULT_QUEST_CONTEXT.recentEventsText).toContain("동쪽 능선");
    expect(DEFAULT_QUEST_CONTEXT.mainQuest.title).toBe("장거리 신호 복구");
    expect(DEFAULT_QUEST_CONTEXT.explorationTargetsText).toContain("탈출 포드 잔해");
  });
});


describe("quest json input helpers", () => {

  it("maps pasted surprise duration JSON into quest context form state", () => {
    const imported = payloadToQuestContext({
      quest_generation_options: {
        domain_counts: { production: 0, delivery: 0, exploration: 1 },
        quest_types: ["surprise"],
        surprise_duration_minutes: 45,
      },
    });

    expect((imported.context as any).surpriseDurationMinutes).toBe(45);
  });
  it("allows pasted surprise duration down to one minute", () => {
    const imported = payloadToQuestContext({
      quest_generation_options: {
        surprise_duration_minutes: 1,
      },
    });

    expect((imported.context as any).surpriseDurationMinutes).toBe(1);
  });  const payload = {
    quest_generation_options: {
      domain_counts: {
        production: 2,
        delivery: 0,
        exploration: 1,
      },
      quest_types: ["daily", "weekly"],
    },
    progression: {
      stage: "early_signal_recovery",
      player_level: 6,
    },
    game_state: {
      inventory: {
        resource_iron_ore: 35,
        resource_copper_wire: 12,
      },
      unlocked_equipment: ["equipment_miner", "equipment_smelter"],
      unlocked_recipes: ["recipe_smelt_iron"],
    },
    recent_events: [
      "동쪽 능선 너머에서 약한 구조 신호가 반복 감지됐다.",
      "자기 폭풍 이후 광맥 스캐너가 불안정하다.",
    ],
    current_main_quest: {
      id: "main_restore_signal",
      title: "장거리 신호 복구",
      description: "기지 밖 신호 간섭을 조사하고 장거리 통신을 복구한다.",
      objectives: [
        {
          target_item_id: "resource_circuit_board",
          quantity: 10,
        },
        {
          target_item_id: "resource_copper_wire",
          required_quantity: 12,
          current_quantity: 7,
        },
      ],
      progress: {
        resource_circuit_board: 4,
      },
    },
    exploration_targets: [
      {
        id: "signal_east_ridge",
        label: "동쪽 능선 신호",
        target_kind: "signal",
        related_resource_id: "resource_copper_ore",
      },
      {
        id: "site_escape_pod_debris",
        label: "탈출 포드 잔해",
        target_kind: "site",
      },
    ],
  };

  it("maps pasted quest type counts into form state", () => {
    const imported = payloadToQuestContext({
      quest_generation_options: {
        domain_counts: { production: 3, delivery: 1, exploration: 1 },
        quest_type_counts: { daily: 3, weekly: 1, surprise: 1 },
        quest_types: ["daily", "weekly", "surprise"],
      },
    });

    expect(imported.questTypes).toEqual(["daily", "weekly", "surprise"]);
    expect(imported.questTypeCounts).toEqual({ daily: 3, weekly: 1, surprise: 1 });
  });

  it("uses default quest type counts", () => {
    expect(DEFAULT_QUEST_TYPE_COUNTS).toEqual({ daily: 1, weekly: 1, surprise: 1 });
  });
  it("maps pasted payload JSON into quest context form state", () => {
    const imported = payloadToQuestContext(payload);

    expect(imported.domainCounts).toEqual({
      production: 2,
      delivery: 0,
      exploration: 1,
    });
    expect(imported.questTypes).toEqual(["daily", "weekly"]);
    expect(imported.context.progression).toEqual({
      stage: "early_signal_recovery",
      playerLevel: 6,
    });
    expect(imported.context.inventoryText).toBe(
      "철광석=35\n구리선=12",
    );
    expect(imported.context.unlockedEquipmentText).toBe(
      "채굴기\n제련기",
    );
    expect(imported.context.unlockedRecipesText).toBe("철괴 제작 공정");
    expect(imported.context.recentEventsText).toContain("동쪽 능선 너머");
    expect(imported.context.mainQuestEnabled).toBe(true);
    expect(imported.context.mainQuest).toEqual({
      id: "main_restore_signal",
      title: "장거리 신호 복구",
      description: "기지 밖 신호 간섭을 조사하고 장거리 통신을 복구한다.",
      objectivesText:
        "회로기판=10/4\n구리선=12/7",
    });
    expect(imported.context.explorationTargetsEnabled).toBe(true);
    expect(imported.context.explorationTargetsText).toBe(
      "signal_east_ridge|동쪽 능선 신호|signal|구리광석\nsite_escape_pod_debris|탈출 포드 잔해|site|",
    );
  });

  it("builds a sendable request from payload-only JSON", () => {
    const request = buildAgentRequestFromRawJson(
      JSON.stringify(payload),
      "ws://example/ws",
    );

    expect(request.websocketUrl).toBe("ws://example/ws");
    expect(request.type).toBe("agent.request");
    expect(request.session_id).toBe("quest-lab");
    expect(request.client_id).toBe("quest-lab-frontend");
    expect(request.agent).toBe("quest_generator");
    expect(request.request_id).toMatch(/^quest-lab-/);
    expect(request.payload).toEqual(payload);
  });

  it("keeps full agent request fields when sending raw JSON", () => {
    const request = buildAgentRequestFromRawJson(
      JSON.stringify({
        type: "agent.request",
        request_id: "request-from-log",
        session_id: "custom-session",
        client_id: "external-client",
        agent: "quest_generator",
        payload,
      }),
      "ws://example/ws",
    );

    expect(request.request_id).toBe("request-from-log");
    expect(request.session_id).toBe("custom-session");
    expect(request.client_id).toBe("external-client");
    expect(request.payload).toEqual(payload);
  });

  it("rejects malformed pasted JSON with a Korean error", () => {
    expect(() => buildAgentRequestFromRawJson("{", "ws://example/ws")).toThrow(
      "JSON 형식이 올바르지 않습니다.",
    );
  });
});



describe("agent trace helpers", () => {
  it("summarizes agent response metadata for the trace panel", () => {
    const trace = buildAgentTraceSummary(
      {
        type: "agent.response",
        request_id: "quest-lab-trace",
        session_id: "quest-lab",
        client_id: "quest-lab-frontend",
        agent: "quest_generator",
        payload: {
          quests: [baseQuest],
          metadata: {
            selectedAgent: "quest_generator",
            selectedLeafAgent: "quest_generator.exploration_quest",
            llm: "used",
            llmProvider: "openai",
            llmModel: "gpt-4.1-mini",
            fallbackReason: "",
          },
        },
        streams: [],
      },
      742,
    );

    expect(trace.requestId).toBe("quest-lab-trace");
    expect(trace.agent).toBe("quest_generator");
    expect(trace.selectedLeafAgent).toBe("quest_generator.exploration_quest");
    expect(trace.llmStatus).toBe("used");
    expect(trace.llmProvider).toBe("openai");
    expect(trace.llmModel).toBe("gpt-4.1-mini");
    expect(trace.fallback).toBe(false);
    expect(trace.latencyMs).toBe(742);
    expect(trace.rawMetadataJson).toContain("selectedLeafAgent");
  });
});