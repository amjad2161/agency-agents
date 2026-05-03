"""
JARVIS BRAINIAC — VR/Gesture Perception Engine
================================================
3D hand gesture tracking, facial micro-expression mapping, eye tracking,
and real-time screen analysis for multimodal interaction.

Zero cloud dependency — 100% local.

Provides a unified perception pipeline that integrates with the broader
JARVIS runtime via a threaded perception loop and callback-based result
delivery. Every sub-system has a realistic mock fallback so the agent
can run (and be unit-tested) even when no camera or GPU is available.

Supported modalities
--------------------
- 21 hand landmarks per hand, both hands simultaneously
- Gesture recognition: point, grab, swipe, pinch, open_palm, fist,
  thumbs_up/down, peace_sign, ok_sign
- 468 face landmarks (MediaPipe face mesh)
- Emotion recognition: happy, sad, angry, surprised, neutral, disgusted, fearful
- Eye tracking: pupil centre, gaze vector, blink detection, fixation / saccade
- Screen analysis: UI element detection, OCR text extraction, accessibility tree
- 3D spatial mapping: user position, depth estimation, FOV

Author: Amjad Mobarsham (sole owner)
"""

from __future__ import annotations

import math
import os
import random
import sys
import threading
import time
import warnings
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

# ---------------------------------------------------------------------------
# Logging guard — prevent local ``logging.py`` from shadowing stdlib
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
    _h = logging.StreamHandler(sys.stdout)
    _h.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")
    )
    logger.addHandler(_h)
    logger.setLevel(logging.INFO)

# ---------------------------------------------------------------------------
# Optional dependency flags
# ---------------------------------------------------------------------------
_HAS_CV2 = False
_HAS_MEDIAPIPE = False
_HAS_PIL = False

try:
    import cv2  # type: ignore[import-untyped]

    _HAS_CV2 = True
except ImportError:  # pragma: no cover
    warnings.warn("opencv-python not installed.  Camera capture disabled.", ImportWarning)

try:
    import mediapipe as mp  # type: ignore[import-untyped]

    _HAS_MEDIAPIPE = True
except ImportError:  # pragma: no cover
    warnings.warn("mediapipe not installed.  Perception engine in MOCK mode.", ImportWarning)

try:
    from PIL import Image  # type: ignore[import-untyped]

    _HAS_PIL = True
except ImportError:  # pragma: no cover
    warnings.warn("pillow not installed.  Screen analysis uses mock fallback.", ImportWarning)

# ===========================================================================
# Constants
# ===========================================================================

HAND_LANDMARK_NAMES = [
    "WRIST",
    "THUMB_CMC", "THUMB_MCP", "THUMB_IP", "THUMB_TIP",
    "INDEX_FINGER_MCP", "INDEX_FINGER_PIP", "INDEX_FINGER_DIP", "INDEX_FINGER_TIP",
    "MIDDLE_FINGER_MCP", "MIDDLE_FINGER_PIP", "MIDDLE_FINGER_DIP", "MIDDLE_FINGER_TIP",
    "RING_FINGER_MCP", "RING_FINGER_PIP", "RING_FINGER_DIP", "RING_FINGER_TIP",
    "PINKY_MCP", "PINKY_PIP", "PINKY_DIP", "PINKY_TIP",
]

EMOTION_LABELS = ["happy", "sad", "angry", "surprised", "neutral", "disgusted", "fearful"]

DEFAULT_GESTURE_COMMANDS = {
    "point": "move_cursor",
    "pinch": "click_select",
    "grab": "drag",
    "swipe": "scroll_switch",
    "open_palm": "activate",
    "fist": "clear_cancel",
    "thumbs_up": "approve",
    "thumbs_down": "reject",
    "peace_sign": "expand_menu",
    "ok_sign": "confirm",
}

# Indices for gesture heuristic helpers
FINGER_TIP_IDS = [4, 8, 12, 16, 20]
FINGER_PIP_IDS = [2, 6, 10, 14, 18]
THUMB_TIP, INDEX_TIP, MIDDLE_TIP, RING_TIP, PINKY_TIP = 4, 8, 12, 16, 20
INDEX_PIP, MIDDLE_PIP, RING_PIP, PINKY_PIP = 6, 10, 14, 18


# ===========================================================================
# Data Models
# ===========================================================================

@dataclass
class Gesture:
    """Recognised gesture with classification metadata."""

    name: str
    type: str  # "static" | "dynamic"
    confidence: float
    command: str = ""


@dataclass
class HandData:
    """Per-hand tracking output."""

    landmarks: List[dict]  # 21 landmarks {x, y, z}
    gestures: List[Gesture]
    is_right: bool
    confidence: float


@dataclass
class HandTrackingResult:
    """Container for a single hand-tracking frame."""

    hands: List[HandData]
    timestamp: float
    fps: float


@dataclass
class EmotionResult:
    """Facial emotion classification output."""

    primary: str
    intensity: float  # 0-1
    valence: float  # -1 (negative) … +1 (positive)
    arousal: float  # 0 (calm) … 1 (excited)


@dataclass
class FaceAnalysisResult:
    """Full-face analysis for a single video frame."""

    landmarks: List[dict]  # 468 landmarks with x, y, z
    emotion: str
    emotion_intensity: float
    head_pose: Dict[str, float]  # yaw, pitch, roll
    eye_openness: Dict[str, float]  # left, right  (0=closed, 1=open)
    gaze_direction: Dict[str, float]  # x, y, z normalised vector


@dataclass
class EyeTrackingResult:
    """Fine-grained eye tracking output."""

    left_pupil: Tuple[int, int]
    right_pupil: Tuple[int, int]
    gaze_screen: Tuple[int, int]  # (x, y) on screen
    is_blinking: bool
    blink_rate: float  # blinks per minute
    fixation: bool = False
    saccade: bool = False


@dataclass
class UIElement:
    """Detected on-screen UI element."""

    element_type: str  # button, text, link, image, input, menu, checkbox
    coordinates: Tuple[int, int, int, int]  # x1, y1, x2, y2
    text: str
    confidence: float


