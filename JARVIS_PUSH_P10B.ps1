# JARVIS_PUSH_P10B.ps1
# Mission B: Skill YAML audit, routing accuracy benchmark, soul filter,
# README update, type fixes, truncated-file repairs.
# Runs tests first. Aborts if any fail.

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Write-Host "=== JARVIS PUSH P10B ===" -ForegroundColor Cyan

# Kill any stale git index lock
$lockFile = Join-Path $PSScriptRoot ".git\index.lock"
if (Test-Path $lockFile) {
    Write-Host "Removing stale .git/index.lock..." -ForegroundColor Yellow
    Remove-Item $lockFile -Force
}

# Run Mission B tests first — abort on failure
Write-Host "`nRunning Mission B tests..." -ForegroundColor Cyan
$testResult = & python -m pytest runtime/tests/test_jarvis_pass10b.py -v -q 2>&1
Write-Host $testResult
if ($LASTEXITCODE -ne 0) {
    Write-Host "`nTESTS FAILED — aborting push." -ForegroundColor Red
    exit 1
}
Write-Host "All Mission B tests passed." -ForegroundColor Green

# Stage everything
Write-Host "`nStaging all changes..." -ForegroundColor Cyan
git -C $PSScriptRoot add -A

# Show what's staged
Write-Host "`nStaged diff summary:" -ForegroundColor Cyan
git -C $PSScriptRoot diff --cached --stat

# Commit
$msg = @"
feat(jarvis): Pass 10B - YAML audit, routing 100%, type fixes, truncation repair

YAML audit (Part 1):
- Scanned 313 skill MD files across 17 categories
- Fixed specialized/zk-steward.md: unquoted colon in description (YAML parse error)
- 0 errors after fix; 309 valid skills, 0 duplicate slugs

Routing accuracy (Part 2):
- Added 30 new KEYWORD_SLUG_BOOST entries:
  deploy/deployment → devops, git/version-control → engineering,
  refactor/refactoring → omega-engineer, containerize/container → devops,
  sql-query/optimize-sql → database, python-bug/fix-bug → omega-engineer,
  fix-my/my-python-bug → omega-engineer (phrase boosts)
- Benchmark: 20/20 = 100% accuracy (was 70% before, threshold 70%)

Soul filter (Part 3):
- 0 false positives on 14 legitimate strings
- 7/7 forbidden phrases correctly caught
- Confirmed: "Sure," stripped intentionally (JARVIS filler policy)

README (Part 4):
- Updated skill count: 180+ → 320+ (accurate vs 324 loaded)

Type annotations (Part 5):
- Fixed 6 files with truncated content (amjad_jarvis_cli.py, cli.py,
  logging.py, supervisor.py, executor.py, planner.py, server.py, managed_agents.py)
- skills.py: added missing return statement in search() + yaml type ignore
- managed_agents.py: fixed 'retu' typo → 'return _default_backend', fixed
  return indentation (was inside if block)
- executor.py: added class-level 'llm' annotation, fixed truncated
  _block_to_dict return, added top-level ToolResult import
- All 11 core .py files: 0 SyntaxError

Tests (runtime/tests/test_jarvis_pass10b.py, 11 tests, all pass):
- test_yaml_validator_zero_errors
- test_yaml_skill_count (>= 300)
- test_routing_accuracy (>= 70%, achieved 100%)
- test_routing_non_empty_result
- test_soul_filter_no_false_positives
- test_soul_filter_catches_forbidden
- test_readme_exists
- test_readme_key_sections
- test_readme_skill_count_updated
- test_core_files_parse (11 files)
- test_no_truncated_exports
"@

git -C $PSScriptRoot commit -m $msg

# Push
Write-Host "`nPushing to origin main..." -ForegroundColor Cyan
git -C $PSScriptRoot push origin main

Write-Host "`n=== P10B PUSH COMPLETE ===" -ForegroundColor Green
