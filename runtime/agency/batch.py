"""Batch execution engine for agency runtime.

Reads prompts from a script file (one per line, # = comments),
runs each through JARVIS sequentially or in parallel, and writes
output to <script>.output.md.

Usage:
    agency run script.txt
    agency run script.txt --parallel 4
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .logging import get_logger

log = get_logger()


@dataclass
class BatchResult:
    """Result for a single prompt in a batch run."""

    index: int          # 1-based position in the file
    prompt: str
    output: str
    elapsed_s: float
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error


@dataclass
class BatchRun:
    """Complete result of a batch execution."""

    script_path: Path
    results: list[BatchResult] = field(default_factory=list)
    output_path: Path | None = None

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def succeeded(self) -> int:
        return sum(1 for r in self.results if r.ok)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if not r.ok)


def _parse_script(path: Path) -> list[str]:
    """Read a script file and return non-empty, non-comment lines."""
    prompts: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            prompts.append(stripped)
    return prompts


def _write_output_md(run: BatchRun) -> Path:
    """Write batch results to <script>.output.md and return the path."""
    out_path = run.script_path.with_suffix(".output.md")
    lines: list[str] = [
        f"# Batch Run: {run.script_path.name}",
        "",
        f"- Total prompts: {run.total}",
        f"- Succeeded: {run.succeeded}",
        f"- Failed: {run.failed}",
        "",
        "---",
        "",
    ]
    for r in run.results:
        lines.append(f"## [{r.index}/{run.total}] Prompt")
        lines.append("")
        lines.append(f"> {r.prompt}")
        lines.append("")
        if r.ok:
            lines.append("### Response")
            lines.append("")
            lines.append(r.output)
        else:
            lines.append(f"### ❌ Error")
            lines.append("")
            lines.append(f"```\n{r.error}\n```")
        lines.append("")
        lines.append(f"*elapsed: {r.elapsed_s:.2f}s*")
        lines.append("")
        lines.append("---")
        lines.append("")
    out_path.write_text("\n".join(lines), encoding="utf-8")
    run.output_path = out_path
    return out_path


class BatchRunner:
    """Run a list of prompts through a handler function.

    Parameters
    ----------
    handler:
        Callable(prompt: str) -> str.  Called for each prompt.
        Should raise on error; the runner catches and records it.
    progress_cb:
        Optional callable(index, total, prompt) called before each run.
    """

    def __init__(
        self,
        handler: Callable[[str], str],
        progress_cb: Callable[[int, int, str], None] | None = None,
    ) -> None:
        self._handler = handler
        self._progress_cb = progress_cb

    # ── public API ──────────────────────────────────────────────────────────

    def run_file(
        self,
        script_path: Path,
        parallel: int = 1,
    ) -> BatchRun:
        """Execute all prompts in *script_path*.

        Parameters
        ----------
        script_path:
            Path to the script file.
        parallel:
            Number of concurrent workers.  1 = sequential (default).
        """
        prompts = _parse_script(script_path)
        run = BatchRun(script_path=script_path)

        if parallel > 1:
            run.results = asyncio.run(
                self._run_parallel(prompts, parallel)
            )
        else:
            run.results = self._run_sequential(prompts)

        _write_output_md(run)
        return run

    def run_prompts(
        self,
        prompts: list[str],
        script_path: Path | None = None,
        parallel: int = 1,
    ) -> BatchRun:
        """Execute a list of prompts directly (no file required)."""
        sp = script_path or Path("batch_run.txt")
        run = BatchRun(script_path=sp)

        if parallel > 1:
            run.results = asyncio.run(
                self._run_parallel(prompts, parallel)
            )
        else:
            run.results = self._run_sequential(prompts)

        _write_output_md(run)
        return run

    # ── internals ───────────────────────────────────────────────────────────

    def _run_sequential(self, prompts: list[str]) -> list[BatchResult]:
        results: list[BatchResult] = []
        total = len(prompts)
        for i, prompt in enumerate(prompts, 1):
            if self._progress_cb:
                self._progress_cb(i, total, prompt)
            result = self._execute_one(i, total, prompt)
            results.append(result)
        return results

    async def _run_parallel(
        self, prompts: list[str], workers: int
    ) -> list[BatchResult]:
        total = len(prompts)
        semaphore = asyncio.Semaphore(workers)

        async def _one(idx: int, prompt: str) -> BatchResult:
            async with semaphore:
                if self._progress_cb:
                    self._progress_cb(idx, total, prompt)
                loop = asyncio.get_event_loop()
                return await loop.run_in_executor(
                    None, self._execute_one, idx, total, prompt
                )

        tasks = [_one(i, p) for i, p in enumerate(prompts, 1)]
        return list(await asyncio.gather(*tasks))

    def _execute_one(self, index: int, total: int, prompt: str) -> BatchResult:
        t0 = time.monotonic()
        try:
            output = self._handler(prompt)
            elapsed = time.monotonic() - t0
            log.debug("batch[%d/%d] ok (%.2fs): %s", index, total, elapsed, prompt[:60])
            return BatchResult(
                index=index, prompt=prompt, output=output, elapsed_s=elapsed
            )
        except Exception as exc:  # noqa: BLE001
            elapsed = time.monotonic() - t0
            err = f"{type(exc).__name__}: {exc}"
            log.warning("batch[%d/%d] error: %s", index, total, err)
            return BatchResult(
                index=index, prompt=prompt, output="", elapsed_s=elapsed, error=err
            )
