"""Tests for bridges.jarvs."""
from __future__ import annotations

import pytest

from bridges.jarvs import JarVSBridge, SUPPORTED_CHART_TYPES


@pytest.fixture
def bridge() -> JarVSBridge:
    return JarVSBridge()


def test_chart_html_contains_chartjs_cdn(bridge: JarVSBridge) -> None:
    out = bridge.generate_chart_html([1, 2, 3], chart_type="line")
    assert "chart.js" in out.lower() or "chart.umd" in out.lower()
    assert "new Chart" in out
    assert "<canvas" in out


def test_chart_html_supports_all_types(bridge: JarVSBridge) -> None:
    data = [(0, 1), (1, 2), (2, 3)]
    for ctype in SUPPORTED_CHART_TYPES:
        html = bridge.generate_chart_html(data, chart_type=ctype)
        assert "<!doctype html>" in html.lower()


def test_chart_html_invalid_type(bridge: JarVSBridge) -> None:
    with pytest.raises(ValueError):
        bridge.generate_chart_html([1, 2], chart_type="bogus")


def test_chart_html_includes_title(bridge: JarVSBridge) -> None:
    out = bridge.generate_chart_html([1, 2], title="Sales Q1")
    assert "Sales Q1" in out


def test_chart_html_dict_data(bridge: JarVSBridge) -> None:
    out = bridge.generate_chart_html(
        {"labels": [1, 2, 3], "values": [10, 20, 15]})
    assert "10" in out and "20" in out and "15" in out


def test_dashboard_html_renders_panels(bridge: JarVSBridge) -> None:
    panels = [
        {"title": "Revenue", "type": "line", "data": [1, 2, 3, 4]},
        {"title": "Pie", "type": "pie", "data": [10, 20, 30]},
        {"title": "Bars", "type": "bar", "data": [(0, 5), (1, 7)]},
    ]
    html = bridge.generate_dashboard_html(panels)
    assert "Revenue" in html
    assert "Pie" in html
    assert "Bars" in html
    assert "d3" in html.lower()


def test_dashboard_html_invalid_panel_type(bridge: JarVSBridge) -> None:
    with pytest.raises(ValueError):
        bridge.generate_dashboard_html(
            [{"title": "x", "type": "fake", "data": [1]}])


def test_dashboard_html_rejects_non_list(bridge: JarVSBridge) -> None:
    with pytest.raises(ValueError):
        bridge.generate_dashboard_html("not a list")  # type: ignore[arg-type]


def test_export_svg_line(bridge: JarVSBridge) -> None:
    svg = bridge.export_svg([(0, 0), (1, 5), (2, 3)], "line")
    assert svg.startswith("<svg")
    assert "<polyline" in svg
    assert "</svg>" in svg


def test_export_svg_bar(bridge: JarVSBridge) -> None:
    svg = bridge.export_svg([(0, 1), (1, 2), (2, 3)], "bar")
    assert "<rect" in svg
    rect_count = svg.count("<rect")
    assert rect_count >= 4  # background + 3 bars


def test_export_svg_pie(bridge: JarVSBridge) -> None:
    svg = bridge.export_svg([1, 2, 3, 4], "pie")
    assert "<path" in svg


def test_export_svg_scatter(bridge: JarVSBridge) -> None:
    svg = bridge.export_svg([(0, 1), (1, 2), (3, 4)], "scatter")
    assert svg.count("<circle") == 3


def test_export_svg_area(bridge: JarVSBridge) -> None:
    svg = bridge.export_svg([(0, 1), (1, 2), (2, 1)], "area")
    assert "<polygon" in svg
    assert "<polyline" in svg


def test_export_svg_empty_data(bridge: JarVSBridge) -> None:
    svg = bridge.export_svg([], "line")
    assert "no data" in svg
    assert svg.startswith("<svg")


def test_export_svg_invalid_type(bridge: JarVSBridge) -> None:
    with pytest.raises(ValueError):
        bridge.export_svg([1, 2], "doughnut")


def test_invoke_dispatches(bridge: JarVSBridge) -> None:
    svg = bridge.invoke("export_svg", data=[1, 2, 3], chart_type="line")
    assert svg.startswith("<svg")


def test_invoke_unknown(bridge: JarVSBridge) -> None:
    with pytest.raises(ValueError):
        bridge.invoke("not_real")
