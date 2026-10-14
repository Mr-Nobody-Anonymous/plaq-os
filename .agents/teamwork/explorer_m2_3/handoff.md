# Handoff Report: Milestone M2 Explorer 3 (Audit Trail, Secret Redaction, Artifact Service)

**Author**: Explorer M2.3  
**Working Directory**: `C:\Users\hp\Desktop\plaq-os\.agents\teamwork\explorer_m2_3`  
**Target Milestone**: M2 (Shared Contracts & Control Plane Persistence)  
**Assigned Deliverables**:
1. Append-Only Cryptographic Audit Trail (`services/control-plane/src/plaq_control_plane/audit.py`)
2. Secret Redaction Filter (`services/control-plane/src/plaq_control_plane/redact.py`)
3. Artifact Service (`services/artifact-service/src/plaq_artifacts/service.py`)

---

## 1. Observation

### 1.1 Existing Test Suite Expectations & Fixture Implementation
Inspection of `tests/e2e/test_tier1_feature.py`, `tests/e2e/test_tier2_boundary.py`, `tests/e2e/test_tier3_pairwise.py`, `tests/e2e/test_tier4_workloads.py`, and `tests/e2e/conftest.py` reveals the exact contracts expected for the audit trail, secret redaction, and artifact persistence:

1. **Audit Hash Formula and Genesis Block** (`tests/e2e/conftest.py:228-245`):
   ```python
   GENESIS_HASH = "0" * 64

   def compute_record_hash(
       previous_hash: str,
       task_id: str,
       tool_name: str,
       parameters: str,
       output: str,
       exit_code: int,
       duration_ms: float,
       modified_files: str,
   ) -> str:
       payload = f"{previous_hash}|{task_id}|{tool_name}|{parameters}|{output}|{exit_code}|{duration_ms:.2f}|{modified_files}"
       return hashlib.sha256(payload.encode("utf-8")).hexdigest()
   ```
   *Note*: `duration_ms` must be formatted with 2 decimal places (`:.2f`). `parameters` and `modified_files` are serialized JSON strings.

2. **Audit Verification Contract** (`tests/e2e/conftest.py:247-269` & `test_tier1_feature.py:357-387`):
   - First record of any task MUST have `sequence_number == 1` and `previous_hash == "0" * 64`.
   - Each successive record must satisfy `rec["previous_hash"] == prev_rec["current_hash"]`.
   - Recomputing `compute_record_hash` on stored fields must match `rec["current_hash"]`.
   - Tampering with any stored field (e.g. `output`) causes `verify_chain` / `verify_audit_trail` to return `False`.

3. **Audit Trail Schema** (`tests/e2e/conftest.py:381-400`):
   ```sql
   CREATE TABLE IF NOT EXISTS audit_trail (
       id TEXT PRIMARY KEY,
       task_id TEXT NOT NULL,
       sequence_number INTEGER NOT NULL,
       tool_name TEXT NOT NULL,
       parameters TEXT,
       output TEXT,
       exit_code INTEGER NOT NULL,
       duration_ms REAL NOT NULL,
       modified_files TEXT,
       previous_hash TEXT NOT NULL,
       current_hash TEXT NOT NULL,
       created_at TEXT NOT NULL,
       FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
   );
   CREATE INDEX IF NOT EXISTS idx_audit_task_id ON audit_trail(task_id, sequence_number);
   ```

