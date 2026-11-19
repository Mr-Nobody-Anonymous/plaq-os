"""Regression tests for security, artifact integrity, and execution correctness."""
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from plaq_agent_runtime.loop import AgentRuntime, TaskResult
from plaq_agent_runtime.queue import BackgroundTaskQueue
from plaq_agent_runtime.tools.artifact_tools import ArtifactPublishParams, artifacts_publish
from plaq_agent_runtime.tools.workspace_tools import WorkspacePatchParams, workspace_patch
from plaq_api.app import create_app
from plaq_api.events import EventBroadcaster
from plaq_artifacts.service import ArtifactService
from plaq_contracts.event import EventType, PlatformEvent
from plaq_contracts.tool import ToolResult
from plaq_control_plane.db import DatabaseEngine
from plaq_control_plane.repository import ControlPlaneRepository
from plaq_model_gateway.providers import DeterministicPlanner


@pytest.fixture
def repo(tmp_path):
    result = ControlPlaneRepository(DatabaseEngine(str(tmp_path / "db.sqlite")))
    yield result
    result.close()


def test_anonymous_workbench_does_not_grant_access(monkeypatch, repo):
    monkeypatch.setenv("PLAQ_API_KEY", "secret")
    monkeypatch.delenv("PLAQ_AUTH", raising=False)
    with TestClient(create_app(repository=repo)) as client:
        assert client.get("/").status_code == 200
        assert "plaq_session" not in client.cookies
        assert client.get("/api/v1/tasks").status_code == 401
        assert client.get("/api/v1/tasks?token=secret").status_code == 401
        assert client.post("/api/v1/session", json={"key": "wrong"}).status_code == 401
        assert client.post("/api/v1/session", json={"key": "secret"}).status_code == 200
        assert client.get("/api/v1/tasks").status_code == 200
        assert client.post("/api/v1/tasks", json={"goal": "x"}, headers={"Origin": "https://evil.example"}).status_code == 403


def test_artifact_name_confined_and_immutable(tmp_path, repo):
    task = repo.create_task("artifacts")
    svc = ArtifactService(tmp_path / "artifacts", repo.db)
    for name in ("../escape", "/tmp/escape", "C:\\escape"):
        with pytest.raises(ValueError):
            svc.publish_artifact(task["id"], "report", name, "data")
    a = svc.publish_artifact(task["id"], "report", "report.txt", "first")
    b = svc.publish_artifact(task["id"], "report", "report.txt", "second")
    assert a.file_path != b.file_path
    assert svc.read_artifact_text(a.id) == "first"
    assert svc.read_artifact_text(b.id) == "second"


def test_artifact_tool_requires_real_file_and_registers(tmp_path, repo):
    task = repo.create_task("artifacts")
    ctx = SimpleNamespace(workspace_path=tmp_path, task_id=task["id"], control_plane=repo, artifact_service=None)
    result = artifacts_publish(ArtifactPublishParams(file="missing.json"), ctx)
    assert not result.success
    assert not (tmp_path / "missing.json").exists()
    (tmp_path / "report.json").write_text('{"value":1}')
    result = artifacts_publish(ArtifactPublishParams(file="report.json"), ctx)
    assert result.success
    assert len(repo.list_artifacts(task_id=task["id"])) == 1


def test_artifact_api_rejects_tampered_blob(tmp_path, repo):
    task = repo.create_task("artifacts")
    service = ArtifactService(tmp_path / "artifacts", repo.db)
    record = service.publish_artifact(task["id"], "report", "report.txt", "original")
    Path(record.file_path).write_text("changed")
    with TestClient(create_app(repository=repo)) as client:
        assert client.get(f"/api/v1/artifacts/{record.id}/content").status_code == 409


def test_unmatched_patch_never_changes_file(tmp_path):
    file = tmp_path / "a.txt"
    file.write_text("alpha\nbeta\n")
    ctx = SimpleNamespace(workspace_path=tmp_path)
    result = workspace_patch(WorkspacePatchParams(path="a.txt", diff="@@ -1,2 +1,2 @@\n alpha\n-wrong\n+new\n"), ctx)
    assert not result.success
    assert file.read_text() == "alpha\nbeta\n"
    result = workspace_patch(WorkspacePatchParams(path="a.txt", diff="@@ -1,2 +1,2 @@\n alpha\n-beta\n+new\n"), ctx)
    assert result.success
    assert file.read_text() == "alpha\nnew\n"


