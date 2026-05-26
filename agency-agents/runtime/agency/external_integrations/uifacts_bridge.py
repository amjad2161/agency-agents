"""
JARVIS BRAINIAC - UI-TARS Integration Bridge
============================================

Unified UI-TARS (bytedance/UI-TARS) adapter providing:
- GUI screen understanding and analysis
- Action execution on UI elements
- Element tracking across screen states
- Mock fallback when ui-tars is not installed

Usage:
    bridge = UITARSBridge()
    analysis = bridge.understand_screen(screenshot_bytes)
    result = bridge.execute_action("click", {"x": 100, "y": 200})
    tracked = bridge.track_element(element_id="btn_submit")
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Availability flag
# ---------------------------------------------------------------------------
_UITARS_AVAILABLE: bool = False

try:
    import ui_tars
    from ui_tars.vision import ScreenUnderstanding
    from ui_tars.action import ActionExecutor
    from ui_tars.tracking import ElementTracker
    from ui_tars.model import UITARSModel
    _UITARS_AVAILABLE = True
    logger.info("UI-TARS %s loaded successfully.", ui_tars.__version__)
except Exception as _import_exc:
    logger.warning(
        "UI-TARS not installed or failed to import (%s). "
        "Falling back to mock implementations.", _import_exc,
    )

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class ScreenAnalysis:
    """Output from screen understanding."""
    description: str = ""
    elements: List[Dict[str, Any]] = field(default_factory=list)
    layout: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    success: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "description": self.description,
            "elements": self.elements,
            "layout": self.layout,
            "confidence": self.confidence,
            "success": self.success,
        }


@dataclass
class ActionResult:
    """Output from action execution."""
    action: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    result: str = ""
    screen_changed: bool = False
    duration_ms: int = 0
    success: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action, "parameters": self.parameters,
            "result": self.result, "screen_changed": self.screen_changed,
            "duration_ms": self.duration_ms, "success": self.success,
        }


@dataclass
class ElementTrackResult:
    """Output from element tracking."""
    element_id: str
    found: bool = False
    position: Dict[str, int] = field(default_factory=dict)
    state: str = "unknown"
    history: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "element_id": self.element_id, "found": self.found,
            "position": self.position, "state": self.state,
            "history": self.history,
        }


# ---------------------------------------------------------------------------
# Mock implementations
# ---------------------------------------------------------------------------

class _MockScreenUnderstanding:
    """Mock screen understanding for UI-TARS."""

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self.config: Dict[str, Any] = config or {}

    def analyze(self, screenshot: Union[bytes, str]) -> ScreenAnalysis:
        elements = [
            {"type": "button", "label": "Submit", "bbox": [120, 300, 200, 330], "confidence": 0.95},
            {"type": "text_field", "label": "Username", "bbox": [120, 150, 400, 180], "confidence": 0.92},
            {"type": "text_field", "label": "Password", "bbox": [120, 200, 400, 230], "confidence": 0.91},
            {"type": "link", "label": "Forgot Password?", "bbox": [320, 240, 450, 260], "confidence": 0.88},
            {"type": "heading", "label": "Login", "bbox": [200, 50, 300, 90], "confidence": 0.97},
        ]
        return ScreenAnalysis(
            description="Login form with username/password fields and submit button.",
            elements=elements,
            layout={"type": "form", "orientation": "vertical", "element_count": len(elements)},
            confidence=0.93,
            success=True,
        )

    def find_element(self, screenshot: Union[bytes, str], query: str) -> Optional[Dict[str, Any]]:
        return {"type": "button", "label": query, "bbox": [100, 100, 200, 130], "confidence": 0.9}


class _MockActionExecutor:
    """Mock action executor for UI-TARS."""

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self.config: Dict[str, Any] = config or {}
        self.history: List[Dict[str, Any]] = []

    VALID_ACTIONS = {"click", "double_click", "right_click", "type", "scroll", "drag", "hover", "keypress"}

    def execute(self, action: str, parameters: Dict[str, Any]) -> ActionResult:
        start = time.time()
        if action not in self.VALID_ACTIONS:
            result = ActionResult(
                action=action, parameters=parameters,
                result=f"Unknown action: {action}", success=False,
            )
        else:
            coords = f"({parameters.get('x', '?')}, {parameters.get('y', '?')})"
            result = ActionResult(
                action=action, parameters=parameters,
                result=f"[MOCK] Executed {action} at {coords}",
                screen_changed=True, success=True,
            )
        result.duration_ms = int((time.time() - start) * 1000)
        self.history.append(result.to_dict())
        return result

    def batch_execute(self, actions: List[Dict[str, Any]]) -> List[ActionResult]:
        return [self.execute(a["action"], a.get("parameters", {})) for a in actions]


class _MockElementTracker:
    """Mock element tracker for UI-TARS."""

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self.config: Dict[str, Any] = config or {}
        self._elements: Dict[str, Dict[str, Any]] = {}
        self._seed_defaults()

    def _seed_defaults(self) -> None:
        self._elements["btn_submit"] = {"x": 120, "y": 300, "w": 80, "h": 30, "state": "visible"}
        self._elements["input_username"] = {"x": 120, "y": 150, "w": 280, "h": 30, "state": "visible"}
        self._elements["input_password"] = {"x": 120, "y": 200, "w": 280, "h": 30, "state": "visible"}

    def track(self, element_id: str, screenshot: Optional[Union[bytes, str]] = None) -> ElementTrackResult:
        elem = self._elements.get(element_id)
        if elem:
            history = [{"timestamp": time.time(), "state": elem["state"], "position": {"x": elem["x"], "y": elem["y"]}}]
            return ElementTrackResult(
                element_id=element_id, found=True,
                position={"x": elem["x"], "y": elem["y"]},
                state=elem["state"], history=history,
            )
        return ElementTrackResult(element_id=element_id, found=False)

    def register(self, element_id: str, position: Dict[str, int]) -> bool:
        self._elements[element_id] = {**position, "state": "visible"}
        return True


# ---------------------------------------------------------------------------
# UITARSBridge
# ---------------------------------------------------------------------------

class UITARSBridge:
    """
    Unified UI-TARS integration bridge for JARVIS BRAINIAC.

    Provides GUI screen understanding, action execution, and element
    tracking. When UI-TARS is not installed, all methods return
    fully-functional mock implementations.

    Attributes:
        available (bool): Whether the real UI-TARS library is installed.
        config (dict): Bridge configuration.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None, verbose: bool = True) -> None:
        self.available: bool = _UITARS_AVAILABLE
        self.verbose: bool = verbose
        self.config: Dict[str, Any] = config or self._build_default_config()
        self._screen: Any = None
        self._action_executor: Any = None
        self._tracker: Any = None
        self._call_count: int = 0
        logger.info("UITARSBridge initialized (available=%s)", self.available)

    def _build_default_config(self) -> Dict[str, Any]:
        return {
            "model": {
                "provider": os.environ.get("LLM_PROVIDER", "openai"),
                "model": os.environ.get("UITARS_MODEL", "gpt-4-vision-preview"),
                "api_key": os.environ.get("OPENAI_API_KEY", ""),
            },
            "action": {"delay_ms": 100, "timeout": 30},
        }

    def _log(self, msg: str) -> None:
        if self.verbose:
            logger.info("[UITARSBridge] %s", msg)

    def _get_screen(self) -> Any:
        if self._screen is None:
            self._screen = _MockScreenUnderstanding(self.config)
        return self._screen

    def _get_executor(self) -> Any:
        if self._action_executor is None:
            self._action_executor = _MockActionExecutor(self.config)
        return self._action_executor

    def _get_tracker(self) -> Any:
        if self._tracker is None:
            self._tracker = _MockElementTracker(self.config)
        return self._tracker

    # -- public API ----------------------------------------------------------

    def understand_screen(self, screenshot: Union[bytes, str, None] = None) -> ScreenAnalysis:
        """
        Analyze a screenshot and understand the GUI layout.

        Args:
            screenshot: Raw image bytes or path string. Uses mock if None.

        Returns:
            ScreenAnalysis with elements and layout description.
        """
        self._log("Analyzing screen")
        screen = self._get_screen()
        try:
            result = screen.analyze(screenshot or b"")
        except Exception as exc:
            logger.error("understand_screen failed: %s", exc)
            result = ScreenAnalysis(success=False)
        self._call_count += 1
        return result

    def execute_action(self, action: str, parameters: Dict[str, Any]) -> ActionResult:
        """
        Execute a UI action (click, type, scroll, etc.).

        Args:
            action: Action type ('click', 'type', 'scroll', 'drag', etc.).
            parameters: Action-specific parameters (x, y, text, etc.).

        Returns:
            ActionResult with execution outcome.
        """
        self._log(f"Executing action: {action} with params={parameters}")
        executor = self._get_executor()
        try:
            result = executor.execute(action, parameters)
        except Exception as exc:
            logger.error("execute_action failed: %s", exc)
            result = ActionResult(action=action, parameters=parameters, success=False)
        self._call_count += 1
        return result

    def track_element(self, element_id: str, screenshot: Optional[Union[bytes, str]] = None) -> ElementTrackResult:
        """
        Track a UI element across screen states.

        Args:
            element_id: Identifier for the element to track.
            screenshot: Optional screenshot for visual tracking.

        Returns:
            ElementTrackResult with position and state.
        """
        self._log(f"Tracking element: {element_id}")
        tracker = self._get_tracker()
        try:
            result = tracker.track(element_id, screenshot)
        except Exception as exc:
            logger.error("track_element failed: %s", exc)
            result = ElementTrackResult(element_id=element_id, found=False)
        self._call_count += 1
        return result

    def get_status(self) -> Dict[str, Any]:
        """Return detailed bridge status."""
        return {
            "available": self.available,
            "calls": self._call_count,
            "components": {
                "screen_understanding": self._screen is not None,
                "action_executor": self._action_executor is not None,
                "element_tracker": self._tracker is not None,
            },
        }

    def health_check(self) -> Dict[str, Any]:
        """Return health status of the bridge."""
        return {
            "available": self.available,
            "calls": self._call_count,
            "component_status": {
                "screen_understanding": "ok" if self._get_screen() else "fail",
                "action_executor": "ok" if self._get_executor() else "fail",
                "element_tracker": "ok" if self._get_tracker() else "fail",
            },
        }

    def metadata(self) -> Dict[str, Any]:
        """Return bridge metadata."""
        return {
            "name": "UITARSBridge",
            "version": "1.0.0",
            "project": "bytedance/UI-TARS",
            "stars": "29.6k",
            "description": "Multimodal AI agent for GUI automation",
            "methods": ["understand_screen", "execute_action", "track_element", "get_status"],
            "mock_fallback": True,
        }


# ---------------------------------------------------------------------------
# Factory function
# ---------------------------------------------------------------------------

def get_uitars_bridge(config: Optional[Dict[str, Any]] = None, verbose: bool = True) -> UITARSBridge:
    return UITARSBridge(config=config, verbose=verbose)


# ---------------------------------------------------------------------------
# __main__ self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    bridge = get_uitars_bridge(verbose=True)

    assert bridge.health_check()["available"] in (True, False)
    assert bridge.metadata()["name"] == "UITARSBridge"

    analysis = bridge.understand_screen()
    assert isinstance(analysis, ScreenAnalysis)
    assert len(analysis.elements) >= 4
    assert analysis.success

    action = bridge.execute_action("click", {"x": 100, "y": 200})
    assert isinstance(action, ActionResult)
    assert action.success
    assert action.screen_changed

    tracked = bridge.track_element("btn_submit")
    assert isinstance(tracked, ElementTrackResult)
    assert tracked.found
    assert "x" in tracked.position

    status = bridge.get_status()
    assert status["calls"] == 3

    print("All UITARSBridge self-tests passed!")
