"""CubeSandbox 3D Physics Bridge.

Build interactive browser-based 3D physics scenes (Three.js + cannon-es)
and a Python-side rigid-body simulator for headless / scripted use.

Public API
----------
CubeSandboxBridge
    create_scene(objects)                       -> {'scene_id', 'html_path'}
    add_object(scene_id, type, position, ...)   -> object_id
    apply_force(scene_id, object_id, force)     -> dict
    simulate_physics(scene_id, steps, dt)       -> list[dict]   (final state)
    get_state(scene_id)                         -> dict          (full state)
    invoke(action, **kwargs)                    -> Any
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any, Sequence


_DEFAULT_ASSET_DIR = Path("assets") / "scenes"
_GRAVITY = (0.0, -9.81, 0.0)
_FLOOR_Y = 0.0
_RESTITUTION = 0.35  # bounce coefficient
_FRICTION = 0.92     # tangential damping per second of contact


# ---------------------------------------------------------------------------
# Internal scene model — minimal physics for headless simulation.
# ---------------------------------------------------------------------------
def _vec3(v: Sequence[float] | None, default: tuple[float, float, float]) -> list[float]:
    if v is None:
        return list(default)
    if len(v) != 3:
        raise ValueError("vector must have 3 components")
    return [float(v[0]), float(v[1]), float(v[2])]


def _step_object(obj: dict[str, Any], dt: float) -> None:
    """Advance one rigid body by dt with gravity + simple floor collision."""
    if obj.get("static"):
        return
    pos = obj["position"]
    vel = obj["velocity"]
    # Apply gravity (acceleration on velocity).
    vel[0] += _GRAVITY[0] * dt
    vel[1] += _GRAVITY[1] * dt
    vel[2] += _GRAVITY[2] * dt
    # Integrate position.
    pos[0] += vel[0] * dt
    pos[1] += vel[1] * dt
    pos[2] += vel[2] * dt
    # Floor collision against y = _FLOOR_Y, accounting for object extent.
    radius = obj.get("radius", 0.5)
    floor_contact = _FLOOR_Y + radius
    if pos[1] < floor_contact:
        pos[1] = floor_contact
        if vel[1] < 0:
            vel[1] = -vel[1] * _RESTITUTION
        # Ground friction on horizontal velocity.
        damp = _FRICTION ** max(dt, 1e-6)
        vel[0] *= damp
        vel[2] *= damp


class CubeSandboxBridge:
    """3D physics sandbox — headless sim + browser-renderable HTML."""

    def __init__(self, asset_dir: str | Path | None = None) -> None:
        self.asset_dir = Path(asset_dir) if asset_dir else _DEFAULT_ASSET_DIR
        self._scenes: dict[str, dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # Scene lifecycle
    # ------------------------------------------------------------------
    def create_scene(
        self,
        objects: list[dict[str, Any]] | None = None,
        scene_id: str | None = None,
        output_path: str | Path | None = None,
    ) -> dict[str, Any]:
        """Create a scene and write its interactive HTML viewer.

        Returns ``{'scene_id', 'html_path', 'object_ids'}``.
        """
        sid = scene_id or f"scene_{uuid.uuid4().hex[:8]}"
        scene = {
            "id": sid,
            "objects": {},
            "created": time.time(),
            "step_count": 0,
        }
        self._scenes[sid] = scene

        object_ids: list[str] = []
        for spec in (objects or []):
            oid = self.add_object(
                sid,
                type=spec.get("type", "box"),
                position=spec.get("position", (0, 1, 0)),
                mass=spec.get("mass", 1.0),
                color=spec.get("color", "#00ff88"),
                size=spec.get("size", 1.0),
                static=spec.get("static", False),
                velocity=spec.get("velocity"),
            )
            object_ids.append(oid)

        out = Path(output_path) if output_path else self._html_path(sid)
        self._write_scene_html(sid, out)
        return {"scene_id": sid, "html_path": out, "object_ids": object_ids}

    def _html_path(self, scene_id: str) -> Path:
        self.asset_dir.mkdir(parents=True, exist_ok=True)
        return self.asset_dir / f"{scene_id}.html"

    # ------------------------------------------------------------------
    # Object lifecycle
    # ------------------------------------------------------------------
    def add_object(
        self,
        scene_id: str,
        type: str = "box",
        position: Sequence[float] = (0.0, 1.0, 0.0),
        mass: float = 1.0,
        color: str = "#00ff88",
        size: float = 1.0,
        static: bool = False,
        velocity: Sequence[float] | None = None,
    ) -> str:
        scene = self._require_scene(scene_id)
        if type not in ("box", "sphere", "cylinder"):
            raise ValueError(
                f"unknown type {type!r}; choose box, sphere, cylinder"
            )
        oid = f"obj_{uuid.uuid4().hex[:8]}"
        radius = size / 2.0
        scene["objects"][oid] = {
            "id": oid,
            "type": type,
            "position": _vec3(position, (0.0, 1.0, 0.0)),
            "velocity": _vec3(velocity, (0.0, 0.0, 0.0)),
            "mass": float(mass),
            "color": color,
            "size": float(size),
            "radius": radius,
            "static": bool(static),
        }
        return oid

    def apply_force(
        self,
        scene_id: str,
        object_id: str,
        force_vector: Sequence[float],
    ) -> dict[str, Any]:
        """Apply an instantaneous force (impulse-style: F * 1s / mass)."""
        scene = self._require_scene(scene_id)
        obj = scene["objects"].get(object_id)
        if obj is None:
            raise KeyError(f"object {object_id!r} not found")
        if obj.get("static"):
            raise ValueError(f"cannot apply force to static object {object_id!r}")
        f = _vec3(force_vector, (0.0, 0.0, 0.0))
        m = max(obj["mass"], 1e-6)
        obj["velocity"][0] += f[0] / m
        obj["velocity"][1] += f[1] / m
        obj["velocity"][2] += f[2] / m
        return dict(obj)

    # ------------------------------------------------------------------
    # Simulation
    # ------------------------------------------------------------------
    def simulate_physics(
        self,
        scene_id: str,
        steps: int = 100,
        dt: float = 0.016,
    ) -> list[dict[str, Any]]:
        """Step the physics simulation; return final positions/velocities."""
        if steps < 0:
            raise ValueError("steps must be >= 0")
        if dt <= 0:
            raise ValueError("dt must be > 0")
        scene = self._require_scene(scene_id)
        for _ in range(steps):
            for obj in scene["objects"].values():
                _step_object(obj, dt)
            scene["step_count"] += 1
        return [
            {
                "id": o["id"],
                "type": o["type"],
                "position": list(o["position"]),
                "velocity": list(o["velocity"]),
            }
            for o in scene["objects"].values()
        ]

    def get_state(self, scene_id: str) -> dict[str, Any]:
        scene = self._require_scene(scene_id)
        return {
            "scene_id": scene_id,
            "step_count": scene["step_count"],
            "objects": [
                {
                    "id": o["id"],
                    "type": o["type"],
                    "position": list(o["position"]),
                    "velocity": list(o["velocity"]),
                    "mass": o["mass"],
                    "color": o["color"],
                    "size": o["size"],
                    "static": o["static"],
                }
                for o in scene["objects"].values()
            ],
        }

    # ------------------------------------------------------------------
    # HTML render
    # ------------------------------------------------------------------
    def _write_scene_html(self, scene_id: str, out: Path) -> None:
        out.parent.mkdir(parents=True, exist_ok=True)
        scene = self._require_scene(scene_id)
        objects = list(scene["objects"].values())
        html = _SCENE_HTML_TEMPLATE.format(
            scene_id=scene_id,
            objects_json=json.dumps(objects),
        )
        out.write_text(html, encoding="utf-8")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _require_scene(self, scene_id: str) -> dict[str, Any]:
        scene = self._scenes.get(scene_id)
        if scene is None:
            raise KeyError(f"scene {scene_id!r} not found")
        return scene

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------
    def invoke(self, action: str, **kwargs: Any) -> Any:
        actions = {
            "create_scene": self.create_scene,
            "add_object": self.add_object,
            "apply_force": self.apply_force,
            "simulate_physics": self.simulate_physics,
            "get_state": self.get_state,
        }
        fn = actions.get(action)
        if fn is None:
            raise ValueError(
                f"unknown action {action!r}; choose one of {sorted(actions)}"
            )
        return fn(**kwargs)


# ---------------------------------------------------------------------------
# HTML template — Three.js scene + cannon-es physics.
# ---------------------------------------------------------------------------
_SCENE_HTML_TEMPLATE = """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>CubeSandbox — {scene_id}</title>
<style>
  html,body {{ margin:0; height:100%; background:#0a0e27; overflow:hidden;
                font-family: system-ui, sans-serif; color:#fff; }}
  #stage {{ position:fixed; inset:0; }}
  #ui {{ position:fixed; top:10px; left:12px; padding:8px 12px;
         background:rgba(0,0,0,.55); border-radius:8px; font-size:12px;
         backdrop-filter: blur(6px); }}
  #ui button {{ margin:2px; padding:5px 10px; border:0; border-radius:4px;
                background:#1abc9c; color:#fff; cursor:pointer; }}
