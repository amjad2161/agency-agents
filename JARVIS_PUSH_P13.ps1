# JARVIS_PUSH_P13.ps1
# Pass 13 — batch mode, skill hot-reload, export, dead-letter queue
# Run from repo root: .\JARVIS_PUSH_P13.ps1

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RepoRoot

Write-Host "=== JARVIS Pass 13 — pre-push checks ===" -ForegroundColor Cyan

# 1. Verify new modules exist
$modules = @(
    "runtime\agency\batch.py",
    "runtime\agency\dlq.py",
    "runtime\agency\export.py"
)
foreach ($m in $modules) {
    if (-not (Test-Path $m)) {
        Write-Error "Missing module: $m"
        exit 1
    }
    Write-Host "  ✓ $m" -ForegroundColor Green
}

# 2. Verify SkillWatcher is in skills.py
$skillsContent = Get-Content "runtime\agency\skills.py" -Raw
if ($skillsContent -notmatch "class SkillWatcher") {
    Write-Error "SkillWatcher not found in runtime\agency\skills.py"
    exit 1
}
Write-Host "  ✓ SkillWatcher in skills.py" -ForegroundColor Green

# 3. Verify CLI commands were added
$cliContent = Get-Content "runtime\agency\cli.py" -Raw
foreach ($cmd in @("batch_cmd", "export_cmd", "dlq_cmd")) {
    if ($cliContent -notmatch $cmd) {
        Write-Error "CLI command missing: $cmd"
        exit 1
    }
    Write-Host "  ✓ CLI: $cmd" -ForegroundColor Green
}

# 4. Run Pass 13 tests
Write-Host "`nRunning tests..." -ForegroundColor Cyan
Push-Location "runtime"
try {
    $env:PYTHONPYCACHEPREFIX = "/tmp/fresh_pycache"
    python -m pytest tests/test_jarvis_pass13.py -q --tb=short --timeout=60
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Tests failed (exit $LASTEXITCODE)"
        exit 1
    }
} finally {
    Pop-Location
}
Write-Host "  ✓ All Pass 13 tests green" -ForegroundColor Green

# 5. Git commit & push
Write-Host "`nCommitting..." -ForegroundColor Cyan
git add -A
git commit -m "feat(jarvis): Pass 13 — batch mode, skill hot-reload, export, dead-letter queue"
git push

Write-Host "`n=== Pass 13 pushed successfully ===" -ForegroundColor Green
