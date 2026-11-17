"""MCP JSON-RPC dispatcher and stdio framing."""

from __future__ import annotations

import io
import json

from plaq_mcp.server import (
    handle_rpc,
    prompt_catalog,
    run_stdio_server,
    tool_catalog,
)


def _call(name: str, arguments: dict | None = None, msg_id: int = 3) -> dict:
    return handle_rpc(
        {
            "jsonrpc": "2.0",
            "id": msg_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments or {}},
        }
    )


def _payload(reply: dict) -> dict:
    assert "result" in reply, reply
    body = reply["result"]
    assert body.get("isError") is False, body
    return json.loads(body["content"][0]["text"])


def test_initialize_and_tool_list():
    init = handle_rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert init["result"]["serverInfo"]["name"] == "plaq-os"
    assert init["result"]["protocolVersion"] == "2024-11-05"
    assert "tools" in init["result"]["capabilities"]
    assert "prompts" in init["result"]["capabilities"]

    listed = handle_rpc({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    names = {t["name"] for t in listed["result"]["tools"]}
    assert "quantum_run" in names
    assert "quantum_simulate" in names
    assert "task_create" in names
    assert "quantum_noise" in names
    assert "quantum_mitigate" in names
    assert "quantum_transpile" in names
    assert "quantum_surgery" in names
    assert "quantum_draw" in names
    assert "quantum_qasm" in names
    assert {t["name"] for t in tool_catalog()} == names
    for tool in listed["result"]["tools"]:
        assert "inputSchema" in tool
        assert tool["inputSchema"]["type"] == "object"


def test_initialize_negotiates_modern_protocol():
    init = handle_rpc(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "t"}},
        }
    )
    assert init["result"]["protocolVersion"] == "2025-03-26"


