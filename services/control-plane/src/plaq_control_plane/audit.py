"""Append-Only Cryptographic Audit Trail for Plaq-OS Control Plane.

Maintains an unbroken SHA-256 cryptographic hash chain recording all tool
invocations, parameter payloads, exit codes, execution durations, and modified
file fingerprints.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

from plaq_control_plane.redact import SecretRedactor


class AuditIntegrityError(ValueError):
    """Raised when an append-only audit trail hash chain has been tampered with or corrupted."""
    pass


class AuditChainer:
    """Manages SHA-256 cryptographic hash chaining and integrity verification."""

    GENESIS_HASH: str = "0" * 64

    @classmethod
    def compute_record_hash(
        cls,
        previous_hash: str,
        task_id: str,
        tool_name: str,
        parameters: str,
        output: str,
        exit_code: int,
        duration_ms: float,
        modified_files: str,
    ) -> str:
        """Compute SHA-256 digest chaining the previous block's hash.

        Payload format:
          {previous_hash}|{task_id}|{tool_name}|{parameters}|{output}|{exit_code}|{duration_ms:.2f}|{modified_files}
        """
        payload = (
            f"{previous_hash}|{task_id}|{tool_name}|{parameters}|"
            f"{output}|{exit_code}|{duration_ms:.2f}|{modified_files}"
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @classmethod
    def verify_chain(cls, records: List[Dict[str, Any]]) -> bool:
        """Verify unbroken chain of hashes across all audit records.

        Returns True if the chain is fully valid, False otherwise.
        """
        if not records:
            return True

        expected_prev = cls.GENESIS_HASH
        for idx, rec in enumerate(records):
            actual_prev = rec.get("previous_hash")
            if actual_prev != expected_prev:
                return False

            # Verify contiguous sequence numbers starting from 1
            expected_seq = idx + 1
            if int(rec.get("sequence_number", 0)) != expected_seq:
                return False

            recalculated = cls.compute_record_hash(
                previous_hash=actual_prev,
                task_id=str(rec["task_id"]),
                tool_name=str(rec["tool_name"]),
                parameters=str(rec.get("parameters", "")),
                output=str(rec.get("output", "")),
                exit_code=int(rec.get("exit_code", 0)),
                duration_ms=float(rec.get("duration_ms", 0.0)),
                modified_files=str(rec.get("modified_files", "[]")),
            )

            if recalculated != rec.get("current_hash"):
                return False

            expected_prev = rec["current_hash"]

        return True


@dataclass
class AuditEntry:
    id: str
    task_id: str
    sequence_number: int
    tool_name: str
    parameters: str
    output: str
    exit_code: int
    duration_ms: float
    modified_files: str
    previous_hash: str
    current_hash: str
    created_at: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class AuditTrailManager:
    """Database-backed manager for persisting and verifying audit logs."""

    def __init__(self, conn_or_engine: Any):
        self.target = conn_or_engine

    def _get_connection(self) -> sqlite3.Connection:
        if hasattr(self.target, "get_connection"):
            return self.target.get_connection()
        if hasattr(self.target, "conn"):
            return self.target.conn
        return self.target

    def record_audit(
        self,
        task_id: str,
        tool_name: str,
        parameters: Any,
        output: str,
        exit_code: int = 0,
        duration_ms: float = 0.0,
        modified_files: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Record an append-only audit entry with secret scrubbing and hash chaining."""
        redacted_params = SecretRedactor.redact_json(parameters if parameters is not None else {})
        redacted_output = SecretRedactor.redact_text(output if output is not None else "")
        params_str = json.dumps(redacted_params)
        files_str = json.dumps(modified_files or [])

        conn = self._get_connection()
        with conn:
            cursor = conn.execute(
                """
                SELECT sequence_number, current_hash
                FROM audit_trail
                WHERE task_id = ?
                ORDER BY sequence_number DESC
                LIMIT 1
                """,
                (task_id,),
            )
            prev_row = cursor.fetchone()

            if prev_row:
                seq_num = prev_row[0] + 1 if isinstance(prev_row, tuple) else prev_row["sequence_number"] + 1
                prev_hash = prev_row[1] if isinstance(prev_row, tuple) else prev_row["current_hash"]
            else:
                seq_num = 1
                prev_hash = AuditChainer.GENESIS_HASH

            curr_hash = AuditChainer.compute_record_hash(
                previous_hash=prev_hash,
                task_id=task_id,
                tool_name=tool_name,
                parameters=params_str,
                output=redacted_output,
                exit_code=exit_code,
                duration_ms=duration_ms,
                modified_files=files_str,
            )

            entry_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc).isoformat()

            conn.execute(
                """
                INSERT INTO audit_trail (
                    id, task_id, sequence_number, tool_name, parameters, output,
                    exit_code, duration_ms, modified_files, previous_hash, current_hash, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry_id,
                    task_id,
                    seq_num,
                    tool_name,
                    params_str,
                    redacted_output,
                    exit_code,
                    duration_ms,
                    files_str,
                    prev_hash,
                    curr_hash,
                    now,
                ),
            )

        cursor = conn.execute("SELECT * FROM audit_trail WHERE id = ?", (entry_id,))
        row = cursor.fetchone()
        return dict(row)

    def get_audit_trail(self, task_id: str) -> List[Dict[str, Any]]:
        """Retrieve full chronological audit trail for a task."""
        conn = self._get_connection()
        cursor = conn.execute(
            "SELECT * FROM audit_trail WHERE task_id = ? ORDER BY sequence_number ASC",
            (task_id,),
        )
        return [dict(r) for r in cursor.fetchall()]

    def verify_audit_trail(self, task_id: str) -> bool:
        """Verify the integrity of the audit log for a given task."""
        records = self.get_audit_trail(task_id)
        return AuditChainer.verify_chain(records)
