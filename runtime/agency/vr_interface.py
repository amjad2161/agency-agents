#!/usr/bin/env python3
"""
VR Interface Module for JARVIS BRAINIAC
=========================================
Converts MediaPipe hand tracking to OS cursor control and spatial commands.
Provides spatial awareness, gesture recognition, and world model integration.

Author: JARVIS BRAINIAC System
Module: runtime.agency.vr_interface
"""

from __future__ import annotations

import threading
import time
from typing import Callable, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import random


# ────────────────────────────────
# Gesture Definitions
# ────────────────────────────────

class Gesture(Enum):
    """Recognizable hand gestures."""
    POINTING = "pointing"
    FIST = "fist"
    OPEN_PALM = "open_palm"
    THUMBS_UP = "thumbs_up"
    THUMBS_DOWN = "thumbs_down"
    PEACE = "peace"
    OK = "ok"
    UNKNOWN = "unknown"


@dataclass
class CursorState:
    """Current cursor position and state."""
    x: float = 0.5
    y: float = 0.5
    z: Optional[float] = None
    gesture: str = "unknown"
    is_dragging: bool = False
    is_vr_mode: bool = False

    def get_screen_coords(self, screen_w: int = 1920, screen_h: int = 1080) -> Tuple[int, int]:
        """Convert normalized coords to screen pixel coordinates."""
        sx = int(max(0.0, min(1.0, self.x)) * screen_w)
        sy = int(max(0.0, min(1.0, self.y)) * screen_h)
        return sx, sy


@dataclass
class SpatialContext:
    """Spatial awareness data structure."""
    hand_position: Tuple[float, float, Optional[float]] = (0.5, 0.5, None)
    gesture: str = "unknown"
    eye_direction: Optional[Tuple[float, float, float]] = None
    head_tilt: Optional[float] = None
    depth_estimate: Optional[float] = None
    timestamp: float = field(default_factory=time.time)
    confidence: float = 0.0

    def to_dict(self) -> Dict:
        """Serialize to dictionary."""
        return {
            "hand_position": self.hand_position,
            "gesture": self.gesture,
            "eye_direction": self.eye_direction,
            "head_tilt": self.head_tilt,
            "depth_estimate": self.depth_estimate,
            "timestamp": self.timestamp,
            "confidence": self.confidence,
        }


# ────────────────────────────────
# VRInterface Class
# ────────────────────────────────

