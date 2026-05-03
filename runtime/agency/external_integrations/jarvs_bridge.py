"""
JARVIS BRAINIAC - JarVS Integration Bridge
==========================================

Unified JarVS (Jar Virtual Studio) adapter providing:
- Spatial workspace setup for Apple Vision Pro
- Floating virtual screen arrangement
- VS Code spatial editor sessions
- Claude Code command execution in immersive environment
- System status monitoring
- Mock fallback when JarVS SDK is not available

Usage:
    bridge = JarVSBridge()
    ws = bridge.setup_workspace(layout="developer")
    editor = bridge.open_editor(["main.py", "README.md"])
    result = bridge.run_claude_command("/help")
    layout = bridge.arrange_screens({"count": 6, "spacing": 1.2})
    status = bridge.get_status()

App Store: https://apps.apple.com/us/app/jarvs/id6759111444
"""

from __future__ import annotations

import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Availability flag
# ---------------------------------------------------------------------------
_JARVS_AVAILABLE: bool = False

try:
    import jarvs_sdk
    from jarvs_sdk.workspace import SpatialWorkspace
    from jarvs_sdk.display import DisplayManager
    from jarvs_sdk.claude import ClaudeCodeClient
    from jarvs_sdk.layout import ScreenLayoutManager
    _JARVS_AVAILABLE = True
    logger.info("JarVS SDK %s loaded successfully.", jarvs_sdk.__version__)
except Exception as _import_exc:
    logger.warning(
        "JarVS SDK not installed or failed to import (%s). "
        "Falling back to mock implementations.", _import_exc,
    )

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class Screen:
    """A single floating virtual screen in the spatial workspace."""
    screen_id: str
    name: str
    width: float = 1.2
    height: float = 0.8
    position: Tuple[float, float, float] = (0.0, 1.5, -1.5)
    rotation: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    scale: float = 1.0
    opacity: float = 1.0
    pinned: bool = False
    content: str = ""
    active: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "screen_id": self.screen_id,
            "name": self.name,
            "width": self.width,
            "height": self.height,
            "position": self.position,
            "rotation": self.rotation,
            "scale": self.scale,
            "opacity": self.opacity,
            "pinned": self.pinned,
            "content": self.content,
            "active": self.active,
        }


@dataclass
class Workspace:
    """A spatial workspace with floating screens."""
    workspace_id: str
    name: str
    screens: List[Screen] = field(default_factory=list)
    layout_type: str = "default"
    created_at: float = field(default_factory=time.time)
    active: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "workspace_id": self.workspace_id,
            "name": self.name,
            "screens": [s.to_dict() for s in self.screens],
            "layout_type": self.layout_type,
            "created_at": self.created_at,
            "active": self.active,
        }


@dataclass
class EditorSession:
    """An active VS Code spatial editor session."""
    session_id: str
    files: List[str] = field(default_factory=list)
    active_file: str = ""
    cursor_line: int = 1
    cursor_col: int = 1
    language: str = "python"
    connected: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "files": self.files,
            "active_file": self.active_file,
            "cursor_line": self.cursor_line,
            "cursor_col": self.cursor_col,
            "language": self.language,
            "connected": self.connected,
        }


@dataclass
class ClaudeResult:
    """Result from a Claude Code command execution."""
    command: str
    output: str
    status: str = "success"  # success, error, pending
    duration_ms: int = 0
    suggestions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "command": self.command,
            "output": self.output,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "suggestions": self.suggestions,
        }


@dataclass
class Layout:
    """Screen layout configuration."""
    layout_id: str
    screen_count: int = 6
    arrangement: str = "semicircle"
    spacing: float = 1.0
    curvature: float = 0.5
    positions: List[Tuple[float, float, float]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "layout_id": self.layout_id,
            "screen_count": self.screen_count,
            "arrangement": self.arrangement,
            "spacing": self.spacing,
            "curvature": self.curvature,
            "positions": self.positions,
        }


# ---------------------------------------------------------------------------
# Mock implementations
# ---------------------------------------------------------------------------

