import { useEffect, useMemo, useState } from "react";
import { QuestCard } from "./components/QuestCard";
import {
  DEFAULT_DOMAIN_COUNTS,
  DEFAULT_QUEST_CONTEXT,
  DEFAULT_QUEST_TYPE_COUNTS,
  QUEST_DOMAINS,
  QUEST_TYPES,
  buildAgentRequest,
  buildAgentRequestFromRawJson,
  appendQuestLabItems,
  buildAgentTraceSummary,
  createQuestLabItems,
  displayQuestInputAlias,
  getQuestExpirationTime,
  getQuestInputCatalogOptions,
  isQuestExpired,
  normalizeQuestContextDefaults,
  parseInventoryText,
  parseListText,
  payloadToQuestContext,
  sampleExplorationQuest,
} from "./lib/questLab";
import { sendAgentRequest } from "./lib/wsClient";
import type {
  AgentEnvelope,
  DomainCounts,
  QuestDomain,
  QuestLabItem,
  QuestType,
} from "./types/quest";
import type { AgentRequestPreview, AgentTraceSummary, QuestContextFormState, QuestInputAliasKind, QuestTypeCounts } from "./lib/questLab";

type DomainFilter = QuestDomain | "all";
type TypeFilter = QuestType | "all";
type CatalogPickerMode = "inventory" | "equipment" | "recipe";

type CatalogPickerConfig = {
  aliasKind: QuestInputAliasKind;
  title: string;
  searchPlaceholder: string;
};

const CATALOG_PICKER_CONFIG: Record<CatalogPickerMode, CatalogPickerConfig> = {
  inventory: {
    aliasKind: "resource",
    title: "\uC778\uBCA4\uD1A0\uB9AC \uC790\uC6D0 \uC120\uD0DD",
    searchPlaceholder: "\uC790\uC6D0\uBA85\uC774\uB098 ID\uB85C \uAC80\uC0C9",
  },
  equipment: {
    aliasKind: "equipment",
    title: "\uD574\uAE08 \uC7A5\uBE44 \uC120\uD0DD",
    searchPlaceholder: "\uC7A5\uBE44\uBA85\uC774\uB098 ID\uB85C \uAC80\uC0C9",
  },
  recipe: {
    aliasKind: "recipe",
    title: "\uD574\uAE08 \uB808\uC2DC\uD53C \uC120\uD0DD",
    searchPlaceholder: "\uB808\uC2DC\uD53C\uBA85\uC774\uB098 ID\uB85C \uAC80\uC0C9",
  },
};

const domainLabel = {
  production: "생산",
  delivery: "납품",
  exploration: "탐험",
};

const typeLabel = {
  daily: "일일",
  weekly: "주간",
  surprise: "돌발",
};

const EXPIRATION_ANIMATION_MS = 900;
const REMAINING_TIME_REFRESH_MS = 1_000;

function getRequestBody(preview: AgentRequestPreview): Record<string, unknown> {
  const { websocketUrl: _websocketUrl, ...request } = preview;
  return request;
}

function questItemKey(item: QuestLabItem): string {
  return `${item.receivedAt}:${item.quest.domain ?? "unknown"}:${item.quest.type}:${item.quest.id}`;
}

