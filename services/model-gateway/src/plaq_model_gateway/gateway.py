"""Model Gateway implementation providing centralized provider management."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from plaq_contracts.step import PlanDefinition, PlanStep
from plaq_contracts.tool import ToolResult
from plaq_model_gateway.providers import BaseModelProvider, DeterministicPlanner


class ModelGateway:
    """Central gateway routing planning, criteria verification, and summarization requests."""

    def __init__(self, default_provider: Optional[BaseModelProvider] = None):
        self._providers: Dict[str, BaseModelProvider] = {}
        default = default_provider or DeterministicPlanner()
        self.register_provider("default", default)
        self.register_provider("deterministic", default)

    def register_provider(self, name: str, provider: BaseModelProvider) -> None:
        """Register a named model provider."""
        self._providers[name] = provider

    def get_provider(self, name: Optional[str] = None) -> BaseModelProvider:
        """Retrieve provider by name, defaulting to 'default'."""
        provider_name = name or "default"
        if provider_name not in self._providers:
            return self._providers["default"]
        return self._providers[provider_name]

    def generate_plan(
        self,
        goal: str,
        context: Optional[Dict[str, Any]] = None,
        task_id: Optional[str] = None,
        provider_name: Optional[str] = None,
    ) -> PlanDefinition:
        """Generate a structured multi-step plan for the given goal."""
        provider = self.get_provider(provider_name)
        tid = task_id or "task-plan"
        steps = provider.generate_plan(goal=goal, context=context, task_id=tid)
        return PlanDefinition(
            task_id=tid,
            goal=goal,
            steps=steps,
        )

    def verify_criteria(
        self,
        criteria: str,
        tool_result: ToolResult,
        context: Optional[Dict[str, Any]] = None,
        provider_name: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """Verify whether tool execution meets the step criteria."""
        provider = self.get_provider(provider_name)
        return provider.verify_criteria(criteria=criteria, tool_result=tool_result, context=context)

    def summarize_delivery(
        self,
        task_goal: str,
        steps: List[PlanStep],
        tool_results: List[ToolResult],
        modified_files: List[str],
        provider_name: Optional[str] = None,
    ) -> str:
        """Produce a formatted delivery summary of task execution."""
        provider = self.get_provider(provider_name)
        return provider.summarize_delivery(
            task_goal=task_goal,
            steps=steps,
            tool_results=tool_results,
            modified_files=modified_files,
        )
