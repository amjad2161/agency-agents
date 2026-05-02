"""Neural Avatar 3D Bridge.

Generates browser-renderable Three.js avatars with animation and
lip-sync support. Output is a self-contained HTML file at
``assets/avatar/avatar.html``.

Public API
----------
NeuralAvatarBridge
    generate_avatar(style, gender)        -> Path
    animate(emotion)                      -> dict
    speak(text, language='he')            -> dict
    set_appearance(params)                -> dict
    export_glb(output_path)               -> Path
    invoke(action, **kwargs)              -> Any
"""

from __future__ import annotations

import json
import struct
from pathlib import Path
from typing import Any


_DEFAULT_ASSET_DIR = Path("assets") / "avatar"


# ---------------------------------------------------------------------------
# Emotion presets — animation parameters consumed by the HTML runtime.
# ---------------------------------------------------------------------------
EMOTION_PRESETS: dict[str, dict[str, Any]] = {
    "neutral": {
        "head_tilt": 0.0,
        "mouth_open": 0.05,
        "eye_scale": 1.0,
        "color": "#4a90e2",
        "duration_ms": 600,
        "easing": "ease-in-out",
    },
    "happy": {
        "head_tilt": 0.05,
        "mouth_open": 0.35,
        "mouth_curve": 0.6,
        "eye_scale": 1.05,
        "color": "#f5d442",
        "duration_ms": 400,
        "easing": "ease-out",
    },
    "thinking": {
        "head_tilt": -0.18,
        "mouth_open": 0.0,
        "eye_scale": 0.85,
        "color": "#9b59b6",
        "duration_ms": 800,
        "easing": "ease-in",
    },
    "speaking": {
        "head_tilt": 0.02,
        "mouth_open": 0.4,
        "eye_scale": 1.0,
        "color": "#1abc9c",
        "duration_ms": 200,
        "easing": "linear",
    },
    "alert": {
        "head_tilt": 0.0,
        "mouth_open": 0.5,
        "eye_scale": 1.25,
        "color": "#e74c3c",
        "duration_ms": 250,
        "easing": "ease-out",
    },
}


# Phoneme → mouth shape (visemes). Subset covering Hebrew + English.
_PHONEME_VISEMES: dict[str, dict[str, float]] = {
    "A":  {"open": 0.7, "wide": 0.4},
    "E":  {"open": 0.4, "wide": 0.6},
    "I":  {"open": 0.2, "wide": 0.7},
    "O":  {"open": 0.6, "wide": 0.2},
    "U":  {"open": 0.3, "wide": 0.1},
    "M":  {"open": 0.0, "wide": 0.0},
    "B":  {"open": 0.05, "wide": 0.05},
    "P":  {"open": 0.05, "wide": 0.05},
    "F":  {"open": 0.1, "wide": 0.3},
    "S":  {"open": 0.15, "wide": 0.5},
    "T":  {"open": 0.2, "wide": 0.3},
    "L":  {"open": 0.25, "wide": 0.3},
    "N":  {"open": 0.15, "wide": 0.2},
    "R":  {"open": 0.3, "wide": 0.3},
    "K":  {"open": 0.25, "wide": 0.25},
    "G":  {"open": 0.25, "wide": 0.25},
    "H":  {"open": 0.4, "wide": 0.3},
    "SH": {"open": 0.2, "wide": 0.4},
    "CH": {"open": 0.25, "wide": 0.4},
    "TH": {"open": 0.15, "wide": 0.3},
    "REST": {"open": 0.05, "wide": 0.0},
}


# Letter → phoneme mapping. Hebrew + English fallback.
_HEBREW_MAP: dict[str, str] = {
    "א": "A", "ב": "B", "ג": "G", "ד": "T", "ה": "H",
    "ו": "U", "ז": "S", "ח": "H", "ט": "T", "י": "I",
    "כ": "K", "ך": "K", "ל": "L", "מ": "M", "ם": "M",
    "נ": "N", "ן": "N", "ס": "S", "ע": "A", "פ": "P",
    "ף": "P", "צ": "S", "ץ": "S", "ק": "K", "ר": "R",
    "ש": "SH", "ת": "T",
}

_ENGLISH_MAP: dict[str, str] = {
    "a": "A", "b": "B", "c": "K", "d": "T", "e": "E",
    "f": "F", "g": "G", "h": "H", "i": "I", "j": "CH",
    "k": "K", "l": "L", "m": "M", "n": "N", "o": "O",
    "p": "P", "q": "K", "r": "R", "s": "S", "t": "T",
    "u": "U", "v": "F", "w": "U", "x": "K", "y": "I",
    "z": "S",
}


