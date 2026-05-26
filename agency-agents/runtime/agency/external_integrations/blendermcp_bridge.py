"""
JARVIS BRAINIAC - Blender MCP Integration Bridge
================================================

Bridge adapter for Blender MCP — a Model Context Protocol server that enables
AI to build complex 3D models in Blender via natural language, without writing
code directly.

Repository: https://github.com/ahujasid/blender-mcp
Features:
    - Create 3D models from text descriptions
    - Edit existing models via natural language instructions
    - Generate geometric primitives with parameters
    - Export models in OBJ, FBX, GLB, STL, and other formats

Usage:
    bridge = BlenderMCPBridge()
    model = bridge.create_model("A wooden table with four legs", style="realistic")
    edited = bridge.edit_model(model.model_id, "Add a glass top to the table")
    geo = bridge.generate_geometry("cube", {"size": 2.0})
    obj_bytes = bridge.export_model(model.model_id, format="obj")
"""

from __future__ import annotations

import base64
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Availability flag
# ---------------------------------------------------------------------------
_BLENDER_MCP_AVAILABLE: bool = False
_BLENDER_MCP_VERSION: str = "unknown"

try:
    import blender_mcp
    from blender_mcp.client import BlenderMCPClient
    from blender_mcp.modeling import ModelCreator, ModelEditor
    from blender_mcp.geometry import GeometryGenerator
    from blender_mcp.export import ModelExporter
    _BLENDER_MCP_AVAILABLE = True
    _BLENDER_MCP_VERSION = getattr(blender_mcp, "__version__", "unknown")
    logger.info("Blender MCP %s loaded successfully.", _BLENDER_MCP_VERSION)
except Exception as _import_exc:
    logger.warning(
        "Blender MCP not installed or failed to import (%s). "
        "Falling back to mock implementations.", _import_exc,
    )

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

class ModelStyle(str, Enum):
    """Supported model generation styles."""
    REALISTIC = "realistic"
    LOW_POLY = "low_poly"
    CARTOON = "cartoon"
    WIREFRAME = "wireframe"
    MINIMAL = "minimal"
    SCULPTED = "sculpted"


@dataclass
class VertexData:
    """3D vertex with position and optional normal/UV."""
    position: Tuple[float, float, float]
    normal: Optional[Tuple[float, float, float]] = None
    uv: Optional[Tuple[float, float]] = None

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"position": list(self.position)}
        if self.normal:
            d["normal"] = list(self.normal)
        if self.uv:
            d["uv"] = list(self.uv)
        return d


@dataclass
class MeshData:
    """Mesh data containing vertices and face indices."""
    vertices: List[VertexData] = field(default_factory=list)
    faces: List[List[int]] = field(default_factory=list)
    vertex_count: int = 0
    face_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "vertex_count": self.vertex_count,
            "face_count": self.face_count,
            "vertices": [v.to_dict() for v in self.vertices[:10]],  # truncated
            "face_count_total": len(self.faces),
        }


@dataclass
class Model3D:
    """A 3D model created or edited via Blender MCP."""
    model_id: str
    description: str
    style: str = "realistic"
    mesh: MeshData = field(default_factory=MeshData)
    materials: List[Dict[str, Any]] = field(default_factory=list)
    modifiers: List[str] = field(default_factory=list)
    bounds: Dict[str, float] = field(default_factory=dict)
    creation_time_ms: int = 0
    edit_history: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_id": self.model_id, "description": self.description,
            "style": self.style, "mesh": self.mesh.to_dict(),
            "materials": self.materials, "modifiers": self.modifiers,
            "bounds": self.bounds, "creation_time_ms": self.creation_time_ms,
            "edit_history": self.edit_history,
            "metadata": self.metadata,
        }


@dataclass
class Geometry:
    """Generated geometric primitive data."""
    shape_type: str
    params: Dict[str, Any] = field(default_factory=dict)
    vertices: List[Tuple[float, float, float]] = field(default_factory=list)
    faces: List[List[int]] = field(default_factory=list)
    vertex_count: int = 0
    face_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "shape_type": self.shape_type, "params": self.params,
            "vertex_count": self.vertex_count, "face_count": self.face_count,
        }


