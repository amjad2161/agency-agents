"""
task_executor.py — JARVIS Pass 24
Background-thread priority-queue task executor for robot tasks.
"""

from __future__ import annotations

import heapq
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Enums & Dataclasses
# ---------------------------------------------------------------------------

class ExecutorStatus(str, Enum):
    IDLE    = "IDLE"
    RUNNING = "RUNNING"
    PAUSED  = "PAUSED"
    ERROR   = "ERROR"


@dataclass
class RobotTask:
    task_id:     str
    description: str
    priority:    int        # 1 (highest) – 5 (lowest)
    steps:       list[str] = field(default_factory=list)
    timeout_s:   float = 30.0

    # For heapq comparison (lower priority int = higher urgency)
    def __lt__(self, other: "RobotTask") -> bool:
        return self.priority < other.priority


@dataclass
class TaskResult:
    task_id:         str
    success:         bool
    steps_completed: int
    error:           str
    duration_s:      float


# ---------------------------------------------------------------------------
# Optional NLP motion parser
# ---------------------------------------------------------------------------
try:
    from runtime.agency.robotics.nlp_motion_parser import NLPMotionParser  # type: ignore
    _HAS_PARSER = True
except ImportError:
    _HAS_PARSER = False

    class NLPMotionParser:  # type: ignore
        def parse(self, step: str) -> list[str]:
            return [step]

try:
    from runtime.agency.robotics.robot_brain import RobotBrain  # type: ignore
    _HAS_BRAIN = True
except ImportError:
    _HAS_BRAIN = False

    class RobotBrain:  # type: ignore
        def execute_step(self, step: str) -> bool:
            return True


# ---------------------------------------------------------------------------
# TaskExecutor
# ---------------------------------------------------------------------------

class TaskExecutor:
    """
    Background-thread task executor with a priority heap queue.
    Thread-safe.  Single worker thread.
    """

    def __init__(self):
        self._heap: list[tuple[int, RobotTask]] = []   # (priority, task)
        self._lock = threading.Lock()
        self._status = ExecutorStatus.IDLE
        self._current_task: Optional[RobotTask] = None
        self._cancel_event = threading.Event()
        self._worker = threading.Thread(target=self._worker_loop, daemon=True,
                                        name="TaskExecutor-Worker")
        self._worker.start()
        self._parser = NLPMotionParser()
        self._brain  = RobotBrain()
        self._results: dict[str, TaskResult] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def queue_task(self, task: RobotTask) -> str:
        """Add task to priority queue. Returns task_id."""
        with self._lock:
            heapq.heappush(self._heap, (task.priority, task))
        return task.task_id

    def execute(self, task: RobotTask) -> TaskResult:
        """
        Synchronous execute (blocks until done or timeout).
        Bypasses the queue — used for direct/test invocation.
        """
        return self._run_task(task)

    def cancel_current(self) -> None:
        """Signal the running task to stop. No-op if IDLE."""
        self._cancel_event.set()

    def get_status(self) -> ExecutorStatus:
        return self._status

    def get_result(self, task_id: str) -> Optional[TaskResult]:
        return self._results.get(task_id)

    # ------------------------------------------------------------------
    # Worker loop
    # ------------------------------------------------------------------

    def _worker_loop(self) -> None:
        while True:
            task = self._pop_task()
            if task is None:
                time.sleep(0.05)
                continue
            result = self._run_task(task)
            with self._lock:
                self._results[task.task_id] = result

    def _pop_task(self) -> Optional[RobotTask]:
        with self._lock:
            if self._heap:
                _, task = heapq.heappop(self._heap)
                return task
        return None

    def _run_task(self, task: RobotTask) -> TaskResult:
        self._cancel_event.clear()
        self._status = ExecutorStatus.RUNNING
        self._current_task = task
        start = time.perf_counter()
        steps_done = 0
        error_msg = ""

        try:
            steps = task.steps or [task.description]
            deadline = start + task.timeout_s

            for raw_step in steps:
                if self._cancel_event.is_set():
                    error_msg = "cancelled"
                    break
                if time.perf_counter() > deadline:
                    error_msg = "timeout"
                    break

                # Parse step via NLPMotionParser
                try:
                    parsed_steps = self._parser.parse(raw_step)
                except Exception:
                    parsed_steps = [raw_step]

                for ps in parsed_steps:
                    if self._cancel_event.is_set():
                        break
                    try:
                        self._brain.execute_step(ps)
                    except Exception as e:
                        error_msg = str(e)
                        self._status = ExecutorStatus.ERROR
                        duration = time.perf_counter() - start
                        return TaskResult(task.task_id, False, steps_done, error_msg, duration)

                steps_done += 1

        except Exception as e:
            error_msg = str(e)
            self._status = ExecutorStatus.ERROR
        finally:
            self._current_task = None
            if self._status != ExecutorStatus.ERROR:
                self._status = ExecutorStatus.IDLE

        duration = time.perf_counter() - start
        success = not error_msg or error_msg == ""
        return TaskResult(task.task_id, success, steps_done, error_msg, duration)


# ---------------------------------------------------------------------------
# MockTaskExecutor
# ---------------------------------------------------------------------------

class MockTaskExecutor:
    """Test double — always succeeds instantly."""

    def execute(self, task: RobotTask) -> TaskResult:
        return TaskResult(task.task_id, True, 0, "", 0.0)

    def queue_task(self, task: RobotTask) -> str:
        return task.task_id

    def cancel_current(self) -> None:
        pass

    def get_status(self) -> ExecutorStatus:
        return ExecutorStatus.IDLE


# ---------------------------------------------------------------------------
# Helper: create a task with a generated ID
# ---------------------------------------------------------------------------

def make_task(
    description: str,
    priority: int = 3,
    steps: list[str] | None = None,
    timeout_s: float = 30.0,
    task_id: str | None = None,
) -> RobotTask:
    return RobotTask(
        task_id=task_id or str(uuid.uuid4())[:8],
        description=description,
        priority=priority,
        steps=steps or [],
        timeout_s=timeout_s,
    )
