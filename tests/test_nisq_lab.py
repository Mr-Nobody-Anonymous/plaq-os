"""NISQ ↔ FTQC lab: noise, mitigation, routing, surgery, new algorithms."""

from __future__ import annotations

import json
from unittest.mock import patch
import io

from plaq_agent_runtime.registry import ToolContext, create_default_tool_registry
from plaq_contracts.tool import ToolRequest
from plaq_model_gateway.providers import DeterministicPlanner
from plaq_quantum.algorithms import make_grover_circuit
from plaq_quantum.mitigation import run_mitigation
from plaq_quantum.noise import run_noisy_simulation
from plaq_quantum.simulation import run_circuit_simulation
from plaq_quantum.surgery import plan_lattice_surgery
from plaq_quantum.transpiler import coupling_edges, route_circuit
from plaq_quantum.visualize import draw_circuit
from plaq_quantum.workloads import resolve_circuit


def test_empty_workload_still_test_circuit():
    qc = resolve_circuit("")
    assert qc.num_qubits == 4


def test_grover_two_qubit_marks_all_ones():
    qc = make_grover_circuit(2)
    res = run_circuit_simulation(qc)
    p11 = res.probabilities.get("11", 0.0)
    assert p11 > 0.9


def test_new_workloads_resolve_and_simulate():
    for name, n in [("bell", 2), ("grover", 2), ("teleport", 3), ("qpe", 3), ("deutsch", 2), ("toffoli", 3)]:
        qc = resolve_circuit(name)
        assert qc.num_qubits == n
        sim = run_circuit_simulation(qc)
        assert sim.num_qubits == n
        assert sim.depth >= 1


def test_noisy_bell_has_positive_tvd():
    res = run_noisy_simulation(workload="bell", shots=2048, p1=0.0, p2=0.05, p_readout=0.0, seed=1)
    assert res.num_qubits == 2
    assert res.total_variation_distance > 0.01
    assert res.survival_probability < 1.0
    assert res.two_qubit_gates >= 1


def test_readout_and_zne_do_not_crash_and_report_improvement_flag():
    mit = run_mitigation(workload="bell", p1=0.0, p2=0.04, p_readout=0.05, observable="success")
    assert mit.num_qubits == 2
    assert 0.0 <= mit.ideal_value <= 1.0
    assert isinstance(mit.improved, bool)
    assert len(mit.scale_factors) == 3
    # Readout inversion should not increase TVD vs the ideal distribution.
    assert mit.readout_tvd is not None
    assert mit.readout_tvd <= mit.unmitigated_tvd + 1e-9


def test_linear_router_inserts_swap_for_nonadjacent_cx():
    from qiskit import QuantumCircuit

    qc = QuantumCircuit(3)
    qc.cx(0, 2)
    routed = route_circuit(qc, topology="linear")
    assert routed.swap_count >= 1
    assert routed.connected is True
    assert routed.routed_cx > routed.original_cx


def test_heavy_hex_coupling_has_skip_links():
    edges = coupling_edges("heavy_hex", 7)
    assert (0, 2) in edges or (2, 0) in edges


def test_surgery_plan_scales_with_distance():
    small = plan_lattice_surgery(workload="qft", qubits=4, code_distance=3)
    big = plan_lattice_surgery(workload="qft", qubits=4, code_distance=5)
    assert small.physical_qubits_total > 0
    assert big.physical_qubits_total > small.physical_qubits_total
    assert small.merge_split_ops == small.cx_count
    assert big.code_distance == 5
    assert "lattice surgery" in " ".join(small.notes).lower() or "Model-based" in small.notes[0]


def test_draw_ascii_contains_qubit_wires():
    drawing = draw_circuit(workload="bell")
    assert drawing.num_qubits == 2
    assert drawing.depth >= 1
    assert "q" in drawing.ascii.lower() or "-" in drawing.ascii
    assert "flowchart" in drawing.mermaid


def test_planner_new_keywords_do_not_break_bv_or_pareto():
    p = DeterministicPlanner()
    bv = p.generate_plan("Bernstein-Vazirani hidden string 101", task_id="t")
    assert [s.tool_name for s in bv] == ["quantum.compile", "quantum.estimate", "artifacts.publish"]
    pareto = p.generate_plan("Run a Pareto QEC optimization", task_id="t")
    assert len(pareto) == 4
    assert pareto[2].tool_name == "quantum.simulate"
    noise = p.generate_plan("Simulate a noisy circuit with depolarizing noise", task_id="t")
    assert any(s.tool_name == "quantum.noise" for s in noise)
    zne = p.generate_plan("Apply zero-noise extrapolation error mitigation", task_id="t")
    assert any(s.tool_name == "quantum.mitigate" for s in zne)
    surg = p.generate_plan("Build a lattice surgery patch layout", task_id="t")
    assert any(s.tool_name == "quantum.surgery" for s in surg)


def test_new_tools_registered_and_run():
    registry = create_default_tool_registry()
    tier = registry.get_tier_map()
    assert len(tier) >= 12
    for name in (
        "quantum.noise",
        "quantum.mitigate",
        "quantum.transpile",
        "quantum.surgery",
        "quantum.draw",
        "quantum.simulate",
        "quantum.run",
    ):
        assert tier[name] == "quantum_engine"
    ctx = ToolContext(workspace_path=".", task_id="lab")
    noise = registry.execute(
        ToolRequest(tool_name="quantum.noise", parameters={"workload": "bell", "shots": 128}, task_id="lab"),
        ctx,
    )
    assert noise.success is True
    draw = registry.execute(
        ToolRequest(tool_name="quantum.draw", parameters={"workload": "bell"}, task_id="lab"),
        ctx,
    )
    assert draw.success is True


def test_cli_noise_and_surgery():
    from plaq_cli.main import main

    buf = io.StringIO()
    with patch("sys.stdout", buf):
        rc = main(["quantum", "noise", "bell", "--shots", "64"])
    assert rc == 0
    data = json.loads(buf.getvalue())
    assert data["num_qubits"] == 2

    buf2 = io.StringIO()
    with patch("sys.stdout", buf2):
        rc2 = main(["quantum", "surgery", "qft", "--qubits", "3", "--json"])
    assert rc2 == 0
    plan = json.loads(buf2.getvalue())
    assert plan["physical_qubits_total"] > 0


def test_mcp_noise_tool():
    from plaq_mcp.server import handle_rpc, tool_catalog

    names = {t["name"] for t in tool_catalog()}
    assert "quantum_noise" in names
    assert "quantum_surgery" in names
    reply = handle_rpc(
        {
            "jsonrpc": "2.0",
            "id": 11,
            "method": "tools/call",
            "params": {"name": "quantum_draw", "arguments": {"workload": "bell"}},
        }
    )
    body = json.loads(reply["result"]["content"][0]["text"])
    assert body["num_qubits"] == 2