# ---------------------------------------------------------------------------
# Bridge
# ---------------------------------------------------------------------------
class NeuralAvatarBridge:
    """Generate browser-renderable 3D avatars with animation + lip-sync."""

    def __init__(self, asset_dir: str | Path | None = None) -> None:
        self.asset_dir = Path(asset_dir) if asset_dir else _DEFAULT_ASSET_DIR
        self.appearance: dict[str, Any] = {
            "skin_color": "#f4c8a0",
            "shirt_color": "#2c3e50",
            "eye_color": "#1a1a1a",
            "hair_color": "#3a2f25",
            "background": "#0a0e27",
        }
        self.style: str = "professional"
        self.gender: str = "neutral"

    # ------------------------------------------------------------------
    # Avatar generation
    # ------------------------------------------------------------------
    def generate_avatar(
        self,
        style: str = "professional",
        gender: str = "neutral",
        output_path: str | Path | None = None,
    ) -> Path:
        """Write a self-contained Three.js avatar HTML file. Return path."""
        self.style = style
        self.gender = gender
        out = Path(output_path) if output_path else (self.asset_dir / "avatar.html")
        out.parent.mkdir(parents=True, exist_ok=True)

        appearance_json = json.dumps(self.appearance)
        emotions_json = json.dumps(EMOTION_PRESETS)
        html = _AVATAR_HTML_TEMPLATE.format(
            style=style,
            gender=gender,
            appearance=appearance_json,
            emotions=emotions_json,
        )
        out.write_text(html, encoding="utf-8")
        return out

    # ------------------------------------------------------------------
    # Animation
    # ------------------------------------------------------------------
    def animate(self, emotion: str) -> dict[str, Any]:
        """Return CSS/JS animation parameters for an emotion."""
        preset = EMOTION_PRESETS.get(emotion)
        if preset is None:
            raise ValueError(
                f"unknown emotion {emotion!r}; choose one of "
                f"{sorted(EMOTION_PRESETS)}"
            )
        return {
            "emotion": emotion,
            "css_transform": (
                f"rotateZ({preset['head_tilt']}rad) "
                f"scale({preset['eye_scale']})"
            ),
            "js_params": dict(preset),
            "transition": (
                f"all {preset['duration_ms']}ms {preset['easing']}"
            ),
        }

    # ------------------------------------------------------------------
    # Lip-sync
    # ------------------------------------------------------------------
    def speak(self, text: str, language: str = "he") -> dict[str, Any]:
        """Return phoneme/timing data for lip-sync."""
        if not isinstance(text, str):
            raise TypeError("text must be a string")
        mapping = _HEBREW_MAP if language == "he" else _ENGLISH_MAP
        phonemes: list[dict[str, Any]] = []
        cursor_ms = 0
        per_phoneme_ms = 90
        gap_ms = 30
        for ch in text:
            key = ch if language == "he" else ch.lower()
            phoneme = mapping.get(key)
            if phoneme is None:
                if ch.isspace():
                    cursor_ms += gap_ms * 2
                    phonemes.append({
                        "phoneme": "REST",
                        "viseme": _PHONEME_VISEMES["REST"],
                        "start_ms": cursor_ms - gap_ms * 2,
                        "duration_ms": gap_ms * 2,
                    })
                continue
            phonemes.append({
                "phoneme": phoneme,
                "viseme": _PHONEME_VISEMES[phoneme],
                "start_ms": cursor_ms,
                "duration_ms": per_phoneme_ms,
            })
            cursor_ms += per_phoneme_ms + gap_ms
        return {
            "text": text,
            "language": language,
            "total_ms": cursor_ms,
            "phonemes": phonemes,
        }

    # ------------------------------------------------------------------
    # Appearance
    # ------------------------------------------------------------------
    def set_appearance(self, params: dict[str, Any]) -> dict[str, Any]:
        """Update appearance (color scheme, clothing). Returns new state."""
        if not isinstance(params, dict):
            raise TypeError("params must be a dict")
        allowed = set(self.appearance.keys())
        unknown = set(params.keys()) - allowed
        if unknown:
            raise ValueError(
                f"unknown appearance keys: {sorted(unknown)}; "
                f"allowed: {sorted(allowed)}"
            )
        new_state = {**self.appearance, **params}
        self.appearance = new_state
        return dict(new_state)

    # ------------------------------------------------------------------
    # GLB export — minimal valid GLB header.
    # ------------------------------------------------------------------
    def export_glb(self, output_path: str | Path) -> Path:
        """Write a minimal valid binary glTF (GLB) container.

        Produces a parseable GLB with header + JSON chunk that contains
        only an asset stub. Useful as a placeholder for downstream tools
        that probe GLB validity.
        """
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)

        json_payload = json.dumps({
            "asset": {"version": "2.0", "generator": "NeuralAvatarBridge"},
            "scenes": [{"nodes": []}],
            "scene": 0,
            "nodes": [],
            "meshes": [],
        }).encode("utf-8")
        # JSON chunk must be 4-byte aligned, padded with spaces (0x20).
        pad = (4 - (len(json_payload) % 4)) % 4
        json_payload += b" " * pad

        json_chunk_header = struct.pack("<II", len(json_payload), 0x4E4F534A)  # "JSON"
        total_length = 12 + 8 + len(json_payload)
        glb_header = struct.pack("<III", 0x46546C67, 2, total_length)  # "glTF", v2

        out.write_bytes(glb_header + json_chunk_header + json_payload)
        return out

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------
    def invoke(self, action: str, **kwargs: Any) -> Any:
        """Dispatch to a public action by name."""
        actions = {
            "generate_avatar": self.generate_avatar,
            "animate": self.animate,
            "speak": self.speak,
            "set_appearance": self.set_appearance,
            "export_glb": self.export_glb,
        }
        fn = actions.get(action)
        if fn is None:
            raise ValueError(
                f"unknown action {action!r}; choose one of {sorted(actions)}"
            )
        return fn(**kwargs)


