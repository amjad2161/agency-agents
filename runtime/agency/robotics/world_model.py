"""
world_model.py — JARVIS Pass 24
Maintains a 3-D world map from vision detections + monocular depth.
Decays old objects, persists to JSON every 30 s.
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class WorldObject:
    label:       str
    x:           float
    y:           float
    z:           float
    distance_m:  float
    confidence:  float
    last_update: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "WorldObject":
        return cls(**d)


# Detection is a thin alias (same fields for incoming data)
@dataclass
class Detection:
    label:      str
    x:          float
    y:          float
    z:          float = 0.0
    distance_m: float = 0.0
    confidence: float = 1.0


# ---------------------------------------------------------------------------
# WorldModel
# ---------------------------------------------------------------------------

PERSIST_PATH = Path.home() / ".agency" / "world_model.json"
PERSIST_INTERVAL_S = 30.0


class WorldModel:
    """
    Thread-safe 3-D world map.
    Objects not seen for > decay_s are removed automatically.
    Persists to JSON every 30 s (background thread).
    """

    def __init__(self, decay_s: float = 10.0, persist_path: Path | None = None):
        self._objects: dict[str, WorldObject] = {}  # label → latest WorldObject
        self._decay_s = decay_s
        self._lock = threading.Lock()
        self._persist_path = persist_path or PERSIST_PATH
        self._last_persist = time.time()
        self._load_from_disk()

        # Background persist thread
        self._stop_event = threading.Event()
        self._persist_thread = threading.Thread(
            target=self._persist_loop, daemon=True, name="WorldModel-Persist"
        )
        self._persist_thread.start()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update(self, detection: Detection) -> None:
        """Insert or update a detected object."""
        obj = WorldObject(
            label=detection.label,
            x=detection.x,
            y=detection.y,
            z=detection.z,
            distance_m=detection.distance_m,
            confidence=detection.confidence,
            last_update=time.time(),
        )
        with self._lock:
            self._objects[detection.label] = obj

    def get_objects(self) -> list[WorldObject]:
        """Return all non-decayed objects."""
        self._decay()
        with self._lock:
            return list(self._objects.values())

    def get_nearest(self, label: str) -> Optional[WorldObject]:
        """Return the object with the given label (exact match) or None."""
        self._decay()
        with self._lock:
            return self._objects.get(label)

    def to_dict(self) -> dict:
        self._decay()
        with self._lock:
            return {k: v.to_dict() for k, v in self._objects.items()}

    def stop(self) -> None:
        """Stop background persist thread."""
        self._stop_event.set()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _decay(self) -> None:
        """Remove objects older than decay_s."""
        now = time.time()
        with self._lock:
            stale = [
                label for label, obj in self._objects.items()
                if (now - obj.last_update) > self._decay_s
            ]
            for label in stale:
                del self._objects[label]

    def _persist_loop(self) -> None:
        while not self._stop_event.is_set():
            self._stop_event.wait(timeout=PERSIST_INTERVAL_S)
            if not self._stop_event.is_set():
                self._save_to_disk()

    def _save_to_disk(self) -> None:
        try:
            self._persist_path.parent.mkdir(parents=True, exist_ok=True)
            data = self.to_dict()
            tmp = self._persist_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, indent=2))
            tmp.replace(self._persist_path)
        except Exception:
            pass

    def _load_from_disk(self) -> None:
        try:
            if self._persist_path.exists():
                data = json.loads(self._persist_path.read_text())
                now = time.time()
                with self._lock:
                    for label, d in data.items():
                        obj = WorldObject.from_dict(d)
                        # Only restore if not decayed
                        if (now - obj.last_update) <= self._decay_s:
                            self._objects[label] = obj
        except Exception:
            pass


# ---------------------------------------------------------------------------
# MockWorldModel
# ---------------------------------------------------------------------------

class MockWorldModel:
    """Test double — empty, all operations succeed."""

    def __init__(self, decay_s: float = 10.0, persist_path: Path | None = None):
        self._objects: dict[str, WorldObject] = {}

    def update(self, detection: Detection) -> None:
        obj = WorldObject(
            label=detection.label,
            x=detection.x,
            y=detection.y,
            z=detection.z,
            distance_m=detection.distance_m,
            confidence=detection.confidence,
            last_update=time.time(),
        )
        self._objects[detection.label] = obj

    def get_objects(self) -> list[WorldObject]:
        return list(self._objects.values())

    def get_nearest(self, label: str) -> Optional[WorldObject]:
        return self._objects.get(label)

    def to_dict(self) -> dict:
        return {k: v.to_dict() for k, v in self._objects.items()}

    def stop(self) -> None:
        pass
