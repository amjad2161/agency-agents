"""
face_recognition.py — Pass 22
Backend priority: face_recognition lib → OpenCV DNN (res10_300x300_ssd) → MockFaceRecognizer
"""
from __future__ import annotations

import os
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Union

logger = logging.getLogger(__name__)

# ── dataclass ──────────────────────────────────────────────────────────────────

@dataclass
class FaceMatch:
    name: str
    confidence: float
    bbox: tuple  # (x, y, w, h) normalised 0-1

# ── backend detection ──────────────────────────────────────────────────────────

_FACE_RECOGNITION_AVAILABLE = False
_OPENCV_DNN_AVAILABLE = False

try:
    import face_recognition as _fr
    import os as _os
    # Guard against self-import: the real library must have face_locations and
    # its __file__ must NOT be this file.
    _self_file = _os.path.abspath(__file__)
    _fr_file   = _os.path.abspath(getattr(_fr, "__file__", "") or "")
    if not hasattr(_fr, "face_locations") or _fr_file == _self_file:
        raise ImportError("face_recognition is our own module (self-import) — skipping")
    import numpy as _np_fr
    _FACE_RECOGNITION_AVAILABLE = True
    logger.info("face_recognition library available")
except (ImportError, AttributeError):
    pass

try:
    import cv2 as _cv2
    import numpy as _np_cv
    _OPENCV_DNN_AVAILABLE = True
    logger.info("OpenCV available for DNN face detection")
except ImportError:
    pass

if not _FACE_RECOGNITION_AVAILABLE and not _OPENCV_DNN_AVAILABLE:
    logger.warning("No face recognition backend available — using MockFaceRecognizer")

# ── Mock backend ───────────────────────────────────────────────────────────────

class MockFaceRecognizer:
    """Always returns a single unknown face — no external deps required."""

    def load_known_faces(self, directory: str) -> int:
        logger.debug("MockFaceRecognizer.load_known_faces(%s) — no-op", directory)
        return 0

    def recognize_frame(self, img_array) -> List[FaceMatch]:
        return [FaceMatch("unknown", 0.0, (0, 0, 1, 1))]

    def identify_person(self, img_path_or_array) -> str:
        return "unknown"


# ── OpenCV DNN backend ─────────────────────────────────────────────────────────

class _OpenCVDNNRecognizer:
    """Uses res10_300x300_ssd_iter_140000 for detection only (no recognition)."""

    _MODEL_URL = (
        "https://raw.githubusercontent.com/opencv/opencv_3rdparty/dnn_samples_face_detector_20170830/"
        "res10_300x300_ssd_iter_140000.caffemodel"
    )
    _PROTO_URL = (
        "https://raw.githubusercontent.com/opencv/opencv/master/samples/dnn/"
        "face_detector/deploy.prototxt"
    )

    def __init__(self):
        self._net = None
        self._known: dict = {}  # name → list of sample paths

    def _get_net(self):
        if self._net is not None:
            return self._net
        model_path = Path(__file__).parent / "models" / "res10_300x300_ssd.caffemodel"
        proto_path = Path(__file__).parent / "models" / "deploy.prototxt"
        if model_path.exists() and proto_path.exists():
            self._net = _cv2.dnn.readNetFromCaffe(str(proto_path), str(model_path))
        return self._net

    def load_known_faces(self, directory: str) -> int:
        self._known = {}
        d = Path(directory)
        if not d.exists():
            return 0
        count = 0
        for person_dir in d.iterdir():
            if person_dir.is_dir():
                imgs = list(person_dir.glob("*.jpg")) + list(person_dir.glob("*.png"))
                if imgs:
                    self._known[person_dir.name] = [str(p) for p in imgs]
                    count += len(imgs)
        logger.info("OpenCV: loaded %d images across %d people", count, len(self._known))
        return count

    def recognize_frame(self, img_array) -> List[FaceMatch]:
        net = self._get_net()
        if net is None:
            return [FaceMatch("unknown", 0.0, (0, 0, 1, 1))]
        h, w = img_array.shape[:2]
        blob = _cv2.dnn.blobFromImage(
            _cv2.resize(img_array, (300, 300)), 1.0,
            (300, 300), (104.0, 177.0, 123.0)
        )
        net.setInput(blob)
        detections = net.forward()
        results: List[FaceMatch] = []
        for i in range(detections.shape[2]):
            confidence = float(detections[0, 0, i, 2])
            if confidence < 0.5:
                continue
            box = detections[0, 0, i, 3:7]
            x1, y1, x2, y2 = (box * [w, h, w, h]).astype(int)
            bx = (x1 / w, y1 / h, (x2 - x1) / w, (y2 - y1) / h)
            results.append(FaceMatch("unknown", confidence, bx))
        return results if results else [FaceMatch("unknown", 0.0, (0, 0, 1, 1))]

    def identify_person(self, img_path_or_array) -> str:
        # DNN-only: detection without recognition → always "unknown"
        return "unknown"


