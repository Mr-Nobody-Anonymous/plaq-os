"""Plaq-OS Artifact Service.

Provides content-addressable storage (CAS), cryptographic SHA-256 fingerprinting,
metadata registration, task record linkage, and integrity verification for
quantum run manifests, Pareto reports, diffs, and benchmark data.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sqlite3
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Union

from plaq_contracts import ArtifactRecord, ArtifactType


class ArtifactIntegrityError(ValueError):
    """Raised when an artifact's content does not match its expected SHA-256 hash."""
    pass


class ArtifactNotFoundError(KeyError):
    """Raised when the requested artifact record or content file does not exist."""
    pass


class ArtifactService:
    """Content-addressable artifact storage and control plane tracking."""

    def __init__(
        self,
        storage_dir: Union[str, Path],
        conn: Optional[Any] = None,
        event_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ):
        self.storage_dir = Path(storage_dir).resolve()
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.conn = conn
        self.event_callback = event_callback

    def _get_db_conn(self) -> Optional[sqlite3.Connection]:
        if self.conn is None:
            return None
        if hasattr(self.conn, "get_connection"):
            return self.conn.get_connection()
        if hasattr(self.conn, "conn"):
            return self.conn.conn
        if hasattr(self.conn, "db"):
            db = self.conn.db
            if hasattr(db, "get_connection"):
                return db.get_connection()
            if hasattr(db, "conn"):
                return db.conn
        return self.conn

    def publish_artifact(
        self,
        task_id: str,
        artifact_type: Union[ArtifactType, str],
        name: str,
        content: Union[str, bytes, Path],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ArtifactRecord:
        """Publish and fingerprint an artifact, writing to disk and linking to task."""
        # 1. Resolve content bytes
        if isinstance(content, Path) or (isinstance(content, str) and os.path.isfile(content)):
            source_path = Path(content)
            raw_bytes = source_path.read_bytes()
        elif isinstance(content, str):
            raw_bytes = content.encode("utf-8")
        elif isinstance(content, bytes):
            raw_bytes = content
        else:
            raise TypeError(f"Unsupported artifact content type: {type(content)}")

        # 2. Compute content SHA-256 and byte size
        sha256_hash = hashlib.sha256(raw_bytes).hexdigest()
        size_bytes = len(raw_bytes)

        # 3. Content-addressable storage destination
        target_dir = self.storage_dir / "tasks" / task_id
        target_dir.mkdir(parents=True, exist_ok=True)
        dest_path = target_dir / name

        # Atomic file write via temp file
        temp_dest = dest_path.with_suffix(dest_path.suffix + ".tmp")
        temp_dest.write_bytes(raw_bytes)
        temp_dest.replace(dest_path)

        # 4. Create database record
        artifact_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        type_str = artifact_type.value if isinstance(artifact_type, ArtifactType) else str(artifact_type)
        metadata_json = json.dumps(metadata) if metadata is not None else None

        db_conn = self._get_db_conn()
        if db_conn is not None:
            with db_conn:
                db_conn.execute(
                    """
                    INSERT INTO artifacts (
                        id, task_id, artifact_type, name, file_path, sha256_hash,
                        size_bytes, created_at, metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        artifact_id,
                        task_id,
                        type_str,
                        name,
                        str(dest_path),
                        sha256_hash,
                        size_bytes,
                        now,
                        metadata_json,
                    ),
                )

        record = ArtifactRecord(
            id=artifact_id,
            task_id=task_id,
            artifact_type=type_str,  # type: ignore
            name=name,
            file_path=str(dest_path),
            sha256_hash=sha256_hash,
            size_bytes=size_bytes,
            created_at=now,  # type: ignore
            metadata=metadata or {},
        )

        # 5. Emit event notification
        if self.event_callback:
            event = {
                "event_type": "artifact_published",
                "artifact_id": artifact_id,
                "task_id": task_id,
                "artifact_type": type_str,
                "name": name,
                "sha256": sha256_hash,
                "size_bytes": size_bytes,
                "file_path": str(dest_path),
                "timestamp": now,
            }
            self.event_callback(event)

        return record

    def get_artifact(self, artifact_id: str) -> Optional[ArtifactRecord]:
        """Fetch artifact record by ID."""
        db_conn = self._get_db_conn()
        if db_conn is None:
            raise RuntimeError("Database connection not configured.")
        cursor = db_conn.execute("SELECT * FROM artifacts WHERE id = ?", (artifact_id,))
        row = cursor.fetchone()
        if not row:
            return None
        row_dict = dict(row)
        meta = json.loads(row_dict["metadata"]) if row_dict.get("metadata") else {}
        return ArtifactRecord(
            id=row_dict["id"],
            task_id=row_dict["task_id"],
            artifact_type=row_dict["artifact_type"],
            name=row_dict["name"],
            file_path=row_dict["file_path"],
            sha256_hash=row_dict["sha256_hash"],
            size_bytes=row_dict["size_bytes"],
            created_at=row_dict["created_at"],
            metadata=meta,
        )

    def list_artifacts(
        self,
        task_id: Optional[str] = None,
        artifact_type: Optional[str] = None,
    ) -> List[ArtifactRecord]:
        """List artifacts with optional filtering."""
        db_conn = self._get_db_conn()
        if db_conn is None:
            raise RuntimeError("Database connection not configured.")
        query = "SELECT * FROM artifacts WHERE 1=1"
        params: List[Any] = []
        if task_id:
            query += " AND task_id = ?"
            params.append(task_id)
        if artifact_type:
            query += " AND artifact_type = ?"
            params.append(artifact_type)
        query += " ORDER BY created_at DESC"

        cursor = db_conn.execute(query, params)
        records: List[ArtifactRecord] = []
        for r in cursor.fetchall():
            rd = dict(r)
            meta = json.loads(rd["metadata"]) if rd.get("metadata") else {}
            records.append(
                ArtifactRecord(
                    id=rd["id"],
                    task_id=rd["task_id"],
                    artifact_type=rd["artifact_type"],
                    name=rd["name"],
                    file_path=rd["file_path"],
                    sha256_hash=rd["sha256_hash"],
                    size_bytes=rd["size_bytes"],
                    created_at=rd["created_at"],
                    metadata=meta,
                )
            )
        return records

    def read_artifact_bytes(self, artifact_id: str) -> bytes:
        """Read raw bytes of an artifact, validating its hash integrity."""
        record = self.get_artifact(artifact_id)
        if not record:
            raise ArtifactNotFoundError(f"Artifact {artifact_id} not found.")
        file_path = Path(record.file_path)
        if not file_path.exists():
            raise ArtifactNotFoundError(f"Artifact file {record.file_path} missing from storage.")
        content = file_path.read_bytes()
        actual_hash = hashlib.sha256(content).hexdigest()
        if actual_hash != record.sha256_hash:
            raise ArtifactIntegrityError(
                f"Artifact {artifact_id} hash mismatch: expected {record.sha256_hash}, got {actual_hash}"
            )
        return content

    def read_artifact_text(self, artifact_id: str, encoding: str = "utf-8") -> str:
        """Read text content of an artifact with UTF-8 decoding."""
        return self.read_artifact_bytes(artifact_id).decode(encoding)

    def verify_artifact_integrity(self, artifact_id: str) -> bool:
        """Verify whether an artifact file exists and matches its stored SHA-256."""
        try:
            self.read_artifact_bytes(artifact_id)
            return True
        except (ArtifactNotFoundError, ArtifactIntegrityError):
            return False
