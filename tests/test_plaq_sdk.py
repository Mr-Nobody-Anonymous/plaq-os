"""Unit tests for plaq_sdk package."""

import pytest
from plaq_sdk import PlaqClient
from plaq_contracts import TaskStatus, ApprovalStatus


def test_plaq_client_local_lifecycle():
    with PlaqClient.local_client(":memory:") as client:
        health = client.health()
        assert health["status"] == "ok"
        assert health["mode"] == "local"

        task = client.create_task("Compile surface code", parameters={"distance": 3})
        assert task.goal == "Compile surface code"
        assert task.status == TaskStatus.QUEUED

        loaded = client.get_task(task.id)
        assert loaded is not None
        assert loaded.id == task.id

        tasks = client.list_tasks()
        assert len(tasks) == 1

        t_running = client.transition_task(task.id, "planning")
        assert t_running.status == TaskStatus.PLANNING

        t_running2 = client.transition_task(task.id, "running")
        assert t_running2.status == TaskStatus.RUNNING

        app = client.request_approval(task.id, "terminal.run", {"cmd": "pytest"}, "Run verification")
        assert app.status == ApprovalStatus.PENDING

        task_blocked = client.get_task(task.id)
        assert task_blocked.status == TaskStatus.BLOCKED

        dec = client.decide_approval(app.id, approved=True, reason="Approved by tester")
        assert dec["status"] == "approved"

        task_resumed = client.get_task(task.id)
        assert task_resumed.status == TaskStatus.RUNNING


def test_plaq_client_quantum_estimation():
    with PlaqClient.local_client(":memory:") as client:
        res = client.estimate_quantum(qubits=4, physical_error_rate=0.001)
        assert res.num_qubits == 4
        assert res.code_distance >= 3
        assert res.feasible is True
