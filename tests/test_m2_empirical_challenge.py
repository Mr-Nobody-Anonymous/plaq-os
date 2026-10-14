"""Adversarial Empirical Stress Tests for Milestone M2: Cryptographic Audit & Recovery.

Authored by Challenger M2-2 (critic, specialist).
Empirically verifies:
1. Audit Tamper Detection (all failure modes and corruption vectors in hash chain)
2. Secret Redactor Rigor & False Positive Resistance (tokens scrubbed, UUIDs/git hashes preserved)
3. Checkpoint Recovery across all in-flight task states (running, planning, verifying, blocked)
4. Content-addressable Artifact Integrity (bit-flips, missing files, corrupted DB hashes)
"""

import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import uuid
import pytest

from plaq_contracts import ArtifactType, TaskStatus
from plaq_control_plane import (
    AuditChainer,
    AuditTrailManager,
    CheckpointRecoveryManager,
    ControlPlaneRepository,
    DatabaseEngine,
    InvalidStateTransitionError,
    SecretRedactor,
    TaskStateMachine,
)
from plaq_artifacts import (
    ArtifactIntegrityError,
    ArtifactNotFoundError,
    ArtifactRecord,
    ArtifactService,
)


# ===========================================================================
# Fixtures
# ===========================================================================

@pytest.fixture
def disk_db():
    """Create an isolated SQLite database backed by real disk with WAL mode."""
    fd, path = tempfile.mkstemp(prefix="plaq_m2_stress_", suffix=".db")
    os.close(fd)
    engine = DatabaseEngine(path)
    repo = ControlPlaneRepository(engine)
    yield repo, engine, path
    engine.close()
    for ext in ("", "-wal", "-shm"):
        try:
            os.unlink(path + ext)
        except Exception:
            pass


@pytest.fixture
def artifact_disk_env():
    """Create an isolated disk storage directory and SQLite repo for artifact testing."""
    tmp_dir = tempfile.mkdtemp(prefix="plaq_m2_artifacts_")
    fd, db_path = tempfile.mkstemp(prefix="plaq_m2_art_db_", suffix=".db")
    os.close(fd)
    engine = DatabaseEngine(db_path)
    repo = ControlPlaneRepository(engine)
    task = repo.create_task("Artifact Stress Test Task")
    service = ArtifactService(storage_dir=tmp_dir, conn=engine.conn)
    yield service, task["id"], tmp_dir, engine, db_path
    engine.close()
    for ext in ("", "-wal", "-shm"):
        try:
            os.unlink(db_path + ext)
        except Exception:
            pass


# ===========================================================================
# 1. Audit Tamper Detection Stress Tests
# ===========================================================================

