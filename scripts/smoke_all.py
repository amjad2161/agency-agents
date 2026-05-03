"""Run every scripts/smoke_*.py and summarize results.

Each smoke is invoked as a subprocess. We print a per-smoke status
line, then a final table. Exits non-zero if any smoke fails.
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"

SMOKES = sorted(p for p in SCRIPTS.glob("smoke_*.py") if p.name != "smoke_all.py")


def run_one(p: Path) -> tuple[bool, float, str]:
    t0 = time.perf_counter()
    proc = subprocess.run(
        [sys.executable, str(p)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )
    dt = time.perf_counter() - t0
    ok = proc.returncode == 0
    tail = (proc.stdout.strip().splitlines() or ["(no stdout)"])[-1]
    if not ok:
        tail = (proc.stderr.strip().splitlines() or [tail])[-1]
    return ok, dt, tail


def main() -> int:
    results = []
    for p in SMOKES:
        print(f"--- {p.name} ---", flush=True)
        ok, dt, tail = run_one(p)
        flag = "OK " if ok else "FAIL"
        print(f"  {flag}  {dt:5.2f}s  {tail}")
        results.append((p.name, ok, dt))

    print("\n=== summary ===")
    width = max(len(n) for n, _, _ in results)
    for name, ok, dt in results:
        print(f"  {name:<{width}}  {'OK' if ok else 'FAIL':4}  {dt:5.2f}s")
    failed = [n for n, ok, _ in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} green"
          + (f"  failed: {failed}" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
