"""JarVS Visualization Bridge.

Browser-renderable charts and graphs. Each method writes a
self-contained HTML file (CDN-loaded Chart.js / D3.js) under
``assets/visualizations/`` and returns the path.

Public API
----------
JarvsVisualization
    create_dashboard(data, title)               -> Path
    plot_timeseries(data, x_key, y_keys, title) -> Path
    plot_bar(labels, values, title)             -> Path
    plot_radar(categories, values, title)       -> Path
    plot_network(nodes, edges)                  -> Path
    render_heatmap(matrix, row_labels, col_labels) -> Path
    invoke(action, **kwargs)                    -> Any
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Sequence


_DEFAULT_ASSET_DIR = Path("assets") / "visualizations"


def _slugify(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "_", text or "chart").strip("_").lower()
    return s or "chart"


# Chart.js color palette — perceptually distinct.
_PALETTE = [
    "#1abc9c", "#3498db", "#9b59b6", "#e67e22", "#e74c3c",
    "#f1c40f", "#2ecc71", "#34495e", "#16a085", "#d35400",
]


class JarvsVisualization:
    """Generate browser-renderable visualizations as standalone HTML."""

    def __init__(self, asset_dir: str | Path | None = None) -> None:
        self.asset_dir = Path(asset_dir) if asset_dir else _DEFAULT_ASSET_DIR

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _path(self, name: str) -> Path:
        self.asset_dir.mkdir(parents=True, exist_ok=True)
        return self.asset_dir / name

    @staticmethod
    def _color(i: int) -> str:
        return _PALETTE[i % len(_PALETTE)]

    # ------------------------------------------------------------------
    # Dashboard — multiple cards, one chart each.
    # ------------------------------------------------------------------
    def create_dashboard(
        self,
        data: dict[str, Any],
        title: str = "JARVIS Dashboard",
        output_path: str | Path | None = None,
    ) -> Path:
        """Render a dashboard with one card per metric in ``data``.

        ``data`` shape::

            {
                "metric_name": {
                    "type": "line" | "bar" | "doughnut",
                    "labels": [...],
                    "values": [...],
                }
            }

        Or a flat ``{ "metric": value }`` map (rendered as one bar chart).
        """
        if not isinstance(data, dict):
            raise TypeError("data must be a dict")
        out = Path(output_path) if output_path else self._path("dashboard.html")

        # Normalise: if values are scalars, fold them into a single bar chart.
        normalised: dict[str, Any] = {}
        scalar_pairs: list[tuple[str, Any]] = []
        for k, v in data.items():
            if isinstance(v, dict) and "values" in v:
                normalised[k] = v
            else:
                scalar_pairs.append((k, v))
        if scalar_pairs:
            normalised["overview"] = {
                "type": "bar",
                "labels": [k for k, _ in scalar_pairs],
                "values": [v for _, v in scalar_pairs],
            }

        cards_json = json.dumps(normalised)
        html = _DASHBOARD_TEMPLATE.format(
            title=title,
            generated=time.strftime("%Y-%m-%d %H:%M:%S"),
            cards=cards_json,
        )
        out.write_text(html, encoding="utf-8")
        return out

    # ------------------------------------------------------------------
    # Time-series — multiple Y series against one X axis.
    # ------------------------------------------------------------------
    def plot_timeseries(
        self,
        data: list[dict[str, Any]],
        x_key: str,
        y_keys: Sequence[str],
        title: str = "",
        output_path: str | Path | None = None,
    ) -> Path:
        if not isinstance(data, list):
            raise TypeError("data must be a list of dicts")
        if not y_keys:
            raise ValueError("y_keys must not be empty")
        labels = [row.get(x_key) for row in data]
        datasets = []
        for i, k in enumerate(y_keys):
            color = self._color(i)
            datasets.append({
                "label": k,
                "data": [row.get(k) for row in data],
                "borderColor": color,
                "backgroundColor": color + "33",
                "tension": 0.25,
                "fill": False,
            })
        out = Path(output_path) if output_path else self._path(
            f"timeseries_{_slugify(title)}.html"
        )
        html = _CHARTJS_TEMPLATE.format(
            title=title or "Time Series",
            chart_type="line",
            labels_json=json.dumps(labels),
            datasets_json=json.dumps(datasets),
        )
        out.write_text(html, encoding="utf-8")
        return out

    # ------------------------------------------------------------------
    # Bar
    # ------------------------------------------------------------------
    def plot_bar(
        self,
        labels: Sequence[str],
        values: Sequence[float],
        title: str = "",
        output_path: str | Path | None = None,
    ) -> Path:
        if len(labels) != len(values):
            raise ValueError("labels and values must be the same length")
        datasets = [{
            "label": title or "value",
            "data": list(values),
            "backgroundColor": [self._color(i) for i in range(len(values))],
        }]
        out = Path(output_path) if output_path else self._path(
            f"bar_{_slugify(title)}.html"
        )
        html = _CHARTJS_TEMPLATE.format(
            title=title or "Bar Chart",
            chart_type="bar",
            labels_json=json.dumps(list(labels)),
            datasets_json=json.dumps(datasets),
        )
        out.write_text(html, encoding="utf-8")
        return out

    # ------------------------------------------------------------------
    # Radar / spider
    # ------------------------------------------------------------------
    def plot_radar(
        self,
        categories: Sequence[str],
        values: Sequence[float],
        title: str = "",
        output_path: str | Path | None = None,
    ) -> Path:
        if len(categories) != len(values):
            raise ValueError("categories and values must be the same length")
        color = self._color(0)
        datasets = [{
            "label": title or "value",
            "data": list(values),
            "borderColor": color,
            "backgroundColor": color + "55",
            "pointBackgroundColor": color,
            "fill": True,
        }]
        out = Path(output_path) if output_path else self._path(
            f"radar_{_slugify(title)}.html"
        )
        html = _CHARTJS_TEMPLATE.format(
            title=title or "Radar Chart",
            chart_type="radar",
            labels_json=json.dumps(list(categories)),
            datasets_json=json.dumps(datasets),
        )
        out.write_text(html, encoding="utf-8")
        return out

    # ------------------------------------------------------------------
    # Network (D3 force-directed graph)
    # ------------------------------------------------------------------
    def plot_network(
        self,
        nodes: list[dict[str, Any]],
        edges: list[dict[str, Any]],
        title: str = "Network",
        output_path: str | Path | None = None,
    ) -> Path:
        if not isinstance(nodes, list) or not isinstance(edges, list):
            raise TypeError("nodes and edges must be lists")
        for n in nodes:
            if "id" not in n:
                raise ValueError("each node must have an 'id' field")
        for e in edges:
            if "source" not in e or "target" not in e:
                raise ValueError(
                    "each edge must have 'source' and 'target' fields"
                )
        out = Path(output_path) if output_path else self._path(
            f"network_{_slugify(title)}.html"
        )
        html = _NETWORK_TEMPLATE.format(
            title=title,
            nodes_json=json.dumps(nodes),
            edges_json=json.dumps(edges),
        )
        out.write_text(html, encoding="utf-8")
        return out

    # ------------------------------------------------------------------
    # Heatmap (D3-coloured grid)
    # ------------------------------------------------------------------
    def render_heatmap(
        self,
        matrix: list[list[float]],
        row_labels: Sequence[str],
        col_labels: Sequence[str],
        title: str = "Heatmap",
        output_path: str | Path | None = None,
    ) -> Path:
        if not matrix:
            raise ValueError("matrix must not be empty")
        rows = len(matrix)
        cols = len(matrix[0])
        if any(len(r) != cols for r in matrix):
            raise ValueError("all matrix rows must have the same length")
        if len(row_labels) != rows:
            raise ValueError("row_labels length must match matrix row count")
        if len(col_labels) != cols:
            raise ValueError("col_labels length must match matrix col count")
        flat = [v for r in matrix for v in r]
        vmin, vmax = (min(flat), max(flat)) if flat else (0, 1)
        out = Path(output_path) if output_path else self._path(
            f"heatmap_{_slugify(title)}.html"
        )
        html = _HEATMAP_TEMPLATE.format(
            title=title,
            matrix_json=json.dumps(matrix),
            row_labels_json=json.dumps(list(row_labels)),
            col_labels_json=json.dumps(list(col_labels)),
            vmin=vmin,
            vmax=vmax,
        )
        out.write_text(html, encoding="utf-8")
        return out

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------
    def invoke(self, action: str, **kwargs: Any) -> Any:
        actions = {
            "create_dashboard": self.create_dashboard,
            "plot_timeseries": self.plot_timeseries,
            "plot_bar": self.plot_bar,
            "plot_radar": self.plot_radar,
            "plot_network": self.plot_network,
            "render_heatmap": self.render_heatmap,
        }
        fn = actions.get(action)
        if fn is None:
            raise ValueError(
                f"unknown action {action!r}; choose one of {sorted(actions)}"
            )
        return fn(**kwargs)


# ---------------------------------------------------------------------------
# HTML templates
# ---------------------------------------------------------------------------
_CHARTJS_TEMPLATE = """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>{title}</title>
<style>
  body {{ margin:0; padding:20px; background:#0a0e27; color:#fff;
          font-family: system-ui, sans-serif; }}
  h1 {{ font-weight:300; letter-spacing:0.5px; }}
  .card {{ background:#141a3a; padding:20px; border-radius:10px;
           box-shadow:0 6px 24px rgba(0,0,0,.35); }}
  canvas {{ max-width:100%; }}