# ---------------------------------------------------------------------------
# Mock implementations
# ---------------------------------------------------------------------------

class _MockModelCreator:
    """Mock model creator generating realistic 3D model descriptions."""

    def create(self, description: str, style: str = "realistic") -> Model3D:
        logger.info("[MOCK] Creating model: '%s' (style=%s)", description, style)
        model_id = f"blender_mcp_{uuid.uuid4().hex[:12]}"
        t0 = time.monotonic()

        desc_lower = description.lower()
        meshes, materials, bounds = self._build_mesh_for_description(desc_lower, style)

        elapsed_ms = int((time.monotonic() - t0) * 1000) + 800

        return Model3D(
            model_id=model_id, description=description, style=style,
            mesh=meshes, materials=materials, modifiers=[],
            bounds=bounds, creation_time_ms=elapsed_ms,
            edit_history=[], metadata={"mock": True, "blender_version": "4.2.0"},
        )

    def _build_mesh_for_description(
        self, desc: str, style: str
    ) -> Tuple[MeshData, List[Dict[str, Any]], Dict[str, float]]:
        """Build a plausible mesh based on the description keywords."""

        if "table" in desc:
            vertices = self._table_vertices()
            faces = self._table_faces()
            materials = [{"name": "wood_oak", "type": "principled_bsdf", "color": [0.55, 0.35, 0.15]}]
            bounds = {"min_x": -1.0, "max_x": 1.0, "min_y": 0.0, "max_y": 0.75, "min_z": -0.6, "max_z": 0.6}
        elif "chair" in desc:
            vertices = self._chair_vertices()
            faces = self._chair_faces()
            materials = [{"name": "fabric_gray", "type": "principled_bsdf", "color": [0.5, 0.5, 0.5]}]
            bounds = {"min_x": -0.4, "max_x": 0.4, "min_y": 0.0, "max_y": 1.0, "min_z": -0.4, "max_z": 0.4}
        elif "sphere" in desc or "ball" in desc:
            vertices = self._sphere_vertices()
            faces = self._sphere_faces()
            materials = [{"name": "plastic_red", "type": "principled_bsdf", "color": [0.9, 0.1, 0.1]}]
            bounds = {"min_x": -0.5, "max_x": 0.5, "min_y": -0.5, "max_y": 0.5, "min_z": -0.5, "max_z": 0.5}
        elif "house" in desc or "building" in desc:
            vertices = self._house_vertices()
            faces = self._house_faces()
            materials = [{"name": "brick_red", "type": "principled_bsdf", "color": [0.7, 0.3, 0.2]}]
            bounds = {"min_x": -2.0, "max_x": 2.0, "min_y": 0.0, "max_y": 3.0, "min_z": -1.5, "max_z": 1.5}
        else:
            vertices = self._generic_vertices()
            faces = self._generic_faces()
            materials = [{"name": "default_gray", "type": "principled_bsdf", "color": [0.7, 0.7, 0.7]}]
            bounds = {"min_x": -0.5, "max_x": 0.5, "min_y": 0.0, "max_y": 1.0, "min_z": -0.5, "max_z": 0.5}

        mesh = MeshData(
            vertices=[VertexData(pos) for pos in vertices],
            faces=faces,
            vertex_count=len(vertices),
            face_count=len(faces),
        )
        return mesh, materials, bounds

    # --- Plausible vertex data for common objects ---

    def _table_vertices(self) -> List[Tuple[float, float, float]]:
        return [
            # Table top
            (-0.9, 0.7, -0.5), (0.9, 0.7, -0.5), (0.9, 0.75, -0.5), (-0.9, 0.75, -0.5),
            (-0.9, 0.7, 0.5), (0.9, 0.7, 0.5), (0.9, 0.75, 0.5), (-0.9, 0.75, 0.5),
            # Leg 1
            (-0.85, 0.0, -0.45), (-0.8, 0.0, -0.45), (-0.8, 0.7, -0.45), (-0.85, 0.7, -0.45),
            (-0.85, 0.0, -0.4), (-0.8, 0.0, -0.4), (-0.8, 0.7, -0.4), (-0.85, 0.7, -0.4),
            # Leg 2
            (0.8, 0.0, -0.45), (0.85, 0.0, -0.45), (0.85, 0.7, -0.45), (0.8, 0.7, -0.45),
            (0.8, 0.0, -0.4), (0.85, 0.0, -0.4), (0.85, 0.7, -0.4), (0.8, 0.7, -0.4),
            # Leg 3
            (-0.85, 0.0, 0.4), (-0.8, 0.0, 0.4), (-0.8, 0.7, 0.4), (-0.85, 0.7, 0.4),
            (-0.85, 0.0, 0.45), (-0.8, 0.0, 0.45), (-0.8, 0.7, 0.45), (-0.85, 0.7, 0.45),
            # Leg 4
            (0.8, 0.0, 0.4), (0.85, 0.0, 0.4), (0.85, 0.7, 0.4), (0.8, 0.7, 0.4),
            (0.8, 0.0, 0.45), (0.85, 0.0, 0.45), (0.85, 0.7, 0.45), (0.8, 0.7, 0.45),
        ]

    def _table_faces(self) -> List[List[int]]:
        return [
            [0, 1, 2, 3], [4, 5, 6, 7], [0, 1, 5, 4], [2, 3, 7, 6],
            [0, 3, 7, 4], [1, 2, 6, 5],
            # Each leg: 6 faces
            [8, 9, 10, 11], [12, 13, 14, 15], [8, 9, 13, 12], [10, 11, 15, 14],
            [16, 17, 18, 19], [20, 21, 22, 23], [16, 17, 21, 20], [18, 19, 23, 22],
            [24, 25, 26, 27], [28, 29, 30, 31], [24, 25, 29, 28], [26, 27, 31, 30],
            [32, 33, 34, 35], [36, 37, 38, 39], [32, 33, 37, 36], [34, 35, 39, 38],
        ]

    def _chair_vertices(self) -> List[Tuple[float, float, float]]:
        return [
            (-0.35, 0.0, -0.35), (0.35, 0.0, -0.35), (0.35, 0.5, -0.35), (-0.35, 0.5, -0.35),
            (-0.35, 0.0, 0.35), (0.35, 0.0, 0.35), (0.35, 0.5, 0.35), (-0.35, 0.5, 0.35),
            # Backrest
            (-0.3, 0.5, 0.3), (0.3, 0.5, 0.3), (0.3, 1.0, 0.35), (-0.3, 1.0, 0.35),
        ]

    def _chair_faces(self) -> List[List[int]]:
        return [
            [0, 1, 2, 3], [4, 5, 6, 7], [0, 1, 5, 4], [2, 3, 7, 6],
            [0, 3, 7, 4], [1, 2, 6, 5],
            [8, 9, 10, 11],
        ]

    def _sphere_vertices(self) -> List[Tuple[float, float, float]]:
        import math
        verts = []
        for lat in range(0, 181, 30):
            for lon in range(0, 361, 30):
                x = 0.5 * math.sin(math.radians(lat)) * math.cos(math.radians(lon))
                y = 0.5 * math.cos(math.radians(lat))
                z = 0.5 * math.sin(math.radians(lat)) * math.sin(math.radians(lon))
                verts.append((round(x, 3), round(y, 3), round(z, 3)))
        return verts

    def _sphere_faces(self) -> List[List[int]]:
        return [[i, i + 1, i + 13, i + 12] for i in range(0, 60, 13) if i + 13 < 78]

    def _house_vertices(self) -> List[Tuple[float, float, float]]:
        return [
            # Walls
            (-2, 0, -1.5), (2, 0, -1.5), (2, 2.5, -1.5), (-2, 2.5, -1.5),
            (-2, 0, 1.5), (2, 0, 1.5), (2, 2.5, 1.5), (-2, 2.5, 1.5),
            # Roof
            (-2.5, 2.5, -2), (2.5, 2.5, -2), (0, 4.0, -2),
            (-2.5, 2.5, 2), (2.5, 2.5, 2), (0, 4.0, 2),
            # Door
            (-0.4, 0, 1.5), (0.4, 0, 1.5), (0.4, 1.8, 1.5), (-0.4, 1.8, 1.5),
        ]

    def _house_faces(self) -> List[List[int]]:
        return [
            [0, 1, 2, 3], [4, 5, 6, 7], [0, 1, 5, 4], [2, 3, 7, 6],
            [0, 3, 7, 4], [1, 2, 6, 5],
            [8, 9, 10], [11, 12, 13], [8, 9, 12, 11], [10, 13, 12, 9],
            [14, 15, 16, 17],
        ]

    def _generic_vertices(self) -> List[Tuple[float, float, float]]:
        return [
            (-0.5, 0, -0.5), (0.5, 0, -0.5), (0.5, 1, -0.5), (-0.5, 1, -0.5),
            (-0.5, 0, 0.5), (0.5, 0, 0.5), (0.5, 1, 0.5), (-0.5, 1, 0.5),
        ]

    def _generic_faces(self) -> List[List[int]]:
        return [[0, 1, 2, 3], [4, 5, 6, 7], [0, 1, 5, 4], [2, 3, 7, 6], [0, 3, 7, 4], [1, 2, 6, 5]]


