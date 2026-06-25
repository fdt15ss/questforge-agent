import type {
  DomainCounts,
  QuestDomain,
  QuestLabItem,
  QuestObjective,
  QuestFromServer,
  QuestType,
} from "../types/quest";

export const QUEST_DOMAINS: QuestDomain[] = [
  "production",
  "delivery",
  "exploration",
];

export const QUEST_TYPES: QuestType[] = ["daily", "weekly", "surprise"];

export const DEFAULT_DOMAIN_COUNTS: DomainCounts = {
  production: 1,
  delivery: 1,
  exploration: 1,
};

export type QuestContextFormState = {
  progression: {
    stage: string;
    playerLevel: number;
  };
  inventoryText: string;
  unlockedEquipmentText: string;
  unlockedRecipesText: string;
  recentEventsText: string;
  mainQuestEnabled: boolean;
  mainQuest: {
    id: string;
    title: string;
    description: string;
    objectivesText: string;
  };
  explorationTargetsEnabled: boolean;
  explorationTargetsText: string;
};

export type AgentRequestPreview = {
  type: "agent.request";
  request_id: string;
  session_id: string;
  client_id: string;
  agent: "quest_generator";
  payload: Record<string, any>;
  websocketUrl: string;
};

export const DEFAULT_QUEST_CONTEXT: QuestContextFormState = {
  progression: {
    stage: "early_signal_recovery",
    playerLevel: 6,
  },
  inventoryText: "resource_iron_ore=35\nresource_copper_wire=12",
  unlockedEquipmentText: "equipment_miner\nequipment_smelter",
  unlockedRecipesText: "recipe_smelt_iron\nrecipe_craft_copper_wire",
  recentEventsText:
    "동쪽 능선 너머에서 약한 구조 신호가 반복 감지됐다.\n자기 폭풍 이후 광맥 스캐너가 불안정하다.",
  mainQuestEnabled: true,
  mainQuest: {
    id: "main_restore_signal",
    title: "장거리 신호 복구",
    description: "기지 밖 신호 간섭을 조사하고 장거리 통신을 복구한다.",
    objectivesText: "resource_circuit_board=10/4",
  },
  explorationTargetsEnabled: true,
  explorationTargetsText:
    "signal_east_ridge|동쪽 능선 신호|signal|resource_copper_ore\nsite_escape_pod_debris|탈출 포드 잔해|site|",
};
const LEGACY_DEFAULT_CONTEXT = {
  recentEventsText:
    "Weak rescue signal repeats beyond the east ridge.\nOre scanners became unstable after the magnetic storm.",
  mainQuestTitle: "Restore Long Range Signal",
  mainQuestDescription:
    "Investigate signal interference outside the base and restore long range communication.",
  explorationTargetsText:
    "signal_east_ridge|East Ridge Signal|signal|resource_copper_ore\nsite_escape_pod_debris|Escape Pod Debris|site|",
};

export function normalizeQuestContextDefaults(
  context: QuestContextFormState,
): QuestContextFormState {
  const mainQuest = {
    ...context.mainQuest,
    title:
      context.mainQuest.title === LEGACY_DEFAULT_CONTEXT.mainQuestTitle
        ? DEFAULT_QUEST_CONTEXT.mainQuest.title
        : context.mainQuest.title,
    description:
      context.mainQuest.description === LEGACY_DEFAULT_CONTEXT.mainQuestDescription
        ? DEFAULT_QUEST_CONTEXT.mainQuest.description
        : context.mainQuest.description,
  };

  return {
    ...context,
    recentEventsText:
      context.recentEventsText === LEGACY_DEFAULT_CONTEXT.recentEventsText
        ? DEFAULT_QUEST_CONTEXT.recentEventsText
        : context.recentEventsText,
    mainQuest,
    explorationTargetsText:
      context.explorationTargetsText === LEGACY_DEFAULT_CONTEXT.explorationTargetsText
        ? DEFAULT_QUEST_CONTEXT.explorationTargetsText
        : context.explorationTargetsText,
  };
}

export function createQuestLabItems(
  quests: QuestFromServer[],
  receivedAt = new Date().toISOString(),
): QuestLabItem[] {
  return quests.map((quest) => ({
    quest,
    status: "generated",
    progress: Object.fromEntries(
      quest.objectives.map((objective) => [objective.target_item_id, 0]),
    ),
    selected: false,
    receivedAt,
  }));
}

export function applyProgressDelta(
  item: QuestLabItem,
  targetItemId: string,
  delta: number,
): QuestLabItem {
  const current = item.progress[targetItemId] ?? 0;
  const progress = {
    ...item.progress,
    [targetItemId]: Math.max(0, current + delta),
  };
  const updated = {
    ...item,
    progress,
    status: "testing" as const,
  };
  return isQuestCleared(updated) ? { ...updated, status: "cleared" } : updated;
}