class TestAuditTamperDetectionEmpirical:
    """Stress-test AuditChainer and AuditTrailManager under diverse corruption modes."""

    def test_clean_chain_passes_verification(self, disk_db):
        repo, engine, _ = disk_db
        task = repo.create_task("Clean audit test")
        t_id = task["id"]

        for i in range(5):
            repo.record_audit(
                task_id=t_id,
                tool_name=f"tool_{i}",
                parameters={"param_key": f"value_{i}"},
                output=f"Standard output {i}",
                exit_code=0,
                duration_ms=10.5 * (i + 1),
                modified_files=[f"file_{i}.txt"],
            )

        assert repo.verify_audit_trail(t_id) is True

    def test_tamper_middle_record_parameters(self, disk_db):
        """Tampering with parameters in record 3 of 5 must trigger verification failure."""
        repo, engine, _ = disk_db
        task = repo.create_task("Tamper middle record")
        t_id = task["id"]

        records = []
        for i in range(5):
            r = repo.record_audit(
                task_id=t_id,
                tool_name=f"step_{i}",
                parameters={"step": i},
                output=f"out_{i}",
            )
            records.append(r)

        # Directly tamper parameters of record 3 (sequence_number 3)
        with engine.conn:
            engine.conn.execute(
                "UPDATE audit_trail SET parameters = ? WHERE id = ?",
                (json.dumps({"tampered": True}), records[2]["id"]),
            )

        assert repo.verify_audit_trail(t_id) is False

    def test_tamper_previous_hash_link(self, disk_db):
        """Tampering with previous_hash breaks the cryptographic chain."""
        repo, engine, _ = disk_db
        task = repo.create_task("Tamper prev_hash")
        t_id = task["id"]

        records = [
            repo.record_audit(task_id=t_id, tool_name="t1", parameters={}, output="o1"),
            repo.record_audit(task_id=t_id, tool_name="t2", parameters={}, output="o2"),
            repo.record_audit(task_id=t_id, tool_name="t3", parameters={}, output="o3"),
        ]

        # Corrupt previous_hash of record 2
        with engine.conn:
            engine.conn.execute(
                "UPDATE audit_trail SET previous_hash = ? WHERE id = ?",
                ("f" * 64, records[1]["id"]),
            )

        assert repo.verify_audit_trail(t_id) is False

    def test_tamper_current_hash(self, disk_db):
        """Forging current_hash without changing data must fail."""
        repo, engine, _ = disk_db
        task = repo.create_task("Tamper current_hash")
        t_id = task["id"]

        r = repo.record_audit(task_id=t_id, tool_name="t1", parameters={}, output="o1")
        with engine.conn:
            engine.conn.execute(
                "UPDATE audit_trail SET current_hash = ? WHERE id = ?",
                ("e" * 64, r["id"]),
            )

        assert repo.verify_audit_trail(t_id) is False

    def test_tamper_sequence_number_gap(self, disk_db):
        """Sequence gap (e.g. 1 -> 3) must be unequivocally detected as corruption."""
        repo, engine, _ = disk_db
        task = repo.create_task("Sequence gap")
        t_id = task["id"]

        r1 = repo.record_audit(task_id=t_id, tool_name="t1", parameters={}, output="o1")
        r2 = repo.record_audit(task_id=t_id, tool_name="t2", parameters={}, output="o2")

        with engine.conn:
            engine.conn.execute("UPDATE audit_trail SET sequence_number = 3 WHERE id = ?", (r2["id"],))

        assert repo.verify_audit_trail(t_id) is False

    def test_tamper_record_deletion_middle(self, disk_db):
        """Deleting an intermediate record creates a hash mismatch between preceding and subsequent records."""
        repo, engine, _ = disk_db
        task = repo.create_task("Record deletion")
        t_id = task["id"]

        r1 = repo.record_audit(task_id=t_id, tool_name="t1", parameters={}, output="o1")
        r2 = repo.record_audit(task_id=t_id, tool_name="t2", parameters={}, output="o2")
        r3 = repo.record_audit(task_id=t_id, tool_name="t3", parameters={}, output="o3")

        # Delete middle record
        with engine.conn:
            engine.conn.execute("DELETE FROM audit_trail WHERE id = ?", (r2["id"],))

        assert repo.verify_audit_trail(t_id) is False

    def test_tamper_genesis_hash(self, disk_db):
        """First record must strictly chain from 64 zeros; non-zero genesis hash must fail."""
        repo, engine, _ = disk_db
        task = repo.create_task("Genesis tamper")
        t_id = task["id"]

        r1 = repo.record_audit(task_id=t_id, tool_name="t1", parameters={}, output="o1")
        with engine.conn:
            engine.conn.execute(
                "UPDATE audit_trail SET previous_hash = ? WHERE id = ?",
                ("1" * 64, r1["id"]),
            )

        assert repo.verify_audit_trail(t_id) is False

    def test_tamper_exit_code_and_duration(self, disk_db):
        """Tampering with exit_code or duration_ms alters record hash."""
        repo, engine, _ = disk_db
        task = repo.create_task("Exit code tamper")
        t_id = task["id"]

        r = repo.record_audit(
            task_id=t_id,
            tool_name="t1",
            parameters={},
            output="o1",
            exit_code=0,
            duration_ms=12.34,
        )

        with engine.conn:
            engine.conn.execute("UPDATE audit_trail SET exit_code = 1 WHERE id = ?", (r["id"],))

        assert repo.verify_audit_trail(t_id) is False

    def test_tamper_modified_files(self, disk_db):
        """Tampering with modified_files list alters record hash."""
        repo, engine, _ = disk_db
        task = repo.create_task("Modified files tamper")
        t_id = task["id"]

        r = repo.record_audit(
            task_id=t_id,
            tool_name="t1",
            parameters={},
            output="o1",
            modified_files=["safe.txt"],
        )

        with engine.conn:
            engine.conn.execute(
                "UPDATE audit_trail SET modified_files = ? WHERE id = ?",
                (json.dumps(["malicious.sh"]), r["id"]),
            )

        assert repo.verify_audit_trail(t_id) is False

    def test_audit_empty_and_single_entry(self, disk_db):
        """Empty trail passes trivially; single clean entry passes."""
        repo, engine, _ = disk_db
        task = repo.create_task("Empty task")
        assert repo.verify_audit_trail(task["id"]) is True

        repo.record_audit(task["id"], "t0", {}, "clean")
        assert repo.verify_audit_trail(task["id"]) is True


