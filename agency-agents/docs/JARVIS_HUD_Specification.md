# JARVIS HUD — Authoritative Spec (operator-uploaded 2026-05-03)

This is the canonical movie-accurate HUD specification used by `jarvis_os/hud/iron_hud.py`.

## 1. Color palette
| Token | Hex | Usage |
|---|---|---|
| Primary cyan | `#00FFFF` | Arc reactor core, primary highlights |
| Cyan alt | `#00D9FF` | Softer cyan (VS Code JARVIS theme) |
| Electric blue | `#4D9FFF` | Secondary UI / data streams |
| Deep blue | `#0A1628` | Panel backgrounds |
| Dark navy | `#050D1A` | Status bar bg |
| White | `#FFFFFF` | Text, inner-ring accents |
| Success green | `#00FF9F` | OK indicators |
| Warn orange | `#FFA500` | Pause states |
| Alert red | `#FF4757` | Errors / damage |
| Yellow | `#FFD95A` | Numbers / cautionary |
| Stark red | `#FF0040` | Iron Man weapon mode |
| Stark gold | `#FFD700` | Suit power / premium |

## 2. Typography
- Eurostile Bold Extended (canonical) / Bank Gothic (Iron Man 3 secondary) /
  **Orbitron** (free alternative) / Stark / CGF Arch Reactor / Jura
- Monospace (Fira Code / JetBrains Mono / Consolas) for telemetry/coords
- ALL CAPS for labels; bad kerning intentional on some labels (e.g. `AUDIO ANAL YSIS`)

## 3. Arc reactor geometry (verbatim)
| Ring | Radius | Width | Style | Rotation | Color |
|---|---:|---:|---|---|---|
| Outer bracket | 130 | 3 | Two 90° arcs at 45° / 225° | static | cyan |
| Middle ring | 100 | 12 | Dashed [10,10] | CW +2°/frame | cyan |
| Inner ring | 70 | 4 | Dashed [5,5] | CCW −4°/frame | white |
| Core | 20 + sin(t)·5 | fill | Radial gradient | breathing pulse | cyan |

30 FPS QTimer (33 ms tick). Core color shifts cyan → orange when `active=False`.

## 4. Layout
- **Top bar** — horizontal compass + speed (MACH) + altimeter
- **Center** — arc reactor + data rings
- **Bottom gauges** — 5 persistent boxes (SUIT / TARG / RADAR / HORIZ / MAP)
- **Voice waveform** — 4-bar equalizer near bottom-center
- **Right** — chat / data overlay (cyan text boxes, semi-transparent)

## 5. Window
- `Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool`
- `WA_TranslucentBackground = True`
- Background `rgba(0,0,0,180)` semi-transparent black

## 6. Boot sequence (text)
1. `INITIALIZING NEURAL CORE`
2. `CALIBRATING HUD INTERFACE`
3. `SYNCING SYSTEM MODULES`
4. `LOADING LANGUAGE MATRIX`
5. `ESTABLISHING USER PROFILE`
6. `ACTIVATING J.A.R.V.I.S`

Greeting (after boot): `Good evening, Sir. All systems online. I am at your full disposal.`

## 7. Authority sources
- sci-fiinterfaces.com (Christopher Noessel, 5-part series)
- Typeset in the Future (Eurostile analysis)
- Project_JARVIS by ishit-chaudhari (working PyQt6 reference)
- JARVIS by Sidhant185 (most feature-rich; particle/bokeh layers)
- VS Code JARVIS-3D theme (color codes verified)

## 8. Implementation
`jarvis_os/hud/iron_hud.py` — full PyQt6 implementation per this spec.
Run: `python -m jarvis_os.hud.iron_hud`

Esc to exit.
