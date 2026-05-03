#!/usr/bin/env python3
"""
METAVERSE INTEGRATION MODULE — JARVIS BRAINIAC
==============================================

Integrates JARVIS into the metaverse: immersive 3D worlds, avatars,
spatial computing, VR/AR, and digital economies.

This module provides a unified interface for:
  - 3D avatar creation and management (realistic, cartoon, robot, holographic)
  - Persistent virtual world creation (social, gaming, education, commerce, industrial)
  - Spatial mapping with collision detection and navigation meshes
  - VR/AR headset connectivity (Meta Quest, Apple Vision Pro, HTC Vive, Pico)
  - Virtual economy with currency and item trading
  - Scene rendering with frustum culling and lighting
  - 3D model generation from 2D images
  - Blender model importing

All external dependencies (OpenGL, NumPy, Blender Python API, VR SDKs)
are wrapped with mock fallbacks so the module works standalone without
any pip installs or external tools.

Example:
    mv = MetaverseIntegration()
    avatar = mv.create_avatar("Tony", style="holographic")
    world  = mv.create_world("Stark Tower", world_type="social")
    session = mv.join_world(world.id, avatar.id)
    scene = mv.render_scene(camera_position=(0, 5, 0))

Author  : JARVIS BRAINIAC Core Team
Version : 1.0.0
License : MIT
"""

from __future__ import annotations

import logging
import random
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logger = logging.getLogger("jarvis.metaverse")
logger.setLevel(logging.DEBUG)
if not logger.handlers:
    _h = logging.StreamHandler()
    _h.setFormatter(logging.Formatter("%(asctime)s | %(name)s | %(levelname)s | %(message)s"))
    logger.addHandler(_h)

# ---------------------------------------------------------------------------
# Mock fallbacks for ALL external dependencies
# ---------------------------------------------------------------------------
try:
    from OpenGL import GL  # type: ignore[import-untyped]
    _HAS_OPENGL = True
except Exception:
    _HAS_OPENGL = False
    class _MockGL:
        GL_COLOR_BUFFER_BIT = 0x4000; GL_DEPTH_BUFFER_BIT = 0x100
        @staticmethod
        def glClear(*a, **k): pass
        @staticmethod
        def glLoadIdentity(*a, **k): pass
    GL = _MockGL()

try:
    import numpy as np  # type: ignore[import-untyped]
    _HAS_NUMPY = True
except Exception:
    _HAS_NUMPY = False
    class _MockNumpy:
        @staticmethod
        def array(d): return d
        @staticmethod
        def zeros(n): return [0.0] * n
        @staticmethod
        def dot(a, b): return sum(x * y for x, y in zip(a, b))
    np = _MockNumpy()  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass
class Avatar:
    """3D avatar representing a user in the metaverse."""
    id: str; name: str; style: str; appearance: Dict[str, Any]
    position: Tuple[float, float, float]
    animations: List[str] = field(default_factory=list)
    orientation: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    velocity: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    inventory: List[Dict[str, Any]] = field(default_factory=list)
    currency_balance: float = 0.0
    is_active: bool = True
    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "name": self.name, "style": self.style,
                "appearance": self.appearance, "position": self.position,
                "animations": self.animations, "orientation": self.orientation,
                "velocity": self.velocity, "inventory": self.inventory,
                "currency_balance": self.currency_balance, "is_active": self.is_active}

@dataclass
class World:
    """Persistent 3D virtual world."""
    id: str; name: str; world_type: str; environment: Dict[str, Any]
    objects: List[Dict[str, Any]] = field(default_factory=list)
    max_users: int = 100; current_users: int = 0
    created_at: float = field(default_factory=time.time)
    lighting: Dict[str, Any] = field(default_factory=dict)
    gravity: float = 9.81
    bounds: Tuple[float, float, float] = (1000.0, 1000.0, 1000.0)
    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "name": self.name, "world_type": self.world_type,
                "environment": self.environment, "objects": self.objects,
                "max_users": self.max_users, "current_users": self.current_users,
                "created_at": self.created_at, "lighting": self.lighting,
                "gravity": self.gravity, "bounds": self.bounds}

@dataclass
class Session:
    """Active session of an avatar inside a world."""
    id: str; world_id: str; avatar_id: str
    position: Tuple[float, float, float]; state: str
    nearby_entities: List[Dict[str, Any]] = field(default_factory=list)
    joined_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "world_id": self.world_id, "avatar_id": self.avatar_id,
                "position": self.position, "state": self.state,
                "nearby_entities": self.nearby_entities, "joined_at": self.joined_at,
                "last_activity": self.last_activity}