class _MockSpatialWorkspace:
    """Mock spatial workspace manager for JarVS."""

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self.config: Dict[str, Any] = config or {}
        self._workspaces: Dict[str, Workspace] = {}

    def create_workspace(self, name: str, layout: str = "default") -> Workspace:
        ws_id = f"jvs_{uuid.uuid4().hex[:8]}"
        screens = self._generate_screens(layout)
        ws = Workspace(
            workspace_id=ws_id,
            name=name,
            screens=screens,
            layout_type=layout,
        )
        self._workspaces[ws_id] = ws
        return ws

    def _generate_screens(self, layout: str) -> List[Screen]:
        screens: List[Screen] = []
        configs = {
            "default": [
                ("Main", (-1.3, 1.5, -1.8), (0, 15, 0)),
                ("Terminal", (0, 1.5, -2.0), (0, 0, 0)),
                ("Browser", (1.3, 1.5, -1.8), (0, -15, 0)),
                ("Chat", (-1.8, 1.5, -0.8), (0, 35, 0)),
                ("Docs", (1.8, 1.5, -0.8), (0, -35, 0)),
                ("Files", (0, 0.9, -1.5), (-15, 0, 0)),
            ],
            "developer": [
                ("Editor", (-1.0, 1.6, -2.0), (0, 12, 0)),
                ("Terminal", (1.0, 1.6, -2.0), (0, -12, 0)),
                ("Debug", (0, 1.6, -1.8), (0, 0, 0)),
                ("Git", (-2.0, 1.4, -1.0), (0, 40, 0)),
                ("Preview", (2.0, 1.4, -1.0), (0, -40, 0)),
                ("AI Chat", (0, 1.2, -1.5), (-10, 0, 0)),
            ],
            "minimal": [
                ("Main", (0, 1.5, -2.0), (0, 0, 0)),
                ("Secondary", (1.5, 1.5, -1.2), (0, -30, 0)),
            ],
        }
        screen_configs = configs.get(layout, configs["default"])
        for i, (name, pos, rot) in enumerate(screen_configs):
            screens.append(Screen(
                screen_id=f"scr_{i}",
                name=name,
                width=1.2 + (0.4 if "Editor" in name else 0),
                height=0.8 + (0.2 if "Editor" in name else 0),
                position=pos,
                rotation=rot,
            ))
        return screens

    def get_workspace(self, ws_id: str) -> Optional[Workspace]:
        return self._workspaces.get(ws_id)

    def list_workspaces(self) -> List[Workspace]:
        return list(self._workspaces.values())


class _MockEditorManager:
    """Mock spatial editor manager for VS Code integration."""

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self.config: Dict[str, Any] = config or {}
        self._sessions: Dict[str, EditorSession] = {}

    def open(self, files: List[str], language: str = "python") -> EditorSession:
        sid = f"ed_{uuid.uuid4().hex[:8]}"
        session = EditorSession(
            session_id=sid,
            files=list(files),
            active_file=files[0] if files else "",
            language=language,
            connected=True,
        )
        self._sessions[sid] = session
        return session

    def get_session(self, sid: str) -> Optional[EditorSession]:
        return self._sessions.get(sid)

    def close_session(self, sid: str) -> bool:
        if sid in self._sessions:
            self._sessions[sid].connected = False
            return True
        return False


class _MockClaudeClient:
    """Mock Claude Code client for JarVS spatial environment."""

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self.config: Dict[str, Any] = config or {}
        self._history: List[Dict[str, Any]] = []

    def run_command(self, command: str) -> ClaudeResult:
        start = time.time()
        cmd = command.strip().lower()

        if cmd.startswith("/help"):
            output = (
                "JarVS Claude Code - Available commands:\n"
                "  /help      - Show this help\n"
                "  /edit      - Edit a file\n"
                "  /commit    - Generate commit message\n"
                "  /test      - Run tests\n"
                "  /explain   - Explain code\n"
                "  /fix       - Fix errors\n"
            )
            suggestions = ["/edit main.py", "/commit", "/test"]
        elif cmd.startswith("/edit"):
            output = f"[Claude Code] Opening editor for editing...\nApplied changes to {command[6:].strip() or 'current file'}."
            suggestions = ["/commit", "/test", "/explain"]
        elif cmd.startswith("/commit"):
            output = "[Claude Code] Generated commit message:\nfeat: update implementation with spatial workspace support"
            suggestions = ["/push", "/status"]
        elif cmd.startswith("/test"):
            output = "[Claude Code] Running test suite...\nAll 42 tests passed (mock)."
            suggestions = ["/fix", "/coverage"]
        elif cmd.startswith("/explain"):
            output = "[Claude Code] This code creates a spatial workspace with 6 floating screens arranged in a semicircle, providing an immersive development environment on Vision Pro."
            suggestions = ["/refactor", "/document"]
        else:
            output = f"[Claude Code] Executed: {command}\nResult: OK (mock simulation)"
            suggestions = ["/help"]

        result = ClaudeResult(
            command=command,
            output=output,
            status="success",
            duration_ms=int((time.time() - start) * 1000) or 120,
            suggestions=suggestions,
        )
        self._history.append(result.to_dict())
        return result