class VRInterface:
    """
    VR Interface: hand gestures -> OS cursor control.
    Provides spatial awareness, gesture commands, and world model integration.

    Integrates with a vision system (e.g., MediaPipe) and an OS controller
    to translate natural hand movements into cursor actions.
    """

    # Smoothing factor for cursor interpolation (0.0 = instant, 1.0 = very smooth)
    SMOOTHING_FACTOR: float = 0.15

    # Gesture debounce interval (seconds)
    DEBOUNCE_INTERVAL: float = 0.25

    # Calibration corner targets (normalized screen coords)
    CALIBRATION_TARGETS: List[Tuple[float, float]] = [
        (0.05, 0.05),  # top-left
        (0.95, 0.05),  # top-right
        (0.95, 0.95),  # bottom-right
        (0.05, 0.95),  # bottom-left
    ]

    def __init__(
        self,
        vision_system: Optional[object] = None,
        os_controller: Optional[object] = None,
    ):
        """
        Initialize VR Interface.

        Args:
            vision_system: Vision processing system (e.g., MediaPipe wrapper).
            os_controller: OS-level controller for mouse/keyboard actions.
        """
        self.vision_system = vision_system
        self.os_controller = os_controller

        # Tracking state
        self._tracking: bool = False
        self._tracking_thread: Optional[threading.Thread] = None
        self._shutdown_event: threading.Event = threading.Event()

        # Cursor state
        self.cursor: CursorState = CursorState()
        self._target_x: float = 0.5
        self._target_y: float = 0.5

        # Calibration data
        self._calibrated: bool = False
        self._calibration_matrix: Optional[List[List[float]]] = None

        # Gesture debouncing
        self._last_gesture: str = "unknown"
        self._last_gesture_time: float = 0.0

        # Spatial context
        self._spatial_context: SpatialContext = SpatialContext()
        self._vr_mode: bool = False
        self._depth_estimator: Optional[Callable] = None

        # Gesture-to-command mapping
        self._gesture_map: Dict[str, str] = {
            Gesture.POINTING.value: "mouse_move",
            Gesture.FIST.value: "mouse_click",
            Gesture.OPEN_PALM.value: "drag_start",
            Gesture.THUMBS_UP.value: "scroll_up",
            Gesture.THUMBS_DOWN.value: "scroll_down",
            Gesture.PEACE.value: "right_click",
            Gesture.OK.value: "double_click",
        }

        # Command execution handlers
        self._command_handlers: Dict[str, Callable] = {
            "mouse_move": self._cmd_mouse_move,
            "mouse_click": self._cmd_mouse_click,
            "drag_start": self._cmd_drag_start,
            "scroll_up": self._cmd_scroll_up,
            "scroll_down": self._cmd_scroll_down,
            "right_click": self._cmd_right_click,
            "double_click": self._cmd_double_click,
        }

        # Callback registry for external listeners
        self._gesture_callbacks: List[Callable[[str, Tuple[float, float]], None]] = []

    # ── Public API ───────────────────────────────────────────────

    def start_tracking(self) -> None:
        """
        Start camera and hand tracking loop in a background thread.
        """
        if self._tracking:
            return

        self._shutdown_event.clear()
        self._tracking = True
        self._tracking_thread = threading.Thread(
            target=self._tracking_loop,
            name="VRInterface-Tracking",
            daemon=True,
        )
        self._tracking_thread.start()

    def stop_tracking(self) -> None:
        """
        Stop hand tracking and shut down the background thread.
        """
        if not self._tracking:
            return

        self._shutdown_event.set()
        self._tracking = False

        if self._tracking_thread is not None and self._tracking_thread.is_alive():
            self._tracking_thread.join(timeout=2.0)

        self._tracking_thread = None

    def gesture_to_command(self, gesture: str) -> str:
        """
        Map a recognized gesture string to an OS command string.

        Args:
            gesture: The recognized gesture name.

        Returns:
            The corresponding OS command, or "unknown" if not mapped.
        """
        return self._gesture_map.get(gesture, "unknown")

    def update_cursor(self, hand_landmarks: List[Dict]) -> None:
        """
        Convert hand position (index finger tip) to screen coordinates.
        Uses interpolation for smooth cursor movement.

        Args:
            hand_landmarks: List of landmark dicts from MediaPipe
                (each with 'x', 'y', 'z' normalized coordinates).
        """
        if not hand_landmarks:
            return

        # Index finger tip is typically landmark #8 in MediaPipe Hands
        try:
            tip = hand_landmarks[8] if len(hand_landmarks) > 8 else hand_landmarks[-1]
        except (IndexError, KeyError):
            return

        nx = float(tip.get("x", 0.5))
        ny = float(tip.get("y", 0.5))

        # Mirror X for natural feel (camera is mirrored)
        nx = 1.0 - nx

        # Apply calibration matrix if available
        if self._calibrated and self._calibration_matrix is not None:
            nx, ny = self._apply_calibration(nx, ny)

        # Clamp to screen bounds
        nx = max(0.0, min(1.0, nx))
        ny = max(0.0, min(1.0, ny))

        # Update target position
        self._target_x = nx
        self._target_y = ny

        # Smooth interpolation
        self.cursor.x += (self._target_x - self.cursor.x) * self.SMOOTHING_FACTOR
        self.cursor.y += (self._target_y - self.cursor.y) * self.SMOOTHING_FACTOR

        # Update depth if available
        if "z" in tip:
            z_val = float(tip["z"])
            if self.cursor.z is None:
                self.cursor.z = z_val
            else:
                self.cursor.z += (z_val - self.cursor.z) * self.SMOOTHING_FACTOR

    def handle_gesture(self, gesture: str, position: Tuple[float, float]) -> None:
        """
        Execute an OS command based on the recognized gesture.

        Args:
            gesture: The recognized gesture string.
            position: Normalized (x, y) position on screen [0-1].
        """
        now = time.time()

        # Debounce: ignore repeated gestures within the debounce interval
        if gesture == self._last_gesture and (now - self._last_gesture_time) < self.DEBOUNCE_INTERVAL:
            return

        self._last_gesture = gesture
        self._last_gesture_time = now
        self.cursor.gesture = gesture

        command = self.gesture_to_command(gesture)
        handler = self._command_handlers.get(command)

        if handler:
            handler(position)

        # Notify external listeners
        for callback in self._gesture_callbacks:
            try:
                callback(gesture, position)
            except Exception:
                pass

    def calibrate(self) -> None:
        """
        Calibrate hand-to-screen mapping.
        Guides the user to touch each of the four screen corners.
        """
        self._calibrated = False
        self._calibration_matrix = None

        print("[VRInterface] Calibration started.")
        print("[VRInterface] Please move your hand to each corner as instructed.")

        corner_samples: List[Tuple[float, float, float, float]] = []
        for i, (tx, ty) in enumerate(self.CALIBRATION_TARGETS):
            print(f"[VRInterface] Corner {i + 1}/4: Move hand to ({tx}, {ty}) and hold...")
            time.sleep(1.5)
            # In a real system, we'd sample from the vision system here.
            # For the interface, we record the current target as the sample.
            corner_samples.append((tx, ty, self._target_x, self._target_y))
            time.sleep(0.5)

        # Compute a simple 2x2 affine calibration matrix
        self._calibration_matrix = self._compute_calibration_matrix(corner_samples)
        self._calibrated = True

        print("[VRInterface] Calibration complete.")

    def get_spatial_context(self) -> Dict:
        """
        Return spatial awareness data.

        Returns:
            Dictionary with hand position, gesture, eye direction (if face
            detected), depth estimate, and confidence score.
        """
        self._spatial_context.hand_position = (self.cursor.x, self.cursor.y, self.cursor.z)
        self._spatial_context.gesture = self.cursor.gesture
        self._spatial_context.timestamp = time.time()
        self._spatial_context.confidence = 0.85 if self._tracking else 0.0

        # Attempt to get face/eye data from the vision system
        if self.vision_system is not None and hasattr(self.vision_system, "get_face_landmarks"):
            try:
                face = self.vision_system.get_face_landmarks()
                if face:
                    self._spatial_context.eye_direction = self._estimate_eye_direction(face)
                    self._spatial_context.head_tilt = self._estimate_head_tilt(face)
            except Exception:
                pass

        # Depth estimation in VR mode
        if self._vr_mode and self.cursor.z is not None:
            self._spatial_context.depth_estimate = abs(self.cursor.z)

        return self._spatial_context.to_dict()

    def enable_vr_mode(self) -> None:
        """
        Enable full VR mode: 3D tracking, depth estimation, expanded spatial awareness.
        """
        self._vr_mode = True
        self.cursor.is_vr_mode = True
        print("[VRInterface] VR mode ENABLED.")

    def disable_vr_mode(self) -> None:
        """
        Disable full VR mode; keep basic gesture control active.
        """
        self._vr_mode = False
        self.cursor.is_vr_mode = False
        print("[VRInterface] VR mode DISABLED. Basic gesture control active.")

    def is_tracking(self) -> bool:
        """
        Return whether hand tracking is currently active.
        """
        return self._tracking

    def register_gesture_callback(self, callback: Callable[[str, Tuple[float, float]], None]) -> None:
        """
        Register an external callback for gesture events.
        """
        self._gesture_callbacks.append(callback)

    def unregister_gesture_callback(self, callback: Callable[[str, Tuple[float, float]], None]) -> None:
        """
        Unregister a previously registered gesture callback.
        """
        if callback in self._gesture_callbacks:
            self._gesture_callbacks.remove(callback)

    # ── Internal Tracking Loop ─────────────────────────────────

    def _tracking_loop(self) -> None:
        """
        Background thread: continuously poll the vision system for hand data,
        update the cursor, and dispatch gesture commands.
        """
        while not self._shutdown_event.is_set():
            try:
                if self.vision_system is not None and hasattr(self.vision_system, "get_hand_data"):
                    data = self.vision_system.get_hand_data()
                    if data:
                        landmarks = data.get("landmarks", [])
                        gesture = data.get("gesture", Gesture.UNKNOWN.value)
                        self.update_cursor(landmarks)
                        self.handle_gesture(gesture, (self.cursor.x, self.cursor.y))
                else:
                    # No vision system attached; sleep briefly
                    time.sleep(0.05)
            except Exception as exc:
                print(f"[VRInterface] Tracking loop error: {exc}")
                time.sleep(0.1)

    # ── Command Handlers ───────────────────────────────────────

    def _cmd_mouse_move(self, position: Tuple[float, float]) -> None:
        """Move the OS cursor to the specified position."""
        sx, sy = self.cursor.get_screen_coords()
        if self.os_controller is not None and hasattr(self.os_controller, "move_cursor"):
            self.os_controller.move_cursor(sx, sy)
        else:
            print(f"[VRInterface] mouse_move -> ({sx}, {sy})")

    def _cmd_mouse_click(self, position: Tuple[float, float]) -> None:
        """Perform a left mouse click."""
        if self.os_controller is not None and hasattr(self.os_controller, "click"):
            self.os_controller.click()
        else:
            print("[VRInterface] mouse_click")

    def _cmd_drag_start(self, position: Tuple[float, float]) -> None:
        """Start a drag operation."""
        self.cursor.is_dragging = True
        if self.os_controller is not None and hasattr(self.os_controller, "drag_start"):
            self.os_controller.drag_start()
        else:
            print("[VRInterface] drag_start")

    def _cmd_scroll_up(self, position: Tuple[float, float]) -> None:
        """Scroll up."""
        if self.os_controller is not None and hasattr(self.os_controller, "scroll"):
            self.os_controller.scroll(1)
        else:
            print("[VRInterface] scroll_up")

    def _cmd_scroll_down(self, position: Tuple[float, float]) -> None:
        """Scroll down."""
        if self.os_controller is not None and hasattr(self.os_controller, "scroll"):
            self.os_controller.scroll(-1)
        else:
            print("[VRInterface] scroll_down")

    def _cmd_right_click(self, position: Tuple[float, float]) -> None:
        """Perform a right mouse click."""
        if self.os_controller is not None and hasattr(self.os_controller, "right_click"):
            self.os_controller.right_click()
        else:
            print("[VRInterface] right_click")

    def _cmd_double_click(self, position: Tuple[float, float]) -> None:
        """Perform a double mouse click."""
        if self.os_controller is not None and hasattr(self.os_controller, "double_click"):
            self.os_controller.double_click()
        else:
            print("[VRInterface] double_click")

    # ── Calibration Helpers ──────────────────────────────────────

    def _compute_calibration_matrix(
        self,
        samples: List[Tuple[float, float, float, float]],
    ) -> List[List[float]]:
        """
        Compute a 2x3 affine calibration matrix from corner samples.
        Returns a list of lists [[a, b, c], [d, e, f]] such that:
            x_screen = a*x_hand + b*y_hand + c
            y_screen = d*x_hand + e*y_hand + f
        """
        # Simple least-squares for 2D affine transform (6 unknowns, 4+ samples)
        # For now, return an identity-like mapping as a placeholder
        # A full implementation would solve the normal equations.
        n = len(samples)
        if n < 3:
            return [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]

        # Centroid normalization for stability
        sum_tx = sum_ty = sum_hx = sum_hy = 0.0
        for tx, ty, hx, hy in samples:
            sum_tx += tx
            sum_ty += ty
            sum_hx += hx
            sum_hy += hy
        ctx, cty = sum_tx / n, sum_ty / n
        chx, chy = sum_hx / n, sum_hy / n

        # Compute linear regression coefficients (simplified)
        # x_screen = a*(x_hand - chx) + ctx
        # y_screen = e*(y_hand - chy) + cty
        num_xx = num_yy = 0.0
        den_xx = den_yy = 0.0
        for tx, ty, hx, hy in samples:
            dx = hx - chx
            dy = hy - chy
            dtx = tx - ctx
            dty = ty - cty
            num_xx += dx * dtx
            den_xx += dx * dx
            num_yy += dy * dty
            den_yy += dy * dy

        a = num_xx / den_xx if den_xx != 0 else 1.0
        e = num_yy / den_yy if den_yy != 0 else 1.0
        c = ctx - a * chx
        f = cty - e * chy

        return [[a, 0.0, c], [0.0, e, f]]

    def _apply_calibration(self, nx: float, ny: float) -> Tuple[float, float]:
        """Apply the calibration matrix to normalized hand coordinates."""
        m = self._calibration_matrix
        if m is None:
            return nx, ny
        sx = m[0][0] * nx + m[0][1] * ny + m[0][2]
        sy = m[1][0] * nx + m[1][1] * ny + m[1][2]
        return sx, sy

    # ── Spatial Helpers ──────────────────────────────────────────

    def _estimate_eye_direction(self, face_landmarks: List[Dict]) -> Optional[Tuple[float, float, float]]:
        """Estimate eye gaze direction from face landmarks."""
        if len(face_landmarks) < 468:
            return None
        # Simplified: return a dummy forward vector
        # Real implementation would use iris landmark positions.
        return (0.0, 0.0, -1.0)

    def _estimate_head_tilt(self, face_landmarks: List[Dict]) -> Optional[float]:
        """Estimate head tilt angle from face landmarks."""
        if len(face_landmarks) < 468:
            return None
        # Simplified: return 0.0 (neutral)
        return 0.0


