"""Environment diagnostics for Plaq-OS (``plaq doctor`` / ``plaq init``)."""

from __future__ import annotations

import json
import os
import platform
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for p in [here, *here.parents]:
        if (p / "plaq.py").exists() and (p / ".env.example").exists():
            return p
    return Path.cwd()


def _ok(name: str, detail: str = "ok") -> Dict[str, str]:
    return {"name": name, "status": "ok", "detail": detail}


def _warn(name: str, detail: str) -> Dict[str, str]:
    return {"name": name, "status": "warn", "detail": detail}


def _fail(name: str, detail: str) -> Dict[str, str]:
    return {"name": name, "status": "fail", "detail": detail}


def _try_import(mod: str) -> Tuple[bool, str]:
    try:
        m = __import__(mod)
        ver = getattr(m, "__version__", "")
        return True, ver or "present"
    except Exception as exc:
        return False, str(exc)


def collect_report() -> Dict[str, Any]:
    checks: List[Dict[str, str]] = []

    py = sys.version_info
    if py >= (3, 10):
        checks.append(_ok("python", f"{py.major}.{py.minor}.{py.micro} ({sys.executable})"))
    else:
        checks.append(_fail("python", f"{py.major}.{py.minor} < 3.10"))

    checks.append(_ok("os", f"{platform.system()} {platform.release()} {platform.machine()}"))

    for label, mod in (
        ("pydantic", "pydantic"),
        ("fastapi", "fastapi"),
        ("qiskit", "qiskit"),
        ("numpy", "numpy"),
    ):
        ok, detail = _try_import(mod)
        checks.append(_ok(label, detail) if ok else _warn(label, f"missing ({detail})"))

    stim_ok, stim_d = _try_import("stim")
    pm_ok, pm_d = _try_import("pymatching")
    if stim_ok and pm_ok:
        checks.append(_ok("stim", stim_d))
        checks.append(_ok("pymatching", pm_d))
    else:
        checks.append(_warn("stim", stim_d if not stim_ok else stim_d + " (ok)"))
        checks.append(_warn("pymatching", pm_d if not pm_ok else pm_d + " (ok)"))
        checks.append(_warn("qec", "Surface-code Monte Carlo degraded without stim+pymatching"))

    for label, mod in (
        ("plaq_contracts", "plaq_contracts"),
        ("plaq_control_plane", "plaq_control_plane"),
        ("plaq_agent_runtime", "plaq_agent_runtime"),
        ("plaq_quantum", "plaq_quantum"),
        ("plaq_api", "plaq_api"),
        ("plaq_cli", "plaq_cli"),
        ("plaq_mcp", "plaq_mcp"),
    ):
        ok, detail = _try_import(mod)
        checks.append(_ok(label, detail) if ok else _fail(label, detail))

    from plaq_control_plane.db import resolve_db_path

    db_path = Path(resolve_db_path())
    parent = db_path.parent
    try:
        parent.mkdir(parents=True, exist_ok=True)
        probe = parent / ".plaq_write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        checks.append(_ok("data_dir", str(parent)))
    except Exception as exc:
        checks.append(_fail("data_dir", f"{parent}: {exc}"))

    auth = os.environ.get("PLAQ_AUTH", "").strip().lower()
    if auth in {"off", "0", "false"}:
        checks.append(_warn("auth", "PLAQ_AUTH=off (API is open)"))
    elif os.environ.get("PLAQ_API_KEY"):
        checks.append(_ok("auth", "PLAQ_API_KEY is set"))
    else:
        key_file = parent / "api_key"
        if key_file.exists():
            checks.append(_ok("auth", f"key file {key_file}"))
        else:
            checks.append(_ok("auth", "will generate ~/.plaq/api_key on `plaq serve`"))

    worst = "ok"
    for c in checks:
        if c["status"] == "fail":
            worst = "fail"
            break
        if c["status"] == "warn" and worst != "fail":
            worst = "warn"

    return {
        "status": worst,
        "python": f"{py.major}.{py.minor}.{py.micro}",
        "platform": platform.platform(),
        "executable": sys.executable,
        "checks": checks,
    }


def format_report(report: Dict[str, Any]) -> str:
    lines = [
        f"Plaq-OS doctor  [{report['status']}]",
        f"  python : {report['python']}  {report['executable']}",
        f"  system : {report['platform']}",
        "",
    ]
    mark = {"ok": "OK  ", "warn": "WARN", "fail": "FAIL"}
    for c in report["checks"]:
        lines.append(f"  {mark.get(c['status'], c['status'])}  {c['name']:<22} {c['detail']}")
    return "\n".join(lines)


def run_doctor(*, as_json: bool = False) -> int:
    report = collect_report()
    if as_json:
        print(json.dumps(report, indent=2))
    else:
        print(format_report(report))
    return 1 if report["status"] == "fail" else 0


def run_init(*, as_json: bool = False) -> int:
    """Create the local data dir, apply migrations, and seed an API key."""
    from plaq_api.auth import default_key_path, resolve_api_key
    from plaq_control_plane.db import DatabaseEngine
    from plaq_control_plane.migrations import applied_versions

    from plaq_control_plane.db import resolve_db_path

    db_path = Path(resolve_db_path())
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = DatabaseEngine(str(db_path))
    versions = applied_versions(engine.conn)
    engine.close()
    key = resolve_api_key(generate=True)
    key_path = default_key_path()
    env_example = _repo_root() / ".env.example"
    env_target = Path.cwd() / ".env"
    env_copied = False
    if env_example.exists() and not env_target.exists():
        env_target.write_text(env_example.read_text(encoding="utf-8"), encoding="utf-8")
        env_copied = True
    payload = {
        "db": str(db_path),
        "migrations": versions,
        "api_key_file": str(key_path) if key else None,
        "env_copied": env_copied,
    }
    if as_json:
        print(json.dumps(payload, indent=2))
    else:
        print("Plaq-OS initialized.")
        print(f"  database : {payload['db']}")
        print(f"  schema   : {payload['migrations']}")
        if payload["api_key_file"]:
            print(f"  api key  : {payload['api_key_file']}")
        if env_copied:
            print(f"  env file : {env_target}")
        print("Next: plaq doctor && plaq serve")
    return 0
