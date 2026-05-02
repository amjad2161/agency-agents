"""Metaverse VR/AR bridge built on A-Frame WebXR.

Generates a self-contained ``world.html`` file that runs in any WebXR
browser (Quest, Chrome with WebXR flags, Firefox Reality, etc.). The
HTML pulls A-Frame from the official CDN at runtime so the generated
file is small and always uses the latest stable scene graph.

The bridge keeps a thread-safe, in-memory world registry so callers
can manage multiple sessions and avatars without hitting any external
service.
"""

from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass, field
from html import escape as _escape
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..logging import get_logger

log = get_logger()


# ---------------------------------------------------------------------------
# Defaults & catalogues
# ---------------------------------------------------------------------------

AFRAME_CDN = "https://aframe.io/releases/1.5.0/aframe.min.js"
AFRAME_EXTRAS_CDN = "https://cdn.jsdelivr.net/npm/aframe-extras@7.5.1/dist/aframe-extras.min.js"

VALID_THEMES = (
    "cyberpunk", "savanna", "spacestation", "underwater",
    "library", "neon-city", "forest", "void",
)
VALID_SIZES = ("small", "medium", "large", "xl")
VALID_SKIES = ("day", "night", "dusk", "dawn", "void", "stars")
VALID_ASSETS = (
    "cube", "sphere", "plane", "cylinder", "torus", "cone", "screen", "portal",
)
VALID_ROLES = ("guide", "guard", "merchant", "scientist", "ally", "narrator")

_SIZE_RADIUS = {"small": 12.0, "medium": 30.0, "large": 60.0, "xl": 120.0}

_THEME_PALETTE: Dict[str, Dict[str, str]] = {
    "cyberpunk":  {"floor": "#0b0c1a", "ambient": "#ff00d4", "accent": "#00ffff"},
    "savanna":    {"floor": "#c98c4b", "ambient": "#ffe6a8", "accent": "#7d4f24"},
    "spacestation": {"floor": "#23272f", "ambient": "#bcd3ff", "accent": "#5cb6ff"},
    "underwater": {"floor": "#08334a", "ambient": "#7be0ff", "accent": "#1ea7c4"},
    "library":    {"floor": "#3b2916", "ambient": "#fbe7c0", "accent": "#a06a36"},
    "neon-city":  {"floor": "#10131a", "ambient": "#ff39c5", "accent": "#39ffe1"},
    "forest":     {"floor": "#2d3a1f", "ambient": "#9ec46a", "accent": "#3f7a30"},
    "void":       {"floor": "#000000", "ambient": "#222222", "accent": "#ffffff"},
}


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class _Object:
    object_id: str
    asset_type: str
    position: Tuple[float, float, float]
    properties: Dict[str, Any] = field(default_factory=dict)


@dataclass
class _Avatar:
    avatar_id: str
    name: str
    role: str


@dataclass
class _Session:
    session_token: str
    user_name: str
    joined_at: float


@dataclass
class _World:
    world_id: str
    theme: str
    size: str
    sky: str = "night"
    fog: bool = True
    ambient_light: float = 0.3
    objects: Dict[str, _Object] = field(default_factory=dict)
    avatars: Dict[str, _Avatar] = field(default_factory=dict)
    sessions: Dict[str, _Session] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    physics: Dict[str, Any] = field(default_factory=lambda: {
        "gravity": -9.81,
        "friction": 0.4,
        "restitution": 0.2,
        "engine": "aframe-physics-system",
    })


# ---------------------------------------------------------------------------
# Bridge
# ---------------------------------------------------------------------------