class _MockModelEditor:
    """Mock model editor applying edits to existing models."""

    def edit(self, model: Model3D, instruction: str) -> Model3D:
        logger.info("[MOCK] Editing model %s: '%s'", model.model_id, instruction)
        inst_lower = instruction.lower()

        edit_desc = f"EDIT: {instruction}"
        model.edit_history.append(edit_desc)
        model.description = f"{model.description} ({instruction})"

        if "color" in inst_lower or "material" in inst_lower:
            if "red" in inst_lower:
                model.materials = [{"name": "painted_red", "type": "principled_bsdf", "color": [0.9, 0.1, 0.1]}]
            elif "blue" in inst_lower:
                model.materials = [{"name": "painted_blue", "type": "principled_bsdf", "color": [0.1, 0.3, 0.9]}]
            elif "green" in inst_lower:
                model.materials = [{"name": "painted_green", "type": "principled_bsdf", "color": [0.1, 0.7, 0.2]}]
            else:
                model.materials = [{"name": "painted_custom", "type": "principled_bsdf", "color": [0.5, 0.5, 0.5]}]

        if "scale" in inst_lower or "size" in inst_lower:
            # Apply a uniform scale factor
            factor = 1.5 if "larger" in inst_lower or "bigger" in inst_lower else 0.7
            for k in model.bounds:
                model.bounds[k] *= factor

        model.modifiers.append(f"edit: {instruction[:40]}")
        model.metadata["last_edit"] = instruction
        return model


