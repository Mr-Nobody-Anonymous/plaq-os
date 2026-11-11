# Plaq-OS MCP Server

Exposes the Plaq-OS fault-tolerant quantum engine to MCP hosts
(Claude Desktop, Cursor, and any JSON-RPC MCP client) over **stdio**.

## Tools

| Tool | What it does |
|---|---|
| `quantum_compile` | Named workload or OpenQASM → T-count / depth |
| `quantum_estimate` | Surface-code resource estimate |
| `quantum_simulate` | Stim + PyMatching surface-code Monte Carlo |
| `quantum_run` | Statevector / shot circuit simulation + optional MaxCut energy |
| `quantum_optimize` | Pareto co-design search |
| `quantum_baselines` | 4-baselines protocol |
| `quantum_threshold` | Logical-error vs distance sweep |
| `quantum_workloads` / `quantum_hardware` | Catalogs |
| `task_create` / `task_run` / `task_status` | Agent loop |

Resources: `plaq://workloads`, `plaq://hardware`, `plaq://tools`.

## Run

```bash
python -m plaq_mcp          # stdio (MCP host spawns this)
plaq mcp                    # same, via the unified CLI
```

## Claude Desktop

```json
{
  "mcpServers": {
    "plaq-os": {
      "command": "python",
      "args": ["-m", "plaq_mcp"],
      "env": {
        "PLAQ_DB_PATH": "/home/you/.plaq/plaq.db"
      }
    }
  }
}
```

The process **must not** print banners to stdout — only JSON-RPC frames.
Logs go to stderr.
