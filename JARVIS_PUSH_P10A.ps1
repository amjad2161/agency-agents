# JARVIS_PUSH_P10A.ps1
# Mission A: Shell execution skill + streaming responses
# Delivers: shell_skill.py, test_shell_skill.py, cli.py patches (--stream + Hebrew errors)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$REPO = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $REPO

Write-Host "=== JARVIS P10A pre-flight ===" -ForegroundColor Cyan

# 1. Verify new/modified files exist
$required = @(
    "runtime\agency\shell_skill.py",
    "runtime\tests\test_shell_skill.py",
    "runtime\agency\cli.py"
)
foreach ($f in $required) {
    if (-not (Test-Path "$REPO\$f")) {
        Write-Error "Missing: $f"
    }
    Write-Host "  [ok] $f"
}

# 2. Run full test suite
Write-Host "`n=== Running tests ===" -ForegroundColor Cyan
Push-Location "$REPO\runtime"
try {
    python -m pytest tests/ -x -q --tb=short 2>&1 | Tee-Object -Variable testOut
    $exitCode = $LASTEXITCODE
} finally {
    Pop-Location
}

if ($exitCode -ne 0) {
    Write-Error "Tests failed (exit $exitCode). Aborting push."
}

# Extract pass count from pytest output
$passLine = $testOut | Select-String -Pattern "\d+ passed"
Write-Host "`nTest result: $passLine" -ForegroundColor Green

# 3. Git operations
Write-Host "`n=== Git commit ===" -ForegroundColor Cyan
git add runtime/agency/shell_skill.py `
       runtime/tests/test_shell_skill.py `
       runtime/agency/cli.py `
       JARVIS_PUSH_P10A.ps1

git diff --cached --stat

$msg = "feat(p10a): shell_skill + streaming chat + Hebrew error messages

- runtime/agency/shell_skill.py: TrustMode-gated shell execution skill
  * OFF => Hebrew refusal message
  * ON_MY_MACHINE => SAFE_ALLOWLIST + trust.py denylist + extra patterns
  * YOLO => warning print + unrestricted execution
  * subprocess.run(capture_output=True, text=True, timeout=30)
  * every attempt logged via stdlib logging

- runtime/tests/test_shell_skill.py: 30+ parameterized tests
  * OFF/ON_MY_MACHINE/YOLO mode coverage
  * dangerous command blocking (rm -rf /, del /s, format C:)
  * timeout assertion (@pytest.mark.slow)
  * ShellResult property contracts
  * SAFE_ALLOWLIST membership checks

- runtime/agency/cli.py: streaming + Hebrew UX
  * agency chat --stream: uses executor.stream(), prints text_delta tokens live
  * 'No skills matched' -> 'לא נמצאו skills'
  * LLMError -> '[שגיאת חיבור] ... — בדוק את ה-API key'
  * JARVIS ERROR -> '[שגיאה] ...'
  * tool_result labels in Hebrew during streaming"

git commit -m $msg

git push

Write-Host "`n=== P10A push complete ===" -ForegroundColor Green
Write-Host "Deliverables:"
Write-Host "  shell_skill.py   TrustMode-gated execution, Hebrew OFF refusal"
Write-Host "  test_shell_skill.py  Full test coverage"
Write-Host "  cli.py           --stream flag + Hebrew error messages"
