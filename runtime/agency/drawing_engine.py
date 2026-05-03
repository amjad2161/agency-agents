#!/usr/bin/env python3
"""
JARVIS Drawing/Sketch Engine
============================
Local visual explanation engine. Creates diagrams, flowcharts, mind maps,
technical drawings, and visual aids using matplotlib, PIL, and SVG.

100% local — matplotlib, PIL, SVG. No external APIs.

Classes
-------
DrawingEngine    : Full-featured visual engine
MockDrawingEngine: Same interface, creates placeholder images

Factory
-------
get_drawing_engine() -> Returns the best available engine

Author : JARVIS Agency
License: MIT
"""

from __future__ import annotations

import os
import sys
import math
import json
import textwrap
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any, Union

# ---------------------------------------------------------------------------
# Optional third-party libraries (soft deps)
# ---------------------------------------------------------------------------
_has_mpl = False
_has_pil = False
_has_svgwrite = False

# ── matplotlib ──────────────────────────────────────────────────────────────
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    import matplotlib.patheffects as pe
    from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Circle, Ellipse, Polygon, Wedge
    import matplotlib.patheffects as PathEffects
    _has_mpl = True
except Exception:  # pragma: no cover
    _has_mpl = False

# ── Pillow ──────────────────────────────────────────────────────────────────
try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance, ImageChops
    _has_pil = True
except Exception:  # pragma: no cover
    _has_pil = False

# ── svgwrite ────────────────────────────────────────────────────────────────
try:
    import svgwrite
    _has_svgwrite = True
except Exception:  # pragma: no cover
    _has_svgwrite = False

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------
__version__ = "1.0.0"
__all__ = [
    "DrawingEngine",
    "MockDrawingEngine",
    "get_drawing_engine",
]

# ---------------------------------------------------------------------------
# Color Schemes
# ---------------------------------------------------------------------------

TECHNICAL_COLORS: Dict[str, Any] = {
    "name": "TECHNICAL",
    "primary": "#1f4e79",
    "secondary": "#2e75b6",
    "accent": "#5b9bd5",
    "background": "#ffffff",
    "text": "#2c3e50",
    "light": "#dce6f1",
    "dark": "#1a252f",
    "success": "#27ae60",
    "warning": "#f39c12",
    "error": "#c0392b",
    "palette": ["#1f4e79", "#2e75b6", "#5b9bd5", "#70ad47", "#ed7d31", "#a5a5a5"],
    "box_style": "round,pad=0.5",
    "font_family": "DejaVu Sans",
    "title_font": {"size": 16, "weight": "bold"},
    "body_font": {"size": 10, "weight": "normal"},
}

CREATIVE_COLORS: Dict[str, Any] = {
    "name": "CREATIVE",
    "primary": "#e67e22",
    "secondary": "#9b59b6",
    "accent": "#1abc9c",
    "background": "#fdf6e3",
    "text": "#2c3e50",
    "light": "#fdebd0",
    "dark": "#6c3483",
    "success": "#2ecc71",
    "warning": "#f1c40f",
    "error": "#e74c3c",
    "palette": ["#e67e22", "#9b59b6", "#1abc9c", "#e74c3c", "#3498db", "#f1c40f"],
    "box_style": "round,pad=0.6",
    "font_family": "DejaVu Sans",
    "title_font": {"size": 18, "weight": "bold"},
    "body_font": {"size": 11, "weight": "normal"},
}

MINIMAL_COLORS: Dict[str, Any] = {
    "name": "MINIMAL",
    "primary": "#000000",
    "secondary": "#333333",
    "accent": "#666666",
    "background": "#ffffff",
    "text": "#000000",
    "light": "#f5f5f5",
    "dark": "#000000",
    "success": "#333333",
    "warning": "#666666",
    "error": "#000000",
    "palette": ["#000000", "#444444", "#888888", "#bbbbbb", "#dddddd", "#eeeeee"],
    "box_style": "square,pad=0.4",
    "font_family": "monospace",
    "title_font": {"size": 14, "weight": "bold"},
    "body_font": {"size": 9, "weight": "normal"},
}

COLORFUL_COLORS: Dict[str, Any] = {
    "name": "COLORFUL",
    "primary": "#e53935",
    "secondary": "#1e88e5",
    "accent": "#43a047",
    "background": "#fafafa",
    "text": "#212121",
    "light": "#e3f2fd",
    "dark": "#0d47a1",
    "success": "#43a047",
    "warning": "#fdd835",
    "error": "#e53935",
    "palette": [
        "#e53935", "#1e88e5", "#43a047", "#fdd835", "#8e24aa",
        "#fb8c00", "#00acc1", "#3949ab", "#7cb342", "#f4511e",
    ],
    "box_style": "round,pad=0.5",
    "font_family": "DejaVu Sans",
    "title_font": {"size": 16, "weight": "bold"},
    "body_font": {"size": 10, "weight": "normal"},
}

COLOR_SCHEMES = {
    "technical": TECHNICAL_COLORS,
    "creative": CREATIVE_COLORS,
    "minimal": MINIMAL_COLORS,
    "colorful": COLORFUL_COLORS,
}

# ---------------------------------------------------------------------------
# Unicode-safe fallbacks for common emoji/icon requests
# ---------------------------------------------------------------------------
_ICON_MAP = {
    "📊": "CHART",
    "📈": "TREND",
    "📉": "DOWN",
    "📝": "NOTE",
    "🔧": "WRENCH",
    "⚙️": "GEAR",
    "🔍": "SEARCH",
    "💡": "IDEA",
    "🚀": "ROCKET",
    "✅": "CHECK",
    "❌": "CROSS",
    "⚠️": "WARN",
    "🔒": "LOCK",
    "🔑": "KEY",
    "💾": "SAVE",
    "🗄️": "DB",
    "🌐": "WEB",
    "📱": "PHONE",
    "💻": "PC",
    "📂": "FOLDER",
}


# ---------------------------------------------------------------------------
# Hebrew / RTL helpers
# ---------------------------------------------------------------------------

def _is_hebrew(text: str) -> bool:
    """Return True if *text* contains any Hebrew characters."""
    if not text:
        return False
    for ch in text:
        if "\u0590" <= ch <= "\u05FF" or "\uFB1D" <= ch <= "\uFB4F":
            return True
    return False


def _reverse_hebrew_line(line: str) -> str:
    """
    Reverse a Hebrew line for visual RTL rendering.
    This is a naive approach; for production use python-bidi.
    """
    result = []
    word_buffer = []
    for ch in line:
        if _is_hebrew(ch):
            word_buffer.insert(0, ch)
        else:
            if word_buffer:
                result.extend(word_buffer)
                word_buffer = []
            result.append(ch)
    if word_buffer:
        result.extend(word_buffer)
    return "".join(result)


def _prepare_text(text: str) -> str:
    """Prepare text for display (handle Hebrew RTL)."""
    if _is_hebrew(text):
        return _reverse_hebrew_line(text)
    return text


def _auto_wrap(text: str, width: int = 20) -> str:
    """Wrap *text* to *width* characters."""
    return "\n".join(textwrap.wrap(text, width=width))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _timestamp() -> str:
    """Return a filesystem-safe timestamp string."""
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _safe_filename(name: str) -> str:
    """Sanitise a string for use as a filename."""
    keep = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
    return "".join(c if c in keep else "_" for c in name)[:80]


