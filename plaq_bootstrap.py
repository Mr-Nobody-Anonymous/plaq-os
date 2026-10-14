"""
Plaq-OS Monorepo Bootstrap Hook
Configures sys.path to include engines, packages, services, and apps src directories
for seamless root-level imports, testing, and backward compatibility.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent

MONOREPO_SOURCE_DIRS = [
    ROOT_DIR,
    ROOT_DIR / "engines" / "quantum" / "src",
    ROOT_DIR / "packages" / "contracts" / "src",
    ROOT_DIR / "packages" / "sdk-python" / "src",
    ROOT_DIR / "services" / "control-plane" / "src",
    ROOT_DIR / "services" / "agent-runtime" / "src",
    ROOT_DIR / "services" / "sandbox-manager" / "src",
    ROOT_DIR / "services" / "model-gateway" / "src",
    ROOT_DIR / "services" / "artifact-service" / "src",
    ROOT_DIR / "apps" / "api" / "src",
    ROOT_DIR / "apps" / "cli" / "src",
]

def _apply_compatibility_shims() -> None:
    """Apply upstream framework compatibility shims (e.g. Starlette 1.x / FastAPI 0.109)."""
    try:
        import starlette.routing
        orig_router_init = starlette.routing.Router.__init__
        if not getattr(orig_router_init, "_plaq_patched", False):
            def _patched_router_init(self, *args, on_startup=None, on_shutdown=None, **kwargs):
                orig_router_init(self, *args, **kwargs)
                self.on_startup = on_startup or []
                self.on_shutdown = on_shutdown or []
            _patched_router_init._plaq_patched = True  # type: ignore
            starlette.routing.Router.__init__ = _patched_router_init
    except ImportError:
        pass

    try:
        import fastapi
        if not hasattr(fastapi.FastAPI, "max_body_size"):
            setattr(fastapi.FastAPI, "max_body_size", None)
    except ImportError:
        pass


def bootstrap() -> None:
    """Insert all monorepo source directories into sys.path if not present."""
    for path in MONOREPO_SOURCE_DIRS:
        path_str = str(path)
        if path_str not in sys.path:
            sys.path.insert(0, path_str)
    _apply_compatibility_shims()

# Run bootstrap on module import
bootstrap()
