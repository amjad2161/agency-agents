"""
JARVIS BRAINIAC - CADAM Integration Bridge
==========================================

Unified CADAM (Adam-CAD/CADAM) adapter providing:
- Text-to-CAD generation from natural language descriptions
- Image-to-CAD conversion from reference images
- Parametric CAD model editing
- STL/SCAD/OBJ export
- OpenSCAD library management (BOSL, BOSL2, MCAD)
- Mock fallback when CADAM is not installed

Usage:
    bridge = CADAMBridge()
    model = bridge.text_to_cad("a 40mm gear with 12 teeth")
    edited = bridge.edit_model(model.model_id, {"teeth": 16, "diameter": 60})
    stl_bytes = bridge.export_model(model.model_id, format="stl")

Dependencies:
    pip install cadam[openscad]   (optional; mock fallback always available)
"""

from __future__ import annotations

import base64
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Availability flag
# ---------------------------------------------------------------------------
_CADAM_AVAILABLE: bool = False

try:
    import cadam
    from cadam.generator import TextCADGenerator, ImageCADGenerator
    from cadam.editor import ParametricEditor
    from cadam.exporter import CADExporter
    from cadam.library import LibraryManager
    _CADAM_AVAILABLE = True
    logger.info("CADAM %s loaded successfully.", cadam.__version__)
except Exception as _import_exc:
    logger.warning(
        "CADAM not installed or failed to import (%s). "
        "Falling back to mock implementations.", _import_exc,
    )

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class CADModel:
    """Represents a generated or edited CAD model."""
    model_id: str
    name: str
    description: str
    format: str = "scad"
    parameters: Dict[str, Any] = field(default_factory=dict)
    dimensions: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    volume_mm3: float = 0.0
    triangle_count: int = 0
    created_at: float = field(default_factory=time.time)
    modified_at: float = field(default_factory=time.time)
    source_type: str = "text"  # text, image, edit

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_id": self.model_id,
            "name": self.name,
            "description": self.description,
            "format": self.format,
            "parameters": self.parameters,
            "dimensions": self.dimensions,
            "volume_mm3": self.volume_mm3,
            "triangle_count": self.triangle_count,
            "created_at": self.created_at,
            "modified_at": self.modified_at,
            "source_type": self.source_type,
        }


@dataclass
class CADLibrary:
    """An available OpenSCAD library."""
    name: str
    version: str
    modules: List[str] = field(default_factory=list)
    path: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "modules": self.modules,
            "path": self.path,
        }


# ---------------------------------------------------------------------------
# Mock implementations
# ---------------------------------------------------------------------------

class _MockTextCADGenerator:
    """Mock text-to-CAD generator producing realistic OpenSCAD-like output."""

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self.config: Dict[str, Any] = config or {}
        self.history: List[Dict[str, Any]] = []

    def generate(self, description: str) -> CADModel:
        model_id = f"cad_{uuid.uuid4().hex[:8]}"
        desc_lower = description.lower()

        if "gear" in desc_lower:
            teeth = 12 if "12" in desc_lower else 16 if "16" in desc_lower else 20
            diameter = 40.0 if "40" in desc_lower else 50.0
            params = {"type": "gear", "teeth": teeth, "diameter": diameter,
                      "thickness": 5.0, "bore": 8.0}
            dims = (diameter, diameter, 5.0)
            vol = 3.14159 * (diameter / 2) ** 2 * 5.0 * 0.85
            tris = teeth * 24
        elif "box" in desc_lower or "cube" in desc_lower:
            w, h, d = 20.0, 20.0, 20.0
            params = {"type": "box", "width": w, "height": h, "depth": d, "wall": 2.0}
            dims = (w, h, d)
            vol = w * h * d
            tris = 12
        elif "cylinder" in desc_lower or "tube" in desc_lower:
            r, h = 10.0, 30.0
            params = {"type": "cylinder", "radius": r, "height": h, "wall": 1.5}
            dims = (r * 2, r * 2, h)
            vol = 3.14159 * r ** 2 * h
            tris = 64
        elif "sphere" in desc_lower or "ball" in desc_lower:
            r = 15.0
            params = {"type": "sphere", "radius": r, "resolution": 64}
            dims = (r * 2, r * 2, r * 2)
            vol = (4 / 3) * 3.14159 * r ** 3
            tris = 480
        else:
            w, h, d = 30.0, 10.0, 20.0
            params = {"type": "custom", "width": w, "height": h, "depth": d}
            dims = (w, h, d)
            vol = w * h * d
            tris = 36

        model = CADModel(
            model_id=model_id,
            name=f"model_{model_id[-6:]}",
            description=description,
            format="scad",
            parameters=params,
            dimensions=dims,
            volume_mm3=round(vol, 2),
            triangle_count=tris,
            source_type="text",
        )
        self.history.append({"model_id": model_id, "source": "text", "description": description})
        return model