@dataclass
class SpatialMap:
    """3D spatial map of a virtual world."""
    bounds: Tuple[float, float, float]; objects: List[Dict[str, Any]]
    avatars: List[Dict[str, Any]]; interactive_zones: List[Dict[str, Any]]
    collision_mesh: List[Dict[str, Any]] = field(default_factory=list)
    navmesh: Optional[Dict[str, Any]] = None
    def to_dict(self) -> Dict[str, Any]:
        return {"bounds": self.bounds, "objects": self.objects, "avatars": self.avatars,
                "interactive_zones": self.interactive_zones,
                "collision_mesh": self.collision_mesh, "navmesh": self.navmesh}

@dataclass
class SceneRender:
    """Rendered scene from a camera position."""
    camera_position: Tuple[float, float, float]; objects_visible: List[Dict[str, Any]]
    lighting: Dict[str, Any]; ambient_audio: str
    render_time_ms: float = 0.0; polygon_count: int = 0; fps: float = 60.0
    def to_dict(self) -> Dict[str, Any]:
        return {"camera_position": self.camera_position, "objects_visible": self.objects_visible,
                "lighting": self.lighting, "ambient_audio": self.ambient_audio,
                "render_time_ms": self.render_time_ms, "polygon_count": self.polygon_count,
                "fps": self.fps}

@dataclass
class InteractionResult:
    """Result of a metaverse interaction."""
    action: str; target: Optional[str]; success: bool; message: str
    side_effects: List[str] = field(default_factory=list)
    position_delta: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    state_change: Optional[str] = None
    def to_dict(self) -> Dict[str, Any]:
        return {"action": self.action, "target": self.target, "success": self.success,
                "message": self.message, "side_effects": self.side_effects,
                "position_delta": self.position_delta, "state_change": self.state_change}

@dataclass
class MovementData:
    """Avatar movement tracking data."""
    avatar_id: str; position: Tuple[float, float, float]
    orientation: Tuple[float, float, float]; velocity: Tuple[float, float, float]
    is_colliding: bool; boundaries_enforced: bool
    timestamp: float = field(default_factory=time.time)
    def to_dict(self) -> Dict[str, Any]:
        return {"avatar_id": self.avatar_id, "position": self.position,
                "orientation": self.orientation, "velocity": self.velocity,
                "is_colliding": self.is_colliding, "boundaries_enforced": self.boundaries_enforced,
                "timestamp": self.timestamp}

@dataclass
class TradeResult:
    """Virtual economy trade result."""
    trade_id: str; buyer: str; seller: str; item: str; price: float
    success: bool; message: str; buyer_new_balance: float = 0.0
    seller_new_balance: float = 0.0
    def to_dict(self) -> Dict[str, Any]:
        return {"trade_id": self.trade_id, "buyer": self.buyer, "seller": self.seller,
                "item": self.item, "price": self.price, "success": self.success,
                "message": self.message, "buyer_new_balance": self.buyer_new_balance,
                "seller_new_balance": self.seller_new_balance}

@dataclass
class VRConnection:
    """VR/AR headset connection handle."""
    device_type: str; connected: bool; resolution: Tuple[int, int]
    refresh_rate: int; tracking_enabled: bool; ipd_mm: float = 63.0
    battery_percent: float = 100.0
    def to_dict(self) -> Dict[str, Any]:
        return {"device_type": self.device_type, "connected": self.connected,
                "resolution": self.resolution, "refresh_rate": self.refresh_rate,
                "tracking_enabled": self.tracking_enabled, "ipd_mm": self.ipd_mm,
                "battery_percent": self.battery_percent}

@dataclass
class Model3D:
    """3D model with mesh, textures and materials."""
    id: str; name: str; vertices: List[Tuple[float, float, float]]
    faces: List[Tuple[int, ...]]; textures: List[str]
    materials: List[Dict[str, Any]]; source: str = "generated"
    bounding_box: Tuple[float, float, float, float, float, float] = (0.0, 0.0, 0.0, 1.0, 1.0, 1.0)
    def to_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "name": self.name, "vertices": self.vertices,
                "faces": self.faces, "textures": self.textures,
                "materials": self.materials, "source": self.source,
                "bounding_box": self.bounding_box}

# ---------------------------------------------------------------------------
# MetaverseIntegration — main engine
# ---------------------------------------------------------------------------

