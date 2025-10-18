<#
Windows setup script

Creates a Python virtual environment in .venv and installs dependencies
from requirements.txt using pip.

Usage:
  powershell -ExecutionPolicy Bypass -File .\setup.ps1
  # or if already in PowerShell
  .\setup.ps1

Optional params:
  -VenvDir <path>          # default: .venv
  -Requirements <path>     # default: requirements.txt
  -NoPipUpgrade            # do not upgrade pip before install
#>

[CmdletBinding()]
param(
  [string]$VenvDir = ".venv",
  [string]$Requirements = "requirements.txt",
  [switch]$NoPipUpgrade
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Write-Info($msg) { Write-Host "[setup] $msg" -ForegroundColor Cyan }
function Write-Warn($msg) { Write-Host "[setup] $msg" -ForegroundColor Yellow }

Write-Info "Starting Windows setup"

# Resolve Python launcher/executable
$pythonCmd = $null
if (Get-Command py -ErrorAction SilentlyContinue) {
  $pythonCmd = 'py -3'
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
  $pythonCmd = 'python'
} else {
  Write-Error "Python 3 not found. Install Python 3.x and ensure 'py' or 'python' is on PATH."
}

# Create venv if missing
if (-not (Test-Path -LiteralPath $VenvDir)) {
  Write-Info "Creating virtual environment at '$VenvDir'"
  & $Env:ComSpec /c "$pythonCmd -m venv `"$VenvDir`"" | Out-Null
} else {
  Write-Info "Virtual environment already exists at '$VenvDir'"
}

$venvPython = Join-Path -Path $VenvDir -ChildPath "Scripts/python.exe"
if (-not (Test-Path -LiteralPath $venvPython)) {
  Write-Error "Failed to locate venv Python at '$venvPython'."
}

# Upgrade pip unless disabled
if (-not $NoPipUpgrade) {
  Write-Info "Upgrading pip"
  & $venvPython -m pip install --upgrade pip
}

# Install dependencies
if (Test-Path -LiteralPath $Requirements) {
  Write-Info "Installing dependencies from '$Requirements'"
  & $venvPython -m pip install -r $Requirements
} else {
  Write-Warn "No '$Requirements' found; skipping dependency install."
}

Write-Host ""  # blank line
Write-Info "Done. To activate the venv in this shell:"
Write-Host "  `"$((Resolve-Path $VenvDir).Path)\Scripts\Activate.ps1`"" -ForegroundColor Green
Write-Host "If you see a policy error, run: Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass" -ForegroundColor DarkGray

