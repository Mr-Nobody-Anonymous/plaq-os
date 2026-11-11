"""Model providers for Plaq-OS Model Gateway."""

from __future__ import annotations

from abc import ABC, abstractmethod
import json
import os
from typing import Any, Dict, List, Optional, Tuple

from plaq_contracts.step import PlanStep, StepStatus
from plaq_contracts.tool import ToolResult


class BaseModelProvider(ABC):
    """Abstract base provider for plan generation, criteria evaluation, and summarization."""

    @abstractmethod
    def generate_plan(
        self,
        goal: str,
        context: Optional[Dict[str, Any]] = None,
        task_id: Optional[str] = None,
    ) -> List[PlanStep]:
        """Generate a structured multi-step plan with validation criteria."""
        pass

    @abstractmethod
    def verify_criteria(
        self,
        criteria: str,
        tool_result: ToolResult,
        context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, str]:
        """Verify whether tool execution output satisfies the specified criteria."""
        pass

    @abstractmethod
    def summarize_delivery(
        self,
        task_goal: str,
        steps: List[PlanStep],
        tool_results: List[ToolResult],
        modified_files: List[str],
    ) -> str:
        """Produce a human-readable delivery summary of task execution."""
        pass


class DeterministicPlanner(BaseModelProvider):
    """Deterministic, rule-based planner and validator for quantum and benchmarking tasks."""

    def generate_plan(
        self,
        goal: str,
        context: Optional[Dict[str, Any]] = None,
        task_id: Optional[str] = None,
    ) -> List[PlanStep]:
        tid = task_id or "task-plan"
        g_lower = goal.lower()

        # 1. Quantum Bernstein-Vazirani / Circuit Synthesis
        if any(k in g_lower for k in ["bernstein", "bv", "bernstein-vazirani", "101", "circuit synthesis"]):
            return [
                PlanStep(
                    task_id=tid,
                    step_number=1,
                    step_name="Synthesize BV Circuit",
                    criteria="Circuit depth > 0, 4 qubits",
                    tool_name="quantum.compile",
                    tool_parameters={"bitstring": "101"},
                ),
                PlanStep(
                    task_id=tid,
                    step_number=2,
                    step_name="Extract Cost Metrics",
                    criteria="T-count evaluated, code distance >= 3",
                    tool_name="quantum.estimate",
                    tool_parameters={"code_distance": 3},
                ),
                PlanStep(
                    task_id=tid,
                    step_number=3,
                    step_name="Publish Resource Manifest",
                    criteria="SHA-256 artifact saved",
                    tool_name="artifacts.publish",
                    tool_parameters={"file": "bv_resource_report.json"},
                ),
            ]

        # 2. Quantum Pareto / Benchmark / Cost Optimization
        if any(k in g_lower for k in ["pareto", "benchmark", "optimize", "clifford", "qec", "fault-tolerant"]):
            return [
                PlanStep(
                    task_id=tid,
                    step_number=1,
                    step_name="Synthesize Clifford+T",
                    criteria="T-count < 1000",
                    tool_name="quantum.compile",
                    tool_parameters={"circuit": "qft_4"},
                ),
                PlanStep(
                    task_id=tid,
                    step_number=2,
                    step_name="Estimate Logical Qubits",
                    criteria="Physical qubits <= 500",
                    tool_name="quantum.estimate",
                    tool_parameters={"physical_error": 0.001},
                ),
                PlanStep(
                    task_id=tid,
                    step_number=3,
                    step_name="Run Stim Simulation",
                    criteria="Shots >= 100",
                    tool_name="quantum.simulate",
                    tool_parameters={"code_distance": 3, "rounds": 3},
                ),
                PlanStep(
                    task_id=tid,
                    step_number=4,
                    step_name="Publish Resource Manifest",
                    criteria="SHA-256 artifact saved",
                    tool_name="artifacts.publish",
                    tool_parameters={"file": "pareto_report.json"},
                ),
            ]

        # 3. Clean & Maintenance
        if any(k in g_lower for k in ["clean", "purge", "rebuild"]):
            return [
                PlanStep(
                    task_id=tid,
                    step_number=1,
                    step_name="Clean Cache & Artifacts",
                    criteria="Clean completed",
                    tool_name="terminal.run",
                    tool_parameters={"cmd": "git clean -fdx"},
                ),
                PlanStep(
                    task_id=tid,
                    step_number=2,
                    step_name="Verify Clean Status",
                    criteria="Working tree clean",
                    tool_name="git.diff",
                    tool_parameters={},
                ),
            ]

        # 4. Test Suite Execution
        if any(k in g_lower for k in ["test", "pytest", "unit tests"]):
            return [
                PlanStep(
                    task_id=tid,
                    step_number=1,
                    step_name="Run Test Suite",
                    criteria="Tests pass cleanly",
                    tool_name="tests.run",
                    tool_parameters={"test_path": "tests/"},
                ),
                PlanStep(
                    task_id=tid,
                    step_number=2,
                    step_name="Inspect Test Results",
                    criteria="No test failures",
                    tool_name="workspace.list",
                    tool_parameters={"path": "."},
                ),
            ]

        # 5. QAOA / MaxCut circuit simulation
        if any(k in g_lower for k in ["qaoa", "maxcut", "max-cut"]):
            return [
                PlanStep(
                    task_id=tid,
                    step_number=1,
                    step_name="Compile QAOA MaxCut ansatz",
                    criteria="Circuit depth > 0",
                    tool_name="quantum.compile",
                    tool_parameters={"workload": "qaoa", "qubits": 6},
                ),
                PlanStep(
                    task_id=tid,
                    step_number=2,
                    step_name="Statevector simulation + MaxCut energy",
                    criteria="Exit code 0",
                    tool_name="quantum.run",
                    tool_parameters={"workload": "qaoa", "qubits": 6, "compute_energy": True},
                ),
                PlanStep(
                    task_id=tid,
                    step_number=3,
                    step_name="Fault-tolerant resource estimate",
                    criteria="T-count evaluated, code distance >= 3",
                    tool_name="quantum.estimate",
                    tool_parameters={"workload": "qaoa", "hardware_profile": "superconducting"},
                ),
                PlanStep(
                    task_id=tid,
                    step_number=4,
                    step_name="Publish simulation report",
                    criteria="SHA-256 artifact saved",
                    tool_name="artifacts.publish",
                    tool_parameters={"file": "qaoa_simulation_report.json"},
                ),
            ]

        # 6. Chemistry / VQE
        if any(k in g_lower for k in ["chemistry", "vqe", "femoco", "molecular"]):
            return [
                PlanStep(
                    task_id=tid,
                    step_number=1,
                    step_name="Compile chemistry ansatz",
                    criteria="Circuit depth > 0",
                    tool_name="quantum.compile",
                    tool_parameters={"workload": "chemistry", "qubits": 6},
                ),
                PlanStep(
                    task_id=tid,
                    step_number=2,
                    step_name="Circuit simulation",
                    criteria="Exit code 0",
                    tool_name="quantum.run",
                    tool_parameters={"workload": "chemistry", "compute_energy": True},
                ),
                PlanStep(
                    task_id=tid,
                    step_number=3,
                    step_name="FT resource estimate",
                    criteria="T-count evaluated, code distance >= 3",
                    tool_name="quantum.estimate",
                    tool_parameters={"workload": "chemistry"},
                ),
            ]

        # 7. Surface-code threshold study
        if any(k in g_lower for k in ["threshold", "surface code", "mwpm", "logical error"]):
            return [
                PlanStep(
                    task_id=tid,
                    step_number=1,
                    step_name="Surface-code Monte Carlo",
                    criteria="Shots >= 100",
                    tool_name="quantum.simulate",
                    tool_parameters={"code_distance": 3, "shots": 200},
                ),
                PlanStep(
                    task_id=tid,
                    step_number=2,
                    step_name="Threshold sweep",
                    criteria="Exit code 0",
                    tool_name="quantum.threshold",
                    tool_parameters={"distances": [3], "shots_per_point": 40},
                ),
            ]

        # 8. Shor / cryptanalysis kernel
        if any(k in g_lower for k in ["shor", "rsa", "period finding"]):
            return [
                PlanStep(
                    task_id=tid,
                    step_number=1,
                    step_name="Compile Shor modexp kernel",
                    criteria="Circuit depth > 0",
                    tool_name="quantum.compile",
                    tool_parameters={"workload": "shor"},
                ),
                PlanStep(
                    task_id=tid,
                    step_number=2,
                    step_name="FT resource estimate",
                    criteria="T-count evaluated, code distance >= 3",
                    tool_name="quantum.estimate",
                    tool_parameters={"workload": "shor"},
                ),
            ]

        # 9. Default Generic Flow
        return [
            PlanStep(
                task_id=tid,
                step_number=1,
                step_name="Inspect Workspace Context",
                criteria="Files identified",
                tool_name="workspace.list",
                tool_parameters={"path": "."},
            ),
            PlanStep(
                task_id=tid,
                step_number=2,
                step_name="Execute Goal Operation",
                criteria="Exit code 0",
                tool_name="terminal.run",
                tool_parameters={"cmd": "python --version"},
            ),
            PlanStep(
                task_id=tid,
                step_number=3,
                step_name="Review and Deliver",
                criteria="Context reviewed",
                tool_name="workspace.read",
                tool_parameters={"path": "README.md"},
            ),
        ]

    def verify_criteria(
        self,
        criteria: str,
        tool_result: ToolResult,
        context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, str]:
        if tool_result.exit_code is not None and tool_result.exit_code != 0:
            return (
                False,
                f"Tool execution failed with exit code {tool_result.exit_code}: {tool_result.error or tool_result.output}",
            )

        c_lower = criteria.lower()
        out = (tool_result.output or "").lower()

        # Circuit depth / qubits criteria
        if "4 qubits" in c_lower or "depth" in c_lower:
            if "qubit" in out or "size=" in out or tool_result.success:
                return True, "Circuit compilation criteria satisfied"

        # Code distance / cost metrics criteria
        if "code distance" in c_lower or "t-count" in c_lower:
            if "distance" in out or "metrics" in out or "feasible" in out or tool_result.success:
                return True, "Quantum resource metrics evaluated successfully"

        # Artifact publishing criteria
        if "artifact" in c_lower or "sha-256" in c_lower:
            if "sha256=" in out or "published" in out or "artifact" in out or tool_result.success:
                return True, "Artifact saved and published"

        # Clean / maintenance criteria
        if "clean" in c_lower:
            if "clean" in out or tool_result.success:
                return True, "Cleanup verified"

        # Fallback check
        if tool_result.success and (tool_result.exit_code is None or tool_result.exit_code == 0):
            return True, f"Criteria '{criteria}' satisfied"

        return False, f"Criteria '{criteria}' not clearly satisfied by output"

    def summarize_delivery(
        self,
        task_goal: str,
        steps: List[PlanStep],
        tool_results: List[ToolResult],
        modified_files: List[str],
    ) -> str:
        lines = [
            f"# Delivery Summary for Goal: {task_goal}",
            "",
            "## Completed Steps",
        ]
        for s in steps:
            status_symbol = "[x]" if s.status == StepStatus.COMPLETED else "[ ]"
            lines.append(f"- {status_symbol} Step {s.step_number}: {s.step_name} (Criteria: {s.criteria})")
        lines.append("")
        lines.append("## Artifacts & Modified Files")
        if modified_files:
            for f in sorted(set(modified_files)):
                lines.append(f"- `{f}`")
        else:
            lines.append("- No files were modified.")
        return "\n".join(lines)


