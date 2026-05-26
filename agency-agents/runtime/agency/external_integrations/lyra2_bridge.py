"""
JARVIS BRAINIAC - Lyra 2.0 Integration Bridge
=============================================

Bridge adapter for NVIDIA Lyra 2.0 — a generative model that converts a single
image into a fully explorable 3D world. Supports multi-image world generation,
scene navigation, and GLB export.

Repository: https://github.com/nv-tlabs/lyra
Hugging Face: https://huggingface.co/nvidia/Lyra-2.0
Features:
    - Single image to 3D scene conversion
    - Multi-image world generation and fusion
    - First-person scene navigation
    - GLB/GLTF scene export

Usage:
    bridge = Lyra2Bridge()
    scene = bridge.image_to_3d("/path/to/image.jpg")
    world = bridge.generate_world(["/path/to/img1.jpg", "/path/to/img2.jpg"])
    view = bridge.navigate_scene(scene.scene_id, (1.5, 0.0, 2.0))
    glb_bytes = bridge.export_glb(scene.scene_id)
"""

from __future__ import annotations

import base64
import io
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Availability flag
# ---------------------------------------------------------------------------
_LYRA_AVAILABLE: bool = False
_LYRA_VERSION: str = "unknown"

try:
    import lyra
    from lyra.pipeline import LyraPipeline
    from lyra.scene import SceneGenerator, WorldGenerator
    from lyra.navigation import SceneNavigator
    from lyra.export import GLBExporter
    _LYRA_AVAILABLE = True
    _LYRA_VERSION = getattr(lyra, "__version__", "unknown")
    logger.info("Lyra 2.0 %s loaded successfully.", _LYRA_VERSION)
except Exception as _import_exc:
    logger.warning(
        "Lyra 2.0 not installed or failed to import (%s). "
        "Falling back to mock implementations.", _import_exc,
    )

# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class CameraPose:
    """Camera pose in 3D space."""
    position: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    fov: float = 75.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "position": list(self.position),
            "rotation": list(self.rotation),
            "fov": self.fov,
        }


@dataclass
class MeshInfo:
    """Metadata for a 3D mesh in a scene."""
    mesh_id: str
    name: str
    vertex_count: int = 0
    face_count: int = 0
    bounds: Dict[str, float] = field(default_factory=dict)
    material: str = "default"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mesh_id": self.mesh_id, "name": self.name,
            "vertex_count": self.vertex_count, "face_count": self.face_count,
            "bounds": self.bounds, "material": self.material,
        }


@dataclass
class Scene3D:
    """A generated 3D scene from a single image."""
    scene_id: str
    source_image: str
    meshes: List[MeshInfo] = field(default_factory=list)
    camera: CameraPose = field(default_factory=CameraPose)
    dimensions: Dict[str, float] = field(default_factory=dict)
    generation_time_ms: int = 0
    scene_format: str = "lyra_v2"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scene_id": self.scene_id, "source_image": self.source_image,
            "meshes": [m.to_dict() for m in self.meshes],
            "camera": self.camera.to_dict(),
            "dimensions": self.dimensions,
            "generation_time_ms": self.generation_time_ms,
            "scene_format": self.scene_format,
            "metadata": self.metadata,
        }


@dataclass
class World3D:
    """A multi-image fused 3D world."""
    world_id: str
    source_images: List[str] = field(default_factory=list)
    scenes: List[Scene3D] = field(default_factory=list)
    world_bounds: Dict[str, float] = field(default_factory=dict)
    fusion_quality: float = 0.0
    generation_time_ms: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "world_id": self.world_id,
            "source_images": self.source_images,
            "scenes": [s.to_dict() for s in self.scenes],
            "world_bounds": self.world_bounds,
            "fusion_quality": self.fusion_quality,
            "generation_time_ms": self.generation_time_ms,
            "metadata": self.metadata,
        }


@dataclass
class View:
    """A rendered view from a specific position in a 3D scene."""
    scene_id: str
    position: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    rotation: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    image_data: Optional[bytes] = None
    depth_map: Optional[bytes] = None
    fov: float = 75.0
    render_time_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scene_id": self.scene_id,
            "position": list(self.position),
            "rotation": list(self.rotation),
            "image_data_size": len(self.image_data) if self.image_data else 0,
            "depth_map_size": len(self.depth_map) if self.depth_map else 0,
            "fov": self.fov, "render_time_ms": self.render_time_ms,
        }


