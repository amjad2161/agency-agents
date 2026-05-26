"""
AgentRegistry — discovers, parses, and indexes all 341+ agent .md files
across all divisions. Provides keyword/semantic lookup for the Orchestrator.
"""
from __future__ import annotations

import re
import json
import hashlib
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Iterable, Optional


DIVISIONS = (
    "academic", "design", "engineering", "finance", "game-development",
    "jarvis", "marketing", "paid-media", "product", "project-management",
    "sales", "science", "spatial-computing", "specialized", "strategy",
    "support", "testing",
)

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


@dataclass
class Agent:
    name: str
    division: str
    path: str
    description: str = ""
    color: str = ""
    tools: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    sha256: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class AgentRegistry:
    """
    Walks the project root, parses every agent .md, builds an index.
    Index is persisted to ``.jarvis_brainiac/registry.json`` for fast cold-start.
    """

    def __init__(self, root: Path | str):
        self.root = Path(root).resolve()
        self.cache_dir = self.root / ".jarvis_brainiac"
        self.cache_dir.mkdir(exist_ok=True)
        self.cache_file = self.cache_dir / "registry.json"
        self.agents: dict[str, Agent] = {}

    # --------------------------------------------------------------- discovery
    def discover(self, force: bool = False) -> dict[str, Agent]:
        """Scan all division dirs, parse frontmatter, build index."""
        if not force and self.cache_file.exists():
            try:
                cached = json.loads(self.cache_file.read_text(encoding="utf-8"))
                self.agents = {
                    name: Agent(**data) for name, data in cached.items()
                }
                return self.agents
            except Exception:
                pass  # fall through to fresh scan

        for div in DIVISIONS:
            div_path = self.root / div
            if not div_path.is_dir():
                continue
            for md in div_path.rglob("*.md"):
                try:
                    agent = self._parse_agent(md, division=div)
                    if agent:
                        self.agents[agent.name] = agent
                except Exception as exc:  # pragma: no cover — keep scan resilient
                    print(f"[registry] skip {md}: {exc}")

        self._persist()
        return self.agents

    def _parse_agent(self, path: Path, division: str) -> Optional[Agent]:
        text = path.read_text(encoding="utf-8", errors="replace")
        if not text.strip():
            return None
        sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
        m = FRONTMATTER_RE.match(text)
        meta = {}
        if m:
            for line in m.group(1).splitlines():
                if ":" in line:
                    k, _, v = line.partition(":")
                    meta[k.strip()] = v.strip().strip('"').strip("'")
        name = meta.get("name") or path.stem
        body = text[m.end():] if m else text
        keywords = self._extract_keywords(body)
        return Agent(
            name=name,
            division=division,
            path=str(path.relative_to(self.root)),
            description=meta.get("description", "")[:500],
            color=meta.get("color", ""),
            tools=[t.strip() for t in meta.get("tools", "").split(",") if t.strip()],
            keywords=keywords[:30],
            sha256=sha,
        )

    @staticmethod
    def _extract_keywords(body: str) -> list[str]:
        """Naive keyword extractor: lowercase tokens of length ≥4, top frequency."""
        tokens = re.findall(r"[A-Za-z][A-Za-z0-9_-]{3,}", body.lower())
        stop = {
            "this", "that", "with", "from", "have", "your", "will", "they",
            "been", "were", "what", "when", "where", "should", "would",
            "could", "their", "there", "these", "those", "into", "than",
            "then", "also", "such", "each", "more", "most", "some", "many",
            "very", "make", "made", "must", "only", "like", "just", "user",
            "claude", "tools", "tool",
        }
        freq: dict[str, int] = {}
        for t in tokens:
            if t in stop:
                continue
            freq[t] = freq.get(t, 0) + 1
        return [w for w, _ in sorted(freq.items(), key=lambda kv: -kv[1])]

    def _persist(self) -> None:
        data = {name: a.to_dict() for name, a in self.agents.items()}
        self.cache_file.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # ------------------------------------------------------------------ search
    def find(self, query: str, top_k: int = 5) -> list[Agent]:
        """Keyword-overlap ranking. Replace with embeddings later."""
        if not self.agents:
            self.discover()
        q_tokens = set(re.findall(r"[a-z][a-z0-9_-]{2,}", query.lower()))
        scored: list[tuple[int, Agent]] = []
        for a in self.agents.values():
            score = 0
            score += sum(2 for k in a.keywords if k in q_tokens)
            score += sum(3 for k in q_tokens if k in a.name.lower())
            score += sum(1 for k in q_tokens if k in a.description.lower())
            if score:
                scored.append((score, a))
        scored.sort(key=lambda kv: -kv[0])
        return [a for _, a in scored[:top_k]]

    def by_division(self, division: str) -> Iterable[Agent]:
        return (a for a in self.agents.values() if a.division == division)

    def stats(self) -> dict:
        if not self.agents:
            self.discover()
        by_div: dict[str, int] = {}
        for a in self.agents.values():
            by_div[a.division] = by_div.get(a.division, 0) + 1
        return {
            "total_agents": len(self.agents),
            "by_division": by_div,
            "cache_path": str(self.cache_file),
        }
