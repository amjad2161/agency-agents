# JARVIS — one-shot setup (Windows PowerShell).
# Creates .venv at the repo root and installs the agency runtime in editable
# mode. Re-run safely to upgrade dependencies.
$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$Runtime = Join-Path $Root "runtime"
$Venv = Join-Path $Root ".venv"

Write-Host ""
Write-Host " [JARVIS] Supreme Brainiac — Setup"
Write-Host " ==================================="
Write-Host ""

$Python = $null
foreach ($candidate in @("py", "python")) {
    if (Get-Command $candidate -ErrorAction SilentlyContinue) {
        $Python = $candidate
        break
    }
}
if (-not $Python) {
    Write-Error "[ERROR] Python not found. Install Python 3.10+ from https://python.org"
    exit 1
}

& $Python --version
Write-Host ""

if (-not (Test-Path $Venv)) {
    Write-Host "[SETUP] Creating virtual environment at $Venv..."
    & $Python -m venv $Venv
    if ($LASTEXITCODE -ne 0) { Write-Error "venv creation failed"; exit 1 }
    Write-Host "[OK] Virtual environment created."
} else {
    Write-Host "[OK] Virtual environment already exists."
}

$VenvPython = Join-Path $Venv "Scripts\python.exe"
$VenvPip = Join-Path $Venv "Scripts\pip.exe"

Write-Host "[SETUP] Upgrading pip..."
& $VenvPython -m pip install --upgrade pip --quiet
Write-Host "[SETUP] Installing agency runtime (pip install -e runtime[dev])..."
& $VenvPip install -e "$Runtime[dev]" --quiet
if ($LASTEXITCODE -ne 0) { Write-Error "[ERROR] Installation failed."; exit 1 }
Write-Host "[OK] Runtime installed."

if (-not $env:ANTHROPIC_API_KEY) {
    Write-Host ""
    Write-Host "[WARN] ANTHROPIC_API_KEY is not set." -ForegroundColor Yellow
    Write-Host "       setx ANTHROPIC_API_KEY ""sk-ant-your-key-here"""
} else {
    Write-Host "[OK] ANTHROPIC_API_KEY is set."
}

Write-Host ""
Write-Host " ==================================="
Write-Host " [JARVIS] Setup complete."
Write-Host " Run scripts\jarvis\start.ps1 to launch."
Write-Host " ==================================="
