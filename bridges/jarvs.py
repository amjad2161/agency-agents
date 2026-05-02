"""JarVS visualization bridge — Chart.js HTML, D3 dashboards, pure SVG export.

Requirement #39 — JarVS visualization.
"""
from __future__ import annotations

import html
import json
import math
from typing import Any, Iterable

SUPPORTED_CHART_TYPES = ("line", "bar", "pie", "scatter", "area")


def _normalize_pairs(data: Any) -> list[tuple[float, float]]:
    """Coerce data into list of (x, y) numeric pairs."""
    if data is None:
        return []
    if isinstance(data, dict):
        labels = data.get("labels")
        values = data.get("values")
        if labels is not None and values is not None:
            out: list[tuple[float, float]] = []
            for i, v in enumerate(values):
                try:
                    out.append((float(i if labels is None else
                                      labels[i] if isinstance(labels[i], (int, float))
                                      else i),
                                float(v)))
                except (ValueError, TypeError):
                    continue
            return out
        if "points" in data:
            return _normalize_pairs(data["points"])
    if isinstance(data, Iterable):
        out2: list[tuple[float, float]] = []
        for i, item in enumerate(data):
            if isinstance(item, dict):
                x = item.get("x", i)
                y = item.get("y", 0)
                try:
                    out2.append((float(x), float(y)))
                except (ValueError, TypeError):
                    continue
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                try:
                    out2.append((float(item[0]), float(item[1])))
                except (ValueError, TypeError):
                    continue
            else:
                try:
                    out2.append((float(i), float(item)))
                except (ValueError, TypeError):
                    continue
        return out2
    return []


class JarVSBridge:
    """Visualization bridge — produces HTML pages and standalone SVG."""

    def __init__(self) -> None:
        self.supported_types = SUPPORTED_CHART_TYPES

    def generate_chart_html(
        self,
        data: Any,
        chart_type: str = "line",
        title: str = "",
        width: int = 800,
        height: int = 400,
    ) -> str:
        if chart_type not in SUPPORTED_CHART_TYPES:
            raise ValueError(f"unsupported chart_type: {chart_type}")

        pairs = _normalize_pairs(data)
        labels = [p[0] for p in pairs]
        values = [p[1] for p in pairs]

        cjs_type = {
            "line": "line",
            "bar": "bar",
            "pie": "pie",
            "scatter": "scatter",
            "area": "line",
        }[chart_type]

        if chart_type == "scatter":
            dataset_data = json.dumps(
                [{"x": p[0], "y": p[1]} for p in pairs])
        else:
            dataset_data = json.dumps(values)

        labels_json = json.dumps(labels)
        fill_flag = "true" if chart_type == "area" else "false"
        safe_title = html.escape(title)

        return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>JarVS — {safe_title or chart_type}</title>