4. **Secret Redaction Patterns & Edge Cases** (`tests/e2e/conftest.py:92-142`, `test_tier1_feature.py:410-460`, and `test_tier2_boundary.py:499-607`):
   - **Bearer Tokens**: `re.compile(r"Bearer\s+([A-Za-z0-9_\-\.]+)", re.IGNORECASE)` -> `"Bearer [REDACTED_TOKEN]"`
   - **AWS Access Keys**: `re.compile(r"\b((?:AKIA|ABIA|ACCA|ASIA)[0-9A-Z]{16})\b")` -> `"[REDACTED_AWS_KEY]"`
   - **AWS Secret Keys**: `re.compile(r"((?:aws_secret_access_key|aws_secret)\s*[:=]\s*['\"]?)([A-Za-z0-9/+=]{16,})(['\"]?)", re.IGNORECASE)` -> `r"\1[REDACTED_SECRET_KEY]\3"` (supports special characters `+`, `/`, `=`)
   - **GitHub Personal Access Tokens**: `re.compile(r"\b(ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{36,})\b")` -> `"[REDACTED_GH_TOKEN]"`
   - **Slack Tokens**: `re.compile(r"\b(xox[baprs]-[A-Za-z0-9\-]{20,})\b")` -> `"[REDACTED_SLACK_TOKEN]"`
   - **Basic Auth in URLs**: `re.compile(r"(https?://[^:\s]+:)([^@\s]+)(@)", re.IGNORECASE)` -> `r"\1[REDACTED]\3"`
   - **PEM Private Keys**: `re.compile(r"-----BEGIN [A-Z ]+ PRIVATE KEY-----[\s\S]*?-----END [A-Z ]+ PRIVATE KEY-----")` -> `"[REDACTED_PRIVATE_KEY]"` (multiline regex)
   - **Generic Key-Value Assignments**: `re.compile(r"((?:api[_-]?key|password|access[_-]?token|auth[_-]?token)\s*[:=]\s*['\"]?)([^\s'\"&,;]+)(['\"]?)", re.IGNORECASE)` -> `r"\1[REDACTED]\3"`
   - **Recursive JSON Redaction**: Dictionaries matching sensitive root keywords `{"password", "secret", "token", "apikey", "authorization", "privatekey", "accesskey"}` have their values replaced with `"[REDACTED]"`.
   - **Preservation of Legitimate Identifiers**: SHA-256 digests (64 hex characters), git commit SHAs (40 hex characters), and UUIDs (`8-4-4-4-12` format) MUST NOT be falsely redacted (`test_b5_03`).
   - **Null / Type Safety**: `None`, `""`, numbers, booleans, and empty collections must be safely handled without raising exceptions (`test_b5_05`).

5. **Artifact Service Schema & Event Emission** (`tests/e2e/conftest.py:368-379`, `test_tier3_pairwise.py:392-450`, `test_tier4_workloads.py:104-126`, `337-372`):
   ```sql
   CREATE TABLE IF NOT EXISTS artifacts (
       id TEXT PRIMARY KEY,
       task_id TEXT NOT NULL,
       artifact_type TEXT NOT NULL,
       name TEXT NOT NULL,
       file_path TEXT NOT NULL,
       sha256_hash TEXT NOT NULL,
       size_bytes INTEGER NOT NULL,
       created_at TEXT NOT NULL,
       metadata TEXT,
       FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
   );
   ```
   - Content addressing: SHA-256 digest of stored bytes.
   - Files stored on disk are verified against `sha256_hash`.
   - Dispatches `artifact_published` and `artifact_ready` event payloads:
     ```json
     {
       "event_type": "artifact_published",
       "artifact_id": "<uuid>",
       "task_id": "<task_id>",
       "artifact_type": "quantum_pareto",
       "name": "pareto_report.json",
       "sha256": "<hash>",
       "size_bytes": 1024,
       "timestamp": "2026-10-14T..."
     }
     ```

### 1.2 Monorepo Layout & Packaging Baseline
`services/control-plane` and `services/artifact-service` currently contain `.gitkeep`. They need clean package structures:
- `services/control-plane/pyproject.toml` and `src/plaq_control_plane/`
- `services/artifact-service/pyproject.toml` and `src/plaq_artifacts/`
Both must conform to Python >=3.10 and Pydantic v2.

---

## 2. Logic Chain

