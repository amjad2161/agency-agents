"""Autonomous background loop - scheduled tasks, proactive checks."""
from __future__ import annotations
import threading, time
from datetime import datetime


class AutonomousLoop:
    def __init__(self, on_event):
        self.on_event = on_event  # callback(event_type, data)
        self._running = False
        self._thread = None
        self._tasks = []  # list of (interval_s, fn, last_run)

    def add_task(self, interval_s: int, fn, name: str = "task"):
        self._tasks.append({"interval": interval_s, "fn": fn, "last": 0, "name": name})

    def start(self):
        if self._running: return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def _loop(self):
        while self._running:
            now = time.time()
            for task in self._tasks:
                if now - task["last"] >= task["interval"]:
                    try:
                        result = task["fn"]()
                        self.on_event("task_done", {"name": task["name"], "result": result})
                    except Exception as e:
                        self.on_event("task_err", {"name": task["name"], "err": str(e)})
                    task["last"] = now
            time.sleep(5)

    @staticmethod
    def hourly_check():
        return f"hourly check at {datetime.now().strftime('%H:%M')}"