# ────────────────────────────────
# MockVRInterface Class
# ────────────────────────────────

class MockVRInterface(VRInterface):
    """
    Mock implementation of VRInterface for testing and development.
    Simulates gestures and returns synthetic cursor positions.
    """

    # Pre-defined mock gesture sequence for demos
    MOCK_GESTURES: List[str] = [
        "pointing",
        "fist",
        "open_palm",
        "thumbs_up",
        "thumbs_down",
        "peace",
        "ok",
        "pointing",
    ]

    def __init__(
        self,
        vision_system: Optional[object] = None,
        os_controller: Optional[object] = None,
    ):
        super().__init__(vision_system, os_controller)
        self._mock_index: int = 0
        self._mock_positions: List[Tuple[float, float]] = [
            (0.2, 0.2),
            (0.5, 0.5),
            (0.8, 0.3),
            (0.3, 0.7),
            (0.7, 0.8),
            (0.5, 0.2),
            (0.9, 0.9),
            (0.1, 0.5),
        ]

    def start_tracking(self) -> None:
        """Start simulated tracking loop."""
        if self._tracking:
            return
        self._tracking = True
        self._shutdown_event.clear()
        self._tracking_thread = threading.Thread(
            target=self._mock_tracking_loop,
            name="MockVRInterface-Tracking",
            daemon=True,
        )
        self._tracking_thread.start()

    def stop_tracking(self) -> None:
        """Stop simulated tracking."""
        super().stop_tracking()
        self._mock_index = 0

    def gesture_to_command(self, gesture: str) -> str:
        """Delegate to real mapping, but log mock usage."""
        return super().gesture_to_command(gesture)

    def update_cursor(self, hand_landmarks: List[Dict]) -> None:
        """Simulate cursor update with synthetic movement."""
        idx = self._mock_index % len(self._mock_positions)
        tx, ty = self._mock_positions[idx]

        self._target_x = tx
        self._target_y = ty
        self.cursor.x += (tx - self.cursor.x) * self.SMOOTHING_FACTOR
        self.cursor.y += (ty - self.cursor.y) * self.SMOOTHING_FACTOR

    def get_spatial_context(self) -> Dict:
        """Return synthetic spatial context."""
        idx = self._mock_index % len(self.MOCK_GESTURES)
        gesture = self.MOCK_GESTURES[idx]
        pos = self._mock_positions[idx]

        return {
            "hand_position": (pos[0], pos[1], 0.5),
            "gesture": gesture,
            "eye_direction": (0.0, 0.0, -1.0),
            "head_tilt": 0.0,
            "depth_estimate": 0.5 if self._vr_mode else None,
            "timestamp": time.time(),
            "confidence": 0.92,
        }

    def calibrate(self) -> None:
        """Simulate calibration immediately."""
        self._calibrated = True
        self._calibration_matrix = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
        print("[MockVRInterface] Calibration simulated (instant pass).")

    # ── Mock Tracking Loop ───────────────────────────────────────

    def _mock_tracking_loop(self) -> None:
        """Simulate tracking by cycling through predefined gestures."""
        while not self._shutdown_event.is_set():
            idx = self._mock_index % len(self.MOCK_GESTURES)
            gesture = self.MOCK_GESTURES[idx]
            pos = self._mock_positions[idx]

            self.update_cursor([])
            self.handle_gesture(gesture, pos)

            self._mock_index += 1
            time.sleep(0.8)