# ── face_recognition lib backend ──────────────────────────────────────────────

class _FaceRecognitionLibRecognizer:
    """Full face recognition using the face_recognition library."""

    def __init__(self):
        self._known_encodings: list = []
        self._known_names: list = []

    def load_known_faces(self, directory: str) -> int:
        import numpy as np
        self._known_encodings = []
        self._known_names = []
        d = Path(directory)
        if not d.exists():
            return 0
        count = 0
        for person_dir in d.iterdir():
            if not person_dir.is_dir():
                continue
            for img_path in list(person_dir.glob("*.jpg")) + list(person_dir.glob("*.png")):
                try:
                    img = _fr.load_image_file(str(img_path))
                    encs = _fr.face_encodings(img)
                    if encs:
                        self._known_encodings.append(encs[0])
                        self._known_names.append(person_dir.name)
                        count += 1
                except Exception as exc:
                    logger.warning("Could not encode %s: %s", img_path, exc)
        logger.info("face_recognition: loaded %d encodings", count)
        return count

    def recognize_frame(self, img_array) -> List[FaceMatch]:
        import numpy as np
        locations = _fr.face_locations(img_array)
        encodings = _fr.face_encodings(img_array, locations)
        h, w = img_array.shape[:2]
        results: List[FaceMatch] = []
        for enc, loc in zip(encodings, locations):
            top, right, bottom, left = loc
            bbox = (left / w, top / h, (right - left) / w, (bottom - top) / h)
            if self._known_encodings:
                distances = _fr.face_distance(self._known_encodings, enc)
                best_idx = int(np.argmin(distances))
                best_dist = float(distances[best_idx])
                confidence = max(0.0, 1.0 - best_dist)
                name = self._known_names[best_idx] if confidence > 0.5 else "unknown"
            else:
                name = "unknown"
                confidence = 0.0
            results.append(FaceMatch(name, confidence, bbox))
        return results if results else [FaceMatch("unknown", 0.0, (0, 0, 1, 1))]

    def identify_person(self, img_path_or_array) -> str:
        if isinstance(img_path_or_array, (str, Path)):
            img = _fr.load_image_file(str(img_path_or_array))
        else:
            img = img_path_or_array
        matches = self.recognize_frame(img)
        if matches:
            best = max(matches, key=lambda m: m.confidence)
            return best.name
        return "unknown"


# ── Public facade ──────────────────────────────────────────────────────────────

class FaceRecognizer:
    """
    Facade that selects the best available backend automatically.
    Backend priority: face_recognition lib → OpenCV DNN → Mock
    """

    def __init__(self):
        if _FACE_RECOGNITION_AVAILABLE:
            self._backend = _FaceRecognitionLibRecognizer()
            self._backend_name = "face_recognition"
        elif _OPENCV_DNN_AVAILABLE:
            self._backend = _OpenCVDNNRecognizer()
            self._backend_name = "opencv_dnn"
        else:
            self._backend = MockFaceRecognizer()
            self._backend_name = "mock"
        logger.info("FaceRecognizer using backend: %s", self._backend_name)

    @property
    def backend_name(self) -> str:
        return self._backend_name

    def load_known_faces(self, directory: str) -> int:
        """
        Load face encodings from directory.
        Expected layout: <directory>/<person_name>/<img1.jpg> ...
        Returns number of images loaded.
        """
        return self._backend.load_known_faces(directory)

    def recognize_frame(self, img_array) -> List[FaceMatch]:
        """
        Detect and recognise faces in a numpy image array (H×W×3 BGR or RGB).
        Returns list of FaceMatch objects.
        """
        return self._backend.recognize_frame(img_array)

    def identify_person(self, img_path_or_array) -> str:
        """
        Identify the most prominent person in an image.
        Accepts file path (str/Path) or numpy array.
        Returns person name string.
        """
        return self._backend.identify_person(img_path_or_array)


# ── CLI convenience ────────────────────────────────────────────────────────────

def cli_identify(image_path: str) -> str:
    rec = FaceRecognizer()
    result = rec.identify_person(image_path)
    print(f"זוהה: {result}")
    return result
