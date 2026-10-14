"""
Root-level backward compatibility shim for plaq_quantum.benchmark.
Re-exports transpilation and fault-tolerant benchmarking runners.
"""

from __future__ import annotations
import plaq_bootstrap  # noqa: F401
from plaq_quantum.benchmark import *
from plaq_quantum.benchmark import (
    run_compiler_baseline,
    run_full_benchmark_suite,
)

if __name__ == "__main__":
    import sys
    hw_choice = sys.argv[1] if len(sys.argv) > 1 else "superconducting"
    run_full_benchmark_suite(hardware_name=hw_choice)
