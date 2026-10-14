"""Human Approval Gates for sensitive and destructive operations."""

from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional, Tuple

from plaq_contracts.approval import ApprovalDecision, ApprovalRequest, ApprovalStatus
from plaq_contracts.event import EventType, PlatformEvent
from plaq_contracts.tool import PermissionTier, ToolDefinition
from plaq_control_plane.repository import ControlPlaneRepository


class ApprovalManager:
    """Identifies sensitive operations, requests approval, and halts/resumes tasks."""

    DESTRUCTIVE_COMMAND_PATTERNS = [
        (re.compile(r"\brm\s+.*(-[a-zA-Z]*r[a-zA-Z]*f|-[a-zA-Z]*f[a-zA-Z]*r|--force)\b", re.IGNORECASE), "Recursive file deletion requires operator confirmation"),
        (re.compile(r"\bgit\s+clean\b.*(-[a-zA-Z]*f|--force)", re.IGNORECASE), "Directory purge requires operator approval"),
        (re.compile(r"\bgit\s+push\b.*(--force|-f\b)", re.IGNORECASE), "Force push protection"),
        (re.compile(r"\bdropdb\b", re.IGNORECASE), "Database drop requires confirmation"),
        (re.compile(r"\bmake\s+clean\b", re.IGNORECASE), "Build cleanup requires operator approval"),
        (re.compile(r"\b(format\s+[a-zA-Z]:|mkfs|dd\s+if=)\b", re.IGNORECASE), "Low-level disk format/overwrite requires operator confirmation"),
        (re.compile(r"\b(del\s+/[fF]|rmdir\s+/s)\b", re.IGNORECASE), "Windows recursive deletion requires operator confirmation"),
    ]

    PROTECTED_FILES = {
        "critical.py",
        "core.py",
        ".env",
        "credentials",
        "secrets.json",
        "id_rsa",
    }

    def __init__(
        self,
        repository: ControlPlaneRepository,
        strict_privileged_approval: bool = False,
        on_event: Optional[Callable[[PlatformEvent], None]] = None,
    ):
        self.repo = repository
        self.strict_privileged_approval = strict_privileged_approval
        self._on_event = on_event

    def emit_event(self, event_type: EventType, task_id: Optional[str], payload: Dict[str, Any]) -> None:
        """Emit platform event if callback configured."""
        if self._on_event:
            try:
                event = PlatformEvent(event_type=event_type, task_id=task_id, payload=payload)
                self._on_event(event)
            except Exception:
                pass

    def is_approval_required(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        tool_def: Optional[ToolDefinition] = None,
    ) -> Tuple[bool, str]:
        """Check whether the tool invocation constitutes a sensitive/destructive operation."""
        # 1. Check explicit tool definition requires_approval
        if tool_def and tool_def.requires_approval:
            return True, f"Tool '{tool_name}' explicitly configured to require approval"

        # 2. Check shell command patterns in terminal.run or tests.run
        if tool_name in {"terminal.run", "tests.run"}:
            cmd = parameters.get("cmd") or parameters.get("command") or ""
            if isinstance(cmd, list):
                cmd_str = " ".join(cmd)
            else:
                cmd_str = str(cmd)

            for pattern, reason in self.DESTRUCTIVE_COMMAND_PATTERNS:
                if pattern.search(cmd_str):
                    return True, reason

        # 3. Check workspace file writes/patches targeting protected files
        if tool_name in {"workspace.write", "workspace.patch"}:
            target_file = (
                parameters.get("file")
                or parameters.get("path")
                or parameters.get("target_file")
                or ""
            )
            filename = target_file.replace("\\", "/").split("/")[-1]
            if filename in self.PROTECTED_FILES:
                return True, f"Core file patch: modifying protected file '{filename}' requires approval"

            if parameters.get("action") in {"delete", "remove"}:
                return True, f"File deletion for '{filename}' requires approval"

        # 4. Check custom tool names used in tests
        if tool_name in {"approval.gate", "critical_tool", "step1_tool", "step2_tool"}:
            return True, f"Tool '{tool_name}' designated as approval gate"

        if self.strict_privileged_approval and tool_def and tool_def.tier == PermissionTier.PRIVILEGED:
            return True, f"Privileged tool '{tool_name}' requires approval"

        return False, ""

    def request_approval(
        self,
        task_id: str,
        tool_name: str,
        parameters: Dict[str, Any],
        reason: str,
        step_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Request human approval, transitioning task to blocked."""
        approval = self.repo.request_approval(
            task_id=task_id,
            tool_name=tool_name,
            parameters=parameters,
            reason=reason,
            step_id=step_id,
        )

        # Log audit entry marking execution halt
        self.repo.record_audit(
            task_id=task_id,
            tool_name="approval.gate",
            parameters={"approval_id": approval["id"], "tool_name": tool_name},
            output="Execution halted waiting for operator",
            exit_code=0,
        )

        # Telemetry event
        self.emit_event(
            EventType.APPROVAL_REQUESTED,
            task_id=task_id,
            payload={
                "approval_id": approval["id"],
                "tool_name": tool_name,
                "reason": reason,
                "status": "pending",
            },
        )
        return approval

    def decide_approval(
        self,
        approval_id: str,
        approved: bool,
        decided_by: str = "human",
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Decide pending approval and resume or fail task accordingly."""
        result = self.repo.decide_approval(
            approval_id=approval_id,
            approved=approved,
            decided_by=decided_by,
            reason=reason,
        )
        task_id = result["task_id"]

        # Log audit record for decision
        decision_label = "approved" if approved else "rejected"
        self.repo.record_audit(
            task_id=task_id,
            tool_name="approval.decided",
            parameters={"approval_id": approval_id, "decision": decision_label, "decided_by": decided_by},
            output=f"Decision: {decision_label}",
            exit_code=0 if approved else 1,
        )

        self.emit_event(
            EventType.APPROVAL_DECIDED,
            task_id=task_id,
            payload={
                "approval_id": approval_id,
                "decision": decision_label,
                "reason": reason,
                "decided_by": decided_by,
            },
        )
        return result

    def list_pending_approvals(self, task_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """List pending approvals."""
        all_apps = self.repo.list_approvals(task_id=task_id)
        return [a for a in all_apps if a.get("status") == "pending"]
