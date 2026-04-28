# JARVIS Pass 6 — Technical Report

**Date:** 2026-04-28  
**Scope:** Security, edge cases, robustness, production-readiness  
**Result:** 959 tests, 0 failures

---

## 1. What Was Tested (Pass 6)

| Section | Coverage |
|---|---|
| Planner brain-failure | Logs warning + falls back on RuntimeError/ValueError |
| Routing edge cases | empty, 10k-char, Hebrew, CJK/Arabic, whitespace, special chars, NUL/BEL control chars |
| Soul filter edge cases | empty, unicode, Hebrew, very long input, forbidden-phrase detection |
| Shell security | `allow_shell` off by default; `_run_shell` returns error when disabled; args passed as list not string; empty/whitespace commands rejected; nonexistent executables return error |
| ToolContext safe-path | `_safe_path` raises `PermissionError` on traversal outside workdir (both `../..` and absolute `/etc/passwd`) |
| Knowledge expansion error logging | `_store_chunk` logs WARNING on `vector_store.add` OSError and `context_manager.store` RuntimeError |
| SelfLearnerEngine snapshot import | malformed lessons logged+skipped; count reflects only valid; empty/missing key returns 0 |
| Supervisor shell safety | `shell=False` default in signature; list args; timeout kills process |

---

## 2. Bugs Fixed

### 2.1 `tests/conftest.py` — Trust-mode env pollution

**Root cause:** `test_jarvis_pass4.py::TestTrustMode::test_set_trust_mode` writes
`os.environ["AGENCY_TRUST_MODE"] = "on-my-machine"` directly (not via monkeypatch).
Old conftest guard `if "AGENCY_TRUST_MODE" not in os.environ: monkeypatch.delenv(...)` was
a no-op when the key was already present. Subsequent tests in `test_tools.py` ran with
`allow_shell=True`, breaking sandbox-enforcement assertions.

**Fix:** Replace monkeypatch-based cleanup with explicit `os.environ.pop()` before AND
after `yield`, saving and restoring original values directly:

```python
_trust_vars = ("AGENCY_TRUST_MODE", "AGENCY_ALLOW_SHELL")
_saved = {k: os.environ.pop(k, None) for k in _trust_vars}
yield
for k in _trust_vars:
    os.environ.pop(k, None)
    if _saved[k] is not None:
        os.environ[k] = _saved[k]
```

**Write-tool hazard:** The Write tool truncates files at em-dash (`—`) characters.
All multi-session file writes were done via `cat > file << 'HEREDOC'` in bash.

### 2.2 `tests/test_jarvis_pass6.py` — caplog propagation pollution

**Root cause:** `test_jarvis_pass5.py::TestDiagnostics::test_doctor_shows_agency_backend`
uses `click.testing.CliRunner().invoke(main, [...])`. During invocation, `main()` calls
`agency.logging.configure()`, which sets `agency_logger.propagate = False` and attaches a
`StreamHandler(sys.stderr)` where `sys.stderr` is CliRunner's internal buffer.
After CliRunner exits, the buffer is closed. The handler remains on the logger with a dead
stream, and `propagate=False` blocks caplog's `LogCaptureHandler` (installed on root).

**Symptom:** `"--- Logging error ---" + ValueError: I/O operation on closed file` on
stderr; `caplog.records` empty in the 4 affected tests.

**Why the original fixture didn't work:** The fixture set `propagate=True` in its setup
phase. However, tracing showed `propagate=False` was present during the test body despite
the fixture having run. The restore path in teardown also re-attached the stale handler
because `original_handlers` captured it from the polluted state of a prior run.

**Fix:** Patch `agency.logging.configure` (and `agency.cli.configure_logging`) inside the
fixture so any configure call during the test immediately forces `propagate=True` back:

```python
@pytest.fixture(autouse=True)
def _reset_agency_logger(monkeypatch):
    import agency.logging as alog
    log = logging.getLogger("agency")
    ...reset propagate/level/handlers...

    _orig_configure = alog.configure
    def _safe_configure(*args, **kwargs):
        result = _orig_configure(*args, **kwargs)
        log.propagate = True
        return result
    monkeypatch.setattr(alog, "configure", _safe_configure)
    try:
        import agency.cli
        monkeypatch.setattr(agency.cli, "configure_logging", _safe_configure)
    except (ImportError, AttributeError):
        pass
    yield
    ...restore...
```

### 2.3 `tests/test_jarvis_pass7.py` — Write-tool em-dash truncation

**Root cause:** File was truncated mid-method by the Write tool in a prior session.
The stale `.pyc` (from session `tender-relaxed-bell`) referenced a module path that no
longer existed in the current session, causing `ModuleNotFoundError: No module named 'tomllib'`
at collection time (line 21 of the pyc pointed to a top-level import that predated the
try/except wrapper).

**Fix:** Reconstructed the three missing methods (`test_entry_point_correct_module`,
`test_anthropic_dep_listed`, `test_dev_extras_has_pytest`) from pyc disassembly via
`marshal.loads` + `dis.dis`, then appended and deduplicated via a Python repair script.

---

## 3. Root-Cause Summary Table

| Failure | Mechanism | Fix |
|---|---|---|
| `test_tools.py` after pass4 | `os.environ` mutation bypassing monkeypatch, leaked across tests | Direct `os.environ.pop()` in conftest autouse |
| 4 caplog tests in pass6 | CliRunner closes `sys.stderr` stream; `configure()` leaves `propagate=False` + dead StreamHandler | Wrap `configure` in fixture to re-enforce `propagate=True` |
| pass7 collection error | Stale `.pyc` from old session; Write tool em-dash truncation | Reconstructed from disassembly; appended via bash |

---

## 4. Files Modified

| File | Change |
|---|---|
| `runtime/tests/conftest.py` | Trust-mode env isolation: `os.environ.pop()` before+after yield |
| `runtime/tests/test_jarvis_pass6.py` | `_reset_agency_logger` fixture: accepts `monkeypatch`, patches `agency.logging.configure` |
| `runtime/tests/test_jarvis_pass7.py` | Reconstructed 3 truncated methods from pyc disassembly |

---

## 5. Final Test Count

```
test_jarvis_pass3..7    230 passed
test_tools et al.       127 passed
test_cli et al.         107 passed
test_character et al.   365 passed
test_amjad et al.       130 passed
TOTAL                   959 passed, 0 failed
```
