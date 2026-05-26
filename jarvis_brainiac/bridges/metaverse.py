from __future__ import annotations
import sys
from pathlib import Path
from .base import Bridge

# Insert runtime directory into sys.path to resolve agency imports
_runtime_path = str(Path(__file__).resolve().parents[2] / "runtime")
if _runtime_path not in sys.path:
    sys.path.insert(0, _runtime_path)

from agency.bridges.metaverse import MetaverseBridge as RealMetaverseBridge


class MetaverseBridge(Bridge):
    name = "metaverse"
    capabilities = ["enter-world", "spawn-object", "record"]

    def __init__(self, **config):
        self.config = config
        self._real_bridge = RealMetaverseBridge(assets_dir=config.get("assets_dir"))
        self._connected = False
        self._last_world_id = None

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
            if action == "enter-world":
                res = self._real_bridge.create_world(
                    theme=kw.get("theme", "cyberpunk"),
                    size=kw.get("size", "medium")
                )
                if res.get("ok"):
                    self._last_world_id = res.get("world_id")
            elif action == "spawn-object":
                world_id = kw.get("world_id") or self._last_world_id
                if not world_id:
                    return {"ok": False, "error": "No active world_id. Call enter-world first."}
                res = self._real_bridge.add_object(
                    world_id=world_id,
                    asset_type=kw["asset_type"],
                    position=kw["position"],
                    properties=kw.get("properties")
                )
            elif action == "record":
                world_id = kw.get("world_id") or self._last_world_id
                if not world_id:
                    return {"ok": False, "error": "No active world_id to record."}
                res = {
                    "ok": True,
                    "world_id": world_id,
                    "video_path": str(self._real_bridge._assets_dir / "recording_sim.mp4"),
                    "status": "recording-saved"
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

