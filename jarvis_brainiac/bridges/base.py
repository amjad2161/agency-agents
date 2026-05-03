"""Bridge abstract base + registry."""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class BridgeStatus:
    name: str
    connected: bool = False
    capabilities: list[str] = field(default_factory=list)
    error: str = ""


class Bridge(ABC):
    """Uniform interface for external system bridges."""
    name: str = "base"
    capabilities: list[str] = []

    @abstractmethod
    def connect(self) -> bool: ...

    @abstractmethod
    def invoke(self, action: str, **kw) -> dict: ...

    def disconnect(self) -> None:
        pass

    def status(self) -> BridgeStatus:
        return BridgeStatus(name=self.name, capabilities=list(self.capabilities))


class BridgeRegistry:
    """Single source of truth for all bridges."""
    def __init__(self):
        self._bridges: dict[str, Bridge] = {}

    def register(self, bridge: Bridge) -> None:
        self._bridges[bridge.name] = bridge

    def get(self, name: str) -> Bridge | None:
        return self._bridges.get(name)

    def all(self) -> list[Bridge]:
        return list(self._bridges.values())

    def connect_all(self) -> dict[str, bool]:
        return {b.name: b.connect() for b in self._bridges.values()}
