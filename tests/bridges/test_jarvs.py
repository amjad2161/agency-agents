"""Tests for bridges.jarvs."""

from __future__ import annotations

from pathlib import Path

import pytest

from bridges.jarvs import JarvsVisualization


@pytest.fixture
def viz(tmp_path: Path) -> JarvsVisualization:
    return JarvsVisualization(asset_dir=tmp_path / "viz")


def test_create_dashboard_writes_chartjs_html(viz):
    out = viz.create_dashboard(
        {
            "latency_ms": {"type": "line", "labels": ["t1", "t2", "t3"], "values": [10, 12, 9]},
            "errors":     {"type": "bar",  "labels": ["a", "b"],         "values": [3, 1]},
        },
        title="Ops Dashboard",
    )
    html = out.read_text(encoding="utf-8")
    assert out.exists()
    assert "Chart" in html
    assert "chart.js" in html.lower()
    assert "Ops Dashboard" in html
    assert "latency_ms" in html
    assert "errors" in html


def test_create_dashboard_folds_scalars_into_overview(viz):
    out = viz.create_dashboard({"users": 100, "sessions": 250})
    html = out.read_text(encoding="utf-8")
    assert "overview" in html
    assert "users" in html and "sessions" in html


def test_create_dashboard_rejects_non_dict(viz):
    with pytest.raises(TypeError):
        viz.create_dashboard([1, 2, 3])  # type: ignore[arg-type]


def test_plot_timeseries_renders_line_chart(viz):
    data = [
        {"day": "mon", "cpu": 30, "mem": 50},
        {"day": "tue", "cpu": 45, "mem": 55},
        {"day": "wed", "cpu": 60, "mem": 52},
    ]
    out = viz.plot_timeseries(data, x_key="day", y_keys=["cpu", "mem"], title="Load")
    html = out.read_text(encoding="utf-8")
    assert "'line'" in html
    assert "cpu" in html and "mem" in html
    assert "mon" in html


def test_plot_timeseries_requires_y_keys(viz):
    with pytest.raises(ValueError, match="y_keys"):
        viz.plot_timeseries([{"x": 1}], x_key="x", y_keys=[])


def test_plot_bar_writes_html(viz):
    out = viz.plot_bar(["a", "b", "c"], [1, 2, 3], title="Counts")
    html = out.read_text(encoding="utf-8")
    assert "'bar'" in html
    assert "Counts" in html


def test_plot_bar_length_mismatch(viz):
    with pytest.raises(ValueError, match="same length"):
        viz.plot_bar(["a"], [1, 2])


def test_plot_radar_writes_html(viz):
    out = viz.plot_radar(["speed", "power", "skill"], [0.7, 0.5, 0.9], title="Stats")
    html = out.read_text(encoding="utf-8")
    assert "'radar'" in html
    assert "speed" in html


def test_plot_network_writes_d3_html(viz):
    nodes = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
    edges = [{"source": "a", "target": "b"}, {"source": "b", "target": "c"}]
    out = viz.plot_network(nodes, edges, title="net")
    html = out.read_text(encoding="utf-8")
    assert "d3" in html.lower()
    assert "forceSimulation" in html
    assert '"id": "a"' in html or '"id":"a"' in html


def test_plot_network_requires_id(viz):
    with pytest.raises(ValueError, match="'id'"):
        viz.plot_network([{"name": "a"}], [])


def test_plot_network_requires_edge_endpoints(viz):
    with pytest.raises(ValueError, match="source"):
        viz.plot_network([{"id": "a"}], [{"from": "a", "to": "b"}])


def test_render_heatmap_writes_html(viz):
    matrix = [[0.1, 0.5, 0.9], [0.2, 0.3, 0.4]]
    out = viz.render_heatmap(matrix, ["r1", "r2"], ["c1", "c2", "c3"], title="hm")
    html = out.read_text(encoding="utf-8")
    assert "d3" in html.lower()
    assert "interpolateViridis" in html
    assert "r1" in html and "c2" in html


def test_render_heatmap_validates_shape(viz):
    with pytest.raises(ValueError):
        viz.render_heatmap([[1, 2], [3]], ["r1", "r2"], ["c1", "c2"])


def test_invoke_dispatches(viz):
    out = viz.invoke("plot_bar", labels=["x"], values=[1], title="t")
    assert out.exists()


def test_invoke_unknown_action(viz):
    with pytest.raises(ValueError, match="unknown action"):
        viz.invoke("plot_pie")
