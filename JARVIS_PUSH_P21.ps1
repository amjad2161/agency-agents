# JARVIS_PUSH_P21.ps1 — Pass 21: Code Gen REPL, Self-Improvement, ROS2 Bridge, Balance Controller, Emotions
# Run from repo root: .\JARVIS_PUSH_P21.ps1

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RepoRoot

Write-Host "=== JARVIS Pass 21 — Pre-flight checks ===" -ForegroundColor Cyan

# Verify new files exist
$RequiredFiles = @(
    "runtime\agency\code_repl.py",
    "runtime\agency\self_improver.py",
    "runtime\agency\robotics\ros2_bridge.py",
    "runtime\agency\robotics\balance.py",
    "runtime\agency\emotion_state.py",
    "runtime\tests\test_jarvis_pass21.py"
)
foreach ($f in $RequiredFiles) {
    if (-not (Test-Path $f)) {
        Write-Error "Missing: $f"
        exit 1
    }
    Write-Host "  OK  $f" -ForegroundColor Green
}

Write-Host ""
Write-Host "=== Running Pass 21 tests ===" -ForegroundColor Cyan
Set-Location "$RepoRoot\runtime"
$env:PYTHONPYCACHEPREFIX = "/tmp/fresh_pycache"

$result = & python -m pytest tests/test_jarvis_pass21.py -q --tb=short --timeout=60 2>&1
Write-Host $result
if ($LASTEXITCODE -ne 0) {
    Write-Error "Tests FAILED — aborting push."
    exit 1
}
Write-Host "All tests PASSED." -ForegroundColor Green

Set-Location $RepoRoot

Write-Host ""
Write-Host "=== Git commit ===" -ForegroundColor Cyan
git add runtime/agency/code_repl.py `
       runtime/agency/self_improver.py `
       runtime/agency/robotics/ros2_bridge.py `
       runtime/agency/robotics/balance.py `
       runtime/agency/emotion_state.py `
       runtime/tests/test_jarvis_pass21.py `
       JARVIS_PUSH_P21.ps1

git commit -m "feat(jarvis): Pass 21 — code gen REPL, self-improvement, ROS2 bridge, balance controller, emotions"

Write-Host ""
Write-Host "=== Git push ===" -ForegroundColor Cyan
git push

Write-Host ""
Write-Host "=== Pass 21 complete ===" -ForegroundColor Green
Write-Host "  code_repl.py      — sandboxed Python REPL + generate_and_run"
Write-Host "  self_improver.py  — trace-driven routing auto-improver"
Write-Host "  ros2_bridge.py    — ROS2 bridge with MockROS2Bridge fallback"
Write-Host "  balance.py        — CoM/ZMP PID + sinusoidal gait generator"
Write-Host "  emotion_state.py  — 6-state emotion model with Hebrew phrases"
Write-Host "  66 tests passing"