def _get_font(size: int = 12, bold: bool = False):
    """Return a PIL ImageFont (or None if Pillow unavailable)."""
    if not _has_pil:
        return None
    try:
        if bold:
            return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size)
        return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size)
    except Exception:
        try:
            return ImageFont.truetype("DejaVuSans.ttf", size)
        except Exception:
            return ImageFont.load_default()


def _component_color(component_type: str, scheme: Dict) -> str:
    """Map a component type to a color in the given scheme."""
    ctype = (component_type or "service").lower()
    palette = scheme.get("palette", ["#1f4e79"])
    mapping = {
        "service": palette[0] if len(palette) > 0 else "#1f4e79",
        "database": palette[1] if len(palette) > 1 else "#2e75b6",
        "client": palette[2] if len(palette) > 2 else "#5b9bd5",
        "external": palette[3] if len(palette) > 3 else "#70ad47",
        "cache": palette[4] if len(palette) > 4 else "#ed7d31",
        "queue": palette[5] if len(palette) > 5 else "#a5a5a5",
        "api": palette[0] if len(palette) > 0 else "#1f4e79",
        "frontend": palette[2] if len(palette) > 2 else "#5b9bd5",
        "backend": palette[0] if len(palette) > 0 else "#1f4e79",
    }
    return mapping.get(ctype, palette[0] if palette else "#1f4e79")


# =============================================================================
#  DrawingEngine
# =============================================================================

