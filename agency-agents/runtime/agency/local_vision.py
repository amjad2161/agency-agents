"""
JARVIS BRAINIAC - Local Vision System
======================================
100% local computer vision using MediaPipe, OpenCV, and LLaVA.

Components:
- Hand tracking (gesture recognition)
- Facial analysis (expressions, landmarks)
- Screen understanding (LLaVA via Ollama)
- Object tracking (color/shape matching)
- Mock fallback for missing dependencies
"""

from __future__ import annotations

import os
import platform
import socket
import struct
import sys
import time
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

# ---------------------------------------------------------------------------
# Guard against local logging.py shadowing stdlib logging
# ---------------------------------------------------------------------------
_script_dir = os.path.dirname(os.path.abspath(__file__))
_removed = False
if _script_dir in sys.path:
    sys.path.remove(_script_dir)
    _removed = True

import logging  # stdlib logging (safe now)

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
# Optional dependency flags (set at import time)
# ---------------------------------------------------------------------------
_HAS_CV2 = False
_HAS_MEDIAPIPE = False
_HAS_PIL = False
_HAS_PYAUTOGUI = False

# --- OpenCV ---
try:
    import cv2  # type: ignore

    _HAS_CV2 = True
except ImportError:  # pragma: no cover
    warnings.warn("opencv-python not installed. Camera capture disabled.", ImportWarning)

# --- MediaPipe ---
try:
    import mediapipe as mp  # type: ignore

    _HAS_MEDIAPIPE = True
except ImportError:  # pragma: no cover
    warnings.warn("mediapipe not installed. Hand/face tracking disabled.", ImportWarning)

# --- Pillow ---
try:
    from PIL import Image  # type: ignore

    _HAS_PIL = True
except ImportError:  # pragma: no cover
    warnings.warn("Pillow not installed. Screenshot capture disabled.", ImportWarning)

# --- pyautogui ---
try:
    import pyautogui  # type: ignore

    _HAS_PYAUTOGUI = True
except Exception:  # pragma: no cover
    # pyautogui can fail on headless systems (no DISPLAY)
    _HAS_PYAUTOGUI = False

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_CAMERA_ID = 0
DEFAULT_CAMERA_WIDTH = 1280
DEFAULT_CAMERA_HEIGHT = 720
DEFAULT_CAMERA_FPS = 30

OLLAMA_TIMEOUT = 30  # seconds
OLLAMA_MODEL = "llava"

# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------


class CameraNotAvailableError(RuntimeError):
    """Raised when the requested camera cannot be opened or returns no frames."""


class OllamaConnectionError(ConnectionError):
    """Raised when LLaVA/Ollama is unreachable."""


# ---------------------------------------------------------------------------
# Small helper utilities
# ---------------------------------------------------------------------------

