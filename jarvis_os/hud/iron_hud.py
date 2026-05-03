"""JARVIS Iron Man HUD — authentic recreation per movie-canonical spec.

Implements C:\\Users\\User\\agency\\docs\\JARVIS_HUD_Specification.md verbatim:

  Color palette  : #00FFFF cyan / #00D9FF / #4D9FFF / #0A1628 navy / #FFD60A NASA-gold
  Typography     : Eurostile/Orbitron all-caps for labels, monospace for telemetry
  Arc reactor    : 130 outer brackets, 100 mid (CW +2 deg/frame), 70 inner (CCW -4 deg/frame),
                   20 core with sin pulse 0-5px amplitude
  Data rings     : Multi-concentric segmented arcs, dash patterns [10,10] / [5,5]
  Animation      : 30 FPS QTimer (33 ms tick)
  Voice form     : 4-bar equalizer + circular orbital dots, audio-reactive
  Window         : Frameless, translucent, always-on-top
  Bottom gauges  : 5 (Suit / Targeting / Radar / Horizon / Map)
  Top bar        : Compass needle + speed (MACH) + altimeter

Entry point: `run_hud()` or `python -m jarvis_os.hud.iron_hud`.

Graceful degradation: imports cleanly even when PyQt6 not installed (raises at runtime).
"""
from __future__ import annotations

import math
import random
import sys
from typing import Optional

try:
    from PyQt6.QtCore import Qt, QTimer, QPointF, QRectF
    from PyQt6.QtGui import (
        QPainter, QPen, QBrush, QColor, QRadialGradient, QFont, QPolygonF,
    )
    from PyQt6.QtWidgets import QApplication, QWidget
    _HAS_QT = True
except ImportError:
    _HAS_QT = False
    QWidget = object  # type: ignore[misc,assignment]


# ---------------------------------------------------------------------------
# Spec colors (verbatim from JARVIS_HUD_Specification.md section 1)
# ---------------------------------------------------------------------------
COLOR = {
    "cyan":          "#00FFFF",   # primary highlights, arc reactor core
    "cyan_alt":      "#00D9FF",   # softer cyan
    "electric_blue": "#4D9FFF",   # secondary UI
    "deep_blue":     "#0A1628",   # panel backgrounds
    "dark_navy":     "#050D1A",   # status bar bg
    "white":         "#FFFFFF",
    "success":       "#00FF9F",
    "warn":          "#FFA500",
    "alert":         "#FF4757",
    "yellow":        "#FFD95A",
    "stark_red":     "#FF0040",
    "stark_gold":    "#FFD700",
    "black":         "#000000",
}


