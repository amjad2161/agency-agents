"""Tiny on-disk session memory."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path


class TurnRecord:
    """One conversation turn. Accepts either ``text`` or ``content`` (alias)."""

    __slots__ = ("role", "text", "ts")

    def __init__(
        self,
        role: str,
        text: str | None = None,
        ts: float | None = None,
        *,
        content: str | None = None,
    ) -> None:
        if text is None and content is None:
            raise TypeError("TurnRecord requires text= or content=")
        if text is not None and content is not None and text != content:
            raise ValueError("text and content must match if both supplied")
        self.role = role
        self.text = text if text is not None else content  # type: ignore[assignment]
        self.ts = ts if ts is not None else time.time()

    @property
    def content(self) -> str:
        return self.text

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, TurnRecord):
            return NotImplemented
        return self.role == other.role and self.text == other.text and self.ts == other.ts

    def __repr__(self) -> str:
        return f"TurnRecord(role={self.role!r}, text={self.text!r}, ts={self.ts!r})"

    def to_dict(self) -> dict:
        return {"role": self.role, "text": self.text, "ts": self.ts}


@dataclass
class Session:
    session_id: str
    skill_slug: str
    turns: list[TurnRecord] = field(default_factory=list)

    def append(self, role: str, text: str) -> None:
        """Append a turn record with *role* and *text* to this session."""
        self.turns.append(TurnRecord(role=role, text=text))


class MemoryStore:
    """Newline-delimited JSON, one file per session."""

    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, session_id: str) -> Path:
        safe = "".join(c for c in session_id if c.isalnum() or c in "-_") or "default"
        return self.root / f"{safe}.jsonl"

    def load(self, session_id: str) -> Session | None:
        """Load a session from disk, or return None if not found."""
        path = self._path(session_id)
        if not path.exists():
            return None
        skill_slug = ""
        turns: list[TurnRecord] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            data = json.loads(line)
            if data.get("kind") == "header":
                skill_slug = data.get("skill_slug", "")
            elif data.get("kind") == "turn":
                turns.append(TurnRecord(role=data["role"], text=data["text"], ts=data.get("ts", 0)))
        return Session(session_id=session_id, skill_slug=skill_slug, turns=turns)

    def save(self, session: Session) -> None:
        """Persist a session to disk as newline-delimited JSON."""
        path = self._path(session.session_id)
        with path.open("w", encoding="utf-8") as f:
            f.write(json.dumps({"kind": "header", "skill_slug": session.skill_slug}) + "\n")
            for turn in session.turns:
                f.write(json.dumps({"kind": "turn", **turn.to_dict()}) + "\n")
