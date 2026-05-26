"""
3D AI Website Builder — JARVIS BRAINIAC Capability 2
=====================================================
Inspired by: @textura.us — "Claude is not a designer. Claude is a translator.
It converts decisions into pixels. Sharp decisions → a site that moves in
three dimensions."

Pipeline:
    brief (str)
        → BriefParser      — extract feel, palette, industry, style direction
        → DesignSystem     — map brief → CSS tokens, font pair, animation timing
        → ThreeJSScene     — select + configure 3D scene template
        → WebsiteAssembler — combine into single production HTML file

Output: complete, standalone HTML file with embedded CSS + JS.
Fully local — no external API or build tool required.
"""
from __future__ import annotations

import json
import re
import logging
from dataclasses import dataclass, asdict
from pathlib import Path

log = logging.getLogger(__name__)

# ─── Style presets ────────────────────────────────────────────────────────────

STYLE_PRESETS: dict[str, dict] = {
    "luxury": {
        "bg": "#0a0a0a",
        "surface": "#111111",
        "accent": "#c9a96e",
        "text_primary": "#f0ede8",
        "text_secondary": "#8a8580",
        "font_heading": "Playfair Display",
        "font_body": "Inter",
        "border_radius": "2px",
        "scene": "floating_sphere",
        "animation_speed": "slow",
        "keywords": ["luxury", "premium", "high-end", "exclusive", "elegant", "watch", "jewelry", "fashion"],
    },
    "tech": {
        "bg": "#060b14",
        "surface": "#0d1526",
        "accent": "#00d4ff",
        "text_primary": "#e8f4ff",
        "text_secondary": "#5a8ab0",
        "font_heading": "Space Grotesk",
        "font_body": "JetBrains Mono",
        "border_radius": "8px",
        "scene": "particle_field",
        "animation_speed": "medium",
        "keywords": ["tech", "saas", "startup", "software", "ai", "data", "cloud", "api", "platform"],
    },
    "minimal": {
        "bg": "#fafafa",
        "surface": "#ffffff",
        "accent": "#1a1a1a",
        "text_primary": "#111111",
        "text_secondary": "#666666",
        "font_heading": "DM Serif Display",
        "font_body": "DM Sans",
        "border_radius": "4px",
        "scene": "geometric_morph",
        "animation_speed": "slow",
        "keywords": ["minimal", "clean", "simple", "portfolio", "creative", "studio", "agency"],
    },
    "organic": {
        "bg": "#0f1a12",
        "surface": "#152218",
        "accent": "#4ade80",
        "text_primary": "#e8f5e9",
        "text_secondary": "#6aad7a",
        "font_heading": "Fraunces",
        "font_body": "Inter",
        "border_radius": "16px",
        "scene": "liquid_glass",
        "animation_speed": "very_slow",
        "keywords": ["nature", "organic", "sustainable", "health", "wellness", "green", "eco", "food"],
    },
    "bold": {
        "bg": "#0d0d0d",
        "surface": "#161616",
        "accent": "#ff3c3c",
        "text_primary": "#ffffff",
        "text_secondary": "#888888",
        "font_heading": "Bebas Neue",
        "font_body": "Inter",
        "border_radius": "0px",
        "scene": "particle_field",
        "animation_speed": "fast",
        "keywords": ["bold", "sport", "fitness", "gym", "energy", "powerful", "brand", "impact"],
    },
}

# ─── Data classes ─────────────────────────────────────────────────────────────

@dataclass
class ParsedBrief:
    style: str                  # luxury | tech | minimal | organic | bold
    industry: str               # detected industry
    primary_feel: str           # the emotional goal (e.g. "confident", "calm")
    color_palette: dict         # bg, surface, accent, text colors
    fonts: dict                 # heading, body
    hero_message: str           # main H1 derived from brief
    subheadline: str            # supporting text
    cta_text: str               # call to action button text
    scene_type: str             # Three.js scene template name
    animation_speed: str        # slow | medium | fast
    border_radius: str          # CSS border-radius value

    def to_dict(self) -> dict:
        return asdict(self)


# ─── BriefParser ──────────────────────────────────────────────────────────────