# ===========================================================================
# 2. Secret Redactor Rigor & False Positive Resistance
# ===========================================================================

class TestSecretRedactorRigorEmpirical:
    """Stress-test SecretRedactor across diverse secret formats and false-positive guards."""

    def test_bearer_token_variations(self):
        cases = [
            ("Authorization: Bearer my-jwt-token.part2.part3", "Authorization: Bearer [REDACTED_TOKEN]"),
            ("bearer 99887766554433221100", "Bearer [REDACTED_TOKEN]"),
            ("Bearer    token_with_spaces", "Bearer [REDACTED_TOKEN]"),
        ]
        for raw, expected in cases:
            res = SecretRedactor.redact_text(raw)
            assert "[REDACTED_TOKEN]" in res
            assert "my-jwt-token" not in res
            assert "99887766554433221100" not in res

    def test_github_tokens(self):
        classic_pat = "gh" + "p_AbCdEfGhIjKlMnOpQrStUvWxYz0123456789"
        fine_grained = "github_" + "pat_11AAAAAAA_99887766554433221100aabbccddeeffgghhiijjkkllmmnnooppqq"
        raw = f"Cloning with {classic_pat} and {fine_grained}"
        redacted = SecretRedactor.redact_text(raw)
        assert classic_pat not in redacted
        assert fine_grained not in redacted
        assert "[REDACTED_GH_TOKEN]" in redacted

    def test_slack_tokens(self):
        slack_tokens = [
            ("xox" + "b-123456789012-1234567890123-abcdefghijklmnopqrstuvwx"),
            ("xox" + "p-123456789012-1234567890123-abcdefghijklmnopqrstuvwx"),
            ("xox" + "a-123456789012-1234567890123-abcdefghijklmnopqrstuvwx"),
            ("xox" + "r-123456789012-1234567890123-abcdefghijklmnopqrstuvwx"),
            ("xox" + "s-123456789012-1234567890123-abcdefghijklmnopqrstuvwx"),
        ]
        for tok in slack_tokens:
            res = SecretRedactor.redact_text(f"Token is {tok}")
            assert tok not in res
            assert "[REDACTED_SLACK_TOKEN]" in res

    def test_aws_credentials(self):
        access_keys = [
            "AKIAIOSFODNN7EXAMPLE",
            "ASIAIOSFODNN7EXAMPLE",
            "ABIAIOSFODNN7EXAMPLE",
            "ACCAIOSFODNN7EXAMPLE",
        ]
        for key in access_keys:
            res = SecretRedactor.redact_text(f"aws_access_key_id={key}")
            assert key not in res
            assert "[REDACTED_AWS_KEY]" in res

        secret_key_line = "aws_secret_access_key = wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
        res2 = SecretRedactor.redact_text(secret_key_line)
        assert "wJalrXUtnFEMI" not in res2
        assert "[REDACTED_SECRET_KEY]" in res2

    def test_pem_private_keys(self):
        pem_keys = [
            "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA0Y1Wd8VvR7...fake...key...content...\n-----END RSA PRIVATE KEY-----",
            "-----BEGIN OPENSSH PRIVATE KEY-----\nb3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAABAAABlwAAAAdzc2gtcn\n-----END OPENSSH PRIVATE KEY-----",
            "-----BEGIN EC PRIVATE KEY-----\nMHcCAQEEIIzQ...fake...\n-----END EC PRIVATE KEY-----",
        ]
        for pem in pem_keys:
            res = SecretRedactor.redact_text(pem)
            assert "-----BEGIN" not in res
            assert "[REDACTED_PRIVATE_KEY]" in res

    def test_basic_auth_in_urls(self):
        url = "https://admin:super_secret_pass@api.quantum.internal:8080/v1/jobs"
        redacted = SecretRedactor.redact_text(url)
        assert "super_secret_pass" not in redacted
        assert "https://admin:[REDACTED]@api.quantum.internal:8080/v1/jobs" == redacted

    def test_json_sensitive_keys_recursive(self):
        nested = {
            "api_key": "live_12345",
            "db": {
                "PASSWORD": "root_password",
                "SecretToken": "sec_val",
                "normal": "preserve_me",
            },
            "list": [
                {"private_key_path": "/etc/ssl/key.pem", "privatekey": "-----BEGIN..."},
                {"regular_item": 42},
            ],
        }
        res = SecretRedactor.redact_json(nested)
        assert res["api_key"] == "[REDACTED]"
        assert res["db"]["PASSWORD"] == "[REDACTED]"
        assert res["db"]["SecretToken"] == "[REDACTED]"
        assert res["db"]["normal"] == "preserve_me"
        assert res["list"][0]["privatekey"] == "[REDACTED]"
        assert res["list"][1]["regular_item"] == 42

    def test_legitimate_uuids_not_mangled(self):
        """Crucial false positive test: UUIDs must NOT be redacted or corrupted."""
        sample_uuids = [
            str(uuid.uuid4()),
            "550e8400-e29b-41d4-a716-446655440000",
            "c9a646d3-9c61-4cd9-bc15-4dda270d6116",
        ]
        for u in sample_uuids:
            text = f"Task created with id {u} successfully."
            redacted = SecretRedactor.redact_text(text)
            assert u in redacted
            assert "[REDACTED" not in redacted

    def test_legitimate_git_hashes_and_sha256_not_mangled(self):
        """Crucial false positive test: 40-char git commit SHAs and 64-char SHA-256 strings must NOT be redacted."""
        git_sha = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
        sha256_hash = hashlib.sha256(b"quantum test circuit").hexdigest()

        text = f"Commit {git_sha} produced artifact {sha256_hash}"
        redacted = SecretRedactor.redact_text(text)
        assert git_sha in redacted
        assert sha256_hash in redacted
        assert "[REDACTED" not in redacted

    def test_mixed_secrets_and_legitimate_hashes(self):
        """Verify that when a string contains BOTH a secret AND a valid hash, only the secret is redacted."""
        secret_token = "gh" + "p_123456789012345678901234567890123456"
        valid_sha = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        text = f"Using token {secret_token} to verify commit {valid_sha}"

        redacted = SecretRedactor.redact_text(text)
        assert secret_token not in redacted
        assert "[REDACTED_GH_TOKEN]" in redacted
        assert valid_sha in redacted


