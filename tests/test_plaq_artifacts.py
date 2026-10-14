"""Unit tests for plaq_artifacts package."""

from pathlib import Path
import tempfile
import pytest

from plaq_artifacts import (
    ArtifactIntegrityError,
    ArtifactNotFoundError,
    ArtifactRecord,
    ArtifactService,
    ArtifactType,
)
from plaq_control_plane import DatabaseEngine, ControlPlaneRepository


@pytest.fixture
def artifact_setup():
    tmp_dir = tempfile.mkdtemp()
    db = DatabaseEngine(":memory:")
    repo = ControlPlaneRepository(db)
    task = repo.create_task("Artifact test task")
    service = ArtifactService(storage_dir=tmp_dir, conn=db.conn)
    yield service, task["id"], tmp_dir
    db.close()


def test_publish_and_verify_artifact(artifact_setup):
    service, task_id, tmp_dir = artifact_setup

    events = []
    service.event_callback = lambda e: events.append(e)

    record = service.publish_artifact(
        task_id=task_id,
        artifact_type=ArtifactType.REPORT,
        name="test_report.txt",
        content="Quantum execution successful. Pareto optimal point reached.",
        metadata={"run_id": "r1"},
    )

    assert record.name == "test_report.txt"
    assert len(record.sha256_hash) == 64
    assert record.size_bytes > 0
    assert service.verify_artifact_integrity(record.id) is True

    text = service.read_artifact_text(record.id)
    assert "Pareto optimal point" in text
    assert len(events) == 1
    assert events[0]["event_type"] == "artifact_published"


def test_artifact_tamper_detection(artifact_setup):
    service, task_id, tmp_dir = artifact_setup

    record = service.publish_artifact(
        task_id=task_id,
        artifact_type=ArtifactType.DIFF,
        name="patch.diff",
        content="original diff content",
    )

    # Tamper with file directly on disk
    file_path = Path(record.file_path)
    file_path.write_bytes(b"tampered diff content")

    assert service.verify_artifact_integrity(record.id) is False
    with pytest.raises(ArtifactIntegrityError):
        service.read_artifact_bytes(record.id)


def test_artifact_not_found(artifact_setup):
    service, task_id, tmp_dir = artifact_setup

    with pytest.raises(ArtifactNotFoundError):
        service.read_artifact_bytes("non-existent-id")
