#!/usr/bin/env python3
"""Cross-platform Plaq-OS installer (Linux, macOS, Windows, WSL, ARM).

Stdlib only — run with whatever Python 3.10+ is already on the machine:

    python3 scripts/install.py
    py -3 scripts\\install.py
"""

from __future__ import annotations

import argparse
import os
import platform
import subprocess
import sys
import venv
from pathlib import Path
from typing import List, Optional, Sequence

ROOT = Path(__file__).resolve().parents[1]
MIN_PY = (3, 10)

WORKSPACE_PACKAGES = [
    "packages/contracts",
    "packages/sdk-python",
    "services/control-plane",
    "services/sandbox-manager",
    "services/model-gateway",
    "services/artifact-service",
    "services/agent-runtime",
    "engines/quantum",
    "apps/api",
    "apps/cli",
    "apps/mcp",
]


def die(msg: str, code: int = 1) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    raise SystemExit(code)


def run(cmd: Sequence[str], *, cwd: Optional[Path] = None) -> int:
    print(f"  $ {' '.join(cmd)}")
    proc = subprocess.run(list(cmd), cwd=str(cwd or ROOT))
    return proc.returncode


def venv_python(venv_dir: Path) -> Path:
    if sys.platform == "win32":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def pip(py: Path, *args: str) -> int:
    return run([str(py), "-m", "pip", *args])


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Install Plaq-OS on Linux, macOS, or Windows")
    p.add_argument("--venv", default=".venv", help="Virtualenv directory (relative to repo root)")
    p.add_argument("--skip-venv", action="store_true", help="Install into the current interpreter")
    p.add_argument("--lite", action="store_true", help="Skip Stim/PyMatching (no C++ compiler needed)")
    p.add_argument("--dev", action="store_true", help="Also install pytest/ruff")
    p.add_argument("--no-doctor", action="store_true", help="Do not run `plaq doctor` at the end")
    return p.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    print("Plaq-OS installer")
    print(f"  OS:      {platform.system()} {platform.release()} ({platform.machine()})")
    print(f"  Python:  {sys.version.split()[0]}  ({sys.executable})")

    if sys.version_info < MIN_PY:
        die(f"Python {MIN_PY[0]}.{MIN_PY[1]}+ is required (found {sys.version.split()[0]})")

    if args.skip_venv:
        py = Path(sys.executable)
    else:
        venv_dir = (ROOT / args.venv).resolve()
        print(f"Creating virtualenv at {venv_dir} ...")
        venv_dir.parent.mkdir(parents=True, exist_ok=True)
        builder = venv.EnvBuilder(with_pip=True, clear=False, upgrade_deps=False)
        builder.create(str(venv_dir))
        py = venv_python(venv_dir)
        if not py.exists():
            die(f"Virtualenv python not found at {py}")

    if pip(py, "install", "--upgrade", "pip", "setuptools", "wheel") != 0:
        die("Failed to upgrade pip")

    core = ROOT / "requirements-core.txt"
    quantum = ROOT / "requirements-quantum.txt"
    full = ROOT / "requirements.txt"
    dev = ROOT / "requirements-dev.txt"

    req = core if args.lite and core.exists() else full
    print(f"Installing runtime deps from {req.name} ...")
    if pip(py, "install", "-r", str(req)) != 0:
        if not args.lite and quantum.exists() and core.exists():
            print("Full install failed — retrying core (no Stim/PyMatching) ...")
            if pip(py, "install", "-r", str(core)) != 0:
                die("Failed to install core requirements")
            print("NOTE: Stim/PyMatching were skipped. Surface-code Monte Carlo is unavailable.")
            print("      Install a C++ toolchain and re-run:  pip install -r requirements-quantum.txt")
        else:
            die("Failed to install requirements")
    elif not args.lite and quantum.exists():
        # Ensure quantum extras even if they were already in requirements.txt.
        rc = pip(py, "install", "-r", str(quantum))
        if rc != 0:
            print("WARNING: Stim/PyMatching failed. Core Plaq-OS still works; QEC sim is degraded.")

    if args.dev and dev.exists():
        if pip(py, "install", "-r", str(dev)) != 0:
            die("Failed to install dev requirements")

    print("Installing Plaq-OS workspace packages (editable) ...")
    editables = []
    for rel in WORKSPACE_PACKAGES:
        path = ROOT / rel
        if path.exists():
            editables.extend(["-e", str(path)])
    if editables and pip(py, "install", *editables) != 0:
        die("Failed to install workspace packages")

    print()
    print("Install complete.")
    if not args.skip_venv:
        if sys.platform == "win32":
            print("Activate the environment:")
            print(f"  PowerShell :  {args.venv}\\Scripts\\Activate.ps1")
            print(f"  cmd.exe    :  {args.venv}\\Scripts\\activate.bat")
        else:
            print("Activate the environment:")
            print(f"  source {args.venv}/bin/activate")
    print()
    print("Next:")
    print("  plaq doctor")
    print("  plaq init")
    print("  plaq serve --port 8000")

    if not args.no_doctor:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
        print()
        subprocess.run([str(py), str(ROOT / "plaq.py"), "doctor"], cwd=str(ROOT), env=env)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
