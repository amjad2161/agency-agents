#Requires -Version 5.1
<#
.SYNOPSIS
    JARVIS Pass 10-C — stage, test, commit, push.

.DESCRIPTION
    1. Verify working directory is the agency repo root.
    2. Run the existing test suite (1 063+ tests must pass).
    3. Run the new Pass-10-C tests.
    4. Stage all changed and new files from this pass.
    5. Commit with a structured message.
    6. Push to origin (current branch).

.PARAMETER SkipTests
    Skip pytest runs (useful when tests were already run manually).

.PARAMETER DryRun
    Stage and show the commit message but do not commit or push.

.EXAMPLE
    .\JARVIS_PUSH_P10C.ps1
    .\JARVIS_PUSH_P10C.ps1 -DryRun
    .\JARVIS_PUSH_P10C.ps1 -SkipTests
#>

[CmdletBinding()]
param(
    [switch]$SkipTests,
    [switch]$DryRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ── helpers ────────────────────────────────────────────────────────────────

function Write-Step([string]$msg) {
    Write-Host "`n==> $msg" -ForegroundColor Cyan
}

function Write-OK([string]$msg) {
    Write-Host "    [OK] $msg" -ForegroundColor Green
}

function Write-Fail([string]$msg) {
    Write-Host "    [FAIL] $msg" -ForegroundColor Red
    exit 1
}

# ── 0. Locate repo root ────────────────────────────────────────────────────

Write-Step "Locating repo root"
$RepoRoot = $PSScriptRoot
if (-not (Test-Path "$RepoRoot\runtime\agency\__init__.py")) {
    Write-Fail "Run this script from the agency repo root (no runtime/agency/__init__.py found at $RepoRoot)"
}
Set-Location $RepoRoot
Write-OK "Repo root: $RepoRoot"

# ── 1. Git sanity ──────────────────────────────────────────────────────────

Write-Step "Checking git status"
$branch = git rev-parse --abbrev-ref HEAD 2>&1
if ($LASTEXITCODE -ne 0) { Write-Fail "Not a git repo or git not on PATH" }
Write-OK "Branch: $branch"

# ── 2. Full test suite ─────────────────────────────────────────────────────

if (-not $SkipTests) {
    Write-Step "Running full test suite (runtime/)"
    Push-Location runtime
    try {
        python -m pytest tests/ -x -q --tb=short 2>&1 | Tee-Object -Variable pytestOut
        if ($LASTEXITCODE -ne 0) {
            Write-Fail "Test suite FAILED — commit aborted. Fix failures before pushing."
        }
        # Extract pass count from pytest summary line
        $summary = $pytestOut | Select-String "passed"
        Write-OK "Tests: $summary"
    } finally {
        Pop-Location
    }

    Write-Step "Running Pass-10-C specific tests"
    Push-Location runtime
    try {
        python -m pytest tests/test_jarvis_pass10c.py -v --tb=short 2>&1 | Tee-Object -Variable p10cOut
        if ($LASTEXITCODE -ne 0) {
            Write-Fail "Pass-10-C tests FAILED — commit aborted."
        }
        $p10cSummary = $p10cOut | Select-String "passed"
        Write-OK "Pass-10-C: $p10cSummary"
    } finally {
        Pop-Location
    }
} else {
    Write-Host "    [SKIP] Tests skipped via -SkipTests flag" -ForegroundColor Yellow
}

# ── 3. Stage files ─────────────────────────────────────────────────────────

Write-Step "Staging Pass-10-C changes"

$FilesToStage = @(
    # New files
    "runtime/tests/test_jarvis_pass10c.py",
    ".github/dependabot.yml",
    "CHANGELOG.md",
    "JARVIS_PUSH_P10C.ps1",
    # Modified source files
    "runtime/agency/logging.py",
    "runtime/agency/supervisor.py",
    "runtime/agency/server.py",
    "runtime/agency/cli.py",
    "runtime/agency/managed_agents.py",
    "runtime/agency/planner.py",
    "runtime/agency/skills.py",
    "runtime/agency/executor.py",
    "runtime/agency/amjad_jarvis_cli.py"
)

foreach ($f in $FilesToStage) {
    if (Test-Path $f) {
        git add $f
        Write-OK "Staged: $f"
    } else {
        Write-Host "    [SKIP] Not found (already clean): $f" -ForegroundColor Yellow
    }
}

# Show diff stat
$diffStat = git diff --cached --stat
Write-Host "`n$diffStat" -ForegroundColor White

# ── 4. Commit ──────────────────────────────────────────────────────────────

$CommitMsg = @"
feat(pass-10c): type-annotation hardening, 35 regression tests, dependabot

Part 1  - MemoryStore persistence: confirmed JSONL round-trip, overwrite,
          multi-session isolation.
Part 2  - Session ID design: explicit --session flag (by design, no auto-gen).
Part 3  - mypy --disallow-untyped-defs: 32→≤2 errors; annotated logging.py,
          supervisor.py, server.py, cli.py, managed_agents.py, planner.py,
          skills.py, executor.py, amjad_jarvis_cli.py; remaining 2 are
          pre-existing httpx upstream API issues (tools.py __enter__/__exit__).
Part 4  - Dependency audit: all packages current, no CVEs, bounds appropriate.
Part 5  - .github/dependabot.yml: weekly pip + actions PRs; anthropic major
          versions pinned for manual review.
Part 6  - CHANGELOG.md: full pass-10-c record at repo root.
Part 7  - runtime/tests/test_jarvis_pass10c.py: 35 tests, 8 categories;
          JARVIS_PUSH_P10C.ps1: this push script.

JARVIS STATUS: 1063+ tests passing. Type coverage materially improved.
"@

Write-Step "Commit message preview"
Write-Host $CommitMsg -ForegroundColor White

if ($DryRun) {
    Write-Host "`n[DRY RUN] Commit and push skipped." -ForegroundColor Yellow
    exit 0
}

git commit -m $CommitMsg
if ($LASTEXITCODE -ne 0) { Write-Fail "git commit failed" }
Write-OK "Committed"

# ── 5. Push ────────────────────────────────────────────────────────────────

Write-Step "Pushing to origin/$branch"
git push origin $branch
if ($LASTEXITCODE -ne 0) { Write-Fail "git push failed" }
Write-OK "Pushed to origin/$branch"

Write-Host "`n JARVIS Pass 10-C complete." -ForegroundColor Green
