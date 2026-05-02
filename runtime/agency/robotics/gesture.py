"""
gesture.py — Pass 22
GestureRecognizer: MediaPipe Hands → OpenCV contour heuristic → Mock
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, List, Optional

logger = logging.getLogger(__name__)

# ── Gesture names ──────────────────────────────────────────────────────────────

class Gesture(str, Enum):
    WAVE       = "WAVE"
    THUMBS_UP  = "THUMBS_UP"
    THUMBS_DOWN = "THUMBS_DOWN"
    POINT      = "POINT"
    OPEN_PALM  = "OPEN_PALM"
    FIST       = "FIST"
    PEACE      = "PEACE"
    UNKNOWN    = "UNKNOWN"

# Gesture → JARVIS skill slug mapping
GESTURE_SKILL_MAP: dict[str, str] = {
    Gesture.WAVE:        "wave_hand",
    Gesture.THUMBS_UP:   "stand_up",
    Gesture.THUMBS_DOWN: "sit_down",
    Gesture.POINT:       "reach_forward",
    Gesture.OPEN_PALM:   "open_palm",
    Gesture.FIST:        "fist",
    Gesture.PEACE:       "peace",
    Gesture.UNKNOWN:     "unknown",
}

# ── dataclass ──────────────────────────────────────────────────────────────────

@dataclass
class GestureResult:
    gesture_name: str
    confidence: float
    landmarks: List  # list of (x, y) or MediaPipe landmark objects
    skill_slug: str = field(init=False)

    def __post_init__(self):
        self.skill_slug = GESTURE_SKILL_MAP.get(self.gesture_name, "unknown")


# ── backend detection ──────────────────────────────────────────────────────────

_MEDIAPIPE_AVAILABLE = False
_OPENCV_AVAILABLE = False

try:
    import mediapipe as _mp
    import numpy as _np_mp
    _MEDIAPIPE_AVAILABLE = True
    logger.info("MediaPipe available for gesture recognition")
except ImportError:
    pass

try:
    import cv2 as _cv2
    import numpy as _np_cv
    _OPENCV_AVAILABLE = True
    logger.info("OpenCV available for gesture contour heuristic")
except ImportError:
    pass


# ── Mock backend ───────────────────────────────────────────────────────────────

class MockGestureRecognizer:
    """Returns UNKNOWN gesture — no external deps."""

    def __init__(self):
        self._running = False

    def recognize(self, frame) -> GestureResult:
        return GestureResult(Gesture.UNKNOWN, 0.0, [])

    def start_camera_loop(self, callback: Callable[[GestureResult], None]):
        """Fires callback once immediately then stops (test-friendly)."""
        result = self.recognize(None)
        callback(result)

    def stop(self):
        self._running = False


# ── OpenCV contour heuristic backend ──────────────────────────────────────────

class _OpenCVGestureRecognizer:
    """
    Rough hand-gesture detection using skin colour segmentation + convex hull.
    Heuristic only — returns approximate gesture names.
    """

    def __init__(self):
        self._running = False
        self._cap = None
        self._thread: Optional[threading.Thread] = None

    def _skin_mask(self, frame):
        hsv = _cv2.cvtColor(frame, _cv2.COLOR_BGR2HSV)
        lower = _np_cv.array([0, 20, 70], dtype=_np_cv.uint8)
        upper = _np_cv.array([20, 255, 255], dtype=_np_cv.uint8)
        return _cv2.inRange(hsv, lower, upper)

    def _count_fingers(self, contour) -> int:
        hull = _cv2.convexHull(contour, returnPoints=False)
        try:
            defects = _cv2.convexityDefects(contour, hull)
        except Exception:
            return 0
        if defects is None:
            return 0
        count = 0
        for i in range(defects.shape[0]):
            s, e, f, d = defects[i, 0]
            if d > 10000:
                count += 1
        return count

    def recognize(self, frame) -> GestureResult:
        if frame is None:
            return GestureResult(Gesture.UNKNOWN, 0.0, [])
        mask = self._skin_mask(frame)
        contours, _ = _cv2.findContours(mask, _cv2.RETR_EXTERNAL, _cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return GestureResult(Gesture.UNKNOWN, 0.0, [])
        largest = max(contours, key=_cv2.contourArea)
        area = _cv2.contourArea(largest)
        if area < 5000:
            return GestureResult(Gesture.UNKNOWN, 0.2, [])
        fingers = self._count_fingers(largest)
        if fingers == 0:
            gesture = Gesture.FIST
        elif fingers == 1:
            gesture = Gesture.POINT
        elif fingers == 2:
            gesture = Gesture.PEACE
        elif fingers in (3, 4):
            gesture = Gesture.THUMBS_UP
        else:
            gesture = Gesture.OPEN_PALM
        m = _cv2.moments(largest)
        cx = int(m["m10"] / m["m00"]) if m["m00"] else 0
        cy = int(m["m01"] / m["m00"]) if m["m00"] else 0
        return GestureResult(gesture, 0.6, [(cx, cy)])

    def start_camera_loop(self, callback: Callable[[GestureResult], None]):
        self._running = True
        self._thread = threading.Thread(target=self._loop, args=(callback,), daemon=True)
        self._thread.start()

    def _loop(self, callback):
        cap = _cv2.VideoCapture(0)
        while self._running:
            ret, frame = cap.read()
            if not ret:
                time.sleep(0.05)
                continue
            result = self.recognize(frame)
            callback(result)
            time.sleep(0.033)
        cap.release()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)


# ── MediaPipe backend ──────────────────────────────────────────────────────────

class _MediaPipeGestureRecognizer:
    """
    MediaPipe Hands for landmark detection + rule-based gesture classification.
    """

    def __init__(self):
        self._running = False
        self._hands = _mp.solutions.hands.Hands(
            static_image_mode=False,
            max_num_hands=1,
            min_detection_confidence=0.6,
            min_tracking_confidence=0.5,
        )
        self._thread: Optional[threading.Thread] = None

    def _classify(self, landmarks) -> tuple[str, float]:
        """Rule-based classification from 21 MediaPipe hand landmarks."""
        lm = landmarks.landmark
        # tip indices: thumb=4, index=8, middle=12, ring=16, pinky=20
        # pip indices: index=6, middle=10, ring=14, pinky=18
        fingers_up = []
        # thumb: compare x
        fingers_up.append(lm[4].x < lm[3].x)
        # other fingers: tip y < pip y (up means smaller y)
        for tip, pip in [(8, 6), (12, 10), (16, 14), (20, 18)]:
            fingers_up.append(lm[tip].y < lm[pip].y)

        n = sum(fingers_up)
        thumb_up, idx_up, mid_up, ring_up, pinky_up = fingers_up

        if n == 0:
            return Gesture.FIST, 0.9
        if n == 5:
            return Gesture.OPEN_PALM, 0.9
        if thumb_up and not idx_up and not mid_up and not ring_up and not pinky_up:
            return Gesture.THUMBS_UP, 0.9
        if not thumb_up and not idx_up and not mid_up and not ring_up and not pinky_up:
            # Thumb down approximation: thumb is not up AND y > wrist
            if lm[4].y > lm[0].y:
                return Gesture.THUMBS_DOWN, 0.8
        if idx_up and not mid_up and not ring_up and not pinky_up:
            return Gesture.POINT, 0.9
        if idx_up and mid_up and not ring_up and not pinky_up:
            return Gesture.PEACE, 0.9
        if n >= 3:
            return Gesture.WAVE, 0.7
        return Gesture.UNKNOWN, 0.5

    def recognize(self, frame) -> GestureResult:
        if frame is None:
            return GestureResult(Gesture.UNKNOWN, 0.0, [])
        import numpy as np
        rgb = _cv2.cvtColor(frame, _cv2.COLOR_BGR2RGB)
        results = self._hands.process(rgb)
        if not results.multi_hand_landmarks:
            return GestureResult(Gesture.UNKNOWN, 0.0, [])
        hand = results.multi_hand_landmarks[0]
        gesture, confidence = self._classify(hand)
        lm_list = [(lm.x, lm.y, lm.z) for lm in hand.landmark]
        return GestureResult(gesture, confidence, lm_list)

    def start_camera_loop(self, callback: Callable[[GestureResult], None]):
        self._running = True
        self._thread = threading.Thread(target=self._loop, args=(callback,), daemon=True)
        self._thread.start()

    def _loop(self, callback):
        cap = _cv2.VideoCapture(0)
        while self._running:
            ret, frame = cap.read()
            if not ret:
                time.sleep(0.05)
                continue
            result = self.recognize(frame)
            callback(result)
            time.sleep(0.033)
        cap.release()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
        self._hands.close()


# ── Public facade ──────────────────────────────────────────────────────────────

class GestureRecognizer:
    """
    Facade. Backend priority: MediaPipe → OpenCV contour → Mock.
    """

    def __init__(self):
        if _MEDIAPIPE_AVAILABLE and _OPENCV_AVAILABLE:
            self._backend = _MediaPipeGestureRecognizer()
            self._backend_name = "mediapipe"
        elif _OPENCV_AVAILABLE:
            self._backend = _OpenCVGestureRecognizer()
            self._backend_name = "opencv_contour"
        else:
            self._backend = MockGestureRecognizer()
            self._backend_name = "mock"
        logger.info("GestureRecognizer using backend: %s", self._backend_name)

    @property
    def backend_name(self) -> str:
        return self._backend_name

    def recognize(self, frame) -> GestureResult:
        """Recognize gesture in a single frame (numpy array)."""
        return self._backend.recognize(frame)

    def start_camera_loop(self, callback: Callable[[GestureResult], None]):
        """Start continuous camera capture and call callback on each frame."""
        self._backend.start_camera_loop(callback)

    def stop(self):
        """Stop the camera loop."""
        self._backend.stop()

    def gesture_to_skill(self, gesture_name: str) -> str:
        """Return the JARVIS skill slug for a gesture name."""
        return GESTURE_SKILL_MAP.get(gesture_name, "unknown")
