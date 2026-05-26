"""Multi-step workflow executor: research -> plan -> act -> verify."""
from __future__ import annotations
import time


class Workflow:
    def __init__(self, action, vision, telemetry, on_step):
        self.action = action
        self.vision = vision
        self.telemetry = telemetry
        self.on_step = on_step

    def execute_plan(self, steps: list[dict]):
        """Execute a list of steps. Each step: {action, args}."""
        results = []
        for i, step in enumerate(steps):
            self.on_step(i, step)
            r = self._run_step(step)
            results.append(r)
            time.sleep(0.3)
        return results

    def _run_step(self, step):
        a = step.get("action", "")
        args = step.get("args", {})
        try:
            if a == "screenshot": return self.action.screenshot(args.get("path"))
            if a == "see": return self.vision.see_screen(args.get("prompt", "Describe."))
            if a == "click": return self.action.click(args.get("x"), args.get("y"))
            if a == "type": return self.action.type_text(args.get("text", ""))
            if a == "key": return self.action.press_key(args.get("key"))
            if a == "hotkey": return self.action.hotkey(*args.get("keys", []))
            if a == "open": return self.action.open_app(args.get("target"))
            if a == "url": return self.action.open_url(args.get("url"))
            if a == "wait": time.sleep(args.get("s", 1)); return "waited"
            if a == "stats": return self.telemetry.snapshot()
            if a == "focus": return self.action.focus_window(args.get("title", ""))
            return f"unknown action: {a}"
        except Exception as e:
            return f"err: {e}"
