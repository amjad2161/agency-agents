from __future__ import annotations
import sys
from pathlib import Path
from .base import Bridge

# Insert runtime directory into sys.path to resolve agency imports
_runtime_path = str(Path(__file__).resolve().parents[2] / "runtime")
if _runtime_path not in sys.path:
    sys.path.insert(0, _runtime_path)

from agency.bridges.cadam import CadamBridge as RealCadamBridge


class CadamBridge(Bridge):
    name = "cadam"
    capabilities = ["open-part", "tool-path", "simulate"]

    def __init__(self, **config):
        self.config = config
        self._real_bridge = RealCadamBridge()
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
            if action == "open-part":
                res = self._real_bridge.parse_dxf(filepath=kw["filepath"])
            elif action == "tool-path":
                res = self._real_bridge.extract_dimensions(filepath=kw["filepath"])
            elif action == "simulate":
                res = self._real_bridge.dxf_to_svg(
                    input_dxf=kw["input_dxf"],
                    output_svg=kw["output_svg"]
                )
            else:
                return {"ok": False, "error": f"unsupported action: {action}"}
            
            if isinstance(res, dict):
                return {**res, "bridge": self.name, "action": action}
            if isinstance(res, list):
                return {"ok": True, "result": res, "bridge": self.name, "action": action}
            return {"ok": True, "path": str(res), "bridge": self.name, "action": action}
        except Exception as e:
            return {"ok": False, "error": str(e), "bridge": self.name, "action": action}

    def disconnect(self) -> None:
        self._connected = False

