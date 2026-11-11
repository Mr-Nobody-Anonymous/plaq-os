"""Background task queue + jobs table."""

from __future__ import annotations

import json

from plaq_agent_runtime.loop import AgentRuntime
from plaq_agent_runtime.queue import BackgroundTaskQueue, reset_queues
from plaq_control_plane.db import DatabaseEngine
from plaq_control_plane.repository import ControlPlaneRepository


def test_job_crud_and_claim(tmp_path):
    engine = DatabaseEngine(str(tmp_path / "jobs.db"))
    repo = ControlPlaneRepository(engine)
    task = repo.create_task("queue me", workspace_path=str(tmp_path))
    job = repo.create_job(task["id"], action="execute")
    assert job["status"] == "queued"
    claimed = repo.claim_next_job()
    assert claimed is not None
    assert claimed["id"] == job["id"]
    assert claimed["status"] == "running"
    assert repo.claim_next_job() is None
    repo.update_job(job["id"], status="completed", result=json.dumps({"ok": True}))
    done = repo.get_job(job["id"])
    assert done["status"] == "completed"
    engine.close()


def test_requeue_orphaned_jobs(tmp_path):
    engine = DatabaseEngine(str(tmp_path / "orphan.db"))
    repo = ControlPlaneRepository(engine)
    task = repo.create_task("orphan", workspace_path=str(tmp_path))
    job = repo.create_job(task["id"])
    repo.update_job(job["id"], status="running")
    n = repo.requeue_orphaned_jobs()
    assert n == 1
    assert repo.get_job(job["id"])["status"] == "queued"
    engine.close()


def test_background_queue_executes_task(tmp_path):
    reset_queues()
    (tmp_path / "README.md").write_text("# hello\n", encoding="utf-8")
    engine = DatabaseEngine(str(tmp_path / "q.db"))
    repo = ControlPlaneRepository(engine)
    runtime = AgentRuntime(repository=repo)
    task = repo.create_task("Analyze data and generate docs", workspace_path=str(tmp_path))
    queue = BackgroundTaskQueue(repository=repo, runtime=runtime, poll_interval=0.02)
    job = queue.enqueue(task["id"])
    finished = queue.wait(job["id"], timeout=60)
    assert finished["status"] in {"completed", "failed", "blocked"}
    assert finished["status"] != "queued"
    queue.stop()
    engine.close()
    reset_queues()
