"""
Object Memory — Pass 23
Persistent memory of observed objects across frames.
Integrates with RobotVision.Detection from Pass 19.
"""

from __future__ import annotations
import pickle
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Tuple

# ── persistence path ───────────────────────────────────────────────────────────

MEMORY_PATH = Path.home() / ".agency" / "object_memory.pkl"

# ── dataclasses ────────────────────────────────────────────────────────────────

@dataclass
class Detection:
    """Minimal Detection compatible with RobotVision from Pass 19."""
    label: str
    confidence: float
    bbox: Tuple[float, float, float, float]  # x, y, w, h (normalized)


@dataclass
class KnownObject:
    label: str
    last_seen_frame: int
    times_seen: int
    avg_bbox: Tuple[float, float, float, float]
    confidence: float

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "last_seen_frame": self.last_seen_frame,
            "times_seen": self.times_seen,
            "avg_bbox": self.avg_bbox,
            "confidence": self.confidence,
        }


# ── public class ───────────────────────────────────────────────────────────────

class ObjectMemory:
    """
    Maintains a running registry of observed objects.
    Persists to `~/.agency/object_memory.pkl`.
    """

    def __init__(self, memory_path: Optional[Path] = None):
        self._path = memory_path or MEMORY_PATH
        self._store: dict[str, KnownObject] = self._load()

    # ── persistence ───────────────────────────────────────────────────────────

    def _load(self) -> dict:
        if self._path.exists():
            try:
                with open(self._path, "rb") as f:
                    return pickle.load(f)
            except Exception:
                pass
        return {}

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(self._path, "wb") as f:
                pickle.dump(self._store, f)
        except Exception:
            pass

    # ── internal helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _update_avg_bbox(
        old_bbox: Tuple, new_bbox: Tuple, times_seen: int
    ) -> Tuple:
        """Exponential moving average of bounding box."""
        alpha = 1.0 / (times_seen + 1)
        return tuple(
            alpha * n + (1 - alpha) * o
            for o, n in zip(old_bbox, new_bbox)
        )

    # ── public API ────────────────────────────────────────────────────────────

    def observe(self, detection: Detection, frame_id: int) -> None:
        """Register or update an observed object."""
        key = detection.label.lower()
        if key in self._store:
            obj = self._store[key]
            obj.times_seen += 1
            obj.last_seen_frame = frame_id
            obj.confidence = (obj.confidence * (obj.times_seen - 1) + detection.confidence) / obj.times_seen
            obj.avg_bbox = self._update_avg_bbox(obj.avg_bbox, detection.bbox, obj.times_seen)
        else:
            self._store[key] = KnownObject(
                label=detection.label,
                last_seen_frame=frame_id,
                times_seen=1,
                avg_bbox=detection.bbox,
                confidence=detection.confidence,
            )
        self._save()

    def get_known_objects(self) -> list:
        """Return all known objects."""
        return list(self._store.values())

    def find(self, label: str) -> Optional[KnownObject]:
        """Find a known object by label (case-insensitive)."""
        return self._store.get(label.lower())

    def forget_old(self, max_age_frames: int = 300) -> int:
        """Remove objects not seen within `max_age_frames`. Returns count removed."""
        if not self._store:
            return 0
        # Find most recent frame
        max_frame = max(o.last_seen_frame for o in self._store.values())
        to_remove = [
            key for key, obj in self._store.items()
            if (max_frame - obj.last_seen_frame) > max_age_frames
        ]
        for key in to_remove:
            del self._store[key]
        if to_remove:
            self._save()
        return len(to_remove)

    def clear(self) -> None:
        """Remove all objects from memory."""
        self._store.clear()
        self._save()

    def __len__(self) -> int:
        return len(self._store)
