"""Tests for the CADAM bridge — runs against the pure-Python backend."""

from __future__ import annotations

from pathlib import Path

import pytest

from agency.bridges.cadam import CadamBridge, get_cadam_bridge


@pytest.fixture()
def bridge() -> CadamBridge:
    return get_cadam_bridge()


@pytest.fixture()
def sample_drawing(bridge: CadamBridge, tmp_path: Path) -> Path:
    entities = [
        {
            "type": "LINE",
            "layer": "OUTLINE",
            "data": {"start": [0.0, 0.0], "end": [100.0, 0.0]},
        },
        {
            "type": "LINE",
            "layer": "OUTLINE",
            "data": {"start": [100.0, 0.0], "end": [100.0, 50.0]},
        },
        {
            "type": "CIRCLE",
            "layer": "HOLES",
            "data": {"center": [50.0, 25.0], "radius": 10.0},
        },
        {
            "type": "ARC",
            "layer": "OUTLINE",
            "data": {
                "center": [0.0, 50.0],
                "radius": 10.0,
                "start_angle": 0.0,
                "end_angle": 90.0,
            },
        },
        {
            "type": "TEXT",
            "layer": "ANNOTATIONS",
            "data": {"insert": [10.0, 10.0], "text": "PART-001", "height": 2.5},
        },
    ]
    out = tmp_path / "sample.dxf"
    bridge.create_drawing(entities, output=str(out))
    return out


def test_factory_returns_bridge(bridge: CadamBridge) -> None:
    assert isinstance(bridge, CadamBridge)
    assert bridge.backend in {"ezdxf", "pure_python"}


def test_status_reports_backend(bridge: CadamBridge) -> None:
    status = bridge.status()
    assert "backend" in status
    assert status["ezdxf_available"] == (bridge.backend == "ezdxf")


def test_create_drawing_writes_file(bridge: CadamBridge, tmp_path: Path) -> None:
    out = tmp_path / "out.dxf"
    path = bridge.create_drawing(
        entities=[
            {"type": "LINE", "layer": "0", "data": {"start": [0.0, 0.0], "end": [1.0, 1.0]}},
        ],
        output=str(out),
    )
    assert Path(path).exists()
    assert Path(path).stat().st_size > 0


def test_create_drawing_rejects_unknown_entity(bridge: CadamBridge, tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        bridge.create_drawing(
            entities=[{"type": "BLOB", "data": {}}],
            output=str(tmp_path / "bad.dxf"),
        )


def test_parse_dxf_round_trips_entities(bridge: CadamBridge, sample_drawing: Path) -> None:
    parsed = bridge.parse_dxf(str(sample_drawing))
    types = sorted(e["type"] for e in parsed["entities"])
    assert "LINE" in types
    assert "CIRCLE" in types
    assert "ARC" in types
    assert "TEXT" in types


def test_parse_dxf_collects_layers(bridge: CadamBridge, sample_drawing: Path) -> None:
    parsed = bridge.parse_dxf(str(sample_drawing))
    layers = set(parsed["layers"])
    assert "OUTLINE" in layers
    assert "HOLES" in layers
    assert "ANNOTATIONS" in layers


def test_parse_dxf_missing_file_raises(bridge: CadamBridge, tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        bridge.parse_dxf(str(tmp_path / "nope.dxf"))


def test_layer_info_counts_entities(bridge: CadamBridge, sample_drawing: Path) -> None:
    info = bridge.layer_info(str(sample_drawing))
    assert info["OUTLINE"]["entity_count"] >= 2
    assert info["HOLES"]["entity_count"] >= 1
    assert info["ANNOTATIONS"]["entity_count"] >= 1


def test_extract_dimensions_returns_list(bridge: CadamBridge, sample_drawing: Path) -> None:
    dims = bridge.extract_dimensions(str(sample_drawing))
    assert isinstance(dims, list)
    # Sample drawing has no DIMENSION entities — should be empty but well-typed.
    for d in dims:
        assert {"value", "unit", "type"} <= set(d.keys())


def test_dxf_to_svg_writes_valid_svg(
    bridge: CadamBridge, sample_drawing: Path, tmp_path: Path
) -> None:
    out = tmp_path / "sample.svg"
    path = bridge.dxf_to_svg(str(sample_drawing), str(out))
    text = Path(path).read_text(encoding="utf-8")
    assert text.startswith("<?xml")
    assert "<svg" in text
    assert "<line" in text
    assert "<circle" in text
    assert "PART-001" in text


def test_invoke_dispatches_known_actions(
    bridge: CadamBridge, sample_drawing: Path
) -> None:
    parsed = bridge.invoke("parse_dxf", filepath=str(sample_drawing))
    assert "entities" in parsed
    layers = bridge.invoke("layer_info", filepath=str(sample_drawing))
    assert isinstance(layers, dict)
    with pytest.raises(ValueError):
        bridge.invoke("magic_export")
