#!/usr/bin/env python3
"""
JARVIS BRAINIAC - VR HUD Controller
====================================
Python backend serving the Matrix-style 3D spatial interface.
Provides REST endpoints and WebSocket channels for real-time VR data,
gesture streaming, command processing, and subsystem monitoring.

Author: JARVIS System
Version: 3.0.0-MATRIX
"""

import asyncio
import json
import logging
import math
import os
import random
import sys
import time
import uuid
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

# ---------------------------------------------------------------------------
# Dependency handling
# ---------------------------------------------------------------------------
try:
    from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
    from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
    from fastapi.staticfiles import StaticFiles
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel, Field
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False
    try:
        from flask import Flask, request, jsonify, render_template_string, send_from_directory
        from flask_cors import CORS
        HAS_FLASK = True
    except ImportError:
        HAS_FLASK = False
        raise RuntimeError("Install fastapi or flask: pip install fastapi uvicorn flask flask-cors")

try:
    import websockets
    HAS_WEBSOCKETS = True
except ImportError:
    HAS_WEBSOCKETS = False

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_FMT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FMT)
logger = logging.getLogger("jarvis.vr_hud")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
VERSION = "3.0.0-MATRIX"
BUILD_DATE = "2024-01-01"
MODULE_COUNT = 30
WEBSOCKET_HEARTBEAT_INTERVAL = 15.0
GESTURE_BUFFER_SIZE = 256
COMMAND_HISTORY_SIZE = 100

# Hebrew text snippets for UI demonstration
HEBREW_PHRASES = [
    "\u05de\u05e2\u05e8\u05db\u05ea \u05d1\u05e7\u05e8\u05ea",  # System Check
    "\u05d7\u05d9\u05d1\u05d5\u05e8 \u05e4\u05e2\u05d9\u05dc",       # Active Connection
    "\u05de\u05d5\u05d3\u05d5\u05dc \u05e4\u05e2\u05d9\u05dc",       # Active Module
    "\u05de\u05d8\u05e8\u05d9\u05e7\u05e1",                       # Matrix
    "\u05e1\u05d9\u05e0\u05ea\u05d6\u05d4 \u05e0\u05de\u05e9\u05db\u05ea",  # Virtual Reality
    "\u05de\u05e0\u05d4\u05dc \u05de\u05e2\u05e8\u05db\u05ea",       # System Manager
]

# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------
class CommandType(str, Enum):
    SPAWN_WINDOW = "spawn_window"
    CLOSE_WINDOW = "close_window"
    MOVE_WINDOW = "move_window"
    SYSTEM_STATUS = "system_status"
    EXECUTE_TASK = "execute_task"
    TOGGLE_MODULE = "toggle_module"
    SPEECH_COMMAND = "speech_command"
    GESTURE_TRIGGER = "gesture_trigger"
    CUSTOM = "custom"

class GestureType(str, Enum):
    OPEN_HAND = "open_hand"
    CLOSED_FIST = "closed_fist"
    POINTING = "pointing"
    PINCH = "pinch"
    SWIPE_LEFT = "swipe_left"
    SWIPE_RIGHT = "swipe_right"
    SWIPE_UP = "swipe_up"
    SWIPE_DOWN = "swipe_down"
    CIRCLE = "circle"
    NONE = "none"

@dataclass
class GestureData:
    """Represents a detected hand gesture with positional data."""
    gesture_type: GestureType = GestureType.NONE
    confidence: float = 0.0
    hand_x: float = 0.5
    hand_y: float = 0.5
    hand_z: float = 0.0
    palm_open: bool = False
    fingers: List[float] = field(default_factory=lambda: [0.0] * 5)
    timestamp: float = field(default_factory=time.time)
    raw_landmarks: List[Dict[str, float]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "gesture_type": self.gesture_type.value,
            "confidence": round(self.confidence, 4),
            "hand_x": round(self.hand_x, 4),
            "hand_y": round(self.hand_y, 4),
            "hand_z": round(self.hand_z, 4),
            "palm_open": self.palm_open,
            "fingers": [round(f, 4) for f in self.fingers],
            "timestamp": self.timestamp,
        }