</style>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
</head><body>
<h1>{title}</h1>
<div class="card"><canvas id="chart"></canvas></div>
<script>
const ctx = document.getElementById('chart');
new Chart(ctx, {{
  type: '{chart_type}',
  data: {{ labels: {labels_json}, datasets: {datasets_json} }},
  options: {{
    responsive: true,
    plugins: {{
      legend: {{ labels: {{ color: '#fff' }} }},
      title: {{ display: true, text: '{title}', color: '#fff' }}
    }},
    scales: {{
      x: {{ ticks: {{ color: '#bbb' }}, grid: {{ color: '#222a55' }} }},
      y: {{ ticks: {{ color: '#bbb' }}, grid: {{ color: '#222a55' }} }},
      r: {{ ticks: {{ color: '#bbb', backdropColor: 'transparent' }},
            grid: {{ color: '#2a3a6a' }},
            angleLines: {{ color: '#2a3a6a' }},
            pointLabels: {{ color: '#fff' }} }}
    }}
  }}
}});
</script>
</body></html>
"""


_DASHBOARD_TEMPLATE = """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>{title}</title>
<style>
  body {{ margin:0; padding:24px; background:#0a0e27; color:#fff;
          font-family: system-ui, sans-serif; }}
  header {{ display:flex; justify-content:space-between; align-items:center;
            margin-bottom:20px; }}
  h1 {{ font-weight:300; letter-spacing:0.5px; margin:0; }}
  .meta {{ font-size:12px; color:#888; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(360px, 1fr));
           gap:20px; }}
  .card {{ background:#141a3a; padding:18px; border-radius:10px;
           box-shadow:0 6px 24px rgba(0,0,0,.35); }}
  .card h2 {{ margin:0 0 12px; font-size:14px; color:#9ab; text-transform:uppercase;
              letter-spacing:1px; font-weight:400; }}
  canvas {{ max-width:100%; }}