class BriefParser:
    """Parses a natural language brief into structured design decisions."""

    INDUSTRY_MAP: dict[str, list[str]] = {
        "Fashion & Luxury": ["fashion", "luxury", "watch", "jewelry", "couture", "designer"],
        "Technology": ["saas", "software", "ai", "startup", "tech", "platform", "api", "cloud"],
        "Health & Wellness": ["health", "wellness", "fitness", "gym", "nutrition", "medical"],
        "Food & Beverage": ["food", "restaurant", "cafe", "drink", "beverage", "organic"],
        "Creative Studio": ["studio", "agency", "design", "creative", "portfolio", "art"],
        "Finance": ["finance", "fintech", "banking", "investment", "crypto", "trading"],
        "Education": ["edu", "learning", "course", "academy", "university", "training"],
        "Real Estate": ["real estate", "property", "apartment", "home", "interior"],
    }

    FEEL_MAP: dict[str, list[str]] = {
        "confident & powerful": ["bold", "powerful", "strong", "impact", "dominant"],
        "elegant & refined": ["elegant", "luxury", "premium", "sophisticated", "exclusive"],
        "calm & trustworthy": ["minimal", "clean", "trust", "reliable", "professional"],
        "innovative & futuristic": ["future", "tech", "innovation", "cutting-edge", "next-gen"],
        "warm & inviting": ["organic", "warm", "natural", "friendly", "community", "cozy"],
    }

    def parse(self, brief: str) -> ParsedBrief:
        brief_lower = brief.lower()

        # Detect style
        style = self._detect_style(brief_lower)
        preset = STYLE_PRESETS[style]

        # Detect industry
        industry = self._detect_industry(brief_lower)

        # Detect feel
        feel = self._detect_feel(brief_lower)

        # Generate content from brief
        hero_message = self._extract_hero_message(brief, style, industry)
        subheadline = self._generate_subheadline(industry, feel, style)
        cta_text = self._generate_cta(industry)

        return ParsedBrief(
            style=style,
            industry=industry,
            primary_feel=feel,
            color_palette={
                "bg": preset["bg"],
                "surface": preset["surface"],
                "accent": preset["accent"],
                "text_primary": preset["text_primary"],
                "text_secondary": preset["text_secondary"],
            },
            fonts={
                "heading": preset["font_heading"],
                "body": preset["font_body"],
            },
            hero_message=hero_message,
            subheadline=subheadline,
            cta_text=cta_text,
            scene_type=preset["scene"],
            animation_speed=preset["animation_speed"],
            border_radius=preset["border_radius"],
        )

    def _detect_style(self, brief_lower: str) -> str:
        scores: dict[str, int] = {name: 0 for name in STYLE_PRESETS}
        for name, preset in STYLE_PRESETS.items():
            scores[name] = sum(1 for kw in preset["keywords"] if kw in brief_lower)
        best = max(scores.items(), key=lambda x: x[1])
        return best[0] if best[1] > 0 else "tech"

    def _detect_industry(self, brief_lower: str) -> str:
        for industry, keywords in self.INDUSTRY_MAP.items():
            if any(kw in brief_lower for kw in keywords):
                return industry
        return "Technology"

    def _detect_feel(self, brief_lower: str) -> str:
        for feel, keywords in self.FEEL_MAP.items():
            if any(kw in brief_lower for kw in keywords):
                return feel
        return "innovative & futuristic"

    def _extract_hero_message(self, brief: str, style: str, industry: str) -> str:
        # Try to extract a key phrase from the brief
        sentences = re.split(r"[.!?]", brief.strip())
        if sentences:
            first = sentences[0].strip()
            if len(first) > 10:
                return first[:60].title()
        defaults = {
            "luxury": "Where Excellence Lives",
            "tech": "Build the Future, Today",
            "minimal": "Work That Speaks for Itself",
            "organic": "Live in Harmony",
            "bold": "Dominate Your Space",
        }
        return defaults.get(style, "The Next Big Thing")

    def _generate_subheadline(self, industry: str, feel: str, style: str) -> str:
        templates = {
            "luxury": f"Exceptional {industry} for those who demand the finest.",
            "tech": f"The platform that changes how {industry} works.",
            "minimal": f"Focused {industry}. Zero compromise.",
            "organic": f"Natural, sustainable {industry} for a better world.",
            "bold": f"The most {feel} {industry} brand you've never heard of.",
        }
        return templates.get(style, f"Premium {industry} — reimagined.")

    def _generate_cta(self, industry: str) -> str:
        cta_map = {
            "Technology": "Start Free Trial",
            "Fashion & Luxury": "Explore Collection",
            "Health & Wellness": "Start Your Journey",
            "Food & Beverage": "View Menu",
            "Creative Studio": "See Our Work",
            "Finance": "Get Started",
            "Education": "Enroll Now",
            "Real Estate": "View Properties",
        }
        return cta_map.get(industry, "Get Started")


# ─── Three.js Scene Templates ─────────────────────────────────────────────────

