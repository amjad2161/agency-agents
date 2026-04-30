# JARVIS — launch the unified runtime (Windows PowerShell).
# Activates the venv created by setup.ps1 and runs `agency singularity` by
# default; pass any other agency subcommand to run it directly.
$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$Venv = Join-Path $Root ".venv"
$VenvAgency = Join-Path $Venv "Scripts\agency.exe"
$VenvPython = Join-Path $Venv "Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
    Write-Error "[ERROR] Virtual environment not found. Run scripts\jarvis\setup.ps1 first."
    exit 1
}

# Auto-load .env at the repo root if present (KEY=VALUE pairs).
$EnvFile = Join-Path $Root ".env"
if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        if ($_ -match "^\s*([^#=\s][^=]*)=(.*)$") {
            $name = $matches[1].Trim()
            $value = $matches[2].Trim()
            Set-Item -Path "Env:$name" -Value $value
        }
    }
}

if ($args.Count -eq 0) {
    if (Test-Path $VenvAgency) {
        & $VenvAgency singularity
    } else {
        & $VenvPython -m agency.cli singularity
    }
} else {
    if (Test-Path $VenvAgency) {
        & $VenvAgency @args
    } else {
        & $VenvPython -m agency.cli @args
    }
}
exit $LASTEXITCODE