class _MockGeometryGenerator:
    """Mock geometry primitive generator."""

    def generate(self, shape_type: str, params: Dict[str, Any]) -> Geometry:
        logger.info("[MOCK] Generating geometry: %s with %s", shape_type, params)
        shape = shape_type.lower()
        size = float(params.get("size", 1.0))
        segments = int(params.get("segments", 8))

        if shape == "cube":
            s = size / 2
            vertices = [
                (-s, -s, -s), (s, -s, -s), (s, s, -s), (-s, s, -s),
                (-s, -s, s), (s, -s, s), (s, s, s), (-s, s, s),
            ]
            faces = [[0, 1, 2, 3], [4, 5, 6, 7], [0, 1, 5, 4], [2, 3, 7, 6], [0, 3, 7, 4], [1, 2, 6, 5]]
        elif shape == "sphere":
            import math
            vertices = []
            faces = []
            r = size / 2
            for i in range(segments + 1):
                lat = math.pi * i / segments
                for j in range(segments + 1):
                    lon = 2 * math.pi * j / segments
                    x = r * math.sin(lat) * math.cos(lon)
                    y = r * math.cos(lat)
                    z = r * math.sin(lat) * math.sin(lon)
                    vertices.append((round(x, 4), round(y, 4), round(z, 4)))
            # Simplified face generation
            faces = [[i, i + 1, i + segments + 2, i + segments + 1]
                     for i in range(0, (segments + 1) * (segments + 1) - segments - 2, segments + 1)]
        elif shape == "cylinder":
            import math
            vertices, faces = [], []
            r, h = size / 2, params.get("height", size)
            for i in range(segments):
                angle = 2 * math.pi * i / segments
                x, z = r * math.cos(angle), r * math.sin(angle)
                vertices.append((round(x, 4), 0.0, round(z, 4)))
                vertices.append((round(x, 4), h, round(z, 4)))
            # Simple side faces
            for i in range(0, len(vertices) - 2, 2):
                faces.append([i, i + 2, i + 3, i + 1])
        else:
            vertices = [(0.0, 0.0, 0.0), (size, 0.0, 0.0), (size / 2, size, 0.0)]
            faces = [[0, 1, 2]]

        return Geometry(
            shape_type=shape_type, params=params,
            vertices=vertices, faces=faces,
            vertex_count=len(vertices), face_count=len(faces),
        )


