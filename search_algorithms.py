"""
Root-level backward compatibility shim for plaq_quantum.search_algorithms.
Re-exports exhaustive, random, greedy, and simulated annealing search algorithms.
"""

from __future__ import annotations
import plaq_bootstrap  # noqa: F401
from plaq_quantum.search_algorithms import *
from plaq_quantum.search_algorithms import (
    SearchBenchmarkResult,
    search_exhaustive,
    search_random,
    search_greedy,
    search_simulated_annealing,
    benchmark_search_methods,
)
