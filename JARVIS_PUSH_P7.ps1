# JARVIS_PUSH_P7.ps1
# Pass 7: Performance + Documentation + Production Hardening
# Kill lock, stage all, commit, push.

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Write-Host "=== JARVIS PUSH P7 ===" -ForegroundColor Cyan

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
feat(jarvis): Pass 7 — perf + docs + production hardening, 41 new tests

Performance:
- jarvis_brain: cache lowercased skill fields at init (_skill_texts list)
  eliminates 4xN .lower() calls per route(); was 26,100 calls/20 requests
- jarvis_brain: pre-filter KEYWORD_SLUG_BOOST keys against request string
  before inner skill loop; reduces O(191x323)=61,693 to O(191+matched x323)
- vector_memory: batch IDF query (N serial SELECT -> 1 IN() GROUP BY)
  eliminates per-term round-trips to SQLite for every search() call
- Result: single route() 3.4ms, 50 varied calls 214ms total

Benchmark (323 skills, 191 boost keys):
  100 identical calls: 631ms (6.3ms/call)
  50 varied calls:    214ms (4.3ms/call)
  single call:          3.4ms

Documentation (14 public functions gained docstrings):
- jarvis_brain: RouteResult.to_dict(), by_slug()
- vector_memory: delete(), clear(), count(), get(), all_ids(), close()
- skills: summary(), SkillRegistry.load(), all(), by_slug(), by_category(), categories()
- trust: trust_conf_path(), gate()
- memory: Session.append(), MemoryStore.load(), MemoryStore.save()

Tests (runtime/tests/test_jarvis_p7_perf.py, 41 tests, all pass):
- TestRoutingPerformance: 100x<5s, 50 varied <5s, single <100ms
- TestBoostPreFilter: correctness, determinism, edge cases
- TestRoutingCorrectness: score, sorted, top_k, by_slug, empty raises, to_dict
- TestVectorMemory: search, batched IDF, count, get, delete, clear, all_ids, close
- TestPublicAPI: 6 import smoke tests
- TestCLI: help exits 0, mentions run, list exits 0
- TestProjectConfig: requires-python, entry point, deps, dev extras

pyproject.toml verified: requires-python>=3.10, agency=agency.cli:main,
  anthropic dep present, pytest in dev optional-dependencies
"@

Write-Host "`nCommitting..." -ForegroundColor Cyan
git -C $PSScriptRoot commit -m $msg

# Push
Write-Host "`nPushing..." -ForegroundColor Cyan
git -C $PSScriptRoot push

Write-Host "`n=== P7 PUSHED ===" -ForegroundColor Green
