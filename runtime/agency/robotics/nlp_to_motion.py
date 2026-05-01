"""Natural language to motion skill mapper."""

from __future__ import annotations

import re
from typing import Optional

from .motion_skills import MotionController


class NLPToMotion:
    """Parse natural language commands into motion skill calls."""

    # Pattern → (skill_name, param_key or None)
    PATTERNS: list[tuple[str, str, Optional[str]]] = [
        (r"walk\s+forward\s+(\d+\.?\d*)\s*(?:meter|m|metres?)?", "walk_forward", "distance"),
        (r"walk\s+back(?:ward)?s?\s+(\d+\.?\d*)\s*(?:meter|m|metres?)?", "walk_backward", "distance"),
        (r"turn\s+(?:left|right)?\s*(\d+\.?\d*)\s*(?:degree|deg)?s?", "turn", "angle"),
        (r"turn\s+(left|right)", "turn", "direction"),
        (r"sit\s*(?:down)?", "sit", None),
        (r"stand\s*(?:up)?", "stand", None),
        (r"wave", "wave", None),
        (r"grasp|pick\s+up\s+(.+)", "grasp", "object_name"),
        (r"release|drop", "release", None),
        (r"nod", "nod", None),
        (r"shake\s*(?:your\s*)?head", "shake_head", None),
        (r"raise\s+(?:your\s+)?(right|left)\s+arm", "raise_arm", "arm"),
        (r"lower\s+(?:your\s+)?(right|left)\s+arm", "lower_arm", "arm"),
        (r"raise\s+arm", "raise_arm", None),
        (r"lower\s+arm", "lower_arm", None),
        (r"walk\s+backward?s?", "walk_backward", None),
        (r"walk\s+forward", "walk_forward", None),
    ]

    def parse(self, text: str) -> Optional[dict]:
        """Return {skill, params} or None if no pattern matches."""
        text_lower = text.lower().strip()
        for pattern, skill, param_key in self.PATTERNS:
            m = re.search(pattern, text_lower)
            if m is None:
                continue
            params: dict = {}
            if param_key and m.lastindex and m.lastindex >= 1:
                raw = m.group(1).strip()
                if skill in ("walk_forward", "walk_backward"):
                    try:
                        params["distance"] = float(raw)
                    except ValueError:
                        params["distance"] = 1.0
                elif skill == "turn":
                    if param_key == "angle":
                        try:
                            params["angle_degrees"] = float(raw)
                        except ValueError:
                            params["angle_degrees"] = 90.0
                    elif param_key == "direction":
                        params["angle_degrees"] = -90.0 if raw == "right" else 90.0
                elif skill == "grasp":
                    params["object_name"] = raw
                elif skill in ("raise_arm", "lower_arm"):
                    params["arm"] = raw if raw in ("right", "left") else "right"
            elif param_key == "direction" and m.lastindex and m.lastindex >= 1:
                raw = m.group(1).strip()
                params["angle_degrees"] = -90.0 if raw == "right" else 90.0

            return {"skill": skill, "params": params}
        return None

    def execute(self, text: str, controller: MotionController) -> dict:
        """Parse text and execute the matching skill. Returns result or error."""
        parsed = self.parse(text)
        if parsed is None:
            return {"error": "no match", "text": text}
        skill_name = parsed["skill"]
        params = parsed["params"]
        method = getattr(controller, skill_name, None)
        if method is None:
            return {"error": f"skill '{skill_name}' not found on controller"}
        try:
            return method(**params)
        except Exception as exc:
            return {"error": str(exc), "skill": skill_name, "params": params}
