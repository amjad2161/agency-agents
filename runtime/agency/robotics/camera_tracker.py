"""
Camera Tracker — Pass 23
Face/object tracking with PID-based pan/tilt control.
Backends: OpenCV TrackerCSRT → OpenCV TrackerKCF → MockTracker
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Tuple

# ── dataclasses ────────────────────────────────────────────────────────────────

@dataclass
class TrackResult:
    target_x: float   # normalized [0,1]
    target_y: float   # normalized [0,1]
    target_w: float   # normalized
    target_h: float   # normalized
    tracked: bool
    label: str


# ── PID controller ─────────────────────────────────────────────────────────────

class _PID:
    def __init__(self, Kp: float = 0.1, Ki: float = 0.01, Kd: float = 0.05):
        self.Kp = Kp
        self.Ki = Ki
        self.Kd = Kd
        self._integral: float = 0.0
        self._prev_error: float = 0.0

    def update(self, error: float) -> float:
        self._integral += error
        derivative = error - self._prev_error
        self._prev_error = error
        return self.Kp * error + self.Ki * self._integral + self.Kd * derivative

    def reset(self):
        self._integral = 0.0
        self._prev_error = 0.0


# ── backends ───────────────────────────────────────────────────────────────────

class _CSRTBackend:
    def __init__(self):
        import cv2  # may raise ImportError
        if not hasattr(cv2, "TrackerCSRT_create"):
            raise RuntimeError("TrackerCSRT not available")
        self._cv2 = cv2
        self._tracker = None
        self._initialized = False

    def init(self, frame, bbox):
        self._tracker = self._cv2.TrackerCSRT_create()
        self._tracker.init(frame, bbox)
        self._initialized = True

    def update(self, frame) -> Tuple[bool, tuple]:
        if not self._initialized or self._tracker is None:
            return False, (0, 0, 0, 0)
        ok, bbox = self._tracker.update(frame)
        return ok, bbox


class _KCFBackend:
    def __init__(self):
        import cv2  # may raise ImportError
        if not hasattr(cv2, "TrackerKCF_create"):
            raise RuntimeError("TrackerKCF not available")
        self._cv2 = cv2
        self._tracker = None
        self._initialized = False

    def init(self, frame, bbox):
        self._tracker = self._cv2.TrackerKCF_create()
        self._tracker.init(frame, bbox)
        self._initialized = True

    def update(self, frame) -> Tuple[bool, tuple]:
        if not self._initialized or self._tracker is None:
            return False, (0, 0, 0, 0)
        ok, bbox = self._tracker.update(frame)
        return ok, bbox


class _MockTrackerBackend:
    """Always returns a centered mock target."""

    def init(self, frame, bbox):
        pass

    def update(self, frame) -> Tuple[bool, tuple]:
        return True, (45, 45, 10, 10)  # x,y,w,h in pixels


# ── face detection helper ──────────────────────────────────────────────────────

def _detect_face_bbox(frame):
    """Returns (x, y, w, h) of first detected face, or None."""
    try:
        import cv2
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        cc = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )
        faces = cc.detectMultiScale(gray, 1.1, 4)
        if len(faces) > 0:
            return tuple(faces[0])
    except Exception:
        pass
    return None


# ── public engine ──────────────────────────────────────────────────────────────

class CameraTracker:
    """
    Tracks faces/objects using OpenCV trackers.
    Computes pan/tilt deltas via PID controllers.
    """

    def __init__(self):
        self._tracker_backend = self._init_backend()
        self._pan_pid  = _PID(Kp=0.1, Ki=0.01, Kd=0.05)
        self._tilt_pid = _PID(Kp=0.1, Ki=0.01, Kd=0.05)
        self._tracking_label: str = ""
        self._frame_h: int = 480
        self._frame_w: int = 640

    def _init_backend(self):
        try:
            return _CSRTBackend()
        except Exception:
            pass
        try:
            return _KCFBackend()
        except Exception:
            pass
        return _MockTrackerBackend()

    # ── internal helpers ──────────────────────────────────────────────────────

    def _bbox_to_track_result(
        self, ok: bool, bbox: tuple, frame_w: int, frame_h: int, label: str
    ) -> TrackResult:
        if not ok or frame_w == 0 or frame_h == 0:
            return TrackResult(0.5, 0.5, 0.0, 0.0, False, label)
        x, y, w, h = bbox
        cx = (x + w / 2) / frame_w
        cy = (y + h / 2) / frame_h
        nw = w / frame_w
        nh = h / frame_h
        return TrackResult(cx, cy, nw, nh, True, label)

    def _frame_size(self, frame) -> Tuple[int, int]:
        try:
            h, w = frame.shape[:2]
            return w, h
        except Exception:
            return self._frame_w, self._frame_h

    # ── public API ────────────────────────────────────────────────────────────

    def track_face(self, frame) -> TrackResult:
        """Detect and track the first face in frame."""
        frame_w, frame_h = self._frame_size(frame)
        self._frame_w, self._frame_h = frame_w, frame_h

        if isinstance(self._tracker_backend, _MockTrackerBackend):
            ok, bbox = self._tracker_backend.update(frame)
            return self._bbox_to_track_result(ok, bbox, frame_w, frame_h, "face")

        bbox = _detect_face_bbox(frame)
        if bbox is None:
            ok, bbox = self._tracker_backend.update(frame)
        else:
            self._tracker_backend.init(frame, bbox)
            ok = True
        return self._bbox_to_track_result(ok, bbox or (0,0,0,0), frame_w, frame_h, "face")

    def track_object(self, frame, object_class: str) -> TrackResult:
        """Track object of given class (uses existing tracker state)."""
        frame_w, frame_h = self._frame_size(frame)
        self._frame_w, self._frame_h = frame_w, frame_h
        ok, bbox = self._tracker_backend.update(frame)
        return self._bbox_to_track_result(ok, bbox, frame_w, frame_h, object_class)

    def get_pan_tilt_command(
        self, track_result: TrackResult, frame_size: Tuple[int, int]
    ) -> Tuple[float, float]:
        """
        Returns (pan_delta_deg, tilt_delta_deg) to re-center target.
        Positive pan = rotate right; positive tilt = tilt up.
        Output clamped to ±30 degrees.
        """
        if not track_result.tracked:
            self._pan_pid.reset()
            self._tilt_pid.reset()
            return 0.0, 0.0

        # Error = distance from frame center (normalized)
        pan_error  = track_result.target_x - 0.5   # positive = target right of center
        tilt_error = 0.5 - track_result.target_y   # positive = target above center

        pan_delta  = self._pan_pid.update(pan_error)   * 30.0
        tilt_delta = self._tilt_pid.update(tilt_error) * 30.0

        # Clamp to ±30°
        pan_delta  = max(-30.0, min(30.0, pan_delta))
        tilt_delta = max(-30.0, min(30.0, tilt_delta))

        return pan_delta, tilt_delta

    @property
    def backend_name(self) -> str:
        return type(self._tracker_backend).__name__