1. **Chain of Integrity Requirement**:
   - The user request explicitly demands an append-only audit trail and secret redaction.
   - If secrets are redacted *after* hashing, re-verifying the log against the stored redacted output would cause a cryptographic hash mismatch unless the hash was computed on the redacted representation.
   - Therefore, the pipeline order must be strictly:
     $$\text{Raw Parameters / Output} \longrightarrow \text{Secret Redaction Filter} \longrightarrow \text{Cryptographic Hash Computation} \longrightarrow \text{Database Persistence}$$
   - This ensures the stored output and the hash input are identical, enabling `verify_audit_trail` to pass cleanly while guaranteeing zero secret leakage.

2. **Crash Recovery & Audit Chain Continuity**:
   - In Milestone M2 Feature 10 (Checkpoint Recovery), tasks can be resumed after system crashes.
   - To avoid breaking the hash chain across restarts (`test_f7_04`), `record_audit` must query the latest `sequence_number` and `current_hash` from the SQLite `audit_trail` table:
     - If rows exist for `task_id`: `next_seq = prev_seq + 1`, `prev_hash = prev_rec.current_hash`.
     - If no rows exist for `task_id`: `next_seq = 1`, `prev_hash = AuditChainer.GENESIS_HASH`.
   - Wrapping this query and insert within a database transaction guarantees strict sequencing without race conditions.

3. **Artifact Service Design Logic**:
   - Artifacts generated during task execution (e.g. quantum Pareto frontiers, benchmark CSVs, git patches) must be immutable, content-addressed, and linked to task records.
   - Content addressing with SHA-256 enables deduplication and fast tamper detection.
   - Linking each artifact to `task_id` with foreign key `ON DELETE CASCADE` satisfies relational integrity with `tasks`.
   - Storing content in a dedicated storage directory while registering metadata in SQLite fulfills both fast binary retrieval and structured querying.

---

## 3. Caveats

1. **Float Representation in Duration**: In `AuditChainer.compute_record_hash`, `duration_ms` is formatted as `{duration_ms:.2f}`. Any implementation must strictly use 2 decimal places to match `tests/e2e/conftest.py`.
2. **Parameters Formatting**: When recording audit entries, `parameters` must be a JSON string (`json.dumps(redacted_params)`) or an empty dict string `"{}"`. Passing raw Python objects into the hash function without JSON serialization would result in inconsistent hash values.
3. **Modified Files Encoding**: `modified_files` must be serialized as `json.dumps(files or [])` to guarantee deterministic whitespace and array formatting (`'["file1.py"]'` vs `'[]'`).
4. **Binary Artifacts**: For binary files (e.g. PNG diagrams, pickled models), secret redaction must not be applied to binary content; redaction applies to text outputs and parameter dictionaries.

---

## 4. Conclusion & Complete Architectural Designs

### 4.1 Secret Redaction Filter (`services/control-plane/src/plaq_control_plane/redact.py`)

#### Design Specification
The `SecretRedactor` class provides:
- Regex-based scrubbing for text strings (`redact_text`).
- Recursive dictionary and list scrubbing (`redact_json`).
- Strict false-positive avoidance for SHA-256 hashes, git SHAs, and UUIDs.

