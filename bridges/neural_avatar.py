"""Neural Avatar bridge — Three.js holographic 3D avatar + rule-based lip sync.

Requirement #23 — Neural Avatar 3D holographic.
"""
from __future__ import annotations

import html
import json
from typing import Any


_STYLE_CONFIGS: dict[str, dict[str, Any]] = {
    "holographic": {
        "color": "#00e5ff",
        "emissive": "#0066ff",
        "emissive_intensity": 0.8,
        "roughness": 0.15,
        "metalness": 0.6,
        "opacity": 0.85,
        "wireframe": False,
        "glow": 1.5,
    },
    "iron_man": {
        "color": "#c8202c",
        "emissive": "#ffc83d",
        "emissive_intensity": 0.6,
        "roughness": 0.3,
        "metalness": 0.95,
        "opacity": 1.0,
        "wireframe": False,
        "glow": 1.2,
    },
    "ghost": {
        "color": "#ffffff",
        "emissive": "#a0d8ff",
        "emissive_intensity": 0.4,
        "roughness": 0.0,
        "metalness": 0.0,
        "opacity": 0.45,
        "wireframe": False,
        "glow": 0.8,
    },
    "neon": {
        "color": "#ff00ff",
        "emissive": "#00ff88",
        "emissive_intensity": 1.0,
        "roughness": 0.05,
        "metalness": 0.5,
        "opacity": 0.9,
        "wireframe": True,
        "glow": 2.0,
    },
}


_PHONEME_MAP: dict[str, str] = {
    "a": "AH", "e": "EH", "i": "IY", "o": "OW", "u": "UW",
    "y": "IY",
    "b": "B", "c": "K", "d": "D", "f": "F", "g": "G",
    "h": "HH", "j": "JH", "k": "K", "l": "L", "m": "M",
    "n": "N", "p": "P", "q": "K", "r": "R", "s": "S",
    "t": "T", "v": "V", "w": "W", "x": "K", "z": "Z",
}

_DIGRAPHS: dict[str, str] = {
    "ch": "CH", "sh": "SH", "th": "TH", "ph": "F",
    "wh": "W", "ng": "NG", "qu": "KW", "oo": "UW",
    "ee": "IY", "ai": "AY", "ay": "AY", "ou": "AW",
    "ow": "AW",
}

_VOWEL_PHONEMES = {"AH", "EH", "IY", "OW", "UW", "AY", "AW"}


class NeuralAvatar:
    """3D holographic avatar generator + lip-sync sequencer."""

    def __init__(self, default_style: str = "holographic") -> None:
        if default_style not in _STYLE_CONFIGS:
            raise ValueError(f"unknown style: {default_style}")
        self.default_style = default_style

    def get_avatar_config(self, style: str) -> dict[str, Any]:
        if style not in _STYLE_CONFIGS:
            raise ValueError(f"unknown style: {style}")
        return dict(_STYLE_CONFIGS[style])

    def generate_lip_sync_sequence(
        self, text: str, voice: str = "en"
    ) -> list[dict[str, Any]]:
        if not text:
            return []

        sequence: list[dict[str, Any]] = []
        cursor = 0.0
        text_lower = text.lower()
        i = 0
        n = len(text_lower)

        while i < n:
            ch = text_lower[i]

            if ch.isspace():
                sequence.append({
                    "phoneme": "SIL",
                    "start": round(cursor, 4),
                    "end": round(cursor + 0.08, 4),
                    "intensity": 0.0,
                })
                cursor += 0.08
                i += 1
                continue

            if i + 1 < n:
                pair = text_lower[i:i + 2]
                if pair in _DIGRAPHS:
                    phoneme = _DIGRAPHS[pair]
                    duration = 0.14 if phoneme in _VOWEL_PHONEMES else 0.10
                    intensity = 0.85 if phoneme in _VOWEL_PHONEMES else 0.55
                    sequence.append({
                        "phoneme": phoneme,
                        "start": round(cursor, 4),
                        "end": round(cursor + duration, 4),
                        "intensity": intensity,
                    })
                    cursor += duration
                    i += 2
                    continue

            phoneme = _PHONEME_MAP.get(ch)
            if phoneme is None:
                i += 1
                continue
            duration = 0.12 if phoneme in _VOWEL_PHONEMES else 0.08
            intensity = 0.8 if phoneme in _VOWEL_PHONEMES else 0.5
            sequence.append({
                "phoneme": phoneme,
                "start": round(cursor, 4),
                "end": round(cursor + duration, 4),
                "intensity": intensity,
            })
            cursor += duration
            i += 1

        return sequence

    def generate_html(
        self, name: str, role: str, style: str = "holographic"
    ) -> str:
        cfg = self.get_avatar_config(style)
        safe_name = html.escape(name)
        safe_role = html.escape(role)
        cfg_json = json.dumps(cfg)

        return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Neural Avatar — {safe_name}</title>
