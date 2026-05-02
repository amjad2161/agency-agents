# ============================================================
#  JARVIS_PUSH_P20.ps1 — Commit & push Pass 20
# ============================================================

param(
    [string]$Branch  = "main",
    [string]$Remote  = "origin",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path

Set-Location $Root

Write-Host ""
Write-Host "  JARVIS — Pass 20 Git Push" -ForegroundColor Cyan
Write-Host "  ─────────────────────────" -ForegroundColor DarkGray
Write-Host ""

# ── 1. Show status ──────────────────────────────────────────
Write-Host "[ GIT STATUS ]" -ForegroundColor Yellow
git status --short
Write-Host ""

# ── 2. Stage Pass 20 files ──────────────────────────────────
Write-Host "[ STAGING ]" -ForegroundColor Yellow

$files = @(
    "runtime/agency/multi_agent.py",
    "runtime/agency/dashboard.py",
    "runtime/agency/installer.py",
    "runtime/agency/personality.py",
    "runtime/tests/test_jarvis_pass20.py",
    "JARVIS_LAUNCH.ps1",
    "JARVIS_PUSH_P20.ps1",
    "README.md"
)

foreach ($f in $files) {
    if (Test-Path (Join-Path $Root $f)) {
        git add $f
        Write-Host "  ✅  staged: $f" -ForegroundColor Green
    } else {
        Write-Host "  ⚠️  missing: $f" -ForegroundColor Yellow
    }
}

Write-Host ""

# ── 3. Run tests before commit ──────────────────────────────
Write-Host "[ RUNNING TESTS ]" -ForegroundColor Yellow
$PyCmd = "python"
$venv = Join-Path $Root "runtime\.venv\Scripts\python.exe"
if (Test-Path $venv) { $PyCmd = $venv }

Push-Location (Join-Path $Root "runtime")
$testResult = & $PyCmd -m pytest tests/test_jarvis_pass20.py -q --tb=short --timeout=60 2>&1
$exitCode = $LASTEXITCODE
Pop-Location

$testResult | ForEach-Object { Write-Host "  $_" -ForegroundColor DarkGray }

if ($exitCode -ne 0) {
    Write-Host ""
    Write-Host "  ❌  Tests FAILED — aborting push." -ForegroundColor Red
    exit 1
}
Write-Host "  ✅  All tests passed." -ForegroundColor Green
Write-Host ""

# ── 4. Commit ───────────────────────────────────────────────
Write-Host "[ COMMITTING ]" -ForegroundColor Yellow

$msg = "feat(jarvis): Pass 20 — multi-agent orchestration, GUI dashboard, installer, personality"

if ($DryRun) {
    Write-Host "  [DRY RUN] would commit: $msg"
} else {
    git commit -m $msg
    Write-Host "  ✅  Committed: $msg" -ForegroundColor Green
}

Write-Host ""

# ── 5. Push ─────────────────────────────────────────────────
Write-Host "[ PUSHING ]" -ForegroundColor Yellow

if ($DryRun) {
    Write-Host "  [DRY RUN] would push to $Remote/$Branch"
} else {
    git push $Remote $Branch
    Write-Host "  ✅  Pushed to $Remote/$Branch" -ForegroundColor Green
}

Write-Host ""
Write-Host "  ─────────────────────────────────────────" -ForegroundColor DarkGray
Write-Host "  Pass 20 delivered successfully." -ForegroundColor Cyan
Write-Host ""