#### Proposed Code for `services/control-plane/src/plaq_control_plane/redact.py`
```python
"""Secret Redaction Filter for Plaq-OS Control Plane.

Scrubs sensitive tokens, passwords, AWS keys, private keys, and credentials
from tool parameters, standard output, and standard error before persistence
and audit logging.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Pattern, Tuple, Union


class SecretRedactor:
    """Automated scrubber for credentials, API tokens, and private keys."""

    PATTERNS: List[Tuple[Pattern[str], Union[str, Any]]] = [
        # 1. Bearer tokens (JWTs or arbitrary alphanumeric tokens)
        (
            re.compile(r"Bearer\s+([A-Za-z0-9_\-\.]+)", re.IGNORECASE),
            "Bearer [REDACTED_TOKEN]",
        ),
        # 2. GitHub Personal Access Tokens (classic and fine-grained)
        (
            re.compile(r"\b(ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{36,})\b"),
            "[REDACTED_GH_TOKEN]",
        ),
        # 3. Slack Bot and User Tokens
        (
            re.compile(r"\b(xox[baprs]-[A-Za-z0-9\-]{20,})\b"),
            "[REDACTED_SLACK_TOKEN]",
        ),
        # 4. Basic Auth embedded in HTTP/HTTPS URLs (http://user:password@host)
        (
            re.compile(r"(https?://[^:\s]+:)([^@\s]+)(@)", re.IGNORECASE),
            r"\1[REDACTED]\3",
        ),
        # 5. AWS Access Key IDs (AKIA, ABIA, ACCA, ASIA)
        (
            re.compile(r"\b((?:AKIA|ABIA|ACCA|ASIA)[0-9A-Z]{16})\b"),
            "[REDACTED_AWS_KEY]",
        ),
        # 6. AWS Secret Access Keys (supports base64 characters +, /, =)
        (
            re.compile(
                r"((?:aws_secret_access_key|aws_secret)\s*[:=]\s*['\"]?)([A-Za-z0-9/+=]{16,})(['\"]?)",
                re.IGNORECASE,
            ),
            r"\1[REDACTED_SECRET_KEY]\3",
        ),
        # 7. Generic API keys and passwords in assignments or query parameters
        (
            re.compile(
                r"((?:api[_-]?key|password|access[_-]?token|auth[_-]?token)\s*[:=]\s*['\"]?)([^\s'\"&,;]+)(['\"]?)",
                re.IGNORECASE,
            ),
            r"\1[REDACTED]\3",
        ),
        # 8. Multiline PEM Private Keys (RSA, EC, OPENSSH, DSA, ENCRYPTED)
        (
            re.compile(r"-----BEGIN [A-Z ]+ PRIVATE KEY-----[\s\S]*?-----END [A-Z ]+ PRIVATE KEY-----"),
            "[REDACTED_PRIVATE_KEY]",
        ),
    ]

    SENSITIVE_KEY_ROOTS = {
        "password",
        "secret",
        "token",
        "apikey",
        "authorization",
        "privatekey",
        "accesskey",
    }

    @classmethod
    def redact_text(cls, text: str) -> str:
        """Redact sensitive patterns from arbitrary text while preserving hashes/UUIDs."""
        if not isinstance(text, str):
            return str(text) if text is not None else ""
        if not text:
            return ""

        redacted = text
        for pattern, replacement in cls.PATTERNS:
            redacted = pattern.sub(replacement, redacted)
        return redacted

    @classmethod
    def redact_json(cls, data: Any) -> Any:
        """Recursively redact dictionary and list data structures."""
        if data is None:
            return None
        if isinstance(data, (int, float, bool)):
            return data
        if isinstance(data, str):
            return cls.redact_text(data)

        if isinstance(data, dict):
            new_dict: Dict[str, Any] = {}
            for k, v in data.items():
                k_norm = str(k).lower().replace("_", "").replace("-", "")
                if any(sk in k_norm for sk in cls.SENSITIVE_KEY_ROOTS):
                    new_dict[k] = "[REDACTED]"
                else:
                    new_dict[k] = cls.redact_json(v)
            return new_dict

        if isinstance(data, list):
            return [cls.redact_json(item) for item in data]

        return data
```

---

### 4.2 Append-Only Cryptographic Audit Trail (`services/control-plane/src/plaq_control_plane/audit.py`)

#### Design Specification
The `audit.py` module delivers:
1. `AuditIntegrityError`: Custom exception raised when chain validation detects tampering.
2. `AuditChainer`: Cryptographic hashing helper with `compute_record_hash` and `verify_chain`.
3. `AuditEntry`: Structured representation of a persisted audit log row.
4. `AuditTrailManager`: High-level manager providing `record_audit`, `get_trail`, and `verify_audit_trail` against SQLite.

