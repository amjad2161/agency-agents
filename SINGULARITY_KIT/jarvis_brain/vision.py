"""See the screen via Ollama vision model (llama3.2-vision)."""
from __future__ import annotations
import base64, io, json, urllib.request
from pathlib import Path


class Vision:
    def __init__(self, action, ollama_url="http://localhost:11434"):
        self.action = action
        self.ollama = ollama_url
        self.model = "llama3.2-vision"
        self._available = self._check()

    def _check(self):
        try:
            req = urllib.request.Request(self.ollama + "/api/tags")
            with urllib.request.urlopen(req, timeout=2) as r:
                data = json.loads(r.read())
            for m in data.get("models", []):
                if "vision" in m.get("name", "").lower() or "llava" in m.get("name", "").lower():
                    self.model = m["name"]
                    return True
        except Exception:
            pass
        return False

    def see_screen(self, prompt="Describe what is visible on the screen in detail."):
        """Capture screen and analyze."""
        if not self._available:
            return "Vision model not available. Pull one: 'ollama pull llama3.2-vision' (or llava)."
        img = self.action.screenshot()
        if not img:
            return "Could not capture screen."
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        try:
            payload = json.dumps({
                "model": self.model,
                "prompt": prompt,
                "images": [b64],
                "stream": False,
            }).encode("utf-8")
            req = urllib.request.Request(self.ollama + "/api/generate", data=payload,
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=120) as r:
                data = json.loads(r.read())
            return data.get("response", "(no response)")
        except Exception as e:
            return f"vision err: {e}"

    def find_element(self, what):
        """Locate UI element by description."""
        return self.see_screen(f"Where is {what}? Reply with coordinates (x, y) if visible, "
                                "or 'not found'. Be precise.")