</style>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
</head><body>
<header>
  <h1>{title}</h1>
  <div class="meta">generated {generated}</div>
</header>
<div class="grid" id="grid"></div>
<script>
const CARDS = {cards};
const PALETTE = ["#1abc9c","#3498db","#9b59b6","#e67e22","#e74c3c",
                 "#f1c40f","#2ecc71","#34495e","#16a085","#d35400"];
const grid = document.getElementById('grid');
Object.entries(CARDS).forEach(([name, spec], idx) => {{
  const card = document.createElement('div'); card.className='card';
  const h2 = document.createElement('h2'); h2.textContent = name;
  const canvas = document.createElement('canvas'); canvas.id = 'c_'+idx;
  card.appendChild(h2); card.appendChild(canvas); grid.appendChild(card);
  const type = spec.type || 'bar';
  const datasets = [{{
    label: name,
    data: spec.values,
    backgroundColor: spec.values.map((_, i) => PALETTE[i % PALETTE.length]),
    borderColor: PALETTE[idx % PALETTE.length],
    tension: 0.25,
    fill: type === 'line' ? false : true
  }}];
  new Chart(canvas, {{
    type: type,
    data: {{ labels: spec.labels, datasets: datasets }},
    options: {{
      responsive: true,
      plugins: {{ legend: {{ labels: {{ color:'#fff' }} }} }},
      scales: type === 'doughnut' ? {{}} : {{
        x: {{ ticks: {{ color:'#bbb' }}, grid: {{ color:'#222a55' }} }},
        y: {{ ticks: {{ color:'#bbb' }}, grid: {{ color:'#222a55' }} }}
      }}
    }}
  }});
}});
</script>
</body></html>
"""


_NETWORK_TEMPLATE = """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>{title}</title>
<style>
  html,body {{ margin:0; height:100%; background:#0a0e27; color:#fff;
                font-family: system-ui, sans-serif; }}
  h1 {{ position:fixed; top:12px; left:16px; font-weight:300; margin:0; }}
  svg {{ width:100%; height:100%; display:block; }}
  .link {{ stroke:#444; stroke-opacity:0.7; }}
  .node circle {{ stroke:#fff; stroke-width:1.5; }}
  .node text {{ fill:#fff; font-size:12px; pointer-events:none; }}
</style>
<script src="https://cdn.jsdelivr.net/npm/d3@7.8.5/dist/d3.min.js"></script>
</head><body>
<h1>{title}</h1>
<svg id="g"></svg>
<script>
const NODES = {nodes_json};
const EDGES = {edges_json};
const svg = d3.select('#g');
const w = window.innerWidth, h = window.innerHeight;

const link = svg.append('g').selectAll('line').data(EDGES).join('line')
  .attr('class','link').attr('stroke-width', d => d.weight || 1.5);

const node = svg.append('g').selectAll('g').data(NODES).join('g')
  .attr('class','node').call(d3.drag()
    .on('start', (e,d) => {{ if(!e.active) sim.alphaTarget(0.3).restart(); d.fx=d.x; d.fy=d.y; }})
    .on('drag',  (e,d) => {{ d.fx=e.x; d.fy=e.y; }})
    .on('end',   (e,d) => {{ if(!e.active) sim.alphaTarget(0); d.fx=null; d.fy=null; }})
  );
node.append('circle').attr('r', d => d.size || 10)
  .attr('fill', d => d.color || '#1abc9c');
node.append('text').attr('x', 14).attr('y', 4).text(d => d.label || d.id);

const sim = d3.forceSimulation(NODES)
  .force('link', d3.forceLink(EDGES).id(d => d.id).distance(80))
  .force('charge', d3.forceManyBody().strength(-200))
  .force('center', d3.forceCenter(w/2, h/2))
  .on('tick', () => {{
    link.attr('x1', d=>d.source.x).attr('y1', d=>d.source.y)
        .attr('x2', d=>d.target.x).attr('y2', d=>d.target.y);
    node.attr('transform', d => `translate(${{d.x}},${{d.y}})`);
  }});
</script>
</body></html>
"""


_HEATMAP_TEMPLATE = """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>{title}</title>
<style>
  body {{ margin:0; padding:24px; background:#0a0e27; color:#fff;
          font-family: system-ui, sans-serif; }}
  h1 {{ font-weight:300; }}
  svg {{ background:#141a3a; border-radius:10px; }}
  .lbl {{ fill:#aaa; font-size:11px; }}
  .val {{ fill:#fff; font-size:10px; pointer-events:none; }}
</style>
<script src="https://cdn.jsdelivr.net/npm/d3@7.8.5/dist/d3.min.js"></script>
</head><body>
<h1>{title}</h1>
<svg id="g"></svg>
<script>
const M = {matrix_json};
const ROWS = {row_labels_json};
const COLS = {col_labels_json};
const VMIN = {vmin}, VMAX = {vmax};

const cell = 50, padL = 80, padT = 60;
const W = padL + COLS.length * cell + 20;
const H = padT + ROWS.length * cell + 20;

const svg = d3.select('#g').attr('width', W).attr('height', H);
const color = d3.scaleSequential(d3.interpolateViridis).domain([VMIN, VMAX]);

svg.append('g').selectAll('text').data(COLS).join('text')
  .attr('class','lbl').attr('x', (d,i) => padL + i*cell + cell/2)
  .attr('y', padT - 10).attr('text-anchor','middle').text(d => d);

svg.append('g').selectAll('text').data(ROWS).join('text')
  .attr('class','lbl').attr('x', padL - 10)
  .attr('y', (d,i) => padT + i*cell + cell/2 + 4)
  .attr('text-anchor','end').text(d => d);

const cells = svg.append('g');
M.forEach((row, i) => row.forEach((v, j) => {{
  cells.append('rect')
    .attr('x', padL + j*cell).attr('y', padT + i*cell)
    .attr('width', cell-2).attr('height', cell-2)
    .attr('fill', color(v)).attr('rx', 3);
  cells.append('text').attr('class','val')
    .attr('x', padL + j*cell + cell/2).attr('y', padT + i*cell + cell/2 + 3)
    .attr('text-anchor','middle').text(Number(v).toFixed(2));
}}));
</script>
</body></html>
"""