export function completeManualQuest(item: QuestLabItem): QuestLabItem {
  if (item.quest.clear_condition.mode !== "manual") {
    return item;
  }
  return {
    ...item,
    status: "cleared",
  };
}

export function resetQuestProgress(item: QuestLabItem): QuestLabItem {
  return {
    ...item,
    status: "generated",
    progress: Object.fromEntries(
      item.quest.objectives.map((objective) => [objective.target_item_id, 0]),
    ),
  };
}

export function isQuestCleared(item: QuestLabItem): boolean {
  if (item.status === "cleared") {
    return true;
  }
  const condition = item.quest.clear_condition;
  if (condition.mode === "manual") {
    return false;
  }
  return (
    (item.progress[condition.target_item_id] ?? 0) >=
    condition.required_quantity
  );
}

export function getObjectiveDisplay(
  objective: QuestObjective,
  domain?: QuestDomain | null,
): { kind: string; label: string; quantity: number } {
  const isExplorationAction =
    domain === "exploration" &&
    (objective.target_item_id.startsWith("exploration_") ||
      !objective.target_item_id.startsWith("resource_"));
  return {
    kind: isExplorationAction ? "탐험 목표" : "자원 목표",
    label: formatObjectiveId(objective.target_item_id, isExplorationAction),
    quantity: objective.quantity,
  };
}

