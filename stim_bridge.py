"""
Root-level backward compatibility shim for plaq_quantum.stim_bridge.
Re-exports Stim/PyMatching QEC simulation bridges, thresholds, and Wilson intervals.
"""

from __future__ import annotations
import plaq_bootstrap  # noqa: F401
from plaq_quantum.stim_bridge import *
from plaq_quantum.stim_bridge import (
    ThresholdSampleResult,
    wilson_score_interval,
    SurfaceCodeStabilizerSimulator,
    StimSurfaceCodeSimulator,
    run_surface_code_simulation,
    run_threshold_study,
    HAS_STIM,
    HAS_PYMATCHING,
)
