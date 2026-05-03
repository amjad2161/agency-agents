"""Cron-based task scheduler for JARVIS.

Parses standard 5-field cron expressions (minute hour dom month dow)
using pure stdlib. Runs tasks in a background thread.

Tasks are persisted to ~/.agency/schedule.json.
Failures are written to the DLQ.

Usage
-----
    sched = Scheduler()
    task = sched.add("daily_brief", "0 9 * * *", "agency run daily_brief.txt")
    sched.start()          # starts background thread
    sched.stop()           # graceful shutdown

CLI
---
    agency schedule add "daily_brief" "0 9 * * *" "agency run daily_brief.txt"
    agency schedule list
    agency schedule remove <id>
    agency schedule run <id>
"""

from __future__ import annotations

import json
import subprocess
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from .logging import get_logger

log = get_logger()

DEFAULT_SCHEDULE_PATH = Path.home() / ".agency" / "schedule.json"

# ---------------------------------------------------------------------------
# Minimal 5-field cron parser
# ---------------------------------------------------------------------------


class CronExpression:
    """Parse and evaluate a 5-field cron expression.

    Fields: minute hour day-of-month month day-of-week
    Supports: * (wildcard), N (exact value), */N (step), N-M (range).
    """

    FIELD_RANGES = [(0, 59), (0, 23), (1, 31), (1, 12), (0, 6)]
    FIELD_NAMES = ["minute", "hour", "dom", "month", "dow"]

    def __init__(self, expression: str) -> None:
        self.expression = expression.strip()
        parts = self.expression.split()
        if len(parts) != 5:
            raise ValueError(
                f"Cron expression must have exactly 5 fields, got {len(parts)}: {expression!r}"
            )
        self._fields: list[set[int]] = []
        for i, part in enumerate(parts):
            lo, hi = self.FIELD_RANGES[i]
            self._fields.append(self._parse_field(part, lo, hi))

    @staticmethod
    def _parse_field(field: str, lo: int, hi: int) -> set[int]:
        values: set[int] = set()
        for segment in field.split(","):
            segment = segment.strip()
            if segment == "*":
                values.update(range(lo, hi + 1))
            elif "/" in segment:
                base, step_str = segment.split("/", 1)
                step = int(step_str)
                if step <= 0:
                    raise ValueError(f"Step must be > 0, got {step}")
                if base == "*":
                    start = lo
                elif "-" in base:
                    a, b = base.split("-", 1)
                    start = int(a)
                else:
                    start = int(base)
                values.update(range(start, hi + 1, step))
            elif "-" in segment:
                a, b = segment.split("-", 1)
                values.update(range(int(a), int(b) + 1))
            else:
                values.add(int(segment))
        return values

    def matches(self, dt: datetime) -> bool:
        """Return True if the given datetime matches this cron expression."""
        return (
            dt.minute in self._fields[0]
            and dt.hour in self._fields[1]
            and dt.day in self._fields[2]
            and dt.month in self._fields[3]
            and dt.weekday() in self._fields[4]  # Python weekday: 0=Mon, cron: 0=Sun
        )

    def next_run(self, after: datetime | None = None) -> datetime:
        """Compute the next datetime (UTC) matching this expression.

        Searches up to 366 days ahead; raises RuntimeError if no match found.
        """
        now = after or datetime.now(tz=timezone.utc)
        # Advance to next minute boundary
        candidate = now.replace(second=0, microsecond=0)
        candidate = _add_minutes(candidate, 1)

        for _ in range(366 * 24 * 60):  # max 1 year
            if self.matches(candidate):
                return candidate
            candidate = _add_minutes(candidate, 1)

        raise RuntimeError(f"Could not find next run time for cron: {self.expression!r}")


