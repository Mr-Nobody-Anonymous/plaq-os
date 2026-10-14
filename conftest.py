"""
Root pytest configuration and fixture setup for Plaq-OS.
Automatically imports plaq_bootstrap to configure monorepo sys.path.
"""

from __future__ import annotations
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import plaq_bootstrap  # noqa: F401
