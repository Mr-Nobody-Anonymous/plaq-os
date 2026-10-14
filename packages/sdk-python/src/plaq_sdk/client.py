"""Unified Plaq-OS Client providing direct local in-process access and remote HTTP/WebSocket access."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Union
import httpx

from plaq_contracts import (
    ApprovalDecision,
    ApprovalRequest,
    ApprovalStatus,
    ArtifactPublishRequest,
    ArtifactRecord,
    PlatformEvent,
    QuantumBenchmarkRequest,
    QuantumCompileRequest,
    QuantumEstimateRequest,
    QuantumResult,
    Task,
    TaskCreate,
    TaskStatus,
)


class PlaqClient:
    """Unified client providing both direct local in-process access and remote HTTP/WebSocket access."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        db_path: Optional[Union[str, Path]] = None,
        local: bool = False,
        api_key: Optional[str] = None,
        timeout: float = 30.0,
        http_client: Optional[httpx.Client] = None,
    ):
        self.local = local or (base_url is None)
        self.base_url = base_url.rstrip("/") if base_url else "http://127.0.0.1:8000"
        self.api_key = api_key
        self.timeout = timeout
        self.db_path = str(db_path) if db_path else None

        self._repo: Any = None
        self._quantum: Any = None
        self._client: Optional[httpx.Client] = None

        if self.local:
            if self.db_path:
                from plaq_control_plane.repository import ControlPlaneRepository
                self._repo = ControlPlaneRepository(self.db_path)
            try:
                import plaq_quantum as pq
                self._quantum = pq
            except ImportError:
                self._quantum = None
        else:
            headers = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            self._client = http_client or httpx.Client(
                base_url=self.base_url,
                headers=headers,
                timeout=self.timeout,
            )

    @classmethod
    def local_client(cls, db_path: Optional[Union[str, Path]] = None) -> PlaqClient:
        """Create a client operating directly against local in-process engines."""
        return cls(local=True, db_path=db_path)

    @classmethod
    def remote_client(
        cls,
        base_url: str = "http://127.0.0.1:8000",
        api_key: Optional[str] = None,
        timeout: float = 30.0,
    ) -> PlaqClient:
        """Create a client operating against a remote FastAPI backend."""
        return cls(base_url=base_url, api_key=api_key, timeout=timeout, local=False)

    def close(self) -> None:
        """Close underlying HTTP or SQLite connections."""
        if self._client:
            self._client.close()
        if self._repo and hasattr(self._repo, "close"):
            self._repo.close()

    def __enter__(self) -> PlaqClient:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    # --- Health ---

    def health(self) -> Dict[str, Any]:
        """Check system and component health."""
        if self.local:
            return {
                "status": "ok",
                "version": "0.1.0",
                "mode": "local",
                "components": {
                    "control_plane": "ok" if self._repo else "unconfigured",
                    "quantum_engine": "ok" if self._quantum else "unconfigured",
                },
            }
        assert self._client is not None
        resp = self._client.get("/api/v1/health")
        resp.raise_for_status()
        return resp.json()

    # --- Task Management ---

    def create_task(
        self,
        goal: str,
        workspace_path: str = "",
        parameters: Optional[Dict[str, Any]] = None,
    ) -> Task:
        """Create a new queued task."""
        if self.local:
            if not self._repo:
                from plaq_control_plane.repository import ControlPlaneRepository
                self._repo = ControlPlaneRepository(self.db_path or ":memory:")
            row = self._repo.create_task(goal=goal, workspace_path=workspace_path, parameters=parameters)
            return Task.model_validate(row)

        assert self._client is not None
        payload = {"goal": goal, "workspace_path": workspace_path, "parameters": parameters or {}}
        resp = self._client.post("/api/v1/tasks", json=payload)
        resp.raise_for_status()
        return Task.model_validate(resp.json())

    def get_task(self, task_id: str) -> Optional[Task]:
        """Retrieve task details by ID."""
        if self.local:
            if not self._repo:
                return None
            row = self._repo.get_task(task_id)
            return Task.model_validate(row) if row else None

        assert self._client is not None
        resp = self._client.get(f"/api/v1/tasks/{task_id}")
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return Task.model_validate(resp.json())

    def list_tasks(self, status: Optional[str] = None) -> List[Task]:
        """List tasks, optionally filtered by status."""
        if self.local:
            if not self._repo:
                return []
            rows = self._repo.list_tasks(status=status)
            return [Task.model_validate(r) for r in rows]

        assert self._client is not None
        params = {"status": status} if status else {}
        resp = self._client.get("/api/v1/tasks", params=params)
        resp.raise_for_status()
        return [Task.model_validate(item) for item in resp.json()]

    def transition_task(self, task_id: str, to_status: str, error: Optional[str] = None) -> Task:
        """Explicitly transition task state."""
        if self.local:
            if not self._repo:
                raise RuntimeError("Local client requires an initialized database.")
            row = self._repo.transition_task(task_id=task_id, to_status=to_status, error=error)
            return Task.model_validate(row)

        assert self._client is not None
        payload = {"status": to_status, "error": error}
        resp = self._client.post(f"/api/v1/tasks/{task_id}/transition", json=payload)
        resp.raise_for_status()
        return Task.model_validate(resp.json())

    def get_task_logs(self, task_id: str) -> List[Dict[str, Any]]:
        """Retrieve append-only audit trail logs for a task."""
        if self.local:
            if not self._repo:
                raise RuntimeError("Local client requires an initialized database.")
            return self._repo.get_audit_trail(task_id)

        assert self._client is not None
        resp = self._client.get(f"/api/v1/tasks/{task_id}/logs")
        resp.raise_for_status()
        return resp.json()

    # --- Approvals ---

    def list_approvals(self, task_id: Optional[str] = None) -> List[ApprovalRequest]:
        """List pending or decided approvals."""
        if self.local:
            if not self._repo:
                return []
            rows = self._repo.list_approvals(task_id=task_id)
            return [ApprovalRequest.model_validate(r) for r in rows]

        assert self._client is not None
        params = {"task_id": task_id} if task_id else {}
        resp = self._client.get("/api/v1/approvals", params=params)
        resp.raise_for_status()
        return [ApprovalRequest.model_validate(a) for a in resp.json()]

    def request_approval(
        self,
        task_id: str,
        tool_name: str,
        parameters: Dict[str, Any],
        reason: str,
        step_id: Optional[str] = None,
    ) -> ApprovalRequest:
        """Request human approval, transitioning task to blocked."""
        if self.local:
            if not self._repo:
                raise RuntimeError("Local client requires an initialized database.")
            row = self._repo.request_approval(task_id=task_id, tool_name=tool_name, parameters=parameters, reason=reason, step_id=step_id)
            return ApprovalRequest.model_validate(row)

        assert self._client is not None
        payload = {
            "task_id": task_id,
            "tool_name": tool_name,
            "parameters": parameters,
            "reason": reason,
            "step_id": step_id,
        }
        resp = self._client.post("/api/v1/approvals", json=payload)
        resp.raise_for_status()
        return ApprovalRequest.model_validate(resp.json())

    def decide_approval(
        self,
        approval_id: str,
        approved: bool,
        reason: Optional[str] = None,
        decided_by: str = "human",
    ) -> Dict[str, Any]:
        """Approve or reject a blocked task."""
        if self.local:
            if not self._repo:
                raise RuntimeError("Local client requires an initialized database.")
            return self._repo.decide_approval(approval_id=approval_id, approved=approved, reason=reason, decided_by=decided_by)

        assert self._client is not None
        payload = {"approved": approved, "reason": reason, "decided_by": decided_by}
        resp = self._client.post(f"/api/v1/approvals/{approval_id}/decide", json=payload)
        resp.raise_for_status()
        return resp.json()

    # --- Quantum Operations ---

    def estimate_quantum(
        self,
        qubits: int = 4,
        physical_error_rate: float = 0.001,
        error_budget: float = 1e-3,
    ) -> QuantumResult:
        """Estimate code distance and fault-tolerant physical resources."""
        if self.local and self._quantum:
            d, feasible, _ = self._quantum.cost_model.solve_minimum_code_distance(
                physical_error=physical_error_rate,
                threshold=0.01,
                spacetime_volume=qubits * 100,
                allocated_error_budget=error_budget,
            )
            return QuantumResult(
                num_qubits=qubits,
                code_distance=d if feasible else 3,
                t_count=qubits * 10,
                estimated_runtime_sec=1.25,
                feasible=feasible,
            )

        assert self._client is not None
        payload = {"qubits": qubits, "physical_error_rate": physical_error_rate, "error_budget": error_budget}
        resp = self._client.post("/api/v1/quantum/estimate", json=payload)
        resp.raise_for_status()
        return QuantumResult.model_validate(resp.json())

    # --- Event Streaming ---

    def stream_events(self, task_id: Optional[str] = None) -> Iterator[PlatformEvent]:
        """Stream real-time platform events using Server-Sent Events (SSE)."""
        if self.local:
            return

        assert self._client is not None
        params = {"task_id": task_id} if task_id else {}
        with self._client.stream("GET", "/api/v1/events/stream", params=params) as response:
            for line in response.iter_lines():
                if line.startswith("data: "):
                    data_str = line[len("data: "):].strip()
                    if data_str:
                        try:
                            event_dict = json.loads(data_str)
                            yield PlatformEvent.model_validate(event_dict)
                        except Exception:
                            continue
