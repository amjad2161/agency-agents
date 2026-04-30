"""VR / spatial gesture interface (Tier 5).

Maps recognised :mod:`local_vision` gestures to high-level intents (cursor
moves, click, scroll, mode toggles). The actual cursor movement goes via
:class:`LocalOS.mouse` so the trust gate still applies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .local_os import LocalOS, OSAction
from .local_vision import KNOWN_GESTURES, LocalVision


# Default gesture → intent mapping. Tweak via VRInterface.bind().
DEFAULT_BINDINGS: dict[str, str] = {
    "pinch": "click",
    "open_palm": "stop",
    "fist": "grab",
    "point": "move_cursor",
    "thumbs_up": "confirm",
    "two_fingers": "scroll",
    "victory": "toggle_mode",
}


@dataclass
class VREvent:
    gesture: str
    intent: str
    payload: dict[str, Any] = field(default_factory=dict)
    action: OSAction | None = None


class VRInterface:
    """Translate spatial gestures into OS-level intents."""

    def __init__(self, vision: LocalVision | None = None,
                 os_bridge: LocalOS | None = None) -> None:
        self.vision = vision or LocalVision()
        self.os = os_bridge or LocalOS()
        self.bindings: dict[str, str] = dict(DEFAULT_BINDINGS)

    def bind(self, gesture: str, intent: str) -> None:
        if gesture not in KNOWN_GESTURES:
            raise ValueError(f"unknown gesture: {gesture!r}")
        self.bindings[gesture] = intent

    def handle_frame(self, frame: Any) -> VREvent:
        detection = self.vision.detect_gesture(frame)
        gesture = detection.get("gesture", "")
        intent = self.bindings.get(gesture, "noop")
        evt = VREvent(gesture=gesture, intent=intent, payload=detection)
        if intent == "click":
            evt.action = self.os.mouse(x=0, y=0, button="left")
        elif intent == "move_cursor":
            evt.action = self.os.mouse(x=10, y=10, button="left")
        return evt

    def health(self) -> dict[str, Any]:
        return {
            "bindings": dict(self.bindings),
            "vision": self.vision.health(),
        }