</style>
</head><body>
<div id="stage"></div>
<div id="ui">
  <div><strong>CubeSandbox</strong> — scene {scene_id}</div>
  <button id="reset">reset</button>
  <button id="impulse">random impulse</button>
</div>
<script type="importmap">
{{ "imports": {{
    "three": "https://unpkg.com/three@0.160.0/build/three.module.js",
    "cannon-es": "https://unpkg.com/cannon-es@0.20.0/dist/cannon-es.js"
}} }}
</script>
<script type="module">
import * as THREE from 'three';
import * as CANNON from 'cannon-es';

const SPEC = {objects_json};

const stage = document.getElementById('stage');
const renderer = new THREE.WebGLRenderer({{ antialias: true }});
renderer.setPixelRatio(window.devicePixelRatio);
renderer.setSize(window.innerWidth, window.innerHeight);
stage.appendChild(renderer.domElement);

const scene = new THREE.Scene();
scene.background = new THREE.Color('#0a0e27');

const camera = new THREE.PerspectiveCamera(55, window.innerWidth/window.innerHeight, 0.1, 200);
camera.position.set(7, 6, 11);
camera.lookAt(0, 1, 0);

scene.add(new THREE.AmbientLight(0xffffff, 0.5));
const dir = new THREE.DirectionalLight(0xffffff, 0.9);
dir.position.set(5, 10, 5); scene.add(dir);