class ThreeJSSceneBuilder:
    """Generates Three.js JavaScript code for 3D hero scenes."""

    def build(self, scene_type: str, accent: str, animation_speed: str) -> str:
        speed_map = {"very_slow": 0.001, "slow": 0.003, "medium": 0.006, "fast": 0.012}
        speed = speed_map.get(animation_speed, 0.005)
        accent_rgb = self._hex_to_rgb(accent)

        scenes = {
            "floating_sphere": self._floating_sphere(accent_rgb, speed),
            "particle_field": self._particle_field(accent_rgb, speed),
            "geometric_morph": self._geometric_morph(accent_rgb, speed),
            "liquid_glass": self._liquid_glass(accent_rgb, speed),
        }
        return scenes.get(scene_type, scenes["particle_field"])

    def _hex_to_rgb(self, hex_color: str) -> tuple:
        h = hex_color.lstrip("#")
        return tuple(int(h[i:i+2], 16) / 255 for i in (0, 2, 4))

    def _floating_sphere(self, rgb: tuple, speed: float) -> str:
        r, g, b = rgb
        return f"""
// Scene: Floating Sphere — Luxury / Minimal
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(60, canvas.offsetWidth / canvas.offsetHeight, 0.1, 100);
const renderer = new THREE.WebGLRenderer({{ canvas, alpha: true, antialias: true }});
renderer.setPixelRatio(window.devicePixelRatio);
renderer.setSize(canvas.offsetWidth, canvas.offsetHeight);
camera.position.set(0, 0, 5);

// Sphere geometry
const geometry = new THREE.IcosahedronGeometry(1.5, 20);
const material = new THREE.MeshPhongMaterial({{
  color: new THREE.Color({r:.4f}, {g:.4f}, {b:.4f}),
  emissive: new THREE.Color({r*0.3:.4f}, {g*0.3:.4f}, {b*0.3:.4f}),
  shininess: 120,
  transparent: true,
  opacity: 0.85,
  wireframe: false,
}});
const sphere = new THREE.Mesh(geometry, material);
scene.add(sphere);

// Wireframe overlay
const wireMat = new THREE.MeshBasicMaterial({{
  color: new THREE.Color({r:.4f}, {g:.4f}, {b:.4f}),
  wireframe: true,
  transparent: true,
  opacity: 0.15,
}});
const wireframe = new THREE.Mesh(geometry, wireMat);
scene.add(wireframe);

// Lighting
const ambientLight = new THREE.AmbientLight(0xffffff, 0.3);
scene.add(ambientLight);
const pointLight = new THREE.PointLight(0xffffff, 2.0, 20);
pointLight.position.set(3, 3, 3);
scene.add(pointLight);
const pointLight2 = new THREE.PointLight(new THREE.Color({r:.4f}, {g:.4f}, {b:.4f}), 1.5, 15);
pointLight2.position.set(-3, -2, 2);
scene.add(pointLight2);

// Mouse parallax
let mouseX = 0, mouseY = 0;
window.addEventListener('mousemove', e => {{
  mouseX = (e.clientX / window.innerWidth - 0.5) * 2;
  mouseY = (e.clientY / window.innerHeight - 0.5) * 2;
}});

// Animation
let frame = 0;
function animate() {{
  requestAnimationFrame(animate);
  frame++;
  sphere.rotation.x += {speed:.5f};
  sphere.rotation.y += {speed * 1.3:.5f};
  wireframe.rotation.x -= {speed * 0.7:.5f};
  wireframe.rotation.y -= {speed:.5f};
  // Floating effect
  sphere.position.y = Math.sin(frame * {speed:.5f}) * 0.2;
  wireframe.position.y = sphere.position.y;
  // Mouse parallax
  camera.position.x += (mouseX * 0.5 - camera.position.x) * 0.05;
  camera.position.y += (-mouseY * 0.5 - camera.position.y) * 0.05;
  camera.lookAt(scene.position);
  renderer.render(scene, camera);
}}
animate();
window.addEventListener('resize', () => {{
  camera.aspect = canvas.offsetWidth / canvas.offsetHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(canvas.offsetWidth, canvas.offsetHeight);
}});
"""

    def _particle_field(self, rgb: tuple, speed: float) -> str:
        r, g, b = rgb
        return f"""
// Scene: Particle Field — Tech / Bold
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(75, canvas.offsetWidth / canvas.offsetHeight, 0.1, 100);
const renderer = new THREE.WebGLRenderer({{ canvas, alpha: true, antialias: true }});
renderer.setPixelRatio(window.devicePixelRatio);
renderer.setSize(canvas.offsetWidth, canvas.offsetHeight);
camera.position.set(0, 0, 6);

// Particles
const PARTICLE_COUNT = 3000;
const positions = new Float32Array(PARTICLE_COUNT * 3);
const speeds = new Float32Array(PARTICLE_COUNT);
for (let i = 0; i < PARTICLE_COUNT; i++) {{
  positions[i * 3]     = (Math.random() - 0.5) * 12;
  positions[i * 3 + 1] = (Math.random() - 0.5) * 12;
  positions[i * 3 + 2] = (Math.random() - 0.5) * 12;
  speeds[i] = Math.random() * 0.5 + 0.5;
}}

const geometry = new THREE.BufferGeometry();
geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
const material = new THREE.PointsMaterial({{
  color: new THREE.Color({r:.4f}, {g:.4f}, {b:.4f}),
  size: 0.04,
  transparent: true,
  opacity: 0.8,
  sizeAttenuation: true,
}});
const particles = new THREE.Points(geometry, material);
scene.add(particles);

// Connections mesh (lines between nearby particles)
const lineMat = new THREE.LineBasicMaterial({{
  color: new THREE.Color({r:.4f}, {g:.4f}, {b:.4f}),
  transparent: true,
  opacity: 0.08,
}});

let mouseX = 0, mouseY = 0;
window.addEventListener('mousemove', e => {{
  mouseX = (e.clientX / window.innerWidth - 0.5) * 2;
  mouseY = (e.clientY / window.innerHeight - 0.5) * 2;
}});

let frame = 0;
function animate() {{
  requestAnimationFrame(animate);
  frame++;
  const pos = geometry.attributes.position.array;
  for (let i = 0; i < PARTICLE_COUNT; i++) {{
    pos[i * 3 + 1] += speeds[i] * {speed * 0.2:.5f};
    if (pos[i * 3 + 1] > 6) pos[i * 3 + 1] = -6;
  }}
  geometry.attributes.position.needsUpdate = true;
  particles.rotation.y += {speed * 0.3:.5f};
  camera.position.x += (mouseX * 1.0 - camera.position.x) * 0.03;
  camera.position.y += (-mouseY * 1.0 - camera.position.y) * 0.03;
  camera.lookAt(scene.position);
  renderer.render(scene, camera);
}}
animate();
window.addEventListener('resize', () => {{
  camera.aspect = canvas.offsetWidth / canvas.offsetHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(canvas.offsetWidth, canvas.offsetHeight);
}});
"""

    def _geometric_morph(self, rgb: tuple, speed: float) -> str:
        r, g, b = rgb
        return f"""
// Scene: Geometric Morph — Minimal / Creative
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(60, canvas.offsetWidth / canvas.offsetHeight, 0.1, 100);
const renderer = new THREE.WebGLRenderer({{ canvas, alpha: true, antialias: true }});
renderer.setPixelRatio(window.devicePixelRatio);
renderer.setSize(canvas.offsetWidth, canvas.offsetHeight);
camera.position.set(0, 0, 5);

const shapes = [];
const geometries = [
  new THREE.TetrahedronGeometry(0.8, 0),
  new THREE.OctahedronGeometry(0.7, 0),
  new THREE.IcosahedronGeometry(0.6, 0),
];
for (let i = 0; i < 8; i++) {{
  const geo = geometries[i % geometries.length];
  const mat = new THREE.MeshPhongMaterial({{
    color: new THREE.Color({r:.4f}, {g:.4f}, {b:.4f}),
    transparent: true,
    opacity: 0.3 + (i * 0.05),
    wireframe: i % 2 === 0,
  }});
  const mesh = new THREE.Mesh(geo, mat);
  const angle = (i / 8) * Math.PI * 2;
  mesh.position.set(Math.cos(angle) * 2, Math.sin(angle) * 2, (Math.random() - 0.5) * 2);
  shapes.push({{ mesh, speed: 0.003 + i * 0.001, angle }});
  scene.add(mesh);
}}
const light = new THREE.DirectionalLight(0xffffff, 1.5);
light.position.set(5, 5, 5);
scene.add(light);
scene.add(new THREE.AmbientLight(0xffffff, 0.4));

let frame = 0;
function animate() {{
  requestAnimationFrame(animate);
  frame++;
  shapes.forEach((s, i) => {{
    s.mesh.rotation.x += s.speed;
    s.mesh.rotation.y += s.speed * 1.5;
    const a = s.angle + frame * {speed:.5f};
    s.mesh.position.x = Math.cos(a) * 2;
    s.mesh.position.y = Math.sin(a) * 2;
  }});
  renderer.render(scene, camera);
}}
animate();
window.addEventListener('resize', () => {{
  camera.aspect = canvas.offsetWidth / canvas.offsetHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(canvas.offsetWidth, canvas.offsetHeight);
}});
"""

    def _liquid_glass(self, rgb: tuple, speed: float) -> str:
        r, g, b = rgb
        return f"""
// Scene: Liquid Glass — Organic / Premium
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(55, canvas.offsetWidth / canvas.offsetHeight, 0.1, 100);
const renderer = new THREE.WebGLRenderer({{ canvas, alpha: true, antialias: true }});
renderer.setPixelRatio(window.devicePixelRatio);
renderer.setSize(canvas.offsetWidth, canvas.offsetHeight);
camera.position.set(0, 0, 5);

const blobs = [];
for (let i = 0; i < 5; i++) {{
  const geo = new THREE.SphereGeometry(0.6 + i * 0.15, 64, 64);
  const mat = new THREE.MeshPhongMaterial({{
    color: new THREE.Color({r:.4f} + i * 0.05, {g:.4f} + i * 0.03, {b:.4f}),
    emissive: new THREE.Color({r*0.2:.4f}, {g*0.2:.4f}, {b*0.2:.4f}),
    transparent: true,
    opacity: 0.35 - i * 0.04,
    shininess: 200,
  }});
  const mesh = new THREE.Mesh(geo, mat);
  blobs.push({{ mesh, phase: (i / 5) * Math.PI * 2, radius: 1.0 + i * 0.3 }});
  scene.add(mesh);
}}

const light1 = new THREE.PointLight(0xffffff, 2.5, 20);
light1.position.set(3, 3, 4);
scene.add(light1);
const light2 = new THREE.PointLight(new THREE.Color({r:.4f}, {g:.4f}, {b:.4f}), 1.5, 15);
light2.position.set(-3, -2, 2);
scene.add(light2);
scene.add(new THREE.AmbientLight(0xffffff, 0.2));

let frame = 0;
function animate() {{
  requestAnimationFrame(animate);
  frame++;
  blobs.forEach(b => {{
    const t = frame * {speed:.5f} + b.phase;
    b.mesh.position.x = Math.cos(t) * b.radius * 0.7;
    b.mesh.position.y = Math.sin(t * 1.3) * b.radius * 0.5;
    b.mesh.position.z = Math.sin(t * 0.7) * 0.5;
    b.mesh.rotation.x += {speed * 0.5:.5f};
    b.mesh.rotation.y += {speed * 0.7:.5f};
  }});
  renderer.render(scene, camera);
}}
animate();
window.addEventListener('resize', () => {{
  camera.aspect = canvas.offsetWidth / canvas.offsetHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(canvas.offsetWidth, canvas.offsetHeight);
}});
"""