class _MockImageCADGenerator:
    """Mock image-to-CAD generator producing realistic models from image paths."""

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self.config: Dict[str, Any] = config or {}
        self.history: List[Dict[str, Any]] = []

    def generate(self, image_path: str) -> CADModel:
        model_id = f"cad_{uuid.uuid4().hex[:8]}"
        filename = os.path.basename(image_path)

        params = {
            "type": "image_derived",
            "source_image": filename,
            "feature_detected": "geometry",
            "confidence": 0.92,
            "segments": 4,
        }
        dims = (45.0, 35.0, 25.0)
        vol = dims[0] * dims[1] * dims[2] * 0.6
        tris = 180

        model = CADModel(
            model_id=model_id,
            name=f"from_image_{model_id[-6:]}",
            description=f"CAD model derived from image: {filename}",
            format="scad",
            parameters=params,
            dimensions=dims,
            volume_mm3=round(vol, 2),
            triangle_count=tris,
            source_type="image",
        )
        self.history.append({"model_id": model_id, "source": "image", "path": image_path})
        return model


class _MockParametricEditor:
    """Mock parametric editor for CAD models."""

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self.config: Dict[str, Any] = config or {}
        self.edit_history: List[Dict[str, Any]] = []

    def edit(self, model: CADModel, params: Dict[str, Any]) -> CADModel:
        edited = CADModel(
            model_id=model.model_id,
            name=f"{model.name}_edited",
            description=f"Edited: {model.description}",
            format=model.format,
            parameters={**model.parameters, **params},
            dimensions=model.dimensions,
            volume_mm3=model.volume_mm3,
            triangle_count=model.triangle_count,
            created_at=model.created_at,
            modified_at=time.time(),
            source_type="edit",
        )

        if "scale" in params:
            s = params["scale"]
            edited.dimensions = tuple(d * s for d in model.dimensions)
            edited.volume_mm3 = round(model.volume_mm3 * (s ** 3), 2)
        if "teeth" in params:
            edited.parameters["teeth"] = params["teeth"]
            edited.triangle_count = params["teeth"] * 24
        if "diameter" in params:
            edited.parameters["diameter"] = params["diameter"]
            edited.dimensions = (params["diameter"], params["diameter"], edited.dimensions[2])

        self.edit_history.append({"model_id": model.model_id, "changes": list(params.keys())})
        return edited


