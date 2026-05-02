"""CubeSandbox bridge — Three.js + cannon-es scene + pure-Python physics step.

Requirement #37 — CubeSandbox physics.
"""
from __future__ import annotations

import json
import uuid
from typing import Any

GRAVITY_Y = -9.81
GROUND_Y = 0.0
RESTITUTION = 0.45
GROUND_FRICTION = 0.92
SUPPORTED_TYPES = ("box", "sphere", "plane")


def _new_id() -> str:
    return uuid.uuid4().hex[:8]


class CubeSandbox:
    """Physics sandbox — generates browser scenes and runs server-side stepping."""

    def __init__(self) -> None:
        self.supported_types = SUPPORTED_TYPES

    def add_object(
        self,
        scene_state: dict[str, Any] | None,
        obj_type: str,
        position: tuple[float, float, float] | list[float] | dict[str, float],
        properties: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if obj_type not in SUPPORTED_TYPES:
            raise ValueError(f"unsupported obj_type: {obj_type}")

        state = self._normalize_state(scene_state)

        if isinstance(position, dict):
            px = float(position.get("x", 0.0))
            py = float(position.get("y", 0.0))
            pz = float(position.get("z", 0.0))
        else:
            seq = list(position)
            if len(seq) != 3:
                raise ValueError("position must have 3 components")
            px, py, pz = float(seq[0]), float(seq[1]), float(seq[2])

        props = dict(properties or {})
        is_static = bool(props.get("static", obj_type == "plane"))
        mass = 0.0 if is_static else float(props.get("mass", 1.0))

        obj: dict[str, Any] = {
            "id": props.get("id") or _new_id(),
            "type": obj_type,
            "x": px, "y": py, "z": pz,
            "vx": float(props.get("vx", 0.0)),
            "vy": float(props.get("vy", 0.0)),
            "vz": float(props.get("vz", 0.0)),
            "color": props.get("color", "#7df9ff"),
            "size": float(props.get("size", 1.0)),
            "mass": mass,
            "static": is_static,
        }
        state["objects"].append(obj)
        return state

    def simulate_step(
        self, scene_state: dict[str, Any], dt: float = 0.016
    ) -> dict[str, Any]:
        state = self._normalize_state(scene_state)
        gravity_on = bool(state.get("gravity", True))
        g = GRAVITY_Y if gravity_on else 0.0

        for obj in state["objects"]:
            if obj.get("static"):
                continue

            obj["vy"] += g * dt
            obj["x"] += obj["vx"] * dt
            obj["y"] += obj["vy"] * dt
            obj["z"] += obj["vz"] * dt

            half = obj["size"] / 2 if obj["type"] == "box" else obj["size"]
            floor = GROUND_Y + half
            if obj["y"] < floor:
                obj["y"] = floor
                if obj["vy"] < 0:
                    obj["vy"] = -obj["vy"] * RESTITUTION
                    if abs(obj["vy"]) < 0.05:
                        obj["vy"] = 0.0
                obj["vx"] *= GROUND_FRICTION
                obj["vz"] *= GROUND_FRICTION

        state["t"] = float(state.get("t", 0.0)) + dt
        return state

    def generate_scene_html(
        self,
        objects: list[dict[str, Any]] | None = None,
        gravity: bool = True,
        width: int = 800,
        height: int = 600,
    ) -> str:
        seeded = objects or []
        validated: list[dict[str, Any]] = []
        for obj in seeded:
            if not isinstance(obj, dict):
                raise ValueError("each object must be a dict")
            t = obj.get("type", "box")
            if t not in SUPPORTED_TYPES:
                raise ValueError(f"unsupported obj type: {t}")
            validated.append({
                "type": t,
                "x": float(obj.get("x", 0.0)),
                "y": float(obj.get("y", 2.0)),
                "z": float(obj.get("z", 0.0)),
                "color": obj.get("color", "#7df9ff"),
                "size": float(obj.get("size", 1.0)),
            })

        objs_json = json.dumps(validated)
        gravity_y = -9.82 if gravity else 0.0

        return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>CubeSandbox</title>
<style>
  html,body{{margin:0;padding:0;background:#04060f;overflow:hidden;
    color:#e7f0ff;font-family:-apple-system,Segoe UI,Roboto,sans-serif}}
  #scene{{position:fixed;inset:0}}
  .controls{{position:fixed;top:14px;left:14px;z-index:5;
    background:rgba(10,18,40,.6);border:1px solid rgba(125,249,255,.3);
    padding:10px 14px;border-radius:10px;backdrop-filter:blur(10px)}}
  .controls button{{background:#0e1b3a;color:#7df9ff;
    border:1px solid #1e3a78;padding:6px 12px;margin-right:6px;
    border-radius:6px;cursor:pointer}}
  .controls button:hover{{background:#15264f}}
  .hint{{font-size:11px;opacity:.7;margin-top:6px}}
</style>
</head>
<body>
<div class="controls">
  <button id="reset">reset</button>
  <button id="spawn">spawn cube</button>
  <div class="hint">click anywhere on scene to spawn a cube</div>
</div>
<canvas id="scene"></canvas>

<script type="importmap">
{{ "imports": {{
  "three": "https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js",
  "three/addons/": "https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/",
  "cannon-es": "https://cdn.jsdelivr.net/npm/cannon-es@0.20.0/dist/cannon-es.js"
}} }}
</script>

<script type="module">
import * as THREE from 'three';
import {{ OrbitControls }} from 'three/addons/controls/OrbitControls.js';
import * as CANNON from 'cannon-es';

const seed = {objs_json};
const canvas = document.getElementById('scene');

const renderer = new THREE.WebGLRenderer({{ canvas, antialias: true }});
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.setSize(innerWidth, innerHeight);

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x04060f);
scene.fog = new THREE.FogExp2(0x04060f, 0.012);

const camera = new THREE.PerspectiveCamera(
  55, innerWidth / innerHeight, 0.1, 200);
camera.position.set(8, 9, 12);

const ambient = new THREE.AmbientLight(0x4488cc, 0.55);
scene.add(ambient);
const sun = new THREE.DirectionalLight(0xffffff, 1.0);
sun.position.set(10, 20, 10);
scene.add(sun);

const controls = new OrbitControls(camera, canvas);
controls.target.set(0, 1, 0);
controls.enableDamping = true;

const world = new CANNON.World({{
  gravity: new CANNON.Vec3(0, {gravity_y}, 0)
}});
world.broadphase = new CANNON.NaiveBroadphase();
world.solver.iterations = 12;

const groundBody = new CANNON.Body({{
  mass: 0,
  shape: new CANNON.Plane(),
}});
groundBody.quaternion.setFromAxisAngle(new CANNON.Vec3(1, 0, 0), -Math.PI / 2);
world.addBody(groundBody);

const groundMesh = new THREE.Mesh(
  new THREE.PlaneGeometry(40, 40),
  new THREE.MeshStandardMaterial({{
    color: 0x142048, roughness: 0.85, metalness: 0.05
  }})
);
groundMesh.rotation.x = -Math.PI / 2;
scene.add(groundMesh);

const grid = new THREE.GridHelper(40, 40, 0x7df9ff, 0x1e3a78);
grid.position.y = 0.01;
grid.material.transparent = true;
grid.material.opacity = 0.4;
scene.add(grid);

const pairs = [];

function spawn(spec) {{
  const t = spec.type || 'box';
  const sz = spec.size || 1;
  const color = new THREE.Color(spec.color || '#7df9ff');
  let mesh, body;

  if (t === 'sphere') {{
    mesh = new THREE.Mesh(
      new THREE.SphereGeometry(sz, 28, 28),
      new THREE.MeshStandardMaterial({{ color, roughness: .35, metalness: .3 }})
    );
    body = new CANNON.Body({{
      mass: 1, shape: new CANNON.Sphere(sz)
    }});
  }} else if (t === 'plane') {{
    mesh = new THREE.Mesh(
      new THREE.BoxGeometry(sz * 4, 0.2, sz * 4),
      new THREE.MeshStandardMaterial({{ color, roughness: .8 }})
    );
    body = new CANNON.Body({{
      mass: 0,
      shape: new CANNON.Box(new CANNON.Vec3(sz * 2, 0.1, sz * 2))
    }});
  }} else {{
    mesh = new THREE.Mesh(
      new THREE.BoxGeometry(sz, sz, sz),
      new THREE.MeshStandardMaterial({{
        color, roughness: .35, metalness: .25,
        emissive: color, emissiveIntensity: .12
      }})
    );
    body = new CANNON.Body({{
      mass: 1,
      shape: new CANNON.Box(new CANNON.Vec3(sz / 2, sz / 2, sz / 2))
    }});
  }}
  body.position.set(spec.x || 0, spec.y || 3, spec.z || 0);
  scene.add(mesh);
  world.addBody(body);
  pairs.push([mesh, body]);
}}

function reset() {{
  pairs.forEach(([m, b]) => {{
    scene.remove(m);
    world.removeBody(b);
  }});
  pairs.length = 0;
  seed.forEach(spawn);
}}

document.getElementById('reset').addEventListener('click', reset);
document.getElementById('spawn').addEventListener('click', () => {{
  spawn({{ type: 'box', x: (Math.random() - .5) * 4, y: 8, z: (Math.random() - .5) * 4,
    color: '#' + Math.floor(Math.random() * 0xffffff).toString(16).padStart(6, '0') }});
}});

const ray = new THREE.Raycaster();
const mouse = new THREE.Vector2();
canvas.addEventListener('click', (e) => {{
  mouse.x = (e.clientX / innerWidth) * 2 - 1;
  mouse.y = -(e.clientY / innerHeight) * 2 + 1;
  ray.setFromCamera(mouse, camera);
  const hit = ray.intersectObject(groundMesh);
  if (hit.length) {{
    const p = hit[0].point;
    spawn({{ type: 'box', x: p.x, y: 8, z: p.z,
      color: '#' + Math.floor(Math.random() * 0xffffff).toString(16).padStart(6, '0') }});
  }}
}});

addEventListener('resize', () => {{
  camera.aspect = innerWidth / innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(innerWidth, innerHeight);
}});

reset();

const clock = new THREE.Clock();
function loop() {{
  const dt = Math.min(clock.getDelta(), 1 / 30);
  world.step(1 / 60, dt, 3);
  pairs.forEach(([m, b]) => {{
    m.position.copy(b.position);
    m.quaternion.copy(b.quaternion);
  }});
  controls.update();
  renderer.render(scene, camera);
  requestAnimationFrame(loop);
}}
loop();
</script>
</body>
</html>
"""

    def invoke(self, action: str, **kwargs: Any) -> Any:
        actions = {
            "generate_scene_html": self.generate_scene_html,
            "add_object": self.add_object,
            "simulate_step": self.simulate_step,
        }
        fn = actions.get(action)
        if fn is None:
            raise ValueError(f"unknown action: {action}")
        return fn(**kwargs)

    @staticmethod
    def _normalize_state(
        scene_state: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if scene_state is None:
            return {"objects": [], "gravity": True, "t": 0.0}
        if not isinstance(scene_state, dict):
            raise ValueError("scene_state must be a dict")
        if "objects" not in scene_state:
            scene_state["objects"] = []
        scene_state.setdefault("gravity", True)
        scene_state.setdefault("t", 0.0)
        return scene_state
