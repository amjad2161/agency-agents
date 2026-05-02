#!/usr/bin/env pwsh
# JARVIS_PUSH_P19.ps1
# Commit and push Pass 19 — Humanoid Robot Brain Integration
# Run from: C:\Users\User\agency

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$REPO = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $REPO

Write-Host "=== JARVIS Pass 19 — Humanoid Robot Brain ===" -ForegroundColor Cyan

# ── 1. Verify new files exist ─────────────────────────────────────────────
$required = @(
    "runtime\agency\robotics\__init__.py"
    "runtime\agency\robotics\simulation.py"
    "runtime\agency\robotics\motion_skills.py"
    "runtime\agency\robotics\nlp_to_motion.py"
    "runtime\agency\robotics\stt.py"
    "runtime\agency\robotics\rl_trainer.py"
    "runtime\agency\robotics\vision_perception.py"
    "runtime\agency\robotics\robot_brain.py"
    "runtime\agency\robotics\HUMANOID_SETUP.md"
    "runtime\tests\test_jarvis_pass19.py"
)

foreach ($f in $required) {
    if (-not (Test-Path (Join-Path $REPO $f))) {
        Write-Error "Missing required file: $f"
        exit 1
    }
    Write-Host "  ✅ $f" -ForegroundColor Green
}

# ── 2. Run the test suite ─────────────────────────────────────────────────
Write-Host "`n=== Running Pass 19 tests ===" -ForegroundColor Cyan

$env:PYTHONPYCACHEPREFIX = "/tmp/fresh_pycache"
Push-Location "$REPO\runtime"
try {
    python -m pytest tests/test_jarvis_pass19.py -v --tb=short --timeout=60
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Tests FAILED — aborting push."
        exit 1
    }
} finally {
    Pop-Location
}

Write-Host "`n✅ All tests passed" -ForegroundColor Green

# ── 3. Git add & commit ────────────────────────────────────────────────────
Write-Host "`n=== Committing ===" -ForegroundColor Cyan

git add runtime/agency/robotics/
git add runtime/agency/cli.py
git add runtime/tests/test_jarvis_pass19.py
git add JARVIS_PUSH_P19.ps1

git status --short

$msg = "feat(jarvis): Pass 19 - humanoid robot brain, simulation bridge, STT, YOLO vision, RL trainer"
git commit -m $msg

Write-Host "`n=== Pushing ===" -ForegroundColor Cyan
git push

Write-Host "`n🤖 JARVIS Pass 19 deployed successfully!" -ForegroundColor Magenta
Write-Host "   Files: $($required.Count) new robotics modules" -ForegroundColor White
Write-Host "   CLI:   agency robotics start|stop|status|exec|listen|train" -ForegroundColor White