# ===========================================================================
# 3. Checkpoint Recovery Across In-Flight States
# ===========================================================================

class TestCheckpointRecoveryEmpirical:
    """Stress-test CheckpointRecoveryManager across process crash and restarts."""

    def test_recovery_across_all_active_states(self, disk_db):
        repo, engine, db_path = disk_db

        # 1. Setup tasks across all states
        t_queued = repo.create_task("Queued task")

        t_planning = repo.create_task("Planning task")
        repo.transition_task(t_planning["id"], "planning")

        t_running = repo.create_task("Running task")
        repo.transition_task(t_running["id"], "planning")
        repo.transition_task(t_running["id"], "running")
        step_running = repo.record_step(t_running["id"], 1, "Execute T-synthesis", "T-count <= 100")
        repo.record_audit(t_running["id"], "quantum.compile", {"qubits": 4}, "Success")

        t_verifying = repo.create_task("Verifying task")
        repo.transition_task(t_verifying["id"], "planning")
        repo.transition_task(t_verifying["id"], "running")
        repo.transition_task(t_verifying["id"], "verifying")

        t_blocked = repo.create_task("Blocked task")
        repo.transition_task(t_blocked["id"], "planning")
        repo.transition_task(t_blocked["id"], "running")
        app = repo.request_approval(
            t_blocked["id"],
            "terminal.run",
            {"cmd": "rm -rf tmp/"},
            "Critical deletion",
        )

        # Terminal tasks
        t_completed = repo.create_task("Completed task")
        repo.transition_task(t_completed["id"], "planning")
        repo.transition_task(t_completed["id"], "running")
        repo.transition_task(t_completed["id"], "verifying")
        repo.transition_task(t_completed["id"], "completed")

        t_failed = repo.create_task("Failed task")
        repo.transition_task(t_failed["id"], "planning")
        repo.transition_task(t_failed["id"], "running")
        repo.transition_task(t_failed["id"], "failed", error="Execution timeout")

        t_cancelled = repo.create_task("Cancelled task")
        repo.transition_task(t_cancelled["id"], "cancelled")

        # 2. Simulate abrupt process termination
        engine.close()

        # 3. Recover in a new database engine and recovery manager
        new_engine = DatabaseEngine(db_path)
        new_repo = ControlPlaneRepository(new_engine)
        recovery = CheckpointRecoveryManager(new_repo)

        active = recovery.scan_active_tasks()
        active_ids = {t["id"] for t in active}

        # Expected active in-flight
        assert t_queued["id"] in active_ids
        assert t_planning["id"] in active_ids
        assert t_running["id"] in active_ids
        assert t_verifying["id"] in active_ids
        assert t_blocked["id"] in active_ids

        # Expected terminal excluded
        assert t_completed["id"] not in active_ids
        assert t_failed["id"] not in active_ids
        assert t_cancelled["id"] not in active_ids

        # 4. Rehydrate each active task and verify contexts
        ctx_queued = recovery.rehydrate_task(t_queued["id"])
        assert ctx_queued.status == "queued"
        assert ctx_queued.recommended_action == "dispatch_to_planner"

        ctx_planning = recovery.rehydrate_task(t_planning["id"])
        assert ctx_planning.status == "planning"
        assert ctx_planning.recommended_action == "resume_planning"

        ctx_running = recovery.rehydrate_task(t_running["id"])
        assert ctx_running.status == "running"
        assert ctx_running.recommended_action == "resume_current_step"
        assert ctx_running.current_step is not None
        assert ctx_running.current_step["id"] == step_running["id"]
        assert len(ctx_running.last_audit_hash) == 64
        assert ctx_running.last_sequence_number == 1

        ctx_verifying = recovery.rehydrate_task(t_verifying["id"])
        assert ctx_verifying.status == "verifying"
        assert ctx_verifying.recommended_action == "rerun_verification"

        ctx_blocked = recovery.rehydrate_task(t_blocked["id"])
        assert ctx_blocked.status == "blocked"
        assert ctx_blocked.recommended_action == "await_human_approval"
        assert ctx_blocked.pending_approval is not None
        assert ctx_blocked.pending_approval["id"] == app["id"]

        # 5. Verify audit continuity post-recovery
        r_post = new_repo.record_audit(
            t_running["id"],
            "quantum.estimate",
            {"distance": 5},
            "Estimated 100 qubits",
        )
        assert r_post["sequence_number"] == 2
        assert r_post["previous_hash"] == ctx_running.last_audit_hash
        assert new_repo.verify_audit_trail(t_running["id"]) is True

        new_engine.close()


