#!/usr/bin/env pwsh
# JARVIS Pass 11 — run tests, commit, push
# Usage: .\JARVIS_PUSH_P11.ps1

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Write-Host "=== JARVIS Pass 11 Push Script ===" -ForegroundColor Cyan

# ── 1. Run tests ────────────────────────────────────────────────────────────
Write-Host "`n[1/3] Running pytest..." -ForegroundColor Yellow
Push-Location "$PSScriptRoot\runtime"
try {
    python -m pytest tests/ -q --tb=short --timeout=60
    if ($LASTEXITCODE -ne 0) {
        Write-Host "TESTS FAILED (exit $LASTEXITCODE) — aborting push." -ForegroundColor Red
        exit $LASTEXITCODE
    }
} finally {
    Pop-Location
}
Write-Host "All tests passed." -ForegroundColor Green

# ── 2. Stage all changes ─────────────────────────────────────────────────────
Write-Host "`n[2/3] Staging changes..." -ForegroundColor Yellow
Push-Location $PSScriptRoot
git add -A
Write-Host "Staged files:" -ForegroundColor Gray
git diff --cached --name-only

# ── 3. Commit & push ─────────────────────────────────────────────────────────
Write-Host "`n[3/3] Committing and pushing..." -ForegroundColor Yellow
git commit -m "feat(jarvis): Pass 11 — httpx streaming fix, --model flag, API smoke test"
git push

Write-Host "`nDone." -ForegroundColor Green
Pop-Location
