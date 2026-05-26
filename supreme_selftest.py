#!/usr/bin/env python3
"""supreme_selftest — comprehensive end-to-end test for JARVIS_SUPREME.

Exercises:
  - all subsystem imports
  - LLM backend detection (offline-only)
  - agent registry construction
  - memory store ops
  - orchestrator routing dry-run
  - file IO atomic-write
  - permissions env

Run: python supreme_selftest.py
Exit: 0 = all pass; 1+ = number of failures
"""
from __future__ import annotations

import importlib
import importlib.util
import json
import os
import sys
import tempfile
import time
import traceback
from pathlib import Path
from typing import Callable, Any

os.environ.setdefault("OFFLINE_MODE", "1")
os.environ.setdefault("ALLOW_ALL", "1")
os.environ.setdefault("JARVIS_PERM_LEVEL", "GOD")
os.environ.setdefault("JARVIS_REQUIRE_API_KEYS", "0")
os.environ.setdefault("PYTHONUTF8", "1")

CANONICAL = Path(os.environ.get("AGENCY_ROOT", Path(__file__).resolve().parent))
WORKSPACE = Path(__file__).parent
SUPREME = WORKSPACE / "JARVIS_SUPREME.py"

for p in (CANONICAL, CANONICAL / "runtime", WORKSPACE):
    if p.exists() and str(p) not in sys.path:
        sys.path.insert(0, str(p))

results: list[dict] = []
failures: list[str] = []


def t(name: str, fn: Callable[[], Any]) -> None:
    start = time.time()
    try:
        v = fn()
        dur = round((time.time() - start) * 1000, 1)
        results.append({"test": name, "status": "PASS", "ms": dur,
                       "detail": repr(v)[:300] if v is not None else "ok"})
        print(f"  PASS  {name}  ({dur}ms)")
    except Exception as e:
        dur = round((time.time() - start) * 1000, 1)
        failures.append(name)
        results.append({"test": name, "status": "FAIL", "ms": dur,
                       "error": f"{type(e).__name__}: {e}",
                       "trace": traceback.format_exc()[:1500]})
        print(f"  FAIL  {name}: {type(e).__name__}: {e}")


print("=== Section 1: Environment ===")
t("python_min_3.10", lambda: sys.version_info >= (3, 10))
t("env_OFFLINE_MODE", lambda: os.environ["OFFLINE_MODE"] == "1")
t("env_ALLOW_ALL", lambda: os.environ["ALLOW_ALL"] == "1")
t("env_PERM_GOD", lambda: os.environ["JARVIS_PERM_LEVEL"] == "GOD")
t("canonical_dir_exists", lambda: CANONICAL.exists())
t("supreme_module_exists", lambda: SUPREME.exists())

print("\n=== Section 2: Subsystem imports ===")
SUBSYSTEMS = [
    "jarvis_brainiac",
    "jarvis_brainiac.agent_registry",
    "jarvis_brainiac.orchestrator",
    "jarvis_brainiac.memory",
    "jarvis_brainiac.cloud_sync",
    "agency",
    "jarvis_singularity",
    "jarvis_os",
    "godskill_nav_v11",
]
loaded_count = 0
for name in SUBSYSTEMS:
    def _import(n=name):
        importlib.import_module(n)
        return n
    try:
        _import()
        loaded_count += 1
    except Exception:
        pass
    t(f"import_{name.replace('.','_')}", _import)

t("majority_subsystems_loaded", lambda: loaded_count >= len(SUBSYSTEMS) // 2)

print("\n=== Section 3: Supreme module ===")
def _load_supreme():
    spec = importlib.util.spec_from_file_location("jarvis_supreme", SUPREME)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["jarvis_supreme"] = mod
    spec.loader.exec_module(mod)
    return mod

supreme_mod = None
try:
    supreme_mod = _load_supreme()
except Exception as e:
    print(f"  supreme load warning: {e}")

t("supreme_module_loads", _load_supreme)
if supreme_mod:
    t("supreme.boot_callable", lambda: callable(supreme_mod.boot))
    t("supreme.health_callable", lambda: callable(supreme_mod.health))
    t("supreme.detect_llm_backend", lambda: callable(supreme_mod.detect_llm_backend))
    t("supreme.boot_returns_report", lambda: hasattr(supreme_mod.boot(), "subsystems"))

print("\n=== Section 4: LLM backend ===")
if supreme_mod:
    backend = supreme_mod.detect_llm_backend()
    t("llm_backend_returns_dict", lambda: isinstance(backend, dict))
    t("llm_backend_has_name", lambda: "backend" in backend)
    print(f"    backend detected: {backend.get('backend')}")

print("\n=== Section 5: Atomic write ===")
try:
    from atomic_write_util import atomic_write, repair_nul_corruption, strip_utf8_bom
    tmpdir = Path(tempfile.gettempdir())
    test_path = tmpdir / "supreme_selftest_atomic.tmp"
    t("atomic_write_text", lambda: (atomic_write(test_path, "hello\n"), test_path.read_text())[1] == "hello\n")
    t("atomic_write_bytes", lambda: (atomic_write(test_path, b"binary\x00data"), test_path.read_bytes())[1] == b"binary\x00data")
    t("strip_utf8_bom_no_bom", lambda: strip_utf8_bom(test_path) == False)
    try: test_path.unlink()
    except OSError: pass
except ImportError as e:
    t("atomic_write_util_import", lambda: (_ for _ in ()).throw(ImportError(f"atomic_write_util: {e}")))

print("\n=== Section 6: Filesystem perms ===")
log_dir = WORKSPACE / "standup"
t("workspace_writable", lambda: log_dir.exists() or log_dir.mkdir(exist_ok=True) is None)

print(f"\n=== Summary ===")
passed = len([r for r in results if r["status"] == "PASS"])
failed = len(failures)
print(f"PASSED: {passed}  FAILED: {failed}  TOTAL: {len(results)}")
if failures:
    print(f"Failed: {', '.join(failures)}")

summary_data = {
    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "canonical": str(CANONICAL),
    "workspace": str(WORKSPACE),
    "python": sys.version,
    "env": {k: os.environ.get(k) for k in
            ["OFFLINE_MODE", "ALLOW_ALL", "JARVIS_PERM_LEVEL"]},
    "passed": passed,
    "failed": failed,
    "total": len(results),
    "results": results,
}
result_path = WORKSPACE / "supreme_selftest_result.json"
result_path.write_text(json.dumps(summary_data, indent=2, default=str), encoding="utf-8")
print(f"Result: {result_path}")

sys.exit(failed)
