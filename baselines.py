"""
Root-level backward compatibility shim for plaq_quantum.baselines.
Re-exports four-baselines protocol and ablation study runners and records.
"""

from __future__ import annotations
import plaq_bootstrap  # noqa: F401
from plaq_quantum.baselines import *
from plaq_quantum.baselines import (
    BaselineComparisonRecord,
    AblationRecord,
    run_four_baselines_protocol,
    run_ablation_study,
)