def test_numeric_criteria_require_correct_evidence():
    planner = DeterministicPlanner()
    def check(output):
        return planner.verify_criteria("Physical qubits <= 500", ToolResult(success=True, output=output, exit_code=0))[0]
    assert not check('{"physical_qubits": 1000000}')
    assert not check("no metrics")
    assert check('{"physical_qubits": 400}')


def test_plan_persisted_without_replanning(tmp_path, repo):
    (tmp_path / "README.md").write_text("hello")
    runtime = AgentRuntime(repo)
    task = repo.create_task("Clean cache", workspace_path=str(tmp_path))
    assert runtime.execute_task(task["id"]).status == "blocked"
    steps = repo.list_steps(task["id"])
    assert steps[0]["tool_name"] == "terminal.run"
    assert json.loads(steps[0]["tool_parameters"])["cmd"] == "git clean -fdx"
    approval = repo.list_approvals(task["id"])[0]
    repo.decide_approval(approval["id"], False)
    with pytest.raises(ValueError):
        repo.decide_approval(approval["id"], True)


def test_start_does_not_requeue_another_worker(repo):
    task = repo.create_task("one")
    job = repo.create_job(task["id"])
    repo.update_job(job["id"], status="running")
    queue = BackgroundTaskQueue(repo)
    queue.start()
    queue.stop()
    assert repo.get_job(job["id"])["status"] == "running"


def test_failed_task_marks_job_failed(repo):
    class Runtime:
        def execute_task(self, task_id):
            return TaskResult(task_id=task_id, status="failed", error="failed task")
    task = repo.create_task("failure")
    queue = BackgroundTaskQueue(repo, runtime=Runtime())
    job = queue.enqueue(task["id"])
    result = queue.wait(job["id"], timeout=5)
    queue.stop()
    assert result["status"] == "failed"
    assert result["error"] == "failed task"


def test_event_publish_from_worker_thread():
    async def run():
        bus = EventBroadcaster()
        bus.bind_loop(asyncio.get_running_loop())
        q = bus.subscribe()
        await asyncio.to_thread(bus.publish, PlatformEvent(event_type=EventType.TASK_CREATED, task_id="t"))
        event = await asyncio.wait_for(q.get(), 2)
        assert event["task_id"] == "t"
    asyncio.run(run())


def test_unknown_hardware_rejected_and_error_override_changes_estimate(repo):
    with TestClient(create_app(repository=repo)) as client:
        assert client.post("/api/v1/quantum/estimate", json={"hardware_profile": "not-a-device"}).status_code == 400
        a = client.post("/api/v1/quantum/estimate", json={"physical_error_rate": 0.0001}).json()
        b = client.post("/api/v1/quantum/estimate", json={"physical_error_rate": 0.02}).json()
        assert a["feasible"]
        assert not b["feasible"]


def test_disabled_queue_cannot_be_started_by_request(monkeypatch, repo):
    monkeypatch.setenv("PLAQ_QUEUE", "off")
    with TestClient(create_app(repository=repo)) as client:
        task = client.post("/api/v1/tasks", json={"goal": "do something"}).json()
        assert client.post(f"/api/v1/tasks/{task['id']}/run").status_code == 503


def test_optimization_uses_requested_circuit(monkeypatch, repo):
    seen = []
    def fake_search(circuit, **kwargs):
        seen.append(circuit.num_qubits)
        return [], []
    monkeypatch.setattr("plaq_api.routers.quantum.pq_optimizer.search_pareto_optimizer", fake_search)
    with TestClient(create_app(repository=repo)) as client:
        assert client.post("/api/v1/quantum/optimize", json={"circuit_name": "bell"}).status_code == 200
        assert client.post("/api/v1/quantum/optimize", json={"circuit_name": "qft"}).status_code == 200
    assert seen == [2, 6]


def test_approval_resume_uses_persisted_plan(monkeypatch, tmp_path, repo):
    import subprocess
    ws = tmp_path / "workspace"
    ws.mkdir()
    subprocess.run(["git", "init", str(ws)], check=True, capture_output=True)
    task = repo.create_task("Clean cache", workspace_path=str(ws))
    runtime = AgentRuntime(repo)
    assert runtime.execute_task(task["id"]).status == "blocked"
    approval = repo.list_approvals(task["id"])[0]
    repo.decide_approval(approval["id"], True)
    def no_replan(*args, **kwargs):
        raise AssertionError("must not replan after approval")
    monkeypatch.setattr(runtime.model_gateway, "generate_plan", no_replan)
    assert runtime.resume_task(task["id"]).status == "completed"