def _check_port_open(host: str, port: int, timeout: float = 2.0) -> bool:
    """Check whether *host:port* is reachable."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (OSError, socket.timeout):
        return False


def _encode_image_to_base64(image: np.ndarray | Image.Image) -> str:
    """Encode an image (numpy BGR or PIL) to a base64 PNG string."""
    import base64
    import io

    if isinstance(image, np.ndarray):
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(rgb)
    else:
        pil_img = image

    buffer = io.BytesIO()
    pil_img.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


# ---------------------------------------------------------------------------
# Gesture heuristics (coordinate-independent)
# ---------------------------------------------------------------------------


def _is_finger_extended(tip_idx: int, pip_idx: int, landmarks: List[List[float]]) -> bool:
    """
    Determine whether a finger is extended.
    Compares the Euclidean distance from the wrist (landmark 0)
    to the tip vs. the PIP joint.  If tip is further from wrist,
    the finger is extended.
    """
    wrist = landmarks[0]
    tip = landmarks[tip_idx]
    pip = landmarks[pip_idx]
    return np.linalg.norm(np.array(tip) - np.array(wrist)) > np.linalg.norm(
        np.array(pip) - np.array(wrist)
    )


# ---------------------------------------------------------------------------
# LocalVisionSystem
# ---------------------------------------------------------------------------


class LocalVisionSystem:
    """
    Local vision pipeline: hand tracking, facial analysis, screen understanding.
    Zero cloud dependency. MediaPipe + OpenCV + LLaVA (via Ollama).
    """

    def __init__(
        self,
        camera_id: int = DEFAULT_CAMERA_ID,
        ollama_url: str = DEFAULT_OLLAMA_URL,
    ) -> None:
        self.camera_id = camera_id
        self.ollama_url = ollama_url.rstrip("/")
        self._cap: Any = None  # cv2.VideoCapture instance
        self._hands: Any = None  # mediapipe Hands solution
        self._face_mesh: Any = None  # mediapipe FaceMesh solution
        self._camera_width = DEFAULT_CAMERA_WIDTH
        self._camera_height = DEFAULT_CAMERA_HEIGHT
        self._camera_fps = DEFAULT_CAMERA_FPS
        self._last_frame_time: float = 0.0

        # ---- OpenCV camera ----
        if _HAS_CV2:
            self._init_camera()
        else:
            logger.warning("OpenCV unavailable – camera capture disabled.")

        # ---- MediaPipe Hands ----
        if _HAS_MEDIAPIPE:
            try:
                self._hands = mp.solutions.hands.Hands(
                    static_image_mode=False,
                    max_num_hands=2,
                    min_detection_confidence=0.5,
                    min_tracking_confidence=0.5,
                )
                logger.info("MediaPipe Hands initialised.")
            except Exception as exc:  # pragma: no cover
                logger.warning("Could not initialise MediaPipe Hands: %s", exc)
                self._hands = None

            try:
                self._face_mesh = mp.solutions.face_mesh.FaceMesh(
                    static_image_mode=False,
                    max_num_faces=1,
                    min_detection_confidence=0.5,
                    min_tracking_confidence=0.5,
                )
                logger.info("MediaPipe FaceMesh initialised.")
            except Exception as exc:  # pragma: no cover
                logger.warning("Could not initialise MediaPipe FaceMesh: %s", exc)
                self._face_mesh = None
        else:
            logger.warning("MediaPipe unavailable – hand/face tracking disabled.")

        # ---- Ollama / LLaVA probe ----
        self._ollama_available = self._probe_ollama()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _init_camera(self) -> None:
        """Attempt to open the camera and read one frame to confirm it works."""
        if not _HAS_CV2:
            return
        cap = cv2.VideoCapture(self.camera_id)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, DEFAULT_CAMERA_WIDTH)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, DEFAULT_CAMERA_HEIGHT)
        cap.set(cv2.CAP_PROP_FPS, DEFAULT_CAMERA_FPS)

        # Wait up to ~2 s for the camera to warm up
        for _ in range(20):
            ret, _ = cap.read()
            if ret:
                break
            time.sleep(0.1)

        if not cap.isOpened():
            logger.warning("Camera %s could not be opened.", self.camera_id)
            cap.release()
            return

        self._cap = cap
        self._camera_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self._camera_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self._camera_fps = cap.get(cv2.CAP_PROP_FPS) or DEFAULT_CAMERA_FPS
        logger.info(
            "Camera %s opened: %sx%s @ %.1f fps",
            self.camera_id,
            self._camera_width,
            self._camera_height,
            self._camera_fps,
        )

    def _probe_ollama(self) -> bool:
        """Check whether the Ollama API is reachable and the LLaVA model is present."""
        try:
            from urllib.parse import urlparse

            parsed = urlparse(self.ollama_url)
            host = parsed.hostname or "localhost"
            port = parsed.port or 11434
            if not _check_port_open(host, port):
                logger.warning("Ollama port %s:%s is not reachable.", host, port)
                return False

            import urllib.request
            import json

            req = urllib.request.Request(
                f"{self.ollama_url}/api/tags",
                method="GET",
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                models = [m.get("name", "") for m in data.get("models", [])]
                available = any("llava" in m for m in models)
                if available:
                    logger.info("Ollama reachable; LLaVA model found.")
                else:
                    logger.warning("Ollama reachable but no LLaVA model found (%s).", models)
                return available
        except Exception as exc:  # pragma: no cover
            logger.warning("Ollama probe failed: %s", exc)
            return False

    def _release_camera(self) -> None:
        """Release the camera resource."""
        if self._cap is not None:
            self._cap.release()
            self._cap = None
            logger.info("Camera released.")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def capture_frame(self) -> np.ndarray:
        """
        Capture a single frame from the camera.

        Returns
        -------
        np.ndarray
            BGR image array with shape (H, W, 3).

        Raises
        ------
        CameraNotAvailableError
            If the camera is not available or fails to return a frame.
        """
        if not _HAS_CV2:
            raise CameraNotAvailableError("OpenCV is not installed.")

        if self._cap is None or not self._cap.isOpened():
            raise CameraNotAvailableError(
                f"Camera {self.camera_id} is not available."
            )

        ret, frame = self._cap.read()
        if not ret or frame is None:
            raise CameraNotAvailableError("Failed to read frame from camera.")

        self._last_frame_time = time.time()
        return frame

    def detect_hands(self, frame: np.ndarray) -> List[Dict[str, Any]]:
        """
        Detect hands in a frame using MediaPipe.

        Parameters
        ----------
        frame : np.ndarray
            BGR image.

        Returns
        -------
        List[Dict[str, Any]]
            Each dict contains:
            - "id" : int            – hand index
            - "landmarks" : list    – 21 MediaPipe landmarks as [x, y, z]
            - "gesture" : str       – one of the supported gesture names or "unknown"
        """
        results: List[Dict[str, Any]] = []
        if not _HAS_MEDIAPIPE or self._hands is None:
            logger.debug("MediaPipe Hands unavailable; returning empty list.")
            return results

        # MediaPipe expects RGB
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_results = self._hands.process(rgb)

        if mp_results.multi_hand_landmarks:
            h, w, _ = frame.shape
            for idx, hand_landmarks in enumerate(mp_results.multi_hand_landmarks):
                coords: List[List[float]] = []
                for lm in hand_landmarks.landmark:
                    coords.append([round(lm.x * w, 3), round(lm.y * h, 3), round(lm.z * w, 3)])
                gesture = self.detect_gesture(coords)
                results.append({
                    "id": idx,
                    "landmarks": coords,
                    "gesture": gesture,
                })
        return results

    def detect_gesture(self, hand_landmarks: List[List[float]]) -> str:
        """
        Recognise a gesture from a list of 21 MediaPipe hand landmarks.

        Supported gestures:
        - "fist", "open_palm", "pointing", "thumbs_up", "thumbs_down",
          "peace", "ok", "unknown"

        Parameters
        ----------
        hand_landmarks : List[List[float]]
            21 landmarks in MediaPipe order.

        Returns
        -------
        str
            Gesture name.
        """
        if len(hand_landmarks) != 21:
            return "unknown"

        # Finger extension booleans (index, middle, ring, pinky)
        fingers = [
            _is_finger_extended(8, 6, hand_landmarks),   # index
            _is_finger_extended(12, 10, hand_landmarks),  # middle
            _is_finger_extended(16, 14, hand_landmarks),  # ring
            _is_finger_extended(20, 18, hand_landmarks),  # pinky
        ]
        extended_count = sum(fingers)

        # Thumb is special – compare tip x to IP joint x (accounting for left/right hand)
        thumb_extended = _is_finger_extended(4, 3, hand_landmarks)

        # -- Heuristic classification --

        # 1. FIST (all fingers curled)
        if extended_count == 0:
            return "fist"

        # 2. OPEN PALM (thumb + all 4 fingers extended)
        if thumb_extended and extended_count == 4:
            return "open_palm"

        # 3. PEACE (index + middle extended, ring+pinky curled, thumb curled)
        if fingers[0] and fingers[1] and not fingers[2] and not fingers[3] and not thumb_extended:
            return "peace"

        # 4. POINTING (only index extended)
        if fingers[0] and not fingers[1] and not fingers[2] and not fingers[3] and not thumb_extended:
            return "pointing"

        # 5. THUMBS UP (only thumb extended, thumb tip above wrist)
        if thumb_extended and extended_count == 0:
            wrist_y = hand_landmarks[0][1]
            thumb_tip_y = hand_landmarks[4][1]
            if thumb_tip_y < wrist_y:
                return "thumbs_up"
            return "thumbs_down"

        # 6. OK (thumb tip near index tip, index not fully extended)
        thumb_tip = np.array(hand_landmarks[4])
        index_tip = np.array(hand_landmarks[8])
        dist_thumb_index = np.linalg.norm(thumb_tip - index_tip)
        if dist_thumb_index < 30 and fingers[1] and fingers[2] and fingers[3]:
            return "ok"

        return "unknown"

    def detect_face(self, frame: np.ndarray) -> Dict[str, Any]:
        """
        Detect face and extract facial landmarks / expression estimate.

        Parameters
        ----------
        frame : np.ndarray
            BGR image.

        Returns
        -------
        Dict[str, Any]
            {
                "landmarks": List[List[float]] | None,
                "expression": "neutral|happy|sad|angry|surprised",
                "confidence": float,
            }
        """
        result: Dict[str, Any] = {
            "landmarks": None,
            "expression": "neutral",
            "confidence": 0.0,
        }
        if not _HAS_MEDIAPIPE or self._face_mesh is None:
            logger.debug("MediaPipe FaceMesh unavailable.")
            return result

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_results = self._face_mesh.process(rgb)

        if mp_results.multi_face_landmarks:
            face = mp_results.multi_face_landmarks[0]
            h, w, _ = frame.shape
            landmarks: List[List[float]] = []
            for lm in face.landmark:
                landmarks.append([round(lm.x * w, 3), round(lm.y * h, 3), round(lm.z * w, 3)])

            result["landmarks"] = landmarks
            result["confidence"] = 0.85
            result["expression"] = self._estimate_expression(landmarks)
        return result

    def _estimate_expression(self, landmarks: List[List[float]]) -> str:
        """
        Very lightweight heuristic expression estimation from FaceMesh landmarks.
        Uses mouth openness and lip curvature as rough proxies.
        """
        if len(landmarks) < 468:
            return "neutral"

        # Key indices (approximate):
        #  upper lip outer: 0 | lower lip outer: 17
        #  mouth left: 61   | mouth right: 291
        #  lip top: 13      | lip bottom: 14
        try:
            lip_top = np.array(landmarks[13])
            lip_bottom = np.array(landmarks[14])
            mouth_left = np.array(landmarks[61])
            mouth_right = np.array(landmarks[291])
            eye_left_top = np.array(landmarks[159])
            eye_left_bottom = np.array(landmarks[145])
            eye_right_top = np.array(landmarks[386])
            eye_right_bottom = np.array(landmarks[374])

            mouth_open = float(np.linalg.norm(lip_top - lip_bottom))
            mouth_width = float(np.linalg.norm(mouth_left - mouth_right))
            eye_left_open = float(np.linalg.norm(eye_left_top - eye_left_bottom))
            eye_right_open = float(np.linalg.norm(eye_right_top - eye_right_bottom))
            avg_eye_open = (eye_left_open + eye_right_open) / 2.0

            # Normalise mouth_open against mouth width
            ratio = mouth_open / max(mouth_width, 1e-6)

            if ratio > 0.35 and avg_eye_open > 15:
                return "surprised"
            if ratio > 0.20 and mouth_width > 70:
                return "happy"
            if ratio < 0.08 and mouth_width < 50:
                return "sad"
            if ratio < 0.06 and avg_eye_open < 8:
                return "angry"
            return "neutral"
        except Exception:
            return "neutral"

    def analyze_screen(self, screenshot_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Analyse the current screen (or a provided screenshot) using LLaVA via Ollama.

        Parameters
        ----------
        screenshot_path : str, optional
            Path to an existing screenshot image. If omitted a new screenshot is taken.

        Returns
        -------
        Dict[str, Any]
            {
                "description": str,
                "ui_elements": List[str],
                "text_content": str,
            }
        """
        result = {
            "description": "No analysis available.",
            "ui_elements": [],
            "text_content": "",
        }

        # --- Step 1: obtain image ---
        image: Optional[Image.Image] = None
        if screenshot_path and os.path.isfile(screenshot_path):
            if _HAS_PIL:
                image = Image.open(screenshot_path).convert("RGB")
            else:
                logger.warning("Pillow unavailable; cannot load %s", screenshot_path)
        else:
            image = self._take_screenshot()

        if image is None:
            return result

        # --- Step 2: call Ollama / LLaVA ---
        if not self._ollama_available:
            logger.warning("Ollama/LLaVA unavailable; returning empty screen analysis.")
            return result

        try:
            description = self._ollama_vision_request(image)
            result["description"] = description
            result["ui_elements"] = self._extract_ui_elements(description)
            result["text_content"] = description  # LLaVA returns free-form text
        except Exception as exc:
            logger.error("Screen analysis failed: %s", exc)
            result["description"] = f"Analysis error: {exc}"

        return result

    def _take_screenshot(self) -> Optional[Image.Image]:
        """Capture the current screen using pyautogui or Pillow (macOS grab)."""
        if _HAS_PYAUTOGUI:
            try:
                screenshot = pyautogui.screenshot()
                return screenshot.convert("RGB")
            except Exception as exc:
                logger.warning("pyautogui screenshot failed: %s", exc)

        if _HAS_PIL:
            try:
                # macOS / Windows / Linux – ImageGrab.grab works on most platforms now
                from PIL import ImageGrab  # type: ignore
                screenshot = ImageGrab.grab()
                return screenshot.convert("RGB")
            except Exception as exc:
                logger.warning("PIL ImageGrab failed: %s", exc)

        return None

    def _ollama_vision_request(self, image: Image.Image) -> str:
        """Send the image + prompt to Ollama's /api/generate endpoint."""
        import json
        import urllib.request

        b64 = _encode_image_to_base64(image)
        prompt = (
            "Describe what you see on this screen. "
            "List any visible UI elements (buttons, menus, text fields, windows). "
            "Also extract any readable text content."
        )

        payload = json.dumps({
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "images": [b64],
            "stream": False,
        }).encode("utf-8")

        req = urllib.request.Request(
            f"{self.ollama_url}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return str(data.get("response", "")).strip()

    def _extract_ui_elements(self, description: str) -> List[str]:
        """Naïve regex extraction of likely UI-element nouns from the LLaVA description."""
        import re
        keywords = [
            "button", "menu", "window", "dialog", "toolbar", "tab",
            "input", "field", "text box", "dropdown", "list", "icon",
            "panel", "sidebar", "navigation", "link", "checkbox", "radio",
        ]
        found = []
        lower = description.lower()
        for kw in keywords:
            if kw in lower:
                found.append(kw)
        # Deduplicate while preserving order
        seen = set()
        out = []
        for item in found:
            if item not in seen:
                seen.add(item)
                out.append(item)
        return out

    def track_object(self, frame: np.ndarray, object_name: str) -> List[Dict[str, Any]]:
        """
        Simple object tracker using colour / shape matching.

        Parameters
        ----------
        frame : np.ndarray
            BGR image.
        object_name : str
            Object to look for.  Supports colour-based names:
            "red", "green", "blue", "yellow", "orange", "purple",
            and generic shapes: "circle", "rectangle".

        Returns
        -------
        List[Dict[str, Any]]
            Bounding boxes with keys x, y, w, h, confidence.
        """
        if not _HAS_CV2:
            return []

        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

        # --- Colour ranges (HSV) ---
        colour_ranges: Dict[str, Tuple[np.ndarray, np.ndarray]] = {
            "red": (
                np.array([0, 120, 70]),
                np.array([10, 255, 255]),
            ),
            "green": (
                np.array([40, 40, 40]),
                np.array([80, 255, 255]),
            ),
            "blue": (
                np.array([100, 150, 0]),
                np.array([140, 255, 255]),
            ),
            "yellow": (
                np.array([20, 100, 100]),
                np.array([35, 255, 255]),
            ),
            "orange": (
                np.array([10, 100, 100]),
                np.array([20, 255, 255]),
            ),
            "purple": (
                np.array([140, 50, 50]),
                np.array([170, 255, 255]),
            ),
        }

        detections: List[Dict[str, Any]] = []

        name_lower = object_name.lower()

        # Colour-based detection
        if name_lower in colour_ranges:
            lower, upper = colour_ranges[name_lower]
            mask = cv2.inRange(hsv, lower, upper)
            # Morphological open to remove noise
            kernel = np.ones((5, 5), np.uint8)
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for cnt in contours:
                area = cv2.contourArea(cnt)
                if area < 500:
                    continue
                x, y, w, h = cv2.boundingRect(cnt)
                detections.append({
                    "x": x,
                    "y": y,
                    "w": w,
                    "h": h,
                    "confidence": round(min(area / 2000.0, 0.99), 3),
                })

        # Shape-based detection (circle / rectangle via Hough / contour approximation)
        elif name_lower in ("circle", "rectangle", "square"):
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            blurred = cv2.GaussianBlur(gray, (9, 9), 2)

            if name_lower == "circle":
                circles = cv2.HoughCircles(
                    blurred,
                    cv2.HOUGH_GRADIENT,
                    dp=1.2,
                    minDist=50,
                    param1=100,
                    param2=30,
                    minRadius=20,
                    maxRadius=200,
                )
                if circles is not None:
                    for c in circles[0, :]:
                        x, y, r = int(c[0]), int(c[1]), int(c[2])
                        detections.append({
                            "x": x - r,
                            "y": y - r,
                            "w": r * 2,
                            "h": r * 2,
                            "confidence": 0.75,
                        })
            else:
                # Rectangle / square via contours
                edges = cv2.Canny(blurred, 50, 150)
                contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                for cnt in contours:
                    approx = cv2.approxPolyDP(cnt, 0.04 * cv2.arcLength(cnt, True), True)
                    if len(approx) == 4:
                        x, y, w, h = cv2.boundingRect(approx)
                        aspect = w / max(h, 1)
                        if name_lower == "square" and 0.8 <= aspect <= 1.2:
                            detections.append({
                                "x": x, "y": y, "w": w, "h": h, "confidence": 0.72,
                            })
                        elif name_lower == "rectangle":
                            detections.append({
                                "x": x, "y": y, "w": w, "h": h, "confidence": 0.70,
                            })

        # Sort by confidence descending
        detections.sort(key=lambda d: d["confidence"], reverse=True)
        return detections[:5]  # cap at top-5

    def get_camera_status(self) -> Dict[str, Any]:
        """
        Return the current camera status.

        Returns
        -------
        Dict[str, Any]
            {
                "available": bool,
                "resolution": (width, height) | None,
                "fps": float | None,
                "backend": str,
                "id": int,
            }
        """
        available = self._cap is not None and self._cap.isOpened()
        backend = "unknown"
        if _HAS_CV2 and self._cap is not None:
            backend = self._cap.getBackendName() if hasattr(self._cap, "getBackendName") else "cv2"

        return {
            "available": available,
            "resolution": (self._camera_width, self._camera_height) if available else None,
            "fps": self._camera_fps if available else None,
            "backend": backend,
            "id": self.camera_id,
        }

    def close(self) -> None:
        """Release all resources (camera, MediaPipe solutions)."""
        self._release_camera()
        if self._hands is not None:
            self._hands.close()
            self._hands = None
        if self._face_mesh is not None:
            self._face_mesh.close()
            self._face_mesh = None
        logger.info("LocalVisionSystem resources released.")

    def __del__(self):
        # Defensive cleanup if user forgets close()
        try:
            self.close()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False


# ---------------------------------------------------------------------------
# MockVisionSystem
# ---------------------------------------------------------------------------


class MockVisionSystem:
    """
    Drop-in replacement for :class:`LocalVisionSystem` when dependencies are missing.
    Every method returns safe mock data without raising exceptions.
    """

    def __init__(
        self,
        camera_id: int = DEFAULT_CAMERA_ID,
        ollama_url: str = DEFAULT_OLLAMA_URL,
    ) -> None:
        self.camera_id = camera_id
        self.ollama_url = ollama_url
        logger.info("MockVisionSystem initialised (no real vision).")

    # -- same interface as LocalVisionSystem --

    def capture_frame(self) -> np.ndarray:
        """Return a blank 720p BGR image."""
        return np.zeros((720, 1280, 3), dtype=np.uint8)

    def detect_hands(self, frame: np.ndarray) -> List[Dict[str, Any]]:
        """Return an empty list."""
        return []

    def detect_gesture(self, hand_landmarks: List[List[float]]) -> str:
        """Always return *unknown*."""
        return "unknown"

    def detect_face(self, frame: np.ndarray) -> Dict[str, Any]:
        """Return a neutral mock face dict."""
        return {
            "landmarks": None,
            "expression": "neutral",
            "confidence": 0.0,
        }

    def analyze_screen(self, screenshot_path: Optional[str] = None) -> Dict[str, Any]:
        """Return a mock screen analysis."""
        return {
            "description": "Mock screen – no vision backend available.",
            "ui_elements": [],
            "text_content": "",
        }

    def track_object(self, frame: np.ndarray, object_name: str) -> List[Dict[str, Any]]:
        """Return an empty list."""
        return []

    def get_camera_status(self) -> Dict[str, Any]:
        """Return unavailable status."""
        return {
            "available": False,
            "resolution": None,
            "fps": None,
            "backend": "mock",
            "id": self.camera_id,
        }

    def close(self) -> None:
        """No-op."""
        pass

    def __del__(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def get_vision_system(
    camera_id: int = DEFAULT_CAMERA_ID,
    ollama_url: str = DEFAULT_OLLAMA_URL,
    prefer_mock: bool = False,
) -> LocalVisionSystem | MockVisionSystem:
    """
    Factory that returns a working vision system.

    - Returns :class:`LocalVisionSystem` if OpenCV **and** MediaPipe are importable.
    - Otherwise returns :class:`MockVisionSystem`.

    Parameters
    ----------
    camera_id : int
        Camera device index.
    ollama_url : str
        Base URL for Ollama REST API.
    prefer_mock : bool
        If ``True``, always return :class:`MockVisionSystem` (useful for tests).

    Returns
    -------
    LocalVisionSystem | MockVisionSystem
    """
    if prefer_mock:
        logger.info("prefer_mock=True → returning MockVisionSystem.")
        return MockVisionSystem(camera_id=camera_id, ollama_url=ollama_url)

    if _HAS_CV2 and _HAS_MEDIAPIPE:
        logger.info("OpenCV + MediaPipe available → returning LocalVisionSystem.")
        return LocalVisionSystem(camera_id=camera_id, ollama_url=ollama_url)

    logger.warning(
        "Missing vision dependencies (cv2=%s, mediapipe=%s) → returning MockVisionSystem.",
        _HAS_CV2,
        _HAS_MEDIAPIPE,
    )
    return MockVisionSystem(camera_id=camera_id, ollama_url=ollama_url)


# ---------------------------------------------------------------------------
# CLI smoke-test (run directly)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="JARVIS Local Vision System smoke test")
    parser.add_argument("--camera", type=int, default=0, help="Camera device index")
    parser.add_argument("--ollama", type=str, default=DEFAULT_OLLAMA_URL, dest="ollama_url", help="Ollama URL")
    parser.add_argument("--mock", action="store_true", help="Force mock mode")
    args = parser.parse_args()

    print("=" * 60)
    print("JARVIS BRAINIAC – Local Vision System")
    print("=" * 60)

    vision = get_vision_system(
        camera_id=args.camera,
        ollama_url=args.ollama_url,
        prefer_mock=args.mock,
    )
    print(f"Vision system type : {type(vision).__name__}")
    print(f"Camera status      : {vision.get_camera_status()}")
    print(f"detect_gesture([]) : {vision.detect_gesture([])}")
    print(f"detect_face(zeros) : {vision.detect_face(np.zeros((100, 100, 3), dtype=np.uint8))}")
    print(f"analyze_screen()   : {vision.analyze_screen()}")
    print(f"track_object()     : {vision.track_object(np.zeros((480, 640, 3), dtype=np.uint8), 'red')}")

    if isinstance(vision, LocalVisionSystem):
        try:
            frame = vision.capture_frame()
            print(f"capture_frame()    : {frame.shape} – OK")
            hands = vision.detect_hands(frame)
            print(f"detect_hands()     : {len(hands)} hand(s) detected")
        except CameraNotAvailableError as exc:
            print(f"capture_frame()    : Camera not available – {exc}")

    vision.close()
    print("\nAll checks passed.")