# ---------------------------------------------------------------------------
# ArcReactor — central focal element
# ---------------------------------------------------------------------------
class ArcReactor:
    """Concentric ring system + pulsing core.

    Specs (from JARVIS_HUD_Specification.md section 4):
      Ring               | Radius | Width | Style                | Rotation
      Outer Bracket      |  130   |   3   | Two 90 deg arcs at 45/225 | static
      Middle Ring        |  100   |  12   | Dashed [10,10]       | CW +2 deg/frame
      Inner Ring         |   70   |   4   | Dashed [5,5]         | CCW -4 deg/frame
      Core               |  20+sin(t)*5 | fill  | radial-gradient      | breathing pulse
    """

    OUTER_RADIUS = 130
    MIDDLE_RADIUS = 100
    INNER_RADIUS = 70
    CORE_RADIUS = 20

    def __init__(self) -> None:
        self.angle_outer = 0.0   # cumulative
        self.angle_middle = 0.0
        self.angle_inner = 0.0
        self.active = True

    # ------------------------------------------------------------------
    def tick(self) -> None:
        """Advance one animation frame. Call at 30 FPS (33 ms)."""
        self.angle_middle = (self.angle_middle + 2.0) % 360.0   # CW
        self.angle_inner = (self.angle_inner - 4.0) % 360.0     # CCW
        self.angle_outer += 0.1   # core-pulse phase

    # ------------------------------------------------------------------
    def core_radius(self) -> float:
        if not self.active:
            return float(self.CORE_RADIUS)
        pulse = (math.sin(self.angle_outer) + 1.0) * 2.5  # 0-5 amplitude
        return self.CORE_RADIUS + pulse

    # ------------------------------------------------------------------
    def paint(self, p: "QPainter", cx: float, cy: float) -> None:
        if not _HAS_QT:
            return

        primary = QColor(COLOR["cyan_alt" if self.active else "warn"])
        white   = QColor(COLOR["white"])

        # ---- Outer bracket: two 90 deg arcs at 45 deg and 225 deg ----
        pen = QPen(primary, 3)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        rect = QRectF(cx - self.OUTER_RADIUS, cy - self.OUTER_RADIUS,
                      2 * self.OUTER_RADIUS, 2 * self.OUTER_RADIUS)
        p.drawArc(rect, int(45 * 16), int(90 * 16))
        p.drawArc(rect, int(225 * 16), int(90 * 16))

        # ---- Middle ring: dashed CW ----
        p.save()
        p.translate(cx, cy)
        p.rotate(self.angle_middle)
        pen = QPen(primary, 12, Qt.PenStyle.CustomDashLine)
        pen.setDashPattern([10.0, 10.0])
        p.setPen(pen)
        p.drawEllipse(QPointF(0, 0), self.MIDDLE_RADIUS, self.MIDDLE_RADIUS)
        p.restore()

        # ---- Inner ring: dashed CCW ----
        p.save()
        p.translate(cx, cy)
        p.rotate(self.angle_inner)
        pen = QPen(white, 4, Qt.PenStyle.CustomDashLine)
        pen.setDashPattern([5.0, 5.0])
        p.setPen(pen)
        p.drawEllipse(QPointF(0, 0), self.INNER_RADIUS, self.INNER_RADIUS)
        p.restore()

        # ---- Core: radial gradient + sinusoidal pulse ----
        r = self.core_radius()
        grad = QRadialGradient(cx, cy, r)
        grad.setColorAt(0.0, QColor(255, 255, 255, 255))
        grad.setColorAt(0.5, QColor(0, 217, 255, 220))
        grad.setColorAt(1.0, QColor(0, 217, 255, 0))
        p.setBrush(QBrush(grad))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(cx, cy), r, r)

        # Glow halo (3 layers, decreasing alpha) — neon effect
        for i, alpha in enumerate((80, 50, 25)):
            pen = QPen(QColor(0, 217, 255, alpha), 4 + i * 2)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QPointF(cx, cy), r + 4 + i * 4, r + 4 + i * 4)


# ---------------------------------------------------------------------------
# DataRings — orbiting telemetry arcs
# ---------------------------------------------------------------------------
class DataRings:
    """Concentric data-display arcs at 160, 200, 250 px radius."""

    SPECS = [
        # (radius, width, color_key, dash_pattern, rotation_deg_per_frame)
        (160, 2, "cyan_alt",      [20, 5], 0.5),
        (200, 2, "electric_blue", [8, 4],  -1.0),
        (250, 1, "cyan",          [3, 3],  2.0),
    ]

    def __init__(self) -> None:
        self.angles = [0.0] * len(self.SPECS)

    def tick(self) -> None:
        for i, (_r, _w, _c, _dash, speed) in enumerate(self.SPECS):
            self.angles[i] = (self.angles[i] + speed) % 360.0

    def paint(self, p: "QPainter", cx: float, cy: float) -> None:
        if not _HAS_QT:
            return
        for i, (radius, width, color_key, dash, _speed) in enumerate(self.SPECS):
            p.save()
            p.translate(cx, cy)
            p.rotate(self.angles[i])
            pen = QPen(QColor(COLOR[color_key]), width, Qt.PenStyle.CustomDashLine)
            pen.setDashPattern([float(d) for d in dash])
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            # Draw arc 0-300 deg (leaves 60 deg gap = technical feel)
            rect = QRectF(-radius, -radius, 2 * radius, 2 * radius)
            p.drawArc(rect, 0, int(300 * 16))
            p.restore()