class DrawingEngine:
    """
    Local visual explanation engine.
    Creates diagrams, flowcharts, mind maps, technical drawings.
    100% local — matplotlib, PIL, SVG. No external APIs.

    Parameters
    ----------
    output_dir : str or Path
        Directory where generated images are saved.
    default_style : str
        One of ``technical``, ``creative``, ``minimal``, ``colorful``.
    """

    def __init__(
        self,
        output_dir: str = "~/.jarvis/drawings",
        default_style: str = "technical",
    ) -> None:
        self.output_dir = Path(output_dir).expanduser().resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.default_style = default_style
        self._backends = {
            "matplotlib": _has_mpl,
            "PIL": _has_pil,
            "svgwrite": _has_svgwrite,
        }
        self._check_backends()

    # ── Backend introspection ──────────────────────────────────────────────

    def _check_backends(self) -> None:
        """Log which backends are available."""
        available = [k for k, v in self._backends.items() if v]
        missing = [k for k, v in self._backends.items() if not v]
        self._available_backends = available
        self._missing_backends = missing

    @property
    def available_backends(self) -> List[str]:
        return list(self._available_backends)

    # ── Style / scheme helpers ─────────────────────────────────────────────

    def _get_scheme(self, style: Optional[str] = None) -> Dict[str, Any]:
        """Return the colour scheme dictionary for *style*."""
        s = (style or self.default_style).lower()
        return COLOR_SCHEMES.get(s, TECHNICAL_COLORS)

    # ── Persistence helpers ────────────────────────────────────────────────

    def _save_figure(self, fig, name: str, fmt: str = "png") -> str:
        """Save a matplotlib Figure to the output directory."""
        fname = f"{_safe_filename(name)}_{_timestamp()}.{fmt}"
        out = self.output_dir / fname
        fig.savefig(str(out), dpi=150, bbox_inches="tight",
                    facecolor="white", edgecolor="none")
        plt.close(fig)
        return str(out)

    def _save_pil(self, img: Image.Image, name: str, fmt: str = "png") -> str:
        """Save a PIL Image to the output directory."""
        fname = f"{_safe_filename(name)}_{_timestamp()}.{fmt}"
        out = self.output_dir / fname
        img.save(str(out), fmt.upper())
        return str(out)

    def _save_svg(self, dwg, name: str) -> str:
        """Save an svgwrite.Drawing to the output directory."""
        fname = f"{_safe_filename(name)}_{_timestamp()}.svg"
        out = self.output_dir / fname
        dwg.saveas(str(out))
        return str(out)

    # ═══════════════════════════════════════════════════════════════════════
    #  1. Flowchart
    # ═══════════════════════════════════════════════════════════════════════

    def create_flowchart(
        self,
        title: str,
        steps: List[Dict],
        decision_points: Optional[List[Dict]] = None,
        style: Optional[str] = None,
    ) -> str:
        """
        Create a flowchart diagram.

        Parameters
        ----------
        title : str
            Chart title.
        steps : list of dict
            Each dict has ``id``, ``text``, and optional ``next`` key.
        decision_points : list of dict, optional
            Each dict has ``id``, ``question``, ``yes``, ``no``.
        style : str, optional
            Override the default colour scheme.

        Returns
        -------
        str
            Path to the generated PNG file.
        """
        if not _has_mpl:
            raise RuntimeError("matplotlib is required for create_flowchart")

        scheme = self._get_scheme(style)
        decision_points = decision_points or []

        # Build a lookup of all nodes
        all_nodes: Dict[str, Dict] = {}
        for s in steps:
            all_nodes[s["id"]] = {**s, "kind": "step"}
        for d in decision_points:
            all_nodes[d["id"]] = {**d, "kind": "decision"}

        # Simple auto-layout: assign levels via BFS
        levels: Dict[str, int] = {}
        queue = [steps[0]["id"]] if steps else []
        visited = set()
        for qid in queue:
            levels[qid] = 0
        while queue:
            node_id = queue.pop(0)
            if node_id in visited:
                continue
            visited.add(node_id)
            node = all_nodes.get(node_id)
            if not node:
                continue
            if node.get("kind") == "step":
                nxt = node.get("next")
                if nxt and nxt not in levels:
                    levels[nxt] = levels[node_id] + 1
                    queue.append(nxt)
            else:
                for branch in ("yes", "no"):
                    nxt = node.get(branch)
                    if nxt and nxt not in levels:
                        levels[nxt] = levels[node_id] + 1
                        queue.append(nxt)

        # Group by level
        level_groups: Dict[int, List[str]] = {}
        for nid, lvl in levels.items():
            level_groups.setdefault(lvl, []).append(nid)

        # Position nodes
        node_positions: Dict[str, Tuple[float, float]] = {}
        max_y_per_level: Dict[int, float] = {}
        y_spacing = 2.0
        x_spacing = 3.5

        for lvl in sorted(level_groups.keys()):
            nodes = level_groups[lvl]
            y_start = -(len(nodes) - 1) * y_spacing / 2
            for i, nid in enumerate(nodes):
                x = lvl * x_spacing
                y = y_start + i * y_spacing
                node_positions[nid] = (x, y)
                max_y_per_level[lvl] = max(max_y_per_level.get(lvl, 0), abs(y))

        # Create figure
        max_x = max((p[0] for p in node_positions.values()), default=0)
        fig_w = max(8, max_x * 1.2 + 2)
        fig_h = max(6, max((sum(max_y_per_level.values()) * 0.5 + 2,), default=(6,)))
        fig, ax = plt.subplots(figsize=(fig_w, fig_h))
        ax.set_xlim(-1, max_x + 2)
        ax.set_ylim(-(fig_h / 2 + 0.5), fig_h / 2 + 0.5)
        ax.set_aspect("equal")
        ax.axis("off")
        fig.patch.set_facecolor(scheme["background"])
        ax.set_facecolor(scheme["background"])

        # Title
        title_text = _prepare_text(title)
        ax.text(
            max_x / 2, fig_h / 2 + 0.2, title_text,
            fontsize=scheme["title_font"]["size"],
            fontweight=scheme["title_font"]["weight"],
            ha="center", va="top", color=scheme["text"],
            fontfamily=scheme["font_family"],
        )

        # Draw edges first (so boxes sit on top)
        for nid, (x, y) in node_positions.items():
            node = all_nodes.get(nid)
            if not node:
                continue
            if node.get("kind") == "step":
                nxt = node.get("next")
                if nxt and nxt in node_positions:
                    nx_x, nx_y = node_positions[nxt]
                    ax.annotate(
                        "", xy=(nx_x - 0.7, nx_y), xytext=(x + 0.7, y),
                        arrowprops=dict(arrowstyle="->", color=scheme["secondary"],
                                        lw=1.5, connectionstyle="arc3,rad=0"),
                    )
            else:
                for branch, color_key in (("yes", "success"), ("no", "error")):
                    nxt = node.get(branch)
                    if nxt and nxt in node_positions:
                        nx_x, nx_y = node_positions[nxt]
                        mid_x = (x + 0.9 + nx_x - 0.7) / 2
                        mid_y = (y + nx_y) / 2
                        ax.annotate(
                            "", xy=(nx_x - 0.7, nx_y), xytext=(x + 0.9, y),
                            arrowprops=dict(arrowstyle="->", color=scheme[color_key],
                                            lw=1.5, connectionstyle="arc3,rad=0.1"),
                        )
                        ax.text(mid_x + 0.3, mid_y, branch.upper(),
                                fontsize=8, color=scheme[color_key], fontweight="bold")

        # Draw nodes
        for nid, (x, y) in node_positions.items():
            node = all_nodes.get(nid)
            if not node:
                continue
            if node.get("kind") == "decision":
                # Diamond shape
                diamond = Polygon(
                    [[x, y + 0.6], [x + 0.9, y], [x, y - 0.6], [x - 0.9, y]],
                    facecolor=scheme["light"], edgecolor=scheme["primary"], lw=2,
                )
                ax.add_patch(diamond)
                label = _auto_wrap(_prepare_text(node.get("question", nid)), 10)
                ax.text(x, y, label, ha="center", va="center",
                        fontsize=scheme["body_font"]["size"] - 1,
                        color=scheme["text"], fontfamily=scheme["font_family"])
            else:
                # Rounded rectangle
                box = FancyBboxPatch(
                    (x - 0.9, y - 0.4), 1.8, 0.8,
                    boxstyle=scheme["box_style"], facecolor=scheme["light"],
                    edgecolor=scheme["primary"], lw=2,
                )
                ax.add_patch(box)
                label = _auto_wrap(_prepare_text(node.get("text", nid)), 14)
                ax.text(x, y, label, ha="center", va="center",
                        fontsize=scheme["body_font"]["size"],
                        color=scheme["text"], fontfamily=scheme["font_family"])

        return self._save_figure(fig, f"flowchart_{title}")

    # ═══════════════════════════════════════════════════════════════════════
    #  2. Mind Map
    # ═══════════════════════════════════════════════════════════════════════

    def create_mindmap(
        self,
        title: str,
        center_node: str,
        branches: List[Dict],
        style: Optional[str] = None,
    ) -> str:
        """
        Create a colourful radial mind map.

        Parameters
        ----------
        title : str
            Diagram title.
        center_node : str
            Text for the central bubble.
        branches : list of dict
            Each dict has ``label`` and optional ``sub_branches`` list.
        style : str, optional
            Colour scheme override.

        Returns
        -------
        str
            Path to the generated PNG file.
        """
        if not _has_mpl:
            raise RuntimeError("matplotlib is required for create_mindmap")

        scheme = self._get_scheme(style or "colorful")
        palette = scheme["palette"]

        fig, ax = plt.subplots(figsize=(12, 10))
        ax.set_xlim(-6, 6)
        ax.set_ylim(-5, 5)
        ax.set_aspect("equal")
        ax.axis("off")
        fig.patch.set_facecolor(scheme["background"])
        ax.set_facecolor(scheme["background"])

        # Title
        ax.text(0, 4.6, _prepare_text(title), fontsize=scheme["title_font"]["size"],
                fontweight=scheme["title_font"]["weight"], ha="center", va="top",
                color=scheme["text"], fontfamily=scheme["font_family"])

        n_branches = len(branches)
        if n_branches == 0:
            return self._save_figure(fig, f"mindmap_{title}")

        angles = [2 * math.pi * i / n_branches for i in range(n_branches)]
        center = (0, 0)
        branch_radius = 2.8
        sub_radius = 4.5

        # Central node
        circle = Circle(center, 1.0, facecolor=scheme["primary"],
                        edgecolor=scheme["dark"], lw=3, zorder=5)
        ax.add_patch(circle)
        ax.text(center[0], center[1], _auto_wrap(_prepare_text(center_node), 12),
                ha="center", va="center", fontsize=11, fontweight="bold",
                color="white", fontfamily=scheme["font_family"], zorder=6)

        for i, branch in enumerate(branches):
            color = palette[i % len(palette)]
            angle = angles[i]

            # Branch endpoint
            bx = center[0] + branch_radius * math.cos(angle)
            by = center[1] + branch_radius * math.sin(angle)

            # Draw connection from center to branch
            ax.plot([center[0], bx], [center[1], by],
                    color=color, lw=2.5, zorder=2)

            # Branch node (rounded rect approximated by ellipse)
            ellipse = Ellipse((bx, by), 1.6, 0.8, angle=math.degrees(angle),
                              facecolor=color, edgecolor=scheme["dark"], lw=2, zorder=4,
                              alpha=0.9)
            ax.add_patch(ellipse)
            ax.text(bx, by, _prepare_text(branch["label"]),
                    ha="center", va="center", fontsize=10, fontweight="bold",
                    color="white", fontfamily=scheme["font_family"], zorder=5)

            # Sub-branches
            sub_branches = branch.get("sub_branches", [])
            n_sub = len(sub_branches)
            if n_sub == 0:
                continue

            # Spread sub-branches in a fan around the branch direction
            fan_angle = math.pi / 3  # 60-degree spread
            start_angle = angle - fan_angle / 2
            for j, sub in enumerate(sub_branches):
                sub_angle = start_angle + fan_angle * j / max(n_sub - 1, 1)
                sx = center[0] + sub_radius * math.cos(sub_angle)
                sy = center[1] + sub_radius * math.sin(sub_angle)

                ax.plot([bx, sx], [by, sy], color=color, lw=1.5, zorder=1, alpha=0.7)

                sub_circle = Circle((sx, sy), 0.5, facecolor=scheme["background"],
                                    edgecolor=color, lw=1.5, zorder=3)
                ax.add_patch(sub_circle)
                ax.text(sx, sy, _auto_wrap(_prepare_text(sub), 10),
                        ha="center", va="center", fontsize=8,
                        color=scheme["text"], fontfamily=scheme["font_family"], zorder=4)

        return self._save_figure(fig, f"mindmap_{title}")

    # ═══════════════════════════════════════════════════════════════════════
    #  3. Architecture Diagram
    # ═══════════════════════════════════════════════════════════════════════

    def create_architecture_diagram(
        self,
        title: str,
        components: List[Dict],
        connections: List[Dict],
        style: Optional[str] = None,
    ) -> str:
        """
        Create a system-architecture diagram.

        Parameters
        ----------
        title : str
            Diagram title.
        components : list of dict
            Each dict has ``name`` and ``type`` (service, database, client, ...).
        connections : list of dict
            Each dict has ``from``, ``to``, and optional ``label``.
        style : str, optional
            Colour scheme override.

        Returns
        -------
        str
            Path to the generated PNG file.
        """
        if not _has_mpl:
            raise RuntimeError("matplotlib is required for create_architecture_diagram")

        scheme = self._get_scheme(style)

        # Simple grid layout
        n = len(components)
        cols = max(3, math.ceil(math.sqrt(n)))
        rows = math.ceil(n / cols)

        fig_w = max(10, cols * 3)
        fig_h = max(6, rows * 2.5 + 1)
        fig, ax = plt.subplots(figsize=(fig_w, fig_h))
        ax.set_xlim(-0.5, cols * 3 - 0.5)
        ax.set_ylim(-1, rows * 2.5 + 0.5)
        ax.set_aspect("equal")
        ax.axis("off")
        fig.patch.set_facecolor(scheme["background"])
        ax.set_facecolor(scheme["background"])

        # Title
        ax.text((cols * 3 - 0.5) / 2, rows * 2.5 + 0.2, _prepare_text(title),
                fontsize=scheme["title_font"]["size"],
                fontweight=scheme["title_font"]["weight"],
                ha="center", va="top", color=scheme["text"],
                fontfamily=scheme["font_family"])

        # Assign positions
        comp_positions: Dict[str, Tuple[float, float]] = {}
        for i, comp in enumerate(components):
            col = i % cols
            row = rows - 1 - (i // cols)
            x = col * 3 + 1.0
            y = row * 2.5 + 0.5
            comp_positions[comp["name"]] = (x, y)

            color = _component_color(comp.get("type", "service"), scheme)

            # Box
            box = FancyBboxPatch(
                (x - 1.1, y - 0.5), 2.2, 1.0,
                boxstyle=scheme["box_style"], facecolor=color,
                edgecolor=scheme["dark"], lw=2, alpha=0.85,
            )
            ax.add_patch(box)
            ax.text(x, y + 0.1, _prepare_text(comp["name"]),
                    ha="center", va="center", fontsize=9,
                    fontweight="bold", color="white",
                    fontfamily=scheme["font_family"])
            ax.text(x, y - 0.25, comp.get("type", "service").upper(),
                    ha="center", va="center", fontsize=7,
                    color="white", alpha=0.8,
                    fontfamily=scheme["font_family"])

        # Draw connections
        for conn in connections:
            src = comp_positions.get(conn.get("from", ""))
            dst = comp_positions.get(conn.get("to", ""))
            if src and dst:
                ax.annotate(
                    "", xy=(dst[0], dst[1] + 0.5), xytext=(src[0], src[1] - 0.5),
                    arrowprops=dict(arrowstyle="->", color=scheme["accent"],
                                    lw=1.5, connectionstyle="arc3,rad=0.1"),
                )
                if conn.get("label"):
                    mx, my = (src[0] + dst[0]) / 2, (src[1] + dst[1]) / 2 + 0.2
                    ax.text(mx, my, _prepare_text(conn["label"]), fontsize=8,
                            ha="center", va="center", color=scheme["secondary"],
                            fontfamily=scheme["font_family"],
                            bbox=dict(boxstyle="round,pad=0.2", facecolor=scheme["background"],
                                      edgecolor="none", alpha=0.8))

        return self._save_figure(fig, f"architecture_{title}")

    # ═══════════════════════════════════════════════════════════════════════
    #  4. Comparison Chart
    # ═══════════════════════════════════════════════════════════════════════

    def create_comparison_chart(
        self,
        title: str,
        items: List[Dict],
        criteria: List[str],
        style: Optional[str] = None,
    ) -> str:
        """
        Create a comparison radar/bar chart.

        Parameters
        ----------
        title : str
            Chart title.
        items : list of dict
            Each dict has ``name`` and ``scores`` list.
        criteria : list of str
            Labels for each score dimension.
        style : str, optional
            Colour scheme override.

        Returns
        -------
        str
            Path to the generated PNG file.
        """
        if not _has_mpl:
            raise RuntimeError("matplotlib is required for create_comparison_chart")

        scheme = self._get_scheme(style)
        palette = scheme["palette"]
        n_criteria = len(criteria)

        if n_criteria < 3:
            # Fallback: bar chart
            return self._create_comparison_bars(title, items, criteria, scheme)

        # Radar chart
        angles = [2 * math.pi * i / n_criteria for i in range(n_criteria)]
        angles += angles[:1]  # close the loop

        fig, ax = plt.subplots(figsize=(9, 9), subplot_kw=dict(polar=True))
        fig.patch.set_facecolor(scheme["background"])
        ax.set_facecolor(scheme["background"])

        # Draw criteria grid
        ax.set_xticks(angles[:-1])
        ax.set_xticklabels([_prepare_text(c) for c in criteria],
                           fontsize=9, color=scheme["text"],
                           fontfamily=scheme["font_family"])
        ax.set_ylim(0, 10)
        ax.set_yticks([2, 4, 6, 8, 10])
        ax.set_yticklabels(["2", "4", "6", "8", "10"], fontsize=7, color=scheme["text"])
        ax.grid(color=scheme["light"], lw=0.5)
        ax.spines["polar"].set_color(scheme["secondary"])

        # Title
        fig.suptitle(_prepare_text(title), fontsize=scheme["title_font"]["size"],
                     fontweight=scheme["title_font"]["weight"], color=scheme["text"],
                     fontfamily=scheme["font_family"], y=0.95)

        # Plot each item
        for idx, item in enumerate(items):
            color = palette[idx % len(palette)]
            scores = item.get("scores", [])
            if len(scores) < n_criteria:
                scores = scores + [5] * (n_criteria - len(scores))
            scores = scores[:n_criteria]
            values = scores + scores[:1]

            ax.plot(angles, values, "o-", color=color, lw=2, label=_prepare_text(item["name"]))
            ax.fill(angles, values, color=color, alpha=0.15)

        ax.legend(loc="lower right", bbox_to_anchor=(1.2, -0.05),
                  frameon=True, facecolor=scheme["background"],
                  edgecolor=scheme["secondary"], fontsize=9)

        return self._save_figure(fig, f"comparison_{title}")

    def _create_comparison_bars(
        self, title: str, items: List[Dict], criteria: List[str], scheme: Dict
    ) -> str:
        """Fallback grouped bar chart for < 3 criteria."""
        palette = scheme["palette"]
        n_items = len(items)
        n_crit = len(criteria)

        fig, ax = plt.subplots(figsize=(max(8, n_crit * n_items * 0.8), 6))
        fig.patch.set_facecolor(scheme["background"])
        ax.set_facecolor(scheme["background"])

        x = range(n_crit)
        bar_width = 0.8 / n_items

        for idx, item in enumerate(items):
            color = palette[idx % len(palette)]
            scores = item.get("scores", []) + [0] * n_crit
            scores = scores[:n_crit]
            offset = (idx - n_items / 2 + 0.5) * bar_width
            ax.bar([xi + offset for xi in x], scores, bar_width,
                   label=_prepare_text(item["name"]), color=color, edgecolor="white")

        ax.set_xticks(x)
        ax.set_xticklabels([_prepare_text(c) for c in criteria],
                           fontfamily=scheme["font_family"])
        ax.set_ylabel("Score", fontfamily=scheme["font_family"], color=scheme["text"])
        ax.set_title(_prepare_text(title), fontsize=scheme["title_font"]["size"],
                     fontweight=scheme["title_font"]["weight"],
                     color=scheme["text"], fontfamily=scheme["font_family"])
        ax.legend(frameon=True, facecolor=scheme["background"],
                  edgecolor=scheme["secondary"])
        ax.set_ylim(0, 10)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

        return self._save_figure(fig, f"comparison_{title}")

    # ═══════════════════════════════════════════════════════════════════════
    #  5. Timeline
    # ═══════════════════════════════════════════════════════════════════════

    def create_timeline(
        self,
        title: str,
        events: List[Dict],
        style: Optional[str] = None,
    ) -> str:
        """
        Create a horizontal timeline visualisation.

        Parameters
        ----------
        title : str
            Timeline title.
        events : list of dict
            Each dict has ``date``, ``label``, and optional ``color``.
        style : str, optional
            Colour scheme override.

        Returns
        -------
        str
            Path to the generated PNG file.
        """
        if not _has_mpl:
            raise RuntimeError("matplotlib is required for create_timeline")

        scheme = self._get_scheme(style)
        palette = scheme["palette"]
        n_events = len(events)

        fig_w = max(10, n_events * 2.5)
        fig, ax = plt.subplots(figsize=(fig_w, 5))
        fig.patch.set_facecolor(scheme["background"])
        ax.set_facecolor(scheme["background"])

        ax.set_xlim(-0.5, n_events - 0.5)
        ax.set_ylim(-1.5, 1.8)
        ax.set_aspect("equal")
        ax.axis("off")

        # Title
        ax.text((n_events - 1) / 2, 1.6, _prepare_text(title),
                fontsize=scheme["title_font"]["size"],
                fontweight=scheme["title_font"]["weight"],
                ha="center", va="center", color=scheme["text"],
                fontfamily=scheme["font_family"])

        # Main horizontal line
        ax.plot([-0.3, n_events - 0.7], [0, 0], color=scheme["primary"], lw=3, zorder=1)

        for i, event in enumerate(events):
            color = event.get("color", palette[i % len(palette)])
            if color.startswith("#"):
                pass  # already hex
            else:
                # Map named colours
                color_map = {
                    "green": scheme["success"], "red": scheme["error"],
                    "yellow": scheme["warning"], "blue": scheme["primary"],
                    "orange": scheme.get("accent", "#ed7d31"), "purple": "#9b59b6",
                }
                color = color_map.get(color.lower(), palette[i % len(palette)])

            # Alternate above/below
            above = (i % 2 == 0)
            y_offset = 0.6 if above else -0.6
            va = "bottom" if above else "top"

            # Vertical connector
            ax.plot([i, i], [0, y_offset * 0.7], color=color, lw=1.5, zorder=1)

            # Event dot
            circle = Circle((i, 0), 0.12, facecolor=color, edgecolor="white", lw=2, zorder=3)
            ax.add_patch(circle)

            # Label
            ax.text(i, y_offset, _auto_wrap(_prepare_text(event.get("label", "")), 16),
                    ha="center", va=va, fontsize=9, color=scheme["text"],
                    fontfamily=scheme["font_family"], fontweight="bold",
                    bbox=dict(boxstyle="round,pad=0.3", facecolor=scheme["light"],
                              edgecolor=color, lw=1.5, alpha=0.9))

            # Date
            date_y = y_offset + (0.35 if above else -0.35)
            ax.text(i, date_y, _prepare_text(str(event.get("date", ""))),
                    ha="center", va="center", fontsize=8, color=color,
                    fontfamily=scheme["font_family"], fontweight="bold")

        return self._save_figure(fig, f"timeline_{title}")

    # ═══════════════════════════════════════════════════════════════════════
    #  6. Pie Chart
    # ═══════════════════════════════════════════════════════════════════════

    def create_pie_chart(
        self,
        title: str,
        data: Dict[str, Union[int, float]],
        style: Optional[str] = None,
    ) -> str:
        """
        Create a pie/doughnut chart.

        Parameters
        ----------
        title : str
            Chart title.
        data : dict
            Mapping of label -> numeric value.
        style : str, optional
            Colour scheme override.

        Returns
        -------
        str
            Path to the generated PNG file.
        """
        if not _has_mpl:
            raise RuntimeError("matplotlib is required for create_pie_chart")

        scheme = self._get_scheme(style or "colorful")
        palette = scheme["palette"]

        labels = list(data.keys())
        values = list(data.values())
        colors = [palette[i % len(palette)] for i in range(len(labels))]

        fig, ax = plt.subplots(figsize=(8, 8))
        fig.patch.set_facecolor(scheme["background"])
        ax.set_facecolor(scheme["background"])

        wedges, texts, autotexts = ax.pie(
            values, labels=[_prepare_text(l) for l in labels],
            colors=colors, autopct="%1.1f%%", startangle=90,
            wedgeprops=dict(width=0.55, edgecolor="white", lw=2),
            textprops={"fontsize": 10, "fontfamily": scheme["font_family"],
                       "color": scheme["text"]},
            pctdistance=0.75,
        )
        for t in autotexts:
            t.set_fontsize(9)
            t.set_fontweight("bold")
            t.set_color("white")

        # Center text
        centre_circle = Circle((0, 0), 0.35, facecolor=scheme["background"],
                               edgecolor="none")
        ax.add_patch(centre_circle)
        ax.text(0, 0, _prepare_text(title), ha="center", va="center",
                fontsize=scheme["title_font"]["size"] - 2,
                fontweight="bold", color=scheme["text"],
                fontfamily=scheme["font_family"])

        return self._save_figure(fig, f"pie_{title}")

    # ═══════════════════════════════════════════════════════════════════════
    #  7. Bar Chart
    # ═══════════════════════════════════════════════════════════════════════

    def create_bar_chart(
        self,
        title: str,
        labels: List[str],
        values: List[Union[int, float]],
        style: Optional[str] = None,
    ) -> str:
        """
        Create a vertical bar chart.

        Parameters
        ----------
        title : str
            Chart title.
        labels : list of str
            X-axis labels.
        values : list of number
            Bar heights.
        style : str, optional
            Colour scheme override.

        Returns
        -------
        str
            Path to the generated PNG file.
        """
        if not _has_mpl:
            raise RuntimeError("matplotlib is required for create_bar_chart")

        scheme = self._get_scheme(style or "colorful")
        palette = scheme["palette"]

        n = len(labels)
        colors = [palette[i % len(palette)] for i in range(n)]

        fig, ax = plt.subplots(figsize=(max(8, n * 1.2), 6))
        fig.patch.set_facecolor(scheme["background"])
        ax.set_facecolor(scheme["background"])

        bars = ax.bar(range(n), values, color=colors, edgecolor="white", lw=1.5)

        # Value labels on bars
        for bar, val in zip(bars, values):
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width() / 2., height + max(values) * 0.01,
                    str(val), ha="center", va="bottom", fontsize=9,
                    fontweight="bold", color=scheme["text"],
                    fontfamily=scheme["font_family"])

        ax.set_xticks(range(n))
        ax.set_xticklabels([_prepare_text(l) for l in labels],
                           fontfamily=scheme["font_family"], fontsize=9)
        ax.set_title(_prepare_text(title), fontsize=scheme["title_font"]["size"],
                     fontweight=scheme["title_font"]["weight"],
                     color=scheme["text"], fontfamily=scheme["font_family"])
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_color(scheme["secondary"])
        ax.spines["bottom"].set_color(scheme["secondary"])
        ax.tick_params(colors=scheme["text"])

        plt.tight_layout()
        return self._save_figure(fig, f"bar_{title}")

    # ═══════════════════════════════════════════════════════════════════════
    #  8. Infographic
    # ═══════════════════════════════════════════════════════════════════════

    def create_infographic(
        self,
        title: str,
        sections: List[Dict],
        style: Optional[str] = None,
    ) -> str:
        """
        Create a simple multi-section infographic.

        Parameters
        ----------
        title : str
            Infographic title.
        sections : list of dict
            Each dict has ``title``, ``text``, and optional ``icon``.
        style : str, optional
            Colour scheme override.

        Returns
        -------
        str
            Path to the generated PNG file.
        """
        if not _has_mpl:
            raise RuntimeError("matplotlib is required for create_infographic")

        scheme = self._get_scheme(style or "creative")
        palette = scheme["palette"]
        n_sections = len(sections)

        cols = min(3, n_sections)
        rows = math.ceil(n_sections / cols)

        fig_w = cols * 4 + 1
        fig_h = rows * 3 + 1.5
        fig, ax = plt.subplots(figsize=(fig_w, fig_h))
        fig.patch.set_facecolor(scheme["background"])
        ax.set_facecolor(scheme["background"])
        ax.set_xlim(0, fig_w)
        ax.set_ylim(0, fig_h)
        ax.axis("off")

        # Title
        ax.text(fig_w / 2, fig_h - 0.4, _prepare_text(title),
                fontsize=scheme["title_font"]["size"] + 2,
                fontweight=scheme["title_font"]["weight"],
                ha="center", va="top", color=scheme["text"],
                fontfamily=scheme["font_family"])

        for i, section in enumerate(sections):
            col = i % cols
            row = rows - 1 - (i // cols)

            x = col * 4 + 0.5
            y = row * 3 + 0.5
            color = palette[i % len(palette)]

            # Section box
            box = FancyBboxPatch(
                (x, y), 3.5, 2.5,
                boxstyle="round,pad=0.2", facecolor=scheme["light"],
                edgecolor=color, lw=2.5, alpha=0.9,
            )
            ax.add_patch(box)

            # Icon (mapped to text symbol)
            icon = section.get("icon", "")
            icon_text = _ICON_MAP.get(icon, icon)[:4] if icon else ""
            if icon_text:
                ax.text(x + 0.35, y + 2.05, icon_text, fontsize=14,
                        ha="center", va="center", color=color,
                        fontweight="bold")

            # Section title
            ax.text(x + 1.8, y + 2.05, _prepare_text(section.get("title", "")),
                    fontsize=12, fontweight="bold", ha="center", va="center",
                    color=scheme["text"], fontfamily=scheme["font_family"])

            # Divider
            ax.plot([x + 0.3, x + 3.2], [y + 1.7, y + 1.7], color=color, lw=1.5)

            # Section text
            text = _auto_wrap(_prepare_text(section.get("text", "")), 28)
            ax.text(x + 1.75, y + 1.3, text,
                    fontsize=scheme["body_font"]["size"],
                    ha="center", va="top", color=scheme["text"],
                    fontfamily=scheme["font_family"], linespacing=1.4)

        return self._save_figure(fig, f"infographic_{title}")

    # ═══════════════════════════════════════════════════════════════════════
    #  9. Sketch from Description
    # ═══════════════════════════════════════════════════════════════════════

    def create_sketch(
        self,
        description: str,
        style: str = "technical",
    ) -> str:
        """
        Create a conceptual sketch from a text description.

        Uses basic geometric primitives (rectangles, circles, arrows, text)
        to illustrate the described concept.

        Parameters
        ----------
        description : str
            Concept description.
        style : str
            One of ``technical``, ``artistic``, ``minimal``, ``detailed``.

        Returns
        -------
        str
            Path to the generated PNG file.
        """
        if not _has_mpl:
            raise RuntimeError("matplotlib is required for create_sketch")

        scheme = self._get_scheme(style)

        fig, ax = plt.subplots(figsize=(10, 8))
        ax.set_xlim(0, 10)
        ax.set_ylim(0, 8)
        ax.axis("off")
        fig.patch.set_facecolor(scheme["background"])
        ax.set_facecolor(scheme["background"])

        # Parse keywords from description
        desc_lower = description.lower()
        keywords = set(desc_lower.split())

        # Title
        ax.text(5, 7.5, _auto_wrap(_prepare_text(description), 50),
                fontsize=12, fontweight="bold", ha="center", va="top",
                color=scheme["text"], fontfamily=scheme["font_family"],
                wrap=True)

        # Keyword-driven primitives
        palette = scheme["palette"]
        primitives = []

        if any(w in keywords for w in ("box", "container", "module", "server", "service")):
            primitives.append(("rect", (2, 4, 6, 2.5), palette[0]))
        if any(w in keywords for w in ("circle", "round", "node", "point", "hub")):
            primitives.append(("circle", (5, 3.5, 1.2), palette[1] if len(palette) > 1 else palette[0]))
        if any(w in keywords for w in ("arrow", "flow", "direction", "connection", "link")):
            primitives.append(("arrow", (1.5, 2.5, 8.5, 2.5), palette[2] if len(palette) > 2 else palette[0]))
        if any(w in keywords for w in ("layer", "stack", "levels", "tier")):
            for j in range(3):
                primitives.append(("rect", (2 + j * 0.3, 1.5 + j * 0.6, 6, 0.5), palette[j % len(palette)]))
        if any(w in keywords for w in ("database", "db", "storage", "disk", "data")):
            primitives.append(("cylinder", (7.5, 4.5, 1.2, 1.0), palette[3] if len(palette) > 3 else palette[0]))
        if any(w in keywords for w in ("user", "person", "people", "team", "client")):
            primitives.append(("person", (1.5, 4.5, 0.6), palette[4] if len(palette) > 4 else palette[0]))

        if not primitives:
            # Default: balanced layout with several shapes
            primitives = [
                ("rect", (1.5, 3.8, 3, 2), palette[0]),
                ("rect", (5.5, 3.8, 3, 2), palette[1] if len(palette) > 1 else palette[0]),
                ("arrow", (4.5, 4.8, 5.5, 4.8), scheme["accent"]),
                ("circle", (5, 1.8, 0.8), palette[2] if len(palette) > 2 else palette[0]),
            ]

        for ptype, coords, color in primitives:
            if ptype == "rect":
                x, y, w, h = coords
                rect = FancyBboxPatch(
                    (x, y), w, h,
                    boxstyle="round,pad=0.15", facecolor=color,
                    edgecolor=scheme["dark"], lw=1.5, alpha=0.6,
                )
                ax.add_patch(rect)
            elif ptype == "circle":
                cx, cy, r = coords
                circle = Circle((cx, cy), r, facecolor=color,
                                edgecolor=scheme["dark"], lw=1.5, alpha=0.6)
                ax.add_patch(circle)
            elif ptype == "arrow":
                x1, y1, x2, y2 = coords
                ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                            arrowprops=dict(arrowstyle="->", color=color, lw=2))
            elif ptype == "cylinder":
                x, y, w, h = coords
                ellipse = Ellipse((x + w / 2, y + h), w, h * 0.4,
                                  facecolor=color, edgecolor=scheme["dark"], lw=1.5, alpha=0.6)
                ax.add_patch(ellipse)
                rect = FancyBboxPatch((x, y), w, h,
                                      boxstyle="square,pad=0", facecolor=color,
                                      edgecolor=scheme["dark"], lw=1.5, alpha=0.6)
                ax.add_patch(rect)
                ellipse_top = Ellipse((x + w / 2, y + h), w, h * 0.4,
                                      facecolor=color, edgecolor=scheme["dark"], lw=1.5, alpha=0.6)
                ax.add_patch(ellipse_top)
            elif ptype == "person":
                cx, cy, r = coords
                head = Circle((cx, cy + r * 1.8), r * 0.35, facecolor=color,
                              edgecolor=scheme["dark"], lw=1.5, alpha=0.6)
                ax.add_patch(head)
                body = Ellipse((cx, cy + r * 0.3), r * 1.4, r * 1.8,
                               facecolor=color, edgecolor=scheme["dark"], lw=1.5, alpha=0.6)
                ax.add_patch(body)

        return self._save_figure(fig, f"sketch_{description[:30]}")

    # ═══════════════════════════════════════════════════════════════════════
    #  10. Whiteboard
    # ═══════════════════════════════════════════════════════════════════════

    def create_whiteboard(
        self,
        elements: List[Dict],
        title: str = "Whiteboard",
        style: Optional[str] = None,
    ) -> str:
        """
        Create a whiteboard-style diagram.

        Parameters
        ----------
        elements : list of dict
            Each dict has ``type`` (box|circle|arrow|text), ``x``, ``y``,
            and optional ``text``, ``width``, ``height``, ``color``.
        title : str
            Whiteboard title.
        style : str, optional
            Colour scheme override.

        Returns
        -------
        str
            Path to the generated PNG file.
        """
        if not _has_mpl:
            raise RuntimeError("matplotlib is required for create_whiteboard")

        scheme = self._get_scheme(style or "minimal")

        fig_w, fig_h = 14, 10
        fig, ax = plt.subplots(figsize=(fig_w, fig_h))
        ax.set_xlim(0, fig_w * 10)
        ax.set_ylim(0, fig_h * 10)
        ax.axis("off")

        # Whiteboard background
        fig.patch.set_facecolor("#fafafa")
        ax.set_facecolor("#fafafa")

        # Subtle grid
        for gx in range(0, fig_w * 10, 50):
            ax.axvline(gx, color="#e0e0e0", lw=0.5, alpha=0.5)
        for gy in range(0, fig_h * 10, 50):
            ax.axhline(gy, color="#e0e0e0", lw=0.5, alpha=0.5)

        # Title
        ax.text(fig_w * 5, fig_h * 10 - 20, _prepare_text(title),
                fontsize=16, fontweight="bold", ha="center", va="top",
                color="#444444", fontfamily=scheme["font_family"])

        for elem in elements:
            etype = elem.get("type", "text").lower()
            x = elem.get("x", 0)
            y = elem.get("y", 0)
            color = elem.get("color", scheme["primary"])

            if etype == "box":
                w = elem.get("width", 100)
                h = elem.get("height", 60)
                box = FancyBboxPatch(
                    (x - w / 2, y - h / 2), w, h,
                    boxstyle="round,pad=0.1",
                    facecolor="white", edgecolor=color, lw=2.5, alpha=0.95,
                )
                ax.add_patch(box)
                if elem.get("text"):
                    ax.text(x, y, _auto_wrap(_prepare_text(elem["text"]), 12),
                            ha="center", va="center", fontsize=10,
                            color=scheme["text"], fontfamily=scheme["font_family"])

            elif etype == "circle":
                r = elem.get("radius", 40)
                circle = Circle((x, y), r, facecolor="white",
                                edgecolor=color, lw=2.5, alpha=0.95)
                ax.add_patch(circle)
                if elem.get("text"):
                    ax.text(x, y, _prepare_text(elem["text"]),
                            ha="center", va="center", fontsize=10,
                            color=scheme["text"], fontfamily=scheme["font_family"])

            elif etype == "arrow":
                x2 = elem.get("x2", x + 100)
                y2 = elem.get("y2", y)
                ax.annotate("", xy=(x2, y2), xytext=(x, y),
                            arrowprops=dict(arrowstyle="->", color=color, lw=2.5))
                if elem.get("text"):
                    mx, my = (x + x2) / 2, (y + y2) / 2 + 10
                    ax.text(mx, my, _prepare_text(elem["text"]), fontsize=9,
                            ha="center", va="center", color=color,
                            fontfamily=scheme["font_family"],
                            bbox=dict(boxstyle="round,pad=0.2", facecolor="white",
                                      edgecolor="none", alpha=0.8))

            elif etype == "text":
                ax.text(x, y, _prepare_text(elem.get("text", "")),
                        fontsize=elem.get("size", 12),
                        ha="center", va="center", color=color,
                        fontfamily=scheme["font_family"],
                        fontweight=elem.get("weight", "normal"))

        return self._save_figure(fig, f"whiteboard_{title}")

    # ═══════════════════════════════════════════════════════════════════════
    #  11. SVG Export
    # ═══════════════════════════════════════════════════════════════════════

    def export_svg(self, drawing_path: str) -> str:
        """
        Convert a PNG drawing to SVG format.

        If *svgwrite* is available, the SVG is vector-native.
        Otherwise, a data-URI raster-embedded SVG is produced.

        Parameters
        ----------
        drawing_path : str
            Path to an existing PNG file.

        Returns
        -------
        str
            Path to the generated SVG file.
        """
        src = Path(drawing_path)
        if not src.exists():
            raise FileNotFoundError(f"Drawing not found: {drawing_path}")

        out = self.output_dir / f"{src.stem}.svg"

        if _has_pil:
            img = Image.open(str(src))
            w, h = img.size

            if _has_svgwrite:
                dwg = svgwrite.Drawing(str(out), size=(f"{w}px", f"{h}px"))
                # Embed as base64 data URI
                import base64
                from io import BytesIO
                buf = BytesIO()
                img.save(buf, format="PNG")
                b64 = base64.b64encode(buf.getvalue()).decode("ascii")
                dwg.add(dwg.image(
                    href=f"data:image/png;base64,{b64}",
                    insert=(0, 0),
                    size=(f"{w}px", f"{h}px"),
                ))
                dwg.save()
            else:
                # Pure base64 SVG wrapper
                import base64
                from io import BytesIO
                buf = BytesIO()
                img.save(buf, format="PNG")
                b64 = base64.b64encode(buf.getvalue()).decode("ascii")
                svg_content = (
                    f'<svg xmlns="http://www.w3.org/2000/svg" '
                    f'width="{w}" height="{h}" viewBox="0 0 {w} {h}">\n'
                    f'  <image href="data:image/png;base64,{b64}" '
                    f'width="{w}" height="{h}"/>\n'
                    f'</svg>'
                )
                out.write_text(svg_content, encoding="utf-8")
        else:
            # Fallback: create a simple SVG with text
            dwg = svgwrite.Drawing(str(out), size=("800px", "600px"))
            dwg.add(dwg.text(
                "SVG export requires Pillow",
                insert=("400px", "300px"),
                text_anchor="middle",
                font_size="20px",
                fill="#999",
            ))
            dwg.save()

        return str(out)

    # ═══════════════════════════════════════════════════════════════════════
    #  12. Available Styles
    # ═══════════════════════════════════════════════════════════════════════

    def get_available_styles(self) -> List[str]:
        """Return a list of available drawing style names."""
        return list(COLOR_SCHEMES.keys())

    # ═══════════════════════════════════════════════════════════════════════
    #  13. Batch / utility helpers
    # ═══════════════════════════════════════════════════════════════════════

    def create_from_json(self, spec_path: str) -> str:
        """
        Create a drawing from a JSON specification file.

        The JSON must contain ``type`` and the relevant parameters for that type.
        """
        spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
        dtype = spec.get("type", "flowchart")
        method = getattr(self, f"create_{dtype}", None)
        if method is None:
            raise ValueError(f"Unknown drawing type: {dtype}")
        kwargs = {k: v for k, v in spec.items() if k != "type"}
        return method(**kwargs)

    def list_drawings(self) -> List[str]:
        """Return a list of previously generated drawing file paths."""
        if not self.output_dir.exists():
            return []
        return sorted(
            str(p) for p in self.output_dir.iterdir()
            if p.suffix.lower() in (".png", ".svg", ".jpg", ".jpeg")
        )

    def delete_drawing(self, name: str) -> bool:
        """Delete a drawing by filename (no path)."""
        target = self.output_dir / name
        if target.exists():
            target.unlink()
            return True
        return False

    def clear_all(self) -> int:
        """Delete all drawings in the output directory. Returns count deleted."""
        count = 0
        for p in self.output_dir.iterdir():
            if p.suffix.lower() in (".png", ".svg", ".jpg", ".jpeg"):
                p.unlink()
                count += 1
        return count


