<#
.SYNOPSIS
    JARVIS Pass 6 — pre-push verification and commit script.
.DESCRIPTION
    Runs the full test suite, aborts on any failure, then commits and pushes.
    Run from the repo root: .\JARVIS_PUSH_P6.ps1
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RuntimeDir = Join-Path $RepoRoot "runtime"

Write-Host "=== JARVIS Push P6 ===" -ForegroundColor Cyan
Write-Host "Repo: $RepoRoot"
Write-Host "Runtime: $RuntimeDir"

# 1. Verify Python
Write-Host "`n[1/4] Checking Python..." -ForegroundColor Yellow
$py = python --version 2>&1
Write-Host "  $py"

# 2. Full test suite
Write-Host "`n[2/4] Running full test suite..." -ForegroundColor Yellow
Push-Location $RuntimeDir
try {
    python -m pytest tests/ -q --tb=short
    if ($LASTEXITCODE -ne 0) {
        Write-Host "TESTS FAILED — aborting push." -ForegroundColor Red
        exit 1
    }
} finally {
    Pop-Location
}
Write-Host "  All tests passed." -ForegroundColor Green

# 3. Git status
Write-Host "`n[3/4] Git status..." -ForegroundColor Yellow
Push-Location $RepoRoot
try {
    git status --short
    git add -A
    $msg = "pass6: security, edge-cases, robustness, caplog isolation fix"
    git commit -m $msg
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Nothing to commit or commit failed." -ForegroundColor Yellow
    } else {
        Write-Host "  Committed: $msg" -ForegroundColor Green
    }

    # 4. Push
    Write-Host "`n[4/4] Pushing..." -ForegroundColor Yellow
    git push
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Push failed." -ForegroundColor Red
        exit 1
    }
    Write-Host "  Pushed." -ForegroundColor Green
} finally {
    Pop-Location
}

Write-Host "`n=== Done ===" -ForegroundColor Cyan
