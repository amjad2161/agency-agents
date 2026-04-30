"""AIOS bridge — inspired by AIOS (AI Operating System).

Lightweight syscall-style adapter that routes high-level intents
(``read_file``, ``write_file``, ``run``, ``list_dir``, ``search``,
``recall``) through the existing :class:`LocalOS` and :class:`LocalMemory`
subsystems. The shape is deliberately minimal so it can be wired into
the AIOS protocol later without API churn.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .local_memory import LocalMemory
from .local_os import LocalOS


SYSCALLS: tuple[str, ...] = (
    "read_file", "write_file", "list_dir", "run",
    "remember", "recall", "ping",
)


@dataclass
class Syscall:
    name: str
    args: dict[str, Any] = field(default_factory=dict)


@dataclass
class SyscallResult:
    name: str
    ok: bool
    value: Any = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


class AIOSBridge:
    """Minimal syscall router."""

    def __init__(self, *, os_bridge: LocalOS | None = None,
                 memory: LocalMemory | None = None) -> None:
        self.os = os_bridge or LocalOS()
        self.memory = memory or LocalMemory()
        self._handlers: dict[str, Callable[..., Any]] = {
            "read_file": self.os.read_file,
            "write_file": lambda **kw: self.os.write_file(**kw).result,
            "list_dir": self.os.list_dir,
            "run": lambda argv, timeout=15.0: self.os.run(argv, timeout=timeout).result,
            "remember": self.memory.add,
            "recall": self.memory.search,
            "ping": lambda: "pong",
        }

    def call(self, syscall: Syscall) -> SyscallResult:
        if syscall.name not in self._handlers:
            return SyscallResult(name=syscall.name, ok=False,
                                 error=f"unknown syscall: {syscall.name!r}")
        try:
            value = self._handlers[syscall.name](**syscall.args)
            return SyscallResult(name=syscall.name, ok=True, value=value)
        except Exception as exc:  # noqa: BLE001 — surface to caller
            return SyscallResult(name=syscall.name, ok=False,
                                 error=f"{type(exc).__name__}: {exc}")

    def syscalls(self) -> tuple[str, ...]:
        return SYSCALLS