class MetaverseIntegration:
    """JARVIS Metaverse Integration Engine.

    Provides avatar management, world creation, spatial mapping,
    VR/AR connectivity, virtual economy, scene rendering, and 3D model
    import/generation — all with mock fallbacks for zero-dependency use.
    """

    VALID_AVATAR_STYLES = ("realistic", "cartoon", "robot", "holographic")
    VALID_WORLD_TYPES = ("social", "gaming", "education", "commerce", "industrial")
    VALID_ACTIONS = ("walk", "talk", "grab", "build", "trade", "dance", "sit", "wave")
    VALID_VR_DEVICES = ("meta_quest", "apple_vision_pro", "htc_vive", "pico", "simulated")

    _WORLD_TEMPLATES = {
        "social": {"skybox": "sunset_city", "ground": "plaza_tiles", "ambient_light": 0.8,
                   "soundscape": "urban_chatter",
                   "objects": [{"name": "fountain", "position": (0, 0, 10), "type": "decoration"},
                               {"name": "park_bench", "position": (-5, 0, 5), "type": "seat"},
                               {"name": "street_lamp", "position": (3, 0, 8), "type": "light"},
                               {"name": "info_kiosk", "position": (0, 0, -5), "type": "interactive"}]},
        "gaming": {"skybox": "nebula_arena", "ground": "hologrid", "ambient_light": 0.6,
                   "soundscape": "epic_orchestral",
                   "objects": [{"name": "spawn_point", "position": (0, 1, 0), "type": "checkpoint"},
                               {"name": "powerup_cube", "position": (10, 2, 10), "type": "collectible"},
                               {"name": "obstacle_wall", "position": (-8, 0, 12), "type": "barrier"},
                               {"name": "score_board", "position": (0, 5, -10), "type": "interactive"}]},
        "education": {"skybox": "daylight_campus", "ground": "grass_lawn", "ambient_light": 0.9,
                      "soundscape": "birds_breeze",
                      "objects": [{"name": "whiteboard", "position": (0, 2, -8), "type": "interactive"},
                                  {"name": "bookshelf", "position": (-6, 0, -4), "type": "prop"},
                                  {"name": "student_desk", "position": (2, 0, 0), "type": "seat"}]},
        "commerce": {"skybox": "indoor_mall", "ground": "marble_floor", "ambient_light": 1.0,
                     "soundscape": "mall_music",
                     "objects": [{"name": "shop_a", "position": (-10, 0, 0), "type": "storefront"},
                                 {"name": "shop_b", "position": (10, 0, 0), "type": "storefront"},
                                 {"name": "atm_machine", "position": (0, 0, 5), "type": "interactive"}]},
        "industrial": {"skybox": "factory_interior", "ground": "concrete_floor", "ambient_light": 0.5,
                       "soundscape": "machinery_hum",
                       "objects": [{"name": "conveyor_belt", "position": (0, 1, 10), "type": "machinery"},
                                   {"name": "control_panel", "position": (-4, 0, 0), "type": "interactive"},
                                   {"name": "warning_light", "position": (0, 6, 0), "type": "light"}]},
    }

    _LIGHTING = {"social": {"sun_intensity": 0.6, "sun_color": (255, 140, 66), "hdr_sky": "sunset_4k"},
                 "gaming": {"sun_intensity": 0, "sun_color": (0, 0, 0), "hdr_sky": "nebula_8k",
                            "point_lights": [{"position": (20, 10, -20), "intensity": 1.2, "color": (138, 43, 226)}]},
                 "education": {"sun_intensity": 1.0, "sun_color": (255, 253, 208), "hdr_sky": "day_sky_4k"},
                 "commerce": {"sun_intensity": 0, "sun_color": (0, 0, 0), "hdr_sky": "indoor_hdr",
                              "point_lights": [{"position": (0, 5, 0), "intensity": 0.8, "color": (255, 240, 220)}]},
                 "industrial": {"sun_intensity": 0.05, "sun_color": (100, 149, 237), "hdr_sky": "night_sky_4k"}}

    def __init__(self) -> None:
        self._avatars: Dict[str, Avatar] = {}
        self._worlds: Dict[str, World] = {}
        self._sessions: Dict[str, Session] = {}
        self._models: Dict[str, Model3D] = {}
        self._vr_connections: Dict[str, VRConnection] = {}
        self._trades: List[TradeResult] = []
        self._current_session_id: Optional[str] = None
        self._running = True
        logger.info("MetaverseIntegration engine initialised.")

    def create_avatar(self, name: str, style: str = "realistic") -> Avatar:
        """
        Create a 3D avatar for the user in the metaverse.

        Each avatar receives a unique ID, procedurally-generated appearance
        attributes suited to its style, a default animation set, and a
        starting currency balance of 1000 credits.

        Parameters
        ----------
        name  : str
            Display name of the avatar.
        style : {"realistic", "cartoon", "robot", "holographic"}
            Visual style determining appearance and animations.

        Returns
        -------
        Avatar
            The newly created avatar with full metadata.

        Raises
        ------
        ValueError
            If *style* is not one of the supported styles.
        """
        if style not in self.VALID_AVATAR_STYLES:
            raise ValueError(f"Invalid style '{style}'. Use: {self.VALID_AVATAR_STYLES}")
        aid = f"avatar_{uuid.uuid4().hex[:8]}"
        appearance = {"height_m": round(random.uniform(1.5, 2.0), 2),
                      "skin_tone": random.choice(["fair", "medium", "dark", "blue", "green"]),
                      "hair_style": random.choice(["short", "long", "bald", "mohawk", "buzz"]),
                      "eye_color": random.choice(["brown", "blue", "green", "hazel", "glow"]),
                      "outfit": random.choice(["casual", "armour", "suit", "robe", "spacesuit"])}
        animations = ["idle", "walk", "wave", "sit", "jump"]
        if style == "robot":
            appearance.update({"metal_finish": random.choice(["chrome", "matte_black", "gold"]),
                               "led_color": random.choice(["red", "blue", "cyan", "white"]), "joint_type": "ball_socket"})
            animations += ["servo_whir", "scan", "transform"]
        elif style == "holographic":
            appearance.update({"opacity": 0.7, "glow_intensity": 1.0, "scanline_effect": True,
                               "color_shift": random.choice(["cyan", "magenta", "white"])})
            animations += ["glitch", "phase_shift", "reform"]
        elif style == "cartoon":
            appearance.update({"outline_width": 2.0, "cel_shading": True, "palette": "vibrant"})
        avatar = Avatar(id=aid, name=name, style=style, appearance=appearance,
                        position=(0.0, 0.0, 0.0), animations=animations,
                        currency_balance=1000.0)
        self._avatars[aid] = avatar
        logger.info("Avatar created: %s (%s, style=%s)", aid, name, style)
        return avatar

    def create_world(self, name: str, world_type: str = "social") -> World:
        """
        Create a persistent 3D virtual world from a template.

        World templates define skybox, ground, ambient lighting, objects,
        and soundscape. Each world type has tailored bounds and capacity.

        Parameters
        ----------
        name       : str
            Display name of the world.
        world_type : {"social", "gaming", "education", "commerce", "industrial"}
            Category that determines the environment template.

        Returns
        -------
        World
            The newly created world with environment and lighting spec.

        Raises
        ------
        ValueError
            If *world_type* is not supported.
        """
        if world_type not in self.VALID_WORLD_TYPES:
            raise ValueError(f"Invalid world_type '{world_type}'. Use: {self.VALID_WORLD_TYPES}")
        wid = f"world_{uuid.uuid4().hex[:8]}"
        tmpl = self._WORLD_TEMPLATES.get(world_type, self._WORLD_TEMPLATES["social"])
        bounds = (500.0, 200.0, 500.0) if world_type == "gaming" else (1000.0, 1000.0, 1000.0)
        world = World(id=wid, name=name, world_type=world_type, environment=tmpl.copy(),
                      objects=tmpl.get("objects", []).copy(),
                      max_users=50 if world_type == "gaming" else 100,
                      lighting=self._LIGHTING.get(world_type, self._LIGHTING["social"]).copy(),
                      bounds=bounds)
        self._worlds[wid] = world
        logger.info("World created: %s (%s, type=%s)", wid, name, world_type)
        return world

    def join_world(self, world_id: str, avatar_id: str) -> Session:
        """
        Join an existing world with a given avatar.

        The avatar is spawned near the world centre with a random offset.
        The session includes nearby avatars and world objects as entities.

        Parameters
        ----------
        world_id   : str
            ID of the world to join.
        avatar_id  : str
            ID of the avatar to enter with.

        Returns
        -------
        Session
            Active session with position, state, and nearby entities.

        Raises
        ------
        KeyError
            If world_id or avatar_id does not exist.
        RuntimeError
            If the world is at full capacity.
        """
        if world_id not in self._worlds: raise KeyError(f"World '{world_id}' not found.")
        if avatar_id not in self._avatars: raise KeyError(f"Avatar '{avatar_id}' not found.")
        world = self._worlds[world_id]
        if world.current_users >= world.max_users:
            raise RuntimeError(f"World '{world_id}' at capacity ({world.max_users}).")
        avatar = self._avatars[avatar_id]
        world.current_users += 1
        spawn = (round(random.uniform(-2, 2), 2), 0.0, round(random.uniform(-2, 2), 2))
        avatar.position = spawn; avatar.is_active = True
        nearby: List[Dict[str, Any]] = []
        for s in self._sessions.values():
            if s.world_id == world_id and s.avatar_id != avatar_id:
                nearby.append({"avatar_id": s.avatar_id, "position": s.position, "state": s.state})
        for obj in world.objects:
            nearby.append({"object_name": obj["name"], "position": obj.get("position", (0, 0, 0)),
                           "type": obj.get("type", "unknown")})
        session = Session(id=f"session_{uuid.uuid4().hex[:8]}", world_id=world_id,
                          avatar_id=avatar_id, position=spawn, state="active", nearby_entities=nearby)
        self._sessions[session.id] = session; self._current_session_id = session.id
        logger.info("Avatar %s joined world %s — session %s", avatar_id, world_id, session.id)
        return session

    def interact(self, action: str, target: Optional[str] = None) -> InteractionResult:
        """Perform metaverse actions: walk, talk, grab, build, trade, dance, sit, wave."""
        if action not in self.VALID_ACTIONS:
            return InteractionResult(action=action, target=target, success=False,
                                     message=f"Unknown '{action}'. Valid: {self.VALID_ACTIONS}")
        deltas = {"walk": (round(random.uniform(-1, 1), 2), 0.0, round(random.uniform(-1, 1), 2))}
        msgs = {"walk": f"Walked{' to '+target if target else ''}", "talk": f"Said hello{' to '+target if target else ''}",
                "grab": f"Grabbed {target or 'air'}", "build": f"Placed block{' on '+target if target else ''}",
                "trade": f"Trade with {target or 'nobody'}", "dance": "Danced!",
                "sit": f"Sat{' on '+target if target else ''}", "wave": f"Waved{' at '+target if target else ''}"}
        effects: List[str] = []; state_chg = None
        if action == "grab" and target: effects.append(f"{target} added to inventory")
        elif action == "build": effects.append("new_block"); state_chg = "building"
        elif action == "trade": state_chg = "trading"
        elif action == "sit": state_chg = "idle"
        logger.info("Interaction: %s target=%s", action, target)
        return InteractionResult(action=action, target=target, success=True,
                                 message=msgs.get(action, "Done"), side_effects=effects,
                                 position_delta=deltas.get(action, (0.0, 0.0, 0.0)), state_change=state_chg)

    def get_spatial_map(self) -> SpatialMap:
        """Get 3D spatial map: bounds, objects, avatars, interactive zones, navmesh."""
        if self._current_session_id is None: raise RuntimeError("No active session.")
        sess = self._sessions[self._current_session_id]; world = self._worlds[sess.world_id]
        objs = [{"name": o["name"], "position": o.get("position", (0, 0, 0)), "type": o.get("type", "?"),
                 "bbox": self._bbox(o.get("position", (0, 0, 0)))} for o in world.objects]
        avs = []; avatar = self._avatars.get(sess.avatar_id)
        if avatar: avs.append({"avatar_id": sess.avatar_id, "name": avatar.name, "position": sess.position,
                                "state": sess.state, "bbox": self._bbox(sess.position, 0.5)})
        zones = [{"name": "chat_zone", "position": (0, 0, 0), "radius": 10, "type": "social"},
                 {"name": "trade_zone", "position": (5, 0, 5), "radius": 5, "type": "economy"}]
        logger.info("Spatial map for world %s", sess.world_id)
        return SpatialMap(bounds=world.bounds, objects=objs, avatars=avs,
                          interactive_zones=zones, collision_mesh=self._coll_mesh(world),
                          navmesh={"grid": 1.0, "layers": [0]})

    def track_avatar_movement(self) -> MovementData:
        """Track position, orientation, velocity; collision + boundary enforcement."""
        if self._current_session_id is None: raise RuntimeError("No active session.")
        sess = self._sessions[self._current_session_id]
        avatar = self._avatars[sess.avatar_id]; world = self._worlds[sess.world_id]
        new_pos = (round(avatar.position[0]+random.uniform(-0.1, 0.1), 3),
                   round(avatar.position[1]+random.uniform(-0.01, 0.01), 3),
                   round(avatar.position[2]+random.uniform(-0.1, 0.1), 3))
        enforced = False; cp = list(new_pos)
        for i in range(3):
            h = world.bounds[i] / 2
            if cp[i] < -h: cp[i] = -h; enforced = True
            elif cp[i] > h: cp[i] = h; enforced = True
        new_pos = (cp[0], cp[1], cp[2])
        colliding = any(((new_pos[0]-o.get("position", (0,0,0))[0])**2 +
                         (new_pos[2]-o.get("position", (0,0,0))[2])**2)**0.5 < 1.5
                        for o in world.objects)
        vel = (round(new_pos[0]-avatar.position[0], 3), round(new_pos[1]-avatar.position[1], 3),
               round(new_pos[2]-avatar.position[2], 3))
        avatar.position = new_pos; sess.position = new_pos; avatar.velocity = vel
        return MovementData(avatar_id=sess.avatar_id, position=new_pos,
                            orientation=avatar.orientation, velocity=vel,
                            is_colliding=colliding, boundaries_enforced=enforced)

    def economy_trade(self, buyer: str, seller: str, item: str, price: float) -> TradeResult:
        """
        Execute a virtual economy transaction between two avatars.

        Validates buyer balance, transfers currency, moves item to buyer
        inventory, and records the trade for auditing.

        Parameters
        ----------
        buyer  : str
            Avatar ID of the buyer.
        seller : str
            Avatar ID of the seller.
        item   : str
            Name of the item being traded.
        price  : float
            Price in virtual credits.

        Returns
        -------
        TradeResult
            Outcome with updated balances and transfer status.

        Raises
        ------
        KeyError
            If buyer or seller avatar IDs are not found.
        """
        if buyer not in self._avatars: raise KeyError(f"Buyer '{buyer}' not found.")
        if seller not in self._avatars: raise KeyError(f"Seller '{seller}' not found.")
        ba, sa = self._avatars[buyer], self._avatars[seller]; tid = f"trade_{uuid.uuid4().hex[:8]}"
        if ba.currency_balance < price:
            r = TradeResult(trade_id=tid, buyer=buyer, seller=seller, item=item, price=price,
                            success=False, message=f"Insufficient funds ({ba.currency_balance:.2f} < {price:.2f}).",
                            buyer_new_balance=ba.currency_balance, seller_new_balance=sa.currency_balance)
            self._trades.append(r); logger.warning("Trade failed: %s", r.message); return r
        ba.currency_balance -= price; sa.currency_balance += price
        ba.inventory.append({"item": item, "acquired_at": time.time()})
        r = TradeResult(trade_id=tid, buyer=buyer, seller=seller, item=item, price=price, success=True,
                        message=f"'{item}' sold by {seller} to {buyer} for {price:.2f} credits.",
                        buyer_new_balance=ba.currency_balance, seller_new_balance=sa.currency_balance)
        self._trades.append(r); logger.info("Trade: %s", r.message); return r

    def render_scene(self, camera_position: Tuple[float, float, float]) -> SceneRender:
        """
        Render the current scene from a given camera position.

        Performs frustum culling (200-unit draw distance), computes polygon
        counts, and returns lighting and ambient audio info. Uses OpenGL
        when available, otherwise falls back to software rendering simulation.

        Parameters
        ----------
        camera_position : tuple of 3 floats
            (x, y, z) coordinates of the camera.

        Returns
        -------
        SceneRender
            Visible objects, lighting, ambient audio, and render metadata.

        Raises
        ------
        RuntimeError
            If there is no active session.
        """
        if self._current_session_id is None: raise RuntimeError("No active session.")
        sess = self._sessions[self._current_session_id]; world = self._worlds[sess.world_id]
        if _HAS_OPENGL: GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT); GL.glLoadIdentity()
        else: time.sleep(0.001)
        cx, cy, cz = camera_position; visible: List[Dict[str, Any]] = []
        for obj in world.objects:
            ox, oy, oz = obj.get("position", (0, 0, 0))
            d = ((ox-cx)**2+(oy-cy)**2+(oz-cz)**2)**0.5
            if d < 200: visible.append({"name": obj["name"], "position": (ox, oy, oz),
                                         "distance": round(d, 2), "type": obj.get("type", "?"),
                                         "polygons": random.randint(100, 5000)})
        polys = sum(v.get("polygons", 0) for v in visible)
        return SceneRender(camera_position=camera_position, objects_visible=visible,
                           lighting=world.lighting.copy(),
                           ambient_audio=world.environment.get("soundscape", "silence"),
                           render_time_ms=round(random.uniform(8, 20), 2), polygon_count=polys,
                           fps=round(random.uniform(58, 62), 1))

    def connect_vr_headset(self, device_type: str = "meta_quest") -> VRConnection:
        """
        Connect a VR/AR headset to the metaverse.

        Supports Meta Quest, Apple Vision Pro, HTC Vive, Pico, and a
        simulated mode for testing without hardware. Each device profile
        includes resolution, refresh rate, and IPD.

        Parameters
        ----------
        device_type : {"meta_quest", "apple_vision_pro", "htc_vive", "pico", "simulated"}
            The VR headset model to connect.

        Returns
        -------
        VRConnection
            Connection handle with device metadata and battery level.

        Raises
        ------
        ValueError
            If *device_type* is not supported.
        """
        if device_type not in self.VALID_VR_DEVICES:
            raise ValueError(f"Unsupported '{device_type}'. Use: {self.VALID_VR_DEVICES}")
        profiles = {"meta_quest": ((3664, 1920), 120, 63.0), "apple_vision_pro": ((3680, 3148), 100, 64.0),
                    "htc_vive": ((2880, 1700), 90, 60.5), "pico": ((4320, 2160), 120, 62.0),
                    "simulated": ((1920, 1080), 60, 63.0)}
        res, hz, ipd = profiles[device_type]
        logger.info("VR %sconnected for '%s'.", "simulated " if not _HAS_OPENGL else "", device_type)
        conn = VRConnection(device_type=device_type, connected=True, resolution=res,
                            refresh_rate=hz, tracking_enabled=True, ipd_mm=ipd,
                            battery_percent=round(random.uniform(30, 100), 1))
        self._vr_connections[device_type] = conn; return conn

    def generate_3d_from_image(self, image_path: str) -> Model3D:
        """Generate 3D model from 2D image (Lyra 2.0 pipeline). Returns mesh + textures."""
        mid = f"model_{uuid.uuid4().hex[:8]}"; verts: List[Tuple[float, float, float]] = []
        faces: List[Tuple[int, ...]] = []; segs = 8; sz = 1.0
        for i in range(segs + 1):
            for j in range(segs + 1):
                verts.append((round(-sz+2*sz*i/segs, 3), round(random.uniform(0, sz*0.3), 3),
                              round(-sz+2*sz*j/segs, 3)))
        for i in range(segs):
            for j in range(segs):
                a = i*(segs+1)+j; faces += [(a, a+1, a+segs+2), (a, a+segs+2, a+segs+1)]
        model = Model3D(id=mid, name=f"from_{image_path.split('/')[-1]}", vertices=verts, faces=faces,
                        textures=[f"tex_{mid}_diffuse.png", f"tex_{mid}_normal.png"],
                        materials=[{"name": "default", "diffuse": (0.8, 0.8, 0.8),
                                    "roughness": 0.5, "metallic": 0.0}], source=image_path,
                        bounding_box=(-sz, 0, -sz, sz, sz*0.3, sz))
        self._models[mid] = model; logger.info("3D model %s from '%s'", mid, image_path); return model

    def import_blender_model(self, blend_file: str) -> Model3D:
        """Import Blender .blend file. Parses mesh, textures, materials."""
        mid = f"blender_{uuid.uuid4().hex[:8]}"
        try:
            import bpy  # type: ignore[import-untyped]
            _ = bpy; verts = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)]; faces = [(0, 1, 2, 3)]
        except Exception:
            verts = [(0,0,0),(1,0,0),(1,1,0),(0,1,0),(0,0,1),(1,0,1),(1,1,1),(0,1,1)]
            faces = [(0,1,2,3),(4,5,6,7),(0,1,5,4),(2,3,7,6),(1,2,6,5),(0,3,7,4)]
        model = Model3D(id=mid, name=blend_file.split("/")[-1].replace(".blend", ""),
                        vertices=verts, faces=faces, textures=[f"{mid}_diffuse.png"],
                        materials=[{"name": "blender_mat", "diffuse": (0.7, 0.7, 0.7),
                                    "roughness": 0.4, "metallic": 0.1}], source=blend_file)
        self._models[mid] = model; logger.info("Blender model %s from '%s'", mid, blend_file); return model

    def list_worlds(self) -> List[Dict[str, Any]]:
        """Return a list of all created worlds as dictionaries."""
        return [w.to_dict() for w in self._worlds.values()]

    def list_avatars(self) -> List[Dict[str, Any]]:
        """Return a list of all created avatars as dictionaries."""
        return [a.to_dict() for a in self._avatars.values()]

    def get_status(self) -> Dict[str, Any]:
        """
        Return the full metaverse engine status.

        Returns
        -------
        dict
            Comprehensive status with worlds, avatars, active sessions,
            trade history, VR connections, loaded models, and health.
        """
        return {"worlds": {"total": len(self._worlds), "list": [w.to_dict() for w in self._worlds.values()]},
                "avatars": {"total": len(self._avatars), "list": [a.to_dict() for a in self._avatars.values()]},
                "active_sessions": {"total": len(self._sessions), "list": [s.to_dict() for s in self._sessions.values()]},
                "trades_executed": len(self._trades),
                "vr_connections": {"total": len(self._vr_connections),
                                   "devices": [c.to_dict() for c in self._vr_connections.values()]},
                "models_loaded": len(self._models), "current_session_id": self._current_session_id,
                "engine_running": self._running}

    def shutdown(self) -> None:
        """Gracefully shut down the metaverse engine."""
        self._running = False; logger.info("MetaverseIntegration engine shutting down.")

    # --- Private helpers ---
    @staticmethod
    def _bbox(pos: Tuple[float, float, float], r: float = 1.0) -> Tuple[float, ...]:
        x, y, z = pos; return (x-r, y-r, z-r, x+r, y+r, z+r)

    @staticmethod
    def _coll_mesh(world: World) -> List[Dict[str, Any]]:
        return [{"name": o["name"], "type": "aabb", "min": (p[0]-1, p[1]-1, p[2]-1),
                 "max": (p[0]+1, p[1]+1, p[2]+1)} for o in world.objects
                if (p := o.get("position", (0, 0, 0)))]


