"""퀘스트 응답 데이터가 올바른 모양인지 검사하는 Pydantic 모델들입니다.

에이전트가 만든 dict를 그대로 믿지 않고, 클라이언트에 보내기 전에 이 모델로
필수 필드와 값 범위를 확인합니다. 잘못된 데이터는 테스트 단계나 실행 중에
빠르게 드러나도록 하는 안전장치입니다.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class QuestObjective(BaseModel):
    """퀘스트 안에서 플레이어가 달성해야 하는 하나의 수량 목표입니다.

    예를 들어 `iron_ore`를 10개 모으라는 목표라면 `target_item_id`는
    `"iron_ore"`, `quantity`는 `10`이 됩니다.
    """

    target_item_id: str = Field(min_length=1)
    quantity: int = Field(gt=0)


class QuestClearCondition(BaseModel):
    """퀘스트가 완료됐는지 판단하는 조건입니다.

    `objective_count`는 특정 아이템 수량이 목표치 이상이면 완료되는 방식입니다.
    `manual`은 깜짝 상황처럼 사용자가 버튼으로 완료 처리하는 단순 방식입니다.
    """

    mode: Literal["objective_count", "manual"]
    target_item_id: str | None = None
    required_quantity: int | None = Field(default=None, gt=0)
    label: str | None = None


class MainQuestLink(BaseModel):
    """생성된 퀘스트가 현재 메인 퀘스트와 어떻게 연결되는지 설명합니다."""

    main_quest_id: str = Field(min_length=1)
    main_quest_title: str = Field(min_length=1)
    relation_kind: Literal[
        "required_material",
        "progress_support",
        "risk_buffer",
        "delivery_support",
    ]
    reason: str = Field(min_length=1)


class QuestReward(BaseModel):
    """퀘스트 완료 시 지급할 보상 한 줄입니다."""

    reward_type: Literal["xp", "credits", "resource"]
    amount: int = Field(gt=0)
    resource_id: str | None = None
    resource_name: str | None = None
    source_rule_id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    @model_validator(mode="after")
    def resource_reward_must_include_resource_identity(self) -> QuestReward:
        if self.reward_type == "resource" and (
            not self.resource_id or not self.resource_name
        ):
            raise ValueError("resource reward must include resource_id and resource_name")
        return self

class Quest(BaseModel):
    """클라이언트로 보낼 퀘스트 한 개의 전체 구조를 정의합니다.

    `Field` 조건은 빈 제목이나 0 이하 수량처럼 UI나 게임 로직에서 다루기
    어려운 값을 미리 막기 위한 검증 규칙입니다.
    """

    id: int = Field(gt=0)
    type: Literal["daily", "weekly", "surprise"]
    domain: Literal["production", "delivery", "exploration"] | None = None
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    objectives: list[QuestObjective] = Field(min_length=1)
    clear_condition: QuestClearCondition
    rewards: list[QuestReward] = Field(min_length=1)
    main_quest_link: MainQuestLink | None = None
    metadata: dict[str, str] | None = None


class QuestResponse(BaseModel):
    """클라이언트로 보낼 여러 개의 퀘스트 응답 묶음입니다.

    최종 WebSocket payload에서는 이 모델을 dict로 변환한 값이 들어갑니다.
    """

    quests: list[Quest] = Field(min_length=1)
    metadata: dict[str, str] | None = None


class QuestPlanDomainMix(BaseModel):
    """LLM이 요청 상황에 맞는 도메인 비율을 설명하기 위한 계획 필드입니다."""

    production: int = Field(ge=0)
    delivery: int = Field(ge=0)
    exploration: int = Field(default=0, ge=0)


class QuestPlanIntent(BaseModel):
    """LLM이 draft quest 하나에 부여하는 기획 의도입니다."""

    id: int = Field(gt=0)
    domain: Literal["production", "delivery", "exploration"]
    target_item_id: str = Field(min_length=1)
    intent: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    title: str | None = Field(default=None, min_length=1)
    description: str | None = Field(default=None, min_length=1)
    main_quest_link_reason: str | None = Field(default=None, min_length=1)


class QuestPlan(BaseModel):
    """LLM이 서버 draft 위에 얹는 퀘스트 기획안입니다."""

    analysis: str = Field(min_length=1)
    domain_mix: QuestPlanDomainMix
    quest_intents: list[QuestPlanIntent] = Field(min_length=1)


class QuestPlanEnvelope(BaseModel):
    """LLM `quest_plan` 응답 envelope입니다."""

    quest_plan: QuestPlan