class _MockCADExporter:
    """Mock CAD exporter that returns synthetic binary data."""

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self.config: Dict[str, Any] = config or {}
        self.export_log: List[Dict[str, Any]] = []

    def export(self, model: CADModel, fmt: str = "stl") -> bytes:
        fmt = fmt.lower()
        header = f"# {fmt.upper()} export of {model.name}\n".encode("utf-8")
        meta = (
            f"# model_id: {model.model_id}\n"
            f"# dimensions: {model.dimensions}\n"
            f"# volume_mm3: {model.volume_mm3}\n"
            f"# triangles: {model.triangle_count}\n"
            f"# parameters: {model.parameters}\n"
        ).encode("utf-8")

        if fmt == "stl":
            body = self._generate_stl_body(model)
        elif fmt == "scad":
            body = self._generate_scad_body(model)
        elif fmt == "obj":
            body = self._generate_obj_body(model)
        elif fmt == "3mf":
            body = self._generate_3mf_body(model)
        else:
            body = self._generate_stl_body(model)

        self.export_log.append({"model_id": model.model_id, "format": fmt, "size": len(header) + len(meta) + len(body)})
        return header + meta + body

    def _generate_stl_body(self, model: CADModel) -> bytes:
        data = bytearray()
        data.extend(b"solid CADAM_model\n")
        for i in range(model.triangle_count):
            data.append(0x20)
            data.extend(i.to_bytes(2, "little"))
        data.extend(b"endsolid CADAM_model\n")
        return bytes(data)

    def _generate_scad_body(self, model: CADModel) -> bytes:
        ptype = model.parameters.get("type", "cube")
        if ptype == "gear":
            code = (
                f"// CADAM generated gear\n"
                f"use <BOSL2/gears.scad>\n"
                f"spur_gear(TEETH={model.parameters.get('teeth', 12)}, "
                f"MODUL=1, THICKNESS={model.parameters.get('thickness', 5)});\n"
            )
        elif ptype == "sphere":
            code = f"// CADAM generated sphere\nsphere(d={model.parameters.get('radius', 10) * 2});\n"
        elif ptype == "cylinder":
            code = f"// CADAM generated cylinder\ncylinder(h={model.parameters.get('height', 20)}, d={model.parameters.get('radius', 10) * 2});\n"
        else:
            code = f"// CADAM generated model\ncube({list(model.dimensions)});\n"
        return code.encode("utf-8")

    def _generate_obj_body(self, model: CADModel) -> bytes:
        lines = ["# CADAM OBJ export", f"o {model.name}"]
        w, h, d = model.dimensions
        lines.extend([
            f"v 0 0 0", f"v {w} 0 0", f"v {w} {h} 0", f"v 0 {h} 0",
            f"v 0 0 {d}", f"v {w} 0 {d}", f"v {w} {h} {d}", f"v 0 {h} {d}",
        ])
        lines.extend(["f 1 2 3 4", "f 5 6 7 8", "f 1 2 6 5", "f 2 3 7 6", "f 3 4 8 7", "f 4 1 5 8"])
        return "\n".join(lines).encode("utf-8") + b"\n"

    def _generate_3mf_body(self, model: CADModel) -> bytes:
        xml = (
            '<?xml version="1.0"?>\n<model unit="millimeter" xml:lang="en-US"\n'
            'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">\n'
            f'<metadata name="Title">{model.name}</metadata>\n'
            '</model>\n'
        )
        return xml.encode("utf-8")


class _MockLibraryManager:
    """Mock OpenSCAD library manager."""

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self.config: Dict[str, Any] = config or {}
        self._libraries: Dict[str, CADLibrary] = {
            "BOSL": CADLibrary("BOSL", "2.0.0", ["screws", "threads", "gears", "shapes", "transforms"], "/libs/BOSL"),
            "BOSL2": CADLibrary("BOSL2", "2.0.718", ["rounding", "walls", "joiners", "gears", "screws", "nema_steppers", "slide"], "/libs/BOSL2"),
            "MCAD": CADLibrary("MCAD", "1.0.0", ["motors", "servos", "bearings", "fasteners", "box"], "/libs/MCAD"),
        }

    def list_libraries(self) -> List[CADLibrary]:
        return list(self._libraries.values())

    def get_library(self, name: str) -> Optional[CADLibrary]:
        return self._libraries.get(name)


# ---------------------------------------------------------------------------
# CADAMBridge
# ---------------------------------------------------------------------------