# ---------------------------------------------------------------------------
# HTML template — Three.js avatar (geometric humanoid, animated).
# ---------------------------------------------------------------------------
_AVATAR_HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>Neural Avatar — {style} / {gender}</title>
<style>
  html, body {{ margin:0; height:100%; background:#0a0e27; color:#fff;
                font-family: system-ui, sans-serif; overflow:hidden; }}
  #stage {{ position:fixed; inset:0; }}
  #ui {{ position:fixed; left:12px; top:12px; padding:10px 12px;
         background:rgba(0,0,0,.55); border-radius:8px; font-size:13px;
         backdrop-filter: blur(6px); }}
  #ui button {{ margin:2px; padding:5px 10px; border:0; border-radius:4px;
                background:#1abc9c; color:#fff; cursor:pointer; }}
  #ui button:hover {{ background:#16a085; }}
</style>
</head>
<body>
<div id="stage"></div>
<div id="ui">
  <div><strong>Neural Avatar</strong> — {style}</div>
  <div id="emo-row"></div>
</div>
<script type="importmap">
{{ "imports": {{
    "three": "https://unpkg.com/three@0.160.0/build/three.module.js"
}} }}
</script>
<script type="module">
import * as THREE from 'three';

const APPEARANCE = {appearance};
const EMOTIONS = {emotions};
let CURRENT = EMOTIONS.neutral;

const stage = document.getElementById('stage');
const renderer = new THREE.WebGLRenderer({{ antialias: true, alpha: true }});
renderer.setPixelRatio(window.devicePixelRatio);
renderer.setSize(window.innerWidth, window.innerHeight);
stage.appendChild(renderer.domElement);

const scene = new THREE.Scene();
scene.background = new THREE.Color(APPEARANCE.background);

const camera = new THREE.PerspectiveCamera(45, window.innerWidth/window.innerHeight, 0.1, 100);
camera.position.set(0, 1.5, 4);
camera.lookAt(0, 1.2, 0);

scene.add(new THREE.AmbientLight(0xffffff, 0.55));
const key = new THREE.DirectionalLight(0xffffff, 1.0);
key.position.set(2, 4, 3);
scene.add(key);
const rim = new THREE.DirectionalLight(0x6688ff, 0.5);
rim.position.set(-3, 2, -2);
scene.add(rim);

// Avatar root
const avatar = new THREE.Group();
scene.add(avatar);

// Body (torso)
const torso = new THREE.Mesh(
  new THREE.CylinderGeometry(0.45, 0.55, 1.1, 16),
  new THREE.MeshStandardMaterial({{ color: APPEARANCE.shirt_color, roughness: 0.7 }})
);
torso.position.y = 0.6;
avatar.add(torso);

