from __future__ import annotations
import sys
from pathlib import Path
from .base import Bridge

# Insert runtime directory into sys.path to resolve agency imports
_runtime_path = str(Path(__file__).resolve().parents[2] / "runtime")
if _runtime_path not in sys.path:
    sys.path.insert(0, _runtime_path)


class WorkingDemosBridge(Bridge):
    name = "working_demos"
    capabilities = ["run-demo", "list-demos", "record-output"]

    def __init__(self, **config):
        self.config = config
        self._connected = False

    def connect(self) -> bool:
        self._connected = True
        return True

    def _get_demos(self) -> list[Path]:
        demo_paths = [
            Path(_runtime_path) / "examples",
            Path(_runtime_path).parent / "examples"
        ]
        demos = []
        for dp in demo_paths:
            if dp.exists() and dp.is_dir():
                for f in dp.glob("*.py"):
                    demos.append(f)
        return demos

    def invoke(self, action: str, **kw) -> dict:
        if not self._connected:
            self.connect()
        if action not in self.capabilities:
            return {"ok": False, "error": f"unknown action: {action}",
                    "available": self.capabilities}
        try:
            if action == "list-demos":
                demos = self._get_demos()
                res = {
                    "ok": True,
                    "demos": [str(d.name) for d in demos],
                    "paths": [str(d.resolve()) for d in demos]
                }
            elif action == "run-demo":
                demo_name = kw.get("demo")
                if not demo_name:
                    return {"ok": False, "error": "No 'demo' script specified."}
                demos = self._get_demos()
                target_demo = next((d for d in demos if d.name == demo_name or d.stem == demo_name), None)
                if not target_demo:
                    return {"ok": False, "error": f"Demo {demo_name} not found."}
                
                res = {
                    "ok": True,
                    "demo": target_demo.name,
                    "run_command": f"python {target_demo.name}",
                    "status": "completed-simulated",
                    "stdout": f"[sim] Executed {target_demo.name} successfully."
                }
            elif action == "record-output":
                res = {
                    "ok": True,
                    "output_log": str(Path(_runtime_path) / "examples" / "demo_output.log")
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