#### Proposed Code for `services/control-plane/src/plaq_control_plane/audit.py`
```python
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

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

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

        with self.conn:
            cursor = self.conn.execute(
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

            self.conn.execute(
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

        cursor = self.conn.execute("SELECT * FROM audit_trail WHERE id = ?", (entry_id,))
        row = cursor.fetchone()
        return dict(row)

    def get_audit_trail(self, task_id: str) -> List[Dict[str, Any]]:
        """Retrieve full chronological audit trail for a task."""
        cursor = self.conn.execute(
            "SELECT * FROM audit_trail WHERE task_id = ? ORDER BY sequence_number ASC",
            (task_id,),
        )
        return [dict(r) for r in cursor.fetchall()]

    def verify_audit_trail(self, task_id: str) -> bool:
        """Verify the integrity of the audit log for a given task."""
        records = self.get_audit_trail(task_id)
        return AuditChainer.verify_chain(records)
```

---

### 4.3 Content-Addressable Artifact Service (`services/artifact-service/src/plaq_artifacts/service.py`)

#### Design Specification
The `service.py` module delivers:
1. `ArtifactType`: Enum of standard artifact types (`quantum_pareto`, `quantum_manifest`, `benchmark_csv`, `report`, `diff`, `code_patch`, `log`).
2. `ArtifactRecord`: Pydantic/dataclass model tracking artifact metadata.
3. `ArtifactService`:
   - Saves file content in content-addressable storage (`storage_root/<sha256[:2]>/<sha256[2:]>.<ext>` or directory structure).
   - Generates SHA-256 fingerprint and size metadata.
   - Persists metadata to SQLite `artifacts` table.
   - Emits `artifact_published` events.
   - Reads, streams, and verifies file content integrity against the stored digest.

#### Proposed Code for `services/artifact-service/src/plaq_artifacts/service.py`
```python
"""Plaq-OS Artifact Service.

Provides content-addressable storage (CAS), cryptographic SHA-256 fingerprinting,
metadata registration, task record linkage, and integrity verification for
quantum run manifests, Pareto reports, diffs, and benchmark data.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union


class ArtifactIntegrityError(ValueError):
    """Raised when an artifact's content does not match its expected SHA-256 hash."""
    pass


class ArtifactNotFoundError(KeyError):
    """Raised when the requested artifact record or content file does not exist."""
    pass


class ArtifactType(str, Enum):
    QUANTUM_PARETO = "quantum_pareto"
    QUANTUM_MANIFEST = "quantum_manifest"
    BENCHMARK_CSV = "benchmark_csv"
    REPORT = "report"
    DIFF = "diff"
    CODE_PATCH = "code_patch"
    LOG = "log"
    GENERIC = "generic"


@dataclass
class ArtifactRecord:
    id: str
    task_id: str
    artifact_type: str
    name: str
    file_path: str
    sha256_hash: str
    size_bytes: int
    created_at: str
    metadata: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if isinstance(d.get("metadata"), dict):
            d["metadata"] = json.dumps(d["metadata"])
        return d


class ArtifactService:
    """Content-addressable artifact storage and control plane tracking."""

    def __init__(
        self,
        storage_dir: Union[str, Path],
        conn: Optional[sqlite3.Connection] = None,
        event_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ):
        self.storage_dir = Path(storage_dir).resolve()
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.conn = conn
        self.event_callback = event_callback

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
        # Store in <storage_dir>/tasks/<task_id>/<name> or CAS <storage_dir>/objects/<hash[:2]>/<hash>
        target_dir = self.storage_dir / "tasks" / task_id
        target_dir.mkdir(parents=True, exist_ok=True)
        dest_path = target_dir / name

        # Atomic file write via temp file
        temp_dest = dest_path.with_suffix(".tmp")
        temp_dest.write_bytes(raw_bytes)
        temp_dest.replace(dest_path)

        # 4. Create database record
        artifact_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        type_str = artifact_type.value if isinstance(artifact_type, ArtifactType) else str(artifact_type)
        metadata_json = json.dumps(metadata) if metadata is not None else None

        record = ArtifactRecord(
            id=artifact_id,
            task_id=task_id,
            artifact_type=type_str,
            name=name,
            file_path=str(dest_path),
            sha256_hash=sha256_hash,
            size_bytes=size_bytes,
            created_at=now,
            metadata=metadata,
        )

        if self.conn is not None:
            with self.conn:
                self.conn.execute(
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
        if self.conn is None:
            raise RuntimeError("Database connection not configured.")
        cursor = self.conn.execute("SELECT * FROM artifacts WHERE id = ?", (artifact_id,))
        row = cursor.fetchone()
        if not row:
            return None
        row_dict = dict(row)
        meta = json.loads(row_dict["metadata"]) if row_dict.get("metadata") else None
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
        if self.conn is None:
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

        cursor = self.conn.execute(query, params)
        records: List[ArtifactRecord] = []
        for r in cursor.fetchall():
            rd = dict(r)
            meta = json.loads(rd["metadata"]) if rd.get("metadata") else None
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
```