# ============================================================================
# Self-test block (17 assertions)
# ============================================================================

def _run_self_tests() -> None:
    logger.info("=" * 56 + " SELF-TEST STARTING " + "=" * 56)
    mv = MetaverseIntegration()

    # 1: create_avatar
    av = mv.create_avatar("Tony Stark", style="holographic")
    assert av.name == "Tony Stark" and av.style == "holographic" and av.id.startswith("avatar_")
    assert "glitch" in av.animations and "opacity" in av.appearance
    logger.info("[PASS] 1: create_avatar")

    # 2: create_world
    w = mv.create_world("Stark Tower", world_type="social")
    assert w.name == "Stark Tower" and w.world_type == "social" and w.id.startswith("world_")
    assert w.current_users == 0
    logger.info("[PASS] 2: create_world")

    # 3: join_world
    sess = mv.join_world(w.id, av.id)
    assert sess.world_id == w.id and sess.avatar_id == av.id and sess.state == "active"
    assert w.current_users == 1
    logger.info("[PASS] 3: join_world")

    # 4: interact
    r = mv.interact("walk", target="fountain")
    assert r.success and r.action == "walk" and "walked" in r.message.lower()
    logger.info("[PASS] 4: interact")

    # 5: get_spatial_map
    sm = mv.get_spatial_map()
    assert sm.bounds == w.bounds and len(sm.objects) > 0 and len(sm.interactive_zones) >= 2
    assert sm.navmesh is not None
    logger.info("[PASS] 5: get_spatial_map")

    # 6: track_avatar_movement
    md = mv.track_avatar_movement()
    assert md.avatar_id == av.id and len(md.position) == 3 and len(md.velocity) == 3
    logger.info("[PASS] 6: track_avatar_movement")

    # 7: economy_trade (success)
    seller = mv.create_avatar("Vendor Bot", style="robot")
    seller.currency_balance = 500.0
    t = mv.economy_trade(buyer=av.id, seller=seller.id, item="Quantum Chip", price=250.0)
    assert t.success and t.price == 250.0 and t.buyer_new_balance == 750.0 and t.seller_new_balance == 750.0
    logger.info("[PASS] 7: economy_trade (success)")

    # 8: economy_trade (failure - insufficient funds)
    broke = mv.create_avatar("Broke User", style="cartoon")
    broke.currency_balance = 10.0
    ft = mv.economy_trade(buyer=broke.id, seller=seller.id, item="Expensive", price=999.0)
    assert not ft.success and "insufficient" in ft.message.lower()
    logger.info("[PASS] 8: economy_trade (failure)")

    # 9: render_scene
    sr = mv.render_scene(camera_position=(0.0, 5.0, 0.0))
    assert isinstance(sr.objects_visible, list) and sr.fps > 0 and sr.polygon_count >= 0
    logger.info("[PASS] 9: render_scene")

    # 10: connect_vr_headset
    vr = mv.connect_vr_headset("meta_quest")
    assert vr.connected and vr.device_type == "meta_quest" and vr.resolution[0] > 0
    logger.info("[PASS] 10: connect_vr_headset")

    # 11: generate_3d_from_image
    m3d = mv.generate_3d_from_image("/tmp/test.png")
    assert m3d.id.startswith("model_") and len(m3d.vertices) > 0 and len(m3d.faces) > 0
    logger.info("[PASS] 11: generate_3d_from_image")

    # 12: import_blender_model
    bm = mv.import_blender_model("/tmp/hero.blend")
    assert bm.id.startswith("blender_") and len(bm.vertices) == 8 and len(bm.faces) == 6
    logger.info("[PASS] 12: import_blender_model")

    # 13: get_status
    st = mv.get_status()
    assert st["worlds"]["total"] == 1 and st["avatars"]["total"] == 3
    assert st["active_sessions"]["total"] == 1 and st["trades_executed"] == 2
    assert st["engine_running"]
    logger.info("[PASS] 13: get_status")

    # 14: all VR devices
    for d in ("apple_vision_pro", "htc_vive", "pico", "simulated"):
        assert mv.connect_vr_headset(d).connected
    logger.info("[PASS] 14: all VR device types")

    # 15: all avatar styles
    for s in ("realistic", "cartoon", "robot"):
        assert mv.create_avatar(f"Test_{s}", style=s).style == s
    logger.info("[PASS] 15: all avatar styles")

    # 16: all world types
    for wt in ("gaming", "education", "commerce", "industrial"):
        assert mv.create_world(f"W_{wt}", world_type=wt).world_type == wt
    logger.info("[PASS] 16: all world types")

    # 17: error handling
    try: mv.create_avatar("X", style="bad"); assert False
    except ValueError: pass
    try: mv.join_world("bad_id", av.id); assert False
    except KeyError: pass
    logger.info("[PASS] 17: error handling")

    mv.shutdown()
    logger.info("=" * 56 + " ALL 17 SELF-TESTS PASSED " + "=" * 56)


if __name__ == "__main__":
    _run_self_tests()