# ---------------------------------------------------------------------------
# Mock implementations
# ---------------------------------------------------------------------------

class _MockSceneGenerator:
    """Mock Lyra 2.0 scene generator with realistic outputs."""

    def generate(self, image_path: str) -> Scene3D:
        logger.info("[MOCK] Generating 3D scene from: %s", image_path)
        scene_id = f"lyra_scene_{uuid.uuid4().hex[:12]}"
        t0 = time.monotonic()

        # Simulate realistic scene composition based on image filename
        fname = Path(image_path).stem.lower()
        meshes: List[MeshInfo] = []

        if "room" in fname or "interior" in fname:
            meshes = [
                MeshInfo("m1", "floor", 1024, 512, {"min_x": -5, "max_x": 5, "min_y": 0, "max_y": 0.1, "min_z": -5, "max_z": 5}, "wood_floor"),
                MeshInfo("m2", "back_wall", 512, 256, {"min_x": -5, "max_x": 5, "min_y": 0, "max_y": 3, "min_z": -5, "max_z": -4.9}, "plaster"),
                MeshInfo("m3", "left_wall", 512, 256, {"min_x": -5, "max_x": -4.9, "min_y": 0, "max_y": 3, "min_z": -5, "max_z": 5}, "plaster"),
                MeshInfo("m4", "ceiling", 512, 256, {"min_x": -5, "max_x": 5, "min_y": 3, "max_y": 3.1, "min_z": -5, "max_z": 5}, "white_paint"),
                MeshInfo("m5", "furniture_sofa", 2048, 1024, {"min_x": -2, "max_x": 2, "min_y": 0, "max_y": 1, "min_z": -3, "max_z": -1}, "fabric_gray"),
            ]
        elif "street" in fname or "outdoor" in fname:
            meshes = [
                MeshInfo("m1", "road_surface", 2048, 1024, {"min_x": -10, "max_x": 10, "min_y": 0, "max_y": 0.05, "min_z": -10, "max_z": 10}, "asphalt"),
                MeshInfo("m2", "sidewalk_left", 1024, 512, {"min_x": -12, "max_x": -10, "min_y": 0.15, "max_y": 0.25, "min_z": -10, "max_z": 10}, "concrete"),
                MeshInfo("m3", "building_front", 4096, 2048, {"min_x": -8, "max_x": 8, "min_y": 0, "max_y": 15, "min_z": -15, "max_z": -14}, "brick"),
                MeshInfo("m4", "streetlight", 256, 128, {"min_x": -6, "max_x": -5.5, "min_y": 0, "max_y": 5, "min_z": -5, "max_z": -4.5}, "metal"),
            ]
        else:
            meshes = [
                MeshInfo("m1", "ground_plane", 1024, 512, {"min_x": -8, "max_x": 8, "min_y": 0, "max_y": 0.1, "min_z": -8, "max_z": 8}, "grass"),
                MeshInfo("m2", "main_structure", 4096, 2048, {"min_x": -3, "max_x": 3, "min_y": 0, "max_y": 6, "min_z": -3, "max_z": 3}, "concrete"),
                MeshInfo("m3", "detail_objects", 1536, 768, {"min_x": -2, "max_x": 2, "min_y": 0.5, "max_y": 2, "min_z": -2, "max_z": 2}, "mixed"),
            ]

        elapsed_ms = int((time.monotonic() - t0) * 1000) + 1200  # realistic ~1.2s+

        return Scene3D(
            scene_id=scene_id, source_image=image_path, meshes=meshes,
            camera=CameraPose(position=(0.0, 1.6, 2.0), rotation=(0.0, 0.0, 0.0), fov=75.0),
            dimensions={"width": 16.0, "height": 6.0, "depth": 16.0},
            generation_time_ms=elapsed_ms,
            scene_format="lyra_v2_mock",
            metadata={"mock": True, "quality": "high", "inference_steps": 50},
        )


