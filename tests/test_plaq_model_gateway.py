"""Unit tests for plaq_model_gateway package (ModelGateway, DeterministicPlanner, MockModelProvider)."""

from __future__ import annotations

import pytest

from plaq_contracts.step import PlanDefinition, PlanStep, StepStatus
from plaq_contracts.tool import ToolResult
from plaq_model_gateway import (
    BaseModelProvider,
    DeterministicPlanner,
    LLMProvider,
    MockModelProvider,
    ModelGateway,
)


class TestDeterministicPlanner:
    """Verifies DeterministicPlanner plan generation, criteria verification, and summarization."""

    def test_plan_generation_bernstein_vazirani(self):
        planner = DeterministicPlanner()
        steps = planner.generate_plan(goal="Synthesize Bernstein-Vazirani 101 circuit", task_id="task-bv-1")
        assert len(steps) == 3
        assert steps[0].tool_name == "quantum.compile"
        assert steps[0].tool_parameters["bitstring"] == "101"
        assert steps[1].tool_name == "quantum.estimate"
        assert steps[2].tool_name == "artifacts.publish"

    def test_plan_generation_pareto_benchmark(self):
        planner = DeterministicPlanner()
        steps = planner.generate_plan(goal="Run Pareto optimization benchmark on Clifford+T", task_id="task-pareto-1")
        assert len(steps) == 4
        assert steps[0].tool_name == "quantum.compile"
        assert steps[1].tool_name == "quantum.estimate"
        assert steps[2].tool_name == "quantum.simulate"
        assert steps[3].tool_name == "artifacts.publish"

    def test_plan_generation_clean_maintenance(self):
        planner = DeterministicPlanner()
        steps = planner.generate_plan(goal="Clean cache and workspace purge", task_id="task-clean-1")
        assert len(steps) == 2
        assert steps[0].tool_name == "terminal.run"
        assert "git clean" in steps[0].tool_parameters["cmd"]
        assert steps[1].tool_name == "git.diff"

    def test_plan_generation_test_suite(self):
        planner = DeterministicPlanner()
        steps = planner.generate_plan(goal="Run pytest unit tests", task_id="task-test-1")
        assert len(steps) == 2
        assert steps[0].tool_name == "tests.run"
        assert steps[1].tool_name == "workspace.list"

    def test_plan_generation_fallback(self):
        planner = DeterministicPlanner()
        steps = planner.generate_plan(goal="Analyze data and generate docs", task_id="task-gen-1")
        assert len(steps) == 3
        assert steps[0].tool_name == "workspace.list"
        assert steps[1].tool_name == "terminal.run"
        assert steps[2].tool_name == "workspace.read"

    def test_criteria_verification_success(self):
        planner = DeterministicPlanner()
        res = ToolResult(success=True, output="Circuit size=4, 4 qubits compiled", exit_code=0)
        ok, msg = planner.verify_criteria("Circuit depth > 0, 4 qubits", res)
        assert ok is True

        res_est = ToolResult(success=True, output="Metrics extracted: code_distance=3", exit_code=0)
        ok, msg = planner.verify_criteria("T-count evaluated, code distance >= 3", res_est)
        assert ok is True

        res_art = ToolResult(success=True, output="Artifact published: sha256=abc12345", exit_code=0)
        ok, msg = planner.verify_criteria("SHA-256 artifact saved", res_art)
        assert ok is True

    def test_criteria_verification_failure(self):
        planner = DeterministicPlanner()
        fail_res = ToolResult(success=False, output="", error="Syntax error in circuit", exit_code=2)
        ok, msg = planner.verify_criteria("Circuit depth > 0, 4 qubits", fail_res)
        assert ok is False
        assert "exit code 2" in msg

    def test_summarize_delivery(self):
        planner = DeterministicPlanner()
        steps = [
            PlanStep(task_id="t1", step_number=1, step_name="Compile", criteria="OK", status=StepStatus.COMPLETED),
            PlanStep(task_id="t1", step_number=2, step_name="Estimate", criteria="OK", status=StepStatus.COMPLETED),
        ]
        results = [
            ToolResult(success=True, output="OK", exit_code=0),
            ToolResult(success=True, output="OK", exit_code=0),
        ]
        summary = planner.summarize_delivery(
            task_goal="Quantum workflow",
            steps=steps,
            tool_results=results,
            modified_files=["report.json"],
        )
        assert "# Delivery Summary for Goal: Quantum workflow" in summary
        assert "[x] Step 1: Compile" in summary
        assert "`report.json`" in summary


class TestMockModelProviderAlias:
    """Verifies that MockModelProvider behaves identically to DeterministicPlanner."""

    def test_alias_equivalence(self):
        assert MockModelProvider is DeterministicPlanner
        mock = MockModelProvider()
        steps = mock.generate_plan("Synthesize BV circuit")
        assert len(steps) == 3


class TestLLMProviderFallback:
    """Verifies LLMProvider delegates cleanly to DeterministicPlanner fallback."""

    def test_fallback_without_key(self):
        llm = LLMProvider(api_key=None)
        steps = llm.generate_plan("Bernstein-Vazirani 101")
        assert len(steps) == 3
        res = ToolResult(success=True, output="4 qubits", exit_code=0)
        ok, _ = llm.verify_criteria("4 qubits", res)
        assert ok is True


class TestModelGateway:
    """Verifies ModelGateway routing, provider registration, and plan creation."""

    def test_gateway_default_provider(self):
        gw = ModelGateway()
        p = gw.get_provider()
        assert isinstance(p, DeterministicPlanner)

    def test_gateway_generate_plan(self):
        gw = ModelGateway()
        plan_def = gw.generate_plan(goal="Pareto benchmark", task_id="gw-task-1")
        assert isinstance(plan_def, PlanDefinition)
        assert plan_def.task_id == "gw-task-1"
        assert len(plan_def.steps) == 4

    def test_gateway_verify_criteria(self):
        gw = ModelGateway()
        res = ToolResult(success=True, output="Artifact published: sha256=abcdef", exit_code=0)
        ok, msg = gw.verify_criteria("SHA-256 artifact saved", res)
        assert ok is True

    def test_gateway_custom_provider_registration(self):
        gw = ModelGateway()
        custom = DeterministicPlanner()
        gw.register_provider("custom_rule_engine", custom)
        p = gw.get_provider("custom_rule_engine")
        assert p is custom
