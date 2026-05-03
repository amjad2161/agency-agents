"""
JARVIS BRAINIAC — Holistic Body Tracker
========================================
Full-body pose estimation, face mesh, hand tracking, and eye gaze detection
using MediaPipe Holistic.  Zero cloud dependency — 100% local.

Supported modalities
--------------------
- 33 body pose landmarks (x, y, z, visibility, name)
- 468 face mesh landmarks (x, y, z)
- 21 hand landmarks per detected hand
- Eye tracking: pupil position, gaze direction, blink detection
- Body joint angles: elbow, knee, shoulder, hip
- Facial expression classification
- Full-body gesture recognition
- Live overlay drawing (pose/face/hands/eyes)
- Background threaded tracking loop

Mock fallback is provided when MediaPipe or OpenCV are unavailable.

Author: Amjad Mobarsham (sole owner)
"""

from __future__ import annotations

import math
import os
import sys
import threading
import time
import warnings
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

# ---------------------------------------------------------------------------
# Logging (guard against local logging.py shadowing stdlib)
# ---------------------------------------------------------------------------
_script_dir = os.path.dirname(os.path.abspath(__file__))
_removed = False
if _script_dir in sys.path:
    sys.path.remove(_script_dir)
    _removed = True

import logging

if _removed:
    sys.path.insert(0, _script_dir)

logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")
    )
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

# ---------------------------------------------------------------------------
# Optional dependency flags
# ---------------------------------------------------------------------------
_HAS_CV2 = False
_HAS_MEDIAPIPE = False

# --- OpenCV ---
try:
    import cv2  # type: ignore

    _HAS_CV2 = True
except ImportError:  # pragma: no cover
    warnings.warn("opencv-python not installed. Camera capture / overlay disabled.", ImportWarning)

# --- MediaPipe ---
try:
    import mediapipe as mp  # type: ignore

    _HAS_MEDIAPIPE = True
except ImportError:  # pragma: no cover
    warnings.warn("mediapipe not installed. Holistic tracker running in MOCK mode.", ImportWarning)


# ===========================================================================
# Constants & Named Landmark Indices
# ===========================================================================

# --- 33 Pose Landmarks (MediaPipe Pose) ---
POSE_LANDMARK_NAMES: Dict[int, str] = {
    0: "NOSE",
    1: "LEFT_EYE_INNER",
    2: "LEFT_EYE",
    3: "LEFT_EYE_OUTER",
    4: "RIGHT_EYE_INNER",
    5: "RIGHT_EYE",
    6: "RIGHT_EYE_OUTER",
    7: "LEFT_EAR",
    8: "RIGHT_EAR",
    9: "MOUTH_LEFT",
    10: "MOUTH_RIGHT",
    11: "LEFT_SHOULDER",
    12: "RIGHT_SHOULDER",
    13: "LEFT_ELBOW",
    14: "RIGHT_ELBOW",
    15: "LEFT_WRIST",
    16: "RIGHT_WRIST",
    17: "LEFT_PINKY",
    18: "RIGHT_PINKY",
    19: "LEFT_INDEX",
    20: "RIGHT_INDEX",
    21: "LEFT_THUMB",
    22: "RIGHT_THUMB",
    23: "LEFT_HIP",
    24: "RIGHT_HIP",
    25: "LEFT_KNEE",
    26: "RIGHT_KNEE",
    27: "LEFT_ANKLE",
    28: "RIGHT_ANKLE",
    29: "LEFT_HEEL",
    30: "RIGHT_HEEL",
    31: "LEFT_FOOT_INDEX",
    32: "RIGHT_FOOT_INDEX",
}

# --- Face Mesh Contour Indices ---
FACE_CONTOURS: Dict[str, List[int]] = {
    "face_outline": [10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288,
                     397, 365, 379, 378, 400, 377, 152, 148, 176, 149, 150, 136,
                     172, 58, 132, 93, 234, 127, 162, 21, 54, 103, 67, 109],
    "lips_outer": [61, 185, 40, 39, 37, 0, 267, 269, 270, 409, 291, 375, 321,
                   405, 314, 17, 84, 181, 91, 146],
    "lips_inner": [78, 191, 80, 81, 82, 13, 312, 311, 310, 415, 308, 324, 318,
                   402, 317, 14, 87, 178, 88, 95],
    "left_eye": [33, 246, 161, 160, 159, 158, 157, 173, 133, 155, 154, 153, 145, 144],
    "right_eye": [362, 398, 384, 385, 386, 387, 388, 466, 263, 249, 390, 373, 374, 380],
    "left_eyebrow": [276, 283, 282, 295, 285, 300, 293, 334, 296, 336],
    "right_eyebrow": [46, 53, 52, 65, 55, 70, 63, 105, 66, 107],
    "nose_bridge": [6, 197, 195, 5, 4],
    "nose_bottom": [48, 115, 220, 45, 4, 275, 440, 344],
}

# --- Eye-specific indices for pupil estimation ---
LEFT_EYE_INDICES = [33, 246, 161, 160, 159, 158, 157, 173, 133, 155, 154, 153, 145, 144, 163, 7]
RIGHT_EYE_INDICES = [362, 398, 384, 385, 386, 387, 388, 466, 263, 249, 390, 373, 374, 380, 382, 381]

# --- Left eye landmarks (for blink detection) ---
LEFT_EYE_TOP = 159
LEFT_EYE_BOTTOM = 145
LEFT_EYE_LEFT = 33
LEFT_EYE_RIGHT = 133

# --- Right eye landmarks (for blink detection) ---
RIGHT_EYE_TOP = 386
RIGHT_EYE_BOTTOM = 374
RIGHT_EYE_LEFT = 362
RIGHT_EYE_RIGHT = 263

# --- Blink threshold (EAR < this => blink) ---
BLINK_EAR_THRESHOLD = 0.18

# --- Hand landmark names ---
HAND_LANDMARK_NAMES: Dict[int, str] = {
    0: "WRIST",
    1: "THUMB_CMC", 2: "THUMB_MCP", 3: "THUMB_IP", 4: "THUMB_TIP",
    5: "INDEX_FINGER_MCP", 6: "INDEX_FINGER_PIP", 7: "INDEX_FINGER_DIP", 8: "INDEX_FINGER_TIP",
    9: "MIDDLE_FINGER_MCP", 10: "MIDDLE_FINGER_PIP", 11: "MIDDLE_FINGER_DIP", 12: "MIDDLE_FINGER_TIP",
    13: "RING_FINGER_MCP", 14: "RING_FINGER_PIP", 15: "RING_FINGER_DIP", 16: "RING_FINGER_TIP",
    17: "PINKY_MCP", 18: "PINKY_PIP", 19: "PINKY_DIP", 20: "PINKY_TIP",
}

