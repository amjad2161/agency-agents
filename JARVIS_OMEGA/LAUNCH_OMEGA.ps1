# Omega-SINGULARITY launcher — PowerShell
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "Python 3.11+ required on PATH"
}
if ($args.Count -eq 0) {
    python omega.py stats
} else {
    python omega.py @args
}
