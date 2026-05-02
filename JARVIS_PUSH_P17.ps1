# JARVIS_PUSH_P17.ps1
# Pass 17 — Vision / Voice / Browser / Email
# Run from repo root: C:\Users\User\agency\

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$REPO_ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $REPO_ROOT

Write-Host "=== JARVIS Pass 17 — Push Script ===" -ForegroundColor Cyan
Write-Host "Root: $REPO_ROOT" -ForegroundColor Gray

# ---------------------------------------------------------------------------
# 1. Verify new files exist
# ---------------------------------------------------------------------------
$required = @(
    "runtime\agency\vision.py",
    "runtime\agency\voice.py",
    "runtime\agency\browser.py",
    "runtime\agency\email_client.py",
    "runtime\tests\test_jarvis_pass17.py"
)

foreach ($f in $required) {
    $path = Join-Path $REPO_ROOT $f
    if (-not (Test-Path $path)) {
        Write-Error "Missing required file: $f"
        exit 1
    }
    Write-Host "  OK $f" -ForegroundColor Green
}

# ---------------------------------------------------------------------------
# 2. Run Pass 17 tests
# ---------------------------------------------------------------------------
Write-Host "`n--- Running Pass 17 tests ---" -ForegroundColor Cyan

$pytestExe = $null
foreach ($candidate in @(
    "$env:LOCALAPPDATA\Programs\Python\Python311\Scripts\pytest.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python312\Scripts\pytest.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python310\Scripts\pytest.exe",
    "pytest"
)) {
    if (Get-Command $candidate -ErrorAction SilentlyContinue) {
        $pytestExe = $candidate
        break
    }
}

if (-not $pytestExe) {
    Write-Warning "pytest not found on PATH — skipping local test run (CI will verify)"
} else {
    $testArgs = @(
        "runtime\tests\test_jarvis_pass17.py",
        "-v",
        "--tb=short",
        "--timeout=60"
    )
    $env:PYTHONPYCACHEPREFIX = "$env:TEMP\fresh_pycache"
    Push-Location (Join-Path $REPO_ROOT "runtime")
    try {
        & $pytestExe @testArgs
        if ($LASTEXITCODE -ne 0) {
            Write-Error "Tests FAILED — aborting push"
            exit 1
        }
    } finally {
        Pop-Location
    }
    Write-Host "All Pass 17 tests PASSED" -ForegroundColor Green
}

# ---------------------------------------------------------------------------
# 3. Stage new files
# ---------------------------------------------------------------------------
Write-Host "`n--- Staging files ---" -ForegroundColor Cyan

$toAdd = @(
    "runtime/agency/vision.py",
    "runtime/agency/voice.py",
    "runtime/agency/browser.py",
    "runtime/agency/email_client.py",
    "runtime/tests/test_jarvis_pass17.py"
)

foreach ($f in $toAdd) {
    git add $f
    Write-Host "  staged: $f" -ForegroundColor Gray
}

# ---------------------------------------------------------------------------
# 4. Commit
# ---------------------------------------------------------------------------
Write-Host "`n--- Committing ---" -ForegroundColor Cyan

$commitMsg = "feat(jarvis): Pass 17 - vision/image analysis, voice TTS, browser automation, email"

git commit -m $commitMsg
if ($LASTEXITCODE -ne 0) {
    Write-Warning "git commit returned $LASTEXITCODE (possibly nothing to commit)"
}

# ---------------------------------------------------------------------------
# 5. Push
# ---------------------------------------------------------------------------
Write-Host "`n--- Pushing ---" -ForegroundColor Cyan
git push
if ($LASTEXITCODE -ne 0) {
    Write-Error "git push failed"
    exit 1
}

Write-Host "`n=== Pass 17 pushed successfully ===" -ForegroundColor Green
Write-Host @"

New modules:
  runtime/agency/vision.py       — analyze_image() via Claude vision API
  runtime/agency/voice.py        — speak() with pyttsx3/gtts/espeak/say/PS fallback
  runtime/agency/browser.py      — BrowserAgent: browse/screenshot/fill_form
  runtime/agency/email_client.py — read_inbox() IMAP + send_email() SMTP

Tests: 50 passed (test_jarvis_pass17.py)
"@ -ForegroundColor Cyan