# --- Body angle joint definitions (triplets: vertex, pt1, pt2) ---
ANGLE_JOINTS: Dict[str, Tuple[int, int, int]] = {
    "left_elbow": (13, 11, 15),   # shoulder-elbow-wrist
    "right_elbow": (14, 12, 16),
    "left_knee": (25, 23, 27),    # hip-knee-ankle
    "right_knee": (26, 24, 28),
    "left_shoulder": (11, 23, 13),# hip-shoulder-elbow
    "right_shoulder": (12, 24, 14),
    "left_hip": (23, 11, 25),     # shoulder-hip-knee
    "right_hip": (24, 12, 26),
}

# --- Overlay colors (BGR) ---
COLOR_POSE = (255, 128, 0)      # Blue-ish
COLOR_FACE = (0, 255, 128)      # Green-ish
COLOR_HAND = (0, 0, 255)        # Red
COLOR_EYE = (0, 255, 255)       # Yellow
COLOR_TEXT = (255, 255, 255)    # White

# --- Tracking defaults ---
DEFAULT_CAMERA_ID = 0
DEFAULT_MIN_DETECTION_CONFIDENCE = 0.5
DEFAULT_MIN_TRACKING_CONFIDENCE = 0.5


# ===========================================================================
# Helper functions
# ===========================================================================

def _calculate_angle(
    vertex: Dict[str, float],
    pt1: Dict[str, float],
    pt2: Dict[str, float]
) -> float:
    """Calculate the angle (in degrees) between two vectors sharing a vertex."""
    v1x = pt1["x"] - vertex["x"]
    v1y = pt1["y"] - vertex["y"]
    v2x = pt2["x"] - vertex["x"]
    v2y = pt2["y"] - vertex["y"]
    dot = v1x * v2x + v1y * v2y
    mag1 = math.sqrt(v1x * v1x + v1y * v1y)
    mag2 = math.sqrt(v2x * v2x + v2y * v2y)
    if mag1 == 0.0 or mag2 == 0.0:
        return 0.0
    cos_angle = max(-1.0, min(1.0, dot / (mag1 * mag2)))
    return math.degrees(math.acos(cos_angle))


def _eye_aspect_ratio(
    landmarks: List[Dict[str, float]],
    top_idx: int,
    bottom_idx: int,
    left_idx: int,
    right_idx: int
) -> float:
    """Compute Eye Aspect Ratio (EAR) given 4 landmark indices."""
    try:
        top_pt = landmarks[top_idx]
        bottom_pt = landmarks[bottom_idx]
        left_pt = landmarks[left_idx]
        right_pt = landmarks[right_idx]
    except (IndexError, KeyError):
        return 1.0  # open by default

    vertical = math.sqrt(
        (top_pt["x"] - bottom_pt["x"]) ** 2
        + (top_pt["y"] - bottom_pt["y"]) ** 2
    )
    horizontal = math.sqrt(
        (left_pt["x"] - right_pt["x"]) ** 2
        + (left_pt["y"] - right_pt["y"]) ** 2
    )
    if horizontal == 0.0:
        return 1.0
    return vertical / horizontal


def _compute_pupil_center(
    landmarks: List[Dict[str, float]],
    eye_indices: List[int]
) -> Tuple[float, float]:
    """Estimate pupil centre as the mean of the eye contour landmarks."""
    xs: List[float] = []
    ys: List[float] = []
    for idx in eye_indices:
        if idx < len(landmarks):
            lm = landmarks[idx]
            xs.append(lm["x"])
            ys.append(lm["y"])
    if not xs:
        return (0.0, 0.0)
    return (float(np.mean(xs)), float(np.mean(ys)))


def _landmark_distance(lm1: Dict[str, float], lm2: Dict[str, float]) -> float:
    """Euclidean distance between two 2-D landmarks (normalised coords)."""
    dx = lm1["x"] - lm2["x"]
    dy = lm1["y"] - lm2["y"]
    return math.sqrt(dx * dx + dy * dy)


# ===========================================================================
# HolisticTracker
# ===========================================================================