# =============================================================================
#  MockDrawingEngine — same interface, creates blank placeholders
# =============================================================================

class MockDrawingEngine:
    """
    Drop-in replacement for :class:`DrawingEngine`.
    Every ``create_*`` method returns the path to a blank placeholder image.
    Useful for testing, CI, or environments without matplotlib.
    """

    def __init__(self, output_dir: str = "~/.jarvis/drawings") -> None:
        self.output_dir = Path(output_dir).expanduser().resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.default_style = "technical"

    def _placeholder(self, name: str) -> str:
        """Generate a blank grey PNG."""
        fname = f"{_safe_filename(name)}_{_timestamp()}.png"
        out = self.output_dir / fname
        try:
            from PIL import Image, ImageDraw
            img = Image.new("RGB", (400, 300), color="#e0e0e0")
            d = ImageDraw.Draw(img)
            font = _get_font(14, bold=True)
            label = f"[Placeholder]\n{name[:60]}"
            d.text((200, 150), label, fill="#999999", font=font, anchor="mm")
            img.save(str(out))
        except Exception:
            out.write_bytes(b"")  # empty file as last resort
        return str(out)

    # ── All create_* methods delegate to _placeholder ──────────────────────

    def create_flowchart(self, title, steps, decision_points=None, style=None):
        return self._placeholder(f"flowchart_{title}")

    def create_mindmap(self, title, center_node, branches, style=None):
        return self._placeholder(f"mindmap_{title}")

    def create_architecture_diagram(self, title, components, connections, style=None):
        return self._placeholder(f"architecture_{title}")

    def create_comparison_chart(self, title, items, criteria, style=None):
        return self._placeholder(f"comparison_{title}")

    def create_timeline(self, title, events, style=None):
        return self._placeholder(f"timeline_{title}")

    def create_pie_chart(self, title, data, style=None):
        return self._placeholder(f"pie_{title}")

    def create_bar_chart(self, title, labels, values, style=None):
        return self._placeholder(f"bar_{title}")

    def create_infographic(self, title, sections, style=None):
        return self._placeholder(f"infographic_{title}")

    def create_sketch(self, description, style="technical"):
        return self._placeholder(f"sketch_{description[:30]}")

    def create_whiteboard(self, elements, title="Whiteboard", style=None):
        return self._placeholder(f"whiteboard_{title}")

    def export_svg(self, drawing_path):
        out = self.output_dir / f"{Path(drawing_path).stem}.svg"
        out.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300">'
            '<rect width="400" height="300" fill="#e0e0e0"/>'
            '<text x="200" y="150" text-anchor="middle" fill="#999" font-size="16">'
            'Placeholder SVG</text></svg>'
        )
        return str(out)

    def get_available_styles(self):
        return list(COLOR_SCHEMES.keys())

    # Batch helpers
    def create_from_json(self, spec_path):
        return self._placeholder("from_json")

    def list_drawings(self):
        return []

    def delete_drawing(self, name):
        return False

    def clear_all(self):
        return 0