@dataclass
class WindowState:
    """State of a floating holographic window."""
    window_id: str
    title: str
    content: str
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    width: float = 400.0
    height: float = 300.0
    opacity: float = 0.85
    pinned: bool = False
    minimized: bool = False
    window_type: str = "terminal"
    created_at: float = field(default_factory=time.time)
    hebrew_content: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "window_id": self.window_id,
            "title": self.title,
            "content": self.content,
            "x": self.x, "y": self.y, "z": self.z,
            "width": self.width, "height": self.height,
            "opacity": self.opacity, "pinned": self.pinned,
            "minimized": self.minimized,
            "window_type": self.window_type,
            "created_at": self.created_at,
            "hebrew_content": self.hebrew_content,
        }

@dataclass
class SubsystemStatus:
    """Status of a JARVIS subsystem/module."""
    module_id: str
    name: str
    status: str  # active, idle, error, loading
    health: float = 100.0
    uptime: float = 0.0
    last_ping: float = 0.0
    tasks_queued: int = 0
    tasks_completed: int = 0
    hebrew_name: str = ""
    icon: str = "circle"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "module_id": self.module_id,
            "name": self.name,
            "status": self.status,
            "health": round(self.health, 1),
            "uptime": round(self.uptime, 1),
            "last_ping": self.last_ping,
            "tasks_queued": self.tasks_queued,
            "tasks_completed": self.tasks_completed,
            "hebrew_name": self.hebrew_name,
            "icon": self.icon,
        }

@dataclass
class HUDMessage:
    """Message format for WebSocket communication."""
    msg_type: str
    payload: Dict[str, Any]
    timestamp: float = field(default_factory=time.time)
    msg_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])

    def to_json(self) -> str:
        return json.dumps({
            "msg_type": self.msg_type,
            "payload": self.payload,
            "timestamp": self.timestamp,
            "msg_id": self.msg_id,
        })

# Pydantic models for request validation
if HAS_FASTAPI:
    class SpawnWindowRequest(BaseModel):
        title: str = "New Window"
        content: str = ""
        x: float = 0.0
        y: float = 0.0
        window_type: str = "terminal"
        hebrew_title: Optional[str] = None
        hebrew_content: Optional[str] = None

    class CommandRequest(BaseModel):
        command_type: str
        params: Dict[str, Any] = Field(default_factory=dict)
        source: str = "hud"  # hud, voice, gesture

    class GestureUpdateRequest(BaseModel):
        gesture_type: str
        confidence: float = 1.0
        hand_x: float = 0.5
        hand_y: float = 0.5
        hand_z: float = 0.0