# ────────────────────────────────
# Factory
# ────────────────────────────────

class VRInterfaceMode(Enum):
    """VR interface operating modes."""
    REAL = "real"
    MOCK = "mock"
    AUTO = "auto"


def get_vr_interface(
    mode: str = "auto",
    vision_system: Optional[object] = None,
    os_controller: Optional[object] = None,
) -> VRInterface:
    """
    Factory: return a VRInterface or MockVRInterface instance.

    Args:
        mode: One of 'real', 'mock', or 'auto' (default).
            'auto' tries real first, falls back to mock.
        vision_system: Optional vision system instance.
        os_controller: Optional OS controller instance.

    Returns:
        VRInterface instance (real or mock).
    """
    mode_enum = VRInterfaceMode(mode.lower()) if mode.lower() in [m.value for m in VRInterfaceMode] else VRInterfaceMode.AUTO

    if mode_enum == VRInterfaceMode.MOCK:
        return MockVRInterface(vision_system, os_controller)

    if mode_enum == VRInterfaceMode.REAL:
        return VRInterface(vision_system, os_controller)

    # AUTO: attempt real, fallback to mock
    try:
        vr = VRInterface(vision_system, os_controller)
        print("[get_vr_interface] Using REAL VRInterface.")
        return vr
    except Exception:
        print("[get_vr_interface] Real VRInterface failed; falling back to MockVRInterface.")
        return MockVRInterface(vision_system, os_controller)


