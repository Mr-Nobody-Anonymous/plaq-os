"""Unit and integration tests for Plaq-OS FastAPI Backend API."""

import json
import pytest
from fastapi import status
from fastapi.testclient import TestClient

from plaq_api.app import create_app
from plaq_api.events import EventBroadcaster
from plaq_control_plane.db import DatabaseEngine
from plaq_control_plane.repository import ControlPlaneRepository


@pytest.fixture
def test_repo(tmp_path):
    """Fixture providing isolated SQLite repository for API tests."""
    db_file = tmp_path / "test_api_control_plane.db"
    db_engine = DatabaseEngine(str(db_file))
    repo = ControlPlaneRepository(db_engine)
    yield repo
    repo.close()


@pytest.fixture
def client(test_repo):
    """Fixture providing FastAPI TestClient wired to isolated repository."""
    app = create_app(repository=test_repo)
    with TestClient(app) as test_client:
        yield test_client


class TestAPIHealth:
    """Verifies healthcheck endpoints."""

    def test_health_endpoint(self, client):
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["version"] == "0.3.0"
        assert "components" in data

    def test_healthz_endpoint(self, client):
        resp = client.get("/api/v1/healthz")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


class TestAPITasks:
    """Verifies task creation, listing, retrieval, and status transitions."""

    def test_create_task_success(self, client):
        resp = client.post("/api/v1/tasks", json={"goal": "Optimize QAOA Circuit", "workspace_path": "/tmp/test"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["goal"] == "Optimize QAOA Circuit"
        assert data["status"] == "queued"
        assert "id" in data

    def test_create_task_empty_goal_rejected(self, client):
        resp = client.post("/api/v1/tasks", json={"goal": "   "})
        assert resp.status_code == 422

    def test_get_task_by_id(self, client):
        create_resp = client.post("/api/v1/tasks", json={"goal": "Retrieve Me"})
        task_id = create_resp.json()["id"]

        get_resp = client.get(f"/api/v1/tasks/{task_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["id"] == task_id

    def test_get_nonexistent_task_404(self, client):
        resp = client.get("/api/v1/tasks/non-existent-uuid-1234")
        assert resp.status_code == 404

    def test_list_tasks_with_filtering(self, client):
        client.post("/api/v1/tasks", json={"goal": "Task 1"})
        client.post("/api/v1/tasks", json={"goal": "Task 2"})

        resp = client.get("/api/v1/tasks")
        assert resp.status_code == 200
        assert len(resp.json()) >= 2

        filtered = client.get("/api/v1/tasks?status=running")
        assert filtered.status_code == 200
        assert len(filtered.json()) == 0

    def test_transition_task_lifecycle(self, client):
        create_resp = client.post("/api/v1/tasks", json={"goal": "Lifecycle Task"})
        task_id = create_resp.json()["id"]

        resp1 = client.post(f"/api/v1/tasks/{task_id}/transition", json={"status": "planning"})
        assert resp1.status_code == 200
        assert resp1.json()["status"] == "planning"

        resp2 = client.post(f"/api/v1/tasks/{task_id}/transition", json={"status": "running"})
        assert resp2.status_code == 200
        assert resp2.json()["status"] == "running"

    def test_disallowed_state_transition_400(self, client):
        create_resp = client.post("/api/v1/tasks", json={"goal": "Invalid Transition Task"})
        task_id = create_resp.json()["id"]

        # queued -> completed is illegal
        resp = client.post(f"/api/v1/tasks/{task_id}/transition", json={"status": "completed"})
        assert resp.status_code == 400


class TestAPIApprovals:
    """Verifies human approval gates via REST API."""

    def test_request_and_decide_approval(self, client):
        create_resp = client.post("/api/v1/tasks", json={"goal": "Destructive Task"})
        task_id = create_resp.json()["id"]
        client.post(f"/api/v1/tasks/{task_id}/transition", json={"status": "planning"})
        client.post(f"/api/v1/tasks/{task_id}/transition", json={"status": "running"})

        # Request approval
        app_resp = client.post(
            "/api/v1/approvals",
            json={
                "task_id": task_id,
                "tool_name": "terminal.run",
                "parameters": {"cmd": "rm -rf build"},
                "reason": "Clean build directory",
            },
        )
        assert app_resp.status_code == 201
        app_id = app_resp.json()["id"]

        # Verify task transitioned to blocked
        task_resp = client.get(f"/api/v1/tasks/{task_id}")
        assert task_resp.json()["status"] == "blocked"

        # Decide approval (approve)
        decide_resp = client.post(
            f"/api/v1/approvals/{app_id}/decide",
            json={"approved": True, "reason": "Proceed with build cleanup"},
        )
        assert decide_resp.status_code == 200
        assert decide_resp.json()["status"] == "approved"

        # Verify task unblocked to running
        task_resp2 = client.get(f"/api/v1/tasks/{task_id}")
        assert task_resp2.json()["status"] == "running"


class TestAPIQuantum:
    """Verifies quantum co-design and resource estimation endpoints."""

    def test_quantum_estimate_endpoint(self, client):
        resp = client.post("/api/v1/quantum/estimate", json={"qubits": 4, "physical_error_rate": 0.001})
        assert resp.status_code == 200
        data = resp.json()
        assert data["num_qubits"] == 4
        assert data["code_distance"] >= 3
        assert "t_count" in data
        assert "estimated_runtime_sec" in data
        assert data["feasible"] is True

    def test_quantum_compile_endpoint(self, client):
        resp = client.post("/api/v1/quantum/compile", json={"circuit_name": "bernstein_vazirani", "num_qubits": 4})
        assert resp.status_code == 200
        data = resp.json()
        assert data["num_qubits"] == 4
        assert data["depth"] > 0
        assert data["total_ops"] > 0

    def test_quantum_baselines_endpoint(self, client):
        resp = client.post("/api/v1/quantum/baselines")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "comparisons" in data


class TestAPIStreaming:
    """Verifies WebSocket and SSE event streaming."""

    def test_websocket_connection_and_welcome(self, client):
        with client.websocket_connect("/ws/stream") as websocket:
            data = websocket.receive_json()
            assert data["event_type"] == "welcome"
            assert data["status"] == "connected"

            # Ping-pong
            websocket.send_text(json.dumps({"type": "ping", "time": 12345}))
            reply = websocket.receive_json()
            assert reply["type"] == "pong"
            assert reply["time"] == 12345
