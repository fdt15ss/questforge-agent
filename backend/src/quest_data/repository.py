"""퀘스트 생성 agent가 CSV 데이터를 조회하는 repository입니다."""

from __future__ import annotations

from pathlib import Path

from quest_data.csv_loader import load_csv_rows
from quest_data.schemas import (
    QuestRewardRuleRow,
    RecipeRow,
    ResourceRow,
    ScenarioContextRow,
)


class QuestDataRepository:
    """`data/game` CSV를 읽어 id 기반 조회 API를 제공합니다."""

    def __init__(self, game_data_dir: Path | None = None) -> None:
        repo_root = Path(__file__).resolve().parents[3]
        self._game_data_dir = game_data_dir or repo_root / "data" / "game"
        self._scenario_contexts: list[ScenarioContextRow] | None = None
        self._resources: dict[str, ResourceRow] | None = None
        self._recipes: dict[str, RecipeRow] | None = None
        self._reward_rules: dict[str, QuestRewardRuleRow] | None = None

    def list_scenario_contexts(self) -> list[ScenarioContextRow]:
        if self._scenario_contexts is None:
            rows = load_csv_rows(self._game_data_dir / "scenario_context.csv")
            self._scenario_contexts = [
                ScenarioContextRow.from_csv_row(row) for row in rows
            ]
        return list(self._scenario_contexts)

    def find_scenario_contexts(
        self,
        related_resource_ids: list[str] | None = None,
        related_recipe_ids: list[str] | None = None,
        quest_type: str | None = None,
    ) -> list[ScenarioContextRow]:
        resource_ids = set(related_resource_ids or [])
        recipe_ids = set(related_recipe_ids or [])
        matched_contexts: list[ScenarioContextRow] = []

        for context in self.list_scenario_contexts():
            if quest_type and quest_type not in context.related_quest_types:
                continue
            has_resource = bool(resource_ids.intersection(context.related_resources))
            has_recipe = bool(recipe_ids.intersection(context.related_recipes))
            if has_resource or has_recipe:
                matched_contexts.append(context)

        return matched_contexts

    def list_resources(self) -> list[ResourceRow]:
        return list(self._load_resources().values())

    def list_recipes(self) -> list[RecipeRow]:
        return list(self._load_recipes().values())

    def get_resource(self, resource_id: str) -> ResourceRow:
        resources = self._load_resources()
        try:
            return resources[resource_id]
        except KeyError as exc:
            raise KeyError(resource_id) from exc

    def get_recipe(self, recipe_id: str) -> RecipeRow:
        recipes = self._load_recipes()
        try:
            return recipes[recipe_id]
        except KeyError as exc:
            raise KeyError(recipe_id) from exc

    def list_reward_rules(self) -> list[QuestRewardRuleRow]:
        return list(self._load_reward_rules().values())

    def get_reward_rule(self, reward_rule_id: str) -> QuestRewardRuleRow:
        reward_rules = self._load_reward_rules()
        try:
            return reward_rules[reward_rule_id]
        except KeyError as exc:
            raise KeyError(reward_rule_id) from exc

    def find_reward_rule(
        self,
        *,
        quest_type: str,
        tier: str,
    ) -> QuestRewardRuleRow:
        reward_rule_id = f"reward_{quest_type.lower()}_{tier.lower()}"
        try:
            return self.get_reward_rule(reward_rule_id)
        except KeyError:
            return self.get_reward_rule("reward_daily_t1")

    def find_reward_resource_candidates(self, resource_group: str) -> list[ResourceRow]:
        resources = self.list_resources()
        if "원재료" in resource_group or "보급품" in resource_group:
            return [resource for resource in resources if resource.resource_type == "원재료"]
        if "기초 가공" in resource_group or "긴급 가공" in resource_group:
            return [resource for resource in resources if resource.resource_type == "가공 자원"]
        if "중급" in resource_group:
            return [resource for resource in resources if resource.resource_type == "중간 부품"]
        if "고급" in resource_group:
            return [resource for resource in resources if resource.resource_type == "핵심 모듈"]
        return []

    def _load_resources(self) -> dict[str, ResourceRow]:
        if self._resources is None:
            rows = load_csv_rows(self._game_data_dir / "resources.csv")
            resources = [ResourceRow.from_csv_row(row) for row in rows]
            self._resources = {
                resource.resource_id: resource for resource in resources
            }
        return self._resources

    def _load_recipes(self) -> dict[str, RecipeRow]:
        if self._recipes is None:
            rows = load_csv_rows(self._game_data_dir / "recipes.csv")
            recipes = [RecipeRow.from_csv_row(row) for row in rows]
            self._recipes = {recipe.recipe_id: recipe for recipe in recipes}
        return self._recipes

    def _load_reward_rules(self) -> dict[str, QuestRewardRuleRow]:
        if self._reward_rules is None:
            rows = load_csv_rows(self._game_data_dir / "quest_reward_rules.csv")
            reward_rules = [QuestRewardRuleRow.from_csv_row(row) for row in rows]
            self._reward_rules = {
                reward_rule.reward_rule_id: reward_rule
                for reward_rule in reward_rules
            }
        return self._reward_rules