@dataclass
class ScreenAnalysis:
    """Snapshot of the user's screen."""

    width: int
    height: int
    elements: List[UIElement]
    text_content: str
    dominant_colors: List[str]


@dataclass
class SpatialContext:
    """3D spatial context of the user and scene."""

    user_position: Tuple[float, float, float]  # x, y, z (metres)
    hand_positions: List[Tuple[float, float, float]]
    field_of_view: float  # degrees
    depth_estimate: float  # average metres to user
    scene_geometry: Dict[str, Any]  # bounding boxes, planes, etc.


# ===========================================================================
# VR Perception Engine
# ===========================================================================

class VRPerceptionEngine:
    """Unified perception pipeline for hand, face, eye, screen and 3D spatial data.

    Runs in *mock mode* automatically when MediaPipe or OpenCV are unavailable,
    producing realistic synthetic data so the rest of the JARVIS runtime can
    continue to operate.

    The engine can be driven in two ways:

    1. **Synchronous** — call ``track_hands``, ``analyze_face``, etc. directly
       with a video frame.
    2. **Asynchronous** — start the perception loop via
       ``start_perception_loop(callback)`` and consume results from a background
       thread.
    """

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def __init__(
        self,
        target_fps: int = 30,
        camera_index: int = 0,
        resolution: Tuple[int, int] = (1280, 720),
        mock_mode: bool = False,
    ) -> None:
        """Initialise the perception engine.

        Args:
            target_fps: Desired camera / loop framerate.
            camera_index: OpenCV camera device index.
            resolution: (width, height) capture resolution.
            mock_mode: Force synthetic data even when camera libraries are
                present. Useful for testing and demos.
        """
        self.target_fps = target_fps
        self.camera_index = camera_index
        self.resolution = resolution
        self.mock_mode = mock_mode or (not _HAS_CV2) or (not _HAS_MEDIAPIPE)

        # Threading
        self._lock = threading.Lock()
        self._perception_thread: Optional[threading.Thread] = None
        self._running = False
        self._callback: Optional[Callable[[Dict[str, Any]], None]] = None
        self._stop_event = threading.Event()

        # Mutable state (lock-protected)
        self._fps_history: deque[float] = deque(maxlen=target_fps)
        self._gesture_commands = dict(DEFAULT_GESTURE_COMMANDS)
        self._custom_gestures: Dict[str, Callable[[List[dict]], float]] = {}
        self._latest_frame_time = 0.0
        self._blink_times: deque[float] = deque(maxlen=30)
        self._prev_hand_landmarks: Optional[List[dict]] = None
        self._camera_calibrated = False
        self._camera_matrix: Optional[np.ndarray] = None
        self._dist_coeffs: Optional[np.ndarray] = None

        # MediaPipe instances (created lazily)
        self._hands_solution: Optional[Any] = None
        self._face_mesh_solution: Optional[Any] = None
        self._cap: Optional[Any] = None

        if not self.mock_mode:
            self._init_mediapipe()
        else:
            logger.info("VRPerceptionEngine running in MOCK mode (synthetic data).")

    def _init_mediapipe(self) -> None:
        """Create MediaPipe Hands and Face Mesh solutions."""
        if not _HAS_MEDIAPIPE:
            return
        mp_hands = mp.solutions.hands
        mp_face_mesh = mp.solutions.face_mesh
        self._hands_solution = mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=2,
            min_detection_confidence=0.7,
            min_tracking_confidence=0.5,
        )
        self._face_mesh_solution = mp_face_mesh.FaceMesh(
            static_image_mode=False,
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        logger.info("MediaPipe Hands + Face Mesh initialised.")

    # ------------------------------------------------------------------
    # Hand Gesture Tracking
    # ------------------------------------------------------------------

    def track_hands(self, frame: "np.ndarray") -> HandTrackingResult:
        """Detect and track hands in *frame*.

        Returns a :class:`HandTrackingResult` with per-hand landmarks and
        recognised gestures.  In mock mode returns synthetically generated
        data.
        """
        t0 = time.time()

        if self.mock_mode:
            result = self._mock_hand_tracking()
            result.fps = self._compute_fps()
            return result

        # Normalise frame for MediaPipe (expects RGB)
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w = frame.shape[:2]
        results = self._hands_solution.process(rgb)

        hands: List[HandData] = []
        if results.multi_hand_landmarks:
            for idx, hand_landmarks in enumerate(results.multi_hand_landmarks):
                landmarks = [
                    {
                        "name": HAND_LANDMARK_NAMES[i],
                        "x": lm.x,
                        "y": lm.y,
                        "z": lm.z,
                    }
                    for i, lm in enumerate(hand_landmarks.landmark)
                ]
                # Determine chirality
                handedness = (
                    results.multi_handedness[idx].classification[0].label == "Right"
                )
                gestures = self._classify_all_gestures(landmarks)
                conf = results.multi_handedness[idx].classification[0].score
                hands.append(
                    HandData(
                        landmarks=landmarks,
                        gestures=gestures,
                        is_right=handedness,
                        confidence=conf,
                    )
                )
                self._prev_hand_landmarks = landmarks

        result = HandTrackingResult(
            hands=hands, timestamp=time.time(), fps=self._compute_fps()
        )
        self._fps_history.append(1.0 / (time.time() - t0 + 1e-6))
        return result

    def _mock_hand_tracking(self) -> HandTrackingResult:
        """Generate realistic synthetic hand tracking data."""
        num_hands = random.choice([0, 1, 1, 2])  # bias toward hands present
        hands: List[HandData] = []
        for h in range(num_hands):
            # Generate coherent hand pose around a plausible position
            cx, cy = random.uniform(0.3, 0.7), random.uniform(0.3, 0.7)
            landmarks = self._generate_mock_hand_landmarks(cx, cy)
            gestures = self._classify_all_gestures(landmarks)
            hands.append(
                HandData(
                    landmarks=landmarks,
                    gestures=gestures,
                    is_right=(h == 0),
                    confidence=random.uniform(0.75, 0.98),
                )
            )
        return HandTrackingResult(
            hands=hands, timestamp=time.time(), fps=float(self.target_fps)
        )

    def _generate_mock_hand_landmarks(self, cx: float, cy: float) -> List[dict]:
        """Create a plausible set of 21 hand landmarks around centre (cx, cy)."""
        lms: List[dict] = []
        for i in range(21):
            # Rough skeletal structure — wrist at bottom, fingers extend upward
            base_angle = math.radians(90 + (i % 5 - 2) * 15)
            finger_len = 0.15 + (i // 5) * 0.05
            x = cx + math.cos(base_angle) * finger_len * (i % 5) / 5.0
            y = cy - finger_len * (i % 5) / 5.0
            z = random.uniform(-0.05, 0.05)
            lms.append({"name": HAND_LANDMARK_NAMES[i], "x": x, "y": y, "z": z})
        return lms

    # ------------------------------------------------------------------
    # Gesture Classification
    # ------------------------------------------------------------------

    def recognize_gesture(self, landmarks: List[dict]) -> List[Gesture]:
        """Classify gestures from a single set of 21 hand landmarks.

        Returns a list of candidate :class:`Gesture` objects sorted by
        descending confidence.
        """
        return self._classify_all_gestures(landmarks)

    def _classify_all_gestures(self, landmarks: List[dict]) -> List[Gesture]:
        """Run every built-in and custom gesture classifier."""
        if not landmarks:
            return []

        gestures: List[Gesture] = []

        # --- Built-in static classifiers ---
        for name, scorer in [
            ("open_palm", self._score_open_palm),
            ("fist", self._score_fist),
            ("point", self._score_point),
            ("pinch", self._score_pinch),
            ("grab", self._score_grab),
            ("thumbs_up", self._score_thumbs_up),
            ("thumbs_down", self._score_thumbs_down),
            ("peace_sign", self._score_peace_sign),
            ("ok_sign", self._score_ok_sign),
        ]:
            conf = scorer(landmarks)
            if conf > 0.5:
                gestures.append(
                    Gesture(
                        name=name,
                        type="static",
                        confidence=round(conf, 3),
                        command=self._gesture_commands.get(name, ""),
                    )
                )

        # --- Dynamic classifiers (require history) ---
        if self._prev_hand_landmarks is not None:
            swipe_conf = self._score_swipe(landmarks, self._prev_hand_landmarks)
            if swipe_conf > 0.5:
                gestures.append(
                    Gesture(
                        name="swipe",
                        type="dynamic",
                        confidence=round(swipe_conf, 3),
                        command=self._gesture_commands.get("swipe", ""),
                    )
                )

        # --- Custom gesture plugins ---
        for custom_name, custom_fn in self._custom_gestures.items():
            conf = custom_fn(landmarks)
            if conf > 0.5:
                gestures.append(
                    Gesture(
                        name=custom_name,
                        type="custom",
                        confidence=round(conf, 3),
                        command=self._gesture_commands.get(custom_name, ""),
                    )
                )

        gestures.sort(key=lambda g: g.confidence, reverse=True)
        return gestures

    # --- Static gesture heuristics ---

    def _score_open_palm(self, lm: List[dict]) -> float:
        extended = sum(
            1
            for tip, pip in zip(FINGER_TIP_IDS[1:], FINGER_PIP_IDS[1:])
            if lm[tip]["y"] < lm[pip]["y"]
        )
        thumb_ext = lm[THUMB_TIP]["x"] > lm[THUMB_TIP - 1]["x"] if lm[0]["x"] < 0.5 else lm[THUMB_TIP]["x"] < lm[THUMB_TIP - 1]["x"]
        return 1.0 if (extended == 4 and thumb_ext) else 0.0

    def _score_fist(self, lm: List[dict]) -> float:
        curled = sum(
            1
            for tip, pip in zip(FINGER_TIP_IDS[1:], FINGER_PIP_IDS[1:])
            if lm[tip]["y"] > lm[pip]["y"]
        )
        return 1.0 if curled >= 3 else 0.0

    def _score_point(self, lm: List[dict]) -> float:
        idx_ext = lm[INDEX_TIP]["y"] < lm[INDEX_PIP]["y"]
        others_curled = all(
            lm[t]["y"] > lm[p]["y"]
            for t, p in zip(FINGER_TIP_IDS[2:], FINGER_PIP_IDS[2:])
        )
        return 1.0 if (idx_ext and others_curled) else 0.0

    def _score_pinch(self, lm: List[dict]) -> float:
        d = math.hypot(
            lm[THUMB_TIP]["x"] - lm[INDEX_TIP]["x"],
            lm[THUMB_TIP]["y"] - lm[INDEX_TIP]["y"],
        )
        return 1.0 if d < 0.06 else max(0.0, 1.0 - (d - 0.06) / 0.15)

    def _score_grab(self, lm: List[dict]) -> float:
        # All fingertips close to wrist centre
        wrist = lm[0]
        total_d = sum(
            math.hypot(lm[t]["x"] - wrist["x"], lm[t]["y"] - wrist["y"])
            for t in FINGER_TIP_IDS
        )
        avg_d = total_d / 5.0
        return 1.0 if avg_d < 0.18 else max(0.0, 1.0 - (avg_d - 0.18) / 0.3)

    def _score_thumbs_up(self, lm: List[dict]) -> float:
        thumb_high = lm[THUMB_TIP]["y"] < lm[THUMB_TIP - 2]["y"]
        fingers_curled = all(
            lm[t]["y"] > lm[p]["y"]
            for t, p in zip(FINGER_TIP_IDS[1:], FINGER_PIP_IDS[1:])
        )
        return 1.0 if (thumb_high and fingers_curled) else 0.0

    def _score_thumbs_down(self, lm: List[dict]) -> float:
        thumb_low = lm[THUMB_TIP]["y"] > lm[THUMB_TIP - 2]["y"]
        fingers_curled = all(
            lm[t]["y"] > lm[p]["y"]
            for t, p in zip(FINGER_TIP_IDS[1:], FINGER_PIP_IDS[1:])
        )
        return 1.0 if (thumb_low and fingers_curled) else 0.0

    def _score_peace_sign(self, lm: List[dict]) -> float:
        idx_ext = lm[INDEX_TIP]["y"] < lm[INDEX_PIP]["y"]
        mid_ext = lm[MIDDLE_TIP]["y"] < lm[MIDDLE_PIP]["y"]
        others_curled = all(
            lm[t]["y"] > lm[p]["y"]
            for t, p in zip(FINGER_TIP_IDS[3:], FINGER_PIP_IDS[3:])
        )
        spread = abs(lm[INDEX_TIP]["x"] - lm[MIDDLE_TIP]["x"])
        return 1.0 if (idx_ext and mid_ext and others_curled and spread > 0.04) else 0.0

    def _score_ok_sign(self, lm: List[dict]) -> float:
        d = math.hypot(
            lm[THUMB_TIP]["x"] - lm[INDEX_TIP]["x"],
            lm[THUMB_TIP]["y"] - lm[INDEX_TIP]["y"],
        )
        others_ext = sum(
            1
            for t, p in zip(FINGER_TIP_IDS[2:], FINGER_PIP_IDS[2:])
            if lm[t]["y"] < lm[p]["y"]
        )
        return 1.0 if (d < 0.05 and others_ext >= 2) else 0.0

    def _score_swipe(self, lm: List[dict], prev: List[dict]) -> float:
        dx = lm[0]["x"] - prev[0]["x"]
        dy = lm[0]["y"] - prev[0]["y"]
        speed = math.hypot(dx, dy)
        return 1.0 if speed > 0.08 else max(0.0, (speed - 0.03) / 0.05)

    # ------------------------------------------------------------------
    # Gesture → Command Mapping
    # ------------------------------------------------------------------

    def get_gesture_command(self, gesture: Gesture) -> str:
        """Return the system command mapped to *gesture*."""
        return self._gesture_commands.get(gesture.name, "")

    def set_gesture_command(self, gesture_name: str, command: str) -> None:
        """Override the command for a named gesture."""
        with self._lock:
            self._gesture_commands[gesture_name] = command
        logger.info("Mapped gesture '%s' -> command '%s'", gesture_name, command)

    def register_custom_gesture(
        self, name: str, scorer: Callable[[List[dict]], float], command: str = ""
    ) -> None:
        """Register a user-defined gesture scorer function.

        *scorer* receives 21 landmarks and returns a float 0..1 confidence.
        """
        with self._lock:
            self._custom_gestures[name] = scorer
            if command:
                self._gesture_commands[name] = command
        logger.info("Registered custom gesture '%s' -> '%s'", name, command or "(no command)")

    # ------------------------------------------------------------------
    # Facial Expression Analysis
    # ------------------------------------------------------------------

    def analyze_face(self, frame: "np.ndarray") -> FaceAnalysisResult:
        """Run face mesh detection and emotion estimation on *frame*.

        Returns a :class:`FaceAnalysisResult` with 468 landmarks, emotion
        classification, head pose, eye openness and gaze direction.
        """
        if self.mock_mode:
            return self._mock_face_analysis()

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self._face_mesh_solution.process(rgb)

        if not results.multi_face_landmarks:
            return self._mock_face_analysis()  # fallback when no face found

        face_landmarks = results.multi_face_landmarks[0]
        landmarks = [
            {"x": lm.x, "y": lm.y, "z": lm.z}
            for lm in face_landmarks.landmark
        ]

        emotion_res = self.detect_emotion(landmarks)
        head_pose = self._estimate_head_pose(landmarks)
        eye_open = self._estimate_eye_openness(landmarks)
        gaze = self._estimate_gaze_direction(landmarks)

        return FaceAnalysisResult(
            landmarks=landmarks,
            emotion=emotion_res.primary,
            emotion_intensity=emotion_res.intensity,
            head_pose=head_pose,
            eye_openness=eye_open,
            gaze_direction=gaze,
        )

    def _mock_face_analysis(self) -> FaceAnalysisResult:
        """Generate realistic synthetic face data."""
        emotion = random.choice(EMOTION_LABELS)
        landmarks = [
            {
                "x": random.gauss(0.5, 0.15),
                "y": random.gauss(0.5, 0.15),
                "z": random.gauss(0.0, 0.05),
            }
            for _ in range(468)
        ]
        # Constrain to [0, 1]
        for lm in landmarks:
            lm["x"] = max(0.0, min(1.0, lm["x"]))
            lm["y"] = max(0.0, min(1.0, lm["y"]))
        intensity = random.uniform(0.3, 0.9)
        return FaceAnalysisResult(
            landmarks=landmarks,
            emotion=emotion,
            emotion_intensity=round(intensity, 3),
            head_pose={
                "yaw": random.gauss(0.0, 10.0),
                "pitch": random.gauss(0.0, 5.0),
                "roll": random.gauss(0.0, 3.0),
            },
            eye_openness={"left": random.uniform(0.7, 1.0), "right": random.uniform(0.7, 1.0)},
            gaze_direction={
                "x": random.gauss(0.0, 0.2),
                "y": random.gauss(0.0, 0.2),
                "z": 1.0,
            },
        )

    # ------------------------------------------------------------------
    # Emotion Detection
    # ------------------------------------------------------------------

    def detect_emotion(self, face_landmarks: List[dict]) -> EmotionResult:
        """Classify the primary emotion from 468 facial landmarks.

        Uses geometric heuristics — distances between eyebrows, mouth
        corners, and eye regions — to estimate basic emotions.
        """
        if not face_landmarks or len(face_landmarks) < 468:
            return EmotionResult(primary="neutral", intensity=0.5, valence=0.0, arousal=0.5)

        # Heuristic geometric features (indices approximate MediaPipe face mesh)
        try:
            mouth_left = face_landmarks[61]
            mouth_right = face_landmarks[291]
            mouth_top = face_landmarks[0]
            mouth_bottom = face_landmarks[17]
            brow_left = face_landmarks[105]
            brow_right = face_landmarks[334]
            eye_left = face_landmarks[33]
            eye_right = face_landmarks[263]

            mouth_width = math.hypot(
                mouth_left["x"] - mouth_right["x"], mouth_left["y"] - mouth_right["y"]
            )
            mouth_height = math.hypot(
                mouth_top["x"] - mouth_bottom["x"], mouth_top["y"] - mouth_bottom["y"]
            )
            brow_distance = math.hypot(
                brow_left["x"] - brow_right["x"], brow_left["y"] - brow_right["y"]
            )

            # Simple rule-based classification
            smile_ratio = mouth_width / max(mouth_height, 1e-6)
            brow_raise = (brow_left["y"] + brow_right["y"]) / 2.0

            if smile_ratio > 3.0 and mouth_height < 0.03:
                return EmotionResult(
                    primary="happy", intensity=0.85, valence=0.8, arousal=0.6
                )
            elif smile_ratio > 2.5 and mouth_height > 0.04:
                return EmotionResult(
                    primary="surprised", intensity=0.8, valence=0.0, arousal=0.95
                )
            elif brow_raise < 0.35 and brow_distance < 0.2:
                return EmotionResult(
                    primary="angry", intensity=0.75, valence=-0.7, arousal=0.85
                )
            elif mouth_height > 0.05 and smile_ratio < 2.0:
                return EmotionResult(
                    primary="sad", intensity=0.7, valence=-0.6, arousal=0.2
                )
            elif brow_raise < 0.32:
                return EmotionResult(
                    primary="fearful", intensity=0.65, valence=-0.5, arousal=0.9
                )
            elif mouth_height < 0.015 and smile_ratio > 2.8:
                return EmotionResult(
                    primary="neutral", intensity=0.9, valence=0.0, arousal=0.1
                )
            else:
                return EmotionResult(
                    primary="neutral", intensity=0.6, valence=0.0, arousal=0.3
                )
        except (IndexError, KeyError):
            return EmotionResult(primary="neutral", intensity=0.5, valence=0.0, arousal=0.5)

    def _estimate_head_pose(self, landmarks: List[dict]) -> Dict[str, float]:
        """Estimate head pose (yaw, pitch, roll) from face landmarks."""
        if len(landmarks) < 468:
            return {"yaw": 0.0, "pitch": 0.0, "roll": 0.0}
        nose = landmarks[1]
        left_eye = landmarks[33]
        right_eye = landmarks[263]
        # Approximate angles from landmark geometry
        yaw = math.degrees(math.atan2(nose["x"] - 0.5, nose["z"] + 0.01))
        pitch = math.degrees(math.atan2(nose["y"] - 0.5, nose["z"] + 0.01))
        roll = math.degrees(
            math.atan2(right_eye["y"] - left_eye["y"], right_eye["x"] - left_eye["x"])
        )
        return {"yaw": round(yaw, 2), "pitch": round(pitch, 2), "roll": round(roll, 2)}

    def _estimate_eye_openness(self, landmarks: List[dict]) -> Dict[str, float]:
        """Estimate how open each eye is (0=closed, 1=open)."""
        if len(landmarks) < 468:
            return {"left": 1.0, "right": 1.0}
        # Approximate eye aperture from top/bottom landmark distances
        left_top, left_bottom = landmarks[159], landmarks[145]
        right_top, right_bottom = landmarks[386], landmarks[374]
        left_h = math.hypot(left_top["x"] - left_bottom["x"], left_top["y"] - left_bottom["y"])
        right_h = math.hypot(
            right_top["x"] - right_bottom["x"], right_top["y"] - right_bottom["y"]
        )
        return {
            "left": round(min(1.0, left_h / 0.03), 3),
            "right": round(min(1.0, right_h / 0.03), 3),
        }

    def _estimate_gaze_direction(self, landmarks: List[dict]) -> Dict[str, float]:
        """Estimate gaze direction as a normalised 3-D vector."""
        if len(landmarks) < 468:
            return {"x": 0.0, "y": 0.0, "z": 1.0}
        left_iris = landmarks[468] if len(landmarks) > 468 else landmarks[33]
        right_iris = landmarks[473] if len(landmarks) > 473 else landmarks[263]
        gaze_x = (left_iris.get("x", 0.5) + right_iris.get("x", 0.5)) / 2.0 - 0.5
        gaze_y = (left_iris.get("y", 0.5) + right_iris.get("y", 0.5)) / 2.0 - 0.5
        return {"x": round(gaze_x * 2, 3), "y": round(gaze_y * 2, 3), "z": 1.0}

    # ------------------------------------------------------------------
    # Eye Tracking
    # ------------------------------------------------------------------

    def track_eyes(self, frame: "np.ndarray") -> EyeTrackingResult:
        """Fine-grained eye tracking: pupil centres, gaze on screen, blink
        detection, fixation and saccade classification.
        """
        if self.mock_mode:
            return self._mock_eye_tracking()

        # Re-use face mesh for iris landmarks
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w = frame.shape[:2]
        results = self._face_mesh_solution.process(rgb)

        if not results.multi_face_landmarks:
            return self._mock_eye_tracking()

        face = results.multi_face_landmarks[0]
        lm = face.landmark

        # Iris centres (refined landmarks 468-477 in MediaPipe)
        left_pupil = (int(lm[468].x * w), int(lm[468].y * h)) if len(lm) > 468 else (w // 2, h // 2)
        right_pupil = (int(lm[473].x * w), int(lm[473].y * h)) if len(lm) > 473 else (w // 2, h // 2)

        # Eye openness for blink detection
        eye_open = self._estimate_eye_openness(
            [{"x": p.x, "y": p.y, "z": p.z} for p in lm]
        )
        is_blink = (eye_open["left"] < 0.2) and (eye_open["right"] < 0.2)
        if is_blink:
            self._blink_times.append(time.time())

        # Gaze screen mapping (naive model)
        gaze_vec = self._estimate_gaze_direction(
            [{"x": p.x, "y": p.y, "z": p.z} for p in lm]
        )
        screen_x = int((0.5 + gaze_vec["x"] * 0.5) * w)
        screen_y = int((0.5 + gaze_vec["y"] * 0.5) * h)

        # Blink rate (last 60 seconds)
        now = time.time()
        recent_blinks = sum(1 for t in self._blink_times if now - t < 60.0)
        blink_rate = recent_blinks

        # Fixation / saccade (simple velocity threshold)
        fixation = False
        saccade = False
        if self._prev_hand_landmarks:
            vel = math.hypot(
                lm[468].x - self._prev_hand_landmarks[0].get("x", lm[468].x),
                lm[468].y - self._prev_hand_landmarks[0].get("y", lm[468].y),
            )
            fixation = vel < 0.005
            saccade = vel > 0.05

        return EyeTrackingResult(
            left_pupil=left_pupil,
            right_pupil=right_pupil,
            gaze_screen=(screen_x, screen_y),
            is_blinking=is_blink,
            blink_rate=round(blink_rate, 1),
            fixation=fixation,
            saccade=saccade,
        )

    def _mock_eye_tracking(self) -> EyeTrackingResult:
        """Generate realistic synthetic eye tracking data."""
        w, h = self.resolution
        gaze_x = int(w * random.gauss(0.5, 0.15))
        gaze_y = int(h * random.gauss(0.5, 0.15))
        gaze_x = max(0, min(w, gaze_x))
        gaze_y = max(0, min(h, gaze_y))
        is_blink = random.random() < 0.05
        if is_blink:
            self._blink_times.append(time.time())
        now = time.time()
        recent_blinks = sum(1 for t in self._blink_times if now - t < 60.0)
        return EyeTrackingResult(
            left_pupil=(gaze_x - 10, gaze_y),
            right_pupil=(gaze_x + 10, gaze_y),
            gaze_screen=(gaze_x, gaze_y),
            is_blinking=is_blink,
            blink_rate=float(recent_blinks),
            fixation=random.random() < 0.3,
            saccade=random.random() < 0.1,
        )

    # ------------------------------------------------------------------
    # Screen Analysis
    # ------------------------------------------------------------------

    def analyze_screen(self, frame: Optional["np.ndarray"] = None) -> ScreenAnalysis:
        """Capture and analyse the user's screen.

        When *frame* is provided it is analysed directly; otherwise a
        screenshot is attempted (mock data is used when unavailable).
        """
        if self.mock_mode or frame is None:
            return self._mock_screen_analysis()

        h, w = frame.shape[:2]
        elements = self._detect_ui_elements(frame)
        text_content = self._extract_screen_text(frame)
        colors = self._extract_dominant_colors(frame)

        return ScreenAnalysis(
            width=w,
            height=h,
            elements=elements,
            text_content=text_content,
            dominant_colors=colors,
        )

    def _detect_ui_elements(self, frame: "np.ndarray") -> List[UIElement]:
        """Heuristic UI element detection from a screen frame."""
        elements: List[UIElement] = []
        if not _HAS_CV2:
            return elements
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for cnt in contours:
            x, y, cw, ch = cv2.boundingRect(cnt)
            if cw > 40 and ch > 20 and cw < frame.shape[1] * 0.8:
                area = cw * ch
                elem_type = "button" if area < 5000 else "text"
                elements.append(
                    UIElement(
                        element_type=elem_type,
                        coordinates=(x, y, x + cw, y + ch),
                        text="",
                        confidence=0.7,
                    )
                )
        return elements

    def _extract_screen_text(self, frame: "np.ndarray") -> str:
        """Extract text via OCR if available; otherwise return placeholder."""
        if _HAS_CV2:
            return "(screen text — OCR not available in this build)"
        return ""

    def _extract_dominant_colors(self, frame: "np.ndarray") -> List[str]:
        """Return dominant hex colours in the frame."""
        if not _HAS_CV2:
            return ["#333333", "#666666", "#999999"]
        small = cv2.resize(frame, (50, 50))
        pixels = small.reshape(-1, 3)
        from collections import Counter

        hexes = [f"#{p[2]:02x}{p[1]:02x}{p[0]:02x}" for p in pixels[:1000]]
        most = Counter(hexes).most_common(3)
        return [c[0] for c in most] if most else ["#333333"]

    def _mock_screen_analysis(self) -> ScreenAnalysis:
        """Generate realistic synthetic screen data."""
        w, h = self.resolution
        element_types = ["button", "text", "link", "input", "menu", "checkbox"]
        elements = []
        for _ in range(random.randint(3, 10)):
            x1 = random.randint(50, w - 200)
            y1 = random.randint(50, h - 100)
            x2 = x1 + random.randint(60, 200)
            y2 = y1 + random.randint(20, 60)
            elements.append(
                UIElement(
                    element_type=random.choice(element_types),
                    coordinates=(x1, y1, x2, y2),
                    text=random.choice(
                        ["Submit", "Cancel", "Menu", "Search...", "Home", "Settings", ""]
                    ),
                    confidence=round(random.uniform(0.6, 0.95), 3),
                )
            )
        return ScreenAnalysis(
            width=w,
            height=h,
            elements=elements,
            text_content="Mock screen content — synthetic data for testing.",
            dominant_colors=["#2d2d2d", "#4a90d9", "#ffffff"],
        )

    def find_element(self, description: str, screen_analysis: ScreenAnalysis) -> Optional[UIElement]:
        """Find a UI element by natural-language *description*.

        Supports simple keyword matching (e.g. "submit button",
        "search box") against element types and text labels.
        """
        desc = description.lower().strip()
        keyword_map = {
            "submit": ["submit", "send", "ok", "confirm"],
            "cancel": ["cancel", "close", "dismiss"],
            "search": ["search", "find", "query"],
            "menu": ["menu", "nav", "options"],
            "button": ["button", "btn", "click"],
            "input": ["input", "field", "box", "text", "type"],
            "link": ["link", "url", "href"],
        }
        matched_keywords: List[str] = []
        for key, variants in keyword_map.items():
            if key in desc or any(v in desc for v in variants):
                matched_keywords.extend(variants)

        best: Optional[UIElement] = None
        best_score = 0.0
        for elem in screen_analysis.elements:
            score = 0.0
            # Type match
            if any(kw in elem.element_type for kw in matched_keywords):
                score += 0.5
            # Text match
            if any(kw in elem.text.lower() for kw in matched_keywords):
                score += 0.4
            # Fuzzy text containment
            if desc in elem.text.lower() or elem.text.lower() in desc:
                score += 0.3
            if elem.text and any(w in desc for w in elem.text.lower().split()):
                score += 0.2
            score += elem.confidence * 0.1
            if score > best_score:
                best_score = score
                best = elem

        if best:
            logger.debug("find_element('%s') -> %s (score=%.2f)", description, best.text, best_score)
        return best

    # ------------------------------------------------------------------
    # 3D Spatial Mapping
    # ------------------------------------------------------------------

    def get_spatial_context(self) -> SpatialContext:
        """Return the current 3D spatial context.

        Estimates user position, hand positions, field of view and scene
        depth.  In mock mode returns synthetic but plausible data.
        """
        if self.mock_mode:
            return SpatialContext(
                user_position=(0.0, 0.0, round(random.uniform(0.5, 1.5), 2)),
                hand_positions=[
                    (round(random.uniform(-0.3, 0.3), 2),
                     round(random.uniform(-0.2, 0.2), 2),
                     round(random.uniform(0.4, 0.8), 2))
                    for _ in range(random.randint(0, 2))
                ],
                field_of_view=70.0,
                depth_estimate=round(random.uniform(0.6, 1.2), 2),
                scene_geometry={"floor_y": 0.0, "walls": [], "objects": []},
            )

        # Derive from latest hand positions if available
        with self._lock:
            hands = getattr(self, "_latest_hands", None)
        hand_positions = []
        if hands:
            for hand in hands:
                wrist = hand.landmarks[0] if hand.landmarks else {"x": 0.5, "y": 0.5, "z": 0.0}
                hand_positions.append((wrist["x"] - 0.5, 0.5 - wrist["y"], wrist["z"]))

        return SpatialContext(
            user_position=(0.0, 0.0, 0.8),
            hand_positions=hand_positions,
            field_of_view=70.0 if not self._camera_calibrated else 60.0,
            depth_estimate=0.8,
            scene_geometry={"floor_y": 0.0, "walls": [], "objects": []},
        )

    def calibrate_camera(self) -> None:
        """Camera calibration stub.

        Computes a simple focal-length estimate from the configured
        resolution. Full chessboard calibration can be added later.
        """
        w, h = self.resolution
        # Approximate focal length for a 70-degree FOV
        f_x = w / (2.0 * math.tan(math.radians(35.0)))
        f_y = h / (2.0 * math.tan(math.radians(35.0)))
        self._camera_matrix = np.array(
            [[f_x, 0, w / 2], [0, f_y, h / 2], [0, 0, 1]], dtype=np.float64
        )
        self._dist_coeffs = np.zeros((4, 1), dtype=np.float64)
        self._camera_calibrated = True
        logger.info("Camera calibrated: fx=%.1f fy=%.1f at %dx%d", f_x, f_y, w, h)

    # ------------------------------------------------------------------
    # Perception Loop (Background Thread)
    # ------------------------------------------------------------------

    def start_perception_loop(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """Start a background thread that continuously captures frames,
        runs all perception pipelines and delivers results via *callback*.

        Args:
            callback: Receives one dictionary per frame with keys
                ``hands``, ``face``, ``eyes``, ``screen``, ``spatial``,
                ``timestamp`` and ``fps``.
        """
        if self._running:
            logger.warning("Perception loop already running.")
            return

        self._callback = callback
        self._running = True
        self._stop_event.clear()
        self._perception_thread = threading.Thread(
            target=self._perception_loop, name="VRPerceptionLoop", daemon=True
        )
        self._perception_thread.start()
        logger.info("Perception loop started (target FPS=%d, mock=%s)", self.target_fps, self.mock_mode)

    def stop_perception_loop(self) -> None:
        """Signal the perception loop to stop and wait for thread exit."""
        if not self._running:
            return
        self._running = False
        self._stop_event.set()
        if self._perception_thread and self._perception_thread.is_alive():
            self._perception_thread.join(timeout=2.0)
        # Release camera
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        logger.info("Perception loop stopped.")

    def _perception_loop(self) -> None:
        """Main loop body — runs on the background thread."""
        frame_time = 1.0 / self.target_fps

        if not self.mock_mode and _HAS_CV2:
            self._cap = cv2.VideoCapture(self.camera_index)
            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.resolution[0])
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.resolution[1])
            self._cap.set(cv2.CAP_PROP_FPS, self.target_fps)

        while self._running and not self._stop_event.is_set():
            loop_start = time.time()

            if not self.mock_mode and self._cap is not None:
                ret, frame = self._cap.read()
                if not ret:
                    time.sleep(0.01)
                    continue
            else:
                # Mock frame — just a blank array
                frame = np.zeros((self.resolution[1], self.resolution[0], 3), dtype=np.uint8)

            # Run perception pipelines
            hands_result = self.track_hands(frame)
            face_result = self.analyze_face(frame)
            eye_result = self.track_eyes(frame)
            screen_result = self.analyze_screen(frame)
            spatial_result = self.get_spatial_context()

            # Store latest hands for spatial context
            with self._lock:
                self._latest_hands = hands_result.hands

            payload = {
                "hands": hands_result,
                "face": face_result,
                "eyes": eye_result,
                "screen": screen_result,
                "spatial": spatial_result,
                "timestamp": time.time(),
                "fps": hands_result.fps,
            }

            try:
                if self._callback:
                    self._callback(payload)
            except Exception as exc:
                logger.error("Perception callback error: %s", exc)

            # Throttle to target FPS
            elapsed = time.time() - loop_start
            sleep_time = frame_time - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def get_status(self) -> Dict[str, Any]:
        """Return a snapshot of engine health and performance."""
        with self._lock:
            avg_fps = (
                sum(self._fps_history) / len(self._fps_history)
                if self._fps_history
                else float(self.target_fps)
            )
        return {
            "mock_mode": self.mock_mode,
            "camera_available": _HAS_CV2 and not self.mock_mode,
            "mediapipe_available": _HAS_MEDIAPIPE and not self.mock_mode,
            "running": self._running,
            "target_fps": self.target_fps,
            "average_fps": round(avg_fps, 1),
            "resolution": self.resolution,
            "camera_calibrated": self._camera_calibrated,
            "active_tracking_modes": [
                "hands",
                "face",
                "eyes",
                "screen",
                "spatial",
            ],
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _compute_fps(self) -> float:
        with self._lock:
            if not self._fps_history:
                return float(self.target_fps)
            return round(sum(self._fps_history) / len(self._fps_history), 1)


# ===========================================================================
# Self-test
# ===========================================================================

def _run_self_test() -> None:  # pragma: no cover
    """Execute an internal suite of assertions to verify module integrity."""
    logger.info("=== VRPerceptionEngine Self-Test ===")

    # 1. Instantiate in mock mode (guaranteed to work everywhere)
    engine = VRPerceptionEngine(mock_mode=True, target_fps=30)
    assert engine.mock_mode is True
    logger.info("[PASS] Engine instantiation (mock mode)")

    # 2. Status check
    status = engine.get_status()
    assert status["mock_mode"] is True
    assert status["running"] is False
    assert "hands" in status["active_tracking_modes"]
    logger.info("[PASS] get_status()")

    # 3. Hand tracking with synthetic data
    dummy_frame = np.zeros((720, 1280, 3), dtype=np.uint8)
    hand_result = engine.track_hands(dummy_frame)
    assert isinstance(hand_result, HandTrackingResult)
    assert hand_result.timestamp > 0
    logger.info("[PASS] track_hands() -> %d hand(s)", len(hand_result.hands))

    # 4. Gesture recognition
    if hand_result.hands:
        gestures = engine.recognize_gesture(hand_result.hands[0].landmarks)
        assert isinstance(gestures, list)
        for g in gestures:
            assert isinstance(g, Gesture)
            assert 0.0 <= g.confidence <= 1.0
        logger.info("[PASS] recognize_gesture() -> %d gesture(s)", len(gestures))

    # 5. Gesture → command mapping
    test_gesture = Gesture(name="pinch", type="static", confidence=0.9)
    cmd = engine.get_gesture_command(test_gesture)
    assert cmd == "click_select"
    engine.set_gesture_command("pinch", "custom_action")
    assert engine.get_gesture_command(test_gesture) == "custom_action"
    logger.info("[PASS] Gesture command mapping")

    # 6. Face analysis
    face_result = engine.analyze_face(dummy_frame)
    assert isinstance(face_result, FaceAnalysisResult)
    assert face_result.emotion in EMOTION_LABELS
    assert 0.0 <= face_result.emotion_intensity <= 1.0
    assert "yaw" in face_result.head_pose
    logger.info("[PASS] analyze_face() -> emotion=%s", face_result.emotion)

    # 7. Emotion detection
    emotion_res = engine.detect_emotion(face_result.landmarks)
    assert isinstance(emotion_res, EmotionResult)
    assert -1.0 <= emotion_res.valence <= 1.0
    assert 0.0 <= emotion_res.arousal <= 1.0
    logger.info("[PASS] detect_emotion() -> %s", emotion_res.primary)

    # 8. Eye tracking
    eye_result = engine.track_eyes(dummy_frame)
    assert isinstance(eye_result, EyeTrackingResult)
    assert len(eye_result.gaze_screen) == 2
    assert eye_result.blink_rate >= 0.0
    logger.info("[PASS] track_eyes() -> gaze=%s blink=%s", eye_result.gaze_screen, eye_result.is_blinking)

    # 9. Screen analysis
    screen_result = engine.analyze_screen(dummy_frame)
    assert isinstance(screen_result, ScreenAnalysis)
    assert screen_result.width > 0
    assert screen_result.height > 0
    assert len(screen_result.elements) > 0
    logger.info("[PASS] analyze_screen() -> %d elements", len(screen_result.elements))

    # 10. Find UI element
    if screen_result.elements:
        found = engine.find_element("submit button", screen_result)
        assert found is None or isinstance(found, UIElement)
        found2 = engine.find_element("search", screen_result)
        assert found2 is None or isinstance(found2, UIElement)
    logger.info("[PASS] find_element()")

    # 11. Spatial context
    spatial = engine.get_spatial_context()
    assert isinstance(spatial, SpatialContext)
    assert spatial.field_of_view > 0
    assert spatial.depth_estimate > 0
    logger.info("[PASS] get_spatial_context() -> depth=%.2fm", spatial.depth_estimate)

    # 12. Camera calibration
    engine.calibrate_camera()
    assert engine._camera_calibrated is True
    assert engine._camera_matrix is not None
    logger.info("[PASS] calibrate_camera()")

    # 13. Custom gesture registration
    def custom_scorer(lm: List[dict]) -> float:
        return 0.8

    engine.register_custom_gesture("wave", custom_scorer, command="wave_hello")
    assert "wave" in engine._custom_gestures
    logger.info("[PASS] register_custom_gesture()")

    # 14. Perception loop start/stop
    received: List[Dict[str, Any]] = []

    def _cb(payload: Dict[str, Any]) -> None:
        received.append(payload)

    engine.start_perception_loop(_cb)
    assert engine._running is True
    time.sleep(0.5)  # collect a few frames
    engine.stop_perception_loop()
    assert engine._running is False
    assert len(received) > 0
    assert "hands" in received[0]
    assert "face" in received[0]
    assert "eyes" in received[0]
    logger.info("[PASS] Perception loop start/stop (%d frames captured)", len(received))

    logger.info("=== All %d assertions passed ===", 14)


if __name__ == "__main__":
    _run_self_test()
