"""atomic_write_util — root-cause fix for Windows-write corruption pattern.

Symptoms observed in JARVIS repo (2026-05-04 run):
  - 3 .py files corrupted: trailing NUL padding + duplicate code block appended
  - Pattern: write happens twice, second write truncates partway, leaves
    NULs from leftover buffer.

Root cause hypothesis:
  Non-atomic writes via `open(path, 'w').write(...)` while another process
  reads/locks the file. On Windows + OneDrive, file-sync hooks can swap the
  underlying handle mid-write, leading to truncated tail + NUL padding.

Fix: write-to-tmp-then-rename pattern with explicit fsync.

Drop this util into any module that writes .py / .md / .json output.
Import and use `atomic_write(path, data, mode='w')` instead of raw open().
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import IO, Any, Union

PathLike = Union[str, os.PathLike]


def atomic_write(path: PathLike, data: Union[str, bytes], mode: str = "w",
                 encoding: str = "utf-8", newline: str | None = "") -> None:
    """Atomically write `data` to `path`.

    Steps:
      1. Write to a same-directory tmp file (so rename is atomic on same FS).
      2. flush + fsync the tmp file.
      3. os.replace(tmp, path) — atomic on POSIX and Windows.
      4. On Windows, also fsync the parent dir if possible.

    Behavior:
      - If `data` is bytes, mode is forced to 'wb' regardless of arg.
      - Failure → tmp file is removed; original path unchanged.

    Args:
        path: target file path
        data: str or bytes to write
        mode: 'w' or 'wb' (auto-detected from `data` type)
        encoding: text encoding (ignored if mode='wb')
        newline: text newline policy ("" = preserve, default for cross-platform)
    """
    path = Path(path)
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)

    is_binary = isinstance(data, bytes) or "b" in mode
    open_mode = "wb" if is_binary else "w"
    open_kwargs: dict[str, Any] = {} if is_binary else {
        "encoding": encoding, "newline": newline,
    }

    fd, tmp_path = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=parent,
    )
    try:
        with os.fdopen(fd, open_mode, **open_kwargs) as f:
            f.write(data)  # type: ignore[arg-type]
            f.flush()
            os.fsync(f.fileno())
        # Atomic swap
        os.replace(tmp_path, path)
        # Best-effort directory fsync (POSIX only, NOOP on Windows)
        if hasattr(os, "O_DIRECTORY"):
            try:
                dfd = os.open(parent, os.O_DIRECTORY)
                os.fsync(dfd)
                os.close(dfd)
            except OSError:
                pass
    except Exception:
        # Clean up tmp on any failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def repair_nul_corruption(path: PathLike) -> bool:
    """Remove NUL bytes from a file. Returns True if any NULs were stripped.

    Use as one-shot remediation after a known corruption event:
      from atomic_write_util import repair_nul_corruption
      if repair_nul_corruption('runtime/tests/test_jarvis_pass33.py'):
          print('repaired')
    """
    path = Path(path)
    raw = path.read_bytes()
    if b"\x00" not in raw:
        return False
    cleaned = raw.replace(b"\x00", b"")
    atomic_write(path, cleaned)
    return True


def strip_utf8_bom(path: PathLike) -> bool:
    """Strip UTF-8 BOM (\\xef\\xbb\\xbf) from start of file. Returns True if stripped."""
    path = Path(path)
    raw = path.read_bytes()
    if raw[:3] != b"\xef\xbb\xbf":
        return False
    atomic_write(path, raw[3:])
    return True


__all__ = ["atomic_write", "repair_nul_corruption", "strip_utf8_bom"]


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("usage: atomic_write_util.py {repair-nul|strip-bom|test} <path>")
        sys.exit(1)
    cmd, target = sys.argv[1], sys.argv[2]
    if cmd == "repair-nul":
        print("repaired" if repair_nul_corruption(target) else "no NUL bytes")
    elif cmd == "strip-bom":
        print("stripped" if strip_utf8_bom(target) else "no BOM")
    elif cmd == "test":
        atomic_write(target, "atomic write test\n")
        print(f"wrote {target} via atomic_write")
    else:
        print(f"unknown cmd: {cmd}")
        sys.exit(1)