# ─── WebsiteAssembler ─────────────────────────────────────────────────────────

class WebsiteAssembler:
    """Combines design system + Three.js scene into a single production HTML file."""

    def assemble(self, brief: ParsedBrief, scene_js: str) -> str:
        pal = brief.color_palette
        fonts = brief.fonts
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{brief.hero_message} | Generated by JARVIS BRAINIAC</title>
<meta name="description" content="{brief.subheadline}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family={fonts['heading'].replace(' ', '+')}:wght@400;700;900&family={fonts['body'].replace(' ', '+')}:wght@300;400;500;600&display=swap" rel="stylesheet">
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

  :root {{
    --bg: {pal['bg']};
    --surface: {pal['surface']};
    --accent: {pal['accent']};
    --text: {pal['text_primary']};
    --text-muted: {pal['text_secondary']};
    --radius: {brief.border_radius};
    --font-h: '{fonts['heading']}', serif;
    --font-b: '{fonts['body']}', sans-serif;
    --transition: cubic-bezier(0.16, 1, 0.3, 1);
  }}

  html {{ scroll-behavior: smooth; }}
  body {{
    background: var(--bg);
    color: var(--text);
    font-family: var(--font-b);
    min-height: 100vh;
    overflow-x: hidden;
  }}

  /* ─── Navigation ────────────────────── */
  nav {{
    position: fixed;
    top: 0; left: 0; right: 0;
    z-index: 100;
    padding: 1.5rem 4rem;
    display: flex;
    justify-content: space-between;
    align-items: center;
    background: linear-gradient(to bottom, {pal['bg']}ee, transparent);
    backdrop-filter: blur(8px);
  }}
  .nav-brand {{
    font-family: var(--font-h);
    font-size: 1.4rem;
    font-weight: 700;
    color: var(--text);
    text-decoration: none;
    letter-spacing: 0.05em;
  }}
  .nav-links {{
    display: flex;
    gap: 2.5rem;
    list-style: none;
  }}
  .nav-links a {{
    color: var(--text-muted);
    text-decoration: none;
    font-size: 0.875rem;
    font-weight: 500;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    transition: color 0.3s var(--transition);
  }}
  .nav-links a:hover {{ color: var(--accent); }}

  /* ─── Hero ──────────────────────────── */
  .hero {{
    position: relative;
    height: 100vh;
    display: grid;
    grid-template-columns: 1fr 1fr;
    align-items: center;
    overflow: hidden;
  }}

  .hero-content {{
    position: relative;
    z-index: 2;
    padding: 0 4rem;
    animation: fadeInUp 1.2s var(--transition) both;
  }}

  .hero-tag {{
    display: inline-block;
    font-size: 0.75rem;
    font-weight: 600;
    letter-spacing: 0.2em;
    text-transform: uppercase;
    color: var(--accent);
    border: 1px solid {pal['accent']}44;
    padding: 0.4rem 1rem;
    border-radius: var(--radius);
    margin-bottom: 2rem;
  }}

  h1 {{
    font-family: var(--font-h);
    font-size: clamp(2.5rem, 5vw, 5rem);
    font-weight: 900;
    line-height: 1.05;
    letter-spacing: -0.02em;
    margin-bottom: 1.5rem;
    background: linear-gradient(135deg, var(--text) 0%, var(--text-muted) 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
  }}

  .hero-sub {{
    font-size: 1.125rem;
    color: var(--text-muted);
    line-height: 1.7;
    max-width: 42ch;
    margin-bottom: 3rem;
  }}

  .hero-actions {{
    display: flex;
    gap: 1rem;
    align-items: center;
  }}

  .btn-primary {{
    padding: 1rem 2.5rem;
    background: var(--accent);
    color: {pal['bg']};
    border: none;
    border-radius: var(--radius);
    font-family: var(--font-b);
    font-size: 0.9rem;
    font-weight: 600;
    letter-spacing: 0.05em;
    cursor: pointer;
    transition: all 0.3s var(--transition);
    text-decoration: none;
  }}
  .btn-primary:hover {{
    transform: translateY(-2px);
    box-shadow: 0 12px 40px {pal['accent']}44;
  }}

  .btn-ghost {{
    padding: 1rem 2rem;
    background: transparent;
    color: var(--text-muted);
    border: 1px solid {pal['text_secondary']}44;
    border-radius: var(--radius);
    font-family: var(--font-b);
    font-size: 0.9rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.3s var(--transition);
    text-decoration: none;
  }}
  .btn-ghost:hover {{ color: var(--text); border-color: var(--accent); }}

  /* ─── 3D Canvas ─────────────────────── */
  .hero-canvas-wrap {{
    position: relative;
    height: 100%;
  }}
  #hero-canvas {{
    width: 100%;
    height: 100%;
    display: block;
  }}

  /* Background gradient orbs */
  .orb {{
    position: fixed;
    border-radius: 50%;
    filter: blur(100px);
    opacity: 0.12;
    pointer-events: none;
  }}
  .orb-1 {{
    width: 600px; height: 600px;
    background: {pal['accent']};
    top: -200px; right: -100px;
    animation: orbFloat 8s ease-in-out infinite;
  }}
  .orb-2 {{
    width: 400px; height: 400px;
    background: {pal['accent']};
    bottom: -100px; left: -100px;
    animation: orbFloat 10s ease-in-out infinite reverse;
  }}

  /* ─── Stats bar ─────────────────────── */
  .stats-bar {{
    position: relative;
    z-index: 2;
    border-top: 1px solid {pal['text_secondary']}22;
    border-bottom: 1px solid {pal['text_secondary']}22;
    padding: 3rem 4rem;
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 2rem;
    background: {pal['surface']}88;
    backdrop-filter: blur(12px);
  }}
  .stat {{
    text-align: center;
  }}
  .stat-value {{
    font-family: var(--font-h);
    font-size: 3rem;
    font-weight: 900;
    color: var(--accent);
    line-height: 1;
  }}
  .stat-label {{
    font-size: 0.8rem;
    color: var(--text-muted);
    letter-spacing: 0.1em;
    text-transform: uppercase;
    margin-top: 0.5rem;
  }}

  /* ─── Features section ──────────────── */
  .features {{
    padding: 8rem 4rem;
    max-width: 1200px;
    margin: 0 auto;
  }}
  .section-label {{
    font-size: 0.75rem;
    font-weight: 600;
    letter-spacing: 0.2em;
    text-transform: uppercase;
    color: var(--accent);
    margin-bottom: 1rem;
  }}
  .section-title {{
    font-family: var(--font-h);
    font-size: clamp(2rem, 3.5vw, 3.5rem);
    font-weight: 800;
    margin-bottom: 4rem;
    max-width: 20ch;
  }}
  .feature-grid {{
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 2rem;
  }}
  .feature-card {{
    padding: 2.5rem;
    background: {pal['surface']};
    border: 1px solid {pal['text_secondary']}18;
    border-radius: calc(var(--radius) * 4);
    transition: all 0.4s var(--transition);
    cursor: default;
  }}
  .feature-card:hover {{
    border-color: {pal['accent']}44;
    transform: translateY(-4px);
    box-shadow: 0 20px 60px {pal['accent']}18;
  }}
  .feature-icon {{
    width: 48px; height: 48px;
    background: {pal['accent']}18;
    border-radius: var(--radius);
    display: flex; align-items: center; justify-content: center;
    font-size: 1.4rem;
    margin-bottom: 1.5rem;
  }}
  .feature-title {{
    font-family: var(--font-h);
    font-size: 1.25rem;
    font-weight: 700;
    margin-bottom: 0.75rem;
  }}
  .feature-desc {{
    font-size: 0.9rem;
    color: var(--text-muted);
    line-height: 1.7;
  }}

  /* ─── CTA Section ───────────────────── */
  .cta-section {{
    padding: 8rem 4rem;
    text-align: center;
    background: {pal['surface']};
    border-top: 1px solid {pal['text_secondary']}18;
    border-bottom: 1px solid {pal['text_secondary']}18;
  }}
  .cta-section h2 {{
    font-family: var(--font-h);
    font-size: clamp(2.5rem, 4vw, 4rem);
    font-weight: 900;
    margin-bottom: 1.5rem;
  }}
  .cta-section p {{
    color: var(--text-muted);
    font-size: 1.125rem;
    max-width: 50ch;
    margin: 0 auto 3rem;
    line-height: 1.7;
  }}

  /* ─── Footer ────────────────────────── */
  footer {{
    padding: 3rem 4rem;
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 0.85rem;
    color: var(--text-muted);
    border-top: 1px solid {pal['text_secondary']}18;
  }}

  /* ─── Animations ────────────────────── */
  @keyframes fadeInUp {{
    from {{ opacity: 0; transform: translateY(30px); }}
    to   {{ opacity: 1; transform: translateY(0); }}
  }}
  @keyframes orbFloat {{
    0%, 100% {{ transform: translate(0, 0) scale(1); }}
    50%       {{ transform: translate(30px, -30px) scale(1.05); }}
  }}

  /* Scroll reveal */
  .reveal {{ opacity: 0; transform: translateY(20px); transition: all 0.8s var(--transition); }}
  .reveal.visible {{ opacity: 1; transform: translateY(0); }}

  /* ─── Responsive ────────────────────── */
  @media (max-width: 768px) {{
    nav {{ padding: 1.2rem 1.5rem; }}
    .nav-links {{ display: none; }}
    .hero {{ grid-template-columns: 1fr; height: auto; min-height: 100vh; }}
    .hero-content {{ padding: 8rem 1.5rem 2rem; }}
    .hero-canvas-wrap {{ height: 50vh; }}
    .stats-bar {{ grid-template-columns: 1fr; padding: 2rem 1.5rem; text-align: center; }}
    .features {{ padding: 4rem 1.5rem; }}
    .feature-grid {{ grid-template-columns: 1fr; }}
    .cta-section {{ padding: 4rem 1.5rem; }}
    footer {{ flex-direction: column; gap: 1rem; text-align: center; padding: 2rem 1.5rem; }}
  }}