# ===========================================================================
# 4. Artifact Integrity & Content-Addressable Storage Stress Tests
# ===========================================================================

class TestArtifactIntegrityEmpirical:
    """Stress-test ArtifactService against content corruption, missing files, and tampered hashes."""

    def test_publish_and_verify_valid_artifacts(self, artifact_disk_env):
        service, task_id, _, _, _ = artifact_disk_env

        # Text artifact
        text_rec = service.publish_artifact(
            task_id=task_id,
            artifact_type=ArtifactType.REPORT,
            name="pareto_summary.json",
            content=json.dumps({"pareto_points": 5, "optimal_distance": 7}),
        )
        assert service.verify_artifact_integrity(text_rec.id) is True
        assert json.loads(service.read_artifact_text(text_rec.id))["pareto_points"] == 5

        # Binary artifact
        bin_data = b"\x00\x01\x02\xff\xfe\xfd\xaa\x55" * 128
        bin_rec = service.publish_artifact(
            task_id=task_id,
            artifact_type=ArtifactType.MANIFEST,
            name="circuit_binary.stim",
            content=bin_data,
        )
        assert service.verify_artifact_integrity(bin_rec.id) is True
        assert service.read_artifact_bytes(bin_rec.id) == bin_data

    def test_bitflip_tamper_detection(self, artifact_disk_env):
        """Modifying even 1 byte in stored file raises ArtifactIntegrityError."""
        service, task_id, _, _, _ = artifact_disk_env

        rec = service.publish_artifact(
            task_id=task_id,
            artifact_type=ArtifactType.DIFF,
            name="patch_core.diff",
            content="--- a/circuits.py\n+++ b/circuits.py\n@@ -1,3 +1,3 @@\n-def test():\n+def test_mod():\n",
        )

        file_path = Path(rec.file_path)
        content = bytearray(file_path.read_bytes())
        # Flip first byte
        content[0] ^= 0xFF
        file_path.write_bytes(content)

        assert service.verify_artifact_integrity(rec.id) is False
        with pytest.raises(ArtifactIntegrityError, match="hash mismatch"):
            service.read_artifact_bytes(rec.id)

    def test_missing_file_detection(self, artifact_disk_env):
        """Deleting the physical artifact file raises ArtifactNotFoundError."""
        service, task_id, _, _, _ = artifact_disk_env

        rec = service.publish_artifact(
            task_id=task_id,
            artifact_type=ArtifactType.REPORT,
            name="deleted_test.txt",
            content="Content to be deleted.",
        )

        file_path = Path(rec.file_path)
        file_path.unlink()

        assert service.verify_artifact_integrity(rec.id) is False
        with pytest.raises(ArtifactNotFoundError, match="missing from storage"):
            service.read_artifact_bytes(rec.id)

    def test_corrupted_database_stored_hash(self, artifact_disk_env):
        """If the SHA-256 hash in SQLite is altered, reading the artifact raises ArtifactIntegrityError."""
        service, task_id, _, engine, _ = artifact_disk_env

        rec = service.publish_artifact(
            task_id=task_id,
            artifact_type=ArtifactType.REPORT,
            name="forged_hash.txt",
            content="Legitimate file content.",
        )

        # Alter hash in DB table
        with engine.conn:
            engine.conn.execute(
                "UPDATE artifacts SET sha256_hash = ? WHERE id = ?",
                ("0" * 64, rec.id),
            )

        assert service.verify_artifact_integrity(rec.id) is False
        with pytest.raises(ArtifactIntegrityError, match="hash mismatch"):
            service.read_artifact_bytes(rec.id)

    def test_zero_byte_artifact_cas_and_integrity(self, artifact_disk_env):
        """Zero-byte artifact must produce standard empty SHA-256 and verify cleanly."""
        service, task_id, _, _, _ = artifact_disk_env

        rec = service.publish_artifact(
            task_id=task_id,
            artifact_type=ArtifactType.DIFF,
            name="empty.diff",
            content="",
        )
        empty_sha = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        assert rec.sha256_hash == empty_sha
        assert rec.size_bytes == 0
        assert service.verify_artifact_integrity(rec.id) is True
        assert service.read_artifact_bytes(rec.id) == b""