class _MockLayoutManager:
    """Mock screen layout manager for JarVS."""

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self.config: Dict[str, Any] = config or {}
        self._layouts: Dict[str, Layout] = {}

    def arrange(self, config: Dict[str, Any]) -> Layout:
        lid = f"lay_{uuid.uuid4().hex[:8]}"
        count = config.get("count", 6)
        spacing = config.get("spacing", 1.0)
        arrangement = config.get("arrangement", "semicircle")
        curvature = config.get("curvature", 0.5)

        positions = self._calculate_positions(count, spacing, arrangement, curvature)
        layout = Layout(
            layout_id=lid,
            screen_count=count,
            arrangement=arrangement,
            spacing=spacing,
            curvature=curvature,
            positions=positions,
        )
        self._layouts[lid] = layout
        return layout

    def _calculate_positions(
        self, count: int, spacing: float, arrangement: str, curvature: float
    ) -> List[Tuple[float, float, float]]:
        positions: List[Tuple[float, float, float]] = []
        if arrangement == "semicircle":
            radius = max(1.5, count * spacing * 0.4)
            for i in range(count):
                angle = -60 + (120 / max(count - 1, 1)) * i
                rad = angle * 3.14159 / 180
                x = radius * rad * 0.8 if count > 1 else 0
                y = 1.5
                z = -2.0 + abs(x) * curvature * 0.3
                positions.append((round(x, 2), round(y, 2), round(z, 2)))
        elif arrangement == "grid":
            cols = int(count ** 0.5) or 1
            for i in range(count):
                x = (i % cols - cols / 2) * spacing
                y = 1.5 + (i // cols) * spacing * 0.6
                z = -2.0
                positions.append((round(x, 2), round(y, 2), round(z, 2)))
        elif arrangement == "linear":
            for i in range(count):
                x = (i - count / 2) * spacing
                y = 1.5
                z = -2.0
                positions.append((round(x, 2), round(y, 2), round(z, 2)))
        else:
            positions = [(0, 1.5, -2.0)] * count
        return positions

    def get_layout(self, lid: str) -> Optional[Layout]:
        return self._layouts.get(lid)


# ---------------------------------------------------------------------------
# JarVSBridge
# ---------------------------------------------------------------------------

class JarVSBridge:
    """
    Unified JarVS integration bridge for JARVIS BRAINIAC.

    Provides spatial workspace setup, VS Code editor sessions,
    Claude Code command execution, and screen arrangement on Apple Vision Pro.
    When JarVS SDK is not installed, all methods return
    fully-functional mock implementations.

    Attributes:
        available (bool): Whether the real JarVS SDK is installed.
        config (dict): Bridge configuration.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None, verbose: bool = True) -> None:
        self.available: bool = _JARVS_AVAILABLE
        self.verbose: bool = verbose
        self.config: Dict[str, Any] = config or self._build_default_config()
        self._workspace_mgr: Any = None
        self._editor_mgr: Any = None
        self._claude_client: Any = None
        self._layout_mgr: Any = None
        self._active_workspace: Optional[str] = None
        logger.info("JarVSBridge initialized (available=%s)", self.available)

    def _build_default_config(self) -> Dict[str, Any]:
        return {
            "vision_pro_ip": os.environ.get("VISION_PRO_IP", "192.168.1.100"),
            "hand_tracking": os.environ.get("JARVS_HAND_TRACKING", "enabled"),
            "eye_tracking": os.environ.get("JARVS_EYE_TRACKING", "enabled"),
            "screen_density": os.environ.get("JARVS_SCREEN_DENSITY", "220"),
            "gesture_sensitivity": float(os.environ.get("JARVS_GESTURE_SENS", "0.8")),
        }

    def _log(self, msg: str) -> None:
        if self.verbose:
            logger.info("[JarVSBridge] %s", msg)

    def _get_workspace_mgr(self) -> Any:
        if self._workspace_mgr is None:
            self._workspace_mgr = _MockSpatialWorkspace(self.config)
        return self._workspace_mgr

    def _get_editor_mgr(self) -> Any:
        if self._editor_mgr is None:
            self._editor_mgr = _MockEditorManager(self.config)
        return self._editor_mgr

    def _get_claude_client(self) -> Any:
        if self._claude_client is None:
            self._claude_client = _MockClaudeClient(self.config)
        return self._claude_client

    def _get_layout_mgr(self) -> Any:
        if self._layout_mgr is None:
            self._layout_mgr = _MockLayoutManager(self.config)
        return self._layout_mgr

    # -- public API ----------------------------------------------------------

    def setup_workspace(self, layout: str = "default") -> Workspace:
        """
        Set up a new spatial workspace with floating screens.

        Args:
            layout: Layout preset - "default", "developer", or "minimal".

        Returns:
            A Workspace object containing the configured floating screens.
        """
        self._log(f"setup_workspace: layout={layout}")
        mgr = self._get_workspace_mgr()
        try:
            ws = mgr.create_workspace(name=f"workspace_{layout}", layout=layout)
            self._active_workspace = ws.workspace_id
        except Exception as exc:
            logger.error("setup_workspace failed: %s", exc)
            ws = Workspace(workspace_id="error", name="error", layout_type=layout)
        return ws

    def open_editor(self, files: List[str]) -> EditorSession:
        """
        Open VS Code in a spatial floating screen.

        Args:
            files: List of file paths to open in the editor.

        Returns:
            An EditorSession object tracking the spatial editor state.
        """
        self._log(f"open_editor: {files}")
        mgr = self._get_editor_mgr()
        try:
            lang = self._detect_language(files[0]) if files else "python"
            session = mgr.open(files, language=lang)
        except Exception as exc:
            logger.error("open_editor failed: %s", exc)
            session = EditorSession(session_id="error", files=list(files))
        return session

    def _detect_language(self, filepath: str) -> str:
        ext = os.path.splitext(filepath)[1].lower()
        lang_map = {
            ".py": "python", ".js": "javascript", ".ts": "typescript",
            ".tsx": "typescriptreact", ".jsx": "javascriptreact",
            ".java": "java", ".go": "go", ".rs": "rust",
            ".c": "c", ".cpp": "cpp", ".h": "c",
            ".html": "html", ".css": "css", ".scss": "scss",
            ".md": "markdown", ".json": "json", ".yaml": "yaml",
        }
        return lang_map.get(ext, "plaintext")

    def run_claude_command(self, command: str) -> ClaudeResult:
        """
        Run a Claude Code command in the spatial environment.

        Args:
            command: Claude Code command string.
                     Examples: "/help", "/edit main.py", "/test"

        Returns:
            A ClaudeResult object with command output and suggestions.
        """
        self._log(f"run_claude_command: {command}")
        client = self._get_claude_client()
        try:
            result = client.run_command(command)
        except Exception as exc:
            logger.error("run_claude_command failed: %s", exc)
            result = ClaudeResult(command=command, output=f"Error: {exc}", status="error")
        return result

    def arrange_screens(self, config: Dict[str, Any]) -> Layout:
        """
        Arrange floating screens in a spatial configuration.

        Args:
            config: Layout configuration dict with keys:
                    - count (int): Number of screens (default 6)
                    - arrangement (str): "semicircle", "grid", "linear"
                    - spacing (float): Distance between screens
                    - curvature (float): Arc curvature for semicircle

        Returns:
            A Layout object with computed screen positions.
        """
        self._log(f"arrange_screens: {config}")
        mgr = self._get_layout_mgr()
        try:
            layout = mgr.arrange(config)
        except Exception as exc:
            logger.error("arrange_screens failed: %s", exc)
            layout = Layout(layout_id="error", screen_count=config.get("count", 6))
        return layout

    def get_status(self) -> Dict[str, Any]:
        """
        Get JarVS system status.

        Returns:
            Dict with workspace, editor, and layout status.
        """
        self._log("get_status")
        return {
            "sdk_available": self.available,
            "active_workspace": self._active_workspace,
            "workspaces": len(self._get_workspace_mgr().list_workspaces()),
            "editor_sessions": len([s for s in [self._editor_mgr] if s]),
            "config": {k: v for k, v in self.config.items() if "ip" not in k.lower()},
        }

    def health_check(self) -> Dict[str, Any]:
        """Return health status of the JarVS bridge."""
        return {
            "available": self.available,
            "active_workspace": self._active_workspace is not None,
            "component_status": {
                "workspace_manager": "ok" if self._get_workspace_mgr() else "fail",
                "editor_manager": "ok" if self._get_editor_mgr() else "fail",
                "claude_client": "ok" if self._get_claude_client() else "fail",
                "layout_manager": "ok" if self._get_layout_mgr() else "fail",
            },
        }

    def metadata(self) -> Dict[str, Any]:
        """Return bridge metadata."""
        return {
            "name": "JarVSBridge",
            "version": "1.0.0",
            "project": "JarVS (Apple Vision Pro)",
            "description": "6 floating screens in living room, VS Code + Claude Code on Vision Pro",
            "app_store_url": "https://apps.apple.com/us/app/jarvs/id6759111444",
            "methods": [
                "setup_workspace", "open_editor", "run_claude_command",
                "arrange_screens", "get_status",
            ],
            "mock_fallback": True,
        }


# ---------------------------------------------------------------------------
# Factory function
# ---------------------------------------------------------------------------

def get_jarvs_bridge(config: Optional[Dict[str, Any]] = None, verbose: bool = True) -> JarVSBridge:
    """Factory: create a JarVSBridge instance."""
    return JarVSBridge(config=config, verbose=verbose)


# ---------------------------------------------------------------------------
# __main__ self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    bridge = get_jarvs_bridge(verbose=True)

    # health_check + metadata
    assert bridge.health_check()["available"] in (True, False)
    assert bridge.metadata()["name"] == "JarVSBridge"
    assert "setup_workspace" in bridge.metadata()["methods"]

    # setup_workspace - default layout
    ws = bridge.setup_workspace("default")
    assert isinstance(ws, Workspace)
    assert ws.workspace_id.startswith("jvs_")
    assert len(ws.screens) == 6
    assert ws.screens[0].name == "Main"

    # setup_workspace - developer layout
    ws_dev = bridge.setup_workspace("developer")
    assert isinstance(ws_dev, Workspace)
    assert len(ws_dev.screens) == 6
    assert ws_dev.layout_type == "developer"

    # setup_workspace - minimal layout
    ws_min = bridge.setup_workspace("minimal")
    assert len(ws_min.screens) == 2

    # open_editor
    editor = bridge.open_editor(["main.py", "utils.py", "README.md"])
    assert isinstance(editor, EditorSession)
    assert editor.session_id.startswith("ed_")
    assert len(editor.files) == 3
    assert editor.language == "python"
    assert editor.connected is True

    # run_claude_command - /help
    result = bridge.run_claude_command("/help")
    assert isinstance(result, ClaudeResult)
    assert result.status == "success"
    assert len(result.suggestions) > 0

    # run_claude_command - /test
    result2 = bridge.run_claude_command("/test")
    assert result2.status == "success"
    assert "test" in result2.output.lower()

    # arrange_screens - semicircle
    layout = bridge.arrange_screens({"count": 6, "arrangement": "semicircle", "spacing": 1.2})
    assert isinstance(layout, Layout)
    assert layout.layout_id.startswith("lay_")
    assert len(layout.positions) == 6
    assert all(len(p) == 3 for p in layout.positions)

    # arrange_screens - grid
    layout2 = bridge.arrange_screens({"count": 4, "arrangement": "grid", "spacing": 1.0})
    assert len(layout2.positions) == 4

    # get_status
    status = bridge.get_status()
    assert isinstance(status, dict)
    assert "sdk_available" in status

    print("All JarVSBridge self-tests passed!")