class _MockWorldGenerator:
    """Mock world generator that fuses multiple scenes."""

    def generate(self, image_paths: List[str]) -> World3D:
        logger.info("[MOCK] Generating world from %d images", len(image_paths))
        world_id = f"lyra_world_{uuid.uuid4().hex[:12]}"
        t0 = time.monotonic()

        scene_gen = _MockSceneGenerator()
        scenes: List[Scene3D] = []
        for img in image_paths:
            scene = scene_gen.generate(img)
            scenes.append(scene)

        # Compute world bounds
        all_bounds = []
        for scene in scenes:
            d = scene.dimensions
            all_bounds.extend([d.get("width", 10), d.get("depth", 10)])

        world_size = max(all_bounds) * len(scenes) if all_bounds else 50.0
        elapsed_ms = int((time.monotonic() - t0) * 1000) + 3000

        return World3D(
            world_id=world_id, source_images=image_paths, scenes=scenes,
            world_bounds={
                "min_x": -world_size / 2, "max_x": world_size / 2,
                "min_y": 0.0, "max_y": 20.0,
                "min_z": -world_size / 2, "max_z": world_size / 2,
            },
            fusion_quality=0.87,
            generation_time_ms=elapsed_ms,
            metadata={"mock": True, "scene_count": len(scenes), "fusion_mode": "overlap_blend"},
        )


class _MockSceneNavigator:
    """Mock scene navigator that generates views from positions."""

    def navigate(self, scene_id: str, position: Tuple[float, ...]) -> View:
        logger.info("[MOCK] Navigating scene %s to position %s", scene_id, position)

        # Generate a small synthetic depth map as mock data
        depth_data = b"MOCK_DEPTH_" + f"{position[0]:.2f}_{position[1]:.2f}_{position[2]:.2f}".encode()

        # Generate a tiny synthetic JPEG header as mock image data
        mock_image = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00" + \
                     depth_data + b"\xff\xd9"

        return View(
            scene_id=scene_id,
            position=(position[0], position[1], position[2]),
            rotation=(0.0, 0.0, 0.0),
            image_data=mock_image,
            depth_map=depth_data,
            fov=75.0,
            render_time_ms=180,
        )


class _MockGLBExporter:
    """Mock GLB exporter that produces a minimal valid GLB byte stream."""

    # Minimal GLB magic header + version + length (mock)
    _GLB_HEADER = (
        b"\x67\x6c\x54\x46"  # magic "glTF"
        b"\x02\x00\x00\x00"  # version 2
    )

    def export(self, scene_id: str) -> bytes:
        logger.info("[MOCK] Exporting GLB for scene: %s", scene_id)

        scene_id_bytes = scene_id.encode("utf-8")
        # Mock: GLB header + a JSON chunk descriptor + placeholder scene JSON
        json_chunk = (
            b'{"asset":{"version":"2.0","generator":"lyra2-mock-bridge"},'
            b'"scene":0,"scenes":[{"nodes":[]}]}'
        )
        json_chunk_len = len(json_chunk).to_bytes(4, "little")
        json_chunk_type = b"\x4e\x4f\x53\x4a"  # JSON chunk type

        total_len = (12 + 8 + len(json_chunk)).to_bytes(4, "little")

        glb = self._GLB_HEADER + total_len + json_chunk_len + json_chunk_type + json_chunk
        logger.info("[MOCK] GLB exported: %d bytes", len(glb))
        return glb


# ---------------------------------------------------------------------------
# Main bridge class
# ---------------------------------------------------------------------------

