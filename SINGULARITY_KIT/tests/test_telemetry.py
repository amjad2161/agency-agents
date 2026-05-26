"""Tests for jarvis_brain.telemetry"""
import sys, os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from jarvis_brain.telemetry import Telemetry


def test_snapshot_runs():
    t = Telemetry()
    snap = t.snapshot()
    if "err" in snap:
        # On non-Windows or no psutil, just verify it doesn't crash
        print(f"[skip] {snap['err']}")
        return
    # On Windows with psutil, must have these keys
    assert "cpu_percent" in snap or "err" in snap
    assert "ram_percent" in snap or "err" in snap


def test_processes_runs():
    t = Telemetry()
    procs = t.top_processes(5)
    # may be empty if psutil missing - just shouldn't crash
    assert isinstance(procs, list)


if __name__ == "__main__":
    test_snapshot_runs(); print("[OK] snapshot")
    test_processes_runs(); print("[OK] processes")
    print("ALL TESTS PASS")
