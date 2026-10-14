"""
Unit tests for hardware models & coupling topologies.
"""

import pytest
from hardware import (
    HardwareModel,
    DEMO_HARDWARE,
    SUPERCONDUCTING_HERON,
    TRAPPED_ION_FORTE,
    NEUTRAL_ATOM_AQUILA,
    QLDPC_BIVARIATE_BICYCLE,
    HARDWARE_CATALOG,
)


def test_linear_coupling_edges():
    edges = DEMO_HARDWARE.get_coupling_edges(5)
    assert (0, 1) in edges
    assert (1, 0) in edges
    assert (3, 4) in edges
    assert len(edges) == 8


def test_all_to_all_coupling_edges():
    edges = TRAPPED_ION_FORTE.get_coupling_edges(4)
    assert len(edges) == 12


def test_grid_coupling_edges():
    edges = NEUTRAL_ATOM_AQUILA.get_coupling_edges(9)
    assert len(edges) > 0
    node_4_out = [dst for src, dst in edges if src == 4]
    assert len(node_4_out) == 4


def test_qldpc_hardware_profile():
    hw = QLDPC_BIVARIATE_BICYCLE
    assert hw.technology == "qldpc"
    edges = hw.get_coupling_edges(9)
    assert len(edges) > 0


def test_hardware_catalog_presets():
    assert "superconducting" in HARDWARE_CATALOG
    assert "trapped_ion" in HARDWARE_CATALOG
    assert "neutral_atom" in HARDWARE_CATALOG
    assert "qldpc" in HARDWARE_CATALOG
    for name, hw in HARDWARE_CATALOG.items():
        assert hw.single_qubit_error > 0
        assert hw.two_qubit_error > 0