class Lyra2Bridge:
    """Bridge adapter for NVIDIA Lyra 2.0 image-to-3D generation.

    Provides typed access to Lyra 2.0 capabilities with automatic mock
    fallback when the native library is not installed.

    Args:
        device: Compute device ("cuda", "cpu", or None for auto).
        model_id: Hugging Face model ID or local path.

    Example:
        bridge = Lyra2Bridge()
        scene = bridge.image_to_3d("photo.jpg")
        world = bridge.generate_world(["img1.jpg", "img2.jpg"])
        view = bridge.navigate_scene(scene.scene_id, (1.5, 1.6, 2.0))
        glb = bridge.export_glb(scene.scene_id)
    """

    def __init__(
        self,
        device: Optional[str] = None,
        model_id: str = "nvidia/Lyra-2.0",
    ) -> None:
        self.device = device or ("cuda" if _LYRA_AVAILABLE else "cpu")
        self.model_id = model_id
        self._scene_cache: Dict[str, Scene3D] = {}
        self._world_cache: Dict[str, World3D] = {}

        if _LYRA_AVAILABLE:
            self._scene_gen = SceneGenerator(device=self.device, model_id=model_id)
            self._world_gen = WorldGenerator(device=self.device, model_id=model_id)
            self._navigator = SceneNavigator(device=self.device)
            self._exporter = GLBExporter()
            logger.info("Lyra2Bridge initialized with native backend v%s.", _LYRA_VERSION)
        else:
            self._scene_gen = _MockSceneGenerator()
            self._world_gen = _MockWorldGenerator()
            self._navigator = _MockSceneNavigator()
            self._exporter = _MockGLBExporter()
            logger.info("Lyra2Bridge initialized with mock backend.")

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def image_to_3d(self, image_path: str) -> Scene3D:
        """Convert a single image into an explorable 3D scene.

        Args:
            image_path: Path to the source image (JPG, PNG, etc.).

        Returns:
            Scene3D with meshes, camera pose, dimensions, and metadata.

        Raises:
            FileNotFoundError: If the image file does not exist.
        """
        path = Path(image_path)
        if not path.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")

        scene = self._scene_gen.generate(str(path.resolve()))
        self._scene_cache[scene.scene_id] = scene
        logger.info("Generated scene %s from %s", scene.scene_id, image_path)
        return scene

    def generate_world(self, image_paths: List[str]) -> World3D:
        """Generate a fused 3D world from multiple images.

        Args:
            image_paths: List of image file paths to fuse into a world.

        Returns:
            World3D containing all sub-scenes with fused bounds.

        Raises:
            ValueError: If fewer than 1 image path is provided.
            FileNotFoundError: If any image file does not exist.
        """
        if not image_paths:
            raise ValueError("At least one image path is required.")

        resolved = []
        for p in image_paths:
            path = Path(p)
            if not path.exists():
                raise FileNotFoundError(f"Image not found: {p}")
            resolved.append(str(path.resolve()))

        world = self._world_gen.generate(resolved)
        self._world_cache[world.world_id] = world
        # Also cache individual scenes
        for scene in world.scenes:
            self._scene_cache[scene.scene_id] = scene
        logger.info("Generated world %s with %d scenes", world.world_id, len(world.scenes))
        return world

    def navigate_scene(
        self,
        scene_id: str,
        position: Tuple[float, float, float],
    ) -> View:
        """Navigate within a 3D scene to a specific position.

        Args:
            scene_id: ID of the scene to navigate.
            position: (x, y, z) world coordinates.

        Returns:
            View containing rendered image data and depth map.

        Raises:
            KeyError: If the scene_id is not found.
        """
        if scene_id not in self._scene_cache:
            raise KeyError(f"Scene '{scene_id}' not found. Generate it first with image_to_3d().")

        view = self._navigator.navigate(scene_id, position)
        logger.info("Navigated scene %s to %s (rendered in %d ms)",
                     scene_id, position, view.render_time_ms)
        return view

    def export_glb(self, scene_id: str) -> bytes:
        """Export a 3D scene as GLB binary format.

        Args:
            scene_id: ID of the scene to export.

        Returns:
            Raw GLB file bytes.

        Raises:
            KeyError: If the scene_id is not found.
        """
        if scene_id not in self._scene_cache:
            raise KeyError(f"Scene '{scene_id}' not found. Generate it first with image_to_3d().")

        glb_data = self._exporter.export(scene_id)
        logger.info("Exported GLB for scene %s: %d bytes", scene_id, len(glb_data))
        return glb_data

    # ------------------------------------------------------------------
    # Bridge contract
    # ------------------------------------------------------------------

    def health_check(self) -> Dict[str, Any]:
        """Return bridge health status.

        Returns:
            Dict with 'status', 'backend', 'version', device, and cache info.
        """
        return {
            "status": "healthy",
            "backend": "native" if _LYRA_AVAILABLE else "mock",
            "version": _LYRA_VERSION if _LYRA_AVAILABLE else "mock-1.0.0",
            "device": self.device,
            "model_id": self.model_id,
            "cached_scenes": len(self._scene_cache),
            "cached_worlds": len(self._world_cache),
            "native_available": _LYRA_AVAILABLE,
        }

    def metadata(self) -> Dict[str, Any]:
        """Return bridge metadata for JARVIS registry.

        Returns:
            Dict with bridge name, version, capabilities, and dependencies.
        """
        return {
            "name": "lyra2_bridge",
            "display_name": "Lyra 2.0 (NVIDIA) Image-to-3D",
            "version": "1.0.0",
            "description": (
                "Convert single images into fully explorable 3D worlds. "
                "Multi-image world generation, scene navigation, and GLB export."
            ),
            "author": "JARVIS Integration Team",
            "license": "MIT",
            "capabilities": [
                "image_to_3d",
                "multi_image_world_generation",
                "scene_navigation",
                "glb_export",
                "depth_map_generation",
            ],
            "dependencies": {
                "lyra": _LYRA_AVAILABLE,
                "torch": False,
                "python": ">=3.9",
            },
            "repository": "https://github.com/nv-tlabs/lyra",
            "huggingface": "https://huggingface.co/nvidia/Lyra-2.0",
            "mock_fallback": not _LYRA_AVAILABLE,
        }

    def clear_cache(self) -> None:
        """Clear internal scene and world caches."""
        self._scene_cache.clear()
        self._world_cache.clear()
        logger.info("Scene and world caches cleared.")

    def get_cached_scene(self, scene_id: str) -> Optional[Scene3D]:
        """Retrieve a cached scene by ID.

        Args:
            scene_id: Scene identifier.

        Returns:
            Scene3D if cached, None otherwise.
        """
        return self._scene_cache.get(scene_id)


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format="%(name)s | %(levelname)s | %(message)s")
    logger.info("=== Lyra 2.0 Bridge Self-Test ===")

    bridge = Lyra2Bridge()

    # Test health_check
    health = bridge.health_check()
    assert health["status"] == "healthy"
    assert "backend" in health
    logger.info("health_check: %s", health)

    # Test metadata
    meta = bridge.metadata()
    assert meta["name"] == "lyra2_bridge"
    assert "capabilities" in meta
    logger.info("metadata: %s", meta)

    # Test image_to_3d with a dummy file
    dummy_image = "/tmp/lyra_test_room.jpg"
    Path(dummy_image).write_bytes(b"\xff\xd8\xff\xe0\x00\x10JFIF\x00mock\xff\xd9")
    scene = bridge.image_to_3d(dummy_image)
    assert isinstance(scene, Scene3D)
    assert len(scene.scene_id) > 0
    assert len(scene.meshes) > 0
    assert scene.generation_time_ms > 0
    logger.info("image_to_3d: %s (%d meshes)", scene.scene_id, len(scene.meshes))

    # Test generate_world
    dummy_image2 = "/tmp/lyra_test_street.jpg"
    Path(dummy_image2).write_bytes(b"\xff\xd8\xff\xe0\x00\x10JFIF\x00street\xff\xd9")
    world = bridge.generate_world([dummy_image, dummy_image2])
    assert isinstance(world, World3D)
    assert len(world.scenes) == 2
    assert world.fusion_quality > 0
    logger.info("generate_world: %s (%d scenes)", world.world_id, len(world.scenes))

    # Test navigate_scene
    view = bridge.navigate_scene(scene.scene_id, (1.5, 1.6, 2.0))
    assert isinstance(view, View)
    assert view.image_data is not None
    assert len(view.image_data) > 0
    logger.info("navigate_scene: rendered %d bytes in %d ms",
                len(view.image_data), view.render_time_ms)

    # Test export_glb
    glb = bridge.export_glb(scene.scene_id)
    assert isinstance(glb, bytes)
    assert len(glb) > 0
    assert glb[:4] == b"\x67\x6c\x54\x46"  # GLB magic
    logger.info("export_glb: %d bytes", len(glb))

    # Test cache retrieval
    cached = bridge.get_cached_scene(scene.scene_id)
    assert cached is scene
    logger.info("Cache retrieval verified.")

    bridge.clear_cache()

    # Cleanup
    Path(dummy_image).unlink(missing_ok=True)
    Path(dummy_image2).unlink(missing_ok=True)

    logger.info("=== All Lyra 2.0 Bridge self-tests passed ===")
