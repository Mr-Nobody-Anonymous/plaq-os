"""Installer CLI smoke (does not actually pip-install)."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_install():
    spec = importlib.util.spec_from_file_location("plaq_install", ROOT / "scripts" / "install.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_install_script_help():
    script = ROOT / "scripts" / "install.py"
    proc = subprocess.run(
        [sys.executable, str(script), "--help"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert "--lite" in proc.stdout
    assert "--dev" in proc.stdout


def test_install_wrappers_exist():
    assert (ROOT / "install.sh").exists()
    assert (ROOT / "install.ps1").exists()
    assert (ROOT / "INSTALL.md").exists()
    assert (ROOT / "requirements-core.txt").exists()
    assert (ROOT / "requirements-quantum.txt").exists()
    assert (ROOT / "Dockerfile").exists()
    assert (ROOT / "docker-compose.yml").exists()
    assert (ROOT / "environment.yml").exists()
    assert (ROOT / "Makefile").exists()


def _req_packages(path: Path) -> list[str]:
    names = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("-"):
            continue
        names.append(stripped.split(">")[0].split("=")[0].split("[")[0].strip().lower())
    return names


def test_core_requirements_do_not_force_stim():
    core = _req_packages(ROOT / "requirements-core.txt")
    assert "stim" not in core
    assert "pymatching" not in core
    quantum = _req_packages(ROOT / "requirements-quantum.txt")
    assert "stim" in quantum
    assert "pymatching" in quantum


def test_install_parse_args_lite():
    mod = _load_install()
    args = mod.parse_args(["--lite", "--dev", "--no-doctor", "--skip-venv"])
    assert args.lite is True
    assert args.dev is True
    assert args.no_doctor is True
    assert args.skip_venv is True


def test_engine_pyproject_stim_is_optional():
    text = (ROOT / "engines" / "quantum" / "pyproject.toml").read_text(encoding="utf-8")
    required, _, optional = text.partition("[project.optional-dependencies]")
    assert "stim" not in required.lower()
    assert "stim" in optional.lower()
