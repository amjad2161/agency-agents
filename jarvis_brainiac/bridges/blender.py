from __future__ import annotations
import sys
from pathlib import Path
from .base import Bridge

# Insert runtime directory into sys.path to resolve agency imports
_runtime_path = str(Path(__file__).resolve().parents[2] / "runtime")
if _runtime_path not in sys.path:
    sys.path.insert(0, _runtime_path)

from agency.bridges.blender import BlenderBridge as RealBlenderBridge


class BlenderBridge(Bridge):
    name = "blender"
    capabilities = ["create-mesh", "render-scene", "export-gltf"]

    def __init__(self, **config):
        self.config = config
        self._real_bridge = RealBlenderBridge(blender_executable=config.get("blender_executable"))
        self._connected = False

    def connect(self) -> bool:
        self._connected = True
        return True

    def invoke(self, action: str, **kw) -> dict:
        if not self._connected:
            self.connect()
        if action not in self.capabilities:
            return {"ok": False, "error": f"unknown action: {action}",
                    "available": self.capabilities}
        try:
            if action == "create-mesh":
                res = self._real_bridge.create_primitive(
                    type=kw.get("type", "CUBE"),
                    location=kw.get("location", (0.0, 0.0, 0.0)),
                    scale=kw.get("scale", (1.0, 1.0, 1.0)),
                    output_blend=kw.get("output_blend")
                )
            elif action == "render-scene":
                res = self._real_bridge.render_scene(
                    blend_file=kw["blend_file"],
                    output_path=kw["output_path"],
                    frame=kw.get("frame", 1),
                    resolution=kw.get("resolution", (1920, 1080))
                )
            elif action == "export-gltf":
                res = self._real_bridge.export_gltf(
                    blend_file=kw["blend_file"],
                    output_path=kw["output_path"]
                )
            else:
                return {"ok": False, "error": f"unsupported action: {action}"}
            
            if isinstance(res, dict):
                return {**res, "bridge": self.name, "action": action}
            return {"ok": True, "result": res, "bridge": self.name, "action": action}
        except Exception as e:
            return {"ok": False, "error": str(e), "bridge": self.name, "action": action}

    def disconnect(self) -> None:
        self._connected = False