# ===========================================================================
# 5. Advanced Cross-Feature Stress Scenarios
# ===========================================================================

class TestAdvancedCrossFeatureStressEmpirical:
    """Multi-task concurrent isolation and boundary adversarial cases."""

    def test_multi_task_audit_trail_isolation(self, disk_db):
        """Ensure multiple concurrent tasks in the same audit table maintain completely independent hash chains."""
        repo, engine, _ = disk_db
        task1 = repo.create_task("Task 1 audit")
        task2 = repo.create_task("Task 2 audit")

        # Interleaved audit recording
        repo.record_audit(task1["id"], "tool1", {"n": 1}, "out1")
        repo.record_audit(task2["id"], "toolA", {"m": 10}, "outA")
        repo.record_audit(task1["id"], "tool2", {"n": 2}, "out2")
        repo.record_audit(task2["id"], "toolB", {"m": 20}, "outB")

        t1_trail = repo.get_audit_trail(task1["id"])
        t2_trail = repo.get_audit_trail(task2["id"])

        assert len(t1_trail) == 2
        assert len(t2_trail) == 2

        assert t1_trail[0]["sequence_number"] == 1
        assert t1_trail[1]["sequence_number"] == 2
        assert t2_trail[0]["sequence_number"] == 1
        assert t2_trail[1]["sequence_number"] == 2

        # Both independent chains verify
        assert repo.verify_audit_trail(task1["id"]) is True
        assert repo.verify_audit_trail(task2["id"]) is True

        # Tampering with Task 1 does not invalidate Task 2
        with engine.conn:
            engine.conn.execute("UPDATE audit_trail SET output = 'hacked' WHERE id = ?", (t1_trail[0]["id"],))

        assert repo.verify_audit_trail(task1["id"]) is False
        assert repo.verify_audit_trail(task2["id"]) is True

    def test_multi_step_crash_recovery_preserves_active_step(self, disk_db):
        """Task with 3 steps where step 1 is completed and step 2 is running preserves step 2 on restart."""
        repo, engine, db_path = disk_db
        task = repo.create_task("Multi-step task")
        t_id = task["id"]
        repo.transition_task(t_id, "planning")
        repo.transition_task(t_id, "running")

        s1 = repo.record_step(t_id, 1, "Step 1", "Crit 1")
        # Mark step 1 completed
        repo.update_step(s1["id"], status="completed")

        s2 = repo.record_step(t_id, 2, "Step 2", "Crit 2")
        # Step 2 is running and current_step_id points to s2
        assert repo.get_task(t_id)["current_step_id"] == s2["id"]

        engine.close()

        # Reopen
        new_engine = DatabaseEngine(db_path)
        new_repo = ControlPlaneRepository(new_engine)
        recovery = CheckpointRecoveryManager(new_repo)

        ctx = recovery.rehydrate_task(t_id)
        assert ctx.current_step is not None
        assert ctx.current_step["id"] == s2["id"]
        assert len(ctx.all_steps) == 2
        assert ctx.all_steps[0]["status"] == "completed"
        assert ctx.all_steps[1]["status"] == "running"
        new_engine.close()

