from __future__ import annotations
import sys
from pathlib import Path
from .base import Bridge

# Insert runtime directory into sys.path to resolve agency imports
_runtime_path = str(Path(__file__).resolve().parents[2] / "runtime")
if _runtime_path not in sys.path:
    sys.path.insert(0, _runtime_path)


class ScifiUiBridge(Bridge):
    name = "scifi_ui"
    capabilities = ["render-hud", "holo-text", "particle-field"]

    def __init__(self, **config):
        self.config = config
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
            if action == "render-hud":
                hud_path = Path(_runtime_path) / "agency" / "static" / "spatial.html"
                res = {
                    "ok": True,
                    "url": "http://127.0.0.1:8765/spatial",
                    "file_path": str(hud_path.resolve()),
                    "status": "ready"
                }
            elif action == "holo-text":
                text = kw.get("text", "JARVIS ACTIVE")
                color = kw.get("color", "#00ffff")
                res = {
                    "ok": True,
                    "styled_text": f"<span style='color: {color}; text-shadow: 0 0 10px {color}; font-family: monospace;'>{text}</span>",
                    "style": {
                        "color": color,
                        "text-shadow": f"0 0 10px {color}",
                        "font-family": "monospace"
                    }
                }
            elif action == "particle-field":
                density = kw.get("density", 100)
                speed = kw.get("speed", 1.0)
                res = {
                    "ok": True,
                    "particles_count": density,
                    "speed_multiplier": speed,
                    "canvas_script": "/* particle field draw logic */"
                }
            else:
                return {"ok": False, "error": f"unsupported action: {action}"}
            
            if isinstance(res, dict):
                return {**res, "bridge": self.name, "action": action}
            return {"ok": True, "result": res, "bridge": self.name, "action": action}
        except Exception as e:
            return {"ok": False, "error": str(e), "bridge": self.name, "action": action}

    def disconnect(self) -> None:
        self._connected = False

