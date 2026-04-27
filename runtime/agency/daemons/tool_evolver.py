"""Proactive tool evolution daemon.

Walks `~/.agency/tools/*.py` (the directory where the agent has
written its own ad-hoc tools across past sessions), benchmarks each
one with a tiny self-test, and either:

  - **logs a "fast enough"** entry for the tool, or
  - **asks the LLM to rewrite it** with a hint about the bottleneck
    (slow timing / high memory / Python warning emitted), runs the
    rewrite past the same test, and replaces the file ONLY if the
    new version still passes its tests.

The daemon is **not** a long-running background process. It's a
CLI command (`agency evolve`) the user can:

  - Run manually when the system is idle, or
  - Wire to cron / launchd / systemd / Task Scheduler if they want
    it to run on a schedule.

Why not a real daemon? Two reasons:
  1. The runtime should never grow a permanent background process
     the user didn't explicitly start.
  2. Scheduling is platform-specific; using the OS's scheduler
     means the user retains full control over when, how often, and
     under what env this runs.

Convention for tool files:
    ~/.agency/tools/<name>.py

    Each file should export:
      - a callable `run(input: dict) -> str | dict` (the tool body)
      - an optional `BENCH = [{"input": ..., "expect_contains": "..."}]`
        list that the evolver runs on every pass

    If `BENCH` is missing the evolver records the tool as "no
    benchmarks; skipping" instead of touching it. Tools are never
    rewritten without a passing test on hand.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import sys
import time
import traceback

if sys.platform != "win32":
    import resource  # noqa: F401  Unix-only; reserved for future RLIMIT use
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

# How "slow" is slow enough to ask for a rewrite, in seconds. Anything
# under 50ms is considered fast enough that rewriting probably doesn't
# pay off. Override via AGENCY_EVOLVE_SLOW_S.
SLOW_THRESHOLD_S = float(os.environ.get("AGENCY_EVOLVE_SLOW_S", "0.5"))


def tools_dir() -> Path:
    override = os.environ.get("AGENCY_TOOLS_DIR")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".agency" / "tools"


@dataclass
class BenchResult:
    """One bench run of one tool."""
    name: str
    elapsed_s: float
    ok: bool
    error: str | None = None
    output_len: int = 0


@dataclass
class ToolReport:
    """Summary of every bench run for a single tool file."""
    path: Path
    runs: list[BenchResult] = field(default_factory=list)
    skipped_reason: str | None = None
    rewrite_attempted: bool = False
    rewrite_succeeded: bool = False
    rewrite_diff_lines: int = 0

    @property
    def median_elapsed_s(self) -> float:
        timings = sorted(r.elapsed_s for r in self.runs if r.ok)
        if not timings:
            return 0.0
        mid = len(timings) // 2
        if len(timings) % 2 == 1:
            return timings[mid]
        return (timings[mid - 1] + timings[mid]) / 2

    @property
    def is_slow(self) -> bool:
        return self.median_elapsed_s > SLOW_THRESHOLD_S


def discover_tool_files() -> list[Path]:
    """Return the .py files under ~/.agency/tools/ excluding __init__ and dotfiles."""
    d = tools_dir()
    if not d.is_dir():
        return []
    return sorted(
        p for p in d.glob("*.py")
        if p.name != "__init__.py" and not p.name.startswith(".")
    )


def _load_module(path: Path):
    """Import a .py file as an isolated module — never cached in
    sys.modules under its real name so the evolver can re-load after
    a rewrite without affecting other code."""
    name = f"_evolver__{path.stem}"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def bench_tool(path: Path, *, repeats: int = 3) -> ToolReport:
    """Run the tool's BENCH suite `repeats` times and record timings."""
    report = ToolReport(path=path)

    try:
        mod = _load_module(path)
    except Exception:
        report.skipped_reason = (
            f"import failed:\n{traceback.format_exc(limit=5)}"
        )
        return report

    if mod is None:
        report.skipped_reason = "could not load module"
        return report

    run_fn = getattr(mod, "run", None)
    if not callable(run_fn):
        report.skipped_reason = "no run() callable"
        return report

    bench = getattr(mod, "BENCH", None)
    if not bench:
        report.skipped_reason = "no BENCH suite — refusing to evolve"
        return report

    for case in bench:
        for _ in range(repeats):
            inp = case.get("input", {})
            expect = case.get("expect_contains")
            t0 = time.monotonic()
            try:
                out = run_fn(inp)
                elapsed = time.monotonic() - t0
                out_str = str(out)
                ok = True
                if expect is not None and str(expect) not in out_str:
                    ok = False
                report.runs.append(BenchResult(
                    name=case.get("name", "case"),
                    elapsed_s=elapsed,
                    ok=ok,
                    output_len=len(out_str),
                    error=None if ok else f"expected substring not found: {expect!r}",
                ))
            except Exception as e:  # noqa: BLE001
                elapsed = time.monotonic() - t0
                report.runs.append(BenchResult(
                    name=case.get("name", "case"),
                    elapsed_s=elapsed,
                    ok=False,
                    error=f"{type(e).__name__}: {e}",
                ))
    return report


