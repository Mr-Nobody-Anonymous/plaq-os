"""python -m plaq_mcp  —  start the stdio MCP server."""

from __future__ import annotations

import sys

from plaq_mcp.server import run_stdio_server


def main() -> int:
    try:
        run_stdio_server()
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