# =============================================================================
#  Factory
# =============================================================================

def get_drawing_engine(output_dir: str = "~/.jarvis/drawings", **kwargs) -> Union[DrawingEngine, MockDrawingEngine]:
    """
    Return the best available drawing engine.

    If *matplotlib* is installed, returns a :class:`DrawingEngine`.
    Otherwise falls back to :class:`MockDrawingEngine`.

    Parameters
    ----------
    output_dir : str
        Directory for generated images.
    **kwargs
        Passed to the engine constructor.

    Returns
    -------
    DrawingEngine or MockDrawingEngine
    """
    if _has_mpl:
        return DrawingEngine(output_dir=output_dir, **kwargs)
    return MockDrawingEngine(output_dir=output_dir)


# =============================================================================
#  Standalone execution — quick demo
# =============================================================================

if __name__ == "__main__":
    print("JARVIS Drawing Engine v" + __version__)
    print("Backends available:", [k for k, v in {
        "matplotlib": _has_mpl,
        "PIL": _has_pil,
        "svgwrite": _has_svgwrite,
    }.items() if v])

    de = get_drawing_engine()
    print("Engine:", type(de).__name__)

    # Quick smoke test: flowchart
    path = de.create_flowchart(
        "Sample Flow",
        [
            {"id": "1", "text": "Start", "next": "2"},
            {"id": "2", "text": "Process Data", "next": "3"},
            {"id": "3", "text": "Validate", "next": None},
        ],
        decision_points=[{"id": "2", "question": "Valid?", "yes": "3", "no": "1"}],
    )
    print("Created:", path)
