import { describe, expect, it } from "vitest";
import {
  DEFAULT_QUEST_CONTEXT,
  applyProgressDelta,
  buildAgentRequest,
  buildAgentRequestFromRawJson,
  completeManualQuest,
  createQuestLabItems,
  getObjectiveDisplay,
  isQuestCleared,
  normalizeQuestContextDefaults,
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

  it("labels exploration action ids as exploration objectives", () => {
    expect(getObjectiveDisplay(baseQuest.objectives[0], baseQuest.domain)).toEqual({
      kind: "탐험 목표",
      label: "Signal Ping",
      quantity: 1,
    });
  });
});

describe("quest context request builder", () => {
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
          objectivesText: "resource_circuit_board=10/4\nresource_copper_wire=12/7",
        },
        explorationTargetsEnabled: true,
        explorationTargetsText:
          "signal_east_ridge|동쪽 능선 신호|signal|resource_copper_ore\nsite_escape_pod_debris|탈출 포드 잔해|site|",
      },
    });

    expect(request.websocketUrl).toBe("ws://example/ws");
    expect(request.payload.quest_generation_options).toEqual({
      domain_counts: { production: 1, exploration: 1 },
      quest_types: ["daily", "surprise"],
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
      unlocked_equipment: ["equipment_miner", "equipment_assembler"],
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
        "signal_east_ridge|East Ridge Signal|signal|resource_copper_ore\nsite_escape_pod_debris|Escape Pod Debris|site|",
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
  const payload = {
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
      "resource_iron_ore=35\nresource_copper_wire=12",
    );
    expect(imported.context.unlockedEquipmentText).toBe(
      "equipment_miner\nequipment_smelter",
    );
    expect(imported.context.unlockedRecipesText).toBe("recipe_smelt_iron");
    expect(imported.context.recentEventsText).toContain("동쪽 능선 너머");
    expect(imported.context.mainQuestEnabled).toBe(true);
    expect(imported.context.mainQuest).toEqual({
      id: "main_restore_signal",
      title: "장거리 신호 복구",
      description: "기지 밖 신호 간섭을 조사하고 장거리 통신을 복구한다.",
      objectivesText:
        "resource_circuit_board=10/4\nresource_copper_wire=12/7",
    });
    expect(imported.context.explorationTargetsEnabled).toBe(true);
    expect(imported.context.explorationTargetsText).toBe(
      "signal_east_ridge|동쪽 능선 신호|signal|resource_copper_ore\nsite_escape_pod_debris|탈출 포드 잔해|site|",
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

