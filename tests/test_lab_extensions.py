"""Sampler/Estimator, DD+twirl, Pauli frame, repetition, VQE, job bundle, MCP completions."""

from __future__ import annotations

import json
from unittest.mock import patch
import io

from fastapi.testclient import TestClient

from plaq_agent_runtime.registry import ToolContext, create_default_tool_registry
from plaq_api.app import create_app
from plaq_contracts.tool import ToolRequest
from plaq_control_plane.db import DatabaseEngine
from plaq_control_plane.repository import ControlPlaneRepository
from plaq_mcp.server import handle_rpc
from plaq_model_gateway.providers import DeterministicPlanner
from plaq_quantum.bundle import export_bundle
from plaq_quantum.pauli_frame import track_pauli_frame
from plaq_quantum.primitives import run_estimator, run_sampler
from plaq_quantum.repetition import run_repetition_code
from plaq_quantum.suppression import run_suppression
from plaq_quantum.vqe import run_vqe
from plaq_quantum.workloads import resolve_circuit


def test_empty_workload_still_test_circuit():
    qc = resolve_circuit("")
    assert qc.num_qubits == 4


def test_sampler_bell_hits_even_parity():
    res = run_sampler(workload="bell", shots=256, seed=1)
    assert res.num_qubits == 2
    assert res.shots == 256
    assert sum(res.counts.values()) == 256
    even = res.counts.get("00", 0) + res.counts.get("11", 0)
    assert even > 200


def test_estimator_bell_zz_is_one():
    res = run_estimator(workload="bell", observable="ZZ", shots=0)
    assert res.num_qubits == 2
    assert abs(res.expectation - 1.0) < 1e-9


def test_suppression_reports_dd_depth():
    res = run_suppression(workload="bell", twirl_randomizations=2, p2=0.05, observable="ZZ")
    assert res.dd_depth >= res.original_depth
    assert isinstance(res.improved, bool)
    assert res.twirl_randomizations == 2


def test_pauli_frame_counts_twoq():
    report = track_pauli_frame(workload="qft", qubits=4, code_distance=3)
    assert report.logical_qubits == 4
    assert report.two_qubit_gates >= 1
    assert report.frame_updates >= report.two_qubit_gates
    assert "d3" in report.cycles_if_d


def test_repetition_logical_beats_physical():
    res = run_repetition_code(distance=3, physical_error=0.1, shots=4000, seed=0)
    assert res.distance == 3
    assert res.logical_error_rate < res.physical_error
    assert 0.0 <= res.logical_error_rate <= 1.0


def test_vqe_h2_returns_energy():
    res = run_vqe(maxiter=12, seed=0, hamiltonian="h2")
    assert len(res.parameters) == 4
    assert res.energy < 0.0
    assert res.exact_diagonal is not None
    assert res.exact_diagonal < 0.0
    assert res.iterations >= 1


def test_job_bundle_emits_qasm():
    bundle = export_bundle(workload="bell", hardware_profile="superconducting")
    assert bundle.num_qubits == 2
    assert "OPENQASM" in bundle.qasm2
    assert bundle.version
    assert bundle.depth >= 1


def test_planner_new_keywords_do_not_break_bv_or_chemistry():
    p = DeterministicPlanner()
    bv = p.generate_plan("Bernstein-Vazirani hidden string 101", task_id="t")
    assert [s.tool_name for s in bv] == ["quantum.compile", "quantum.estimate", "artifacts.publish"]
    chem = p.generate_plan("Run a molecular VQE FeMoCo ansatz", task_id="t")
    assert chem[0].tool_name == "quantum.compile"
    assert chem[0].tool_parameters.get("workload") == "chemistry"
    hea = p.generate_plan("Run a hardware-efficient toy H2 ansatz", task_id="t")
    assert any(s.tool_name == "quantum.vqe" for s in hea)
    samp = p.generate_plan("Collect a sampler primitive shot distribution", task_id="t")
    assert samp[0].tool_name == "quantum.sampler"
    est = p.generate_plan("Compute a Pauli observable expectation value", task_id="t")
    assert any(s.tool_name == "quantum.estimator" for s in est)
    dd = p.generate_plan("Apply dynamical decoupling XpXm and a Pauli twirl", task_id="t")
    assert dd[0].tool_name == "quantum.suppress"
    frame = p.generate_plan("Track the Pauli frame of a logical circuit", task_id="t")
    assert frame[0].tool_name == "quantum.frame"
    rep = p.generate_plan("Simulate a repetition code without Stim", task_id="t")
    assert rep[0].tool_name == "quantum.repetition"
    bundle = p.generate_plan("Export a QASM3 job bundle", task_id="t")
    assert bundle[0].tool_name == "quantum.bundle"
    pareto = p.generate_plan("Run a Pareto QEC optimization", task_id="t")
    assert pareto[2].tool_name == "quantum.simulate"


