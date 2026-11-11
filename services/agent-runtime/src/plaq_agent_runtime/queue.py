"""In-process background task queue backed by the control-plane ``jobs`` table.

Long quantum optimizations no longer block the API worker: ``enqueue`` records a
job and a daemon thread runs ``AgentRuntime.execute_task`` / ``resume_task``.
No extra broker (Celery/Redis) is required.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from plaq_agent_runtime.loop import AgentRuntime, TaskResult
from plaq_control_plane.repository import ControlPlaneRepository


def _result_payload(result: TaskResult) -> Dict[str, Any]:
    return {
        "task_id": result.task_id,
        "status": result.status,
        "summary": result.summary,
        "error": result.error,
        "artifacts": result.artifacts,
        "modified_files": result.modified_files,
        "duration_ms": result.duration_ms,
    }


@dataclass
class QueueStats:
    workers: int
    started: bool
    queued: int = 0
    running: int = 0


class BackgroundTaskQueue:
    """Polls SQLite for queued jobs and executes them on daemon worker threads."""

    def __init__(
        self,
        repository: ControlPlaneRepository,
        runtime: Optional[AgentRuntime] = None,
        max_workers: int = 1,
        poll_interval: float = 0.05,
        runtime_factory: Optional[Callable[[], AgentRuntime]] = None,
    ) -> None:
        self.repo = repository
        self._runtime = runtime
        self._runtime_factory = runtime_factory
        self.max_workers = max(1, int(max_workers))
        self.poll_interval = poll_interval
        self._stop = threading.Event()
        self._threads: List[threading.Thread] = []
        self._started = False
        self._lock = threading.Lock()

    @property
    def runtime(self) -> AgentRuntime:
        if self._runtime is None:
            if self._runtime_factory:
                self._runtime = self._runtime_factory()
            else:
                self._runtime = AgentRuntime(repository=self.repo)
        return self._runtime

    def recover_orphans(self) -> int:
        """Re-queue jobs left ``running`` after a crash so workers can pick them up."""
        return self.repo.requeue_orphaned_jobs()

    def start(self) -> None:
        with self._lock:
            if self._started:
                return
            try:
                self.recover_orphans()
            except Exception:
                pass
            self._stop.clear()
            for i in range(self.max_workers):
                t = threading.Thread(
                    target=self._worker,
                    name=f"plaq-queue-{i}",
                    daemon=True,
                )
                t.start()
                self._threads.append(t)
            self._started = True

    def stop(self, timeout: float = 15.0) -> None:
        self._stop.set()
        for t in self._threads:
            t.join(timeout=timeout)
        with self._lock:
            self._threads.clear()
            self._started = False

    def enqueue(self, task_id: str, action: str = "execute") -> Dict[str, Any]:
        """Record a job and ensure workers are running."""
        if action not in {"execute", "resume"}:
            raise ValueError(f"Unknown job action: {action}")
        job = self.repo.create_job(task_id=task_id, action=action)
        if not self._started:
            self.start()
        return job

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        return self.repo.get_job(job_id)

    def list_jobs(self, task_id: Optional[str] = None, status: Optional[str] = None) -> List[Dict[str, Any]]:
        return self.repo.list_jobs(task_id=task_id, status=status)

    def wait(self, job_id: str, timeout: float = 60.0) -> Dict[str, Any]:
        """Block until a job reaches a terminal state or ``timeout`` elapses."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            job = self.repo.get_job(job_id)
            if not job:
                raise KeyError(f"Job '{job_id}' not found.")
            if job["status"] in {"completed", "failed", "cancelled"}:
                return job
            time.sleep(min(0.05, self.poll_interval))
        job = self.repo.get_job(job_id)
        if not job:
            raise KeyError(f"Job '{job_id}' not found.")
        return job

    def stats(self) -> QueueStats:
        jobs = self.repo.list_jobs()
        return QueueStats(
            workers=self.max_workers,
            started=self._started,
            queued=sum(1 for j in jobs if j.get("status") == "queued"),
            running=sum(1 for j in jobs if j.get("status") == "running"),
        )

    def _worker(self) -> None:
        while not self._stop.is_set():
            job = None
            try:
                job = self.repo.claim_next_job()
            except Exception:
                job = None
            if job is None:
                self._stop.wait(self.poll_interval)
                continue
            try:
                action = job.get("action") or "execute"
                if action == "resume":
                    result = self.runtime.resume_task(job["task_id"])
                else:
                    result = self.runtime.execute_task(job["task_id"])
                self.repo.update_job(
                    job["id"],
                    status="completed",
                    result=json.dumps(_result_payload(result)),
                )
            except Exception as exc:
                self.repo.update_job(job["id"], status="failed", error=str(exc))


_queues: Dict[int, BackgroundTaskQueue] = {}
_queues_lock = threading.Lock()


def get_queue(
    repository: ControlPlaneRepository,
    runtime: Optional[AgentRuntime] = None,
    autostart: bool = True,
) -> BackgroundTaskQueue:
    """Process-wide queue singleton keyed by repository identity."""
    key = id(repository)
    with _queues_lock:
        q = _queues.get(key)
        if q is None:
            q = BackgroundTaskQueue(repository=repository, runtime=runtime)
            _queues[key] = q
        elif runtime is not None and q._runtime is None:
            q._runtime = runtime
        if autostart and not q._started:
            q.start()
        return q


def stop_queue_for(repository: ControlPlaneRepository, timeout: float = 15.0) -> None:
    """Stop the process-wide queue bound to ``repository``, if any."""
    key = id(repository)
    with _queues_lock:
        q = _queues.pop(key, None)
    if q is not None:
        try:
            q.stop(timeout=timeout)
        except Exception:
            pass


def reset_queues() -> None:
    """Stop and drop process-wide queue instances (tests)."""
    with _queues_lock:
        qs = list(_queues.values())
        _queues.clear()
    for q in qs:
        try:
            q.stop(timeout=15.0)
        except Exception:
            pass