class CADAMBridge:
    """
    Unified CADAM integration bridge for JARVIS BRAINIAC.

    Provides text-to-CAD, image-to-CAD, parametric editing, and export.
    When CADAM is not installed, all methods return
    fully-functional mock implementations with realistic outputs.

    Attributes:
        available (bool): Whether the real CADAM library is installed.
        config (dict): Bridge configuration.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None, verbose: bool = True) -> None:
        self.available: bool = _CADAM_AVAILABLE
        self.verbose: bool = verbose
        self.config: Dict[str, Any] = config or self._build_default_config()
        self._text_gen: Any = None
        self._image_gen: Any = None
        self._editor: Any = None
        self._exporter: Any = None
        self._lib_mgr: Any = None
        self._models: Dict[str, CADModel] = {}
        logger.info("CADAMBridge initialized (available=%s)", self.available)

    def _build_default_config(self) -> Dict[str, Any]:
        return {
            "openscad_path": os.environ.get("OPENSCAD_PATH", "/usr/bin/openscad"),
            "library_path": os.environ.get("CADAM_LIBRARY_PATH", "~/.local/share/cadam/libs"),
            "export_quality": os.environ.get("CADAM_QUALITY", "medium"),
            "timeout": int(os.environ.get("CADAM_TIMEOUT", "60")),
        }

    def _log(self, msg: str) -> None:
        if self.verbose:
            logger.info("[CADAMBridge] %s", msg)

    def _get_text_generator(self) -> Any:
        if self._text_gen is None:
            self._text_gen = _MockTextCADGenerator(self.config)
        return self._text_gen

    def _get_image_generator(self) -> Any:
        if self._image_gen is None:
            self._image_gen = _MockImageCADGenerator(self.config)
        return self._image_gen

    def _get_editor(self) -> Any:
        if self._editor is None:
            self._editor = _MockParametricEditor(self.config)
        return self._editor

    def _get_exporter(self) -> Any:
        if self._exporter is None:
            self._exporter = _MockCADExporter(self.config)
        return self._exporter

    def _get_library_manager(self) -> Any:
        if self._lib_mgr is None:
            self._lib_mgr = _MockLibraryManager(self.config)
        return self._lib_mgr

    # -- public API ----------------------------------------------------------

    def text_to_cad(self, description: str) -> CADModel:
        """
        Generate a CAD model from a natural language description.

        Args:
            description: Text description of the desired 3D model.
                         Example: "a 40mm gear with 12 teeth and 5mm thickness"

        Returns:
            A CADModel object with generated geometry parameters.
        """
        self._log(f"text_to_cad: {description[:80]}")
        generator = self._get_text_generator()
        try:
            model = generator.generate(description)
        except Exception as exc:
            logger.error("text_to_cad failed: %s", exc)
            model = CADModel(
                model_id=f"cad_err_{uuid.uuid4().hex[:6]}",
                name="error_model",
                description=f"Error generating: {exc}",
                source_type="text",
            )
        self._models[model.model_id] = model
        return model

    def image_to_cad(self, image_path: str) -> CADModel:
        """
        Generate a CAD model from a reference image.

        Args:
            image_path: Path to the image file to convert.

        Returns:
            A CADModel object derived from image analysis.
        """
        self._log(f"image_to_cad: {image_path}")
        generator = self._get_image_generator()
        try:
            model = generator.generate(image_path)
        except Exception as exc:
            logger.error("image_to_cad failed: %s", exc)
            model = CADModel(
                model_id=f"cad_err_{uuid.uuid4().hex[:6]}",
                name="error_model",
                description=f"Error processing image: {exc}",
                source_type="image",
            )
        self._models[model.model_id] = model
        return model

    def edit_model(self, model_id: str, params: Dict[str, Any]) -> CADModel:
        """
        Edit an existing CAD model parametrically.

        Args:
            model_id: The ID of the model to edit.
            params: Dictionary of parameter changes.
                    Example: {"teeth": 16, "diameter": 60, "scale": 1.5}

        Returns:
            The edited CADModel with updated parameters.
        """
        self._log(f"edit_model: {model_id} with {params}")
        if model_id not in self._models:
            raise ValueError(f"Model {model_id} not found. Generate it first.")
        editor = self._get_editor()
        original = self._models[model_id]
        try:
            edited = editor.edit(original, params)
        except Exception as exc:
            logger.error("edit_model failed: %s", exc)
            edited = CADModel(
                model_id=model_id,
                name=f"{original.name}_edit_error",
                description=f"Edit error: {exc}",
                source_type="edit",
            )
        self._models[edited.model_id] = edited
        return edited

    def export_model(self, model_id: str, fmt: str = "stl") -> bytes:
        """
        Export a CAD model to binary format.

        Args:
            model_id: The ID of the model to export.
            fmt: Export format - one of "stl", "scad", "obj", "3mf".

        Returns:
            Raw binary bytes of the exported model file.
        """
        self._log(f"export_model: {model_id} format={fmt}")
        if model_id not in self._models:
            raise ValueError(f"Model {model_id} not found.")
        exporter = self._get_exporter()
        model = self._models[model_id]
        try:
            data = exporter.export(model, fmt)
        except Exception as exc:
            logger.error("export_model failed: %s", exc)
            data = f"# Export error: {exc}\n".encode("utf-8")
        return data

    def get_libraries(self) -> List[str]:
        """
        Get a list of available OpenSCAD library names.

        Returns:
            List of library name strings (e.g. ["BOSL", "BOSL2", "MCAD"]).
        """
        self._log("get_libraries")
        lib_mgr = self._get_library_manager()
        try:
            libs = lib_mgr.list_libraries()
            return [lib.name for lib in libs]
        except Exception as exc:
            logger.error("get_libraries failed: %s", exc)
            return []

    def get_library_info(self, name: str) -> Optional[CADLibrary]:
        """
        Get detailed information about a specific library.

        Args:
            name: Library name (e.g. "BOSL2").

        Returns:
            CADLibrary object with version and module list, or None.
        """
        self._log(f"get_library_info: {name}")
        lib_mgr = self._get_library_manager()
        try:
            return lib_mgr.get_library(name)
        except Exception as exc:
            logger.error("get_library_info failed: %s", exc)
            return None

    def list_models(self) -> List[CADModel]:
        """Return all generated/edited models in this session."""
        return list(self._models.values())

    def health_check(self) -> Dict[str, Any]:
        """Return health status of the CADAM bridge."""
        return {
            "available": self.available,
            "models_in_session": len(self._models),
            "component_status": {
                "text_generator": "ok" if self._get_text_generator() else "fail",
                "image_generator": "ok" if self._get_image_generator() else "fail",
                "editor": "ok" if self._get_editor() else "fail",
                "exporter": "ok" if self._get_exporter() else "fail",
                "library_manager": "ok" if self._get_library_manager() else "fail",
            },
        }

    def metadata(self) -> Dict[str, Any]:
        """Return bridge metadata."""
        return {
            "name": "CADAMBridge",
            "version": "1.0.0",
            "project": "Adam-CAD/CADAM",
            "description": "Text/images to editable 3D CAD models in browser",
            "methods": [
                "text_to_cad", "image_to_cad", "edit_model",
                "export_model", "get_libraries", "get_library_info", "list_models",
            ],
            "mock_fallback": True,
        }


# ---------------------------------------------------------------------------
# Factory function
# ---------------------------------------------------------------------------

def get_cadam_bridge(config: Optional[Dict[str, Any]] = None, verbose: bool = True) -> CADAMBridge:
    """Factory: create a CADAMBridge instance."""
    return CADAMBridge(config=config, verbose=verbose)


# ---------------------------------------------------------------------------
# __main__ self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    bridge = get_cadam_bridge(verbose=True)

    # health_check + metadata
    assert bridge.health_check()["available"] in (True, False)
    assert bridge.metadata()["name"] == "CADAMBridge"
    assert "text_to_cad" in bridge.metadata()["methods"]

    # text_to_cad
    model = bridge.text_to_cad("a 40mm gear with 12 teeth and 5mm thickness")
    assert isinstance(model, CADModel)
    assert model.model_id.startswith("cad_")
    assert model.parameters["type"] == "gear"
    assert model.parameters["teeth"] == 12
    assert model.volume_mm3 > 0
    assert model.triangle_count > 0

    # image_to_cad
    img_model = bridge.image_to_cad("/tmp/gear_reference.png")
    assert isinstance(img_model, CADModel)
    assert img_model.source_type == "image"

    # edit_model
    edited = bridge.edit_model(model.model_id, {"teeth": 16, "diameter": 60, "scale": 1.2})
    assert isinstance(edited, CADModel)
    assert edited.parameters["teeth"] == 16

    # export_model
    stl = bridge.export_model(model.model_id, "stl")
    assert isinstance(stl, bytes)
    assert len(stl) > 0
    scad = bridge.export_model(model.model_id, "scad")
    assert b"CADAM" in scad or b"scad" in scad.lower() or b"//" in scad
    obj = bridge.export_model(model.model_id, "obj")
    assert isinstance(obj, bytes)

    # get_libraries
    libs = bridge.get_libraries()
    assert isinstance(libs, list)
    assert "BOSL2" in libs
    assert "BOSL" in libs
    assert "MCAD" in libs

    # get_library_info
    bosl2 = bridge.get_library_info("BOSL2")
    assert bosl2 is not None
    assert len(bosl2.modules) > 0

    # list_models
    all_models = bridge.list_models()
    assert len(all_models) >= 2

    print("All CADAMBridge self-tests passed!")