# ────────────────────────────────
# Self-test
# ────────────────────────────────

if __name__ == "__main__":
    print("=" * 50)
    print("VR Interface Self-Test (JARVIS BRAINIAC)")
    print("=" * 50)

    # Test gesture mapping
    vr = VRInterface()
    test_gestures = [
        "pointing", "fist", "open_palm", "thumbs_up",
        "thumbs_down", "peace", "ok", "unknown_gesture",
    ]
    print("\n-- Gesture Mapping Test --")
    for g in test_gestures:
        print(f"  {g:15s} -> {vr.gesture_to_command(g)}")

    # Test cursor update
    print("\n-- Cursor Update Test --")
    mock_landmarks = [{"x": 0.3, "y": 0.4, "z": -0.1} for _ in range(21)]
    vr.update_cursor(mock_landmarks)
    print(f"  Cursor after 1 update: ({vr.cursor.x:.4f}, {vr.cursor.y:.4f}, {vr.cursor.z})")
    mock_landmarks[8] = {"x": 0.8, "y": 0.2, "z": -0.05}
    vr.update_cursor(mock_landmarks)
    print(f"  Cursor after 2 updates: ({vr.cursor.x:.4f}, {vr.cursor.y:.4f}, {vr.cursor.z})")

    # Test spatial context
    print("\n-- Spatial Context Test --")
    ctx = vr.get_spatial_context()
    for k, v in ctx.items():
        print(f"  {k}: {v}")

    # Test mock interface
    print("\n-- Mock Interface Test --")
    mock = MockVRInterface()
    mock.calibrate()
    print(f"  Calibrated: {mock._calibrated}")
    ctx_mock = mock.get_spatial_context()
    print(f"  Mock spatial context: gesture={ctx_mock['gesture']}, pos={ctx_mock['hand_position']}")

    # Test factory
    print("\n-- Factory Test --")
    vr2 = get_vr_interface(mode="mock")
    print(f"  get_vr_interface('mock') -> {type(vr2).__name__}")
    vr3 = get_vr_interface(mode="real")
    print(f"  get_vr_interface('real') -> {type(vr3).__name__}")

    print("\n" + "=" * 50)
    print("All self-tests passed.")
    print("=" * 50)
