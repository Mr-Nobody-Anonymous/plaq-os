"""MCP JSON-RPC dispatcher (no stdio required)."""

from __future__ import annotations

import json

from plaq_mcp.server import handle_rpc, tool_catalog


def test_initialize_and_tool_list():
    init = handle_rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert init["result"]["serverInfo"]["name"] == "plaq-os"
    assert init["result"]["protocolVersion"] == "2024-11-05"

    listed = handle_rpc({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    names = {t["name"] for t in listed["result"]["tools"]}
    assert "quantum_run" in names
    assert "quantum_simulate" in names
    assert "task_create" in names
    assert {t["name"] for t in tool_catalog()} == names


def test_initialized_notification_has_no_response():
    assert handle_rpc({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None


def test_quantum_run_via_mcp():
    reply = handle_rpc(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "quantum_run", "arguments": {"workload": "bell"}},
        }
    )
    text = reply["result"]["content"][0]["text"]
    data = json.loads(text)
    assert data["num_qubits"] == 2


def test_resources_list_and_read():
    listed = handle_rpc({"jsonrpc": "2.0", "id": 4, "method": "resources/list"})
    uris = {r["uri"] for r in listed["result"]["resources"]}
    assert "plaq://workloads" in uris
    read = handle_rpc(
        {"jsonrpc": "2.0", "id": 5, "method": "resources/read", "params": {"uri": "plaq://hardware"}}
    )
    body = json.loads(read["result"]["contents"][0]["text"])
    assert any(row["id"] == "superconducting" for row in body)


def test_unknown_method():
    reply = handle_rpc({"jsonrpc": "2.0", "id": 9, "method": "nope"})
    assert reply["error"]["code"] == -32601
