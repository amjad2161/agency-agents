# JARVIS_PUSH_P16.ps1
# Pass 16 — structured logging, tracing, profiling, audit log
# Commit: feat(jarvis): Pass 16 — structured logging, tracing, profiling, audit log

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $RepoRoot

Write-Host "=== JARVIS Pass 16 — Deploy ===" -ForegroundColor Cyan

# ---------------------------------------------------------------------------
# 1. Verify new modules exist
# ---------------------------------------------------------------------------
$required = @(
    "runtime\agency\logging_config.py",
    "runtime\agency\tracing.py",
    "runtime\agency\profiler.py",
    "runtime\agency\audit.py"
)
foreach ($f in $required) {
    if (-not (Test-Path $f)) {
        Write-Error "Missing required file: $f"
        exit 1
    }
}
Write-Host "[OK] All new modules present" -ForegroundColor Green

# ---------------------------------------------------------------------------
# 2. Run Pass 16 tests
# ---------------------------------------------------------------------------
Write-Host "`nRunning Pass 16 tests..." -ForegroundColor Yellow
$env:PYTHONPYCACHEPREFIX = "/tmp/fresh_pycache"
Push-Location "$RepoRoot\runtime"
try {
    python -m pytest tests/test_jarvis_pass16.py -q --tb=short --timeout=60
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Pass 16 tests FAILED — aborting push."
        exit 1
    }
} finally {
    Pop-Location
}
Write-Host "[OK] All Pass 16 tests passed" -ForegroundColor Green

# ---------------------------------------------------------------------------
# 3. Quick smoke test — import all new modules
# ---------------------------------------------------------------------------
Write-Host "`nSmoke-testing imports..." -ForegroundColor Yellow
Push-Location "$RepoRoot\runtime"
try {
    python -c @"
from agency.logging_config import setup_logging, get_logger, set_session_id
from agency.tracing import Tracer, get_tracer, new_tracer, load_spans, Span
from agency.profiler import profile_call, top_slowest, export_speedscope, get_store
from agency.audit import log_event, log_shell, log_api_call, verify_integrity, load_entries, AuditEvent
print('All Pass 16 imports OK')
"@
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Import smoke test failed."
        exit 1
    }
} finally {
    Pop-Location
}
Write-Host "[OK] Imports smoke test passed" -ForegroundColor Green

# ---------------------------------------------------------------------------
# 4. Git commit
# ---------------------------------------------------------------------------
Write-Host "`nCommitting..." -ForegroundColor Yellow
git add runtime/agency/logging_config.py `
       runtime/agency/tracing.py `
       runtime/agency/profiler.py `
       runtime/agency/audit.py `
       runtime/agency/cli.py `
       runtime/tests/test_jarvis_pass16.py `
       JARVIS_PUSH_P16.ps1

git commit -m "feat(jarvis): Pass 16 — structured logging, tracing, profiling, audit log

- logging_config.py: setup_logging(level, format=json|pretty)
  JSON fields: timestamp, level, logger, message, session_id, duration_ms
  Pretty formatter with ANSI colours for dev terminals
  Idempotent setup; get_logger(); set_session_id(); timed_structured()

- tracing.py: Span dataclass + Tracer context manager
  Writes completed spans to ~/.agency/traces/YYYY-MM-DD.jsonl
  get_tracer() / new_tracer(); load_spans(date, limit); list_trace_dates()
  Error recorded in span.error on exception; span still persisted

- profiler.py: @profile_call decorator (bare and with args)
  In-memory ring-buffer (_SampleStore, 10k samples, thread-safe)
  top_slowest(n) aggregates by operation name (mean + max)
  export_speedscope() → ~/.agency/profile.json (Speedscope format)

- audit.py: append-only chain-hash audit log (~/.agency/audit.jsonl)
  Events: shell.execute, api.call, plugin.install, plugin.remove, config.change
  verify_integrity() re-derives every SHA-256 chain hash
  load_entries(tail=N); convenience wrappers (log_shell, log_api_call, …)

- cli.py: agency traces list/show, agency profile-perf show/flamegraph,
  agency audit show/verify/path

- 47 tests in test_jarvis_pass16.py (all passing)"

if ($LASTEXITCODE -ne 0) {
    Write-Warning "git commit returned non-zero (nothing to commit, or error)."
}

# ---------------------------------------------------------------------------
# 5. Push
# ---------------------------------------------------------------------------
Write-Host "`nPushing to origin..." -ForegroundColor Yellow
git push origin HEAD
if ($LASTEXITCODE -ne 0) {
    Write-Error "git push failed."
    exit 1
}

Write-Host "`n=== Pass 16 deployed successfully ===" -ForegroundColor Green
Write-Host @"

New modules:
  runtime/agency/logging_config.py   structured JSON/pretty logger
  runtime/agency/tracing.py          Span + Tracer + JSONL traces
  runtime/agency/profiler.py         @profile_call + Speedscope export
  runtime/agency/audit.py            append-only chain-hash audit log

CLI commands added:
  agency traces list/show
  agency profile-perf show/flamegraph
  agency audit show/verify/path

Tests: 47 passed (test_jarvis_pass16.py)
"@