# ---------------------------------------------------------------------------
# HUD Manager - Core State
# ---------------------------------------------------------------------------
class HUDManager:
    """
    Central state manager for the VR HUD.
    Tracks windows, gestures, subsystems, and broadcasts to WebSocket clients.
    """

    def __init__(self):
        self.windows: Dict[str, WindowState] = {}
        self.subsystems: Dict[str, SubsystemStatus] = {}
        self.gesture_history: deque = deque(maxlen=GESTURE_BUFFER_SIZE)
        self.command_history: deque = deque(maxlen=COMMAND_HISTORY_SIZE)
        self.clients: Set[Any] = set()  # WebSocket clients
        self.running = True
        self.session_start = time.time()
        self.total_gestures = 0
        self.total_commands = 0
        self.current_gesture: Optional[GestureData] = None
        self._init_subsystems()

    def _init_subsystems(self):
        """Initialize all 30 JARVIS subsystems."""
        modules = [
            ("core", "Core Engine", "\u05de\u05e0\u05d5\u05e3 \u05dc\u05d1", "cpu"),
            ("nlu", "NLU Processor", "\u05de\u05e2\u05d1\u05d3 \u05e9\u05e4\u05d4", "message-square"),
            ("vision", "Vision System", "\u05de\u05e2\u05e8\u05db\u05ea \u05e8\u05d0\u05d9\u05d9\u05d4", "eye"),
            ("speech", "Speech Engine", "\u05de\u05e0\u05d5\u05e3 \u05d3\u05d9\u05d1\u05d5\u05e8", "mic"),
            ("memory", "Memory Store", "\u05de\u05d0\u05d2\u05e8 \u05d6\u05d9\u05db\u05e8\u05d5\u05df", "database"),
            ("planning", "Task Planner", "\u05de\u05ea\u05db\u05e0\u05df \u05de\u05e9\u05d9\u05de\u05d5\u05ea", "calendar"),
            ("security", "Security Shield", "\u05de\u05d2\u05df \u05d0\u05d1\u05d8\u05d7\u05d4", "shield"),
            ("network", "Network Mesh", "\u05e8\u05e9\u05ea \u05ea\u05e7\u05e9\u05d5\u05e8\u05ea", "globe"),
            ("io", "I/O Handler", "\u05de\u05e0\u05d4\u05dc \u05e7\u05dc\u05d8", "hard-drive"),
            ("gpu", "GPU Compute", "\u05de\u05d7\u05e9\u05d5\u05d1 GPU", "zap"),
            ("scheduler", "Scheduler", "\u05ea\u05d6\u05de\u05d5\u05df", "clock"),
            ("logger", "Event Logger", "\u05de\u05d5\u05d3\u05e2 \u05d0\u05e8\u05d9\u05e2\u05d5\u05ea", "file-text"),
            ("config", "Config Manager", "\u05de\u05e0\u05d4\u05dc \u05d4\u05d2\u05d3\u05e8\u05d5\u05ea", "settings"),
            ("auth", "Auth Service", "\u05e9\u05d9\u05e8\u05d5\u05ea \u05d0\u05d9\u05de\u05d5\u05ea", "lock"),
            ("notifier", "Notifier", "\u05de\u05d5\u05d3\u05d9\u05e2\u05d9\u05df", "bell"),
            ("search", "Search Index", "\u05de\u05e4\u05ea\u05d7 \u05d7\u05d9\u05e4\u05d5\u05e9", "search"),
            ("analytics", "Analytics", "\u05d0\u05e0\u05dc\u05d9\u05d8\u05d9\u05e7\u05d4", "bar-chart-2"),
            ("bridge", "API Bridge", "\u05d2\u05e9\u05e8 API", "link"),
            ("sandbox", "Code Sandbox", "\u05d0\u05e8\u05d2\u05d6 \u05e7\u05d5\u05d3", "code"),
            ("sensor", "Sensor Fusion", "\u05de\u05d9\u05d6\u05d5\u05d2 \u05d7\u05d9\u05d9\u05e9\u05e0\u05d9\u05dd", "activity"),
            ("vr", "VR Interface", "\u05de\u05de\u05e9\u05e7 VR", "headphones"),
            ("learning", "ML Engine", "\u05de\u05e0\u05d5\u05e3 \u05dc\u05de\u05d9\u05d3\u05d4", "trending-up"),
            ("agent", "Agent Core", "\u05dc\u05d1 \u05e1\u05d5\u05db\u05df", "user"),
            ("files", "File Manager", "\u05de\u05e0\u05d4\u05dc \u05e7\u05d1\u05e6\u05d9\u05dd", "folder"),
            ("crypto", "Crypto Vault", "\u05db\u05e1\u05e4\u05ea \u05e7\u05e8\u05d9\u05e4\u05d8\u05d5", "key"),
            ("hebrew", "Hebrew NLP", "\u05e2\u05d9\u05d1\u05d5\u05d3 \u05e2\u05d1\u05e8\u05d9\u05ea", "type"),
            ("weather", "Weather Agent", "\u05e1\u05d5\u05db\u05df \u05de\u05d6\u05d2 \u05d0\u05d5\u05d5\u05d9\u05e8", "cloud"),
            ("docs", "Doc Parser", "\u05de\u05e4\u05e8\u05e9 \u05de\u05e1\u05de\u05db\u05d9\u05dd", "book-open"),
            ("stream", "Stream Proc", "\u05e2\u05d9\u05d1\u05d5\u05d3 \u05d6\u05e8\u05de\u05d9\u05dd", "radio"),
            ("backup", "Backup Sys", "\u05de\u05e2\u05e8\u05db\u05ea \u05d2\u05d9\u05d1\u05d5\u05d9", "save"),
        ]
        now = time.time()
        for i, (mid, name, hebrew, icon) in enumerate(modules):
            health = 85.0 + random.random() * 15.0
            status = random.choice(["active", "active", "active", "idle"])
            self.subsystems[mid] = SubsystemStatus(
                module_id=mid, name=name, status=status,
                health=health, uptime=now - i * 3600,
                last_ping=now - random.random() * 60,
                tasks_queued=random.randint(0, 5),
                tasks_completed=random.randint(100, 9999),
                hebrew_name=hebrew, icon=icon,
            )
        logger.info(f"Initialized {len(self.subsystems)} subsystems")

    # ---- Window Management ----
    def spawn_window(self, title: str, content: str = "", x: float = 0, y: float = 0,
                     window_type: str = "terminal", hebrew_content: Optional[str] = None,
                     **kwargs) -> WindowState:
        wid = f"win_{str(uuid.uuid4())[:8]}"
        # Auto-position if not specified
        if x == 0 and y == 0:
            x = random.uniform(-2.0, 2.0)
            y = random.uniform(-1.0, 1.0)
        win = WindowState(
            window_id=wid, title=title, content=content,
            x=x, y=y, z=kwargs.get("z", random.uniform(-3.0, -1.0)),
            width=kwargs.get("width", 420),
            height=kwargs.get("height", 320),
            window_type=window_type,
            hebrew_content=hebrew_content,
        )
        self.windows[wid] = win
        self._log_command("spawn_window", {"window_id": wid, "title": title})
        asyncio.create_task(self._broadcast("window_spawned", win.to_dict()))
        logger.info(f"Window spawned: {wid} '{title}' at ({x:.2f}, {y:.2f})")
        return win

    def close_window(self, window_id: str) -> bool:
        if window_id in self.windows:
            del self.windows[window_id]
            asyncio.create_task(self._broadcast("window_closed", {"window_id": window_id}))
            return True
        return False

    def move_window(self, window_id: str, x: float, y: float, z: Optional[float] = None) -> bool:
        if window_id in self.windows:
            self.windows[window_id].x = x
            self.windows[window_id].y = y
            if z is not None:
                self.windows[window_id].z = z
            return True
        return False

    # ---- Gesture Handling ----
    def update_gesture(self, gesture: GestureData):
        self.current_gesture = gesture
        self.gesture_history.append(gesture)
        self.total_gestures += 1
        # Auto-trigger actions based on gesture
        if gesture.gesture_type == GestureType.OPEN_HAND and gesture.confidence > 0.8:
            self.spawn_window("Gesture Window", "Auto-spawned via open hand gesture",
                              gesture.hand_x * 4 - 2, -(gesture.hand_y * 2 - 1), window_type="gesture")
        asyncio.create_task(self._broadcast("gesture_update", gesture.to_dict()))

    # ---- Command Processing ----
    def process_command(self, cmd_type: str, params: Dict[str, Any], source: str = "hud") -> Dict[str, Any]:
        self.total_commands += 1
        result = {"status": "ok", "command": cmd_type, "source": source}
        try:
            if cmd_type == CommandType.SPAWN_WINDOW.value:
                win = self.spawn_window(**params)
                result["window"] = win.to_dict()
            elif cmd_type == CommandType.CLOSE_WINDOW.value:
                self.close_window(params.get("window_id", ""))
            elif cmd_type == CommandType.SYSTEM_STATUS.value:
                result["subsystems"] = [s.to_dict() for s in self.subsystems.values()]
            elif cmd_type == CommandType.TOGGLE_MODULE.value:
                mid = params.get("module_id", "")
                if mid in self.subsystems:
                    old = self.subsystems[mid].status
                    self.subsystems[mid].status = "active" if old != "active" else "idle"
                    result["new_status"] = self.subsystems[mid].status
            elif cmd_type == CommandType.CUSTOM.value:
                result["echo"] = params
            else:
                result["status"] = "unknown_command"
        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e)
            logger.error(f"Command error: {e}")
        self._log_command(cmd_type, params)
        asyncio.create_task(self._broadcast("command_result", result))
        return result

    def _log_command(self, cmd_type: str, params: Dict[str, Any]):
        self.command_history.append({
            "command": cmd_type, "params": params,
            "timestamp": time.time(),
        })

    # ---- Subsystem Updates ----
    def get_all_status(self) -> List[Dict[str, Any]]:
        return [s.to_dict() for s in self.subsystems.values()]

    def update_subsystem(self, module_id: str, **kwargs) -> bool:
        if module_id in self.subsystems:
            for k, v in kwargs.items():
                if hasattr(self.subsystems[module_id], k):
                    setattr(self.subsystems[module_id], k, v)
            return True
        return False

    # ---- WebSocket Broadcasting ----
    async def _broadcast(self, msg_type: str, payload: Dict[str, Any]):
        """Broadcast a message to all connected WebSocket clients."""
        msg = HUDMessage(msg_type=msg_type, payload=payload)
        dead = set()
        for ws in self.clients:
            try:
                await ws.send_text(msg.to_json())
            except Exception:
                dead.add(ws)
        for ws in dead:
            self.clients.discard(ws)

    async def register_client(self, ws):
        self.clients.add(ws)
        logger.info(f"Client connected. Total: {len(self.clients)}")
        # Send initial state
        await ws.send_text(HUDMessage("init", {
            "version": VERSION,
            "subsystems": self.get_all_status(),
            "windows": [w.to_dict() for w in self.windows.values()],
        }).to_json())

    async def unregister_client(self, ws):
        self.clients.discard(ws)
        logger.info(f"Client disconnected. Total: {len(self.clients)}")

    # ---- Background Tasks ----
    async def background_updater(self):
        """Continuously update subsystem metrics and broadcast."""
        while self.running:
            try:
                now = time.time()
                for sub in self.subsystems.values():
                    # Jitter health slightly
                    sub.health = max(50, min(100, sub.health + random.uniform(-2, 2)))
                    sub.uptime = now - sub.uptime
                    sub.last_ping = now - random.random() * 30
                    sub.tasks_completed += random.randint(0, 2)
                # Broadcast heartbeat
                await self._broadcast("heartbeat", {
                    "time": now,
                    "active_windows": len(self.windows),
                    "total_gestures": self.total_gestures,
                    "total_commands": self.total_commands,
                    "clients": len(self.clients),
                })
                # Occasionally broadcast subsystem update
                if random.random() < 0.3:
                    sample = random.sample(list(self.subsystems.values()),
                                            min(5, len(self.subsystems)))
                    await self._broadcast("subsystem_update",
                                          [s.to_dict() for s in sample])
                await asyncio.sleep(2.0)
            except Exception as e:
                logger.error(f"Background updater error: {e}")
                await asyncio.sleep(5.0)

    def get_stats(self) -> Dict[str, Any]:
        uptime = time.time() - self.session_start
        return {
            "version": VERSION,
            "uptime_seconds": round(uptime, 1),
            "subsystems_total": len(self.subsystems),
            "subsystems_active": sum(1 for s in self.subsystems.values() if s.status == "active"),
            "windows_open": len(self.windows),
            "total_gestures": self.total_gestures,
            "total_commands": self.total_commands,
            "connected_clients": len(self.clients),
            "hebrew_phrase": random.choice(HEBREW_PHRASES),
        }