// Ground (visual)
const ground = new THREE.Mesh(
  new THREE.PlaneGeometry(40, 40),
  new THREE.MeshStandardMaterial({{ color: '#1c2247', roughness: 0.95 }})
);
ground.rotation.x = -Math.PI/2; scene.add(ground);
// Grid helper
scene.add(new THREE.GridHelper(40, 40, 0x33406a, 0x222a55));

// Physics world
const world = new CANNON.World({{ gravity: new CANNON.Vec3(0, -9.81, 0) }});
world.broadphase = new CANNON.NaiveBroadphase();
world.solver.iterations = 12;

// Ground physics body
const groundBody = new CANNON.Body({{ mass: 0, shape: new CANNON.Plane() }});
groundBody.quaternion.setFromAxisAngle(new CANNON.Vec3(1,0,0), -Math.PI/2);
world.addBody(groundBody);

// Build scene objects (visual + physical)
const items = [];
function build() {{
  while (items.length) {{
    const it = items.pop();
    scene.remove(it.mesh);
    world.removeBody(it.body);
  }}
  for (const spec of SPEC) {{
    const size = spec.size || 1;
    let geom, shape;
    if (spec.type === 'sphere') {{
      const r = size/2;
      geom = new THREE.SphereGeometry(r, 24, 18);
      shape = new CANNON.Sphere(r);
    }} else if (spec.type === 'cylinder') {{
      const r = size/2;
      geom = new THREE.CylinderGeometry(r, r, size, 16);
      shape = new CANNON.Cylinder(r, r, size, 16);
    }} else {{
      geom = new THREE.BoxGeometry(size, size, size);
      shape = new CANNON.Box(new CANNON.Vec3(size/2, size/2, size/2));
    }}
    const mat = new THREE.MeshStandardMaterial({{ color: spec.color, roughness: 0.5 }});
    const mesh = new THREE.Mesh(geom, mat);
    const body = new CANNON.Body({{
      mass: spec.static ? 0 : (spec.mass || 1),
      shape: shape,
      position: new CANNON.Vec3(spec.position[0], spec.position[1], spec.position[2]),
      velocity: new CANNON.Vec3(spec.velocity[0], spec.velocity[1], spec.velocity[2])
    }});
    scene.add(mesh); world.addBody(body);
    items.push({{ mesh, body, spec }});
  }}
}}
build();

document.getElementById('reset').onclick = build;
document.getElementById('impulse').onclick = () => {{
  for (const it of items) {{
    if (it.body.mass === 0) continue;
    it.body.velocity.set(
      (Math.random()-0.5)*8,
      Math.random()*6 + 2,
      (Math.random()-0.5)*8
    );
  }}
}};

const dt = 1/60;
function tick() {{
  world.step(dt);
  for (const it of items) {{
    it.mesh.position.copy(it.body.position);
    it.mesh.quaternion.copy(it.body.quaternion);
  }}
  renderer.render(scene, camera);
  requestAnimationFrame(tick);
}}
tick();

window.addEventListener('resize', () => {{
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
}});
</script>
</body></html>
"""
