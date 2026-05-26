# JARVIS_SUPREME.ps1 — singular launcher
# Boots venv → imports all subsystems → starts daemons → opens HUD
[CmdletBinding()]
param(
  [ValidateSet("boot","health","run","route")]
  [string]$Cmd = "run",
  [string]$Query = "",
  [string]$Canonical = "",
  [switch]$NoVenv
)

$ErrorActionPreference = "Continue"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
if ([string]::IsNullOrEmpty($Canonical)) { $Canonical = $here }
$env:AGENCY_ROOT = $Canonical
$supreme = Join-Path $here "JARVIS_SUPREME.py"
$logPath = Join-Path $here "jarvis_supreme.log"
$env:JARVIS_SUPREME_LOG = $logPath

Write-Host "=== JARVIS_SUPREME launcher ===" -ForegroundColor Cyan
Write-Host "canonical : $Canonical"
Write-Host "supreme   : $supreme"
Write-Host "log       : $logPath"
Write-Host ""

# Activate venv if present
$venv = Join-Path $Canonical ".venv\Scripts\Activate.ps1"
if (-not $NoVenv -and (Test-Path $venv)) {
  Write-Host "[venv] activating $venv" -ForegroundColor DarkGray
  & $venv
}

# Ensure runtime is installed (idempotent)
$runtime = Join-Path $Canonical "runtime"
if (Test-Path (Join-Path $runtime "setup.py")) {
  Write-Host "[deps] pip install -e runtime (quiet, idempotent)" -ForegroundColor DarkGray
  python -m pip install -e $runtime --quiet 2>&1 | Out-Null
}

# Run supreme
$args = @($supreme, $Cmd)
if ($Cmd -eq "route" -and $Query) { $args += $Query.Split(" ") }
Write-Host "[exec] python $($args -join ' ')" -ForegroundColor Yellow
& python @args
$ec = $LASTEXITCODE
Write-Host ""
Write-Host "=== exit_code=$ec  log=$logPath ===" -ForegroundColor Cyan
exit $ec