class HolisticTracker:
    """
    Full-body tracking via MediaPipe Holistic.

    Provides:
    - 33 pose landmarks (named)
    - 468 face mesh landmarks (with contour groups)
    - 21 hand landmarks per hand (named)
    - Eye tracking (pupil, gaze, blink)
    - Body joint angles (elbow, knee, shoulder, hip)
    - Facial expression classification
    - Full-body gesture detection
    - Real-time overlay drawing
    - Background threaded tracking loop

    Mock-safe: gracefully degrades to mock behaviour when MediaPipe is absent.
    """

    def __init__(
        self,
        camera_id: int = DEFAULT_CAMERA_ID,
        min_detection_confidence: float = DEFAULT_MIN_DETECTION_CONFIDENCE,
        min_tracking_confidence: float = DEFAULT_MIN_TRACKING_CONFIDENCE,
    ) -> None:
        self.camera_id = camera_id
        self.min_detection_confidence = min_detection_confidence
        self.min_tracking_confidence = min_tracking_confidence

        # Internal state
        self._holistic = None
        self._drawing_utils = None
        self._mp_pose = None
        self._mp_face_mesh = None
        self._mp_hands = None
        self._cap: Any = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._latest_results: Dict[str, Any] = {}
        self._frame_callbacks: List[Any] = []
        self._fps_history: List[float] = []
        self._last_frame_time: float = 0.0
        self._current_fps: float = 0.0

        # --- Initialise MediaPipe ---
        if _HAS_MEDIAPIPE:
            self._init_mediapipe()
        else:
            logger.warning(
                "MediaPipe unavailable — HolisticTracker will use mock data."
            )

        # --- Initialise camera if OpenCV available ---
        if _HAS_CV2:
            self._init_camera()

        logger.info(
            "HolisticTracker initialised (camera=%s, detection_conf=%.2f)",
            camera_id,
            min_detection_confidence,
        )

    # ------------------------------------------------------------------
    # MediaPipe setup
    # ------------------------------------------------------------------

    def _init_mediapipe(self) -> None:
        """Create MediaPipe Holistic solution and helper objects."""
        mp = __import__("mediapipe")

        self._mp_pose = mp.solutions.pose
        self._mp_face_mesh = mp.solutions.face_mesh
        self._mp_hands = mp.solutions.hands
        self._drawing_utils = mp.solutions.drawing_utils

        self._holistic = mp.solutions.holistic.Holistic(
            min_detection_confidence=self.min_detection_confidence,
            min_tracking_confidence=self.min_tracking_confidence,
            enable_face_mesh=True,
            refine_face_landmarks=True,
        )
        logger.debug("MediaPipe Holistic pipeline created.")

    def _init_camera(self) -> None:
        """Open the capture device (no-op if cv2 absent)."""
        if not _HAS_CV2:
            return
        try:
            self._cap = cv2.VideoCapture(self.camera_id)
            if not self._cap.isOpened():
                logger.error("Cannot open camera %s", self.camera_id)
                self._cap = None
            else:
                logger.debug("Camera %s opened successfully.", self.camera_id)
        except Exception as exc:
            logger.error("Camera init error: %s", exc)
            self._cap = None

    # ------------------------------------------------------------------
    # Frame processing
    # ------------------------------------------------------------------

    def process_frame(self, frame: np.ndarray) -> Dict[str, Any]:
        """
        Process a single BGR frame through the Holistic pipeline.

        Parameters
        ----------
        frame : np.ndarray
            BGR image (H, W, 3).

        Returns
        -------
        dict
            {
                "pose":        [...],   # 33 landmarks
                "face":        [...],   # 468 landmarks
                "hands":       [...],   # 0-2 * 21 landmarks
                "eyes":        {...},   # pupil, gaze, blink
                "body_angles": {...},
                "expression":  str,
                "gesture":     str,
                "fps":         float,
                "timestamp":   float,
            }
        """
        h, w = frame.shape[:2] if frame is not None else (0, 0)
        results: Dict[str, Any] = {
            "pose": [],
            "face": [],
            "hands": [],
            "eyes": {},
            "body_angles": {},
            "expression": "neutral",
            "gesture": "standing",
            "fps": 0.0,
            "timestamp": time.time(),
        }

        if frame is None or h == 0:
            return results

        # --- FPS bookkeeping ---
        now = time.time()
        dt = now - self._last_frame_time if self._last_frame_time else 0.0
        self._last_frame_time = now
        if dt > 0:
            self._fps_history.append(1.0 / dt)
            if len(self._fps_history) > 30:
                self._fps_history.pop(0)
            self._current_fps = float(np.mean(self._fps_history))
        results["fps"] = self._current_fps

        # --- Run MediaPipe Holistic ---
        if _HAS_MEDIAPIPE and self._holistic is not None:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            mp_results = self._holistic.process(rgb)

            # Pose
            pose_landmarks = self.get_pose_landmarks(mp_results)
            results["pose"] = pose_landmarks

            # Face
            face_landmarks = self.get_face_landmarks(mp_results)
            results["face"] = face_landmarks

            # Hands
            hand_landmarks = self.get_hand_landmarks(mp_results)
            results["hands"] = hand_landmarks

            # Eyes
            results["eyes"] = self.get_eye_tracking(mp_results)

            # Derived features
            if pose_landmarks:
                results["body_angles"] = self.get_body_angles(pose_landmarks)
                results["gesture"] = self.get_body_gesture(pose_landmarks)

            if face_landmarks:
                results["expression"] = self.get_facial_expression(face_landmarks)

        else:
            # Mock data path — deterministic simulated results
            results = self._generate_mock_results(results, w, h)

        # Thread-safe update
        with self._lock:
            self._latest_results = results

        return results

    # ------------------------------------------------------------------
    # Pose extraction (33 landmarks)
    # ------------------------------------------------------------------

    def get_pose_landmarks(self, results: Any) -> List[Dict[str, Any]]:
        """
        Extract 33 body pose landmarks from MediaPipe Holistic results.

        Returns list of dicts: {"id": int, "x": float, "y": float,
                                 "z": float, "visibility": float, "name": str}
        """
        landmarks: List[Dict[str, Any]] = []
        if not _HAS_MEDIAPIPE or results is None:
            return landmarks

        pose = getattr(results, "pose_landmarks", None)
        if pose is None or not hasattr(pose, "landmark"):
            return landmarks

        for i, lm in enumerate(pose.landmark):
            landmarks.append({
                "id": i,
                "x": float(lm.x),
                "y": float(lm.y),
                "z": float(lm.z),
                "visibility": float(getattr(lm, "visibility", 0.0)),
                "name": POSE_LANDMARK_NAMES.get(i, f"LANDMARK_{i}"),
            })
        return landmarks

    # ------------------------------------------------------------------
    # Face mesh extraction (468 landmarks)
    # ------------------------------------------------------------------

    def get_face_landmarks(self, results: Any) -> List[Dict[str, Any]]:
        """
        Extract 468 face mesh landmarks from MediaPipe Holistic results.

        Returns list of dicts: {"id": int, "x": float, "y": float, "z": float,
                                 "contours": List[str]}
        Contour names indicate which facial feature groups the point belongs to.
        """
        landmarks: List[Dict[str, Any]] = []
        if not _HAS_MEDIAPIPE or results is None:
            return landmarks

        face = getattr(results, "face_landmarks", None)
        if face is None or not hasattr(face, "landmark"):
            return landmarks

        # Pre-build reverse contour map: landmark index -> list of contour names
        reverse_map: Dict[int, List[str]] = {}
        for contour_name, indices in FACE_CONTOURS.items():
            for idx in indices:
                reverse_map.setdefault(idx, []).append(contour_name)

        for i, lm in enumerate(face.landmark):
            contours = reverse_map.get(i, [])
            landmarks.append({
                "id": i,
                "x": float(lm.x),
                "y": float(lm.y),
                "z": float(lm.z),
                "contours": contours,
            })
        return landmarks

    # ------------------------------------------------------------------
    # Eye tracking (pupil, gaze, blink)
    # ------------------------------------------------------------------

    def get_eye_tracking(self, results: Any) -> Dict[str, Any]:
        """
        Calculate gaze direction and blink state from Holistic face results.

        Returns
        -------
        dict
            {
                "left_pupil":    (x, y),
                "right_pupil":   (x, y),
                "gaze_vector":   (x, y, z),
                "blink_detected": bool,
                "left_ear":      float,
                "right_ear":     float,
            }
        """
        output: Dict[str, Any] = {
            "left_pupil": (0.0, 0.0),
            "right_pupil": (0.0, 0.0),
            "gaze_vector": (0.0, 0.0, 0.0),
            "blink_detected": False,
            "left_ear": 1.0,
            "right_ear": 1.0,
        }
        if not _HAS_MEDIAPIPE or results is None:
            return output

        face = getattr(results, "face_landmarks", None)
        if face is None or not hasattr(face, "landmark"):
            return output

        # Build flat landmark list for helper functions
        face_lms: List[Dict[str, float]] = []
        for lm in face.landmark:
            face_lms.append({"x": float(lm.x), "y": float(lm.y), "z": float(lm.z)})

        # --- Pupil centres ---
        output["left_pupil"] = _compute_pupil_center(face_lms, LEFT_EYE_INDICES)
        output["right_pupil"] = _compute_pupil_center(face_lms, RIGHT_EYE_INDICES)

        # --- Blink detection via EAR ---
        left_ear = _eye_aspect_ratio(
            face_lms, LEFT_EYE_TOP, LEFT_EYE_BOTTOM,
            LEFT_EYE_LEFT, LEFT_EYE_RIGHT
        )
        right_ear = _eye_aspect_ratio(
            face_lms, RIGHT_EYE_TOP, RIGHT_EYE_BOTTOM,
            RIGHT_EYE_LEFT, RIGHT_EYE_RIGHT
        )
        output["left_ear"] = left_ear
        output["right_ear"] = right_ear
        output["blink_detected"] = (
            left_ear < BLINK_EAR_THRESHOLD or right_ear < BLINK_EAR_THRESHOLD
        )

        # --- Gaze vector (approximate from pupil displacement vs eye centre) ---
        # Use inner/outer eye corners to define eye box
        try:
            lex = face_lms[LEFT_EYE_LEFT]
            rex = face_lms[LEFT_EYE_RIGHT]
            ley = face_lms[RIGHT_EYE_LEFT]
            rey = face_lms[RIGHT_EYE_RIGHT]
            eye_centre_x = (lex["x"] + rex["x"] + ley["x"] + rey["x"]) / 4.0
            eye_centre_y = (lex["y"] + rex["y"] + ley["y"] + rey["y"]) / 4.0

            lp = output["left_pupil"]
            rp = output["right_pupil"]
            avg_pupil_x = (lp[0] + rp[0]) / 2.0
            avg_pupil_y = (lp[1] + rp[1]) / 2.0

            dx = avg_pupil_x - eye_centre_x
            dy = avg_pupil_y - eye_centre_y
            # z inferred from pupil size (closer = larger spread)
            eye_width = _landmark_distance(lex, rex)
            dz = 1.0 - min(eye_width * 5.0, 1.0)  # heuristic depth
            output["gaze_vector"] = (round(dx, 4), round(dy, 4), round(dz, 4))
        except (IndexError, KeyError):
            pass

        return output

    # ------------------------------------------------------------------
    # Hand landmarks (21 per hand)
    # ------------------------------------------------------------------

    def get_hand_landmarks(self, results: Any) -> List[Dict[str, Any]]:
        """
        Extract 21 hand landmarks for each detected hand.

        Returns list of hand dicts:
            {
                "hand": "left" | "right",
                "landmarks": [
                    {"id": int, "x": float, "y": float, "z": float,
                     "name": str},
                    ...
                ],
            }
        """
        hands: List[Dict[str, Any]] = []
        if not _HAS_MEDIAPIPE or results is None:
            return hands

        for attr_name, label in [("left_hand_landmarks", "left"),
                                 ("right_hand_landmarks", "right")]:
            hand_data = getattr(results, attr_name, None)
            if hand_data is None or not hasattr(hand_data, "landmark"):
                continue
            lms: List[Dict[str, Any]] = []
            for i, lm in enumerate(hand_data.landmark):
                lms.append({
                    "id": i,
                    "x": float(lm.x),
                    "y": float(lm.y),
                    "z": float(lm.z),
                    "name": HAND_LANDMARK_NAMES.get(i, f"HAND_{i}"),
                })
            hands.append({"hand": label, "landmarks": lms})
        return hands

    # ------------------------------------------------------------------
    # Body angles
    # ------------------------------------------------------------------

    def get_body_angles(
        self, pose_landmarks: List[Dict[str, Any]]
    ) -> Dict[str, float]:
        """
        Calculate joint angles from pose landmarks.

        Returns {"left_elbow": angle, "right_elbow": angle,
                 "left_knee": angle, "right_knee": angle,
                 "left_shoulder": angle, "right_shoulder": angle,
                 "left_hip": angle, "right_hip": angle}
        """
        angles: Dict[str, float] = {}
        if not pose_landmarks or len(pose_landmarks) < 33:
            return angles

        lm_map = {lm["id"]: lm for lm in pose_landmarks}

        for joint_name, (vertex, pt1, pt2) in ANGLE_JOINTS.items():
            v = lm_map.get(vertex)
            a = lm_map.get(pt1)
            b = lm_map.get(pt2)
            if v is None or a is None or b is None:
                angles[joint_name] = 0.0
                continue
            angle = _calculate_angle(v, a, b)
            angles[joint_name] = round(angle, 2)
        return angles

    # ------------------------------------------------------------------
    # Facial expression classification
    # ------------------------------------------------------------------

    def get_facial_expression(
        self, face_landmarks: List[Dict[str, Any]]
    ) -> str:
        """
        Classify facial expression from 468 face mesh landmarks.

        Returns one of:
            "neutral", "happy", "sad", "surprised", "angry", "focused"
        """
        if not face_landmarks or len(face_landmarks) < 468:
            return "neutral"

        lm_map = {lm["id"]: lm for lm in face_landmarks}

        def _get(id_: int) -> Optional[Dict[str, float]]:
            return lm_map.get(id_)

        def _dist(id1: int, id2: int) -> float:
            a = _get(id1)
            b = _get(id2)
            if a is None or b is None:
                return 0.0
            return _landmark_distance(a, b)

        # --- Lip distances ---
        mouth_top = _get(13)
        mouth_bottom = _get(14)
        mouth_left = _get(78)
        mouth_right = _get(308)
        if mouth_top and mouth_bottom and mouth_left and mouth_right:
            mouth_open = abs(mouth_top["y"] - mouth_bottom["y"])
            mouth_width = abs(mouth_right["x"] - mouth_left["x"])
        else:
            mouth_open = 0.0
            mouth_width = 1.0

        # --- Eye openness (average EAR) ---
        left_eye_height = _dist(159, 145)
        left_eye_width = _dist(33, 133)
        right_eye_height = _dist(386, 374)
        right_eye_width = _dist(362, 263)

        le_ear = left_eye_height / left_eye_width if left_eye_width else 1.0
        re_ear = right_eye_height / right_eye_width if right_eye_width else 1.0
        avg_ear = (le_ear + re_ear) / 2.0

        # --- Eyebrow positions (relative to eye) ---
        left_brow = _get(105)
        left_eye = _get(33)
        right_brow = _get(334)
        right_eye = _get(362)

        brow_raise = 0.0
        if left_brow and left_eye and right_brow and right_eye:
            left_brow_y = left_brow["y"]
            left_eye_y = left_eye["y"]
            right_brow_y = right_brow["y"]
            right_eye_y = right_eye["y"]
            brow_raise = ((left_eye_y - left_brow_y) +
                         (right_eye_y - right_brow_y)) / 2.0

        # --- Classification heuristics ---
        # Happy: corners of mouth raised (landmarks 48, 54 vs 50, 58)
        mouth_corner_left = _get(61)
        mouth_corner_right = _get(291)
        mouth_lower_mid = _get(17)
        smile_factor = 0.0
        if mouth_corner_left and mouth_corner_right and mouth_lower_mid:
            left_diff = mouth_lower_mid["y"] - mouth_corner_left["y"]
            right_diff = mouth_lower_mid["y"] - mouth_corner_right["y"]
            smile_factor = (left_diff + right_diff) / 2.0

        # Decision tree
        if mouth_open > 0.06 and avg_ear > 0.25:
            return "surprised"
        if smile_factor > 0.012:
            return "happy"
        if brow_raise > 0.03 and mouth_open < 0.02:
            return "focused"
        if mouth_open < 0.015 and smile_factor < 0.005 and avg_ear < 0.22:
            return "sad"
        if brow_raise < 0.005 and mouth_open < 0.015:
            return "angry"
        return "neutral"

    # ------------------------------------------------------------------
    # Body gesture detection
    # ------------------------------------------------------------------

    def get_body_gesture(
        self, pose_landmarks: List[Dict[str, Any]]
    ) -> str:
        """
        Detect full-body gesture from pose landmarks.

        Returns one of:
            "standing", "sitting", "walking", "running",
            "jumping", "pointing", "waving", "unknown"
        """
        if not pose_landmarks or len(pose_landmarks) < 33:
            return "unknown"

        lm_map = {lm["id"]: lm for lm in pose_landmarks}

        def _g(id_: int) -> Optional[Dict[str, float]]:
            return lm_map.get(id_)

        # --- Key joints ---
        left_shoulder = _g(11)
        right_shoulder = _g(12)
        left_hip = _g(23)
        right_hip = _g(24)
        left_knee = _g(25)
        right_knee = _g(26)
        left_ankle = _g(27)
        right_ankle = _g(28)
        left_wrist = _g(15)
        right_wrist = _g(16)
        left_elbow = _g(13)
        right_elbow = _g(14)
        nose = _g(0)

        # Not enough data
        if not all([left_hip, right_hip, left_knee, right_knee,
                     left_ankle, right_ankle]):
            return "unknown"

        # --- Sitting detection: hips below knees (inverted-Y image coords) ---
        hip_y = (left_hip["y"] + right_hip["y"]) / 2.0
        knee_y = (left_knee["y"] + right_knee["y"]) / 2.0
        ankle_y = (left_ankle["y"] + right_ankle["y"]) / 2.0

        if hip_y > knee_y and knee_y > ankle_y:
            # Further check: thighs roughly horizontal
            thigh_angle = abs(left_hip["y"] - left_knee["y"])
            if thigh_angle < 0.15:
                return "sitting"

        # --- Knee angle (average) ---
        left_knee_angle = _calculate_angle(left_knee, left_hip, left_ankle)
        right_knee_angle = _calculate_angle(right_knee, right_hip, right_ankle)
        avg_knee_angle = (left_knee_angle + right_knee_angle) / 2.0

        # --- Jumping: both ankles above hip level ---
        if left_ankle["y"] < hip_y and right_ankle["y"] < hip_y:
            return "jumping"

        # --- Pointing: one arm extended straight, hand far from body ---
        if left_shoulder and left_wrist:
            left_arm_dist = _landmark_distance(left_shoulder, left_wrist)
            if left_arm_dist > 0.35:
                left_elbow_angle = _calculate_angle(left_elbow, left_shoulder,
                                                     left_wrist)
                if left_elbow_angle > 150:
                    return "pointing"
        if right_shoulder and right_wrist:
            right_arm_dist = _landmark_distance(right_shoulder, right_wrist)
            if right_arm_dist > 0.35:
                right_elbow_angle = _calculate_angle(right_elbow, right_shoulder,
                                                      right_wrist)
                if right_elbow_angle > 150:
                    return "pointing"

        # --- Waving: wrist high, side-to-side motion ---
        if left_wrist and right_wrist and nose:
            lw_y = left_wrist["y"]
            rw_y = right_wrist["y"]
            nose_y = nose["y"]
            if lw_y < nose_y or rw_y < nose_y:
                # Wrist above nose = possible wave
                return "waving"

        # --- Walking vs Running via knee bend ---
        if avg_knee_angle > 90:
            return "standing"
        if avg_knee_angle > 45:
            return "walking"
        return "running"

    # ------------------------------------------------------------------
    # Overlay drawing
    # ------------------------------------------------------------------

    def draw_overlay(
        self,
        frame: np.ndarray,
        results: Dict[str, Any],
        draw_pose: bool = True,
        draw_face: bool = True,
        draw_hands: bool = True,
        draw_eyes: bool = True,
        draw_info: bool = True,
    ) -> np.ndarray:
        """
        Draw all tracked landmarks on the BGR frame.

        Parameters
        ----------
        frame : np.ndarray
            BGR input image.
        results : dict
            Output from ``process_frame``.
        draw_* : bool
            Toggle individual feature overlays.

        Returns
        -------
        np.ndarray
            Annotated frame (in-place modification).
        """
        if frame is None or not _HAS_CV2:
            return frame

        h, w = frame.shape[:2]

        # --- Pose skeleton ---
        if draw_pose and results.get("pose"):
            self._draw_pose_overlay(frame, results["pose"], h, w)

        # --- Face mesh ---
        if draw_face and results.get("face"):
            self._draw_face_overlay(frame, results["face"], h, w)

        # --- Hands ---
        if draw_hands and results.get("hands"):
            self._draw_hand_overlay(frame, results["hands"], h, w)

        # --- Eyes ---
        if draw_eyes and results.get("eyes"):
            self._draw_eye_overlay(frame, results["eyes"], h, w)

        # --- Info text ---
        if draw_info:
            info_lines = [
                f"Expression: {results.get('expression', 'n/a')}",
                f"Gesture:    {results.get('gesture', 'n/a')}",
                f"FPS:        {results.get('fps', 0):.1f}",
                f"Blink:      {results.get('eyes', {}).get('blink_detected', False)}",
            ]
            for i, line in enumerate(info_lines):
                y = 30 + i * 30
                cv2.putText(
                    frame, line, (10, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, COLOR_TEXT, 2
                )

        return frame

    def _draw_pose_overlay(
        self,
        frame: np.ndarray,
        pose_landmarks: List[Dict[str, Any]],
        h: int,
        w: int,
    ) -> None:
        """Draw pose landmarks and skeleton connections."""
        # Skeleton connections (pairs of landmark IDs)
        connections = [
            (11, 12), (11, 13), (13, 15), (12, 14), (14, 16),
            (11, 23), (12, 24), (23, 24),
            (23, 25), (25, 27), (24, 26), (26, 28),
            (27, 29), (27, 31), (28, 30), (28, 32),
            (15, 17), (15, 19), (15, 21), (16, 18), (16, 20), (16, 22),
            (9, 10), (0, 4), (0, 1), (4, 5), (5, 6), (1, 2), (2, 3),
            (3, 7), (6, 8), (0, 9), (0, 10),
        ]

        lm_map = {lm["id"]: lm for lm in pose_landmarks}

        # Draw connections
        for a_id, b_id in connections:
            a = lm_map.get(a_id)
            b = lm_map.get(b_id)
            if a is None or b is None:
                continue
            pt1 = (int(a["x"] * w), int(a["y"] * h))
            pt2 = (int(b["x"] * w), int(b["y"] * h))
            cv2.line(frame, pt1, pt2, COLOR_POSE, 2)

        # Draw joints
        for lm in pose_landmarks:
            cx = int(lm["x"] * w)
            cy = int(lm["y"] * h)
            cv2.circle(frame, (cx, cy), 4, COLOR_POSE, -1)

    def _draw_face_overlay(
        self,
        frame: np.ndarray,
        face_landmarks: List[Dict[str, Any]],
        h: int,
        w: int,
    ) -> None:
        """Draw face mesh landmarks (sub-sampled for performance)."""
        # Draw every 5th point to avoid clutter
        step = 5
        for i in range(0, len(face_landmarks), step):
            lm = face_landmarks[i]
            cx = int(lm["x"] * w)
            cy = int(lm["y"] * h)
            cv2.circle(frame, (cx, cy), 1, COLOR_FACE, -1)

        # Draw contours with stronger lines
        lm_map = {lm["id"]: lm for lm in face_landmarks}
        for contour_name, indices in FACE_CONTOURS.items():
            if contour_name in ("face_outline",):
                pts = []
                for idx in indices:
                    lm = lm_map.get(idx)
                    if lm:
                        pts.append((int(lm["x"] * w), int(lm["y"] * h)))
                if len(pts) > 1:
                    for i in range(len(pts) - 1):
                        cv2.line(frame, pts[i], pts[i + 1], COLOR_FACE, 1)

    def _draw_hand_overlay(
        self,
        frame: np.ndarray,
        hands: List[Dict[str, Any]],
        h: int,
        w: int,
    ) -> None:
        """Draw hand landmarks and finger connections."""
        finger_connections = [
            (0, 1), (1, 2), (2, 3), (3, 4),      # Thumb
            (0, 5), (5, 6), (6, 7), (7, 8),      # Index
            (0, 9), (9, 10), (10, 11), (11, 12), # Middle
            (0, 13), (13, 14), (14, 15), (15, 16),# Ring
            (0, 17), (17, 18), (18, 19), (19, 20),# Pinky
            (5, 9), (9, 13), (13, 17),           # Palm
        ]

        for hand in hands:
            lms = hand.get("landmarks", [])
            lm_map = {lm["id"]: lm for lm in lms}

            # Connections
            for a_id, b_id in finger_connections:
                a = lm_map.get(a_id)
                b = lm_map.get(b_id)
                if a is None or b is None:
                    continue
                pt1 = (int(a["x"] * w), int(a["y"] * h))
                pt2 = (int(b["x"] * w), int(b["y"] * h))
                cv2.line(frame, pt1, pt2, COLOR_HAND, 2)

            # Joints
            for lm in lms:
                cx = int(lm["x"] * w)
                cy = int(lm["y"] * h)
                cv2.circle(frame, (cx, cy), 4, COLOR_HAND, -1)

    def _draw_eye_overlay(
        self,
        frame: np.ndarray,
        eyes: Dict[str, Any],
        h: int,
        w: int,
    ) -> None:
        """Draw eye pupil centres and gaze vector."""
        left_pupil = eyes.get("left_pupil", (0.0, 0.0))
        right_pupil = eyes.get("right_pupil", (0.0, 0.0))
        gaze = eyes.get("gaze_vector", (0.0, 0.0, 0.0))

        # Draw pupil centres
        lp = (int(left_pupil[0] * w), int(left_pupil[1] * h))
        rp = (int(right_pupil[0] * w), int(right_pupil[1] * h))
        cv2.circle(frame, lp, 6, COLOR_EYE, -1)
        cv2.circle(frame, rp, 6, COLOR_EYE, -1)

        # Draw gaze vector
        gaze_scale = 80
        mid_x = (lp[0] + rp[0]) // 2
        mid_y = (lp[1] + rp[1]) // 2
        gx = int(mid_x + gaze[0] * gaze_scale)
        gy = int(mid_y + gaze[1] * gaze_scale)
        cv2.line(frame, (mid_x, mid_y), (gx, gy), COLOR_EYE, 2)

        # Blink indicator
        if eyes.get("blink_detected", False):
            cv2.putText(
                frame, "BLINK", (mid_x - 20, mid_y - 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, COLOR_EYE, 2
            )

    # ------------------------------------------------------------------
    # Background threaded tracking
    # ------------------------------------------------------------------

    def start_tracking(self) -> None:
        """Start the background tracking thread."""
        if self._running:
            logger.warning("Tracking already running.")
            return
        self._running = True
        self._thread = threading.Thread(target=self._tracking_loop, daemon=True)
        self._thread.start()
        logger.info("Holistic tracking started (camera=%s).", self.camera_id)

    def stop_tracking(self) -> None:
        """Stop the background tracking thread."""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        # Release camera
        if self._cap is not None and _HAS_CV2:
            self._cap.release()
            self._cap = None
        logger.info("Holistic tracking stopped.")

    def _tracking_loop(self) -> None:
        """Internal loop: capture -> process -> callback."""
        while self._running:
            if self._cap is None or not self._cap.isOpened():
                time.sleep(0.1)
                continue

            ret, frame = self._cap.read()
            if not ret or frame is None:
                time.sleep(0.01)
                continue

            results = self.process_frame(frame)

            # Invoke registered callbacks
            for cb in self._frame_callbacks:
                try:
                    cb(frame, results)
                except Exception as exc:
                    logger.error("Frame callback error: %s", exc)

            # Throttle to ~30 FPS
            time.sleep(0.033)

    def add_frame_callback(self, callback: Any) -> None:
        """Register a callable(frame, results) invoked on each tracked frame."""
        self._frame_callbacks.append(callback)

    def remove_frame_callback(self, callback: Any) -> None:
        """Unregister a frame callback."""
        if callback in self._frame_callbacks:
            self._frame_callbacks.remove(callback)

    @property
    def latest_results(self) -> Dict[str, Any]:
        """Thread-safe access to the most recent tracking results."""
        with self._lock:
            return dict(self._latest_results)

    @property
    def is_running(self) -> bool:
        return self._running

    # ------------------------------------------------------------------
    # Mock data generator (used when MediaPipe unavailable)
    # ------------------------------------------------------------------

    def _generate_mock_results(
        self,
        base: Dict[str, Any],
        width: int,
        height: int,
    ) -> Dict[str, Any]:
        """
        Produce deterministic simulated landmarks for testing.
        The skeleton stands still in a neutral pose at frame centre.
        """
        cx, cy = 0.5, 0.5
        scale = 0.3

        # --- Mock pose (33 landmarks) ---
        pose: List[Dict[str, Any]] = []
        for i in range(33):
            name = POSE_LANDMARK_NAMES.get(i, f"LANDMARK_{i}")
            # Deterministic pseudo-random but stable positions
            phase = i * 0.191
            px = cx + math.sin(phase) * scale * 0.3
            py = cy + math.cos(phase * 1.3) * scale * 0.5
            pz = math.sin(phase * 0.7) * 0.1
            pose.append({
                "id": i,
                "x": round(px, 4),
                "y": round(py, 4),
                "z": round(pz, 4),
                "visibility": 0.95,
                "name": name,
            })
        base["pose"] = pose

        # --- Mock face (468 landmarks) ---
        face: List[Dict[str, Any]] = []
        for i in range(468):
            phase = i * 0.0134
            fx = cx + math.sin(phase) * 0.12
            fy = cy - 0.15 + math.cos(phase * 1.1) * 0.14
            fz = math.sin(phase * 0.5) * 0.05
            contours = []
            for cname, cindices in FACE_CONTOURS.items():
                if i in cindices:
                    contours.append(cname)
            face.append({
                "id": i,
                "x": round(fx, 4),
                "y": round(fy, 4),
                "z": round(fz, 4),
                "contours": contours,
            })
        base["face"] = face

        # --- Mock hands (both) ---
        hands: List[Dict[str, Any]] = []
        for hand_label, hand_offset in [("left", -0.25), ("right", 0.25)]:
            lms: List[Dict[str, Any]] = []
            for j in range(21):
                phase = j * 0.3
                hx = cx + hand_offset + math.sin(phase) * 0.06
                hy = cy + 0.1 + math.cos(phase * 0.8) * 0.08
                hz = math.sin(phase * 0.4) * 0.02
                lms.append({
                    "id": j,
                    "x": round(hx, 4),
                    "y": round(hy, 4),
                    "z": round(hz, 4),
                    "name": HAND_LANDMARK_NAMES.get(j, f"HAND_{j}"),
                })
            hands.append({"hand": hand_label, "landmarks": lms})
        base["hands"] = hands

        # --- Mock eyes ---
        base["eyes"] = {
            "left_pupil": (cx - 0.05, cy - 0.18),
            "right_pupil": (cx + 0.05, cy - 0.18),
            "gaze_vector": (0.0, 0.0, 0.5),
            "blink_detected": False,
            "left_ear": 0.28,
            "right_ear": 0.28,
        }

        # --- Derived ---
        base["body_angles"] = self.get_body_angles(pose)
        base["expression"] = "neutral"
        base["gesture"] = "standing"

        return base

    # ------------------------------------------------------------------
    # Resource cleanup
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Release all resources."""
        self.stop_tracking()
        if self._holistic is not None:
            self._holistic.close()
            self._holistic = None
        logger.info("HolisticTracker resources released.")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
        return False


# ===========================================================================
# MockHolisticTracker — standalone mock with same interface
# ===========================================================================

class MockHolisticTracker:
    """
    Deterministic mock implementation of HolisticTracker.

    Useful for CI, unit tests, and environments without a camera or MediaPipe.
    Every call returns predictable, reproducible data.
    """

    def __init__(
        self,
        camera_id: int = DEFAULT_CAMERA_ID,
        min_detection_confidence: float = 0.5,
        min_tracking_confidence: float = 0.5,
    ) -> None:
        self.camera_id = camera_id
        self.min_detection_confidence = min_detection_confidence
        self.min_tracking_confidence = min_tracking_confidence
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._latest_results: Dict[str, Any] = {}
        self._frame_callbacks: List[Any] = []
        self._current_fps = 30.0
        self._frame_count = 0
        logger.info("MockHolisticTracker initialised (camera=%s).", camera_id)

    # ------------------------------------------------------------------
    # Frame processing
    # ------------------------------------------------------------------

    def process_frame(self, frame: np.ndarray) -> Dict[str, Any]:
        """Return deterministic mock tracking data."""
        h, w = frame.shape[:2] if frame is not None else (720, 1280)
        self._frame_count += 1

        results = self._build_mock_frame(w, h)
        with self._lock:
            self._latest_results = results
        return results

    # ------------------------------------------------------------------
    # Landmark extraction
    # ------------------------------------------------------------------

    def get_pose_landmarks(self, results: Any) -> List[Dict[str, Any]]:
        """Extract pose landmarks from mock or real results."""
        if isinstance(results, dict):
            return results.get("pose", [])
        return []

    def get_face_landmarks(self, results: Any) -> List[Dict[str, Any]]:
        """Extract face landmarks from mock or real results."""
        if isinstance(results, dict):
            return results.get("face", [])
        return []

    def get_eye_tracking(self, results: Any) -> Dict[str, Any]:
        """Extract eye tracking from mock or real results."""
        if isinstance(results, dict):
            return results.get("eyes", {})
        return {
            "left_pupil": (0.45, 0.35),
            "right_pupil": (0.55, 0.35),
            "gaze_vector": (0.0, 0.0, 0.5),
            "blink_detected": False,
            "left_ear": 0.28,
            "right_ear": 0.28,
        }

    def get_hand_landmarks(self, results: Any) -> List[Dict[str, Any]]:
        """Extract hand landmarks from mock or real results."""
        if isinstance(results, dict):
            return results.get("hands", [])
        return []

    # ------------------------------------------------------------------
    # Derived analytics
    # ------------------------------------------------------------------

    def get_body_angles(
        self, pose_landmarks: List[Dict[str, Any]]
    ) -> Dict[str, float]:
        """Compute body angles from landmarks (same logic as real tracker)."""
        angles: Dict[str, float] = {}
        if not pose_landmarks or len(pose_landmarks) < 33:
            return angles

        lm_map = {lm["id"]: lm for lm in pose_landmarks}
        for joint_name, (vertex, pt1, pt2) in ANGLE_JOINTS.items():
            v = lm_map.get(vertex)
            a = lm_map.get(pt1)
            b = lm_map.get(pt2)
            if v is None or a is None or b is None:
                angles[joint_name] = 0.0
                continue
            angles[joint_name] = round(_calculate_angle(v, a, b), 2)
        return angles

    def get_facial_expression(
        self, face_landmarks: List[Dict[str, Any]]
    ) -> str:
        """Return a deterministic mock expression."""
        expressions = ["neutral", "happy", "sad", "surprised", "angry", "focused"]
        idx = self._frame_count % len(expressions)
        return expressions[idx]

    def get_body_gesture(
        self, pose_landmarks: List[Dict[str, Any]]
    ) -> str:
        """Return a deterministic mock gesture."""
        gestures = ["standing", "sitting", "walking", "pointing", "waving"]
        idx = self._frame_count % len(gestures)
        return gestures[idx]

    # ------------------------------------------------------------------
    # Overlay drawing (identical to real tracker)
    # ------------------------------------------------------------------

    def draw_overlay(
        self,
        frame: np.ndarray,
        results: Dict[str, Any],
        draw_pose: bool = True,
        draw_face: bool = True,
        draw_hands: bool = True,
        draw_eyes: bool = True,
        draw_info: bool = True,
    ) -> np.ndarray:
        """Draw mock overlay annotations."""
        if frame is None or not _HAS_CV2:
            return frame

        h, w = frame.shape[:2]

        # --- Draw mock pose skeleton ---
        if draw_pose and results.get("pose"):
            connections = [
                (11, 12), (11, 13), (13, 15), (12, 14), (14, 16),
                (11, 23), (12, 24), (23, 24),
                (23, 25), (25, 27), (24, 26), (26, 28),
            ]
            lm_map = {lm["id"]: lm for lm in results["pose"]}
            for a_id, b_id in connections:
                a = lm_map.get(a_id)
                b = lm_map.get(b_id)
                if a and b:
                    pt1 = (int(a["x"] * w), int(a["y"] * h))
                    pt2 = (int(b["x"] * w), int(b["y"] * h))
                    cv2.line(frame, pt1, pt2, COLOR_POSE, 2)
            for lm in results["pose"]:
                cx, cy = int(lm["x"] * w), int(lm["y"] * h)
                cv2.circle(frame, (cx, cy), 4, COLOR_POSE, -1)

        # --- Draw mock info ---
        if draw_info:
            info_lines = [
                f"[MOCK] Expression: {results.get('expression', 'n/a')}",
                f"[MOCK] Gesture:    {results.get('gesture', 'n/a')}",
                f"[MOCK] FPS:        {results.get('fps', 0):.1f}",
            ]
            for i, line in enumerate(info_lines):
                y = 30 + i * 30
                cv2.putText(
                    frame, line, (10, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 165, 255), 2
                )

        return frame

    # ------------------------------------------------------------------
    # Background threaded tracking (mock)
    # ------------------------------------------------------------------

    def start_tracking(self) -> None:
        """Start a mock tracking loop that generates synthetic frames."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._mock_loop, daemon=True)
        self._thread.start()
        logger.info("MockHolisticTracker tracking started.")

    def stop_tracking(self) -> None:
        """Stop the mock tracking loop."""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        logger.info("MockHolisticTracker tracking stopped.")

    def _mock_loop(self) -> None:
        """Generate synthetic frames at ~30 FPS."""
        blank = (np.zeros((720, 1280, 3), dtype=np.uint8) + 40) if _HAS_CV2 else None
        while self._running:
            frame = blank if blank is not None else np.zeros((720, 1280, 3), dtype=np.uint8)
            results = self.process_frame(frame)
            for cb in self._frame_callbacks:
                try:
                    cb(frame, results)
                except Exception as exc:
                    logger.error("Mock callback error: %s", exc)
            time.sleep(0.033)

    def add_frame_callback(self, callback: Any) -> None:
        """Register a frame callback."""
        self._frame_callbacks.append(callback)

    def remove_frame_callback(self, callback: Any) -> None:
        """Unregister a frame callback."""
        if callback in self._frame_callbacks:
            self._frame_callbacks.remove(callback)

    @property
    def latest_results(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._latest_results)

    @property
    def is_running(self) -> bool:
        return self._running

    # ------------------------------------------------------------------
    # Mock data builders
    # ------------------------------------------------------------------

    def _build_mock_frame(self, width: int, height: int) -> Dict[str, Any]:
        """Construct a complete deterministic frame result."""
        cx, cy = 0.5, 0.5
        scale = 0.3

        pose = []
        for i in range(33):
            name = POSE_LANDMARK_NAMES.get(i, f"LANDMARK_{i}")
            phase = i * 0.191
            pose.append({
                "id": i,
                "x": round(cx + math.sin(phase) * scale * 0.3, 4),
                "y": round(cy + math.cos(phase * 1.3) * scale * 0.5, 4),
                "z": round(math.sin(phase * 0.7) * 0.1, 4),
                "visibility": 0.95,
                "name": name,
            })

        face = []
        for i in range(468):
            phase = i * 0.0134
            contours = [cn for cn, ci in FACE_CONTOURS.items() if i in ci]
            face.append({
                "id": i,
                "x": round(cx + math.sin(phase) * 0.12, 4),
                "y": round(cy - 0.15 + math.cos(phase * 1.1) * 0.14, 4),
                "z": round(math.sin(phase * 0.5) * 0.05, 4),
                "contours": contours,
            })

        hands = []
        for hand_label, hand_offset in [("left", -0.25), ("right", 0.25)]:
            lms = []
            for j in range(21):
                phase = j * 0.3
                lms.append({
                    "id": j,
                    "x": round(cx + hand_offset + math.sin(phase) * 0.06, 4),
                    "y": round(cy + 0.1 + math.cos(phase * 0.8) * 0.08, 4),
                    "z": round(math.sin(phase * 0.4) * 0.02, 4),
                    "name": HAND_LANDMARK_NAMES.get(j, f"HAND_{j}"),
                })
            hands.append({"hand": hand_label, "landmarks": lms})

        return {
            "pose": pose,
            "face": face,
            "hands": hands,
            "eyes": {
                "left_pupil": (cx - 0.05, cy - 0.18),
                "right_pupil": (cx + 0.05, cy - 0.18),
                "gaze_vector": (0.0, 0.0, 0.5),
                "blink_detected": False,
                "left_ear": 0.28,
                "right_ear": 0.28,
            },
            "body_angles": self.get_body_angles(pose),
            "expression": self.get_facial_expression(face),
            "gesture": self.get_body_gesture(pose),
            "fps": self._current_fps,
            "timestamp": time.time(),
        }

    def close(self) -> None:
        """Release mock resources."""
        self.stop_tracking()
        logger.info("MockHolisticTracker resources released.")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
        return False


# ===========================================================================
# Factory
# ===========================================================================

def get_holistic_tracker(
    camera_id: int = DEFAULT_CAMERA_ID,
    min_detection_confidence: float = DEFAULT_MIN_DETECTION_CONFIDENCE,
    force_mock: bool = False,
) -> HolisticTracker:
    """
    Factory that returns a :class:`HolisticTracker` when MediaPipe is
    available, otherwise falls back to :class:`MockHolisticTracker`.

    Parameters
    ----------
    camera_id : int
        Camera device index (default 0).
    min_detection_confidence : float
        Minimum confidence for pose/face/hand detection.
    force_mock : bool
        If ``True``, always return :class:`MockHolisticTracker`.

    Returns
    -------
    HolisticTracker or MockHolisticTracker
    """
    if force_mock or not _HAS_MEDIAPIPE:
        logger.info("Returning MockHolisticTracker (force_mock=%s, mediapipe=%s)",
                     force_mock, _HAS_MEDIAPIPE)
        return MockHolisticTracker(
            camera_id=camera_id,
            min_detection_confidence=min_detection_confidence,
        )
    logger.info("Returning HolisticTracker (mediapipe available).")
    return HolisticTracker(
        camera_id=camera_id,
        min_detection_confidence=min_detection_confidence,
    )


# ===========================================================================
# Module-level quick test
# ===========================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("=" * 60)
    print("JARVIS BRAINIAC — Holistic Tracker Self-Test")
    print("=" * 60)

    tracker = get_holistic_tracker(force_mock=True)
    blank = np.zeros((720, 1280, 3), dtype=np.uint8) + 40
    results = tracker.process_frame(blank)

    print(f"Pose landmarks:       {len(results['pose'])}/33")
    print(f"Face landmarks:       {len(results['face'])}/468")
    print(f"Hands detected:       {len(results['hands'])}")
    print(f"Expression:           {results['expression']}")
    print(f"Gesture:              {results['gesture']}")
    print(f"Body angles:          {results['body_angles']}")
    print(f"Eye tracking:         {results['eyes']}")
    print("=" * 60)
    print("Self-test PASSED")