</style>
</head>
<body>

<!-- Background orbs -->
<div class="orb orb-1"></div>
<div class="orb orb-2"></div>

<!-- Navigation -->
<nav>
  <a href="#" class="nav-brand">{brief.industry.split('&')[0].strip()}</a>
  <ul class="nav-links">
    <li><a href="#features">Features</a></li>
    <li><a href="#about">About</a></li>
    <li><a href="#contact">Contact</a></li>
  </ul>
  <a href="#cta" class="btn-primary" style="padding:0.7rem 1.5rem;font-size:0.8rem;">{brief.cta_text}</a>
</nav>

<!-- Hero -->
<section class="hero">
  <div class="hero-content">
    <div class="hero-tag">{brief.industry} · {brief.style.title()}</div>
    <h1>{brief.hero_message}</h1>
    <p class="hero-sub">{brief.subheadline}</p>
    <div class="hero-actions">
      <a href="#cta" class="btn-primary">{brief.cta_text}</a>
      <a href="#features" class="btn-ghost">Learn More →</a>
    </div>
  </div>
  <div class="hero-canvas-wrap">
    <canvas id="hero-canvas"></canvas>
  </div>
</section>

<!-- Stats -->
<div class="stats-bar reveal" id="features">
  <div class="stat">
    <div class="stat-value">10×</div>
    <div class="stat-label">Faster Delivery</div>
  </div>
  <div class="stat">
    <div class="stat-value">100%</div>
    <div class="stat-label">Client Satisfaction</div>
  </div>
  <div class="stat">
    <div class="stat-value">3D</div>
    <div class="stat-label">Premium Experience</div>
  </div>
