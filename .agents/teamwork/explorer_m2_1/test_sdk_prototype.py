"""Prototype validation for PlaqClient (Local and Remote)."""

import json
from pathlib import Path
import tempfile
from typing import Any, Dict, List, Optional
import httpx
from fastapi import FastAPI, HTTPException, status
from fastapi.testclient import TestClient

import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_schemas_prototype import (
    Task,
    TaskCreate,
    TaskStatus,
    ApprovalRequest,
    ApprovalDecision,
    ApprovalStatus,
    QuantumEstimateRequest,
    QuantumResult,
    ArtifactRecord,
)

from tests.e2e.conftest import TestDatabase, QuantumEngineBridge


class PlaqClient:
    """Unified client providing both direct local in-process access and remote HTTP access."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        db_path: Optional[str] = None,
        local: bool = False,
        api_key: Optional[str] = None,
        http_client: Optional[httpx.Client] = None,
    ):
        self.local = local or (base_url is None)
        self.base_url = base_url.rstrip("/") if base_url else "http://127.0.0.1:8000"
        self.api_key = api_key
        self._db: Optional[TestDatabase] = None
        self._quantum: Optional[QuantumEngineBridge] = None

        if self.local:
            if db_path:
                self._db = TestDatabase(db_path)
            self._quantum = QuantumEngineBridge()
            self._client = None
        else:
            headers = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            self._client = http_client or httpx.Client(base_url=self.base_url, headers=headers, timeout=30.0)

    @classmethod
    def local_client(cls, db_path: Optional[str] = None) -> "PlaqClient":
        return cls(local=True, db_path=db_path)

    @classmethod
    def remote_client(cls, base_url: str = "http://127.0.0.1:8000", api_key: Optional[str] = None) -> "PlaqClient":
        return cls(base_url=base_url, api_key=api_key, local=False)

    def close(self):
        if self._client:
            self._client.close()
        if self._db:
            self._db.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    # --- Health ---
    def health(self) -> Dict[str, Any]:
        if self.local:
            return {
                "status": "ok",
                "version": "0.3.0",
                "mode": "local",
                "components": {"control_plane": "ok", "quantum_engine": "ok"},
            }
        resp = self._client.get("/api/v1/health")
        resp.raise_for_status()
        return resp.json()

    # --- Task Operations ---
    def create_task(self, goal: str, workspace_path: str = "", parameters: Optional[dict] = None) -> Task:
        if self.local:
            if not self._db:
                raise RuntimeError("Local client requires a database path")
            row = self._db.create_task(goal=goal, workspace_path=workspace_path, parameters=parameters)
            return Task.model_validate(row)
        
        payload = {"goal": goal, "workspace_path": workspace_path, "parameters": parameters or {}}
        resp = self._client.post("/api/v1/tasks", json=payload)
        resp.raise_for_status()
        return Task.model_validate(resp.json())

    def get_task(self, task_id: str) -> Optional[Task]:
        if self.local:
            if not self._db:
                raise RuntimeError("Local client requires a database path")
            row = self._db.get_task(task_id)
            return Task.model_validate(row) if row else None
        
        resp = self._client.get(f"/api/v1/tasks/{task_id}")
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return Task.model_validate(resp.json())

    def list_tasks(self, status: Optional[str] = None) -> List[Task]:
        if self.local:
            if not self._db:
                raise RuntimeError("Local client requires a database path")
            rows = self._db.list_tasks(status=status)
            return [Task.model_validate(r) for r in rows]
        
        params = {"status": status} if status else {}
        resp = self._client.get("/api/v1/tasks", params=params)
        resp.raise_for_status()
        return [Task.model_validate(item) for item in resp.json()]

    def get_task_logs(self, task_id: str) -> List[Dict[str, Any]]:
        if self.local:
            if not self._db:
                raise RuntimeError("Local client requires a database path")
            return self._db.get_audit_trail(task_id)
        
        resp = self._client.get(f"/api/v1/tasks/{task_id}/logs")
        resp.raise_for_status()
        return resp.json()

    def transition_task(self, task_id: str, to_status: str, error: Optional[str] = None) -> Task:
        if self.local:
            if not self._db:
                raise RuntimeError("Local client requires a database path")
            row = self._db.transition_task(task_id=task_id, to_status=to_status, error=error)
            return Task.model_validate(row)
        
        payload = {"status": to_status, "error": error}
        resp = self._client.post(f"/api/v1/tasks/{task_id}/transition", json=payload)
        resp.raise_for_status()
        return Task.model_validate(resp.json())

    # --- Approval Operations ---
    def request_approval(self, task_id: str, tool_name: str, parameters: dict, reason: str, step_id: Optional[str] = None) -> ApprovalRequest:
        if self.local:
            if not self._db:
                raise RuntimeError("Local client requires a database path")
            row = self._db.request_approval(task_id=task_id, tool_name=tool_name, parameters=parameters, reason=reason, step_id=step_id)
            return ApprovalRequest.model_validate(row)
        
        payload = {"task_id": task_id, "tool_name": tool_name, "parameters": parameters, "reason": reason, "step_id": step_id}
        resp = self._client.post("/api/v1/approvals", json=payload)
        resp.raise_for_status()
        return ApprovalRequest.model_validate(resp.json())

    def decide_approval(self, approval_id: str, approved: bool, reason: Optional[str] = None, decided_by: str = "human") -> Dict[str, Any]:
        if self.local:
            if not self._db:
                raise RuntimeError("Local client requires a database path")
            return self._db.decide_approval(approval_id=approval_id, approved=approved, reason=reason, decided_by=decided_by)
        
        payload = {"approved": approved, "reason": reason, "decided_by": decided_by}
        resp = self._client.post(f"/api/v1/approvals/{approval_id}/decide", json=payload)
        resp.raise_for_status()
        return resp.json()

    # --- Quantum Operations ---
    def estimate_quantum(self, qubits: int = 4, physical_error_rate: float = 0.001, error_budget: float = 1e-3) -> QuantumResult:
        if self.local:
            if not self._quantum:
                self._quantum = QuantumEngineBridge()
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
        
        payload = {"qubits": qubits, "physical_error_rate": physical_error_rate, "error_budget": error_budget}
        resp = self._client.post("/api/v1/quantum/estimate", json=payload)
        resp.raise_for_status()
        return QuantumResult.model_validate(resp.json())


def test_client_prototype():
    print("Testing PlaqClient in LOCAL mode...")
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    with PlaqClient.local_client(db_path=db_path) as client:
        health = client.health()
        assert health["status"] == "ok"
        assert health["mode"] == "local"

        task = client.create_task(goal="Synthesize Local Circuit", workspace_path="/test")
        assert task.status == TaskStatus.QUEUED
        assert task.goal == "Synthesize Local Circuit"

        t_fetched = client.get_task(task.id)
        assert t_fetched is not None
        assert t_fetched.id == task.id

        tasks = client.list_tasks()
        assert len(tasks) == 1

        client.transition_task(task.id, "planning")
        client.transition_task(task.id, "running")

        app = client.request_approval(task.id, "terminal.run", {"cmd": "run"}, "Testing approval")
        assert app.status == ApprovalStatus.PENDING

        dec = client.decide_approval(app.id, approved=True)
        assert dec["status"] == "approved"

        qres = client.estimate_quantum(qubits=6, physical_error_rate=0.001)
        assert qres.num_qubits == 6
        assert qres.code_distance >= 3

    print("Testing PlaqClient in REMOTE mode (with FastAPI TestClient)...")
    test_db = TestDatabase(db_path)
    app = FastAPI(title="Plaq API", version="0.3.0")

    @app.get("/api/v1/health")
    def api_health():
        return {"status": "ok", "version": "0.3.0"}

    @app.post("/api/v1/tasks", status_code=201)
    def api_create_task(p: dict):
        return test_db.create_task(p["goal"], p.get("workspace_path", ""), p.get("parameters"))

    @app.get("/api/v1/tasks/{task_id}")
    def api_get_task(task_id: str):
        t = test_db.get_task(task_id)
        if not t:
            raise HTTPException(status_code=404)
        return t

    @app.get("/api/v1/tasks")
    def api_list_tasks(status: Optional[str] = None):
        return test_db.list_tasks(status=status)

    @app.post("/api/v1/quantum/estimate")
    def api_estimate_quantum(p: dict):
        return {
            "num_qubits": p.get("qubits", 4),
            "code_distance": 5,
            "t_count": p.get("qubits", 4) * 10,
            "estimated_runtime_sec": 1.5,
        }

    test_http = TestClient(app)
    # Instantiate client wrapping test_http
    remote_client = PlaqClient(base_url="http://testserver", local=False, http_client=test_http)
    r_health = remote_client.health()
    assert r_health["status"] == "ok"

    r_task = remote_client.create_task("Remote task")
    assert r_task.goal == "Remote task"

    r_est = remote_client.estimate_quantum(qubits=8)
    assert r_est.num_qubits == 8
    assert r_est.code_distance == 5

    remote_client.close()
    test_db.close()
    print("ALL PLAQLIENT PROTOTYPE TESTS PASSED CLEANLY!")


if __name__ == "__main__":
    test_client_prototype()