def _add_minutes(dt: datetime, n: int) -> datetime:
    import datetime as _dt
    return dt + _dt.timedelta(minutes=n)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class ScheduledTask:
    name: str
    cron: str
    command: str
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    enabled: bool = True
    last_run: Optional[float] = None
    next_run: Optional[float] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ScheduledTask":
        return cls(
            id=d.get("id", str(uuid.uuid4())[:8]),
            name=d["name"],
            cron=d["cron"],
            command=d["command"],
            enabled=d.get("enabled", True),
            last_run=d.get("last_run"),
            next_run=d.get("next_run"),
        )

    def compute_next_run(self) -> float:
        expr = CronExpression(self.cron)
        return expr.next_run().timestamp()


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------


class Scheduler:
    """Background cron scheduler for JARVIS tasks."""

    def __init__(
        self,
        schedule_path: Path | None = None,
        dlq_path: Path | None = None,
        tick_interval: float = 30.0,
    ) -> None:
        self._path = Path(schedule_path) if schedule_path else DEFAULT_SCHEDULE_PATH
        self._dlq_path = Path(dlq_path) if dlq_path else (Path.home() / ".agency" / "dlq.jsonl")
        self._tick = tick_interval
        self._tasks: dict[str, ScheduledTask] = {}
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> None:
        if self._path.exists():
            try:
                data = json.loads(self._path.read_text())
                for d in data:
                    t = ScheduledTask.from_dict(d)
                    self._tasks[t.id] = t
                log.debug("scheduler.load tasks=%d", len(self._tasks))
            except Exception as exc:
                log.warning("scheduler.load failed: %s", exc)

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps([t.to_dict() for t in self._tasks.values()], indent=2)
        )

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def add(self, name: str, cron: str, command: str) -> ScheduledTask:
        """Add a new scheduled task. Raises ValueError on bad cron."""
        expr = CronExpression(cron)  # validate
        task = ScheduledTask(name=name, cron=cron, command=command)
        task.next_run = expr.next_run().timestamp()
        self._tasks[task.id] = task
        self._save()
        log.debug("scheduler.add id=%s name=%s cron=%r", task.id, name, cron)
        return task

    def remove(self, task_id: str) -> bool:
        if task_id in self._tasks:
            del self._tasks[task_id]
            self._save()
            return True
        return False

    def get(self, task_id: str) -> Optional[ScheduledTask]:
        return self._tasks.get(task_id)

    def list_tasks(self) -> List[ScheduledTask]:
        return sorted(self._tasks.values(), key=lambda t: t.next_run or 0)

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def run_task(self, task_id: str) -> bool:
        """Manually trigger a task by id. Returns True on success."""
        task = self._tasks.get(task_id)
        if not task:
            return False
        return self._execute(task)

    def _execute(self, task: ScheduledTask) -> bool:
        log.debug("scheduler.execute id=%s name=%s cmd=%r", task.id, task.name, task.command)
        try:
            result = subprocess.run(
                task.command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=300,
            )
            task.last_run = time.time()
            task.next_run = CronExpression(task.cron).next_run().timestamp()
            self._save()
            if result.returncode != 0:
                self._dlq_write(task, f"exit code {result.returncode}: {result.stderr[:200]}")
                return False
            return True
        except Exception as exc:
            task.last_run = time.time()
            self._save()
            self._dlq_write(task, str(exc))
            return False

    def _dlq_write(self, task: ScheduledTask, error: str) -> None:
        import json as _json
        entry = {
            "entry_id": str(uuid.uuid4()),
            "timestamp": time.time(),
            "error": error,
            "input": task.command,
            "retry_count": 0,
            "status": "failed",
            "context": {"task_id": task.id, "task_name": task.name},
        }
        try:
            self._dlq_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._dlq_path, "a") as f:
                f.write(_json.dumps(entry) + "\n")
        except Exception as exc:
            log.warning("scheduler.dlq_write failed: %s", exc)

    # ------------------------------------------------------------------
    # Background thread
    # ------------------------------------------------------------------

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="scheduler")
        self._thread.start()
        log.debug("scheduler.start")

    def stop(self, timeout: float = 5.0) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=timeout)
        log.debug("scheduler.stop")

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            now = time.time()
            for task in list(self._tasks.values()):
                if not task.enabled:
                    continue
                next_run = task.next_run or 0
                if next_run <= now:
                    self._execute(task)
            self._stop_event.wait(self._tick)
