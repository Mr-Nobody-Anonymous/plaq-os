"""
Root-level backward compatibility shim for plaq_quantum.hardware.
Re-exports hardware models, coupling topologies, and hardware catalog presets.
"""

from __future__ import annotations
import plaq_bootstrap  # noqa: F401
from plaq_quantum.hardware import *
from plaq_quantum.hardware import (
    HardwareModel,
    DEMO_HARDWARE,
    SUPERCONDUCTING_HERON,
    TRAPPED_ION_FORTE,
    TRAPPED_ION_QUANTINUUM,
    NEUTRAL_ATOM_AQUILA,
    NEUTRAL_ATOM_QUERA,
    QLDPC_BIVARIATE_BICYCLE,
    HARDWARE_CATALOG,
    get_hardware_profile,
)