---

### 4.4 Packaging & `pyproject.toml` Files

#### `services/control-plane/pyproject.toml`
```toml
[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[project]
name = "plaq-control-plane"
version = "0.3.0"
description = "Plaq-OS Persistent Control Plane, State Engine & Audit Trail"
readme = "README.md"
requires-python = ">=3.10"
dependencies = [
    "pydantic>=2.0.0",
]

[tool.setuptools.packages.find]
where = ["src"]
```

#### `services/artifact-service/pyproject.toml`
```toml
[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[project]
name = "plaq-artifacts"
version = "0.3.0"
description = "Plaq-OS Content-Addressable Artifact Service"
readme = "README.md"
requires-python = ">=3.10"
dependencies = [
    "pydantic>=2.0.0",
]

[tool.setuptools.packages.find]
where = ["src"]
```

---

## 5. Verification Method

### 5.1 Independent Test Commands
To verify the designs against the existing test harness, the implementation workers can execute:
```bash
# 1. Verify Feature 5: Append-Only Audit Trail (5/5 tests)
pytest tests/e2e/test_tier1_feature.py -k "TestFeature05" -v

# 2. Verify Feature 6: Secret Redaction Filter (5/5 tests)
pytest tests/e2e/test_tier1_feature.py -k "TestFeature06" -v

# 3. Verify Boundary Group 5: Secret Redaction Edge Cases (11/11 tests)
pytest tests/e2e/test_tier2_boundary.py -k "TestBoundary05" -v

# 4. Verify Pairwise Group 4: Quantum Pareto Artifact Streaming (5/5 tests)
pytest tests/e2e/test_tier3_pairwise.py -k "TestPairwise04" -v

# 5. Verify Checkpoint Recovery Audit Continuity across Restarts (test_f7_04)
pytest tests/e2e/test_tier1_feature.py -k "test_f7_04" -v

# 6. Verify Full Workload Scenarios 1 & 4 with Audit & Artifact Publishing
pytest tests/e2e/test_tier4_workloads.py -k "test_s1 or test_s4" -v
```

### 5.2 Files to Inspect
- `services/control-plane/src/plaq_control_plane/redact.py`: Ensure all regex patterns and recursive JSON keys match specification.
- `services/control-plane/src/plaq_control_plane/audit.py`: Ensure hash payload format matches `{previous_hash}|{task_id}|{tool_name}|{parameters}|{output}|{exit_code}|{duration_ms:.2f}|{modified_files}`.
- `services/artifact-service/src/plaq_artifacts/service.py`: Ensure content SHA-256 calculation and atomic disk write via temp file replacement.

### 5.3 Invalidation Conditions
- Any change to the order or separator format (`|`) of the hash payload invalidates the chain.
- Omitting the `:.2f` formatting for `duration_ms` causes verification failure against existing E2E fixtures.
- Failing to redact secrets *before* hashing causes tamper false positives or credential leaks.
- Falsely matching 40-character or 64-character hex strings as secrets breaks test `test_b5_03`.
