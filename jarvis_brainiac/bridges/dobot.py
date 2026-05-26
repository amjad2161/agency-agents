from __future__ import annotations
import sys
from pathlib import Path
from .base import Bridge

# Insert runtime directory into sys.path to resolve agency imports
_runtime_path = str(Path(__file__).resolve().parents[2] / "runtime")
if _runtime_path not in sys.path:
    sys.path.insert(0, _runtime_path)

from agency.bridges.dobot import DobotBridge as RealDobotBridge


class DobotBridge(Bridge):
    name = "dobot"
    capabilities = ["home", "move-xyz", "gripper"]

    def __init__(self, **config):
        self.config = config
        self._real_bridge = RealDobotBridge()
        self._connected = False

    def connect(self) -> bool:
        port = self.config.get("port", "COM3")
        self._real_bridge.connect(port=port)
        self._connected = True
        return True

    def invoke(self, action: str, **kw) -> dict:
        if not self._connected:
            self.connect()
        if action not in self.capabilities:
            return {"ok": False, "error": f"unknown action: {action}",
                    "available": self.capabilities}
        try:
            if action == "home":
                res = self._real_bridge.home()
            elif action == "move-xyz":
                res = self._real_bridge.move_to(
                    x=kw["x"],
                    y=kw["y"],
                    z=kw["z"],
                    r=kw.get("r", 0.0),
                    mode=kw.get("mode", "MOVJ")
                )
            elif action == "gripper":
                is_open = kw.get("open", True)
                if isinstance(is_open, str):
                    is_open = (is_open.lower() in ("true", "open", "1"))
                if is_open:
                    res = self._real_bridge.gripper_open()
                else:
                    res = self._real_bridge.gripper_close()
            else:
                return {"ok": False, "error": f"unsupported action: {action}"}
            
            if isinstance(res, dict):
                return {**res, "bridge": self.name, "action": action}
            return {"ok": True, "result": res, "bridge": self.name, "action": action}
        except Exception as e:
            return {"ok": False, "error": str(e), "bridge": self.name, "action": action}

    def disconnect(self) -> None:
        self._real_bridge.disconnect()
        self._connected = False

