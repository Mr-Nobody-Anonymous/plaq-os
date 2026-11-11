"""Circuit-level simulation, workload resolver, and new quantum agent tools."""

from __future__ import annotations

import json

import pytest

from plaq_quantum.simulation import circuit_fidelity, run_circuit_simulation
from plaq_quantum.workloads import (
    list_hardware_profiles,
    list_workloads,
    make_bell_circuit,
    make_ghz_circuit,
    resolve_circuit,
)
from plaq_agent_runtime.registry import ToolContext, create_default_tool_registry
from plaq_contracts.tool import ToolRequest
from plaq_control_plane.db import DatabaseEngine
from plaq_control_plane.repository import ControlPlaneRepository


def test_resolve_named_workloads():
    bell = resolve_circuit(workload="bell")
    assert bell.num_qubits == 2
    qaoa = resolve_circuit(workload="qaoa", qubits=4)
    assert qaoa.num_qubits == 4
    ghz = resolve_circuit(workload="ghz", qubits=3)
    assert ghz.num_qubits == 3
    default = resolve_circuit()
    assert default.num_qubits == 4


def test_bell_statevector_probabilities():
    res = run_circuit_simulation(workload="bell")
    assert res.mode == "statevector"
    assert res.num_qubits == 2
    # |00> and |11> each ~ 1/2 (endianness-tolerant)
    mass_00 = res.probabilities.get("00", 0.0)
    mass_11 = res.probabilities.get("11", 0.0)
    assert mass_00 + mass_11 > 0.9


def test_bell_shot_sampling():
    res = run_circuit_simulation(workload="bell", shots=256, seed=1)
    assert res.mode == "shots"
    assert sum(res.counts.values()) == 256


def test_qaoa_energy():
    res = run_circuit_simulation(workload="qaoa", qubits=4, compute_energy=True)
    assert res.energy is not None
    assert res.energy_kind == "maxcut_cycle"
    assert res.energy >= 0.0


def test_ghz_fidelity_self():
    a = make_ghz_circuit(3)
    b = make_ghz_circuit(3)
    assert circuit_fidelity(a, b) == pytest.approx(1.0, abs=1e-9)


def test_catalogs_nonempty():
    w = list_workloads()
    h = list_hardware_profiles()
    assert any(row["id"] == "qaoa_cycle_6q" for row in w)
    assert any(row["id"] == "superconducting" for row in h)
    assert make_bell_circuit().num_qubits == 2


@pytest.fixture
def tool_env(tmp_path):
    engine = DatabaseEngine(str(tmp_path / "sim.db"))
    repo = ControlPlaneRepository(engine)
    task = repo.create_task("sim", workspace_path=str(tmp_path))
    registry = create_default_tool_registry()
    ctx = ToolContext(workspace_path=tmp_path, task_id=task["id"], control_plane=repo)
    yield registry, ctx
    engine.close()


def test_new_quantum_tools_registered(tool_env):
    registry, _ = tool_env
    names = {t.name for t in registry.list_tools()}
    for n in (
        "quantum.run",
        "quantum.optimize",
        "quantum.baselines",
        "quantum.threshold",
        "quantum.qasm",
        "quantum.workloads",
        "quantum.hardware",
    ):
        assert n in names


def test_quantum_run_tool(tool_env):
    registry, ctx = tool_env
    res = registry.execute(
        ToolRequest(tool_name="quantum.run", parameters={"workload": "bell"}, task_id=ctx.task_id),
        ctx,
    )
    assert res.success is True
    data = json.loads(res.output)
    assert data["num_qubits"] == 2


def test_quantum_workloads_and_hardware_tools(tool_env):
    registry, ctx = tool_env
    w = registry.execute(
        ToolRequest(tool_name="quantum.workloads", parameters={}, task_id=ctx.task_id), ctx
    )
    h = registry.execute(
        ToolRequest(tool_name="quantum.hardware", parameters={}, task_id=ctx.task_id), ctx
    )
    assert w.success and h.success
    assert "qaoa" in w.output.lower() or "qaoa_cycle" in w.output
    assert "superconducting" in h.output


def test_quantum_threshold_tool(tool_env):
    registry, ctx = tool_env
    res = registry.execute(
        ToolRequest(
            tool_name="quantum.threshold",
            parameters={"distances": [3], "physical_error_rates": [0.001], "shots_per_point": 20},
            task_id=ctx.task_id,
        ),
        ctx,
    )
    assert res.success is True
    data = json.loads(res.output)
    assert data["samples"]
