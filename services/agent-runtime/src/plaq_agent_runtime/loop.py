"""Agent Execution Loop implementing the 7-stage deterministic flow."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from typing import Any, Callable, Dict, List, Optional

from plaq_agent_runtime.approvals import ApprovalManager
from plaq_agent_runtime.registry import ToolContext, ToolRegistry, create_default_tool_registry
from plaq_contracts.approval import ApprovalStatus
from plaq_contracts.common import utc_now_iso
from plaq_contracts.event import EventType, PlatformEvent
from plaq_contracts.step import PlanDefinition, PlanStep, StepStatus
from plaq_contracts.task import Task, TaskStatus
from plaq_contracts.tool import ToolRequest, ToolResult
from plaq_control_plane.recovery import CheckpointRecoveryManager
from plaq_control_plane.repository import ControlPlaneRepository
from plaq_control_plane.state_machine import TaskStateMachine
from plaq_model_gateway.gateway import ModelGateway


@dataclass
class TaskResult:
    """Outcome of task execution returned by AgentRuntime."""
    task_id: str
    status: str
    steps: List[Dict[str, Any]] = field(default_factory=list)
    artifacts: List[str] = field(default_factory=list)
    modified_files: List[str] = field(default_factory=list)
    error: Optional[str] = None
    summary: Optional[str] = None
    duration_ms: float = 0.0


class AgentRuntime:
    """Orchestrates the 7-stage deterministic agent loop, tool dispatch, and event telemetry."""

    def __init__(
        self,
        repository: ControlPlaneRepository,
        model_gateway: Optional[ModelGateway] = None,
        tool_registry: Optional[ToolRegistry] = None,
        approval_manager: Optional[ApprovalManager] = None,
        event_broadcaster: Optional[Callable[[PlatformEvent], None]] = None,
        sandbox_manager: Optional[Any] = None,
        artifact_service: Optional[Any] = None,
    ):
        self.repo = repository
        self.model_gateway = model_gateway or ModelGateway()
        self.tool_registry = tool_registry or create_default_tool_registry()
        self._on_event = event_broadcaster
        self.approval_manager = approval_manager or ApprovalManager(
            repository=self.repo,
            on_event=self._on_event,
        )
        self.sandbox_manager = sandbox_manager
        self.artifact_service = artifact_service
        self.recovery_manager = CheckpointRecoveryManager(self.repo)
        self._cancelled_tasks: set[str] = set()

    def emit_event(
        self,
        event_type: EventType,
        task_id: Optional[str],
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Publish a platform telemetry event."""
        if self._on_event:
            try:
                ev = PlatformEvent(
                    event_type=event_type,
                    task_id=task_id,
                    payload=payload or {},
                )
                self._on_event(ev)
            except Exception:
                pass

    def cancel_task(self, task_id: str) -> bool:
        """Cancel an in-flight or queued task."""
        task = self.repo.get_task(task_id)
        if not task:
            raise KeyError(f"Task '{task_id}' not found.")

        current_status = task["status"]
        if TaskStateMachine.is_terminal(current_status):
            return False

        self._cancelled_tasks.add(task_id)
        self.repo.transition_task(task_id, "cancelled")
        self.emit_event(
            EventType.TASK_CANCELLED,
            task_id=task_id,
            payload={"previous_status": current_status},
        )
        return True

    def execute_task(
        self,
        task_id: str,
        on_event: Optional[Callable[[PlatformEvent], None]] = None,
    ) -> TaskResult:
        """Run the 7-stage deterministic agent execution loop for a task."""
        start_time = time.time()
        if on_event:
            self._on_event = on_event
            self.approval_manager._on_event = on_event

        task = self.repo.get_task(task_id)
        if not task:
            raise KeyError(f"Task '{task_id}' not found.")

        # Stage 1: Receive Task (queued)
        if task["status"] != "queued":
            return self.resume_task(task_id, on_event=on_event)

        self.emit_event(
            EventType.TASK_CREATED,
            task_id=task_id,
            payload={"goal": task["goal"], "status": "queued"},
        )

        # Stage 2: Inspect Context (workspace inspection -> planning)
        self.repo.transition_task(task_id, "planning")
        self.emit_event(
            EventType.TASK_TRANSITIONED,
            task_id=task_id,
            payload={"status": "planning"},
        )

        workspace_path = task.get("workspace_path", "")
        ws_files: List[str] = []
        if workspace_path and Path(workspace_path).exists():
            try:
                ws_files = [f.name for f in Path(workspace_path).iterdir()]
            except Exception:
                pass

        task_params = task.get("parameters") or {}
        if isinstance(task_params, str):
            try:
                task_params = json.loads(task_params)
            except Exception:
                task_params = {}

        context = {
            "task_id": task_id,
            "workspace_path": workspace_path,
            "files": ws_files,
            "parameters": task_params,
        }

        # Stage 3: Plan & Define Criteria
        plan = self.model_gateway.generate_plan(
            goal=task["goal"],
            context=context,
            task_id=task_id,
        )

        db_steps = []
        for step in plan.steps:
            db_step = self.repo.record_step(
                task_id=task_id,
                step_number=step.step_number,
                step_name=step.step_name,
                criteria=step.criteria,
            )
            # Annotate with planned tool metadata
            db_step["tool_name"] = step.tool_name
            db_step["tool_parameters"] = step.tool_parameters
            db_steps.append(db_step)

        # Execute planned steps sequentially
        return self._run_step_pipeline(task_id, db_steps, context, start_time)

    def _run_step_pipeline(
        self,
        task_id: str,
        steps: List[Dict[str, Any]],
        context: Dict[str, Any],
        start_time: float,
    ) -> TaskResult:
        """Execute Steps sequentially through Stages 4, 5, 6, and 7."""
        tool_results: List[ToolResult] = []
        modified_files_accum: List[str] = []

        for step in steps:
            if task_id in self._cancelled_tasks:
                return TaskResult(
                    task_id=task_id,
                    status="cancelled",
                    steps=self.repo.list_steps(task_id),
                    duration_ms=(time.time() - start_time) * 1000,
                )

            # Skip steps already completed
            if step.get("status") == "completed":
                continue

            step_id = step["id"]
            tool_name = step.get("tool_name")
            tool_params = step.get("tool_parameters") or {}
            if isinstance(tool_params, str):
                try:
                    tool_params = json.loads(tool_params)
                except Exception:
                    tool_params = {}

            # Stage 4: Execute Tool (running)
            current_task = self.repo.get_task(task_id)
            if current_task["status"] != "running":
                self.repo.transition_task(task_id, "running")
                self.emit_event(
                    EventType.TASK_TRANSITIONED,
                    task_id=task_id,
                    payload={"status": "running"},
                )

            self.repo.update_step(step_id, status="running")
            self.emit_event(
                EventType.STEP_STARTED,
                task_id=task_id,
                payload={"step_id": step_id, "step_number": step["step_number"], "step_name": step["step_name"]},
            )

            # Human Approval Gate Check
            if tool_name:
                req_approval, reason = self.approval_manager.is_approval_required(tool_name, tool_params)
                if req_approval:
                    existing_apps = self.repo.list_approvals(task_id)
                    already_approved = any(
                        a.get("tool_name") == tool_name and a.get("status") == "approved"
                        for a in existing_apps
                    )
                    if not already_approved:
                        self.approval_manager.request_approval(
                            task_id=task_id,
                            tool_name=tool_name,
                            parameters=tool_params,
                            reason=reason,
                            step_id=step_id,
                        )
                        # Task is now blocked. Suspend execution loop.
                        return TaskResult(
                            task_id=task_id,
                            status="blocked",
                            steps=self.repo.list_steps(task_id),
                            duration_ms=(time.time() - start_time) * 1000,
                        )

            # Tool Invocation
            t_start = time.perf_counter()
            self.emit_event(
                EventType.TOOL_INVOKED,
                task_id=task_id,
                payload={"tool_name": tool_name or "step", "parameters": tool_params, "step_id": step_id},
            )

            if self.tool_registry and tool_name:
                try:
                    tool_req = ToolRequest(
                        tool_name=tool_name,
                        parameters=tool_params,
                        task_id=task_id,
                        step_id=step_id,
                    )
                    t_ctx = ToolContext(
                        workspace_path=Path(context.get("workspace_path") or ".").resolve(),
                        task_id=task_id,
                        step_id=step_id,
                        control_plane=self.repo,
                        sandbox_manager=self.sandbox_manager,
                        artifact_service=self.artifact_service,
                    )
                    tool_res = self.tool_registry.execute(tool_req, t_ctx)
                except Exception as exc:
                    tool_res = ToolResult(
                        success=False,
                        output="",
                        error=str(exc),
                        duration_ms=(time.perf_counter() - t_start) * 1000,
                        exit_code=1,
                    )
            else:
                duration = 10.0
                tool_res = ToolResult(
                    success=True,
                    output=f"Executed {tool_name or 'generic_action'} cleanly",
                    exit_code=0,
                    duration_ms=duration,
                )
                self.repo.record_audit(
                    task_id=task_id,
                    tool_name=tool_name or "generic.step",
                    parameters=tool_params,
                    output=tool_res.output,
                    exit_code=0,
                    duration_ms=duration,
                )

            # Record tool call in database
            self.repo.record_tool_call(
                task_id=task_id,
                step_id=step_id,
                tool_name=tool_name or "unknown",
                parameters=tool_params,
                output=tool_res.output,
                exit_code=tool_res.exit_code or 0,
                duration_ms=tool_res.duration_ms,
            )

            tool_results.append(tool_res)
            if tool_res.modified_files:
                modified_files_accum.extend(tool_res.modified_files)

            # Stage 5: Collect Output
            self.emit_event(
                EventType.TOOL_COMPLETED,
                task_id=task_id,
                payload={
                    "tool_name": tool_name or "step",
                    "exit_code": tool_res.exit_code,
                    "duration_ms": tool_res.duration_ms,
                    "success": tool_res.success,
                    "output": tool_res.output[:200] if tool_res.output else "",
                },
            )

            # Stage 6: Verify
            self.repo.transition_task(task_id, "verifying")
            self.emit_event(
                EventType.TASK_TRANSITIONED,
                task_id=task_id,
                payload={"status": "verifying"},
            )

            verified, v_reason = self.model_gateway.verify_criteria(
                criteria=step.get("criteria", ""),
                tool_result=tool_res,
                context=context,
            )

            if verified:
                self.repo.update_step(step_id, status="completed")
                self.emit_event(
                    EventType.STEP_COMPLETED,
                    task_id=task_id,
                    payload={"step_id": step_id, "step_number": step["step_number"]},
                )
            else:
                fail_err = f"Step {step['step_number']} ('{step['step_name']}') verification failed: {v_reason}"
                self.repo.update_step(step_id, status="failed", error=fail_err)
                self.emit_event(
                    EventType.STEP_FAILED,
                    task_id=task_id,
                    payload={"step_id": step_id, "error": fail_err},
                )
                self.repo.transition_task(task_id, "failed", error=fail_err)
                self.emit_event(
                    EventType.TASK_FAILED,
                    task_id=task_id,
                    payload={"error": fail_err},
                )
                return TaskResult(
                    task_id=task_id,
                    status="failed",
                    steps=self.repo.list_steps(task_id),
                    error=fail_err,
                    duration_ms=(time.time() - start_time) * 1000,
                )

        # Stage 7: Review Diff & Deliver
        all_db_steps = self.repo.list_steps(task_id)
        plan_steps = [
            PlanStep(
                task_id=task_id,
                step_number=s["step_number"],
                step_name=s["step_name"],
                criteria=s.get("criteria", ""),
                status=StepStatus(s["status"]),
            )
            for s in all_db_steps
        ]

        summary = self.model_gateway.summarize_delivery(
            task_goal=self.repo.get_task(task_id)["goal"],
            steps=plan_steps,
            tool_results=tool_results,
            modified_files=list(set(modified_files_accum)),
        )

        self.repo.transition_task(task_id, "completed")
        self.emit_event(
            EventType.TASK_COMPLETED,
            task_id=task_id,
            payload={"status": "completed", "summary": summary},
        )

        return TaskResult(
            task_id=task_id,
            status="completed",
            steps=all_db_steps,
            artifacts=[],
            modified_files=list(set(modified_files_accum)),
            summary=summary,
            duration_ms=(time.time() - start_time) * 1000,
        )

    def resume_task(
        self,
        task_id: str,
        on_event: Optional[Callable[[PlatformEvent], None]] = None,
    ) -> TaskResult:
        """Resume an interrupted, crashed, or unblocked task."""
        start_time = time.time()
        if on_event:
            self._on_event = on_event
            self.approval_manager._on_event = on_event

        task = self.repo.get_task(task_id)
        if not task:
            raise KeyError(f"Task '{task_id}' not found.")

        status = task["status"]

        # If blocked, check if pending approval has been resolved
        if status == "blocked":
            pending = self.approval_manager.list_pending_approvals(task_id)
            if pending:
                return TaskResult(
                    task_id=task_id,
                    status="blocked",
                    steps=self.repo.list_steps(task_id),
                )
            apps = self.repo.list_approvals(task_id)
            if apps and apps[0]["status"] == "approved":
                self.repo.transition_task(task_id, "running")
                status = "running"
            elif apps and apps[0]["status"] == "rejected":
                return TaskResult(
                    task_id=task_id,
                    status="failed",
                    error=apps[0].get("decision_reason") or "Approval denied",
                    steps=self.repo.list_steps(task_id),
                )

        steps = self.repo.list_steps(task_id)
        workspace_path = task.get("workspace_path", "")
        task_params = task.get("parameters") or {}
        if isinstance(task_params, str):
            try:
                task_params = json.loads(task_params)
            except Exception:
                task_params = {}

        context = {
            "task_id": task_id,
            "workspace_path": workspace_path,
            "files": [],
            "parameters": task_params,
        }

        # If task was in queued, start execution
        if status == "queued":
            return self.execute_task(task_id, on_event=on_event)

        # If task was in planning with no recorded steps, generate plan
        if status == "planning" and not steps:
            plan = self.model_gateway.generate_plan(task["goal"], context, task_id=task_id)
            steps = []
            for s in plan.steps:
                db_s = self.repo.record_step(task_id, s.step_number, s.step_name, s.criteria)
                db_s["tool_name"] = s.tool_name
                db_s["tool_parameters"] = s.tool_parameters
                steps.append(db_s)

        # Align unfinished steps with plan metadata
        plan = self.model_gateway.generate_plan(task["goal"], context, task_id=task_id)
        plan_step_map = {s.step_number: s for s in plan.steps}
        for s in steps:
            num = s["step_number"]
            if num in plan_step_map:
                s.setdefault("tool_name", plan_step_map[num].tool_name)
                s.setdefault("tool_parameters", plan_step_map[num].tool_parameters)

        unfinished_steps = [s for s in steps if s.get("status") != "completed"]
        if not unfinished_steps and steps:
            if status != "completed":
                self.repo.transition_task(task_id, "completed")
            return TaskResult(task_id=task_id, status="completed", steps=steps)

        return self._run_step_pipeline(task_id, unfinished_steps, context, start_time)