class _MockModelExporter:
    """Mock model exporter producing format-specific byte streams."""

    def export(self, model: Model3D, fmt: str) -> bytes:
        logger.info("[MOCK] Exporting model %s as %s", model.model_id, fmt)
        fmt_lower = fmt.lower()

        if fmt_lower == "obj":
            return self._export_obj(model)
        elif fmt_lower == "glb":
            return self._export_glb(model)
        elif fmt_lower == "stl":
            return self._export_stl(model)
        elif fmt_lower == "fbx":
            return self._export_fbx(model)
        else:
            return self._export_obj(model)

    def _export_obj(self, model: Model3D) -> bytes:
        lines = [f"# Blender MCP OBJ Export: {model.description}", f"o {model.model_id}"]
        for v in model.mesh.vertices:
            lines.append(f"v {v.position[0]:.4f} {v.position[1]:.4f} {v.position[2]:.4f}")
        for f in model.mesh.faces:
            f_str = " ".join(str(i + 1) for i in f)
            lines.append(f"f {f_str}")
        return "\n".join(lines).encode("utf-8")

    def _export_glb(self, model: Model3D) -> bytes:
        return (
            b"\x67\x6c\x54\x46"  # magic
            b"\x02\x00\x00\x00"  # version
            + (24).to_bytes(4, "little")
            + b"\x4e\x4f\x53\x4a"
            + b'{"asset":{"version":"2.0","generator":"blender-mcp-mock"}}'
        )

    def _export_stl(self, model: Model3D) -> bytes:
        header = b"Blender MCP STL Export" + b"\x00" * (80 - 22)
        # Mock: 1 triangle
        tri = b"\x00\x00\x80\x3f" * 3  # normal
        tri += b"\x00\x00\x00\x00" * 9  # 3 vertices
        tri += b"\x00\x00"  # attribute
        return header + (1).to_bytes(4, "little") + tri

    def _export_fbx(self, model: Model3D) -> bytes:
        return f"FBXMock;{model.model_id};{model.description}".encode("utf-8")


# ---------------------------------------------------------------------------
# Main bridge class
# ---------------------------------------------------------------------------

