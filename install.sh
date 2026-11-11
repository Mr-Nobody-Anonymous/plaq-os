#!/usr/bin/env sh
# Plaq-OS installer for Linux, macOS, WSL, and BSD.
# Usage:  ./install.sh [--lite] [--dev] [--skip-venv]
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$ROOT"

if command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
else
  echo "Python 3.10+ is required. Install it, then re-run ./install.sh" >&2
  echo "  Debian/Ubuntu : sudo apt install python3 python3-venv python3-pip" >&2
  echo "  Fedora        : sudo dnf install python3 python3-pip" >&2
  echo "  Arch          : sudo pacman -S python python-pip" >&2
  echo "  macOS         : brew install python" >&2
  exit 1
fi

exec "$PY" "$ROOT/scripts/install.py" "$@"
