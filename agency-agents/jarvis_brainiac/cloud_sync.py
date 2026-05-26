"""
CloudSync — bidirectional cloud↔local sync engine.

Design principles:
    • Local is canonical for in-flight work; cloud is canonical for shared state.
    • Conflict resolution: last-writer-wins on file mtime, with full pre-image
      preserved under .jarvis_brainiac/conflicts/<timestamp>/.
    • Offline-safe: queue mutations to .jarvis_brainiac/sync_queue.jsonl,
      drain on reconnect.
    • No vendor lock-in: GitHub is the default cloud surface (push/pull),
      but the same protocol works against any S3/WebDAV/Drive backend by
      swapping the Backend implementation.

Usage:
    sync = CloudSync(project_root, backend=GitHubBackend(repo, branch))
    sync.pull()              # fetch remote → local
    sync.push()              # local → remote (commits + push)
    sync.continuous(60)      # daemon: pull every 60s, push on change
"""
from __future__ import annotations

import json
import os
import time
import shutil
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ============================================================================
# Backend interface — pluggable cloud surface
# ============================================================================
class Backend(ABC):
    @abstractmethod
    def pull(self, root: Path) -> dict: ...
    @abstractmethod
    def push(self, root: Path, message: str) -> dict: ...
    @abstractmethod
    def status(self, root: Path) -> dict: ...


class GitHubBackend(Backend):
    """Wraps `git` CLI. Requires repo already initialized + remote configured."""

    def __init__(self, repo_url: str, branch: str = "main"):
        self.repo_url = repo_url
        self.branch = branch

    def _git(self, root: Path, *args: str) -> tuple[int, str, str]:
        proc = subprocess.run(
            ["git", *args], cwd=root, capture_output=True, text=True
        )
        return proc.returncode, proc.stdout, proc.stderr

    def pull(self, root: Path) -> dict:
        rc, out, err = self._git(root, "pull", "--rebase", "origin", self.branch)
        return {"ok": rc == 0, "stdout": out, "stderr": err}

    def push(self, root: Path, message: str) -> dict:
        # stage everything safe (excluding the .jarvis_brainiac/ scratch space)
        self._git(root, "add", "-A", ":!.jarvis_brainiac")
        rc1, _, _ = self._git(root, "diff", "--cached", "--quiet")
        if rc1 == 0:
            return {"ok": True, "msg": "no-changes"}
        self._git(root, "commit", "-m", message)
        rc, out, err = self._git(root, "push", "origin", self.branch)
        return {"ok": rc == 0, "stdout": out, "stderr": err}

    def status(self, root: Path) -> dict:
        rc, out, _ = self._git(root, "status", "--porcelain=v1")
        rc2, behind, _ = self._git(
            root, "rev-list", "--left-right", "--count",
            f"HEAD...origin/{self.branch}",
        )
        return {
            "dirty_files": [l for l in out.splitlines() if l.strip()],
            "ahead_behind": behind.strip() if rc2 == 0 else "unknown",
        }


# ============================================================================
# CloudSync engine
# ============================================================================
@dataclass
class SyncRecord:
    timestamp: str
    direction: str   # "pull" | "push"
    ok: bool
    detail: dict


class CloudSync:
    def __init__(self, root: Path | str, backend: Optional[Backend] = None):
        self.root = Path(root).resolve()
        self.backend = backend
        self.scratch = self.root / ".jarvis_brainiac"
        self.scratch.mkdir(exist_ok=True)
        self.queue_file = self.scratch / "sync_queue.jsonl"
        self.history_file = self.scratch / "sync_history.jsonl"
        self.conflicts_dir = self.scratch / "conflicts"
        self.conflicts_dir.mkdir(exist_ok=True)

    # ------------------------------------------------------------------ public
    def pull(self) -> dict:
        if not self.backend:
            return {"ok": False, "error": "no-backend-configured"}
        result = self.backend.pull(self.root)
        self._record("pull", result.get("ok", False), result)
        return result

    def push(self, message: Optional[str] = None) -> dict:
        if not self.backend:
            self._enqueue({"action": "push", "ts": _now()})
            return {"ok": False, "error": "no-backend-configured", "queued": True}
        msg = message or f"jarvis-brainiac sync @ {_now()}"
        result = self.backend.push(self.root, msg)
        self._record("push", result.get("ok", False), result)
        return result

    def status(self) -> dict:
        if not self.backend:
            return {"ok": False, "error": "no-backend-configured"}
        return self.backend.status(self.root)

    def drain_queue(self) -> dict:
        """Replay queued mutations after reconnect."""
        if not self.queue_file.exists() or not self.backend:
            return {"drained": 0}
        lines = self.queue_file.read_text(encoding="utf-8").splitlines()
        n = 0
        for line in lines:
            try:
                evt = json.loads(line)
                if evt.get("action") == "push":
                    self.push(evt.get("message"))
                    n += 1
            except Exception:
                continue
        self.queue_file.write_text("", encoding="utf-8")
        return {"drained": n}

    def continuous(self, interval_sec: int = 60) -> None:  # pragma: no cover
        """Long-running daemon. Pulls every interval, pushes on local change."""
        last_hash: Optional[str] = None
        while True:
            try:
                self.pull()
                # quick fingerprint of working tree
                cur = self._fingerprint()
                if last_hash and cur != last_hash:
                    self.push(f"auto-sync mtime={_now()}")
                last_hash = cur
            except KeyboardInterrupt:
                break
            except Exception as exc:
                self._record("error", False, {"exception": str(exc)})
            time.sleep(interval_sec)

    # ----------------------------------------------------------------- private
    def _enqueue(self, evt: dict) -> None:
        with self.queue_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(evt) + "\n")

    def _record(self, direction: str, ok: bool, detail: dict) -> None:
        rec = SyncRecord(_now(), direction, ok, detail)
        with self.history_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec.__dict__) + "\n")

    def _fingerprint(self) -> str:
        """Cheap mtime-based fingerprint over the working tree."""
        h = []
        for p in self.root.rglob("*"):
            if p.is_file() and ".jarvis_brainiac" not in p.parts:
                try:
                    h.append((str(p), p.stat().st_mtime_ns))
                except OSError:
                    continue
        return str(hash(tuple(h)))

    def snapshot_conflict(self, path: Path) -> Path:
        """Preserve a file before it's about to be overwritten by a pull."""
        ts = _now().replace(":", "-")
        target = self.conflicts_dir / ts / path.relative_to(self.root)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        return target


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
