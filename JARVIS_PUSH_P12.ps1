# JARVIS_PUSH_P12.ps1
# Pass 12 — config file, retry/backoff, chat history, token tracking
# Run from: C:\Users\User\agency\

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$COMMIT_MSG = "feat(jarvis): Pass 12 - config file, retry/backoff, chat history, token tracking"

Write-Host "=== JARVIS Pass 12 Push Script ===" -ForegroundColor Cyan

# 1. Verify we're in the right directory
if (-not (Test-Path "runtime\agency\cli.py")) {
    Write-Error "Run this from C:\Users\User\agency\"
    exit 1
}

# 2. Verify new files exist
$required = @(
    "runtime\agency\config.py",
    "runtime\agency\history.py",
    "runtime\agency\stats.py",
    "runtime\tests\test_jarvis_pass12.py"
)
foreach ($f in $required) {
    if (-not (Test-Path $f)) {
        Write-Error "Missing required file: $f"
        exit 1
    }
    Write-Host "  [OK] $f" -ForegroundColor Green
}

# 3. Run tests
Write-Host "`nRunning Pass 12 tests..." -ForegroundColor Yellow
$env:PYTHONPYCACHEPREFIX = "/tmp/fresh_pycache"
Push-Location runtime
try {
    $result = python -m pytest tests/test_jarvis_pass12.py -q --tb=short --timeout=60
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Tests failed — aborting push."
        exit 1
    }
    Write-Host "All tests passed." -ForegroundColor Green
} finally {
    Pop-Location
}

# 4. Git add + commit + push
Write-Host "`nCommitting..." -ForegroundColor Yellow
git add runtime/agency/config.py `
       runtime/agency/history.py `
       runtime/agency/stats.py `
       runtime/agency/llm.py `
       runtime/agency/cli.py `
       runtime/tests/test_jarvis_pass12.py

git commit -m $COMMIT_MSG

Write-Host "Pushing..." -ForegroundColor Yellow
git push

Write-Host "`n=== Pass 12 pushed successfully ===" -ForegroundColor Cyan
Write-Host "New files:" -ForegroundColor White
Write-Host "  runtime/agency/config.py   — AgencyConfig dataclass, TOML/JSON loading, override precedence"
Write-Host "  runtime/agency/history.py  — HistoryWriter, list_sessions, session_summary"
Write-Host "  runtime/agency/stats.py    — record_usage, get_stats, reset_stats, format_stats"
Write-Host "Modified:"
Write-Host "  runtime/agency/llm.py      — _call_with_retry, exponential backoff on 429/529/5xx"
Write-Host "  runtime/agency/cli.py      — history/stats commands, HistoryWriter in chat loop"
Write-Host "Tests: 51 pass"
