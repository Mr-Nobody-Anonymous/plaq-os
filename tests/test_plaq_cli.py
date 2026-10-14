"""Unit and command tests for Plaq-OS Unified CLI."""

import io
import json
import pytest
from unittest.mock import patch

from plaq_cli.main import build_parser, main


class TestCLIParsing:
    """Verifies CLI argument grammar and command group structure."""

    def test_command_groups_registered(self):
        parser = build_parser()
        subparsers_action = next(
            a for a in parser._actions if a.dest == "command"
        )
        registered_commands = set(subparsers_action.choices.keys())
        assert {"task", "quantum", "workspace", "serve"}.issubset(registered_commands)

    def test_task_create_arguments(self):
        parser = build_parser()
        args = parser.parse_args(["task", "create", "Run Simulation", "--workspace", "/tmp/ws", "--json"])
        assert args.command == "task"
        assert args.subcommand == "create"
        assert args.goal == "Run Simulation"
        assert args.workspace == "/tmp/ws"
        assert args.json is True

    def test_task_list_arguments(self):
        parser = build_parser()
        args = parser.parse_args(["task", "list", "--status", "queued", "--json"])
        assert args.command == "task"
        assert args.subcommand == "list"
        assert args.status == "queued"
        assert args.json is True

    def test_quantum_estimate_arguments(self):
        parser = build_parser()
        args = parser.parse_args(["quantum", "estimate", "--qubits", "8", "--depth", "100", "--error-rate", "0.0005"])
        assert args.command == "quantum"
        assert args.subcommand == "estimate"
        assert args.qubits == 8
        assert args.depth == 100
        assert args.error_rate == 0.0005

    def test_workspace_open_arguments(self):
        parser = build_parser()
        args = parser.parse_args(["workspace", "open", "some/path"])
        assert args.command == "workspace"
        assert args.subcommand == "open"
        assert args.path == "some/path"

    def test_serve_arguments(self):
        parser = build_parser()
        args = parser.parse_args(["serve", "--port", "9090", "--host", "0.0.0.0"])
        assert args.command == "serve"
        assert args.port == 9090
        assert args.host == "0.0.0.0"


class TestCLIExecution:
    """Verifies end-to-end execution of CLI commands."""

    def test_task_create_and_list_execution(self, tmp_path, monkeypatch):
        db_path = tmp_path / "cli_test.db"
        monkeypatch.setenv("PLAQ_DB_PATH", str(db_path))

        out_buf = io.StringIO()
        with patch("sys.stdout", out_buf):
            ret = main(["task", "create", "CLI Verification Goal", "--json"])
        assert ret == 0
        created = json.loads(out_buf.getvalue())
        assert created["goal"] == "CLI Verification Goal"
        assert "id" in created

        # List
        out_buf_list = io.StringIO()
        with patch("sys.stdout", out_buf_list):
            ret_list = main(["task", "list", "--json"])
        assert ret_list == 0
        tasks = json.loads(out_buf_list.getvalue())
        assert len(tasks) == 1
        assert tasks[0]["id"] == created["id"]

    def test_quantum_estimate_execution(self):
        out_buf = io.StringIO()
        with patch("sys.stdout", out_buf):
            ret = main(["quantum", "estimate", "--qubits", "4", "--json"])
        assert ret == 0
        data = json.loads(out_buf.getvalue())
        assert data["num_qubits"] == 4
        assert data["code_distance"] >= 3
        assert "estimated_runtime_sec" in data

    def test_quantum_compile_execution(self):
        out_buf = io.StringIO()
        with patch("sys.stdout", out_buf):
            ret = main(["quantum", "compile", "bernstein_vazirani", "--qubits", "4", "--json"])
        assert ret == 0
        data = json.loads(out_buf.getvalue())
        assert data["num_qubits"] == 4
        assert data["depth"] > 0

    def test_workspace_open_nonexistent_returns_error(self, tmp_path):
        bad_dir = tmp_path / "non_existent_folder_xyz"
        ret = main(["workspace", "open", str(bad_dir)])
        assert ret == 1

    def test_workspace_open_valid_directory(self, tmp_path):
        valid_dir = tmp_path / "valid_folder"
        valid_dir.mkdir()
        out_buf = io.StringIO()
        with patch("sys.stdout", out_buf):
            ret = main(["workspace", "open", str(valid_dir)])
        assert ret == 0
        assert "Workspace opened" in out_buf.getvalue()