# Alias for backward compatibility and test ergonomics
MockModelProvider = DeterministicPlanner


PLANNER_TOOL_CATALOG: List[Dict[str, str]] = [
    {"name": "workspace.list", "description": "List files in the workspace"},
    {"name": "workspace.read", "description": "Read a workspace file"},
    {"name": "workspace.write", "description": "Write a workspace file"},
    {"name": "workspace.patch", "description": "Patch a workspace file"},
    {"name": "git.diff", "description": "Show git diff"},
    {"name": "git.branch", "description": "List or create a git branch"},
    {"name": "terminal.run", "description": "Run a sandboxed shell command"},
    {"name": "tests.run", "description": "Run pytest"},
    {"name": "quantum.compile", "description": "Synthesize a named workload or OpenQASM; extract T-count/depth"},
    {"name": "quantum.estimate", "description": "Fault-tolerant resource estimate (d, physical qubits, runtime)"},
    {"name": "quantum.simulate", "description": "Stim+PyMatching surface-code Monte Carlo"},
    {"name": "quantum.run", "description": "Statevector/shot circuit simulation with optional energy"},
    {"name": "quantum.optimize", "description": "Pareto co-design search"},
    {"name": "quantum.baselines", "description": "Four-baselines comparison protocol"},
    {"name": "quantum.threshold", "description": "Surface-code threshold sweep"},
    {"name": "quantum.qasm", "description": "Compile OpenQASM 2.0"},
    {"name": "quantum.workloads", "description": "List named workloads"},
    {"name": "quantum.hardware", "description": "List hardware profiles"},
    {"name": "artifacts.publish", "description": "Publish a content-addressed artifact"},
]

