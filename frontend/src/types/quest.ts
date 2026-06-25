export type QuestType = "daily" | "weekly" | "surprise";

export type QuestDomain = "production" | "delivery" | "exploration";

export type QuestStatus = "generated" | "testing" | "cleared";

export type ClearCondition =
  | {
      mode: "objective_count";
      target_item_id: string;
      required_quantity: number;
      label?: string | null;
    }
  | {
      mode: "manual";
      target_item_id?: string | null;
      required_quantity?: number | null;
      label?: string | null;
    };

export type QuestObjective = {
  target_item_id: string;
  quantity: number;
};

export type QuestReward = {
  reward_type: "xp" | "credits" | "resource";
  amount: number;
  resource_id?: string | null;
  resource_name?: string | null;
  source_rule_id: string;
  description: string;
};

export type MainQuestLink = {
  main_quest_id: string;
  main_quest_title: string;
  relation_kind:
    | "required_material"
    | "progress_support"
    | "risk_buffer"
    | "delivery_support";
  reason: string;
};

export type QuestFromServer = {
  id: number;
  type: QuestType;
  domain?: QuestDomain | null;
  title: string;
  description: string;
  objectives: QuestObjective[];
  clear_condition: ClearCondition;
  rewards: QuestReward[];
  main_quest_link?: MainQuestLink | null;
  metadata?: Record<string, string> | null;
};

export type QuestResponsePayload = {
  quests: QuestFromServer[];
  metadata?: Record<string, string> | null;
};

export type AgentResponseEnvelope = {
  type: "agent.response";
  request_id: string;
  session_id?: string | null;
  client_id?: string | null;
  agent: string;
  payload: QuestResponsePayload;
  streams?: unknown[];
};

export type AgentErrorEnvelope = {
  type: "agent.error";
  request_id?: string | null;
  session_id?: string | null;
  client_id?: string | null;
  agent?: string | null;
  error: {
    code?: string;
    message?: string;
    details?: unknown;
  };
};

export type AgentEnvelope = AgentResponseEnvelope | AgentErrorEnvelope;

export type QuestLabItem = {
  quest: QuestFromServer;
  status: QuestStatus;
  progress: Record<string, number>;
  selected: boolean;
  receivedAt: string;
};

export type DomainCounts = Record<QuestDomain, number>;