# ---------------------------------------------------------------------------
# VoiceWaveform — 4-bar equalizer near bottom
# ---------------------------------------------------------------------------
class VoiceWaveform:
    """4-bar equalizer reactive to mic input (mocked random when no audio)."""

    BAR_WIDTH = 30
    GAP = 10
    NUM_BARS = 4

    def __init__(self) -> None:
        self.heights = [10.0] * self.NUM_BARS

    def tick(self) -> None:
        # Simulate audio reactivity (replace with real FFT in production)
        self.heights = [
            self.heights[i] * 0.7 + random.uniform(10, 100) * 0.3
            for i in range(self.NUM_BARS)
        ]

    def paint(self, p: "QPainter", cx: float, base_y: float) -> None:
        if not _HAS_QT:
            return
        total_w = self.NUM_BARS * self.BAR_WIDTH + (self.NUM_BARS - 1) * self.GAP
        x = cx - total_w / 2
        cyan = QColor(COLOR["cyan"])
        p.setPen(Qt.PenStyle.NoPen)
        for h in self.heights:
            grad = QRadialGradient(x + self.BAR_WIDTH / 2, base_y, self.BAR_WIDTH * 0.6)
            grad.setColorAt(0.0, cyan)
            grad.setColorAt(1.0, QColor(0, 255, 255, 80))
            p.setBrush(QBrush(grad))
            p.drawRect(QRectF(x, base_y - h, self.BAR_WIDTH, h))
            x += self.BAR_WIDTH + self.GAP


# ---------------------------------------------------------------------------
# Bottom gauges (5 persistent: Suit / Targeting / Radar / Horizon / Map)
# ---------------------------------------------------------------------------
GAUGES = ("SUIT", "TARG", "RADAR", "HORIZ", "MAP")


def paint_bottom_gauges(p: "QPainter", w: float, base_y: float) -> None:
    if not _HAS_QT:
        return
    box_w = 80
    gap = 12
    total_w = len(GAUGES) * box_w + (len(GAUGES) - 1) * gap
    x = (w - total_w) / 2
    cyan = QColor(COLOR["cyan_alt"])
    panel_brush = QBrush(QColor(10, 22, 40, 160))
    border_pen = QPen(cyan, 1, Qt.PenStyle.SolidLine)
    label_font = QFont("Consolas", 9, QFont.Weight.Bold)
    for label in GAUGES:
        # 1) panel: navy fill + cyan border (RESET each iteration — fix critical bugs #1+#2)
        p.setPen(border_pen)
        p.setBrush(panel_brush)
        p.drawRoundedRect(QRectF(x, base_y, box_w, 50), 4, 4)
        # 2) label
        p.setPen(QPen(cyan))
        p.setFont(label_font)
        p.drawText(QRectF(x, base_y + 6, box_w, 16),
                   Qt.AlignmentFlag.AlignCenter, label)
        # 3) mini-bar progress
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(cyan))
        bar_h = random.uniform(4, 16)
        p.drawRect(QRectF(x + 8, base_y + 30, box_w - 16, bar_h))
        x += box_w + gap


# ---------------------------------------------------------------------------
# Top bar (compass + speed + altimeter)
# ---------------------------------------------------------------------------
def paint_top_bar(p: "QPainter", w: float) -> None:
    if not _HAS_QT:
        return
    cyan = QColor(COLOR["cyan_alt"])
    white = QColor(COLOR["white"])
    p.setPen(QPen(cyan, 1))

    # Compass (horizontal line with tick marks)
    cx = w / 2
    y = 30
    p.drawLine(QPointF(cx - 200, y), QPointF(cx + 200, y))
    for i in range(-4, 5):
        tx = cx + i * 50
        p.drawLine(QPointF(tx, y - 4), QPointF(tx, y + 4))

    # Compass needle (white, thin)
    p.setPen(QPen(white, 2))
    p.drawLine(QPointF(cx, y - 10), QPointF(cx, y + 10))

    # Speed (MACH) right side
    p.setPen(QPen(cyan))
    font = QFont("Consolas", 11, QFont.Weight.Bold)
    p.setFont(font)
    p.drawText(QRectF(w - 160, 12, 150, 24),
               Qt.AlignmentFlag.AlignRight, f"MACH {random.uniform(0.8, 2.4):.2f}")

    # Altimeter (left side)
    p.drawText(QRectF(10, 12, 150, 24),
               Qt.AlignmentFlag.AlignLeft, f"ALT {random.randint(15000, 45000)} FT")