def evolve_tool(path: Path, report: ToolReport, *,
                llm: Any, dry_run: bool = False) -> ToolReport:
    """Ask the LLM to rewrite `path` to be faster, run it past the
    same BENCH suite, and only replace the file if the new version
    still passes. `llm` should be an `AnthropicLLM` (or a stub with
    `messages_create(**kwargs) → response.content[0].text`).

    Returns the same `report` with `rewrite_*` fields filled in.

    Never destructive: the original is backed up to
    `<path>.bak.<timestamp>` before replacement, and replacement
    only happens if the rewrite *both* passes BENCH AND is not
    slower than the original at the median.
    """
    if report.skipped_reason:
        return report
    if not report.is_slow:
        return report

    report.rewrite_attempted = True

    original_text = path.read_text(encoding="utf-8")
    median = report.median_elapsed_s
    prompt = (
        "You are a code optimizer. Rewrite the Python module below to "
        "run its `run(input)` function faster while keeping behavior "
        f"identical. Current median timing on the BENCH suite: {median:.3f}s. "
        "Aim for at least a 2x speedup. Preserve the BENCH list and "
        "the run() signature exactly. Reply with the full new module "
        "source — no commentary, no markdown fences.\n\n"
        f"--- {path.name} ---\n{original_text}"
    )

    try:
        resp = llm.messages_create(
            system=[{"type": "text", "text":
                     "You rewrite Python modules for speed. Output the full file body, nothing else."}],
            messages=[{"role": "user", "content": prompt}],
            tools=[],
        )
    except Exception as e:  # noqa: BLE001
        report.skipped_reason = f"LLM call failed: {e}"
        return report

    new_text = "".join(
        getattr(b, "text", "") for b in getattr(resp, "content", [])
    ).strip()
    # Strip any leading/trailing fence the model added despite instructions.
    if new_text.startswith("```"):
        new_text = "\n".join(line for line in new_text.splitlines()
                              if not line.startswith("```"))

    if not new_text or "def run" not in new_text:
        report.skipped_reason = "rewrite produced no usable code"
        return report

    if dry_run:
        report.rewrite_succeeded = True  # claimed, not applied
        report.rewrite_diff_lines = abs(
            len(new_text.splitlines()) - len(original_text.splitlines()),
        )
        return report

    # Write to a sibling file, bench it, replace only on improvement.
    candidate = path.with_suffix(".py.candidate")
    candidate.write_text(new_text, encoding="utf-8")
    new_report = bench_tool(candidate)
    if new_report.skipped_reason or not all(r.ok for r in new_report.runs):
        candidate.unlink(missing_ok=True)
        report.skipped_reason = (
            f"rewrite regressed: {new_report.skipped_reason or 'BENCH failed'}"
        )
        return report
    if new_report.median_elapsed_s >= report.median_elapsed_s:
        candidate.unlink(missing_ok=True)
        report.skipped_reason = (
            f"rewrite not faster ({new_report.median_elapsed_s:.3f}s "
            f"vs {report.median_elapsed_s:.3f}s)"
        )
        return report

    # All good — back up and swap.
    backup = path.with_suffix(f".py.bak.{int(time.time())}")
    shutil.copyfile(path, backup)
    shutil.move(candidate, path)
    report.rewrite_succeeded = True
    report.rewrite_diff_lines = abs(
        len(new_text.splitlines()) - len(original_text.splitlines()),
    )
    return report


def evolve_all(*, llm: Any | None = None,
               dry_run: bool = False) -> Iterator[ToolReport]:
    """Iterate every tool file, bench it, optionally rewrite it.

    `llm=None` means bench-only (no rewriting). Caller decides whether
    to instantiate an `AnthropicLLM` based on whether `ANTHROPIC_API_KEY`
    is set.
    """
    for path in discover_tool_files():
        report = bench_tool(path)
        if llm is not None and report.is_slow and not report.skipped_reason:
            evolve_tool(path, report, llm=llm, dry_run=dry_run)
        yield report
