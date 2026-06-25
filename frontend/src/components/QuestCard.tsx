import {
  applyProgressDelta,
  completeManualQuest,
  formatObjectiveId,
  getObjectiveDisplay,
  isQuestCleared,
  resetQuestProgress,
} from "../lib/questLab";
import type { QuestLabItem } from "../types/quest";

type QuestCardProps = {
  item: QuestLabItem;
  onChange: (item: QuestLabItem) => void;
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

export function QuestCard({ item, onChange }: QuestCardProps) {
  const quest = item.quest;
  const condition = quest.clear_condition;
  const cleared = isQuestCleared(item);

  return (
    <article className={`quest-card ${cleared ? "is-cleared" : ""}`}>
      <header className="quest-card-header">
        <div>
          <div className="badge-row">
            <span className={`badge domain-${quest.domain ?? "unknown"}`}>
              {quest.domain ? domainLabel[quest.domain] : "알 수 없음"}
            </span>
            <span className={`badge type-${quest.type}`}>
              {typeLabel[quest.type]}
            </span>
            <span className={`badge status-${item.status}`}>
              {cleared ? "완료" : item.status === "testing" ? "테스트 중" : "생성됨"}
            </span>
          </div>
          <h2>{quest.title}</h2>
        </div>
        <button
          className="icon-button"
          type="button"
          title="진행도 초기화"
          onClick={() => onChange(resetQuestProgress(item))}
        >
          초기화
        </button>
      </header>

      <p className="quest-description">{quest.description}</p>

      {quest.main_quest_link ? (
        <section className="quest-link">
          <span>{quest.main_quest_link.main_quest_title}</span>
          <p>{quest.main_quest_link.reason}</p>
        </section>
      ) : null}

      <section className="quest-section">
        <h3>목표</h3>
        <div className="objective-list">
          {quest.objectives.map((objective) => {
            const display = getObjectiveDisplay(objective, quest.domain);
            const progress = item.progress[objective.target_item_id] ?? 0;
            return (
              <div className="objective" key={objective.target_item_id}>
                <div>
                  <span>{display.kind}</span>
                  <strong>{display.label}</strong>
                </div>
                <small>
                  {progress} / {objective.quantity}
                </small>
              </div>
            );
          })}
        </div>
      </section>

      <section className="quest-section">
        <h3>완료 조건</h3>
        {condition.mode === "manual" ? (
          <div className="control-row">
            <span>{condition.label ?? "수동 완료"}</span>
            <button type="button" onClick={() => onChange(completeManualQuest(item))}>
              완료 처리
            </button>
          </div>
        ) : (
          <div className="control-row">
            <span>
              {formatObjectiveId(condition.target_item_id)}{" "}
              {item.progress[condition.target_item_id] ?? 0} /{" "}
              {condition.required_quantity}
            </span>
            <button
              type="button"
              onClick={() =>
                onChange(applyProgressDelta(item, condition.target_item_id, 1))
              }
            >
              +1
            </button>
            <button
              type="button"
              onClick={() =>
                onChange(
                  applyProgressDelta(
                    item,
                    condition.target_item_id,
                    condition.required_quantity,
                  ),
                )
              }
            >
              채우기
            </button>
          </div>
        )}
      </section>

      <section className="quest-section">
        <h3>보상</h3>
        <div className="reward-list">
          {quest.rewards.map((reward, index) => (
            <span className="reward" key={`${reward.reward_type}-${index}`}>
              {reward.reward_type}
              <strong>{reward.amount}</strong>
              {reward.resource_name ? reward.resource_name : null}
            </span>
          ))}
        </div>
      </section>
    </article>
  );
}
