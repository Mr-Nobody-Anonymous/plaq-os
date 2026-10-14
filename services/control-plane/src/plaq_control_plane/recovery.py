"""Checkpoint Recovery Layer for crash recovery and state rehydration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from plaq_control_plane.repository import ControlPlaneRepository


@dataclass
class RehydratedTaskContext:
    """Complete in-memory snapshot of an in-flight task restored after system restart."""
    task: Dict[str, Any]
    status: str
    current_step: Optional[Dict[str, Any]] = None
    all_steps: List[Dict[str, Any]] = field(default_factory=list)
    pending_approval: Optional[Dict[str, Any]] = None
    last_audit_hash: str = "0" * 64
    last_sequence_number: int = 0
    recommended_action: str = "resume_execution"


class CheckpointRecoveryManager:
    """Coordinates crash recovery scanning, task rehydration, and execution resumption."""

    def __init__(self, repository: ControlPlaneRepository):
        self.repo = repository

    def scan_active_tasks(self) -> List[Dict[str, Any]]:
        """Scan SQLite database for non-terminal tasks."""
        return self.repo.recover_active_tasks()

    def rehydrate_task(self, task_id: str) -> RehydratedTaskContext:
        """Reconstruct full task context from persistent storage."""
        task = self.repo.get_task(task_id)
        if not task:
            raise KeyError(f"Task '{task_id}' not found for rehydration.")

        status = task["status"]
        steps = self.repo.list_steps(task_id)
        current_step_id = task.get("current_step_id")
        current_step = next((s for s in steps if s["id"] == current_step_id), None)
        if current_step is None and steps:
            # Fall back to latest step
            current_step = steps[-1]

        # Audit trail continuity
        audit_trail = self.repo.get_audit_trail(task_id)
        if audit_trail:
            last_record = audit_trail[-1]
            last_hash = last_record["current_hash"]
            last_seq = last_record["sequence_number"]
        else:
            last_hash = "0" * 64
            last_seq = 0

        # Pending approvals if blocked
        pending_approval = None
        if status == "blocked":
            with self.repo.db.connection() as conn:
                cursor = conn.execute(
                    "SELECT * FROM approvals WHERE task_id = ? AND status = 'pending' ORDER BY created_at DESC LIMIT 1",
                    (task_id,),
                )
                row = cursor.fetchone()
                if row:
                    pending_approval = dict(row)

        # Determine recommended recovery action
        if status == "queued":
            rec_action = "dispatch_to_planner"
        elif status == "planning":
            rec_action = "resume_planning"
        elif status == "blocked":
            rec_action = "await_human_approval"
        elif status == "verifying":
            rec_action = "rerun_verification"
        elif status == "running":
            rec_action = "resume_current_step"
        else:
            rec_action = "noop_terminal"

        return RehydratedTaskContext(
            task=task,
            status=status,
            current_step=current_step,
            all_steps=steps,
            pending_approval=pending_approval,
            last_audit_hash=last_hash,
            last_sequence_number=last_seq,
            recommended_action=rec_action,
        )

    def recover_all_tasks(self) -> List[RehydratedTaskContext]:
        """Scan and rehydrate all in-flight tasks upon system startup."""
        active = self.scan_active_tasks()
        return [self.rehydrate_task(t["id"]) for t in active]

    def resume_task(self, task_id: str) -> Dict[str, Any]:
        """Verify readiness of an in-flight task to resume processing."""
        ctx = self.rehydrate_task(task_id)
        return {
            "task_id": task_id,
            "status": ctx.status,
            "resumable": ctx.status in ("queued", "planning", "running", "verifying", "blocked"),
            "current_step": ctx.current_step,
            "recommended_action": ctx.recommended_action,
            "last_audit_hash": ctx.last_audit_hash,
        }


# Alias for backward compatibility
RecoveryManager = CheckpointRecoveryManager