<style>
  html,body{{margin:0;padding:0;overflow:hidden;background:#04060f;
    font-family:-apple-system,Segoe UI,Roboto,sans-serif;color:#e7f5ff}}
  #scene{{position:fixed;inset:0}}
  .hud{{position:fixed;top:18px;left:22px;padding:10px 16px;
    background:rgba(10,18,40,.55);border:1px solid rgba(0,229,255,.45);
    border-radius:10px;backdrop-filter:blur(10px);z-index:5}}
  .hud h1{{margin:0 0 4px;font-size:18px;letter-spacing:.06em;
    color:#7df9ff;text-shadow:0 0 12px rgba(0,229,255,.7)}}
  .hud p{{margin:0;font-size:12px;opacity:.78}}
  .glow{{position:fixed;inset:0;pointer-events:none;
    background:radial-gradient(ellipse at center,
    rgba(0,229,255,.12) 0%,transparent 60%);z-index:1}}
</style>
</head>
<body>
<div class="glow"></div>
<div class="hud">
  <h1>{safe_name}</h1>
  <p>{safe_role} — style: {html.escape(style)}</p>
</div>
<canvas id="scene"></canvas>

<script type="importmap">
{{ "imports": {{
  "three": "https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js",
  "three/addons/": "https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/"
}} }}
</script>

<script type="module">
import * as THREE from 'three';
import {{ OrbitControls }} from 'three/addons/controls/OrbitControls.js';

const cfg = {cfg_json};
const canvas = document.getElementById('scene');
const renderer = new THREE.WebGLRenderer({{ canvas, antialias: true, alpha: true }});
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.setSize(window.innerWidth, window.innerHeight);

const scene = new THREE.Scene();
scene.fog = new THREE.FogExp2(0x04060f, 0.015);

const camera = new THREE.PerspectiveCamera(
  45, window.innerWidth / window.innerHeight, 0.1, 200);
camera.position.set(0, 1.4, 5.5);

const ambient = new THREE.AmbientLight(0x4488ff, 0.55);
scene.add(ambient);

const point = new THREE.PointLight(new THREE.Color(cfg.emissive), 2.2, 18);
point.position.set(2.5, 3, 4);
scene.add(point);

const rim = new THREE.PointLight(new THREE.Color(cfg.color), 1.6, 14);
rim.position.set(-3, 1.5, 2);
scene.add(rim);

const mat = new THREE.MeshStandardMaterial({{
  color: new THREE.Color(cfg.color),
  emissive: new THREE.Color(cfg.emissive),
  emissiveIntensity: cfg.emissive_intensity,
  roughness: cfg.roughness,
  metalness: cfg.metalness,
  transparent: cfg.opacity < 1,
  opacity: cfg.opacity,
  wireframe: cfg.wireframe
}});

const avatar = new THREE.Group();

const head = new THREE.Mesh(new THREE.SphereGeometry(0.7, 48, 48), mat);
head.position.y = 1.7;
avatar.add(head);

const torso = new THREE.Mesh(new THREE.CapsuleGeometry(0.55, 1.0, 8, 16), mat);
torso.position.y = 0.5;
avatar.add(torso);

const halo = new THREE.Mesh(
  new THREE.TorusGeometry(0.95, 0.025, 16, 96),
  new THREE.MeshBasicMaterial({{
    color: new THREE.Color(cfg.emissive),
    transparent: true, opacity: 0.7
  }}));
halo.rotation.x = Math.PI / 2;
halo.position.y = 2.55;
avatar.add(halo);

scene.add(avatar);

const grid = new THREE.GridHelper(40, 40,
  new THREE.Color(cfg.emissive), new THREE.Color(cfg.color));
grid.position.y = -0.6;
grid.material.transparent = true;
grid.material.opacity = 0.35;
scene.add(grid);

const controls = new OrbitControls(camera, canvas);
controls.enableDamping = true;
controls.target.set(0, 1.2, 0);
controls.minDistance = 2;
controls.maxDistance = 12;

window.addEventListener('resize', () => {{
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
}});

const clock = new THREE.Clock();
function loop() {{
  const t = clock.getElapsedTime();
  avatar.rotation.y = t * 0.45;
  halo.rotation.z = t * 1.1;
  head.position.y = 1.7 + Math.sin(t * 1.6) * 0.04;
  point.intensity = 2.2 + Math.sin(t * 2.3) * 0.6 * cfg.glow;
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
            "generate_html": self.generate_html,
            "generate_lip_sync_sequence": self.generate_lip_sync_sequence,
            "get_avatar_config": self.get_avatar_config,
        }
        fn = actions.get(action)
        if fn is None:
            raise ValueError(f"unknown action: {action}")
        return fn(**kwargs)