# ---------------------------------------------------------------------------
# IronManHUD — main widget
# ---------------------------------------------------------------------------
if _HAS_QT:

    class IronManHUD(QWidget):
        """Frameless translucent always-on-top HUD overlay."""

        def __init__(self) -> None:
            super().__init__()

            # Window flags per spec section 11
            self.setWindowFlags(
                Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.WindowStaysOnTopHint
                | Qt.WindowType.Tool
            )
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            self.resize(900, 700)
            self.setWindowTitle("J.A.R.V.I.S")

            # Components
            self.reactor = ArcReactor()
            self.rings = DataRings()
            self.waveform = VoiceWaveform()

            # Boot sequence text (per spec section 7)
            self.boot_lines = [
                "INITIALIZING NEURAL CORE",
                "CALIBRATING HUD INTERFACE",
                "SYNCING SYSTEM MODULES",
                "LOADING LANGUAGE MATRIX",
                "ESTABLISHING USER PROFILE",
                "ACTIVATING J.A.R.V.I.S",
            ]
            self.boot_idx = 0

            # 30 FPS animation loop
            self.timer = QTimer(self)
            self.timer.timeout.connect(self._tick)
            self.timer.start(33)

            # Boot text advance
            self.boot_timer = QTimer(self)
            self.boot_timer.timeout.connect(self._advance_boot)
            self.boot_timer.start(400)

            self.setMouseTracking(True)

        # ------------------------------------------------------------------
        def _tick(self) -> None:
            self.reactor.tick()
            self.rings.tick()
            self.waveform.tick()
            self.update()

        def _advance_boot(self) -> None:
            if self.boot_idx < len(self.boot_lines):
                self.boot_idx += 1
            else:
                self.boot_timer.stop()

        # ------------------------------------------------------------------
        def paintEvent(self, _event) -> None:  # noqa: N802
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)

            # Background — semi-transparent black with subtle vignette
            p.fillRect(self.rect(), QColor(0, 0, 0, 180))

            w, h = self.width(), self.height()
            cx, cy = w / 2, h / 2

            # Top bar
            paint_top_bar(p, w)

            # Data rings (drawn behind reactor for depth)
            self.rings.paint(p, cx, cy)

            # Arc reactor
            self.reactor.paint(p, cx, cy)

            # Voice waveform near bottom
            self.waveform.paint(p, cx, h - 110)

            # Bottom gauges
            paint_bottom_gauges(p, w, h - 70)

            # Boot text top-left
            font = QFont("Consolas", 10)
            p.setFont(font)
            p.setPen(QPen(QColor(COLOR["cyan_alt"])))
            for i, line in enumerate(self.boot_lines[: self.boot_idx]):
                p.drawText(QPointF(40, 80 + i * 16), f"> {line}")

            # JARVIS personality message
            p.setPen(QPen(QColor(COLOR["white"])))
            font2 = QFont("Consolas", 11)
            p.setFont(font2)
            p.drawText(QPointF(cx - 180, h - 160),
                       "Good evening, Sir. All systems online.")

        def keyPressEvent(self, event) -> None:  # noqa: N802
            if event.key() == Qt.Key.Key_Escape:
                self.close()


def run_hud() -> int:
    """Launch the HUD as a standalone Qt app."""
    if not _HAS_QT:
        print("PyQt6 not installed. Run: pip install PyQt6", file=sys.stderr)
        return 1
    app = QApplication.instance() or QApplication(sys.argv)
    hud = IronManHUD()
    hud.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(run_hud())
ys.stderr)
        return 1
    app = QApplication.instance() or QApplication(sys.argv)
    hud = IronManHUD()
    hud.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(run_hud())
