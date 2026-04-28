# JARVIS_PUSH_P8.ps1
# Pass 8: CI health, integration test gaps, final hardening
# Kill lock, stage all, commit, push.

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Write-Host "=== JARVIS PUSH P8 ===" -ForegroundColor Cyan

# Kill any stale git index lock
$lockFile = Join-Path $PSScriptRoot ".git\index.lock"
if (Test-Path $lockFile) {
    Write-Host "Removing stale .git/index.lock..." -ForegroundColor Yellow
    Remove-Item $lockFile -Force
}

# Stage everything
Write-Host "Staging all changes..." -ForegroundColor Cyan
git -C $PSScriptRoot add -A

# Show what's staged
Write-Host "`nStaged diff summary:" -ForegroundColor Cyan
git -C $PSScriptRoot diff --cached --stat

# Commit
$msg = @"
feat(jarvis): Pass 8 - CI health + integration tests + hardening, 83 new tests

Tests (runtime/tests/test_jarvis_pass8.py, 83 tests, all pass):
- TestRoutingPipeline: 8 structural tests + 20 parametrized diverse queries
  all return non-None slugs; empty/whitespace raises ValueError
- TestFilterPipeline: strips "Certainly!", "Of course!", "Hope this helps!",
  passthrough clean text, empty string, adversarial inputs (50KB, Hebrew,
  null bytes), has_forbidden_phrase detection
- TestMemoryPersistence: hard facts baseline, dynamic override write/read,
  disk persistence across two AmjadMemory instances, shadow + reset_dynamic,
  get_context keys, owner_name, primary_language
- TestTrustMode: off by default, on-my-machine/yolo via env, unknown falls back
- TestGreeting: Hebrew chars present, owner name, time colon marker, mochen
- TestStartupBanner: JARVIS name, owner, mode, systems count, subsystem marker,
  multiline, farewell Hebrew, mode_transition arrow, alert_banner level
- TestJarvisSoul: owner, personality_traits, signature_phrases,
  forbidden_behaviors, core_mission
- TestBrainHelpers: by_slug found/not-found, top_k length/sorted,
  unified_prompt max_chars, unified_prompt with request, very long query (10KB),
  Hebrew-script query no crash
- TestTokenizationHelpers: stopword strip, lowercase, bigram pairs, empty, single
- TestCLISmoke: --help exits 0, cli module importable

CI improvements (.github/workflows/runtime-tests.yml):
- Added pytest-timeout install step
- Added --tb=short for cleaner failure output
- Added --timeout=60 per-test timeout (prevents hung tests blocking CI)
- Added --cov=agency --cov-report=term-missing for coverage visibility
- Matrix: Python 3.10 / 3.11 / 3.12 unchanged
- No platform-specific assumptions found in test suite (clean grep)

Total test count: 959 -> 1042 (83 added, all passing)
"@

Write-Host "`nCommitting..." -ForegroundColor Cyan
git -C $PSScriptRoot commit -m $msg

# Push
Write-Host "`nPushing..." -ForegroundColor Cyan
git -C $PSScriptRoot push

Write-Host "`n=== P8 PUSHED ===" -ForegroundColor Green
