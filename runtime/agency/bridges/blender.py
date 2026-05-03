"""Blender MCP bridge.

Drives Blender headlessly via ``blender --background --python <script>``.
The Blender executable is auto-detected from common install paths but can
be overridden by passing ``blender_executable=`` to :class:`BlenderBridge`
or by setting the ``BLENDER_EXECUTABLE`` environment variable.

If no Blender binary can be located, every method returns a structured
"mock" response containing the script that *would* have been executed and
human-readable installation instructions, so downstream agents always see
a deterministic shape.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from ..logging import get_logger

log = get_logger()


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

_COMMON_BLENDER_PATHS: Tuple[str, ...] = (
    # Windows
    r"C:\Program Files\Blender Foundation\Blender 4.2\blender.exe",
    r"C:\Program Files\Blender Foundation\Blender 4.1\blender.exe",
    r"C:\Program Files\Blender Foundation\Blender 4.0\blender.exe",
    r"C:\Program Files\Blender Foundation\Blender 3.6\blender.exe",
    # macOS
    "/Applications/Blender.app/Contents/MacOS/Blender",
    # Linux / common package paths
    "/usr/bin/blender",
    "/usr/local/bin/blender",
    "/snap/bin/blender",
    "/opt/blender/blender",
)

_VALID_PRIMITIVES = {
    "CUBE",
    "SPHERE",
    "CYLINDER",
    "CONE",
    "PLANE",
    "TORUS",
    "MONKEY",
}


def _detect_blender_executable() -> Optional[str]:
    """Return the path to a Blender executable, or ``None`` if not found."""
    env = os.environ.get("BLENDER_EXECUTABLE")
    if env and Path(env).exists():
        return env

    found = shutil.which("blender")
    if found:
        return found

    for path in _COMMON_BLENDER_PATHS:
        if Path(path).exists():
            return path
    return None


# ---------------------------------------------------------------------------
# Bridge
# ---------------------------------------------------------------------------

@dataclass
class _RunResult:
    returncode: int
    stdout: str
    stderr: str


class BlenderBridge:
    """Headless Blender driver."""

    def __init__(self, blender_executable: Optional[str] = None) -> None:
        self._explicit_executable = blender_executable
        self._executable: Optional[str] = (
            blender_executable
            if blender_executable and Path(blender_executable).exists()
            else _detect_blender_executable()
        )

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    @property
    def hardware_available(self) -> bool:
        """Mirror of :attr:`blender_available` for cross-bridge consistency."""
        return self.blender_available

    @property
    def blender_available(self) -> bool:
        return bool(self._executable) and Path(self._executable).exists()

    @property
    def blender_executable(self) -> Optional[str]:
        return self._executable

    def status(self) -> Dict[str, Any]:
        return {
            "blender_available": self.blender_available,
            "blender_executable": self._executable,
            "explicit_executable": self._explicit_executable,
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def render_scene(
        self,
        blend_file: str,
        output_path: str,
        frame: int = 1,
        resolution: Tuple[int, int] = (1920, 1080),
    ) -> Dict[str, Any]:
        """Render a single frame of ``blend_file`` to ``output_path``."""
        out_path = Path(output_path)
        script = textwrap.dedent(
            f"""
            import bpy
            scene = bpy.context.scene
            scene.render.resolution_x = {int(resolution[0])}
            scene.render.resolution_y = {int(resolution[1])}
            scene.render.image_settings.file_format = 'PNG'
            scene.frame_set({int(frame)})
            scene.render.filepath = {str(out_path)!r}
            bpy.ops.render.render(write_still=True)
            """
        ).strip()

        if not self.blender_available:
            return self._mock_response(
                action="render_scene",
                script=script,
                target=str(out_path),
            )

        result = self._run_with_blend(blend_file, script)
        ok = result.returncode == 0 and out_path.exists()
        return {
            "ok": ok,
            "output_path": str(out_path),
            "frame": int(frame),
            "resolution": [int(resolution[0]), int(resolution[1])],
            "stdout_tail": _tail(result.stdout),
            "stderr_tail": _tail(result.stderr),
        }

    def run_script(self, blend_file: str, python_script: str) -> Dict[str, Any]:
        """Run an arbitrary ``python_script`` inside Blender against ``blend_file``."""
        if not self.blender_available:
            return self._mock_response(
                action="run_script",
                script=python_script,
                target=blend_file,
            )

        result = self._run_with_blend(blend_file, python_script)
        return {
            "ok": result.returncode == 0,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }

    def create_primitive(
        self,
        type: str = "CUBE",
        location: Tuple[float, float, float] = (0.0, 0.0, 0.0),
        scale: Tuple[float, float, float] = (1.0, 1.0, 1.0),
        output_blend: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a primitive mesh in a fresh scene and (optionally) save it."""
        primitive = type.upper()
        if primitive not in _VALID_PRIMITIVES:
            raise ValueError(
                f"unknown primitive {type!r} — expected one of {sorted(_VALID_PRIMITIVES)}"
            )

        op_map = {
            "CUBE": "primitive_cube_add",
            "SPHERE": "primitive_uv_sphere_add",
            "CYLINDER": "primitive_cylinder_add",
            "CONE": "primitive_cone_add",
            "PLANE": "primitive_plane_add",
            "TORUS": "primitive_torus_add",
            "MONKEY": "primitive_monkey_add",
        }
        op = op_map[primitive]
        save_block = (
            f"bpy.ops.wm.save_as_mainfile(filepath={str(output_blend)!r})"
            if output_blend
            else "# no save requested"
        )
        script = textwrap.dedent(
            f"""
            import bpy
            for obj in list(bpy.data.objects):
                bpy.data.objects.remove(obj, do_unlink=True)
            bpy.ops.mesh.{op}(location=({float(location[0])},{float(location[1])},{float(location[2])}))
            obj = bpy.context.active_object
            obj.scale = ({float(scale[0])},{float(scale[1])},{float(scale[2])})
            {save_block}
            """
        ).strip()

        if not self.blender_available:
            return self._mock_response(
                action="create_primitive",
                script=script,
                target=output_blend or "<unsaved>",
                extra={
                    "type": primitive,
                    "location": list(location),
                    "scale": list(scale),
                },
            )

        result = self._run_headless(script)
        return {
            "ok": result.returncode == 0,
            "type": primitive,
            "output_blend": output_blend,
            "stdout_tail": _tail(result.stdout),
            "stderr_tail": _tail(result.stderr),
        }

    def export_gltf(self, blend_file: str, output_path: str) -> Dict[str, Any]:
        """Export ``blend_file`` to GLTF/GLB at ``output_path``."""
        out_path = Path(output_path)
        script = textwrap.dedent(
            f"""
            import bpy
            bpy.ops.export_scene.gltf(filepath={str(out_path)!r}, export_format='GLB')
            """
        ).strip()

        if not self.blender_available:
            return self._mock_response(
                action="export_gltf",
                script=script,
                target=str(out_path),
            )

        result = self._run_with_blend(blend_file, script)
        return {
            "ok": result.returncode == 0 and out_path.exists(),
            "output_path": str(out_path),
            "stdout_tail": _tail(result.stdout),
            "stderr_tail": _tail(result.stderr),
        }

    def get_scene_info(self, blend_file: str) -> Dict[str, Any]:
        """Return objects, materials, and frame range for ``blend_file``."""
        marker = "__SCENE_INFO_JSON__"
        script = textwrap.dedent(
            f"""
            import bpy, json
            scene = bpy.context.scene
            info = {{
                "objects": [o.name for o in bpy.data.objects],
                "materials": [m.name for m in bpy.data.materials],
                "frame_start": int(scene.frame_start),
                "frame_end": int(scene.frame_end),
                "frame_current": int(scene.frame_current),
            }}
            print({marker!r} + json.dumps(info))
            """
        ).strip()

        if not self.blender_available:
            return self._mock_response(
                action="get_scene_info",
                script=script,
                target=blend_file,
                extra={
                    "objects": [],
                    "materials": [],
                    "frame_start": 1,
                    "frame_end": 250,
                    "frame_current": 1,
                },
            )

        result = self._run_with_blend(blend_file, script)
        info = _parse_marker_json(result.stdout, marker) or {}
        return {
            "ok": result.returncode == 0,
            "objects": info.get("objects", []),
            "materials": info.get("materials", []),
            "frames": {
                "start": info.get("frame_start", 1),
                "end": info.get("frame_end", 250),
                "current": info.get("frame_current", 1),
            },
            "stderr_tail": _tail(result.stderr),
        }

    # ------------------------------------------------------------------
    # Generic dispatch
    # ------------------------------------------------------------------

    def invoke(self, action: str, **kwargs: Any) -> Any:
        registry: Dict[str, Callable[..., Any]] = {
            "render_scene": self.render_scene,
            "run_script": self.run_script,
            "create_primitive": self.create_primitive,
            "export_gltf": self.export_gltf,
            "get_scene_info": self.get_scene_info,
            "status": self.status,
        }
        if action not in registry:
            raise ValueError(f"unknown Blender action: {action!r}")
        return registry[action](**kwargs)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _run_with_blend(self, blend_file: str, script: str) -> _RunResult:
        return self._run(["-b", str(blend_file)], script)

    def _run_headless(self, script: str) -> _RunResult:
        return self._run(["-b"], script)

    def _run(self, prefix: Sequence[str], script: str) -> _RunResult:
        assert self._executable is not None
        script_path = Path(_write_temp_script(script))
        try:
            cmd = [self._executable, *prefix, "--python", str(script_path)]
            log.debug("BlenderBridge: %s", " ".join(cmd))
            proc = subprocess.run(  # noqa: S603 — argv is fully controlled
                cmd,
                capture_output=True,
                text=True,
                check=False,
            )
            return _RunResult(
                returncode=proc.returncode,
                stdout=proc.stdout or "",
                stderr=proc.stderr or "",
            )
        finally:
            try:
                script_path.unlink()
            except OSError:
                pass

    def _mock_response(
        self,
        *,
        action: str,
        script: str,
        target: str,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        body: Dict[str, Any] = {
            "ok": False,
            "mock": True,
            "action": action,
            "target": target,
            "script_preview": _tail(script, lines=20),
            "instructions": (
                "Blender executable not found. Install Blender from "
                "https://www.blender.org/download/ or set the "
                "BLENDER_EXECUTABLE environment variable to its path."
            ),
        }
        if extra:
            body.update(extra)
        return body


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_temp_script(script: str) -> str:
    import tempfile

    fd, path = tempfile.mkstemp(prefix="blender_bridge_", suffix=".py")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fp:
            fp.write(script)
    except Exception:
        os.close(fd)
        raise
    return path


def _tail(text: str, *, lines: int = 10) -> str:
    if not text:
        return ""
    parts = text.splitlines()
    return "\n".join(parts[-lines:])


def _parse_marker_json(stdout: str, marker: str) -> Optional[Dict[str, Any]]:
    for line in stdout.splitlines():
        idx = line.find(marker)
        if idx >= 0:
            try:
                return json.loads(line[idx + len(marker):])
            except json.JSONDecodeError:
                return None
    return None


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def get_blender_bridge(blender_executable: Optional[str] = None) -> BlenderBridge:
    return BlenderBridge(blender_executable=blender_executable)