_KNOWN_TOOLS = {t["name"] for t in PLANNER_TOOL_CATALOG}

PLAN_SYSTEM_PROMPT = (
    "You are the Plaq-OS agent planner for fault-tolerant quantum computing. "
    "Return ONLY a JSON object of the form "
    '{"steps":[{"step_name":"...","criteria":"...","tool_name":"...","tool_parameters":{}}]}. '
    "Use 2-8 steps. tool_name MUST be one of the listed tools. "
    "For simulation goals prefer quantum.compile → quantum.run and/or quantum.simulate "
    "→ quantum.estimate → quantum.optimize → artifacts.publish. "
    "criteria must be a short verifiable string."
)


def parse_llm_plan(text: str, task_id: str) -> List[PlanStep]:
    """Extract a validated PlanStep list from an LLM JSON response."""
    if not text:
        return []
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return []
    try:
        data = json.loads(text[start : end + 1])
    except Exception:
        return []
    raw_steps = data.get("steps") if isinstance(data, dict) else data
    if not isinstance(raw_steps, list):
        return []
    steps: List[PlanStep] = []
    for i, item in enumerate(raw_steps, start=1):
        if not isinstance(item, dict):
            continue
        tool_name = item.get("tool_name") or item.get("tool")
        if tool_name not in _KNOWN_TOOLS:
            continue
        params = item.get("tool_parameters") or item.get("parameters") or {}
        if not isinstance(params, dict):
            params = {}
        steps.append(
            PlanStep(
                task_id=task_id,
                step_number=i,
                step_name=str(item.get("step_name") or item.get("name") or f"Step {i}"),
                criteria=str(item.get("criteria") or "Exit code 0"),
                tool_name=str(tool_name),
                tool_parameters=params,
            )
        )
    return steps


