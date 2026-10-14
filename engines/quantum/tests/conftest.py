"""
Pytest configuration for plaq-quantum engine tests.
Configures sys.path so plaq_quantum package and root bootstrap are accessible.
"""

from __future__ import annotations
import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
QUANTUM_ROOT = TESTS_DIR.parent
QUANTUM_SRC = QUANTUM_ROOT / "src"
REPO_ROOT = QUANTUM_ROOT.parent.parent

for p in [str(QUANTUM_SRC), str(REPO_ROOT)]:
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    import plaq_bootstrap  # noqa: F401
except ImportError:
    pass