class BlenderMCPBridge:
    """Bridge adapter for Blender MCP 3D modeling via AI.

    Provides typed access to Blender MCP capabilities with automatic mock
    fallback when the native library is not installed.

    Args:
        blender_host: Hostname of the Blender MCP server.
        blender_port: Port of the Blender MCP server.

    Example:
        bridge = BlenderMCPBridge()
        model = bridge.create_model("A modern chair with steel legs")
        edited = bridge.edit_model(model.model_id, "Change color to blue")
        geo = bridge.generate_geometry("cylinder", {"size": 1.0, "height": 2.0})
        obj = bridge.export_model(model.model_id, format="obj")
    """

    def __init__(
        self,
        blender_host: str = "localhost",
        blender_port: int = 8080,
    ) -> None:
        self.blender_host = blender_host
        self.blender_port = blender_port
        self._model_cache: Dict[str, Model3D] = {}

        if _BLENDER_MCP_AVAILABLE:
            self._creator = ModelCreator(host=blender_host, port=blender_port)
            self._editor = ModelEditor(host=blender_host, port=blender_port)
            self._geo = GeometryGenerator(host=blender_host, port=blender_port)
            self._exporter = ModelExporter(host=blender_host, port=blender_port)
            logger.info("BlenderMCPBridge initialized with native backend v%s.", _BLENDER_MCP_VERSION)
        else:
            self._creator = _MockModelCreator()
            self._editor = _MockModelEditor()
            self._geo = _MockGeometryGenerator()
            self._exporter = _MockModelExporter()
            logger.info("BlenderMCPBridge initialized with mock backend.")

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def create_model(self, description: str, style: str = "realistic") -> Model3D:
        """Create a 3D model from a text description.

        Args:
            description: Natural language description of the desired model.
            style: Visual style — one of "realistic", "low_poly", "cartoon",
                "wireframe", "minimal", "sculpted".

        Returns:
            Model3D with mesh data, materials, bounds, and metadata.
        """
        style_val = style if style in [s.value for s in ModelStyle] else "realistic"
        model = self._creator.create(description, style_val)
        self._model_cache[model.model_id] = model
        logger.info("Created model %s with %d vertices", model.model_id, model.mesh.vertex_count)
        return model

    def edit_model(self, model_id: str, instruction: str) -> Model3D:
        """Edit an existing model via natural language instruction.

        Args:
            model_id: ID of the model to edit (from create_model).
            instruction: Natural language edit instruction.

        Returns:
            Updated Model3D reflecting the applied edits.

        Raises:
            KeyError: If the model_id is not found.
        """
        if model_id not in self._model_cache:
            raise KeyError(f"Model '{model_id}' not found. Create it first with create_model().")

        model = self._model_cache[model_id]
        updated = self._editor.edit(model, instruction)
        self._model_cache[model_id] = updated
        logger.info("Edited model %s: %s", model_id, instruction)
        return updated

    def generate_geometry(self, shape_type: str, params: Dict[str, Any]) -> Geometry:
        """Generate a geometric primitive with specified parameters.

        Args:
            shape_type: Primitive shape — "cube", "sphere", "cylinder",
                "cone", "torus", "plane", "circle".
            params: Shape parameters such as size, segments, radius, height.

        Returns:
            Geometry with vertices, faces, and metadata.
        """
        geometry = self._geo.generate(shape_type, params)
        logger.info("Generated %s geometry: %d vertices", shape_type, geometry.vertex_count)
        return geometry

    def export_model(self, model_id: str, fmt: str = "obj") -> bytes:
        """Export a model to a specific file format.

        Args:
            model_id: ID of the model to export.
            fmt: Export format — "obj", "glb", "gltf", "fbx", "stl", "ply".

        Returns:
            Raw file bytes in the requested format.

        Raises:
            KeyError: If the model_id is not found.
        """
        if model_id not in self._model_cache:
            raise KeyError(f"Model '{model_id}' not found. Create it first with create_model().")

        model = self._model_cache[model_id]
        data = self._exporter.export(model, fmt)
        logger.info("Exported model %s as %s: %d bytes", model_id, fmt, len(data))
        return data

    # ------------------------------------------------------------------
    # Bridge contract
    # ------------------------------------------------------------------

    def health_check(self) -> Dict[str, Any]:
        """Return bridge health status.

        Returns:
            Dict with 'status', 'backend', 'version', and cache info.
        """
        return {
            "status": "healthy",
            "backend": "native" if _BLENDER_MCP_AVAILABLE else "mock",
            "version": _BLENDER_MCP_VERSION if _BLENDER_MCP_AVAILABLE else "mock-1.0.0",
            "blender_host": self.blender_host,
            "blender_port": self.blender_port,
            "cached_models": len(self._model_cache),
            "native_available": _BLENDER_MCP_AVAILABLE,
        }

    def metadata(self) -> Dict[str, Any]:
        """Return bridge metadata for JARVIS registry.

        Returns:
            Dict with bridge name, version, capabilities, and dependencies.
        """
        return {
            "name": "blendermcp_bridge",
            "display_name": "Blender MCP (AI 3D Modeling)",
            "version": "1.0.0",
            "description": (
                "Build complex 3D models in Blender via AI natural language. "
                "Model creation, editing, geometry generation, and multi-format export."
            ),
            "author": "JARVIS Integration Team",
            "license": "MIT",
            "capabilities": [
                "text_to_3d_model",
                "model_editing",
                "geometry_generation",
                "multi_format_export",
                "material_assignment",
                "modifier_stack",
            ],
            "dependencies": {
                "blender_mcp": _BLENDER_MCP_AVAILABLE,
                "blender": ">=4.0",
                "python": ">=3.9",
            },
            "repository": "https://github.com/ahujasid/blender-mcp",
            "mock_fallback": not _BLENDER_MCP_AVAILABLE,
        }

    def clear_cache(self) -> None:
        """Clear the internal model cache."""
        self._model_cache.clear()
        logger.info("Model cache cleared.")

    def get_cached_model(self, model_id: str) -> Optional[Model3D]:
        """Retrieve a cached model by ID.

        Args:
            model_id: Model identifier.

        Returns:
            Model3D if cached, None otherwise.
        """
        return self._model_cache.get(model_id)

    def list_models(self) -> List[str]:
        """List all cached model IDs.

        Returns:
            List of model IDs currently in cache.
        """
        return list(self._model_cache.keys())


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format="%(name)s | %(levelname)s | %(message)s")
    logger.info("=== Blender MCP Bridge Self-Test ===")

    bridge = BlenderMCPBridge()

    # Test health_check
    health = bridge.health_check()
    assert health["status"] == "healthy"
    assert "backend" in health
    logger.info("health_check: %s", health)

    # Test metadata
    meta = bridge.metadata()
    assert meta["name"] == "blendermcp_bridge"
    assert "capabilities" in meta
    logger.info("metadata: %s", meta)

    # Test create_model
    model = bridge.create_model("A wooden table with four legs", style="realistic")
    assert isinstance(model, Model3D)
    assert len(model.model_id) > 0
    assert model.mesh.vertex_count > 0
    assert len(model.materials) > 0
    logger.info("create_model: %s (%d vertices, %d materials)",
                model.model_id, model.mesh.vertex_count, len(model.materials))

    # Test edit_model
    edited = bridge.edit_model(model.model_id, "Change color to blue and make it larger")
    assert "EDIT:" in edited.edit_history[0]
    assert edited.model_id == model.model_id
    logger.info("edit_model: %d edits in history", len(edited.edit_history))

    # Test generate_geometry — cube
    cube = bridge.generate_geometry("cube", {"size": 2.0})
    assert isinstance(cube, Geometry)
    assert cube.vertex_count > 0
    assert cube.face_count > 0
    logger.info("generate_geometry (cube): %d vertices, %d faces", cube.vertex_count, cube.face_count)

    # Test generate_geometry — sphere
    sphere = bridge.generate_geometry("sphere", {"size": 1.0, "segments": 12})
    assert sphere.vertex_count > 0
    logger.info("generate_geometry (sphere): %d vertices", sphere.vertex_count)

    # Test export_model — OBJ
    obj_data = bridge.export_model(model.model_id, fmt="obj")
    assert isinstance(obj_data, bytes)
    assert obj_data.startswith(b"# Blender MCP OBJ")
    logger.info("export_model (obj): %d bytes", len(obj_data))

    # Test export_model — GLB
    glb_data = bridge.export_model(model.model_id, fmt="glb")
    assert isinstance(glb_data, bytes)
    assert glb_data[:4] == b"\x67\x6c\x54\x46"
    logger.info("export_model (glb): %d bytes", len(glb_data))

    # Test export_model — STL
    stl_data = bridge.export_model(model.model_id, fmt="stl")
    assert isinstance(stl_data, bytes)
    logger.info("export_model (stl): %d bytes", len(stl_data))

    # Test cache operations
    cached = bridge.get_cached_model(model.model_id)
    assert cached is model
    model_list = bridge.list_models()
    assert model.model_id in model_list
    logger.info("Cache: %d models cached", len(model_list))

    bridge.clear_cache()
    assert len(bridge.list_models()) == 0
    logger.info("Cache cleared successfully.")

    logger.info("=== All Blender MCP Bridge self-tests passed ===")
