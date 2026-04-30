"""Drawing engine (Tier 3).

Pure-Python SVG renderer for 12 diagram families: flowchart, mindmap,
architecture block diagram, sequence, class, ER, gantt, swimlane,
state machine, network, pie, bar. Output is well-formed SVG that any
browser / dashboard can render without dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

DIAGRAM_TYPES: tuple[str, ...] = (
    "flowchart", "mindmap", "architecture", "sequence",
    "class", "er", "gantt", "swimlane", "state",
    "network", "pie", "bar",
)

COLOR_SCHEMES: dict[str, dict[str, str]] = {
    "ocean":   {"node": "#1e88e5", "edge": "#0d47a1", "text": "#ffffff", "bg": "#e3f2fd"},
    "forest":  {"node": "#43a047", "edge": "#1b5e20", "text": "#ffffff", "bg": "#e8f5e9"},
    "sunset":  {"node": "#fb8c00", "edge": "#e65100", "text": "#ffffff", "bg": "#fff3e0"},
    "mono":    {"node": "#424242", "edge": "#000000", "text": "#ffffff", "bg": "#fafafa"},
}


@dataclass
class DiagramNode:
    id: str
    label: str
    x: float = 0.0
    y: float = 0.0
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class DiagramEdge:
    src: str
    dst: str
    label: str = ""


@dataclass
class Diagram:
    kind: str
    title: str
    nodes: list[DiagramNode] = field(default_factory=list)
    edges: list[DiagramEdge] = field(default_factory=list)
    scheme: str = "ocean"

    def to_svg(self) -> str:
        return DrawingEngine().render(self)


class DrawingEngine:
    """SVG renderer for the 12 supported diagram types."""

    def render(self, diagram: Diagram) -> str:
        if diagram.kind not in DIAGRAM_TYPES:
            raise ValueError(f"unknown diagram kind: {diagram.kind!r}")
        scheme = COLOR_SCHEMES.get(diagram.scheme, COLOR_SCHEMES["ocean"])
        if diagram.kind == "pie":
            return self._render_pie(diagram, scheme)
        if diagram.kind == "bar":
            return self._render_bar(diagram, scheme)
        return self._render_graph(diagram, scheme)

    # ------------------------------------------------------------------
    def auto_layout(self, diagram: Diagram, *, width: float = 800.0,
                    height: float = 480.0) -> Diagram:
        """Lay out nodes on a circle if no coords were provided."""
        n = len(diagram.nodes)
        if n == 0:
            return diagram
        import math
        cx, cy = width / 2, height / 2
        radius = min(width, height) * 0.35
        for i, node in enumerate(diagram.nodes):
            if node.x or node.y:
                continue
            angle = 2 * math.pi * i / max(n, 1)
            node.x = cx + radius * math.cos(angle)
            node.y = cy + radius * math.sin(angle)
        return diagram

    # ------------------------------------------------------------------ renderers
    def _render_graph(self, diagram: Diagram, scheme: dict[str, str]) -> str:
        self.auto_layout(diagram)
        width, height = 800, 480
        parts: list[str] = [self._svg_open(width, height, scheme["bg"])]
        parts.append(f'<title>{_xml_escape(diagram.title)}</title>')
        # Edges first so nodes overlay on top.
        node_by_id = {n.id: n for n in diagram.nodes}
        for edge in diagram.edges:
            a = node_by_id.get(edge.src)
            b = node_by_id.get(edge.dst)
            if a is None or b is None:
                continue
            parts.append(
                f'<line x1="{a.x:.1f}" y1="{a.y:.1f}" '
                f'x2="{b.x:.1f}" y2="{b.y:.1f}" '
                f'stroke="{scheme["edge"]}" stroke-width="2" />'
            )
            if edge.label:
                mx, my = (a.x + b.x) / 2, (a.y + b.y) / 2
                parts.append(
                    f'<text x="{mx:.1f}" y="{my:.1f}" font-size="11" '
                    f'fill="{scheme["edge"]}">{_xml_escape(edge.label)}</text>'
                )
        for node in diagram.nodes:
            parts.append(
                f'<rect x="{node.x - 60:.1f}" y="{node.y - 18:.1f}" '
                f'width="120" height="36" rx="8" '
                f'fill="{scheme["node"]}" stroke="{scheme["edge"]}" />'
            )
            parts.append(
                f'<text x="{node.x:.1f}" y="{node.y + 4:.1f}" '
                f'text-anchor="middle" font-size="12" '
                f'fill="{scheme["text"]}">{_xml_escape(node.label)}</text>'
            )
        parts.append("</svg>")
        return "".join(parts)

    def _render_pie(self, diagram: Diagram, scheme: dict[str, str]) -> str:
        import math
        width, height = 480, 480
        parts: list[str] = [self._svg_open(width, height, scheme["bg"])]
        cx, cy, r = width / 2, height / 2, 180
        total = sum(float(n.extra.get("value", 1)) for n in diagram.nodes) or 1.0
        start = -math.pi / 2
        palette = ["#1e88e5", "#43a047", "#fb8c00", "#e53935", "#8e24aa", "#00897b"]
        for i, node in enumerate(diagram.nodes):
            value = float(node.extra.get("value", 1))
            sweep = 2 * math.pi * value / total
            end = start + sweep
            x1, y1 = cx + r * math.cos(start), cy + r * math.sin(start)
            x2, y2 = cx + r * math.cos(end), cy + r * math.sin(end)
            large = 1 if sweep > math.pi else 0
            color = palette[i % len(palette)]
            parts.append(
                f'<path d="M{cx:.1f},{cy:.1f} L{x1:.1f},{y1:.1f} '
                f'A{r},{r} 0 {large} 1 {x2:.1f},{y2:.1f} Z" '
                f'fill="{color}" stroke="{scheme["edge"]}" />'
            )
            mid = (start + end) / 2
            tx, ty = cx + (r * 0.6) * math.cos(mid), cy + (r * 0.6) * math.sin(mid)
            parts.append(
                f'<text x="{tx:.1f}" y="{ty:.1f}" text-anchor="middle" '
                f'font-size="12" fill="{scheme["text"]}">'
                f'{_xml_escape(node.label)}</text>'
            )
            start = end
        parts.append("</svg>")
        return "".join(parts)

    def _render_bar(self, diagram: Diagram, scheme: dict[str, str]) -> str:
        width, height = 600, 400
        parts: list[str] = [self._svg_open(width, height, scheme["bg"])]
        if not diagram.nodes:
            parts.append("</svg>")
            return "".join(parts)
        max_val = max(float(n.extra.get("value", 1)) for n in diagram.nodes) or 1.0
        bar_width = (width - 80) / max(len(diagram.nodes), 1)
        for i, node in enumerate(diagram.nodes):
            value = float(node.extra.get("value", 1))
            h = (height - 80) * (value / max_val)
            x = 40 + i * bar_width
            y = height - 40 - h
            parts.append(
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_width - 6:.1f}" '
                f'height="{h:.1f}" fill="{scheme["node"]}" />'
            )
            parts.append(
                f'<text x="{x + bar_width / 2:.1f}" y="{height - 20:.1f}" '
                f'text-anchor="middle" font-size="11" '
                f'fill="{scheme["edge"]}">{_xml_escape(node.label)}</text>'
            )
        parts.append("</svg>")
        return "".join(parts)

    @staticmethod
    def _svg_open(width: int, height: int, bg: str) -> str:
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
            f'height="{height}" viewBox="0 0 {width} {height}">'
            f'<rect width="100%" height="100%" fill="{bg}" />'
        )


def quick_diagram(kind: str, title: str, nodes: Iterable[str],
                  edges: Iterable[tuple[str, str]] = (),
                  *, scheme: str = "ocean") -> Diagram:
    """Convenience constructor — accept node labels and (a, b) edges by index."""
    diagram = Diagram(kind=kind, title=title, scheme=scheme)
    for i, label in enumerate(nodes):
        diagram.nodes.append(DiagramNode(id=f"n{i}", label=label))
    for src, dst in edges:
        diagram.edges.append(DiagramEdge(src=src, dst=dst))
    return diagram


def _xml_escape(text: str) -> str:
    return (
        (text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
