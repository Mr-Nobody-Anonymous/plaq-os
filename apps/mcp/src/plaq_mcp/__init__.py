"""Plaq-OS Model Context Protocol (MCP) server."""

from plaq_mcp.server import run_stdio_server, handle_rpc

__version__ = "0.3.0"

__all__ = ["run_stdio_server", "handle_rpc", "__version__"]
