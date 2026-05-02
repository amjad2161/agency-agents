# JARVIS_PUSH_P18.ps1
# Pass 18 — Long-term memory, self-learning, cron scheduler, context builder
# Run from repo root: .\JARVIS_PUSH_P18.ps1

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $repoRoot

Write-Host "=== JARVIS Pass 18 — Pre-flight ===" -ForegroundColor Cyan

# -----------------------------------------------------------------------
# 1. Run tests
# -----------------------------------------------------------------------
Write-Host "`n[1/3] Running Pass 18 tests..." -ForegroundColor Yellow

$env:PYTHONPYCACHEPREFIX = "/tmp/fresh_pycache"

Push-Location "$repoRoot\runtime"
try {
    python -m pytest tests/test_jarvis_pass18.py -v --tb=short --timeout=60
    if ($LASTEXITCODE -ne 0) {
        Write-Host "TESTS FAILED — aborting push." -ForegroundColor Red
        exit 1
    }
} finally {
    Pop-Location
}

Write-Host "`n[1/3] All tests passed." -ForegroundColor Green

# -----------------------------------------------------------------------
# 2. Stage new/modified files
# -----------------------------------------------------------------------
Write-Host "`n[2/3] Staging files..." -ForegroundColor Yellow

$filesToAdd = @(
    "runtime/agency/long_term_memory.py",
    "runtime/agency/learner.py",
    "runtime/agency/scheduler.py",
    "runtime/agency/context_builder.py",
    "runtime/tests/test_jarvis_pass18.py"
)

foreach ($f in $filesToAdd) {
    git add $f
    Write-Host "  + $f"
}

# -----------------------------------------------------------------------
# 3. Commit & push
# -----------------------------------------------------------------------
Write-Host "`n[3/3] Committing and pushing..." -ForegroundColor Yellow

$commitMsg = "feat(jarvis): Pass 18 — long-term memory, self-learning, cron scheduler, context builder"
git commit -m $commitMsg

git push

Write-Host "`n=== Pass 18 shipped successfully! ===" -ForegroundColor Green
Write-Host "New modules:" -ForegroundColor Cyan
Write-Host "  agency/long_term_memory.py  — SQLite FTS5 semantic memory"
Write-Host "  agency/learner.py           — regex fact extraction + LLM-optional"
Write-Host "  agency/scheduler.py         — 5-field cron parser + background thread"
Write-Host "  agency/context_builder.py   — system prompt assembler with memories"
Write-Host "  tests/test_jarvis_pass18.py — 30 tests"
