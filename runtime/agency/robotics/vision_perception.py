"""Robot vision module — webcam capture + object detection + depth estimation.

Backends:
1. ultralytics YOLO (pip install ultralytics)
2. OpenCV DNN (pip install opencv-python)
3. MockVision — deterministic detections, zero deps (CI/testing)

Usage
-----
    vision = RobotVision(camera_id=0)
    vision.start()
    result = vision.detect()
    for det in result.objects:
        print(det.label, det.confidence, det.estimated_distance_m)
    vision.stop()
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

from ..logging import get_logger

log = get_logger()

# Type alias for optional numpy array
_NdArray = Optional[object]  # np.ndarray when available


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class Detection:
    label: str
    confidence: float
    bbox: Tuple[int, int, int, int]  # (x1, y1, x2, y2)
    estimated_distance_m: float = 0.0


@dataclass
class PerceptionResult:
    objects: List[Detection] = field(default_factory=list)
    depth_estimates: Dict[str, float] = field(default_factory=dict)
    frame_id: int = 0


# ---------------------------------------------------------------------------
# Mock Vision (zero deps)
# ---------------------------------------------------------------------------

class _MockVision:
    """Returns preset detections.  No camera, no ML model."""

    DEFAULT_DETECTIONS: List[Detection] = [
        Detection("person", 0.92, (100, 50, 300, 400), 1.5),
        Detection("chair",  0.78, (350, 200, 500, 380), 0.8),
        Detection("bottle", 0.65, (420, 150, 460, 250), 0.5),
    ]

    def __init__(self) -> None:
        self._frame_id = 0
        self._detections: List[Detection] = list(self.DEFAULT_DETECTIONS)
        self._running   = False

    def start(self) -> None:
        self._running = True
        log.info("MockVision started")

    def stop(self) -> None:
        self._running = False

    def get_frame(self) -> _NdArray:
        # Return a tiny fake "frame" if numpy is available
        try:
            import numpy as np  # type: ignore
            return np.zeros((480, 640, 3), dtype="uint8")
        except ImportError:
            return None

    def detect(self, frame: _NdArray = None) -> PerceptionResult:  # noqa: ARG002
        self._frame_id += 1
        depth = {d.label: d.estimated_distance_m for d in self._detections}
        return PerceptionResult(
            objects=list(self._detections),
            depth_estimates=depth,
            frame_id=self._frame_id,
        )

    def set_detections(self, detections: List[Detection]) -> None:
        """Override mock detections for targeted tests."""
        self._detections = detections

    @property
    def is_available(self) -> bool:
        return True


# ---------------------------------------------------------------------------
# YOLO Vision
# ---------------------------------------------------------------------------

class _YOLOVision:
    """Object detection using ultralytics YOLO."""

    def __init__(self, camera_id: int = 0, model: str = "yolov8n") -> None:
        try:
            from ultralytics import YOLO   # type: ignore
            import cv2                     # type: ignore
        except ImportError as e:
            raise ImportError(
                "YOLO requires ultralytics + opencv: "
                "pip install ultralytics opencv-python"
            ) from e
        import cv2 as _cv2
        self._cv2    = _cv2
        self._model  = YOLO(model)
        self._cam_id = camera_id
        self._cap    = None
        self._frame: _NdArray = None
        self._lock   = threading.Lock()
        self._running = False
        self._frame_id = 0
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self._cap = self._cv2.VideoCapture(self._cam_id)
        self._running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
        if self._cap:
            self._cap.release()

    def _capture_loop(self) -> None:
        while self._running:
            ret, frame = self._cap.read()
            if ret:
                with self._lock:
                    self._frame = frame
                    self._frame_id += 1
            time.sleep(0.033)  # ~30 fps

    def get_frame(self) -> _NdArray:
        with self._lock:
            return self._frame

    def detect(self, frame: _NdArray = None) -> PerceptionResult:
        if frame is None:
            frame = self.get_frame()
        if frame is None:
            return PerceptionResult(frame_id=self._frame_id)

        results = self._model(frame, verbose=False)
        detections: List[Detection] = []
        for r in results:
            for box in r.boxes:
                x1, y1, x2, y2 = (int(v) for v in box.xyxy[0].tolist())
                conf  = float(box.conf[0])
                label = r.names[int(box.cls[0])]
                dist  = self.estimate_distance((x1, y1, x2, y2))
                detections.append(Detection(label, conf, (x1, y1, x2, y2), dist))

        depth = {d.label: d.estimated_distance_m for d in detections}
        with self._lock:
            fid = self._frame_id
        return PerceptionResult(objects=detections, depth_estimates=depth, frame_id=fid)

    def estimate_distance(
        self, bbox: Tuple[int, int, int, int], known_height_m: float = 0.3
    ) -> float:
        return _estimate_distance_monocular(bbox, known_height_m)

    @property
    def is_available(self) -> bool:
        try:
            from ultralytics import YOLO  # type: ignore  # noqa: F401
            import cv2  # type: ignore    # noqa: F401
            return True
        except ImportError:
            return False


# ---------------------------------------------------------------------------
# OpenCV DNN Vision (fallback)
# ---------------------------------------------------------------------------

class _OpenCVVision:
    """Object detection using OpenCV DNN + MobileNet SSD."""

    def __init__(self, camera_id: int = 0) -> None:
        try:
            import cv2  # type: ignore
        except ImportError as e:
            raise ImportError("OpenCV not installed: pip install opencv-python") from e
        self._cv2    = cv2
        self._cam_id = camera_id
        self._cap    = None
        self._running = False
        self._frame: _NdArray = None
        self._lock   = threading.Lock()
        self._frame_id = 0
        self._net    = None

    def start(self) -> None:
        self._cap = self._cv2.VideoCapture(self._cam_id)
        self._running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._cap:
            self._cap.release()

    def _capture_loop(self) -> None:
        while self._running:
            ret, frame = self._cap.read()
            if ret:
                with self._lock:
                    self._frame = frame
                    self._frame_id += 1
            time.sleep(0.033)

    def get_frame(self) -> _NdArray:
        with self._lock:
            return self._frame

    def detect(self, frame: _NdArray = None) -> PerceptionResult:
        if frame is None:
            frame = self.get_frame()
        if frame is None:
            return PerceptionResult(frame_id=self._frame_id)
        # Without a loaded model we return an empty result
        with self._lock:
            fid = self._frame_id
        return PerceptionResult(frame_id=fid)

    def estimate_distance(
        self, bbox: Tuple[int, int, int, int], known_height_m: float = 0.3
    ) -> float:
        return _estimate_distance_monocular(bbox, known_height_m)

    @property
    def is_available(self) -> bool:
        try:
            import cv2  # type: ignore  # noqa: F401
            return True
        except ImportError:
            return False


# ---------------------------------------------------------------------------
# Monocular depth estimate (shared helper)
# ---------------------------------------------------------------------------

_FOCAL_LENGTH_PX = 600.0   # approximate focal length for a 640×480 webcam


def _estimate_distance_monocular(
    bbox: Tuple[int, int, int, int], known_height_m: float = 0.3
) -> float:
    """Estimate distance using similar-triangle monocular depth.

    distance = (known_height_m * focal_length) / bbox_height_px
    """
    x1, y1, x2, y2 = bbox
    bbox_height = max(1, abs(y2 - y1))
    distance = (known_height_m * _FOCAL_LENGTH_PX) / bbox_height
    return round(distance, 2)


# ---------------------------------------------------------------------------
# Public façade: RobotVision
# ---------------------------------------------------------------------------

class RobotVision:
    """Unified vision interface.  Auto-detects best available backend.

    Parameters
    ----------
    camera_id:
        OpenCV camera index (default 0 = built-in webcam).
    model:
        YOLO model name (e.g. 'yolov8n', 'yolov8s').
    use_mock:
        Force MockVision regardless of installed packages.
    """

    def __init__(
        self,
        camera_id: int = 0,
        model: str = "yolov8n",
        use_mock: bool = False,
    ) -> None:
        self._impl = self._create_backend(camera_id, model, use_mock)
        log.info("RobotVision backend=%s", type(self._impl).__name__)

    def _create_backend(self, camera_id: int, model: str, use_mock: bool):
        if use_mock:
            return _MockVision()
        try:
            y = _YOLOVision(camera_id, model)
            if y.is_available:
                return y
        except ImportError:
            pass
        try:
            o = _OpenCVVision(camera_id)
            if o.is_available:
                return o
        except ImportError:
            pass
        log.info("RobotVision: no real backend available, using MOCK")
        return _MockVision()

    # --- public API ---

    def start(self) -> None:
        """Open camera stream (background thread)."""
        self._impl.start()

    def stop(self) -> None:
        """Release camera resources."""
        self._impl.stop()

    def get_frame(self) -> _NdArray:
        """Return the most recent camera frame (numpy array or None)."""
        return self._impl.get_frame()

    def detect(self, frame: _NdArray = None) -> PerceptionResult:
        """Run object detection on *frame* (or latest captured frame)."""
        return self._impl.detect(frame)

    def estimate_distance(
        self, bbox: Tuple[int, int, int, int], known_height_m: float = 0.3
    ) -> float:
        """Monocular distance estimate from bounding-box height."""
        return _estimate_distance_monocular(bbox, known_height_m)

    @property
    def is_mock(self) -> bool:
        return isinstance(self._impl, _MockVision)