def test_initialized_notification_has_no_response():
    assert handle_rpc({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    assert handle_rpc({"jsonrpc": "2.0", "method": "notifications/cancelled"}) is None


def test_ping_and_logging():
    ping = handle_rpc({"jsonrpc": "2.0", "id": 7, "method": "ping"})
    assert ping["result"] == {}
    assert handle_rpc({"jsonrpc": "2.0", "method": "ping"}) is None
    lvl = handle_rpc({"jsonrpc": "2.0", "id": 8, "method": "logging/setLevel", "params": {"level": "info"}})
    assert lvl["result"] == {}


def test_quantum_run_via_mcp():
    reply = _call("quantum_run", {"workload": "bell"})
    data = _payload(reply)
    assert data["num_qubits"] == 2
    json.dumps(data)  # numpy-free


def test_nisq_lab_tools_via_mcp():
    noise = _payload(_call("quantum_noise", {"workload": "bell", "shots": 64, "p1": 0.0, "p2": 0.05, "p_readout": 0.0}))
    assert noise["num_qubits"] == 2
    assert noise["noise"]["p1"] == 0.0
    assert noise["total_variation_distance"] > 0.0

    mit = _payload(_call("quantum_mitigate", {"workload": "bell", "p2": 0.03}))
    assert "zne_value" in mit

    routed = _payload(_call("quantum_transpile", {"workload": "qft", "qubits": 3, "topology": "linear"}))
    assert routed["num_qubits"] == 3

    surg = _payload(_call("quantum_surgery", {"workload": "qft", "qubits": 3, "code_distance": 3}))
    assert surg["physical_qubits_total"] > 0

    draw = _payload(_call("quantum_draw", {"workload": "bell"}))
    assert draw["num_qubits"] == 2
    assert "ascii" in draw

    qasm = _payload(
        _call(
            "quantum_qasm",
            {"qasm": "OPENQASM 2.0; include \"qelib1.inc\"; qreg q[2]; h q[0]; cx q[0],q[1];"},
        )
    )
    assert qasm["num_qubits"] == 2


def test_unknown_tool_is_tool_error_not_rpc_error():
    reply = _call("nope_tool", {})
    assert "result" in reply
    assert reply["result"]["isError"] is True


def test_simulate_without_stim_is_clean_error():
    import plaq_quantum.stim_bridge as sb

    if getattr(sb, "HAS_STIM", False):
        data = _payload(_call("quantum_simulate", {"code_distance": 3, "shots": 20}))
        assert "empirical_logical_error_rate" in data or "logical_errors" in data or "code_distance" in data
        return
    reply = _call("quantum_simulate", {"code_distance": 3, "shots": 20})
    assert reply["result"]["isError"] is True
    assert "Stim" in reply["result"]["content"][0]["text"]
    assert "Traceback" not in reply["result"]["content"][0]["text"]


def test_resources_list_and_read():
    listed = handle_rpc({"jsonrpc": "2.0", "id": 4, "method": "resources/list"})
    uris = {r["uri"] for r in listed["result"]["resources"]}
    assert "plaq://workloads" in uris
    assert "plaq://tools" in uris
    read = handle_rpc(
        {"jsonrpc": "2.0", "id": 5, "method": "resources/read", "params": {"uri": "plaq://hardware"}}
    )
    body = json.loads(read["result"]["contents"][0]["text"])
    assert any(row["id"] == "superconducting" for row in body)

    tools = handle_rpc(
        {"jsonrpc": "2.0", "id": 6, "method": "resources/read", "params": {"uri": "plaq://tools"}}
    )
    registry = json.loads(tools["result"]["contents"][0]["text"])
    names = {t["name"] for t in registry}
    assert "quantum.noise" in names
    assert "quantum.simulate" in names

    missing = handle_rpc(
        {"jsonrpc": "2.0", "id": 7, "method": "resources/read", "params": {"uri": "plaq://nope"}}
    )
    assert missing["error"]["code"] == -32602

    templates = handle_rpc({"jsonrpc": "2.0", "id": 8, "method": "resources/templates/list"})
    assert templates["result"]["resourceTemplates"] == []


def test_prompts():
    listed = handle_rpc({"jsonrpc": "2.0", "id": 1, "method": "prompts/list"})
    names = {p["name"] for p in listed["result"]["prompts"]}
    assert names == {p["name"] for p in prompt_catalog()}
    assert "nisq_lab" in names
    got = handle_rpc({"jsonrpc": "2.0", "id": 2, "method": "prompts/get", "params": {"name": "nisq_lab"}})
    assert got["result"]["messages"][0]["content"]["text"]
    bad = handle_rpc({"jsonrpc": "2.0", "id": 3, "method": "prompts/get", "params": {"name": "nope"}})
    assert bad["error"]["code"] == -32602


def test_unknown_method():
    reply = handle_rpc({"jsonrpc": "2.0", "id": 9, "method": "nope"})
    assert reply["error"]["code"] == -32601


def test_stdio_ndjson_roundtrip():
    req = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}) + "\n"
    req += json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n"
    req += json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "quantum_run", "arguments": {"workload": "bell"}},
        }
    ) + "\n"
    stdin = io.StringIO(req)
    stdout = io.StringIO()
    run_stdio_server(stdin=stdin, stdout=stdout)
    lines = [ln for ln in stdout.getvalue().splitlines() if ln.strip()]
    assert len(lines) == 2  # initialize + tools/call; initialized is a notification
    init = json.loads(lines[0])
    assert init["result"]["serverInfo"]["name"] == "plaq-os"
    run = json.loads(lines[1])
    data = json.loads(run["result"]["content"][0]["text"])
    assert data["num_qubits"] == 2


def test_stdio_content_length_roundtrip():
    inner = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"})
    frame = f"Content-Length: {len(inner.encode('utf-8'))}\r\n\r\n{inner}"
    stdin = io.StringIO(frame)
    stdout = io.StringIO()
    run_stdio_server(stdin=stdin, stdout=stdout)
    out = stdout.getvalue()
    assert "Content-Length:" in out
    body = out.split("\r\n\r\n", 1)[1]
    reply = json.loads(body)
    assert reply["result"] == {}
