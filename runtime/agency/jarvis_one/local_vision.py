"""Local vision subsystem (Tier 5).

MediaPipe / OpenCV / LLaVA shaped APIs with deterministic fallbacks.
The mock paths are exercised by tests; the real adapters are loaded
when the optional dependencies are present in the environment.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

KNOWN_GESTURES: tuple[str, ...] = (
    "pinch", "open_palm", "fist", "point",
    "thumbs_up", "two_fingers", "victory",
)


@dataclass
class VisionConfig:
    detector: str = "mediapipe"
    confidence: float = 0.5
    max_landmarks: int = 21

    @classmethod
    def from_env(cls) -> "VisionConfig":
        return cls(
            detector=os.environ.get("JARVIS_VISION_DETECTOR", "mediapipe"),
            confidence=float(os.environ.get("JARVIS_VISION_CONF", "0.5")),
            max_landmarks=int(os.environ.get("JARVIS_VISION_LANDMARKS", "21")),
        )


class LocalVision:
    """Holistic body/face/hands tracking with mock fallback."""

    def __init__(self, config: VisionConfig | None = None) -> None:
        self.config = config or VisionConfig.from_env()
        self._engine = self._load_engine()

    def detect_gesture(self, frame: Any) -> dict[str, Any]:
        """Return the recognised gesture and a confidence score."""
        if self._engine is None:
            # Deterministic mock — pick a gesture from the frame hash.
            label = KNOWN_GESTURES[hash(repr(frame)) % len(KNOWN_GESTURES)]
            return {"gesture": label, "confidence": self.config.confidence,
                    "engine": "mock"}
        return self._engine.detect(frame)  # pragma: no cover

    def describe_image(self, image: Any) -> str:
        """LLaVA-style caption. Mock returns a structured description."""
        if self._engine is None:
            kind = type(image).__name__
            return f"[mock-vision] {kind} payload, {len(repr(image))} chars"
        return self._engine.caption(image)  # pragma: no cover

    def health(self) -> dict[str, Any]:
        return {
            "detector": self.config.detector,
            "engine": "real" if self._engine else "mock",
            "known_gestures": list(KNOWN_GESTURES),
        }

    def _load_engine(self) -> Any | None:
        try:  # pragma: no cover — optional
            import mediapipe as mp  # type: ignore
            return mp.solutions.holistic.Holistic(
                min_detection_confidence=self.config.confidence,
            )
        except Exception:
            return None