// Head
const head = new THREE.Mesh(
  new THREE.SphereGeometry(0.4, 32, 24),
  new THREE.MeshStandardMaterial({{ color: APPEARANCE.skin_color, roughness: 0.6 }})
);
head.position.y = 1.55;
avatar.add(head);

// Hair cap
const hair = new THREE.Mesh(
  new THREE.SphereGeometry(0.42, 24, 16, 0, Math.PI*2, 0, Math.PI/2.2),
  new THREE.MeshStandardMaterial({{ color: APPEARANCE.hair_color, roughness: 0.85 }})
);
hair.position.y = 1.62;
avatar.add(hair);

// Eyes
const eyeGeo = new THREE.SphereGeometry(0.05, 16, 12);
const eyeMat = new THREE.MeshStandardMaterial({{ color: APPEARANCE.eye_color }});
const eyeL = new THREE.Mesh(eyeGeo, eyeMat);
eyeL.position.set(-0.13, 1.6, 0.34);
const eyeR = new THREE.Mesh(eyeGeo, eyeMat);
eyeR.position.set( 0.13, 1.6, 0.34);
avatar.add(eyeL); avatar.add(eyeR);

// Mouth
const mouth = new THREE.Mesh(
  new THREE.BoxGeometry(0.18, 0.04, 0.04),
  new THREE.MeshStandardMaterial({{ color: '#5a1a1a' }})
);
mouth.position.set(0, 1.42, 0.36);
avatar.add(mouth);

// Arms
function arm(side) {{
  const g = new THREE.Group();
  const upper = new THREE.Mesh(
    new THREE.CylinderGeometry(0.12, 0.10, 0.55, 12),
    new THREE.MeshStandardMaterial({{ color: APPEARANCE.shirt_color, roughness: 0.7 }})
  );
  upper.position.y = -0.27;
  g.add(upper);
  g.position.set(side * 0.55, 1.05, 0);
  return g;
}}
const armL = arm(-1), armR = arm(1);
avatar.add(armL); avatar.add(armR);

// Animation state
const clock = new THREE.Clock();
let target = {{ tilt: 0, mouthOpen: 0.05, eyeScale: 1, color: APPEARANCE.shirt_color }};

function applyEmotion(name) {{
  const e = EMOTIONS[name];
  if (!e) return;
  CURRENT = e;
  target.tilt = e.head_tilt;
  target.mouthOpen = e.mouth_open;
  target.eyeScale = e.eye_scale;
  target.color = e.color;
}}

// Build emotion buttons
const row = document.getElementById('emo-row');
Object.keys(EMOTIONS).forEach(name => {{
  const b = document.createElement('button');
  b.textContent = name;
  b.onclick = () => applyEmotion(name);
  row.appendChild(b);
}});

function lerp(a, b, t) {{ return a + (b - a) * t; }}

let mouthCur = 0.05, tiltCur = 0, eyeCur = 1;
function tick() {{
  const t = clock.getElapsedTime();
  // Smooth interpolation toward target
  mouthCur = lerp(mouthCur, target.mouthOpen, 0.12);
  tiltCur  = lerp(tiltCur,  target.tilt, 0.08);
  eyeCur   = lerp(eyeCur,   target.eyeScale, 0.08);

  // Idle breathing + speaking jitter
  const breath = Math.sin(t * 1.4) * 0.012;
  const jitter = CURRENT === EMOTIONS.speaking ? Math.sin(t * 12) * 0.05 : 0;

  head.rotation.z = tiltCur;
  head.position.y = 1.55 + breath;
  hair.rotation.z = tiltCur;
  hair.position.y = 1.62 + breath;

  mouth.scale.y = 1 + (mouthCur + jitter) * 8;
  mouth.scale.x = 1 + (mouthCur * 0.5);

  eyeL.scale.set(eyeCur, eyeCur, eyeCur);
  eyeR.scale.set(eyeCur, eyeCur, eyeCur);

  // Subtle shoulder sway
  armL.rotation.z =  Math.sin(t * 1.1) * 0.04;
  armR.rotation.z = -Math.sin(t * 1.1) * 0.04;

  torso.material.color.lerp(new THREE.Color(target.color), 0.04);

  avatar.rotation.y = Math.sin(t * 0.4) * 0.15;

  renderer.render(scene, camera);
  requestAnimationFrame(tick);
}}
tick();

window.addEventListener('resize', () => {{
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
}});

window.NeuralAvatar = {{ applyEmotion }};
applyEmotion('neutral');
</script>
</body>
</html>
"""