</div>

<!-- Features -->
<section class="features">
  <div class="section-label">What We Offer</div>
  <h2 class="section-title">Built Different. By Design.</h2>
  <div class="feature-grid">
    <div class="feature-card reveal">
      <div class="feature-icon">⚡</div>
      <div class="feature-title">Lightning Fast</div>
      <p class="feature-desc">Optimized for performance from day one. Every millisecond counts when you're competing at the top.</p>
    </div>
    <div class="feature-card reveal">
      <div class="feature-icon">🎯</div>
      <div class="feature-title">Precision Crafted</div>
      <p class="feature-desc">Every decision is intentional. No filler, no compromise. Just exactly what the experience demands.</p>
    </div>
    <div class="feature-card reveal">
      <div class="feature-icon">🌐</div>
      <div class="feature-title">Global Scale</div>
      <p class="feature-desc">Infrastructure that grows with you. From launch day to millions of users, we scale seamlessly.</p>
    </div>
  </div>
</section>

<!-- CTA -->
<section class="cta-section" id="cta">
  <h2>Ready to Start?</h2>
  <p>{brief.subheadline} Let's build something extraordinary together.</p>
  <a href="#" class="btn-primary" style="font-size:1rem;padding:1.2rem 3rem;">{brief.cta_text} →</a>
