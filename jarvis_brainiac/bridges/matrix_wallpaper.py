from __future__ import annotations
import sys
from pathlib import Path
from .base import Bridge

# Insert runtime directory into sys.path to resolve agency imports
_runtime_path = str(Path(__file__).resolve().parents[2] / "runtime")
if _runtime_path not in sys.path:
    sys.path.insert(0, _runtime_path)

from agency.bridges.matrix_wallpaper import MatrixWallpaperBridge as RealMatrixWallpaperBridge


class MatrixWallpaperBridge(Bridge):
    name = "matrix_wallpaper"
    capabilities = ["start", "stop", "set-density"]

    def __init__(self, **config):
        self.config = config
        self._real_bridge = RealMatrixWallpaperBridge(assets_dir=config.get("assets_dir"))
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
            if action == "start":
                res = self._real_bridge.start_screensaver(duration_seconds=kw.get("duration"))
            elif action == "stop":
                res = self._real_bridge.stop_screensaver()
            elif action == "set-density":
                density = kw.get("density", 0.8)
                if isinstance(density, str):
                    density = float(density)
                self._real_bridge.generate_html(density=density)
                status = self._real_bridge.get_status()
                restarted = False
                if status.get("running"):
                    self._real_bridge.stop_screensaver()
                    self._real_bridge.start_screensaver()
                    restarted = True
                res = {"ok": True, "density": density, "restarted": restarted}
            else:
                return {"ok": False, "error": f"unsupported action: {action}"}
            
            if isinstance(res, dict):
                return {**res, "bridge": self.name, "action": action}
            return {"ok": True, "result": res, "bridge": self.name, "action": action}
        except Exception as e:
            return {"ok": False, "error": str(e), "bridge": self.name, "action": action}

    def disconnect(self) -> None:
        self._real_bridge.stop_screensaver()
        self._connected = False

