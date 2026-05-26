from __future__ import annotations
import sys
from pathlib import Path
from .base import Bridge

# Insert runtime directory into sys.path to resolve agency imports
_runtime_path = str(Path(__file__).resolve().parents[2] / "runtime")
if _runtime_path not in sys.path:
    sys.path.insert(0, _runtime_path)

from agency.expert_personas import PersonaFactory


class PersonasBridge(Bridge):
    name = "personas"
    capabilities = ["persona-route", "consult-domain", "memory"]

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
            if action == "persona-route":
                persona = PersonaFactory.route_query(kw["query"])
                res = {
                    "ok": True,
                    "persona_type": persona.name,
                    "title": persona.title,
                    "domains": persona.expertise_domains
                }
            elif action == "consult-domain":
                query = kw["query"]
                persona_type = kw.get("persona_type")
                if persona_type:
                    persona = PersonaFactory.create(persona_type)
                else:
                    persona = PersonaFactory.route_query(query)
                
                context = kw.get("context", {})
                analysis_res = persona.analyze(query, context=context)
                res = {
                    "ok": True,
                    "persona_name": persona.name,
                    "persona_title": persona.title,
                    "analysis": analysis_res
                }
            elif action == "memory":
                persona_type = kw.get("persona_type", "advisor")
                persona = PersonaFactory.create(persona_type)
                res = {
                    "ok": True,
                    "persona_type": persona_type,
                    "memory_size": len(persona.expertise_domains),
                    "disclaimer": persona.get_disclaimer()
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

