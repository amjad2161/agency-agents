"""Pass-24 world model — 3D object tracking with spatial decay.

Tracks named objects with a position, velocity, and confidence value
that decays over time. Used by the spatial HUD and VR interface to keep
a short-term picture of the user's environment.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class WorldObject:
    name: str
    position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    velocity: tuple[float, float, float] = (0.0, 0.0, 0.0)
    confidence: float = 1.0
    last_seen: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "position": self.position,
            "velocity": self.velocity,
            "confidence": round(self.confidence, 3),
            "last_seen": self.last_seen,
            "metadata": self.metadata,
        }


class WorldModel:
    """Spatial registry with exponential confidence decay."""

    def __init__(self, *, half_life: float = 5.0) -> None:
        self.half_life = half_life
        self._objects: dict[str, WorldObject] = {}

    def upsert(self, name: str, *, position: tuple[float, float, float],
               velocity: tuple[float, float, float] = (0, 0, 0),
               confidence: float = 1.0, **meta: Any) -> WorldObject:
        obj = WorldObject(
            name=name, position=position, velocity=velocity,
            confidence=confidence, metadata=meta,
        )
        self._objects[name] = obj
        return obj

    def decay(self, *, now: float | None = None) -> None:
        now = now if now is not None else time.time()
        for obj in list(self._objects.values()):
            elapsed = max(0.0, now - obj.last_seen)
            obj.confidence *= math.pow(0.5, elapsed / self.half_life)
            if obj.confidence < 0.01:
                self._objects.pop(obj.name, None)

    def get(self, name: str) -> WorldObject | None:
        return self._objects.get(name)

    def all(self) -> list[WorldObject]:
        return list(self._objects.values())

    def to_dict(self) -> dict[str, Any]:
        return {
            "count": len(self._objects),
            "half_life": self.half_life,
            "objects": [o.to_dict() for o in self._objects.values()],
        }
