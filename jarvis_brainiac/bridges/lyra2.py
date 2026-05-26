from __future__ import annotations
import sys
from pathlib import Path
from .base import Bridge

# Insert runtime directory into sys.path to resolve agency imports
_runtime_path = str(Path(__file__).resolve().parents[2] / "runtime")
if _runtime_path not in sys.path:
    sys.path.insert(0, _runtime_path)

from agency.bridges.lyra2 import Lyra2Bridge as RealLyra2Bridge


class Lyra2Bridge(Bridge):
    name = "lyra2"
    capabilities = ["tts", "asr", "voice-clone"]

    def __init__(self, **config):
        self.config = config
        self._real_bridge = RealLyra2Bridge(riva_server=config.get("riva_server"))
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
            if action == "tts":
                res = self._real_bridge.synthesize(
                    text=kw["text"],
                    voice=kw.get("voice", "jarvis"),
                    language=kw.get("language", "he"),
                    sample_rate=kw.get("sample_rate", 22050)
                )
                import base64
                encoded = base64.b64encode(res).decode("utf-8")
                return {"ok": True, "audio_content": encoded, "format": "wav", "bridge": self.name, "action": action}
            elif action == "asr":
                audio_bytes = kw["audio_bytes"]
                if isinstance(audio_bytes, str):
                    import base64
                    audio_bytes = base64.b64decode(audio_bytes)
                res = self._real_bridge.transcribe(
                    audio_bytes=audio_bytes,
                    language=kw.get("language", "he")
                )
            elif action == "voice-clone":
                res = {
                    "ok": True,
                    "voice_profile": kw.get("voice_name", "custom_clone"),
                    "status": "cloned-mock",
                    "codec_info": self._real_bridge.get_codec_info()
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