# ---------------------------------------------------------------------------
# Global HUD Manager Instance
# ---------------------------------------------------------------------------
hud = HUDManager()

# ---------------------------------------------------------------------------
# FastAPI Application
# ---------------------------------------------------------------------------
if HAS_FASTAPI:
    app = FastAPI(
        title="JARVIS VR HUD",
        description="Matrix-style 3D spatial interface for JARVIS BRAINIAC",
        version=VERSION,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Static files
    STATIC_DIR = Path(__file__).parent / "static" / "hud"
    if STATIC_DIR.exists():
        app.mount("/hud/static", StaticFiles(directory=str(STATIC_DIR)), name="hud_static")

    @app.get("/hud", response_class=HTMLResponse)
    async def hud_page():
        """Serve the main HUD HTML page."""
        html_path = STATIC_DIR / "index.html"
        if html_path.exists():
            return FileResponse(str(html_path))
        return HTMLResponse(content="<h1>JARVIS HUD - Build the HTML file</h1>")

    @app.get("/hud/status")
    async def hud_status():
        """Get current HUD statistics."""
        return JSONResponse(content=hud.get_stats())

    @app.get("/hud/data")
    async def hud_data():
        """Get all current HUD data (windows, subsystems)."""
        return JSONResponse(content={
            "windows": [w.to_dict() for w in hud.windows.values()],
            "subsystems": hud.get_all_status(),
            "gesture": hud.current_gesture.to_dict() if hud.current_gesture else None,
            "stats": hud.get_stats(),
        })

    @app.post("/hud/command")
    async def hud_command(req: CommandRequest):
        """Execute a HUD command."""
        result = hud.process_command(req.command_type, req.params, req.source)
        return JSONResponse(content=result)

    @app.post("/hud/window/spawn")
    async def hud_spawn_window(req: SpawnWindowRequest):
        """Spawn a new floating window."""
        win = hud.spawn_window(
            title=req.title, content=req.content,
            x=req.x, y=req.y, window_type=req.window_type,
            hebrew_content=req.hebrew_content,
        )
        return JSONResponse(content={"status": "ok", "window": win.to_dict()})

    @app.delete("/hud/window/{window_id}")
    async def hud_close_window(window_id: str):
        """Close a floating window."""
        if hud.close_window(window_id):
            return JSONResponse(content={"status": "ok"})
        raise HTTPException(status_code=404, detail="Window not found")

    @app.get("/hud/subsystems")
    async def hud_subsystems():
        """Get all subsystem statuses."""
        return JSONResponse(content=hud.get_all_status())

    @app.get("/hud/subsystem/{module_id}")
    async def hud_subsystem_detail(module_id: str):
        """Get a specific subsystem's status."""
        if module_id in hud.subsystems:
            return JSONResponse(content=hud.subsystems[module_id].to_dict())
        raise HTTPException(status_code=404, detail="Subsystem not found")

    @app.post("/hud/gesture")
    async def hud_gesture_update(req: GestureUpdateRequest):
        """Update gesture data from tracking system."""
        try:
            gtype = GestureType(req.gesture_type)
        except ValueError:
            gtype = GestureType.NONE
        gesture = GestureData(
            gesture_type=gtype, confidence=req.confidence,
            hand_x=req.hand_x, hand_y=req.hand_y, hand_z=req.hand_z,
        )
        hud.update_gesture(gesture)
        return JSONResponse(content={"status": "ok", "gesture": gesture.to_dict()})

    @app.get("/hud/gestures/history")
    async def hud_gesture_history():
        """Get recent gesture history."""
        return JSONResponse(content=[g.to_dict() for g in hud.gesture_history])

    @app.get("/hud/commands/history")
    async def hud_command_history():
        """Get recent command history."""
        return JSONResponse(content=list(hud.command_history))

    @app.websocket("/hud/ws")
    async def hud_websocket(ws: WebSocket):
        """WebSocket endpoint for real-time HUD updates."""
        await ws.accept()
        await hud.register_client(ws)
        try:
            while True:
                msg = await ws.receive_text()
                try:
                    data = json.loads(msg)
                    if data.get("action") == "ping":
                        await ws.send_text(HUDMessage("pong", {}).to_json())
                    elif data.get("action") == "command":
                        result = hud.process_command(
                            data.get("command_type", "custom"),
                            data.get("params", {}),
                            data.get("source", "hud"),
                        )
                        await ws.send_text(HUDMessage("command_result", result).to_json())
                    elif data.get("action") == "gesture":
                        hud.update_gesture(GestureData(**data.get("gesture", {})))
                    elif data.get("action") == "close_window":
                        hud.close_window(data.get("window_id", ""))
                except Exception as e:
                    logger.error(f"WS message error: {e}")
                    await ws.send_text(HUDMessage("error", {"message": str(e)}).to_json())
        except WebSocketDisconnect:
            await hud.unregister_client(ws)
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
            await hud.unregister_client(ws)

    @app.on_event("startup")
    async def startup_event():
        asyncio.create_task(hud.background_updater())

    @app.on_event("shutdown")
    async def shutdown_event():
        hud.running = False


# ---------------------------------------------------------------------------
# Flask Fallback Application
# ---------------------------------------------------------------------------
if not HAS_FASTAPI and HAS_FLASK:
    app = Flask(__name__, static_folder="static/hud")
    CORS(app)

    @app.route("/hud")
    def hud_page():
        return send_from_directory("static/hud", "index.html")

    @app.route("/hud/status")
    def hud_status():
        return jsonify(hud.get_stats())

    @app.route("/hud/data")
    def hud_data():
        return jsonify({
            "windows": [w.to_dict() for w in hud.windows.values()],
            "subsystems": hud.get_all_status(),
            "stats": hud.get_stats(),
        })

    @app.route("/hud/command", methods=["POST"])
    def hud_command():
        data = request.get_json() or {}
        result = hud.process_command(
            data.get("command_type", "custom"),
            data.get("params", {}),
            data.get("source", "hud"),
        )
        return jsonify(result)

    @app.route("/hud/window/spawn", methods=["POST"])
    def hud_spawn_window():
        data = request.get_json() or {}
        win = hud.spawn_window(**data)
        return jsonify({"status": "ok", "window": win.to_dict()})

    @app.route("/hud/subsystems")
    def hud_subsystems():
        return jsonify(hud.get_all_status())

    @app.route("/hud/gesture", methods=["POST"])
    def hud_gesture_update():
        data = request.get_json() or {}
        gesture = GestureData(
            gesture_type=GestureType(data.get("gesture_type", "none")),
            confidence=data.get("confidence", 1.0),
            hand_x=data.get("hand_x", 0.5),
            hand_y=data.get("hand_y", 0.5),
            hand_z=data.get("hand_z", 0.0),
        )
        hud.update_gesture(gesture)
        return jsonify({"status": "ok"})

# ---------------------------------------------------------------------------
# Standalone WebSocket Server (for systems without FastAPI websockets)
# ---------------------------------------------------------------------------
async def standalone_ws_server(host: str = "0.0.0.0", port: int = 8765):
    """Standalone WebSocket server for HUD streaming."""
    if not HAS_WEBSOCKETS:
        logger.warning("websockets package not installed")
        return

    async def handler(ws, path):
        await hud.register_client(ws)
        try:
            async for msg in ws:
                try:
                    data = json.loads(msg)
                    if data.get("action") == "command":
                        result = hud.process_command(
                            data.get("command_type", "custom"),
                            data.get("params", {}),
                        )
                        await ws.send(HUDMessage("command_result", result).to_json())
                except Exception as e:
                    await ws.send(HUDMessage("error", {"message": str(e)}).to_json())
        except Exception:
            pass
        finally:
            await hud.unregister_client(ws)

    logger.info(f"Standalone WS server on ws://{host}:{port}")
    await websockets.serve(handler, host, port)

# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------
def main():
    import argparse
    parser = argparse.ArgumentParser(description="JARVIS VR HUD Server")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host")
    parser.add_argument("--port", type=int, default=8080, help="HTTP port")
    parser.add_argument("--ws-port", type=int, default=8765, help="WebSocket port")
    parser.add_argument("--workers", type=int, default=1, help="Number of workers")
    args = parser.parse_args()

    if HAS_FASTAPI:
        import uvicorn
        logger.info(f"Starting JARVIS VR HUD v{VERSION}")
        logger.info(f"HUD available at http://{args.host}:{args.port}/hud")
        logger.info(f"WebSocket at ws://{args.host}:{args.port}/hud/ws")
        uvicorn.run(app, host=args.host, port=args.port, workers=args.workers)
    elif HAS_FLASK:
        logger.info(f"Starting JARVIS VR HUD (Flask) v{VERSION}")
        logger.info(f"HUD available at http://{args.host}:{args.port}/hud")
        app.run(host=args.host, port=args.port, debug=True, threaded=True)

if __name__ == "__main__":
    main()
