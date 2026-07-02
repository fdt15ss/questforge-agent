import type {
  AgentResponseEnvelope,
  DomainCounts,
  QuestDomain,
  QuestLabItem,
  QuestObjective,
  QuestFromServer,
  QuestType,
} from "../types/quest";
import equipmentCsv from "../../../data/game/equipment.csv?raw";
import questInputAliasesCsv from "../../../data/game/quest_input_aliases.csv?raw";
import recipesCsv from "../../../data/game/recipes.csv?raw";
import resourcesCsv from "../../../data/game/resources.csv?raw";

export const QUEST_DOMAINS: QuestDomain[] = [
  "production",
  "delivery",
  "exploration",
];

export const QUEST_TYPES: QuestType[] = ["daily", "weekly", "surprise"];

export type QuestTypeCounts = Record<QuestType, number>;

export const DEFAULT_QUEST_TYPE_COUNTS: QuestTypeCounts = {
  daily: 1,
  weekly: 1,
  surprise: 1,
};

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
  surpriseDurationMinutes: number;
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
  inventoryText: "철광석=35\n구리선=12",
  unlockedEquipmentText: "채굴기\n제련기",
  unlockedRecipesText: "철괴 제작 공정\n구리선 인발 공정",
  recentEventsText:
    "동쪽 능선 너머에서 약한 구조 신호가 반복 감지됐다.\n자기 폭풍 이후 광맥 스캐너가 불안정하다.",
  surpriseDurationMinutes: 120,
  mainQuestEnabled: true,
  mainQuest: {
    id: "main_restore_signal",
    title: "장거리 신호 복구",
    description: "기지 밖 신호 간섭을 조사하고 장거리 통신을 복구한다.",
    objectivesText: "회로기판=10/4",
  },
  explorationTargetsEnabled: true,
  explorationTargetsText:
    "signal_east_ridge|동쪽 능선 신호|signal|구리광석\nsite_escape_pod_debris|탈출 포드 잔해|site|",
};
const LEGACY_DEFAULT_CONTEXT = {
  recentEventsText:
    "Weak rescue signal repeats beyond the east ridge.\nOre scanners became unstable after the magnetic storm.",
  mainQuestTitle: "Restore Long Range Signal",
  mainQuestDescription:
    "Investigate signal interference outside the base and restore long range communication.",
  explorationTargetsText:
    "signal_east_ridge|East Ridge Signal|signal|구리광석\nsite_escape_pod_debris|Escape Pod Debris|site|",
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
    surpriseDurationMinutes: normalizeSurpriseDurationMinutes(
      (context as Partial<QuestContextFormState>).surpriseDurationMinutes,
    ),
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

export function appendQuestLabItems(
  currentItems: QuestLabItem[],
  quests: QuestFromServer[],
  receivedAt = new Date().toISOString(),
): QuestLabItem[] {
  return [...createQuestLabItems(quests, receivedAt), ...currentItems];
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


export type AgentTraceSummary = {
  requestId: string;
  agent: string;
  selectedAgent: string;
  selectedLeafAgent: string;
  llmStatus: string;
  llmProvider: string;
  llmModel: string;
  fallback: boolean;
  fallbackReason: string;
  latencyMs: number | null;
  rawMetadataJson: string;
};

function metadataString(
  metadata: Record<string, unknown>,
  key: string,
  fallback = "-",
): string {
  const value = metadata[key];
  return typeof value === "string" && value.trim() ? value : fallback;
}

export function buildAgentTraceSummary(
  envelope: AgentResponseEnvelope,
  latencyMs: number | null = null,
): AgentTraceSummary {
  const metadata = envelope.payload.metadata ?? {};
  const fallback = metadata["fallback"] === true;
  const fallbackReason = metadataString(metadata, "fallbackReason", "");
  return {
    requestId: envelope.request_id,
    agent: envelope.agent,
    selectedAgent: metadataString(metadata, "selectedAgent", envelope.agent),
    selectedLeafAgent: metadataString(metadata, "selectedLeafAgent"),
    llmStatus: metadataString(metadata, "llm", fallback ? "fallback" : "not used"),
    llmProvider: metadataString(metadata, "llmProvider"),
    llmModel: metadataString(metadata, "llmModel"),
    fallback,
    fallbackReason,
    latencyMs,
    rawMetadataJson: JSON.stringify(metadata, null, 2),
  };
}

export function isManualExplorationQuest(quest: QuestFromServer): boolean {
  return quest.domain === "exploration" && quest.clear_condition.mode === "manual";
}

export function getObjectiveProgressText(
  item: QuestLabItem,
  objective: QuestObjective,
): string | null {
  if (isManualExplorationQuest(item.quest)) {
    return null;
  }
  return `${item.progress[objective.target_item_id] ?? 0} / ${objective.quantity}`;
}

export function getManualCompletionActionLabel(quest: QuestFromServer): string {
  return isManualExplorationQuest(quest) ? "방문 완료" : "완료 처리";
}
export function getQuestExpirationTime(quest: QuestFromServer): number | null {
  if (!quest.expires_at) {
    return null;
  }
  const expiresAt = Date.parse(quest.expires_at);
  return Number.isFinite(expiresAt) ? expiresAt : null;
}

export function formatQuestRemainingTime(
  quest: QuestFromServer,
  nowMs = Date.now(),
): string | null {
  const expiresAt = getQuestExpirationTime(quest);
  if (expiresAt === null) {
    return null;
  }

  const remainingMs = expiresAt - nowMs;
  if (remainingMs <= 0) {
    return "만료됨";
  }

  const totalMinutes = Math.ceil(remainingMs / 60_000);
  const days = Math.floor(totalMinutes / (24 * 60));
  const hours = Math.floor((totalMinutes % (24 * 60)) / 60);
  const minutes = totalMinutes % 60;

  if (days > 0) {
    return hours > 0 ? `${days}일 ${hours}시간 남음` : `${days}일 남음`;
  }
  if (hours > 0) {
    return minutes > 0
      ? `${hours}시간 ${minutes}분 남음`
      : `${hours}시간 남음`;
  }
  if (minutes > 0) {
    return `${minutes}분 남음`;
  }
  return "1분 미만 남음";
}

export function isQuestExpired(
  quest: QuestFromServer,
  nowMs = Date.now(),
): boolean {
  const expiresAt = getQuestExpirationTime(quest);
  return expiresAt !== null && expiresAt <= nowMs;
}
const RESOURCE_DISPLAY_NAMES: Record<string, string> = {
  aluminum_ingot: "알루미늄괴",
  aluminum_ore: "알루미늄광석",
  battery_electrolyte: "배터리 전해질",
  carbon_composite: "탄소 복합재",
  circuit_board: "회로기판",
  coal: "석탄",
  cockpit_canopy: "조종석 캐노피",
  copper_ingot: "구리괴",
  copper_ore: "구리광석",
  copper_wire: "구리선",
  cryogenic_coolant: "극저온 냉각수",
  engine_frame: "엔진 프레임",
  fuel_cell: "연료전지",
  glass: "유리",
  helium: "헬륨",
  hull_frame: "선체 프레임",
  hydrogen: "수소",
  ion_propellant: "이온 추진제",
  iron_ingot: "철괴",
  iron_ore: "철광석",
  iron_plate: "철판",
  life_support_module: "생명유지 모듈",
  lightweight_alloy_plate: "경량 합금판",
  navigation_computer: "항법 컴퓨터",
  outer_panel: "외장 패널",
  oxygen: "산소",
  propulsion_core: "추진 코어",
  reinforced_glass: "강화 유리",
  sand: "모래",
  scout_spaceship: "소형 탐사 우주선",
  sulfur_ore: "황광석",
  sulfur_powder: "황 분말",
  titanium_alloy: "티타늄 합금",
  titanium_ingot: "티타늄괴",
  titanium_ore: "티타늄광석",
  water: "물",
};

const EXPLORATION_TARGET_DISPLAY_NAMES: Record<string, string> = {
  "East Ridge Signal": "동쪽 능선 신호",
  "Signal East Ridge": "동쪽 능선 신호",
  "Escape Pod Debris": "탈출 포드 잔해",
  "Site Escape Pod Debris": "탈출 포드 잔해",
};

function humanizeIdentifier(value: string): string {
  return value
    .split("_")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

const DISPLAY_TEXT_REPLACEMENTS = [
  ...Object.entries(RESOURCE_DISPLAY_NAMES).map(([resourceKey, displayName]) => ({
    pattern: new RegExp(`\\b${escapeRegExp(humanizeIdentifier(resourceKey))}\\b`, "gi"),
    displayName,
  })),
  ...Object.entries(EXPLORATION_TARGET_DISPLAY_NAMES).map(
    ([targetName, displayName]) => ({
      pattern: new RegExp(`\\b${escapeRegExp(targetName)}\\b`, "gi"),
      displayName,
    }),
  ),
];

export function localizeResourceTerms(text: string): string {
  return DISPLAY_TEXT_REPLACEMENTS.reduce(
    (localized, replacement) =>
      localized.replace(replacement.pattern, replacement.displayName),
    text,
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
  const resourceDisplayName = RESOURCE_DISPLAY_NAMES[normalized];
  if (resourceDisplayName) {
    return resourceDisplayName;
  }
  return humanizeIdentifier(normalized);
}

export type QuestInputAliasKind = "resource" | "equipment" | "recipe" | "exploration_target";

export type QuestInputCatalogOption = {
  canonicalId: string;
  displayName: string;
};

type QuestInputAliasLookup = {
  canonicalIds: Record<QuestInputAliasKind, Record<string, string>>;
  displayNames: Record<QuestInputAliasKind, Record<string, string>>;
};

function createQuestInputAliasLookup(): QuestInputAliasLookup {
  return {
    canonicalIds: {
      resource: {},
      equipment: {},
      recipe: {},
      exploration_target: {},
    },
    displayNames: {
      resource: {},
      equipment: {},
      recipe: {},
      exploration_target: {},
    },
  };
}

function normalizeAliasKey(value: string): string {
  return value.trim().replace(/\s+/g, " ").toLowerCase();
}

function splitCsvLine(line: string): string[] {
  const values: string[] = [];
  let current = "";
  let inQuotes = false;

  for (let index = 0; index < line.length; index += 1) {
    const char = line[index];
    const next = line[index + 1];
    if (char === '"' && next === '"' && inQuotes) {
      current += '"';
      index += 1;
      continue;
    }
    if (char === '"') {
      inQuotes = !inQuotes;
      continue;
    }
    if (char === "," && !inQuotes) {
      values.push(current.trim());
      current = "";
      continue;
    }
    current += char;
  }

  values.push(current.trim());
  return values;
}

function buildQuestInputAliasLookup(csvText: string): QuestInputAliasLookup {
  const lookup = createQuestInputAliasLookup();
  const [headerLine, ...rows] = csvText
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
  if (!headerLine) {
    return lookup;
  }

  const headers = splitCsvLine(headerLine);
  const kindIndex = headers.indexOf("kind");
  const aliasIndex = headers.indexOf("alias");
  const canonicalIdIndex = headers.indexOf("canonical_id");
  const displayNameIndex = headers.indexOf("display_name");
  if (kindIndex < 0 || aliasIndex < 0 || canonicalIdIndex < 0) {
    return lookup;
  }

  for (const row of rows) {
    const cells = splitCsvLine(row);
    const kind = cells[kindIndex] as QuestInputAliasKind | undefined;
    const alias = cells[aliasIndex]?.trim();
    const canonicalId = cells[canonicalIdIndex]?.trim();
    const displayName = displayNameIndex >= 0 ? cells[displayNameIndex]?.trim() : "";
    if (!kind || !(kind in lookup.canonicalIds) || !alias || !canonicalId) {
      continue;
    }
    lookup.canonicalIds[kind][normalizeAliasKey(alias)] = canonicalId;
    lookup.canonicalIds[kind][normalizeAliasKey(canonicalId)] = canonicalId;
    lookup.displayNames[kind][canonicalId] = displayName || alias;
  }

  return lookup;
}

const QUEST_INPUT_ALIAS_LOOKUP = buildQuestInputAliasLookup(questInputAliasesCsv);

function buildQuestInputCatalogOptions(csvText: string): QuestInputCatalogOption[] {
  const [, ...rows] = csvText
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
  const options = new Map<string, QuestInputCatalogOption>();

  for (const row of rows) {
    const cells = splitCsvLine(row);
    const canonicalId = cells[0]?.trim();
    const displayName = cells[1]?.trim();
    if (!canonicalId || !displayName) {
      continue;
    }
    options.set(canonicalId, { canonicalId, displayName });
  }

  return [...options.values()].sort((left, right) =>
    left.displayName.localeCompare(right.displayName, "ko"),
  );
}

const QUEST_INPUT_CATALOG_OPTIONS: Record<QuestInputAliasKind, QuestInputCatalogOption[]> = {
  resource: buildQuestInputCatalogOptions(resourcesCsv),
  equipment: buildQuestInputCatalogOptions(equipmentCsv),
  recipe: buildQuestInputCatalogOptions(recipesCsv),
  exploration_target: getAliasCatalogOptions("exploration_target"),
};

function getAliasCatalogOptions(kind: QuestInputAliasKind): QuestInputCatalogOption[] {
  return Object.entries(QUEST_INPUT_ALIAS_LOOKUP.displayNames[kind])
    .map(([canonicalId, displayName]) => ({ canonicalId, displayName }))
    .sort((left, right) => left.displayName.localeCompare(right.displayName, "ko"));
}

export function getQuestInputCatalogOptions(kind: QuestInputAliasKind): QuestInputCatalogOption[] {
  return QUEST_INPUT_CATALOG_OPTIONS[kind];
}

function resolveQuestInputAlias(kind: QuestInputAliasKind, value: string): string {
  return QUEST_INPUT_ALIAS_LOOKUP.canonicalIds[kind][normalizeAliasKey(value)] ?? value.trim();
}

export function displayQuestInputAlias(kind: QuestInputAliasKind, value: string): string {
  const canonicalId = resolveQuestInputAlias(kind, value);
  return QUEST_INPUT_ALIAS_LOOKUP.displayNames[kind][canonicalId] ?? value.trim();
}
export function parseListText(value: string, aliasKind?: QuestInputAliasKind): string[] {
  return value
    .split(/\r?\n|,/)
    .map((item) => item.trim())
    .filter(Boolean)
    .map((item) => (aliasKind ? resolveQuestInputAlias(aliasKind, item) : item));
}

export function parseInventoryText(value: string): Record<string, number> {
  const inventory: Record<string, number> = {};
  for (const line of value.split(/\r?\n/)) {
    const [rawId, rawQuantity] = line.split(/[=:]/);
    const id = rawId?.trim();
    const quantity = Number(rawQuantity?.trim());
    if (id && Number.isFinite(quantity) && quantity > 0) {
      inventory[resolveQuestInputAlias("resource", id)] = Math.floor(quantity);
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
      target_item_id: resolveQuestInputAlias("resource", id),
      required_quantity: Math.floor(required),
      current_quantity: Math.floor(normalizedCurrent),
    });
    progress[resolveQuestInputAlias("resource", id)] = Math.floor(normalizedCurrent);
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
      target.related_resource_id = resolveQuestInputAlias("resource", relatedResourceId);
    }
    targets.push(target);
  }
  return targets;
}

export function buildAgentRequest(input: {
  websocketUrl: string;
  domainCounts: DomainCounts;
  questTypes: QuestType[];
  questTypeCounts?: QuestTypeCounts;
  context: QuestContextFormState;
}): AgentRequestPreview {
  const requestId = `quest-lab-${Date.now()}`;
  const context = input.context;
  const inventory = parseInventoryText(context.inventoryText);
  const unlockedEquipment = parseListText(context.unlockedEquipmentText, "equipment");
  const unlockedRecipes = parseListText(context.unlockedRecipesText, "recipe");
  const recentEvents = parseListText(context.recentEventsText);

  const payload: Record<string, any> = {
    quest_generation_options: {
      domain_counts: Object.fromEntries(
        Object.entries(input.domainCounts).filter(([, count]) => count > 0),
      ),
      quest_types: getQuestTypesFromCounts(
        input.questTypeCounts ?? questTypeCountsFromTypes(input.questTypes),
      ),
      quest_type_counts: input.questTypeCounts ?? questTypeCountsFromTypes(input.questTypes),
      surprise_duration_minutes: normalizeSurpriseDurationMinutes(
        context.surpriseDurationMinutes,
      ),
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
  questTypeCounts?: QuestTypeCounts;
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

function normalizeSurpriseDurationMinutes(value: unknown): number {
  const minutes = Number(value);
  if (!Number.isFinite(minutes)) {
    return DEFAULT_QUEST_CONTEXT.surpriseDurationMinutes;
  }
  return Math.max(1, Math.min(24 * 60, Math.floor(minutes)));
}

function getQuestTypesFromCounts(counts: QuestTypeCounts): QuestType[] {
  return QUEST_TYPES.filter((type) => counts[type] > 0);
}

function normalizeQuestTypeCounts(value: unknown): QuestTypeCounts {
  const source = isRecord(value) ? value : {};
  return {
    daily: Number.isFinite(Number(source.daily))
      ? Math.max(0, Math.floor(Number(source.daily)))
      : 0,
    weekly: Number.isFinite(Number(source.weekly))
      ? Math.max(0, Math.floor(Number(source.weekly)))
      : 0,
    surprise: Number.isFinite(Number(source.surprise))
      ? Math.max(0, Math.floor(Number(source.surprise)))
      : 0,
  };
}

function questTypeCountsFromTypes(types: QuestType[]): QuestTypeCounts {
  return {
    daily: types.includes("daily") ? 1 : 0,
    weekly: types.includes("weekly") ? 1 : 0,
    surprise: types.includes("surprise") ? 1 : 0,
  };
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

function recordToLines(value: unknown, aliasKind?: QuestInputAliasKind): string {
  if (!isRecord(value)) {
    return "";
  }
  return Object.entries(value)
    .filter(([, quantity]) => Number.isFinite(Number(quantity)))
    .map(([id, quantity]) => `${aliasKind ? displayQuestInputAlias(aliasKind, id) : id}=${Math.floor(Number(quantity))}`)
    .join("\n");
}

function arrayToLines(value: unknown, aliasKind?: QuestInputAliasKind): string {
  if (!Array.isArray(value)) {
    return "";
  }
  return value
    .filter((item): item is string => typeof item === "string" && item.trim().length > 0)
    .map((item) => item.trim())
    .map((item) => (aliasKind ? displayQuestInputAlias(aliasKind, item) : item))
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
      return `${displayQuestInputAlias("resource", objective.target_item_id)}=${Math.floor(required)}/${Math.floor(normalizedCurrent)}`;
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
      return `${target.id}|${target.label}|${target.target_kind}|${relatedResourceId ? displayQuestInputAlias("resource", relatedResourceId) : ""}`;
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
    inventoryText: recordToLines(gameState.inventory, "resource"),
    unlockedEquipmentText: arrayToLines(gameState.unlocked_equipment, "equipment"),
    unlockedRecipesText: arrayToLines(gameState.unlocked_recipes, "recipe"),
    recentEventsText: arrayToLines(payload.recent_events),
    surpriseDurationMinutes: normalizeSurpriseDurationMinutes(
      options.surprise_duration_minutes,
    ),
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
    questTypes: getQuestTypesFromCounts(
      isRecord(options.quest_type_counts)
        ? normalizeQuestTypeCounts(options.quest_type_counts)
        : questTypeCountsFromTypes(normalizeQuestTypes(options.quest_types)),
    ),
    questTypeCounts: isRecord(options.quest_type_counts)
      ? normalizeQuestTypeCounts(options.quest_type_counts)
      : questTypeCountsFromTypes(normalizeQuestTypes(options.quest_types)),
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
  const generatedAt = new Date();
  const expiresAt = new Date(generatedAt.getTime() + 2 * 60 * 60 * 1000);
  return {
    id: 901,
    type: "surprise",
    domain: "exploration",
    title: "동쪽 능선 신호 확인",
    description: "장거리 통신을 복구하기 전에 반복 감지되는 신호를 확인한다.",
    generated_at: generatedAt.toISOString(),
    expires_at: expiresAt.toISOString(),
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
