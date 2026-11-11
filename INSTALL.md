# Installing Plaq-OS

Works on **Linux**, **macOS** (Intel + Apple Silicon), **Windows 10/11**, **WSL2**, and **Docker**.
Python **3.10, 3.11, or 3.12** is required.

The one-command installer creates a virtualenv, installs packages, and runs `plaq doctor`.

## 1. One-command install (recommended)

### Linux / macOS / WSL

```bash
git clone https://github.com/Mr-Nobody-Anonymous/plaq-os.git
cd plaq-os
chmod +x install.sh
./install.sh --dev
source .venv/bin/activate
plaq doctor
plaq init
plaq serve --port 8000
```

If Stim/PyMatching fail to compile (no C++ toolchain), use the lite profile:

```bash
./install.sh --lite --dev
```

Surface-code Monte Carlo is then degraded; circuit simulation, estimates, and the workbench still work.

### Windows (PowerShell)

```powershell
git clone https://github.com/Mr-Nobody-Anonymous/plaq-os.git
cd plaq-os
Set-ExecutionPolicy -Scope Process Bypass
.\install.ps1 -Dev
.\.venv\Scripts\Activate.ps1
plaq doctor
plaq init
plaq serve --port 8000
```

Install Python first if `python` is missing:

```powershell
winget install Python.Python.3.12
```

Tick **Add python.exe to PATH** if you use the python.org installer.

### Docker (any OS, including NAS / Raspberry Pi with buildx)

```bash
docker compose up --build
# workbench: http://127.0.0.1:8000/
```

## 2. OS packages you may need

| OS | Python | Optional C++ (for Stim) |
|---|---|---|
| Debian / Ubuntu | `sudo apt install python3 python3-venv python3-pip git` | `sudo apt install build-essential` |
| Fedora | `sudo dnf install python3 python3-pip git` | `sudo dnf install gcc-c++` |
| Arch | `sudo pacman -S python python-pip git` | `sudo pacman -S base-devel` |
| Alpine | `apk add python3 py3-pip git` | `apk add build-base` |
| macOS | `brew install python git` | `xcode-select --install` |
| Windows | `winget install Python.Python.3.12 Git.Git` | [MSVC Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/) |

Most platforms now have **binary wheels** for `stim` and `pymatching`. A compiler is only needed if pip falls back to source.

## 3. Conda / Mamba / Micromamba

```bash
conda env create -f environment.yml
conda activate plaq-os
python scripts/install.py --skip-venv --dev
plaq doctor
```

## 4. Manual pip (all platforms)

```bash
python3 -m venv .venv
# Windows: py -3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -r requirements.txt -r requirements-dev.txt
pip install -e ./packages/contracts -e ./packages/sdk-python \
  -e ./services/control-plane -e ./services/sandbox-manager \
  -e ./services/model-gateway -e ./services/artifact-service \
  -e ./services/agent-runtime -e ./engines/quantum \
  -e ./apps/api -e ./apps/cli -e ./apps/mcp
```

Lite (no Stim): `pip install -r requirements-core.txt` instead of `requirements.txt`.

## 5. After install

| Command | What it does |
|---|---|
| `plaq doctor` | Check Python, OS, packages, DB write access, auth |
| `plaq init` | Create `~/.plaq`, migrate SQLite, seed API key |
| `plaq serve` | Workbench + API at http://127.0.0.1:8000/ |
| `plaq quantum run bell --json` | Circuit simulation smoke test |
| `pytest` | Full test suite |

On Windows, if `plaq` is not found after activate, use:

```powershell
python plaq.py doctor
python -m plaq_cli doctor
```

## 6. Environment

Copy `.env.example` to `.env` (or run `plaq init`). Important variables:

- `PLAQ_DB_PATH` — SQLite file (default `~/.plaq/plaq.db`, Windows `%USERPROFILE%\.plaq\plaq.db`)
- `PLAQ_AUTH=off` — disable API-key auth for local demos
- `PLAQ_HOST=0.0.0.0` — bind every interface (Docker / LAN)
- `OPENAI_API_KEY` — enable the LLM planner

## 7. Uninstall

Delete the clone and the data directory:

```bash
rm -rf plaq-os ~/.plaq          # Linux/macOS
rmdir /s plaq-os %USERPROFILE%\.plaq   # Windows cmd
```