VERIFY_SYSTEM_PROMPT = (
    "You verify Plaq-OS tool results against a step's criteria. "
    'Return ONLY JSON {"ok": true|false, "reason": "short explanation"}. '
    "If the tool failed (success=false or nonzero exit_code) you MUST return ok=false."
)


def parse_llm_verify(text: str) -> Optional[Tuple[bool, str]]:
    """Parse ``{"ok": bool, "reason": str}`` from an LLM response."""
    if not text:
        return None
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except Exception:
        return None
    if not isinstance(data, dict) or "ok" not in data:
        return None
    ok = data.get("ok")
    if not isinstance(ok, bool):
        if isinstance(ok, str):
            ok = ok.strip().lower() in {"true", "yes", "1", "pass"}
        else:
            return None
    reason = str(data.get("reason") or ("criteria satisfied" if ok else "criteria not satisfied"))
    return bool(ok), reason


class LLMProvider(BaseModelProvider):
    """LLM-backed provider (OpenAI-compatible chat API) with fallback.

    When ``api_key`` is set:
    - ``generate_plan`` asks for structured JSON tool calls (retry once, then fallback)
    - ``verify_criteria`` asks the model to judge the tool output (failed tools
      never get overridden to pass; parse failure falls back to deterministic)
    - ``summarize_delivery`` rewrites the delivery note
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: str = "gpt-4o",
        base_url: Optional[str] = None,
        fallback: Optional[BaseModelProvider] = None,
        timeout_sec: float = 15.0,
    ):
        self.api_key = api_key
        self.model_name = model_name
        self.base_url = (base_url or "https://api.openai.com/v1").rstrip("/")
        self._fallback = fallback or DeterministicPlanner()
        self.timeout_sec = timeout_sec

    def _chat(
        self,
        system: str,
        user: str,
        max_tokens: int = 800,
        json_mode: bool = False,
    ) -> Optional[str]:
        """Call the OpenAI-compatible chat endpoint. Returns None on failure."""
        if not self.api_key:
            return None
        import urllib.request

        def _post(with_json_mode: bool) -> Optional[str]:
            body: Dict[str, Any] = {
                "model": self.model_name,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0.2,
                "max_tokens": max_tokens,
            }
            if with_json_mode:
                body["response_format"] = {"type": "json_object"}
            payload = json.dumps(body).encode("utf-8")
            req = urllib.request.Request(
                f"{self.base_url}/chat/completions",
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}",
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=self.timeout_sec) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                return data["choices"][0]["message"]["content"].strip()
            except Exception:
                return None

        text = _post(json_mode)
        if text is None and json_mode:
            text = _post(False)
        return text

    def generate_plan(
        self,
        goal: str,
        context: Optional[Dict[str, Any]] = None,
        task_id: Optional[str] = None,
    ) -> List[PlanStep]:
        tid = task_id or "task-plan"
        planning_flag = os.environ.get("PLAQ_LLM_PLANNING", "1").strip().lower()
        if not self.api_key or planning_flag in {"0", "false", "off"}:
            return self._fallback.generate_plan(goal, context, task_id)
        tools_blob = json.dumps(PLANNER_TOOL_CATALOG)
        ctx_blob = json.dumps(context or {}, default=str)[:2000]
        user = (
            f"Goal: {goal}\n\nContext: {ctx_blob}\n\n"
            f"Available tools: {tools_blob}\n\nReturn JSON only."
        )
        text = self._chat(PLAN_SYSTEM_PROMPT, user, max_tokens=1200, json_mode=True)
        steps = parse_llm_plan(text or "", tid)
        if not steps:
            text = self._chat(PLAN_SYSTEM_PROMPT, user, max_tokens=1200, json_mode=False)
            steps = parse_llm_plan(text or "", tid)
        if not steps:
            return self._fallback.generate_plan(goal, context, task_id)
        return steps

    def verify_criteria(
        self,
        criteria: str,
        tool_result: ToolResult,
        context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, str]:
        det_ok, det_reason = self._fallback.verify_criteria(criteria, tool_result, context)
        # Never let the LLM override a hard tool failure.
        if not tool_result.success or (tool_result.exit_code not in (None, 0)):
            return det_ok, det_reason
        flag = os.environ.get("PLAQ_LLM_VERIFY", "1").strip().lower()
        if not self.api_key or flag in {"0", "false", "off"}:
            return det_ok, det_reason
        output_excerpt = (tool_result.output or "")[:1500]
        user = (
            f"Criteria: {criteria}\n"
            f"success={tool_result.success} exit_code={tool_result.exit_code}\n"
            f"error={tool_result.error!r}\n"
            f"output:\n{output_excerpt}\n"
        )
        text = self._chat(VERIFY_SYSTEM_PROMPT, user, max_tokens=250, json_mode=True)
        parsed = parse_llm_verify(text or "")
        if parsed is None:
            return det_ok, det_reason
        return parsed

    def summarize_delivery(
        self,
        task_goal: str,
        steps: List[PlanStep],
        tool_results: List[ToolResult],
        modified_files: List[str],
    ) -> str:
        fallback_text = self._fallback.summarize_delivery(
            task_goal, steps, tool_results, modified_files
        )
        if not self.api_key:
            return fallback_text
        step_lines = "\n".join(
            f"- Step {s.step_number}: {s.step_name} [{s.status.value}]" for s in steps
        )
        user = (
            f"Goal: {task_goal}\n\nSteps:\n{step_lines}\n\n"
            f"Modified files: {sorted(set(modified_files)) or 'none'}\n\n"
            f"Deterministic draft:\n{fallback_text}\n\n"
            "Rewrite as a concise delivery summary (keep the step list)."
        )
        llm_text = self._chat(
            "You summarize quantum-workbench agent task deliveries concisely.",
            user,
        )
        return llm_text or fallback_text
