"""에이전트 id 문자열을 실제 Agent 객체로 연결하는 등록소입니다.

초보자 관점에서는 이 파일을 "전화번호부"처럼 보면 됩니다. 파이프라인은
`quest_generator.delivery_quest` 같은 문자열만 알고 있고, 이 라우터가
그 문자열에 맞는 Python 클래스 인스턴스를 찾아줍니다.
"""

from __future__ import annotations

from agents.base import Agent
from agents.quest_generator.agent import QuestGeneratorAgent
from agents.quest_generator.delivery_quest import DeliveryQuestAgent
from agents.quest_generator.exploration_quest import ExplorationQuestAgent
from agents.quest_generator.production_quest import ProductionQuestAgent


class UnknownAgentError(ValueError):
    """요청한 agent id가 라우터에 등록되어 있지 않을 때 발생하는 예외입니다."""


class AgentRouter:
    """agent id와 실제 구현 객체를 저장하고 찾아주는 간단한 라우터입니다.

    각 Agent 클래스는 `agent_id` 값을 가지고 있습니다. `register()`는 그 값을
    key로 저장하고, `get()`은 나중에 같은 id로 구현 객체를 꺼냅니다.
    """

    def __init__(self) -> None:
        self._agents: dict[str, Agent] = {}

    def register(self, agent: Agent) -> None:
        """Agent 구현체를 `agent.agent_id` 이름으로 등록합니다."""

        self._agents[agent.agent_id] = agent

    def get(self, agent_id: str) -> Agent:
        """등록된 agent id에 맞는 구현 객체를 반환합니다.

        없는 id를 요청하면 조용히 None을 돌려주지 않고 `UnknownAgentError`를
        발생시켜, 잘못된 라우팅이 빨리 드러나게 합니다.
        """

        try:
            return self._agents[agent_id]
        except KeyError as exc:
            raise UnknownAgentError(f"Unknown agent: {agent_id}") from exc

    def has(self, agent_id: str) -> bool:
        """특정 agent id가 현재 라우터에 등록되어 있는지 확인합니다."""

        return agent_id in self._agents

    def list_agent_ids(self) -> list[str]:
        """등록된 agent id 목록을 정렬해서 반환합니다."""

        return sorted(self._agents)


def create_default_agent_router() -> AgentRouter:
    """서버가 기본으로 사용할 모든 top-level/leaf agent를 등록합니다.

    새 leaf agent를 실제 파이프라인에서 사용하려면, 클래스 파일을 만드는 것에
    더해 이 함수의 등록 목록에도 넣어야 합니다.
    """

    router = AgentRouter()
    for agent in (
        QuestGeneratorAgent(),
        ProductionQuestAgent(),
        DeliveryQuestAgent(),
        ExplorationQuestAgent(),
    ):
        router.register(agent)
    return router