def test_atomic_plan_rollback(repo):
    from plaq_contracts.step import PlanStep
    task = repo.create_task("test")
    steps = [PlanStep(task_id=task["id"], step_number=1, step_name="ok", tool_name="workspace.list"),
             PlanStep(task_id=task["id"], step_number=2, step_name="bad", tool_name=None)]
    with pytest.raises(ValueError):
        repo.record_plan(task["id"], steps)
    assert repo.list_steps(task["id"]) == []


def test_unknown_workloads_rejected(repo):
    with TestClient(create_app(repository=repo)) as client:
        assert client.post("/api/v1/quantum/compile", json={"circuit_name": "bogus"}).status_code == 400
        assert client.post("/api/v1/quantum/optimize", json={"circuit_name": "bogus"}).status_code == 400


def test_api_workspace_and_host_command_policy(monkeypatch, tmp_path, repo):
    monkeypatch.setenv("PLAQ_WORKSPACE", str(tmp_path))
    monkeypatch.delenv("PLAQ_ALLOW_HOST_COMMANDS", raising=False)
    (tmp_path / "tests").mkdir()
    with TestClient(create_app(repository=repo)) as client:
        assert client.post("/api/v1/tasks", json={"goal": "run pytest", "workspace_path": "../"}).status_code == 422
        task = client.post("/api/v1/tasks", json={"goal": "run pytest", "workspace_path": "."}).json()
        result = client.post(f"/api/v1/tasks/{task['id']}/run?background=false").json()
        assert result["status"] == "failed"
        assert "Permission denied" in result["error"]


def test_process_cancel_stops_running_tool(tmp_path, repo):
    import sys
    import threading
    import time
    from plaq_contracts.step import PlanDefinition, PlanStep

    marker = tmp_path / "started"
    task = repo.create_task("cancel process", workspace_path=str(tmp_path))
    runtime = AgentRuntime(repo)
    command = [sys.executable, "-c", f"from pathlib import Path; import time; Path({str(marker)!r}).touch(); time.sleep(30)"]
    step = PlanStep(task_id=task["id"], step_number=1, step_name="wait", criteria="Exit code 0",
                    tool_name="terminal.run", tool_parameters={"cmd": command, "timeout_sec": 40})
    runtime.model_gateway.generate_plan = lambda *a, **kw: PlanDefinition(task_id=task["id"], goal=task["goal"], steps=[step])
    results = []
    thread = threading.Thread(target=lambda: results.append(runtime.execute_task(task["id"])))
    thread.start()
    deadline = time.monotonic() + 10
    while not marker.exists() and time.monotonic() < deadline:
        time.sleep(0.02)
    assert marker.exists(), "child process did not start"
    assert runtime.cancel_task(task["id"])
    thread.join(timeout=5)
    assert not thread.is_alive(), "cancel did not terminate the child"
    assert results[0].status == "cancelled"


def test_unsupported_goal_and_unverified_criteria_fail_safely(tmp_path, repo):
    task = repo.create_task("Build me a website", workspace_path=str(tmp_path))
    result = AgentRuntime(repo).execute_task(task["id"])
    assert result.status == "failed"
    assert "No deterministic plan" in result.error
    result = ToolResult(success=True, output='{"depth": 3}', exit_code=0)
    assert not DeterministicPlanner().verify_criteria("depth > 0 and system is secure", result)[0]
    assert not DeterministicPlanner().verify_criteria("The task is complete", result)[0]


def test_active_jobs_are_idempotent(repo):
    task = repo.create_task("queue me")
    one = repo.create_job(task["id"])
    two = repo.create_job(task["id"])
    assert one["id"] == two["id"]
    with pytest.raises(ValueError, match="different action"):
        repo.create_job(task["id"], "resume")
    repo.update_job(one["id"], status="failed")
    assert repo.create_job(task["id"])["id"] != one["id"]


def test_cli_enqueue_without_wait_does_not_spawn_worker(monkeypatch, tmp_path, capsys):
    from plaq_cli.main import main
    db_path = str(tmp_path / "cli.db")
    monkeypatch.setenv("PLAQ_DB_PATH", db_path)
    repo = ControlPlaneRepository(DatabaseEngine(db_path))
    task = repo.create_task("Simulate Bell")
    assert main(["task", "run", task["id"], "--json"]) == 0
    job = json.loads(capsys.readouterr().out)["job"]
    assert repo.get_job(job["id"])["status"] == "queued"
    repo.close()
