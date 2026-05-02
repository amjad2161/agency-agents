"""CADAM CAD bridge.

Reads and writes 2D engineering drawings. ``ezdxf`` is used when present
for full DXF support; otherwise a small pure-Python parser/writer for the
ASCII DXF subset (LINE, CIRCLE, ARC, LWPOLYLINE, TEXT, layers, dimensions)
keeps the bridge usable on minimal installs.

SVG export is implemented in pure Python using a deterministic projection
of the parsed entities, so it works regardless of whether ``ezdxf`` is
installed.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from ..logging import get_logger

log = get_logger()


# ---------------------------------------------------------------------------
# Backend detection
# ---------------------------------------------------------------------------

def _has_ezdxf() -> bool:
    try:
        import ezdxf  # noqa: F401
        return True
    except Exception:
        return False


_VALID_ENTITY_TYPES = {"LINE", "CIRCLE", "ARC", "LWPOLYLINE", "POLYLINE", "TEXT"}
_VALID_DIM_UNITS = {"mm", "cm", "m", "in", "ft"}


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class Entity:
    type: str
    layer: str = "0"
    data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {"type": self.type, "layer": self.layer, "data": dict(self.data)}


@dataclass
class Dimension:
    value: float
    unit: str = "mm"
    type: str = "linear"

    def to_dict(self) -> Dict[str, Any]:
        return {"value": self.value, "unit": self.unit, "type": self.type}


# ---------------------------------------------------------------------------
# Bridge
# ---------------------------------------------------------------------------

class CadamBridge:
    """CAD/engineering-drawing bridge."""

    def __init__(self) -> None:
        self._backend = "ezdxf" if _has_ezdxf() else "pure_python"

    @property
    def hardware_available(self) -> bool:
        # Software-only bridge — the "available" flag tracks ezdxf presence.
        return self._backend == "ezdxf"

    @property
    def ezdxf_available(self) -> bool:
        return self._backend == "ezdxf"

    @property
    def backend(self) -> str:
        return self._backend

    def status(self) -> Dict[str, Any]:
        return {"backend": self._backend, "ezdxf_available": self.ezdxf_available}

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    def parse_dxf(self, filepath: str) -> Dict[str, Any]:
        """Parse ``filepath`` and return entities, layers, and dimensions."""
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"DXF file not found: {filepath}")

        if self.ezdxf_available:
            entities, layers, dimensions = _parse_with_ezdxf(path)
        else:
            entities, layers, dimensions = _parse_with_pure_python(path)

        return {
            "entities": [e.to_dict() for e in entities],
            "layers": layers,
            "dimensions": [d.to_dict() for d in dimensions],
            "backend": self._backend,
        }

    def extract_dimensions(self, filepath: str) -> List[Dict[str, Any]]:
        return self.parse_dxf(filepath)["dimensions"]

    def layer_info(self, filepath: str) -> Dict[str, Dict[str, Any]]:
        parsed = self.parse_dxf(filepath)
        info: Dict[str, Dict[str, Any]] = {}
        for layer in parsed["layers"]:
            info[layer] = {"name": layer, "entity_count": 0}
        for entity in parsed["entities"]:
            layer = entity.get("layer", "0")
            info.setdefault(layer, {"name": layer, "entity_count": 0})
            info[layer]["entity_count"] += 1
        return info

    # ------------------------------------------------------------------
    # Writing
    # ------------------------------------------------------------------

    def create_drawing(
        self,
        entities: List[Dict[str, Any]],
        output: str = "drawing.dxf",
    ) -> str:
        """Write ``entities`` to a new DXF file at ``output`` and return the path."""
        out_path = Path(output)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        normalised = [_normalise_entity(e) for e in entities]
        if self.ezdxf_available:
            _write_with_ezdxf(normalised, out_path)
        else:
            _write_with_pure_python(normalised, out_path)
        return str(out_path)

    def dxf_to_svg(self, input_dxf: str, output_svg: str) -> str:
        """Convert ``input_dxf`` into a deterministic SVG at ``output_svg``."""
        parsed = self.parse_dxf(input_dxf)
        entities = [_dict_to_entity(e) for e in parsed["entities"]]
        svg = _entities_to_svg(entities)
        out_path = Path(output_svg)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(svg, encoding="utf-8")
        return str(out_path)

    # ------------------------------------------------------------------
    # Generic dispatch
    # ------------------------------------------------------------------

    def invoke(self, action: str, **kwargs: Any) -> Any:
        registry: Dict[str, Callable[..., Any]] = {
            "parse_dxf": self.parse_dxf,
            "create_drawing": self.create_drawing,
            "dxf_to_svg": self.dxf_to_svg,
            "extract_dimensions": self.extract_dimensions,
            "layer_info": self.layer_info,
            "status": self.status,
        }
        if action not in registry:
            raise ValueError(f"unknown CADAM action: {action!r}")
        return registry[action](**kwargs)


# ---------------------------------------------------------------------------
# ezdxf-backed implementation
# ---------------------------------------------------------------------------

def _parse_with_ezdxf(path: Path) -> Tuple[List[Entity], List[str], List[Dimension]]:
    import ezdxf  # type: ignore

    doc = ezdxf.readfile(str(path))
    msp = doc.modelspace()

    entities: List[Entity] = []
    for e in msp:
        kind = e.dxftype()
        if kind == "LINE":
            entities.append(
                Entity(
                    type="LINE",
                    layer=str(e.dxf.layer),
                    data={
                        "start": [float(e.dxf.start.x), float(e.dxf.start.y)],
                        "end": [float(e.dxf.end.x), float(e.dxf.end.y)],
                    },
                )
            )
        elif kind == "CIRCLE":
            entities.append(
                Entity(
                    type="CIRCLE",
                    layer=str(e.dxf.layer),
                    data={
                        "center": [float(e.dxf.center.x), float(e.dxf.center.y)],
                        "radius": float(e.dxf.radius),
                    },
                )
            )
        elif kind == "ARC":
            entities.append(
                Entity(
                    type="ARC",
                    layer=str(e.dxf.layer),
                    data={
                        "center": [float(e.dxf.center.x), float(e.dxf.center.y)],
                        "radius": float(e.dxf.radius),
                        "start_angle": float(e.dxf.start_angle),
                        "end_angle": float(e.dxf.end_angle),
                    },
                )
            )
        elif kind == "TEXT":
            entities.append(
                Entity(
                    type="TEXT",
                    layer=str(e.dxf.layer),
                    data={
                        "text": str(e.dxf.text),
                        "insert": [float(e.dxf.insert.x), float(e.dxf.insert.y)],
                        "height": float(e.dxf.height),
                    },
                )
            )

    layers = sorted({layer.dxf.name for layer in doc.layers})
    dimensions: List[Dimension] = []
    for d in msp.query("DIMENSION"):
        try:
            value = float(d.get_measurement())
        except Exception:
            value = 0.0
        dimensions.append(Dimension(value=value, unit="mm", type="linear"))
    return entities, layers, dimensions


def _write_with_ezdxf(entities: List[Entity], path: Path) -> None:
    import ezdxf  # type: ignore

    doc = ezdxf.new(dxfversion="R2010")
    msp = doc.modelspace()
    for entity in entities:
        layer = entity.layer or "0"
        if layer not in doc.layers:
            doc.layers.new(name=layer)
        if entity.type == "LINE":
            msp.add_line(
                tuple(entity.data["start"]),
                tuple(entity.data["end"]),
                dxfattribs={"layer": layer},
            )
        elif entity.type == "CIRCLE":
            msp.add_circle(
                tuple(entity.data["center"]),
                float(entity.data["radius"]),
                dxfattribs={"layer": layer},
            )
        elif entity.type == "ARC":
            msp.add_arc(
                tuple(entity.data["center"]),
                float(entity.data["radius"]),
                float(entity.data["start_angle"]),
                float(entity.data["end_angle"]),
                dxfattribs={"layer": layer},
            )
        elif entity.type == "TEXT":
            msp.add_text(
                str(entity.data["text"]),
                dxfattribs={
                    "layer": layer,
                    "height": float(entity.data.get("height", 2.5)),
                },
            ).set_placement(tuple(entity.data["insert"]))
    doc.saveas(str(path))


# ---------------------------------------------------------------------------
# Pure-Python ASCII DXF parser/writer (subset)
# ---------------------------------------------------------------------------

def _parse_with_pure_python(
    path: Path,
) -> Tuple[List[Entity], List[str], List[Dimension]]:
    pairs = _read_dxf_pairs(path)
    entities: List[Entity] = []
    layers: List[str] = []
    dimensions: List[Dimension] = []

    in_entities = False
    in_tables = False
    in_layer_table = False

    current: Optional[Dict[str, Any]] = None
    current_type: Optional[str] = None
    current_dim: Optional[Dict[str, Any]] = None

    def _flush_entity() -> None:
        nonlocal current, current_type
        if current_type and current is not None:
            entity = _build_entity(current_type, current)
            if entity is not None:
                entities.append(entity)
        current = None
        current_type = None

    for code, value in pairs:
        if code == 0:
            if value == "SECTION":
                continue
            if value == "ENDSEC":
                _flush_entity()
                in_entities = False
                in_tables = False
                in_layer_table = False
                continue
            if value == "ENDTAB":
                in_layer_table = False
                continue
            if value in {"LINE", "CIRCLE", "ARC", "LWPOLYLINE", "TEXT"} and in_entities:
                _flush_entity()
                current_type = value
                current = {"layer": "0", "vertices": []}
                continue
            if value == "DIMENSION" and in_entities:
                _flush_entity()
                current_dim = {"value": 0.0}
                current_type = "DIMENSION"
                current = current_dim
                continue
            if value == "LAYER" and in_layer_table:
                current_type = "LAYER"
                current = {}
                continue
            # Unknown entity start — drop any in-flight one.
            _flush_entity()
        elif code == 2:
            if value == "ENTITIES":
                in_entities = True
                in_tables = False
            elif value == "TABLES":
                in_tables = True
                in_entities = False
            elif value == "LAYER" and in_tables:
                in_layer_table = True
            elif current_type == "LAYER" and current is not None:
                layers.append(value)
                current = None
                current_type = None
        elif current is not None:
            _store_pair(current_type, current, code, value)
            if current_type == "DIMENSION" and code == 42:
                try:
                    dimensions.append(
                        Dimension(value=float(value), unit="mm", type="linear")
                    )
                except (TypeError, ValueError):
                    pass

    _flush_entity()
    if "0" not in layers:
        layers.insert(0, "0")
    return entities, sorted(set(layers)), dimensions


def _store_pair(
    entity_type: Optional[str],
    bucket: Dict[str, Any],
    code: int,
    value: str,
) -> None:
    if code == 8:
        bucket["layer"] = value
        return
    if entity_type == "LINE":
        if code == 10:
            bucket.setdefault("start", [0.0, 0.0])[0] = _to_float(value)
        elif code == 20:
            bucket.setdefault("start", [0.0, 0.0])[1] = _to_float(value)
        elif code == 11:
            bucket.setdefault("end", [0.0, 0.0])[0] = _to_float(value)
        elif code == 21:
            bucket.setdefault("end", [0.0, 0.0])[1] = _to_float(value)
    elif entity_type == "CIRCLE":
        if code == 10:
            bucket.setdefault("center", [0.0, 0.0])[0] = _to_float(value)
        elif code == 20:
            bucket.setdefault("center", [0.0, 0.0])[1] = _to_float(value)
        elif code == 40:
            bucket["radius"] = _to_float(value)
    elif entity_type == "ARC":
        if code == 10:
            bucket.setdefault("center", [0.0, 0.0])[0] = _to_float(value)
        elif code == 20:
            bucket.setdefault("center", [0.0, 0.0])[1] = _to_float(value)
        elif code == 40:
            bucket["radius"] = _to_float(value)
        elif code == 50:
            bucket["start_angle"] = _to_float(value)
        elif code == 51:
            bucket["end_angle"] = _to_float(value)
    elif entity_type == "TEXT":
        if code == 10:
            bucket.setdefault("insert", [0.0, 0.0])[0] = _to_float(value)
        elif code == 20:
            bucket.setdefault("insert", [0.0, 0.0])[1] = _to_float(value)
        elif code == 40:
            bucket["height"] = _to_float(value)
        elif code == 1:
            bucket["text"] = value


def _build_entity(entity_type: str, bucket: Dict[str, Any]) -> Optional[Entity]:
    layer = str(bucket.pop("layer", "0"))
    if entity_type == "LINE":
        if "start" in bucket and "end" in bucket:
            return Entity(type="LINE", layer=layer, data={
                "start": list(bucket["start"]),
                "end": list(bucket["end"]),
            })
    elif entity_type == "CIRCLE":
        if "center" in bucket and "radius" in bucket:
            return Entity(type="CIRCLE", layer=layer, data={
                "center": list(bucket["center"]),
                "radius": float(bucket["radius"]),
            })
    elif entity_type == "ARC":
        if "center" in bucket and "radius" in bucket:
            return Entity(type="ARC", layer=layer, data={
                "center": list(bucket["center"]),
                "radius": float(bucket["radius"]),
                "start_angle": float(bucket.get("start_angle", 0.0)),
                "end_angle": float(bucket.get("end_angle", 360.0)),
            })
    elif entity_type == "TEXT":
        if "insert" in bucket:
            return Entity(type="TEXT", layer=layer, data={
                "insert": list(bucket["insert"]),
                "text": str(bucket.get("text", "")),
                "height": float(bucket.get("height", 2.5)),
            })
    return None


def _read_dxf_pairs(path: Path) -> Iterable[Tuple[int, str]]:
    raw = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    pairs: List[Tuple[int, str]] = []
    i = 0
    while i + 1 < len(raw):
        code_line = raw[i].strip()
        value_line = raw[i + 1]
        try:
            code = int(code_line)
        except ValueError:
            i += 1
            continue
        pairs.append((code, value_line))
        i += 2
    return pairs


def _write_with_pure_python(entities: List[Entity], path: Path) -> None:
    layers = sorted({e.layer or "0" for e in entities} | {"0"})
    parts: List[str] = []

    parts.append("0\nSECTION\n2\nHEADER\n0\nENDSEC")
    parts.append("0\nSECTION\n2\nTABLES")
    parts.append("0\nTABLE\n2\nLAYER\n70\n" + str(len(layers)))
    for layer in layers:
        parts.append(f"0\nLAYER\n2\n{layer}\n70\n0\n62\n7\n6\nCONTINUOUS")
    parts.append("0\nENDTAB\n0\nENDSEC")

    parts.append("0\nSECTION\n2\nENTITIES")
    for entity in entities:
        parts.append(_entity_to_dxf(entity))
    parts.append("0\nENDSEC\n0\nEOF\n")

    path.write_text("\n".join(parts), encoding="utf-8")


def _entity_to_dxf(entity: Entity) -> str:
    layer = entity.layer or "0"
    if entity.type == "LINE":
        sx, sy = entity.data["start"]
        ex, ey = entity.data["end"]
        return (
            f"0\nLINE\n8\n{layer}\n10\n{float(sx)}\n20\n{float(sy)}\n"
            f"11\n{float(ex)}\n21\n{float(ey)}"
        )
    if entity.type == "CIRCLE":
        cx, cy = entity.data["center"]
        return (
            f"0\nCIRCLE\n8\n{layer}\n10\n{float(cx)}\n20\n{float(cy)}\n"
            f"40\n{float(entity.data['radius'])}"
        )
    if entity.type == "ARC":
        cx, cy = entity.data["center"]
        return (
            f"0\nARC\n8\n{layer}\n10\n{float(cx)}\n20\n{float(cy)}\n"
            f"40\n{float(entity.data['radius'])}\n"
            f"50\n{float(entity.data.get('start_angle', 0.0))}\n"
            f"51\n{float(entity.data.get('end_angle', 360.0))}"
        )
    if entity.type == "TEXT":
        x, y = entity.data["insert"]
        return (
            f"0\nTEXT\n8\n{layer}\n10\n{float(x)}\n20\n{float(y)}\n"
            f"40\n{float(entity.data.get('height', 2.5))}\n"
            f"1\n{entity.data.get('text', '')}"
        )
    raise ValueError(f"cannot serialise entity type {entity.type!r}")


# ---------------------------------------------------------------------------
# Normalisation + SVG
# ---------------------------------------------------------------------------

def _normalise_entity(raw: Dict[str, Any]) -> Entity:
    if not isinstance(raw, dict):
        raise TypeError(f"entity must be a dict, got {type(raw).__name__}")
    kind = raw.get("type")
    if kind not in _VALID_ENTITY_TYPES:
        raise ValueError(
            f"unknown entity type {kind!r} — expected one of {sorted(_VALID_ENTITY_TYPES)}"
        )
    return Entity(
        type=str(kind),
        layer=str(raw.get("layer", "0")),
        data=dict(raw.get("data", {})),
    )


def _dict_to_entity(raw: Dict[str, Any]) -> Entity:
    return Entity(
        type=str(raw["type"]),
        layer=str(raw.get("layer", "0")),
        data=dict(raw.get("data", {})),
    )


def _entities_to_svg(entities: List[Entity]) -> str:
    bounds = _compute_bounds(entities)
    min_x, min_y, max_x, max_y = bounds
    width = max(1.0, max_x - min_x)
    height = max(1.0, max_y - min_y)

    body: List[str] = []
    for entity in entities:
        body.append(_entity_to_svg(entity, min_y, max_y))

    return (
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="{min_x} {min_y} {width} {height}" '
        f'width="{width}" height="{height}">\n'
        f'<g fill="none" stroke="black" stroke-width="0.5">\n'
        + "\n".join(body)
        + "\n</g>\n</svg>\n"
    )


def _entity_to_svg(entity: Entity, min_y: float, max_y: float) -> str:
    flip = lambda y: (max_y + min_y) - y  # flip Y so SVG matches CAD orientation
    if entity.type == "LINE":
        sx, sy = entity.data["start"]
        ex, ey = entity.data["end"]
        return f'  <line x1="{sx}" y1="{flip(sy)}" x2="{ex}" y2="{flip(ey)}" />'
    if entity.type == "CIRCLE":
        cx, cy = entity.data["center"]
        return f'  <circle cx="{cx}" cy="{flip(cy)}" r="{entity.data["radius"]}" />'
    if entity.type == "ARC":
        cx, cy = entity.data["center"]
        radius = float(entity.data["radius"])
        start = math.radians(float(entity.data.get("start_angle", 0.0)))
        end = math.radians(float(entity.data.get("end_angle", 360.0)))
        sx = cx + radius * math.cos(start)
        sy = flip(cy + radius * math.sin(start))
        ex = cx + radius * math.cos(end)
        ey = flip(cy + radius * math.sin(end))
        large = 1 if (end - start) % (2 * math.pi) > math.pi else 0
        return (
            f'  <path d="M {sx} {sy} A {radius} {radius} 0 {large} 0 {ex} {ey}" />'
        )
    if entity.type == "TEXT":
        x, y = entity.data["insert"]
        height = float(entity.data.get("height", 2.5))
        text = _escape_xml(str(entity.data.get("text", "")))
        return (
            f'  <text x="{x}" y="{flip(y)}" font-size="{height}" '
            f'fill="black">{text}</text>'
        )
    return f"  <!-- unsupported entity {entity.type} -->"


def _compute_bounds(entities: List[Entity]) -> Tuple[float, float, float, float]:
    xs: List[float] = []
    ys: List[float] = []
    for entity in entities:
        if entity.type == "LINE":
            xs.extend([entity.data["start"][0], entity.data["end"][0]])
            ys.extend([entity.data["start"][1], entity.data["end"][1]])
        elif entity.type in {"CIRCLE", "ARC"}:
            cx, cy = entity.data["center"]
            r = float(entity.data["radius"])
            xs.extend([cx - r, cx + r])
            ys.extend([cy - r, cy + r])
        elif entity.type == "TEXT":
            x, y = entity.data["insert"]
            xs.append(x)
            ys.append(y)
    if not xs or not ys:
        return (0.0, 0.0, 100.0, 100.0)
    return (min(xs), min(ys), max(xs), max(ys))


_XML_ESCAPES = {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&apos;"}


def _escape_xml(value: str) -> str:
    return "".join(_XML_ESCAPES.get(c, c) for c in value)


def _to_float(value: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def get_cadam_bridge() -> CadamBridge:
    return CadamBridge()