class MetaverseBridge:
    """Manage WebXR worlds and emit A-Frame scene HTML."""

    def __init__(self, assets_dir: Optional[Path | str] = None) -> None:
        if assets_dir is None:
            assets_dir = Path("assets") / "metaverse"
        self._assets_dir = Path(assets_dir)
        self._lock = threading.Lock()
        self._worlds: Dict[str, _World] = {}

    # ------------------------------------------------------------------
    # World CRUD
    # ------------------------------------------------------------------

    def create_world(self, theme: str = "cyberpunk", size: str = "medium") -> Dict[str, Any]:
        if theme not in VALID_THEMES:
            raise ValueError(f"theme {theme!r} not in {VALID_THEMES}")
        if size not in VALID_SIZES:
            raise ValueError(f"size {size!r} not in {VALID_SIZES}")

        world_id = f"world_{secrets.token_hex(6)}"
        world = _World(world_id=world_id, theme=theme, size=size)
        self._seed_default_objects(world)

        with self._lock:
            self._worlds[world_id] = world

        path = self._write_world_html(world)
        return {
            "ok": True,
            "world_id": world_id,
            "theme": theme,
            "size": size,
            "html_path": str(path),
            "radius": _SIZE_RADIUS[size],
        }

    def join_session(self, world_id: str, user_name: str) -> Dict[str, Any]:
        if not isinstance(user_name, str) or not user_name.strip():
            raise ValueError("user_name must be a non-empty string")
        world = self._require_world(world_id)
        token = f"sess_{secrets.token_hex(10)}"
        session = _Session(session_token=token, user_name=user_name.strip(), joined_at=time.time())
        with self._lock:
            world.sessions[token] = session
        return {
            "ok": True,
            "session_token": token,
            "world_id": world_id,
            "user_name": session.user_name,
            "joined_at": session.joined_at,
        }

    def add_object(
        self,
        world_id: str,
        asset_type: str,
        position: Tuple[float, float, float] | List[float],
        properties: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if asset_type not in VALID_ASSETS:
            raise ValueError(f"asset_type {asset_type!r} not in {VALID_ASSETS}")
        pos = _coerce_vec3(position)
        props = dict(properties or {})
        world = self._require_world(world_id)
        obj_id = f"obj_{secrets.token_hex(5)}"
        obj = _Object(object_id=obj_id, asset_type=asset_type, position=pos, properties=props)
        with self._lock:
            world.objects[obj_id] = obj
        self._write_world_html(world)
        return {
            "ok": True,
            "object_id": obj_id,
            "world_id": world_id,
            "asset_type": asset_type,
            "position": list(pos),
        }

    def get_world_state(self, world_id: str) -> Dict[str, Any]:
        world = self._require_world(world_id)
        return {
            "world_id": world.world_id,
            "theme": world.theme,
            "size": world.size,
            "sky": world.sky,
            "fog": world.fog,
            "ambient_light": world.ambient_light,
            "objects": [
                {
                    "object_id": o.object_id,
                    "asset_type": o.asset_type,
                    "position": list(o.position),
                    "properties": dict(o.properties),
                }
                for o in world.objects.values()
            ],
            "users": [s.user_name for s in world.sessions.values()],
            "avatars": [
                {"avatar_id": a.avatar_id, "name": a.name, "role": a.role}
                for a in world.avatars.values()
            ],
            "physics": dict(world.physics),
            "created_at": world.created_at,
        }

    def set_environment(
        self,
        world_id: str,
        sky: str = "night",
        fog: bool = True,
        ambient_light: float = 0.3,
    ) -> Dict[str, Any]:
        if sky not in VALID_SKIES:
            raise ValueError(f"sky {sky!r} not in {VALID_SKIES}")
        if not isinstance(fog, bool):
            raise TypeError("fog must be a bool")
        ambient = float(ambient_light)
        if not (0.0 <= ambient <= 1.0):
            raise ValueError("ambient_light must be in [0.0, 1.0]")
        world = self._require_world(world_id)
        with self._lock:
            world.sky = sky
            world.fog = fog
            world.ambient_light = ambient
        self._write_world_html(world)
        return {
            "ok": True,
            "world_id": world_id,
            "sky": sky,
            "fog": fog,
            "ambient_light": ambient,
        }

    def generate_avatar_npc(
        self,
        name: str,
        role: str = "guide",
        world_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not isinstance(name, str) or not name.strip():
            raise ValueError("name must be a non-empty string")
        if role not in VALID_ROLES:
            raise ValueError(f"role {role!r} not in {VALID_ROLES}")

        avatar_id = f"npc_{secrets.token_hex(5)}"
        clean_name = name.strip()
        entity = _aframe_avatar_entity(avatar_id, clean_name, role)
        avatar = _Avatar(avatar_id=avatar_id, name=clean_name, role=role)
        if world_id is not None:
            world = self._require_world(world_id)
            with self._lock:
                world.avatars[avatar_id] = avatar
            self._write_world_html(world)
        return {
            "ok": True,
            "avatar_id": avatar_id,
            "name": clean_name,
            "role": role,
            "entity_html": entity,
            "world_id": world_id,
        }

    # ------------------------------------------------------------------
    # Generic dispatch
    # ------------------------------------------------------------------

    def invoke(self, action: str, **kwargs: Any) -> Any:
        registry: Dict[str, Callable[..., Any]] = {
            "create_world": self.create_world,
            "join_session": self.join_session,
            "add_object": self.add_object,
            "get_world_state": self.get_world_state,
            "set_environment": self.set_environment,
            "generate_avatar_npc": self.generate_avatar_npc,
        }
        if action not in registry:
            raise ValueError(f"unknown metaverse action: {action!r}")
        return registry[action](**kwargs)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _require_world(self, world_id: str) -> _World:
        with self._lock:
            world = self._worlds.get(world_id)
        if world is None:
            raise KeyError(f"unknown world_id: {world_id!r}")
        return world

    def _seed_default_objects(self, world: _World) -> None:
        radius = _SIZE_RADIUS[world.size]
        ring = max(4, int(radius / 6))
        for i in range(ring):
            angle = (i / ring) * 6.283185307179586
            x = round(radius * 0.6 * _math_cos(angle), 3)
            z = round(radius * 0.6 * _math_sin(angle), 3)
            obj_id = f"obj_seed{i:02d}"
            world.objects[obj_id] = _Object(
                object_id=obj_id,
                asset_type="cube",
                position=(x, 0.5, z),
                properties={"color": _THEME_PALETTE[world.theme]["accent"], "scale": 0.8},
            )

    def _write_world_html(self, world: _World) -> Path:
        self._assets_dir.mkdir(parents=True, exist_ok=True)
        html = _render_world_html(world)
        out = self._assets_dir / f"{world.world_id}.html"
        out.write_text(html, encoding="utf-8")
        # Also write/refresh a canonical "world.html" pointing at the most
        # recently touched world for callers expecting a stable filename.
        canonical = self._assets_dir / "world.html"
        canonical.write_text(html, encoding="utf-8")
        log.info("MetaverseBridge: wrote %s", out)
        return out


# ---------------------------------------------------------------------------
# A-Frame HTML rendering
# ---------------------------------------------------------------------------

_BASE_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>JARVIS Metaverse — __WORLD_ID__</title>
<script src="__AFRAME_SRC__"></script>
<script src="__AFRAME_EXTRAS__"></script>
<style>
  html, body { margin: 0; height: 100%; background: #000; }
  .info {
    position: fixed; left: 1rem; top: 1rem; color: #fff;
    font-family: "Inter", "Segoe UI", system-ui, sans-serif; font-size: 0.8rem;
    background: rgba(0, 0, 0, 0.45); padding: 0.5rem 0.75rem; border-radius: 0.4rem;
    pointer-events: none;
  }
</style>
</head>
<body>
<div class="info">
  <strong>JARVIS Metaverse</strong> // __WORLD_ID__ — theme: __THEME__ — size: __SIZE__
</div>
<a-scene background="color: #000" fog="__FOG_DEF__" renderer="antialias: true; physicallyCorrectLights: true" __XR__>
  <a-assets>
    <!-- floor texture placeholder -->
  </a-assets>
  <a-entity light="type: ambient; color: __ACCENT__; intensity: __AMBIENT__"></a-entity>
  <a-entity light="type: directional; color: #ffffff; intensity: 0.8" position="-1 4 2"></a-entity>
  <a-sky color="__SKY_COLOR__"></a-sky>
  <a-plane position="0 0 0" rotation="-90 0 0" width="__FLOOR_SIZE__" height="__FLOOR_SIZE__" color="__FLOOR__"></a-plane>
__OBJECTS__
__AVATARS__
  <a-entity id="rig" movement-controls="speed: 0.15" position="0 1.6 4">
    <a-entity camera look-controls wasd-controls></a-entity>
  </a-entity>
</a-scene>
</body>
</html>
"""


def _render_world_html(world: _World) -> str:
    palette = _THEME_PALETTE[world.theme]
    radius = _SIZE_RADIUS[world.size]
    floor_size = max(8.0, radius * 2.2)

    sky_color = _sky_color(world.sky)
    fog_def = (
        f"type: linear; color: {sky_color}; near: {radius * 0.4:.1f}; far: {radius * 1.4:.1f}"
        if world.fog
        else "type: linear; color: #000000; near: 1000; far: 1001"
    )

    objects_html = "\n".join(_render_object(obj) for obj in world.objects.values()) or "  <!-- no objects -->"
    avatars_html = "\n".join(_aframe_avatar_entity(a.avatar_id, a.name, a.role) for a in world.avatars.values()) or "  <!-- no avatars -->"

    return (
        _BASE_TEMPLATE
        .replace("__WORLD_ID__", _escape(world.world_id))
        .replace("__THEME__", _escape(world.theme))
        .replace("__SIZE__", _escape(world.size))
        .replace("__AFRAME_SRC__", AFRAME_CDN)
        .replace("__AFRAME_EXTRAS__", AFRAME_EXTRAS_CDN)
        .replace("__AMBIENT__", f"{world.ambient_light:.3f}")
        .replace("__ACCENT__", palette["accent"])
        .replace("__FLOOR__", palette["floor"])
        .replace("__SKY_COLOR__", sky_color)
        .replace("__FLOOR_SIZE__", f"{floor_size:.1f}")
        .replace("__FOG_DEF__", fog_def)
        .replace("__OBJECTS__", objects_html)
        .replace("__AVATARS__", avatars_html)
        .replace("__XR__", "vr-mode-ui=\"enabled: true\"")
    )


def _sky_color(sky: str) -> str:
    return {
        "day":   "#7ec8ff",
        "night": "#0a0e1a",
        "dusk":  "#3c2548",
        "dawn":  "#ffaf7b",
        "void":  "#000000",
        "stars": "#020314",
    }.get(sky, "#0a0e1a")


def _render_object(obj: _Object) -> str:
    geom = {
        "cube":     ("a-box",      ""),
        "sphere":   ("a-sphere",   ""),
        "plane":    ("a-plane",    ""),
        "cylinder": ("a-cylinder", ""),
        "torus":    ("a-torus",    ""),
        "cone":     ("a-cone",     ""),
        "screen":   ("a-plane",    "width: 4; height: 2.25"),
        "portal":   ("a-torus",    "radius: 1.5; radius-tubular: 0.1"),
    }[obj.asset_type]
    tag, geom_attrs = geom

    color = _escape(str(obj.properties.get("color", "#39ffe1")))
    scale = float(obj.properties.get("scale", 1.0))
    px, py, pz = obj.position
    extra_attrs = ""
    if geom_attrs:
        extra_attrs = f" geometry=\"{_escape(geom_attrs)}\""
    label = obj.properties.get("label")
    label_html = ""
    if isinstance(label, str) and label.strip():
        label_html = (
            f"\n    <a-text value=\"{_escape(label)}\" position=\"0 1.2 0\" "
            f"align=\"center\" color=\"#ffffff\"></a-text>"
        )
    return (
        f"  <a-entity id=\"{_escape(obj.object_id)}\" "
        f"position=\"{px:.3f} {py:.3f} {pz:.3f}\" "
        f"scale=\"{scale:.3f} {scale:.3f} {scale:.3f}\">\n"
        f"    <{tag} color=\"{color}\"{extra_attrs}></{tag}>{label_html}\n"
        f"  </a-entity>"
    )


def _aframe_avatar_entity(avatar_id: str, name: str, role: str) -> str:
    role_palette = {
        "guide":     "#39ffe1",
        "guard":     "#ff5252",
        "merchant":  "#ffd166",
        "scientist": "#9bc4ff",
        "ally":      "#bae637",
        "narrator":  "#cfa8ff",
    }
    color = role_palette.get(role, "#cccccc")
    return (
        f"  <a-entity id=\"{_escape(avatar_id)}\" position=\"0 0 -2\">\n"
        f"    <a-cylinder color=\"{color}\" radius=\"0.35\" height=\"1.4\" position=\"0 0.7 0\"></a-cylinder>\n"
        f"    <a-sphere color=\"{color}\" radius=\"0.25\" position=\"0 1.55 0\"></a-sphere>\n"
        f"    <a-text value=\"{_escape(name)} ({_escape(role)})\" "
        f"align=\"center\" color=\"#ffffff\" position=\"0 2.0 0\" "
        f"width=\"6\"></a-text>\n"
        f"  </a-entity>"
    )


# ---------------------------------------------------------------------------
# Helpers (inlined math to avoid importing math twice)
# ---------------------------------------------------------------------------

def _math_cos(x: float) -> float:
    import math

    return math.cos(x)


def _math_sin(x: float) -> float:
    import math

    return math.sin(x)


def _coerce_vec3(value: Any) -> Tuple[float, float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError("position must be a 3-element list/tuple")
    try:
        return (float(value[0]), float(value[1]), float(value[2]))
    except (TypeError, ValueError) as exc:
        raise ValueError("position values must be numeric") from exc


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def get_metaverse_bridge(assets_dir: Optional[Path | str] = None) -> MetaverseBridge:
    """Return a fresh :class:`MetaverseBridge`."""
    return MetaverseBridge(assets_dir=assets_dir)


__all__ = [
    "MetaverseBridge",
    "get_metaverse_bridge",
    "VALID_THEMES",
    "VALID_SIZES",
    "VALID_SKIES",
    "VALID_ASSETS",
    "VALID_ROLES",
]