function App() {
  const [websocketUrl, setWebsocketUrl] = useState("ws://127.0.0.1:18000/ws/agent");
  const [domainCounts, setDomainCounts] = useState<DomainCounts>(
    DEFAULT_DOMAIN_COUNTS,
  );
  const [questTypeCounts, setQuestTypeCounts] = useState<QuestTypeCounts>(
    DEFAULT_QUEST_TYPE_COUNTS,
  );
  const [questContext, setQuestContext] = useState<QuestContextFormState>(() =>
    normalizeQuestContextDefaults(DEFAULT_QUEST_CONTEXT),
  );
  const [domainFilter, setDomainFilter] = useState<DomainFilter>("all");
  const [typeFilter, setTypeFilter] = useState<TypeFilter>("all");
  const [items, setItems] = useState<QuestLabItem[]>([]);
  const [expiringItemKeys, setExpiringItemKeys] = useState<Set<string>>(() => new Set());
  const [lastRequest, setLastRequest] = useState<Record<string, unknown> | null>(null);
  const [lastEnvelope, setLastEnvelope] = useState<AgentEnvelope | null>(null);
  const [lastTrace, setLastTrace] = useState<AgentTraceSummary | null>(null);
  const [isSending, setIsSending] = useState(false);
  const [isJsonModalOpen, setIsJsonModalOpen] = useState(false);
  const [jsonDraft, setJsonDraft] = useState("");
  const [jsonImportError, setJsonImportError] = useState("");
  const [copyStatus, setCopyStatus] = useState("");
  const [catalogPickerMode, setCatalogPickerMode] = useState<CatalogPickerMode | null>(null);
  const [catalogSearch, setCatalogSearch] = useState("");
  const [catalogSelectedIds, setCatalogSelectedIds] = useState<Set<string>>(() => new Set());
  const [catalogQuantities, setCatalogQuantities] = useState<Record<string, number>>({});
  const [nowMs, setNowMs] = useState(() => Date.now());

  useEffect(() => {
    setQuestContext((current) => normalizeQuestContextDefaults(current));
  }, []);

  useEffect(() => {
    const interval = window.setInterval(() => setNowMs(Date.now()), REMAINING_TIME_REFRESH_MS);
    return () => window.clearInterval(interval);
  }, []);

  useEffect(() => {
    if (items.length === 0) {
      return undefined;
    }

    const markExpiredItems = () => {
      const now = Date.now();
      const expiredKeys = items
        .filter((item) => isQuestExpired(item.quest, now))
        .map(questItemKey);
      if (expiredKeys.length === 0) {
        return;
      }
      setExpiringItemKeys((current) => {
        const next = new Set(current);
        for (const key of expiredKeys) {
          next.add(key);
        }
        return next;
      });
    };

    markExpiredItems();

    const now = Date.now();
    const nextDelay = items.reduce<number | null>((closest, item) => {
      const expiresAt = getQuestExpirationTime(item.quest);
      if (expiresAt === null || expiresAt <= now) {
        return closest;
      }
      const delay = expiresAt - now;
      return closest === null ? delay : Math.min(closest, delay);
    }, null);

    if (nextDelay === null) {
      return undefined;
    }

    const timeout = window.setTimeout(markExpiredItems, nextDelay + 10);
    return () => window.clearTimeout(timeout);
  }, [items]);

  useEffect(() => {
    if (expiringItemKeys.size === 0) {
      return undefined;
    }

    const timeout = window.setTimeout(() => {
      setItems((current) =>
        current.filter((item) => !expiringItemKeys.has(questItemKey(item))),
      );
      setExpiringItemKeys(new Set());
    }, EXPIRATION_ANIMATION_MS);

    return () => window.clearTimeout(timeout);
  }, [expiringItemKeys]);
  const questTypes = useMemo(
    () => QUEST_TYPES.filter((type) => questTypeCounts[type] > 0),
    [questTypeCounts],
  );

  const domainTotal = useMemo(
    () => Object.values(domainCounts).reduce((sum, count) => sum + count, 0),
    [domainCounts],
  );
  const questTypeTotal = useMemo(
    () => Object.values(questTypeCounts).reduce((sum, count) => sum + count, 0),
    [questTypeCounts],
  );
  const canGenerate = domainTotal === questTypeTotal && questTypeTotal > 0;
  const catalogPickerConfig = catalogPickerMode
    ? CATALOG_PICKER_CONFIG[catalogPickerMode]
    : null;
  const catalogPickerKind = catalogPickerConfig?.aliasKind ?? null;
  const catalogOptions = useMemo(() => {
    if (!catalogPickerKind) {
      return [];
    }
    const normalizedSearch = catalogSearch.trim().toLowerCase();
    return getQuestInputCatalogOptions(catalogPickerKind).filter((option) => {
      if (!normalizedSearch) {
        return true;
      }
      return (
        option.displayName.toLowerCase().includes(normalizedSearch) ||
        option.canonicalId.toLowerCase().includes(normalizedSearch)
      );
    });
  }, [catalogPickerKind, catalogSearch]);

  const requestPreview = useMemo(
    () =>
      buildAgentRequest({
        websocketUrl,
        domainCounts,
        questTypes,
        questTypeCounts,
        context: questContext,
      }),
    [websocketUrl, domainCounts, questTypes, questTypeCounts, questContext],
  );

  const currentRequestBody = useMemo(
    () => getRequestBody(requestPreview),
    [requestPreview],
  );

  const filteredItems = items.filter((item) => {
    const domainMatches =
      domainFilter === "all" || item.quest.domain === domainFilter;
    const typeMatches = typeFilter === "all" || item.quest.type === typeFilter;
    return domainMatches && typeMatches;
  });

  async function dispatchAgentRequest(preview: AgentRequestPreview) {
    const request = getRequestBody(preview);
    setIsSending(true);
    setLastRequest(request);
    setLastEnvelope(null);
    setLastTrace(null);
    const startedAt = performance.now();
    try {
      const envelope = await sendAgentRequest(preview.websocketUrl, request);
      setLastEnvelope(envelope);
      if (envelope.type === "agent.response") {
        setNowMs(Date.now());
        setLastTrace(buildAgentTraceSummary(envelope, Math.round(performance.now() - startedAt)));
        setItems((current) => appendQuestLabItems(current, envelope.payload.quests));
      }
    } catch (error) {
      setLastTrace(null);
      setLastEnvelope({
        type: "agent.error",
        request_id: String(request.request_id ?? ""),
        agent: "quest_generator",
        error: {
          code: "FRONTEND_WEBSOCKET_ERROR",
          message: error instanceof Error ? error.message : String(error),
        },
      });
    } finally {
      setIsSending(false);
    }
  }

  async function handleGenerate() {
    await dispatchAgentRequest(requestPreview);
  }

  function updateDomainCount(domain: QuestDomain, value: number) {
    setDomainCounts((current) => ({
      ...current,
      [domain]: Math.max(0, Math.min(10, value)),
    }));
  }

  function updateQuestTypeCount(type: QuestType, value: number) {
    setQuestTypeCounts((current) => ({
      ...current,
      [type]: Math.max(0, Math.min(10, Math.floor(value || 0))),
    }));
  }

  function updateContext(patch: Partial<QuestContextFormState>) {
    setQuestContext((current) => ({ ...current, ...patch }));
  }

  function updateMainQuest(
    patch: Partial<QuestContextFormState["mainQuest"]>,
  ) {
    setQuestContext((current) => ({
      ...current,
      mainQuest: {
        ...current.mainQuest,
        ...patch,
      },
    }));
  }

  function updateItem(updated: QuestLabItem) {
    setItems((current) =>
      current.map((item) =>
        questItemKey(item) === questItemKey(updated) ? updated : item,
      ),
    );
  }
  function clearQuestItems() {
    setItems([]);
    setExpiringItemKeys(new Set());
  }

  function openCatalogPicker(mode: CatalogPickerMode) {
    const aliasKind = CATALOG_PICKER_CONFIG[mode].aliasKind;
    const selectedIds = new Set<string>();
    const quantities: Record<string, number> = {};

    if (mode === "inventory") {
      const currentInventory = parseInventoryText(questContext.inventoryText);
      for (const [canonicalId, quantity] of Object.entries(currentInventory)) {
        selectedIds.add(canonicalId);
        quantities[canonicalId] = quantity;
      }
    } else {
      const currentItems = parseListText(
        mode === "equipment"
          ? questContext.unlockedEquipmentText
          : questContext.unlockedRecipesText,
        aliasKind,
      );
      for (const canonicalId of currentItems) {
        selectedIds.add(canonicalId);
      }
    }

    setCatalogPickerMode(mode);
    setCatalogSearch("");
    setCatalogSelectedIds(selectedIds);
    setCatalogQuantities(quantities);
  }

  function closeCatalogPicker() {
    setCatalogPickerMode(null);
    setCatalogSearch("");
    setCatalogSelectedIds(new Set());
    setCatalogQuantities({});
  }

  function toggleCatalogSelection(canonicalId: string, checked: boolean) {
    setCatalogSelectedIds((current) => {
      const next = new Set(current);
      if (checked) {
        next.add(canonicalId);
      } else {
        next.delete(canonicalId);
      }
      return next;
    });
    if (checked && catalogPickerMode === "inventory") {
      setCatalogQuantities((current) => ({
        ...current,
        [canonicalId]: current[canonicalId] ?? 1,
      }));
    }
  }

  function updateCatalogQuantity(canonicalId: string, quantity: number) {
    const normalizedQuantity = Math.max(1, Math.min(99999, Math.floor(quantity || 1)));
    setCatalogSelectedIds((current) => new Set(current).add(canonicalId));
    setCatalogQuantities((current) => ({
      ...current,
      [canonicalId]: normalizedQuantity,
    }));
  }

  function applyCatalogSelection() {
    if (!catalogPickerMode || !catalogPickerKind) {
      return;
    }

    const selectedOptions = getQuestInputCatalogOptions(catalogPickerKind).filter((option) =>
      catalogSelectedIds.has(option.canonicalId),
    );

    if (catalogPickerMode === "inventory") {
      updateContext({
        inventoryText: selectedOptions
          .map((option) => {
            const quantity = catalogQuantities[option.canonicalId] ?? 1;
            return `${displayQuestInputAlias("resource", option.canonicalId)}=${quantity}`;
          })
          .join("\n"),
      });
    } else if (catalogPickerMode === "equipment") {
      updateContext({
        unlockedEquipmentText: selectedOptions
          .map((option) => displayQuestInputAlias("equipment", option.canonicalId))
          .join("\n"),
      });
    } else {
      updateContext({
        unlockedRecipesText: selectedOptions
          .map((option) => displayQuestInputAlias("recipe", option.canonicalId))
          .join("\n"),
      });
    }

    closeCatalogPicker();
  }
  function openJsonModal() {
    setJsonDraft(JSON.stringify(lastRequest ?? currentRequestBody, null, 2));
    setJsonImportError("");
    setCopyStatus("");
    setIsJsonModalOpen(true);
  }

  function closeJsonModal() {
    setIsJsonModalOpen(false);
    setJsonImportError("");
  }

  function applyJsonToForm() {
    try {
      const preview = buildAgentRequestFromRawJson(jsonDraft, websocketUrl);
      const imported = payloadToQuestContext(preview.payload);
      setDomainCounts(imported.domainCounts);
      setQuestTypeCounts(imported.questTypeCounts ?? DEFAULT_QUEST_TYPE_COUNTS);
      setQuestContext(imported.context);
      setLastRequest(null);
      setJsonImportError("");
      setIsJsonModalOpen(false);
    } catch (error) {
      setJsonImportError(error instanceof Error ? error.message : String(error));
    }
  }

  async function sendRawJson() {
    try {
      const preview = buildAgentRequestFromRawJson(jsonDraft, websocketUrl);
      setJsonImportError("");
      setIsJsonModalOpen(false);
      await dispatchAgentRequest(preview);
    } catch (error) {
      setJsonImportError(error instanceof Error ? error.message : String(error));
    }
  }

  async function copyCurrentRequestJson() {
    const json = JSON.stringify(currentRequestBody, null, 2);
    try {
      await navigator.clipboard.writeText(json);
      setCopyStatus("복사됨");
    } catch {
      setJsonDraft(json);
      setCopyStatus("클립보드 복사가 제한되어 JSON 창에 내용을 열었습니다.");
      setIsJsonModalOpen(true);
    }
  }

  function injectExplorationSample() {
    const sample = sampleExplorationQuest();
    setNowMs(Date.now());
    setItems((current) => [
      ...createQuestLabItems([sample]),
      ...current.filter((item) => item.quest.id !== sample.id),
    ]);
    const sampleEnvelope: AgentEnvelope = {
      type: "agent.response",
      request_id: "frontend-sample",
      agent: "quest_generator",
      payload: {
        quests: [sample],
        metadata: {
          source: "frontend_sample",
          selectedAgent: "quest_generator",
          selectedLeafAgent: "quest_generator.exploration_quest",
          fallback: true,
          fallbackReason: "frontend_sample",
        },
      },
    };
    setLastEnvelope(sampleEnvelope);
    setLastTrace(buildAgentTraceSummary(sampleEnvelope, null));
  }

  return (
    <main className="app-shell">
      <section className="panel request-panel">
        <div className="panel-heading">
          <p>QuestForge</p>
          <h1>Quest Lab</h1>
        </div>

        <label className="field">
          <span>WebSocket URL</span>
          <input
            value={websocketUrl}
            onChange={(event) => setWebsocketUrl(event.target.value)}
          />
        </label>

        <div className="field-group">
          <span className="group-label">도메인별 생성 수</span>
          {QUEST_DOMAINS.map((domain) => (
            <label className="count-row" key={domain}>
              <span>{domainLabel[domain]}</span>
              <input
                min="0"
                max="10"
                type="number"
                value={domainCounts[domain]}
                onChange={(event) =>
                  updateDomainCount(domain, Number(event.target.value))
                }
              />
            </label>
          ))}
        </div>

        <div className="field-group">
          <span className="group-label">퀘스트 타입별 개수</span>
          {QUEST_TYPES.map((type) => (
            <label className="count-row" key={type}>
              <span>{typeLabel[type]}</span>
              <input
                min="0"
                max="10"
                type="number"
                value={questTypeCounts[type]}
                onChange={(event) =>
                  updateQuestTypeCount(type, Number(event.target.value))
                }
              />
            </label>
          ))}
          {!canGenerate ? (
            <p className="form-warning">
              도메인 총합 {domainTotal}개와 타입 총합 {questTypeTotal}개를 맞춰주세요.
            </p>
          ) : null}
        </div>

        <div className="field-group surprise-duration-panel">
          <span className="group-label">돌발 제한 시간</span>
          <label className="count-row">
            <span>분 단위</span>
            <input
              min="1"
              max="1440"
              type="number"
              value={questContext.surpriseDurationMinutes}
              onChange={(event) =>
                updateContext({
                  surpriseDurationMinutes: Math.max(
                    1,
                    Math.min(1440, Math.floor(Number(event.target.value) || 120)),
                  ),
                })
              }
            />
          </label>
          <div className="duration-preset-grid" aria-label="돌발 제한 시간 빠른 선택">
            {[30, 60, 120, 240].map((minutes) => (
              <button
                className={questContext.surpriseDurationMinutes === minutes ? "toggle active" : "toggle"}
                type="button"
                key={minutes}
                onClick={() => updateContext({ surpriseDurationMinutes: minutes })}
              >
                {minutes < 60 ? `${minutes}분` : `${minutes / 60}시간`}
              </button>
            ))}
          </div>
        </div>
        <section className="context-panel">
          <div className="context-header">
            <div>
              <p>요청 컨텍스트</p>
              <h2>퀘스트 컨텍스트</h2>
            </div>
            <button
              className="secondary-action compact"
              type="button"
              onClick={() => setQuestContext(DEFAULT_QUEST_CONTEXT)}
            >
              초기화
            </button>
          </div>

          <div className="context-grid two-columns">
            <label className="field compact-field">
              <span>진행 단계</span>
              <input
                value={questContext.progression.stage}
                onChange={(event) =>
                  updateContext({
                    progression: {
                      ...questContext.progression,
                      stage: event.target.value,
                    },
                  })
                }
              />
            </label>
            <label className="field compact-field">
              <span>플레이어 레벨</span>
              <input
                min="1"
                type="number"
                value={questContext.progression.playerLevel}
                onChange={(event) =>
                  updateContext({
                    progression: {
                      ...questContext.progression,
                      playerLevel: Number(event.target.value),
                    },
                  })
                }
              />
            </label>
          </div>

          <div className="field compact-field">
            <div className="field-label-row">
              <span>{"\uC778\uBCA4\uD1A0\uB9AC"}</span>
              <button
                className="secondary-action compact catalog-picker-trigger"
                data-picker-kind="inventory"
                type="button"
                onClick={() => openCatalogPicker("inventory")}
              >
                {"\uC120\uD0DD"}
              </button>
            </div>
            <textarea
              rows={3}
              value={questContext.inventoryText}
              onChange={(event) => updateContext({ inventoryText: event.target.value })}
            />
          </div>

          <div className="context-grid two-columns">
            <div className="field compact-field">
              <div className="field-label-row">
                <span>{"\uD574\uAE08 \uC7A5\uBE44"}</span>
                <button
                  className="secondary-action compact catalog-picker-trigger"
                  data-picker-kind="equipment"
                  type="button"
                  onClick={() => openCatalogPicker("equipment")}
                >
                  {"\uC120\uD0DD"}
                </button>
              </div>
              <textarea
                rows={3}
                value={questContext.unlockedEquipmentText}
                onChange={(event) =>
                  updateContext({ unlockedEquipmentText: event.target.value })
                }
              />
            </div>
            <div className="field compact-field">
              <div className="field-label-row">
                <span>{"\uD574\uAE08 \uB808\uC2DC\uD53C"}</span>
                <button
                  className="secondary-action compact catalog-picker-trigger"
                  data-picker-kind="recipe"
                  type="button"
                  onClick={() => openCatalogPicker("recipe")}
                >
                  {"\uC120\uD0DD"}
                </button>
              </div>
              <textarea
                rows={3}
                value={questContext.unlockedRecipesText}
                onChange={(event) =>
                  updateContext({ unlockedRecipesText: event.target.value })
                }
              />
            </div>
          </div>

          <label className="field compact-field">
            <span>최근 이벤트</span>
            <textarea
              rows={3}
              value={questContext.recentEventsText}
              onChange={(event) => updateContext({ recentEventsText: event.target.value })}
            />
          </label>

          <label className="check-row">
            <input
              checked={questContext.mainQuestEnabled}
              type="checkbox"
              onChange={(event) =>
                updateContext({ mainQuestEnabled: event.target.checked })
              }
            />
            <span>현행 메인 퀘스트 포함</span>
          </label>

          {questContext.mainQuestEnabled ? (
            <div className="nested-context">
              <div className="context-grid two-columns">
                <label className="field compact-field">
                  <span>메인 퀘스트 ID</span>
                  <input
                    value={questContext.mainQuest.id}
                    onChange={(event) => updateMainQuest({ id: event.target.value })}
                  />
                </label>
                <label className="field compact-field">
                  <span>메인 퀘스트 제목</span>
                  <input
                    value={questContext.mainQuest.title}
                    onChange={(event) =>
                      updateMainQuest({ title: event.target.value })
                    }
                  />
                </label>
              </div>
              <label className="field compact-field">
                <span>메인 퀘스트 설명</span>
                <textarea
                  rows={3}
                  value={questContext.mainQuest.description}
                  onChange={(event) =>
                    updateMainQuest({ description: event.target.value })
                  }
                />
              </label>
              <label className="field compact-field">
                <span>메인 퀘스트 목표</span>
                <textarea
                  rows={3}
                  value={questContext.mainQuest.objectivesText}
                  onChange={(event) =>
                    updateMainQuest({ objectivesText: event.target.value })
                  }
                />
              </label>
            </div>
          ) : null}

          <label className="check-row">
            <input
              checked={questContext.explorationTargetsEnabled}
              type="checkbox"
              onChange={(event) =>
                updateContext({ explorationTargetsEnabled: event.target.checked })
              }
            />
            <span>탐험 후보지 포함</span>
          </label>

          {questContext.explorationTargetsEnabled ? (
            <label className="field compact-field">
              <span>탐험 후보지</span>
              <textarea
                rows={4}
                value={questContext.explorationTargetsText}
                onChange={(event) =>
                  updateContext({ explorationTargetsText: event.target.value })
                }
              />
            </label>
          ) : null}
        </section>

        <div className="action-stack">
          <button
            className="primary-action"
            type="button"
            disabled={isSending || !canGenerate}
            onClick={handleGenerate}
          >
            {isSending ? "생성 중..." : "퀘스트 생성"}
          </button>
          <button className="secondary-action" type="button" onClick={injectExplorationSample}>
            탐험 샘플 불러오기
          </button>
        </div>
      </section>

      <section className="workspace">
        <div className="toolbar">
          <div>
            <p>결과</p>
            <h2>{items.filter((item) => !expiringItemKeys.has(questItemKey(item))).length}개 퀘스트</h2>
          </div>
          <div className="filter-row">
            <select
              value={domainFilter}
              onChange={(event) => setDomainFilter(event.target.value as DomainFilter)}
            >
              <option value="all">전체 도메인</option>
              {QUEST_DOMAINS.map((domain) => (
                <option value={domain} key={domain}>
                  {domainLabel[domain]}
                </option>
              ))}
            </select>
            <select
              value={typeFilter}
              onChange={(event) => setTypeFilter(event.target.value as TypeFilter)}
            >
              <option value="all">전체 타입</option>
              {QUEST_TYPES.map((type) => (
                <option value={type} key={type}>
                  {typeLabel[type]}
                </option>
              ))}
            </select>
            <button
              className="secondary-action clear-all-action"
              type="button"
              aria-label={"\uC804\uCCB4 \uBE44\uC6B0\uAE30"}
              disabled={items.length === 0}
              onClick={clearQuestItems}
            >
              <span className="clear-all-action-line">{"\uC804\uCCB4"}</span>
              <span className="clear-all-action-line">{"\uBE44\uC6B0\uAE30"}</span>
            </button>
          </div>
        </div>

        <div className="quest-grid">
          {filteredItems.length > 0 ? (
            filteredItems.map((item) => (
              <QuestCard
                item={item}
                isExpiring={expiringItemKeys.has(questItemKey(item))}
                nowMs={nowMs}
                key={questItemKey(item)}
                onChange={updateItem}
              />
            ))
          ) : (
            <div className="empty-state">
              <h2>불러온 퀘스트가 없습니다</h2>
              <p>
                백엔드에서 생성하거나 탐험 샘플을 불러와 Quest Lab 동작을 확인하세요.
              </p>
            </div>
          )}
        </div>

        <section className="debug-panel">
          <div className="agent-trace-panel">
            <h3>Agent Trace</h3>
            {lastTrace ? (
              <div className="trace-content">
                <dl className="trace-list">
                  <div>
                    <dt>Request</dt>
                    <dd>{lastTrace.requestId}</dd>
                  </div>
                  <div>
                    <dt>Agent</dt>
                    <dd>{lastTrace.selectedAgent}</dd>
                  </div>
                  <div>
                    <dt>Leaf</dt>
                    <dd>{lastTrace.selectedLeafAgent}</dd>
                  </div>
                  <div>
                    <dt>LLM</dt>
                    <dd>{lastTrace.llmStatus}</dd>
                  </div>
                  <div>
                    <dt>Provider</dt>
                    <dd>{lastTrace.llmProvider}</dd>
                  </div>
                  <div>
                    <dt>Model</dt>
                    <dd>{lastTrace.llmModel}</dd>
                  </div>
                  <div>
                    <dt>Fallback</dt>
                    <dd>{lastTrace.fallback ? "yes" : "no"}</dd>
                  </div>
                  <div>
                    <dt>Reason</dt>
                    <dd>{lastTrace.fallbackReason || "-"}</dd>
                  </div>
                  <div>
                    <dt>Latency</dt>
                    <dd>{lastTrace.latencyMs === null ? "-" : `${lastTrace.latencyMs} ms`}</dd>
                  </div>
                </dl>
                <pre className="trace-metadata">{lastTrace.rawMetadataJson}</pre>
              </div>
            ) : (
              <p className="trace-empty">아직 agent 응답 trace가 없습니다.</p>
            )}
          </div>
          <div>
            <div className="debug-heading">
              <h3>요청 JSON</h3>
              <div className="debug-actions">
                <button type="button" onClick={openJsonModal}>
                  JSON 가져오기
                </button>
                <button type="button" onClick={copyCurrentRequestJson}>
                  현재 JSON 복사
                </button>
                {copyStatus ? <span>{copyStatus}</span> : null}
              </div>
            </div>
            <pre>{JSON.stringify(lastRequest ?? currentRequestBody, null, 2)}</pre>
          </div>
          <div>
            <h3>응답 / 오류 JSON</h3>
            <pre>{JSON.stringify(lastEnvelope, null, 2)}</pre>
          </div>
        </section>
      </section>

      {catalogPickerMode && catalogPickerConfig && catalogPickerKind ? (
        <div className="modal-backdrop" role="presentation">
          <section className="catalog-modal" role="dialog" aria-modal="true" aria-labelledby="catalog-modal-title">
            <div className="json-modal-header">
              <div>
                <p>CSV Catalog</p>
                <h2 id="catalog-modal-title">{catalogPickerConfig.title}</h2>
              </div>
              <button className="icon-button" type="button" onClick={closeCatalogPicker}>
                {"\uB2EB\uAE30"}
              </button>
            </div>
            <input
              className="catalog-search"
              value={catalogSearch}
              onChange={(event) => setCatalogSearch(event.target.value)}
              placeholder={catalogPickerConfig.searchPlaceholder}
            />
            <div className="catalog-option-list">
              {catalogOptions.length > 0 ? (
                catalogOptions.map((option) => {
                  const selected = catalogSelectedIds.has(option.canonicalId);
                  return (
                    <div className={selected ? "catalog-option is-selected" : "catalog-option"} key={option.canonicalId}>
                      <input
                        checked={selected}
                        type="checkbox"
                        onChange={(event) => toggleCatalogSelection(option.canonicalId, event.target.checked)}
                      />
                      <span className="catalog-option-text">
                        <strong>{option.displayName}</strong>
                        <small>{option.canonicalId}</small>
                      </span>
                      {catalogPickerMode === "inventory" ? (
                        <input
                          className="catalog-quantity-input"
                          min="1"
                          type="number"
                          value={catalogQuantities[option.canonicalId] ?? 1}
                          onChange={(event) => updateCatalogQuantity(option.canonicalId, Number(event.target.value))}
                        />
                      ) : null}
                    </div>
                  );
                })
              ) : (
                <p className="catalog-empty">{"\uC120\uD0DD\uD560 \uC218 \uC788\uB294 \uD56D\uBAA9\uC774 \uC5C6\uC2B5\uB2C8\uB2E4."}</p>
              )}
            </div>
            <div className="modal-actions">
              <button className="primary-action" type="button" onClick={applyCatalogSelection}>
                {"\uC120\uD0DD \uC801\uC6A9"}
              </button>
              <button className="secondary-action" type="button" onClick={closeCatalogPicker}>
                {"\uCDE8\uC18C"}
              </button>
            </div>
          </section>
        </div>
      ) : null}
      {isJsonModalOpen ? (
        <div className="modal-backdrop" role="presentation">
          <section className="json-modal" role="dialog" aria-modal="true" aria-labelledby="json-modal-title">
            <div className="json-modal-header">
              <div>
                <p>Request Override</p>
                <h2 id="json-modal-title">JSON 가져오기</h2>
              </div>
              <button className="icon-button" type="button" onClick={closeJsonModal}>
                닫기
              </button>
            </div>
            <textarea
              value={jsonDraft}
              onChange={(event) => {
                setJsonDraft(event.target.value);
                setJsonImportError("");
              }}
              spellCheck={false}
            />
            {jsonImportError ? <p className="error-text">{jsonImportError}</p> : null}
            <div className="modal-actions">
              <button className="primary-action" type="button" onClick={applyJsonToForm}>
                폼에 반영
              </button>
              <button className="secondary-action" type="button" onClick={sendRawJson} disabled={isSending}>
                그대로 전송
              </button>
              <button className="secondary-action" type="button" onClick={closeJsonModal}>
                취소
              </button>
            </div>
          </section>
        </div>
      ) : null}
    </main>
  );
}

export default App;
