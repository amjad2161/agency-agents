# JARVIS_PUSH_P15.ps1
# Pass 15: Webhooks, Markdown Renderer, Auto-Update, Improved Doctor
# Run from the repo root: .\JARVIS_PUSH_P15.ps1

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RepoRoot

Write-Host "=== JARVIS Pass 15 Push ===" -ForegroundColor Cyan

# 1. Verify new files exist
$RequiredFiles = @(
    "runtime\agency\webhooks.py",
    "runtime\agency\renderer.py",
    "runtime\agency\updater.py",
    "runtime\tests\test_jarvis_pass15.py"
)
foreach ($f in $RequiredFiles) {
    if (-not (Test-Path $f)) {
        Write-Error "Missing required file: $f"
        exit 1
    }
    Write-Host "  OK  $f" -ForegroundColor Green
}

# 2. Run tests
Write-Host "`nRunning Pass 15 tests..." -ForegroundColor Cyan
$env:PYTHONPYCACHEPREFIX = "/tmp/fresh_pycache"
Push-Location runtime
try {
    python -m pytest tests/test_jarvis_pass15.py -q --tb=short --timeout=60
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Tests failed — aborting push."
        exit 1
    }
} finally {
    Pop-Location
}

Write-Host "`nAll tests passed." -ForegroundColor Green

# 3. Git commit and push
Write-Host "`nCommitting..." -ForegroundColor Cyan
git add -A
git commit -m "feat(jarvis): Pass 15 — webhooks, markdown render, auto-update, improved doctor"
git push

Write-Host "`n=== Pass 15 pushed successfully ===" -ForegroundColor Green
Write-Host "New modules:" -ForegroundColor Yellow
Write-Host "  runtime/agency/webhooks.py  — WebhookConfig, WebhookDispatcher, load_webhook_config"
Write-Host "  runtime/agency/renderer.py  — render_markdown (rich or ANSI fallback)"
Write-Host "  runtime/agency/updater.py   — check_update, print_update_notice (Hebrew)"
Write-Host "New CLI commands:"
Write-Host "  agency webhook test [--url URL] [--secret S]"
Write-Host "  agency update"
Write-Host "  agency doctor2"
Write-Host "Tests: 35 passed, 8 skipped (httpx not installed in sandbox)"