export function formatObjectiveId(
  targetItemId: string,
  stripExplorationPrefix = false,
): string {
  const normalized = stripExplorationPrefix
    ? targetItemId.replace(/^exploration_/, "")
    : targetItemId.replace(/^resource_/, "");
  return normalized
    .split("_")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function parseListText(value: string): string[] {
  return value
    .split(/\r?\n|,/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function parseInventoryText(value: string): Record<string, number> {
  const inventory: Record<string, number> = {};
  for (const line of value.split(/\r?\n/)) {
    const [rawId, rawQuantity] = line.split(/[=:]/);
    const id = rawId?.trim();
    const quantity = Number(rawQuantity?.trim());
    if (id && Number.isFinite(quantity) && quantity > 0) {
      inventory[id] = Math.floor(quantity);
    }
  }
  return inventory;
}

function parseMainObjectivesText(value: string): {
  objectives: Array<{
    target_item_id: string;
    required_quantity: number;
    current_quantity: number;
  }>;
  progress: Record<string, number>;
} {
  const objectives: Array<{
    target_item_id: string;
    required_quantity: number;
    current_quantity: number;
  }> = [];
  const progress: Record<string, number> = {};

  for (const line of value.split(/\r?\n/)) {
    const [rawId, rawQuantities] = line.split(/[=:]/);
    const id = rawId?.trim();
    const [rawRequired, rawCurrent = "0"] = (rawQuantities ?? "").split("/");
    const required = Number(rawRequired?.trim());
    const current = Number(rawCurrent?.trim());
    if (!id || !Number.isFinite(required) || required <= 0) {
      continue;
    }
    const normalizedCurrent = Number.isFinite(current) && current > 0 ? current : 0;
    objectives.push({
      target_item_id: id,
      required_quantity: Math.floor(required),
      current_quantity: Math.floor(normalizedCurrent),
    });
    progress[id] = Math.floor(normalizedCurrent);
  }

  return { objectives, progress };
}

function parseExplorationTargetsText(value: string): Array<Record<string, string>> {
  const targets: Array<Record<string, string>> = [];
  for (const line of value.split(/\r?\n/)) {
    const [rawId, rawLabel, rawKind, rawResource] = line.split("|");
    const id = rawId?.trim();
    const label = rawLabel?.trim();
    const targetKind = rawKind?.trim();
    const relatedResourceId = rawResource?.trim();
    if (!id || !label || !targetKind) {
      continue;
    }
    const target: Record<string, string> = {
      id,
      label,
      target_kind: targetKind,
    };
    if (relatedResourceId) {
      target.related_resource_id = relatedResourceId;
    }
    targets.push(target);
  }
  return targets;
}

export function buildAgentRequest(input: {
  websocketUrl: string;
  domainCounts: DomainCounts;
  questTypes: QuestType[];
  context: QuestContextFormState;
}): AgentRequestPreview {
  const requestId = `quest-lab-${Date.now()}`;
  const context = input.context;
  const inventory = parseInventoryText(context.inventoryText);
  const unlockedEquipment = parseListText(context.unlockedEquipmentText);
  const unlockedRecipes = parseListText(context.unlockedRecipesText);
  const recentEvents = parseListText(context.recentEventsText);

  const payload: Record<string, any> = {
    quest_generation_options: {
      domain_counts: Object.fromEntries(
        Object.entries(input.domainCounts).filter(([, count]) => count > 0),
      ),
      quest_types: input.questTypes,
    },
    progression: {
      stage: context.progression.stage,
      player_level: Math.max(1, Math.floor(context.progression.playerLevel)),
    },
    game_state: {
      inventory,
      unlocked_equipment: unlockedEquipment,
      unlocked_recipes: unlockedRecipes,
    },
    recent_events: recentEvents,
  };

  if (context.mainQuestEnabled) {
    const { objectives, progress } = parseMainObjectivesText(
      context.mainQuest.objectivesText,
    );
    payload.current_main_quest = {
      id: context.mainQuest.id,
      title: context.mainQuest.title,
      description: context.mainQuest.description,
      objectives,
      progress,
    };
  }

  if (context.explorationTargetsEnabled) {
    payload.exploration_targets = parseExplorationTargetsText(
      context.explorationTargetsText,
    );
  }

  return {
    type: "agent.request",
    request_id: requestId,
    session_id: "quest-lab",
    client_id: "quest-lab-frontend",
    agent: "quest_generator",
    payload,
    websocketUrl: input.websocketUrl,
  };
}


export type QuestJsonImportResult = {
  domainCounts: DomainCounts;
  questTypes: QuestType[];
  context: QuestContextFormState;
  warnings: string[];
};

function isRecord(value: unknown): value is Record<string, any> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function parseJsonObject(jsonText: string): Record<string, any> {
  try {
    const parsed = JSON.parse(jsonText);
    if (!isRecord(parsed)) {
      throw new Error("payload 없음");
    }
    return parsed;
  } catch (error) {
    if (error instanceof SyntaxError) {
      throw new Error("JSON 형식이 올바르지 않습니다.");
    }
    throw error;
  }
}

function extractPayload(input: Record<string, any>): Record<string, any> {
  if (isRecord(input.payload)) {
    return input.payload;
  }
  if (isRecord(input.quest_generation_options)) {
    return input;
  }
  throw new Error("agent.request 전체 JSON이거나 payload JSON이어야 합니다.");
}

function normalizeDomainCounts(value: unknown): DomainCounts {
  const source = isRecord(value) ? value : {};
  return {
    production: Number.isFinite(Number(source.production))
      ? Math.max(0, Math.floor(Number(source.production)))
      : DEFAULT_DOMAIN_COUNTS.production,
    delivery: Number.isFinite(Number(source.delivery))
      ? Math.max(0, Math.floor(Number(source.delivery)))
      : DEFAULT_DOMAIN_COUNTS.delivery,
    exploration: Number.isFinite(Number(source.exploration))
      ? Math.max(0, Math.floor(Number(source.exploration)))
      : DEFAULT_DOMAIN_COUNTS.exploration,
  };
}

function normalizeQuestTypes(value: unknown): QuestType[] {
  if (!Array.isArray(value)) {
    return [...QUEST_TYPES];
  }
  const types = value.filter((item): item is QuestType =>
    QUEST_TYPES.includes(item as QuestType),
  );
  return types.length > 0 ? types : [...QUEST_TYPES];
}

function recordToLines(value: unknown): string {
  if (!isRecord(value)) {
    return "";
  }
  return Object.entries(value)
    .filter(([, quantity]) => Number.isFinite(Number(quantity)))
    .map(([id, quantity]) => `${id}=${Math.floor(Number(quantity))}`)
    .join("\n");
}

function arrayToLines(value: unknown): string {
  if (!Array.isArray(value)) {
    return "";
  }
  return value
    .filter((item): item is string => typeof item === "string" && item.trim().length > 0)
    .map((item) => item.trim())
    .join("\n");
}

function objectivesToText(mainQuest: Record<string, any>): string {
  const objectives = Array.isArray(mainQuest.objectives)
    ? mainQuest.objectives
    : [];
  const progress = isRecord(mainQuest.progress) ? mainQuest.progress : {};

  return objectives
    .map((objective) => {
      if (!isRecord(objective) || typeof objective.target_item_id !== "string") {
        return null;
      }
      const required = Number(
        objective.required_quantity ?? objective.quantity,
      );
      if (!Number.isFinite(required) || required <= 0) {
        return null;
      }
      const current = Number(
        objective.current_quantity ?? progress[objective.target_item_id] ?? 0,
      );
      const normalizedCurrent = Number.isFinite(current) && current > 0 ? current : 0;
      return `${objective.target_item_id}=${Math.floor(required)}/${Math.floor(normalizedCurrent)}`;
    })
    .filter((line): line is string => Boolean(line))
    .join("\n");
}

function explorationTargetsToText(value: unknown): string {
  if (!Array.isArray(value)) {
    return "";
  }
  return value
    .map((target) => {
      if (
        !isRecord(target) ||
        typeof target.id !== "string" ||
        typeof target.label !== "string" ||
        typeof target.target_kind !== "string"
      ) {
        return null;
      }
      const relatedResourceId =
        typeof target.related_resource_id === "string"
          ? target.related_resource_id
          : "";
      return `${target.id}|${target.label}|${target.target_kind}|${relatedResourceId}`;
    })
    .filter((line): line is string => Boolean(line))
    .join("\n");
}

export function payloadToQuestContext(payload: Record<string, any>): QuestJsonImportResult {
  const options = isRecord(payload.quest_generation_options)
    ? payload.quest_generation_options
    : {};
  const gameState = isRecord(payload.game_state) ? payload.game_state : {};
  const progression = isRecord(payload.progression) ? payload.progression : {};
  const currentMainQuest = isRecord(payload.current_main_quest)
    ? payload.current_main_quest
    : null;
  const explorationTargetsText = explorationTargetsToText(
    payload.exploration_targets,
  );

  const context: QuestContextFormState = {
    progression: {
      stage:
        typeof progression.stage === "string"
          ? progression.stage
          : DEFAULT_QUEST_CONTEXT.progression.stage,
      playerLevel: Number.isFinite(Number(progression.player_level))
        ? Math.max(1, Math.floor(Number(progression.player_level)))
        : DEFAULT_QUEST_CONTEXT.progression.playerLevel,
    },
    inventoryText: recordToLines(gameState.inventory),
    unlockedEquipmentText: arrayToLines(gameState.unlocked_equipment),
    unlockedRecipesText: arrayToLines(gameState.unlocked_recipes),
    recentEventsText: arrayToLines(payload.recent_events),
    mainQuestEnabled: Boolean(currentMainQuest),
    mainQuest: currentMainQuest
      ? {
          id:
            typeof currentMainQuest.id === "string"
              ? currentMainQuest.id
              : DEFAULT_QUEST_CONTEXT.mainQuest.id,
          title:
            typeof currentMainQuest.title === "string"
              ? currentMainQuest.title
              : DEFAULT_QUEST_CONTEXT.mainQuest.title,
          description:
            typeof currentMainQuest.description === "string"
              ? currentMainQuest.description
              : DEFAULT_QUEST_CONTEXT.mainQuest.description,
          objectivesText: objectivesToText(currentMainQuest),
        }
      : DEFAULT_QUEST_CONTEXT.mainQuest,
    explorationTargetsEnabled: Array.isArray(payload.exploration_targets),
    explorationTargetsText,
  };

  return {
    domainCounts: normalizeDomainCounts(options.domain_counts),
    questTypes: normalizeQuestTypes(options.quest_types),
    context: normalizeQuestContextDefaults(context),
    warnings: [],
  };
}

export function buildAgentRequestFromRawJson(
  jsonText: string,
  websocketUrl: string,
): AgentRequestPreview {
  const input = parseJsonObject(jsonText);
  const payload = extractPayload(input);
  if (!isRecord(payload.quest_generation_options)) {
    throw new Error("payload.quest_generation_options가 필요합니다.");
  }

  return {
    type: "agent.request",
    request_id:
      typeof input.request_id === "string"
        ? input.request_id
        : `quest-lab-${Date.now()}`,
    session_id:
      typeof input.session_id === "string" ? input.session_id : "quest-lab",
    client_id:
      typeof input.client_id === "string"
        ? input.client_id
        : "quest-lab-frontend",
    agent: "quest_generator",
    payload,
    websocketUrl,
  };
}

export function sampleExplorationQuest(): QuestFromServer {
  return {
    id: 901,
    type: "surprise",
    domain: "exploration",
    title: "동쪽 능선 신호 확인",
    description: "장거리 통신을 복구하기 전에 반복 감지되는 신호를 확인한다.",
    objectives: [{ target_item_id: "exploration_signal_ping", quantity: 1 }],
    clear_condition: {
      mode: "manual",
      label: "신호 확인 완료",
    },
    rewards: [
      {
        reward_type: "xp",
        amount: 120,
        source_rule_id: "reward_surprise_t1",
        description: "탐험 분석 경험치.",
      },
    ],
    main_quest_link: {
      main_quest_id: "main_restore_signal",
      main_quest_title: "장거리 신호 복구",
      relation_kind: "risk_buffer",
      reason: "통신 장비를 수리하기 전에 신호를 확인하면 작업 위험을 낮출 수 있다.",
    },
    metadata: {
      source: "frontend_sample",
    },
  };
}


