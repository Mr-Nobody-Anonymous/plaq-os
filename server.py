"""DEPRECATED: the ``http.server`` research UI has been replaced by FastAPI.

``python server.py`` and ``main.py --ui`` now launch ``plaq serve``
(apps/workbench + /api/v1). Prefer:

    python plaq.py serve --port 8000
"""

from __future__ import annotations

import sys
import warnings


def start_quantum_server(port: int = 8000, host: str = "127.0.0.1") -> None:
    """Launch the FastAPI workbench (deprecated alias for ``plaq serve``)."""
    warnings.warn(
        "server.py is deprecated; use `plaq serve` (FastAPI + apps/workbench).",
        DeprecationWarning,
        stacklevel=2,
    )
    print(
        "WARNING: server.py is deprecated. Starting FastAPI workbench via `plaq serve`.",
        flush=True,
    )
    import plaq_bootstrap  # noqa: F401
    import uvicorn

    uvicorn.run("plaq_api.app:app", host=host, port=port)


if __name__ == "__main__":
    p = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    start_quantum_server(p)
