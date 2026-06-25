import { useEffect, useMemo, useState } from "react";
import { QuestCard } from "./components/QuestCard";
import {
  DEFAULT_DOMAIN_COUNTS,
  DEFAULT_QUEST_CONTEXT,
  QUEST_DOMAINS,
  QUEST_TYPES,
  buildAgentRequest,
  buildAgentRequestFromRawJson,
  createQuestLabItems,
  normalizeQuestContextDefaults,
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
import type { AgentRequestPreview, QuestContextFormState } from "./lib/questLab";

type DomainFilter = QuestDomain | "all";
type TypeFilter = QuestType | "all";

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

function getRequestBody(preview: AgentRequestPreview): Record<string, unknown> {
  const { websocketUrl: _websocketUrl, ...request } = preview;
  return request;
}

function App() {
  const [websocketUrl, setWebsocketUrl] = useState("ws://127.0.0.1:18000/ws/agent");
  const [domainCounts, setDomainCounts] = useState<DomainCounts>(
    DEFAULT_DOMAIN_COUNTS,
  );
  const [questTypes, setQuestTypes] = useState<QuestType[]>([
    "daily",
    "weekly",
    "surprise",
  ]);
  const [questContext, setQuestContext] = useState<QuestContextFormState>(() =>
    normalizeQuestContextDefaults(DEFAULT_QUEST_CONTEXT),
  );
  const [domainFilter, setDomainFilter] = useState<DomainFilter>("all");
  const [typeFilter, setTypeFilter] = useState<TypeFilter>("all");
  const [items, setItems] = useState<QuestLabItem[]>([]);
  const [lastRequest, setLastRequest] = useState<Record<string, unknown> | null>(null);
  const [lastEnvelope, setLastEnvelope] = useState<AgentEnvelope | null>(null);
  const [isSending, setIsSending] = useState(false);
  const [isJsonModalOpen, setIsJsonModalOpen] = useState(false);
  const [jsonDraft, setJsonDraft] = useState("");
  const [jsonImportError, setJsonImportError] = useState("");
  const [copyStatus, setCopyStatus] = useState("");

  useEffect(() => {
    setQuestContext((current) => normalizeQuestContextDefaults(current));
  }, []);

  const requestPreview = useMemo(
    () =>
      buildAgentRequest({
        websocketUrl,
        domainCounts,
        questTypes,
        context: questContext,
      }),
    [websocketUrl, domainCounts, questTypes, questContext],
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
    try {
      const envelope = await sendAgentRequest(preview.websocketUrl, request);
      setLastEnvelope(envelope);
      if (envelope.type === "agent.response") {
        setItems(createQuestLabItems(envelope.payload.quests));
      }
    } catch (error) {
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

  function toggleQuestType(type: QuestType) {
    setQuestTypes((current) => {
      const next = current.includes(type)
        ? current.filter((item) => item !== type)
        : [...current, type];
      return next.length > 0 ? next : current;
    });
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
      current.map((item) => (item.quest.id === updated.quest.id ? updated : item)),
    );
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
      setQuestTypes(imported.questTypes);
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
    setItems((current) => [
      ...createQuestLabItems([sample]),
      ...current.filter((item) => item.quest.id !== sample.id),
    ]);
    setLastEnvelope({
      type: "agent.response",
      request_id: "frontend-sample",
      agent: "quest_generator",
      payload: {
        quests: [sample],
        metadata: {
          source: "frontend_sample",
        },
      },
    });
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
          <span className="group-label">퀘스트 타입</span>
          <div className="toggle-grid">
            {QUEST_TYPES.map((type) => (
              <button
                className={questTypes.includes(type) ? "toggle active" : "toggle"}
                type="button"
                key={type}
                onClick={() => toggleQuestType(type)}
              >
                {typeLabel[type]}
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

          <label className="field compact-field">
            <span>인벤토리</span>
            <textarea
              rows={3}
              value={questContext.inventoryText}
              onChange={(event) => updateContext({ inventoryText: event.target.value })}
            />
          </label>

          <div className="context-grid two-columns">
            <label className="field compact-field">
              <span>해금 장비</span>
              <textarea
                rows={3}
                value={questContext.unlockedEquipmentText}
                onChange={(event) =>
                  updateContext({ unlockedEquipmentText: event.target.value })
                }
              />
            </label>
            <label className="field compact-field">
              <span>해금 레시피</span>
              <textarea
                rows={3}
                value={questContext.unlockedRecipesText}
                onChange={(event) =>
                  updateContext({ unlockedRecipesText: event.target.value })
                }
              />
            </label>
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
            disabled={isSending}
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
            <h2>{items.length}개 퀘스트</h2>
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
          </div>
        </div>

        <div className="quest-grid">
          {filteredItems.length > 0 ? (
            filteredItems.map((item) => (
              <QuestCard item={item} key={item.quest.id} onChange={updateItem} />
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