<style>
  body{{margin:0;padding:24px;background:#0b0e1a;color:#e7f0ff;
    font-family:-apple-system,Segoe UI,Roboto,sans-serif}}
  h1{{margin:0 0 16px;font-size:18px;color:#7df9ff;letter-spacing:.04em}}
  .wrap{{max-width:{width + 64}px;background:rgba(20,28,48,.65);
    border:1px solid rgba(125,249,255,.25);border-radius:14px;padding:18px}}
  canvas{{width:100% !important;max-width:{width}px;height:{height}px !important}}
</style>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
</head>
<body>
<div class="wrap">
  <h1>{safe_title or html.escape(chart_type.upper())}</h1>
  <canvas id="chart" width="{int(width)}" height="{int(height)}"></canvas>
</div>
<script>
const ctx = document.getElementById('chart').getContext('2d');
new Chart(ctx, {{
  type: {json.dumps(cjs_type)},
  data: {{
    labels: {labels_json},
    datasets: [{{
      label: {json.dumps(safe_title or chart_type)},
      data: {dataset_data},
      borderColor: '#7df9ff',
      backgroundColor: 'rgba(125,249,255,.32)',
      fill: {fill_flag},
      tension: 0.35,
      pointRadius: 3
    }}]
  }},
  options: {{
    responsive: true,
    plugins: {{ legend: {{ labels: {{ color: '#cfe9ff' }} }} }},
    scales: {{
      x: {{ ticks: {{ color: '#9fb6d9' }}, grid: {{ color: '#1c2640' }} }},
      y: {{ ticks: {{ color: '#9fb6d9' }}, grid: {{ color: '#1c2640' }} }}
    }}
  }}
}});
</script>
</body>
</html>
"""

    def generate_dashboard_html(self, panels: list[dict[str, Any]]) -> str:
        if not isinstance(panels, list):
            raise ValueError("panels must be a list")

        normalized: list[dict[str, Any]] = []
        for p in panels:
            if not isinstance(p, dict):
                raise ValueError("each panel must be a dict")
            ctype = p.get("type", "line")
            if ctype not in SUPPORTED_CHART_TYPES:
                raise ValueError(f"unsupported panel type: {ctype}")
            normalized.append({
                "title": str(p.get("title", "")),
                "type": ctype,
                "data": _normalize_pairs(p.get("data")),
            })

        panels_json = json.dumps(normalized)

        return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>JarVS Dashboard</title>
<style>
  body{{margin:0;padding:24px;background:#06080f;color:#e7f0ff;
    font-family:-apple-system,Segoe UI,Roboto,sans-serif}}
  h1{{margin:0 0 18px;font-size:20px;letter-spacing:.05em;color:#7df9ff}}
  .grid{{display:grid;gap:16px;
    grid-template-columns:repeat(auto-fill,minmax(380px,1fr))}}
  .panel{{background:linear-gradient(160deg,#0e1530,#0a1124);
    border:1px solid rgba(125,249,255,.22);border-radius:14px;padding:14px}}
  .panel h2{{margin:0 0 8px;font-size:14px;color:#cfe9ff;
    text-transform:uppercase;letter-spacing:.08em}}
  svg{{width:100%;height:200px;display:block}}
</style>
<script src="https://cdn.jsdelivr.net/npm/d3@7.9.0/dist/d3.min.js"></script>
</head>
<body>
<h1>JarVS Dashboard</h1>
<div class="grid" id="grid"></div>
<script>
const panels = {panels_json};
const grid = d3.select('#grid');
panels.forEach((panel, idx) => {{
  const card = grid.append('div').attr('class', 'panel');
  card.append('h2').text(panel.title || ('panel ' + (idx + 1)));
  const svg = card.append('svg').attr('viewBox', '0 0 400 200');
  const data = panel.data;
  if (!data.length) {{
    svg.append('text').attr('x', 200).attr('y', 100)
      .attr('text-anchor', 'middle').attr('fill', '#5a7099')
      .text('no data');
    return;
  }}
  const xs = data.map(d => d[0]);
  const ys = data.map(d => d[1]);
  const xMin = Math.min(...xs), xMax = Math.max(...xs);
  const yMin = Math.min(0, ...ys), yMax = Math.max(...ys);
  const sx = d3.scaleLinear().domain([xMin, xMax || 1]).range([30, 380]);
  const sy = d3.scaleLinear().domain([yMin, yMax || 1]).range([180, 20]);

  if (panel.type === 'bar') {{
    const w = data.length > 1 ? (350 / data.length) - 4 : 30;
    svg.selectAll('rect').data(data).enter().append('rect')
      .attr('x', d => sx(d[0]) - w / 2)
      .attr('y', d => sy(d[1]))
      .attr('width', w)
      .attr('height', d => 180 - sy(d[1]))
      .attr('fill', '#7df9ff').attr('opacity', .75);
  }} else if (panel.type === 'pie') {{
    const total = ys.reduce((a, b) => a + Math.abs(b), 0) || 1;
    let a0 = 0;
    const arc = d3.arc().innerRadius(20).outerRadius(80);
    const g = svg.append('g').attr('transform', 'translate(200,100)');
    data.forEach((d, i) => {{
      const a1 = a0 + (Math.abs(d[1]) / total) * Math.PI * 2;
      g.append('path').attr('d', arc({{startAngle: a0, endAngle: a1}}))
        .attr('fill', d3.interpolateCool(i / Math.max(1, data.length - 1)));
      a0 = a1;
    }});
  }} else if (panel.type === 'scatter') {{
    svg.selectAll('circle').data(data).enter().append('circle')
      .attr('cx', d => sx(d[0])).attr('cy', d => sy(d[1]))
      .attr('r', 4).attr('fill', '#7df9ff').attr('opacity', .85);
  }} else {{
    const line = d3.line().x(d => sx(d[0])).y(d => sy(d[1]))
      .curve(d3.curveCatmullRom);
    if (panel.type === 'area') {{
      const area = d3.area().x(d => sx(d[0]))
        .y0(sy(yMin)).y1(d => sy(d[1]))
        .curve(d3.curveCatmullRom);
      svg.append('path').attr('d', area(data))
        .attr('fill', 'rgba(125,249,255,.25)');
    }}
    svg.append('path').attr('d', line(data))
      .attr('fill', 'none').attr('stroke', '#7df9ff')
      .attr('stroke-width', 2);
  }}
}});
</script>
</body>
</html>
"""

    def export_svg(
        self, data: Any, chart_type: str = "line",
        width: int = 400, height: int = 200,
    ) -> str:
        if chart_type not in SUPPORTED_CHART_TYPES:
            raise ValueError(f"unsupported chart_type: {chart_type}")

        pairs = _normalize_pairs(data)
        pad = 24
        if not pairs:
            return (
                f'<svg xmlns="http://www.w3.org/2000/svg" '
                f'width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
                f'<rect width="100%" height="100%" fill="#06080f"/>'
                f'<text x="{width // 2}" y="{height // 2}" fill="#5a7099" '
                f'text-anchor="middle" font-family="sans-serif" font-size="14">'
                f'no data</text></svg>'
            )

        xs = [p[0] for p in pairs]
        ys = [p[1] for p in pairs]
        x_min, x_max = min(xs), max(xs)
        y_min, y_max = min(0.0, min(ys)), max(ys)
        if x_max == x_min:
            x_max = x_min + 1.0
        if y_max == y_min:
            y_max = y_min + 1.0

        def sx(x: float) -> float:
            return pad + (x - x_min) / (x_max - x_min) * (width - 2 * pad)

        def sy(y: float) -> float:
            return (height - pad) - (y - y_min) / (y_max - y_min) * (
                height - 2 * pad)

        body_parts: list[str] = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
            f'height="{height}" viewBox="0 0 {width} {height}">',
            '<rect width="100%" height="100%" fill="#06080f"/>',
        ]

        if chart_type == "bar":
            bar_w = max(2.0, ((width - 2 * pad) / max(1, len(pairs))) - 4)
            for x, y in pairs:
                bx = sx(x) - bar_w / 2
                by = sy(y)
                bh = sy(y_min) - by
                body_parts.append(
                    f'<rect x="{bx:.2f}" y="{by:.2f}" '
                    f'width="{bar_w:.2f}" height="{bh:.2f}" '
                    f'fill="#7df9ff" opacity="0.75"/>'
                )
        elif chart_type == "pie":
            total = sum(abs(y) for y in ys) or 1.0
            cx, cy = width / 2, height / 2
            radius = min(width, height) / 2 - pad
            angle = -math.pi / 2
            palette = ["#7df9ff", "#ff6ec7", "#ffd166",
                       "#06d6a0", "#a78bfa", "#ef476f"]
            for i, (_, yval) in enumerate(pairs):
                slice_a = (abs(yval) / total) * 2 * math.pi
                a1 = angle
                a2 = angle + slice_a
                x1 = cx + radius * math.cos(a1)
                y1 = cy + radius * math.sin(a1)
                x2 = cx + radius * math.cos(a2)
                y2 = cy + radius * math.sin(a2)
                large = 1 if slice_a > math.pi else 0
                color = palette[i % len(palette)]
                body_parts.append(
                    f'<path d="M{cx},{cy} L{x1:.2f},{y1:.2f} '
                    f'A{radius:.2f},{radius:.2f} 0 {large} 1 '
                    f'{x2:.2f},{y2:.2f} Z" fill="{color}" opacity="0.85"/>'
                )
                angle = a2
        elif chart_type == "scatter":
            for x, y in pairs:
                body_parts.append(
                    f'<circle cx="{sx(x):.2f}" cy="{sy(y):.2f}" r="3" '
                    f'fill="#7df9ff" opacity="0.85"/>'
                )
        else:
            pts = " ".join(f"{sx(x):.2f},{sy(y):.2f}" for x, y in pairs)
            if chart_type == "area":
                area_pts = (
                    f"{sx(pairs[0][0]):.2f},{sy(y_min):.2f} "
                    + pts
                    + f" {sx(pairs[-1][0]):.2f},{sy(y_min):.2f}"
                )
                body_parts.append(
                    f'<polygon points="{area_pts}" '
                    f'fill="rgba(125,249,255,0.25)"/>'
                )
            body_parts.append(
                f'<polyline points="{pts}" fill="none" '
                f'stroke="#7df9ff" stroke-width="2"/>'
            )

        body_parts.append("</svg>")
        return "".join(body_parts)

    def invoke(self, action: str, **kwargs: Any) -> Any:
        actions = {
            "generate_chart_html": self.generate_chart_html,
            "generate_dashboard_html": self.generate_dashboard_html,
            "export_svg": self.export_svg,
        }
        fn = actions.get(action)
        if fn is None:
            raise ValueError(f"unknown action: {action}")
        return fn(**kwargs)
