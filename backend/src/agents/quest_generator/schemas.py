"""퀘스트 응답 데이터가 올바른 모양인지 검사하는 Pydantic 모델들입니다.

에이전트가 만든 dict를 그대로 믿지 않고, 클라이언트에 보내기 전에 이 모델로
필수 필드와 값 범위를 확인합니다. 잘못된 데이터는 테스트 단계나 실행 중에
빠르게 드러나도록 하는 안전장치입니다.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class QuestObjective(BaseModel):
    """퀘스트 안에서 플레이어가 달성해야 하는 하나의 수량 목표입니다.

    예를 들어 `iron_ore`를 10개 모으라는 목표라면 `target_item_id`는
    `"iron_ore"`, `quantity`는 `10`이 됩니다.
    """

    target_item_id: str = Field(min_length=1)
    quantity: int = Field(gt=0)


class Quest(BaseModel):
    """클라이언트로 보낼 퀘스트 한 개의 전체 구조를 정의합니다.

    `Field` 조건은 빈 제목이나 0 이하 수량처럼 UI나 게임 로직에서 다루기
    어려운 값을 미리 막기 위한 검증 규칙입니다.
    """

    id: int = Field(gt=0)
    type: Literal["production", "tutorial", "exploration", "delivery"]
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    objectives: list[QuestObjective] = Field(min_length=1)


class QuestResponse(BaseModel):
    """클라이언트로 보낼 여러 개의 퀘스트 응답 묶음입니다.

    최종 WebSocket payload에서는 이 모델을 dict로 변환한 값이 들어갑니다.
    """

    quests: list[Quest] = Field(min_length=1)
