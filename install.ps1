# Plaq-OS installer for Windows (PowerShell 5+ / 7).
#   powershell -ExecutionPolicy Bypass -File .\install.ps1
#   .\install.ps1 -Lite -Dev
param(
    [switch]$Lite,
    [switch]$Dev,
    [switch]$SkipVenv
)

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
try { chcp 65001 | Out-Null } catch { }

function Test-Python([string]$Exe, [string[]]$PrefixArgs) {
    try {
        $all = @()
        if ($PrefixArgs) { $all += $PrefixArgs }
        $all += @("-c", "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)")
        & $Exe @all | Out-Null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    }
}

$exe = $null
$prefix = @()
if (Get-Command py -ErrorAction SilentlyContinue) {
    if (Test-Python "py" @("-3")) { $exe = "py"; $prefix = @("-3") }
}
if (-not $exe -and (Get-Command python -ErrorAction SilentlyContinue)) {
    if (Test-Python "python" @()) { $exe = "python"; $prefix = @() }
}
if (-not $exe -and (Get-Command python3 -ErrorAction SilentlyContinue)) {
    if (Test-Python "python3" @()) { $exe = "python3"; $prefix = @() }
}
if (-not $exe) {
    Write-Error @"
Python 3.10+ was not found.
  winget install Python.Python.3.12
or https://www.python.org/downloads/windows/  (tick 'Add python.exe to PATH')
"@
    exit 1
}

$extra = @()
if ($Lite) { $extra += "--lite" }
if ($Dev) { $extra += "--dev" }
if ($SkipVenv) { $extra += "--skip-venv" }

$script = Join-Path $PSScriptRoot "scripts\install.py"
& $exe @prefix $script @extra
exit $LASTEXITCODE
