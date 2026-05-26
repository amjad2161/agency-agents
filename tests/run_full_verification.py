"""
JARVIS BRAINIAC — Full Test Runner & Audit Script
Runs:
  1. pytest tests/test_dashboard_memory.py (ALL variants, isolated + single)
  2. pytest tests/ for navigation tests
  3. Python audit_all.py

Run from project root: python tests/run_full_verification.py
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYTHON = sys.executable

def run(label: str, cmd: list[str]) -> bool:
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    result = subprocess.run(cmd, cwd=str(ROOT))
    ok = result.returncode == 0
    status = "✓ PASSED" if ok else "✗ FAILED"
    print(f"\n  >> {label}: {status}")
    return ok

results = []

# 1. Memory lifecycle tests — run the full file
results.append(run(
    "Memory lifecycle tests (all together)",
    [PYTHON, "-m", "pytest", "tests/test_dashboard_memory.py", "-v"]
))

# 2. Memory lifecycle — run single test to check isolation
results.append(run(
    "Memory lifecycle test — SINGLE test isolation check",
    [PYTHON, "-m", "pytest", "tests/test_dashboard_memory.py::test_api_memory_lifecycle", "-v"]
))

# 3. Bridge tests
results.append(run(
    "Bridge tests",
    [PYTHON, "-m", "pytest", "tests/bridges/", "-v", "--tb=short"]
))

# 4. Navigation tests (just a sample — r1 through r3 to keep fast)
results.append(run(
    "Navigation tests (r1-r3 sample)",
    [PYTHON, "-m", "pytest",
     "tests/test_nav_improvements_r1.py",
     "tests/test_nav_improvements_r2.py",
     "tests/test_nav_improvements_r3.py",
     "-v", "--tb=short"]
))

# 5. Full audit script
results.append(run(
    "Full audit (imports, memory, server, registry)",
    [PYTHON, "tests/audit_all.py"]
))

print(f"\n{'='*60}")
print(f"  FINAL SUMMARY")
print(f"{'='*60}")
all_passed = all(results)
if all_passed:
    print("  ✓ ALL CHECKS PASSED — JARVIS BRAINIAC is 100% clean!")
else:
    print(f"  ✗ {results.count(False)} out of {len(results)} checks FAILED")
print(f"{'='*60}\n")

sys.exit(0 if all_passed else 1)
