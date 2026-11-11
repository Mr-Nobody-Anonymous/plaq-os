# plaq-cli

Unified `plaq` command-line interface for Plaq-OS.

```bash
plaq task create "Optimize chemistry_femoco_6q circuit"
plaq task list
plaq quantum compile qft --qubits 4
plaq quantum estimate --qubits 4 --hardware superconducting
plaq quantum run bell --json
plaq quantum simulate --distance 3 --shots 200
plaq quantum workloads
plaq task run <id> --wait
plaq mcp                 # Model Context Protocol stdio server
plaq serve --port 8000
```

Install: `pip install -e ./apps/cli` (plus its workspace deps), or run
from the repo root with `python plaq.py …`.
