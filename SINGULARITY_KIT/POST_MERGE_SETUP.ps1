# JARVIS SINGULARITY - Post-Merge Setup
# Run after MERGE_SINGULARITY.ps1 completes successfully.
# Bootstraps Python venv, installs runtime, runs smoke tests.

[CmdletBinding()]
param(
    [string]$Root = "C:\Users\User\JARVIS_SINGULARITY",
    [switch]$SkipVenv,
    [switch]$SkipDeps,
    [switch]$SkipSmoke
)

$ErrorActionPreference = 'Continue'

if (-not (Test-Path $Root)) {
    Write-Error "Root not found: $Root - run MERGE_SINGULARITY.ps1 first"
    exit 1
}

Push-Location $Root
try {
    Write-Host "=== JARVIS SINGULARITY POST-MERGE SETUP ===" -ForegroundColor Cyan
    Write-Host "Root: $Root"
    Write-Host ""

    $py = (Get-Command python -ErrorAction SilentlyContinue).Source
    if (-not $py) { $py = (Get-Command python3 -ErrorAction SilentlyContinue).Source }
    if (-not $py) {
        Write-Error 'Python not found in PATH. Install Python 3.10+ first.'
        exit 2
    }
    Write-Host "Python: $py" -ForegroundColor Green
    & $py --version

    # Step 1: venv
    if (-not $SkipVenv) {
        Write-Host ""
        Write-Host "Step 1: create .venv" -ForegroundColor Cyan
        if (-not (Test-Path '.venv')) {
            & $py -m venv .venv
        } else {
            Write-Host "  .venv already exists, skipping"
        }
    }

    $venvPy = Join-Path $Root '.venv\Scripts\python.exe'
    if (-not (Test-Path $venvPy)) { $venvPy = $py }

    # Step 2: deps
    if (-not $SkipDeps) {
        Write-Host ""
        Write-Host "Step 2: upgrade pip + install runtime" -ForegroundColor Cyan
        & $venvPy -m pip install --upgrade pip setuptools wheel 2>&1 | Out-Host
        if (Test-Path 'runtime\pyproject.toml') {
            Write-Host "  installing runtime (editable)"
            & $venvPy -m pip install -e .\runtime 2>&1 | Out-Host
        } elseif (Test-Path 'pyproject.toml') {
            Write-Host "  installing root pyproject (editable)"
            & $venvPy -m pip install -e . 2>&1 | Out-Host
        } else {
            Write-Host "  no pyproject.toml found, skipping editable install" -ForegroundColor Yellow
        }
        if (Test-Path 'requirements.txt') {
            & $venvPy -m pip install -r requirements.txt 2>&1 | Out-Host
        }
    }

    # Step 3: smoke
    if (-not $SkipSmoke) {
        Write-Host ""
        Write-Host "Step 3: smoke test imports" -ForegroundColor Cyan
        $env:PYTHONPATH = "$Root;$Root\runtime;$env:PYTHONPATH"
        $smoke = @'
import importlib, sys, traceback
mods = ["jarvis_brainiac", "jarvis_os"]
ok=0; fail=0
for m in mods:
    try:
        importlib.import_module(m)
        ok += 1
        print(f"[OK]   {m}")
    except Exception as e:
        fail += 1
        print(f"[FAIL] {m}: {e}")
try:
    import agency  # runtime package
    ok += 1
    print("[OK]   agency (runtime)")
except Exception as e:
    fail += 1
    print(f"[FAIL] agency: {e}")
print(f"smoke: ok={ok} fail={fail}")
sys.exit(0 if fail == 0 else 1)
'@
        $smokeFile = Join-Path $env:TEMP "_jarvis_smoke.py"
        $smoke | Out-File $smokeFile -Encoding utf8
        & $venvPy $smokeFile
        Remove-Item $smokeFile -ErrorAction SilentlyContinue
    }

    Write-Host ""
    Write-Host "========== SETUP COMPLETE ==========" -ForegroundColor Green
    Write-Host "Activate venv: .\.venv\Scripts\Activate.ps1"
    Write-Host "Run agency CLI: agency list"
    Write-Host "Run jarvis_brainiac: python -m jarvis_brainiac"
} finally {
    Pop-Location
}