def test_new_tools_registered_and_run():
    registry = create_default_tool_registry()
    tier = registry.get_tier_map()
    assert len(tier) >= 12
    for name in (
        "quantum.sampler",
        "quantum.estimator",
        "quantum.suppress",
        "quantum.vqe",
        "quantum.frame",
        "quantum.repetition",
        "quantum.bundle",
        "quantum.draw",
        "quantum.simulate",
    ):
        assert tier[name] == "quantum_engine"
    ctx = ToolContext(workspace_path=".", task_id="lab2")
    samp = registry.execute(
        ToolRequest(tool_name="quantum.sampler", parameters={"workload": "bell", "shots": 64}, task_id="lab2"),
        ctx,
    )
    assert samp.success is True
    frame = registry.execute(
        ToolRequest(tool_name="quantum.frame", parameters={"workload": "qft", "qubits": 3}, task_id="lab2"),
        ctx,
    )
    assert frame.success is True
    rep = registry.execute(
        ToolRequest(tool_name="quantum.repetition", parameters={"distance": 3, "shots": 200}, task_id="lab2"),
        ctx,
    )
    assert rep.success is True


def test_cli_sampler_and_repetition():
    from plaq_cli.main import main

    buf = io.StringIO()
    with patch("sys.stdout", buf):
        rc = main(["quantum", "sampler", "bell", "--shots", "32"])
    assert rc == 0
    data = json.loads(buf.getvalue())
    assert data["num_qubits"] == 2
    assert data["shots"] == 32

    buf2 = io.StringIO()
    with patch("sys.stdout", buf2):
        rc2 = main(["quantum", "repetition", "--distance", "3", "--shots", "200"])
    assert rc2 == 0
    plan = json.loads(buf2.getvalue())
    assert plan["distance"] == 3


def test_mcp_new_tools_and_structured_content():
    listed = handle_rpc({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    names = {t["name"] for t in listed["result"]["tools"]}
    for name in (
        "quantum_sampler",
        "quantum_estimator",
        "quantum_suppress",
        "quantum_vqe",
        "quantum_frame",
        "quantum_repetition",
        "quantum_bundle",
    ):
        assert name in names

    reply = handle_rpc(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "quantum_estimator", "arguments": {"workload": "bell", "observable": "ZZ"}},
        }
    )
    body = reply["result"]
    assert body["isError"] is False
    assert "structuredContent" in body
    assert abs(body["structuredContent"]["expectation"] - 1.0) < 1e-9
    parsed = json.loads(body["content"][0]["text"])
    assert parsed["num_qubits"] == 2

    samp = handle_rpc(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "quantum_sampler", "arguments": {"workload": "bell", "shots": 32}},
        }
    )
    assert samp["result"]["structuredContent"]["shots"] == 32

    bundle = handle_rpc(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "quantum_bundle", "arguments": {"workload": "bell"}},
        }
    )
    assert "OPENQASM" in bundle["result"]["structuredContent"]["qasm2"]


def test_mcp_completion_complete():
    init = handle_rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert "completions" in init["result"]["capabilities"]

    reply = handle_rpc(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "completion/complete",
            "params": {
                "ref": {"type": "ref/prompt", "name": "ftqc_estimate"},
                "argument": {"name": "workload", "value": "be"},
            },
        }
    )
    values = reply["result"]["completion"]["values"]
    assert any(v.lower().startswith("be") or "bell" in v.lower() for v in values)

    hw = handle_rpc(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "completion/complete",
            "params": {
                "ref": {"type": "ref/tool", "name": "quantum_bundle"},
                "argument": {"name": "hardware_profile", "value": "sup"},
            },
        }
    )
    assert "superconducting" in hw["result"]["completion"]["values"]


def test_api_new_endpoints_and_workspace_tree(tmp_path, monkeypatch):
    (tmp_path / "hello.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "a.txt").write_text("a", encoding="utf-8")
    monkeypatch.setenv("PLAQ_WORKSPACE", str(tmp_path))
    engine = DatabaseEngine(str(tmp_path / "api.db"))
    repo = ControlPlaneRepository(engine)
    try:
        app = create_app(repository=repo)
        with TestClient(app) as client:
            samp = client.post("/api/v1/quantum/sampler", json={"workload": "bell", "shots": 32})
            assert samp.status_code == 200
            assert samp.json()["num_qubits"] == 2
            est = client.post("/api/v1/quantum/estimator", json={"workload": "bell", "observable": "ZZ"})
            assert est.status_code == 200
            assert abs(est.json()["expectation"] - 1.0) < 1e-9
            frame = client.post("/api/v1/quantum/frame", json={"workload": "qft", "qubits": 3})
            assert frame.status_code == 200
            assert frame.json()["logical_qubits"] == 3
            tree = client.get("/api/v1/workspace/tree")
            assert tree.status_code == 200
            names = {e["name"] for e in tree.json()["entries"]}
            assert "hello.py" in names
            assert "sub" in names
            bad = client.get("/api/v1/workspace/tree", params={"path": "../"})
            assert bad.status_code == 400
    finally:
        repo.close()