</section>

<!-- Footer -->
<footer>
  <span>© 2026 · {brief.industry.split('&')[0].strip()}</span>
  <span style="color:var(--accent);font-size:0.75rem;letter-spacing:0.1em;">BUILT WITH JARVIS BRAINIAC</span>
  <span>Privacy · Terms</span>
</footer>

<!-- Three.js CDN -->
<script src="https://cdn.jsdelivr.net/npm/three@0.162.0/build/three.min.js"></script>
<script>
  // ─── 3D Scene ───────────────────────────────────────────────
  const canvas = document.getElementById('hero-canvas');
  if (canvas && window.THREE) {{
    {scene_js}
  }}

  // ─── Scroll Reveal ──────────────────────────────────────────
  const reveals = document.querySelectorAll('.reveal');
  const observer = new IntersectionObserver(entries => {{
    entries.forEach(e => {{
      if (e.isIntersecting) {{
        e.target.classList.add('visible');
        observer.unobserve(e.target);
      }}
    }});
  }}, {{ threshold: 0.1 }});
  reveals.forEach(el => observer.observe(el));

  // ─── Smooth number counter ──────────────────────────────────
  document.querySelectorAll('.stat-value').forEach(el => {{
    const text = el.textContent;
    const num = parseFloat(text.replace(/[^0-9.]/g, ''));
    const suffix = text.replace(/[0-9.]/g, '');
    if (!isNaN(num)) {{
      let start = 0;
      const step = num / 60;
      const timer = setInterval(() => {{
        start += step;
        if (start >= num) {{ el.textContent = text; clearInterval(timer); }}
        else {{ el.textContent = Math.floor(start) + suffix; }}
      }}, 16);
    }}
  }});
