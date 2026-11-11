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

import pytest


@pytest.fixture(autouse=True)
def _stop_background_queues():
    """Ensure in-process job workers cannot outlive a test's SQLite file."""
    yield
    try:
        from plaq_agent_runtime.queue import reset_queues

        reset_queues()
    except Exception:
        pass
