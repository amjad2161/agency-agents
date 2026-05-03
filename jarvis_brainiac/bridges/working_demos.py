"""Bundled demo scripts (one per major capability).

Implements PARTIAL requirement from AUDIT_REQUIREMENTS.md.
Stub: returns deterministic mock; real backend adapter wired in v27+.
"""
from __future__ import annotations
from .base import Bridge


class WorkingDemosBridge(Bridge):
    name = "working_demos"
    capabilities = ["run-demo", "list-demos", "record-output"]

    def __init__(self, **config):
        self.config = config
        self._connected = False

    def connect(self) -> bool:
        self._connected = True
        return True

    def invoke(self, action: str, **kw) -> dict:
        if not self._connected:
            self.connect()
        if action not in self.capabilities:
            return {"ok": False, "error": f"unknown action: {action}",
                    "available": self.capabilities}
        return {"ok": True, "bridge": self.name, "action": action,
                "args": kw, "result": "stub-response"}

    def disconnect(self) -> None:
        self._connected = False