</script>
</body>
</html>"""


# ─── WebsiteBuilder (orchestrator) ───────────────────────────────────────────

class WebsiteBuilder:
    """
    Main entry point: takes a brand brief string, runs the full pipeline,
    and returns a complete standalone HTML string.
    """

    def __init__(self, output_dir: Path | None = None):
        self.output_dir = output_dir
        self.parser = BriefParser()
        self.scene_builder = ThreeJSSceneBuilder()
        self.assembler = WebsiteAssembler()

    def build(self, brief: str, style_override: str | None = None) -> tuple[str, ParsedBrief]:
        """
        Build a complete 3D website from a brief.
        Returns (html_string, parsed_brief).
        """
        log.info("WebsiteBuilder: parsing brief (%d chars)", len(brief))
        parsed = self.parser.parse(brief)
        if style_override and style_override in STYLE_PRESETS:
            # Override style with preset
            preset = STYLE_PRESETS[style_override]
            parsed.style = style_override
            parsed.color_palette = {
                "bg": preset["bg"], "surface": preset["surface"],
                "accent": preset["accent"], "text_primary": preset["text_primary"],
                "text_secondary": preset["text_secondary"],
            }
            parsed.fonts = {"heading": preset["font_heading"], "body": preset["font_body"]}
            parsed.scene_type = preset["scene"]
            parsed.animation_speed = preset["animation_speed"]
            parsed.border_radius = preset["border_radius"]

        log.info("WebsiteBuilder: style=%s scene=%s", parsed.style, parsed.scene_type)
        scene_js = self.scene_builder.build(parsed.scene_type, parsed.color_palette["accent"], parsed.animation_speed)
        html = self.assembler.assemble(parsed, scene_js)

        if self.output_dir:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            fname = re.sub(r"[^a-z0-9_-]", "_", brief.lower()[:25]).strip("_")
            out_path = self.output_dir / f"{fname}_{parsed.style}.html"
            out_path.write_text(html, encoding="utf-8")
            log.info("WebsiteBuilder: saved to %s", out_path)

        return html, parsed
