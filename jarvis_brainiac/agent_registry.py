"""
AgentRegistry — discovers, parses, and indexes all 341+ agent .md files
across all divisions. Provides keyword/semantic lookup for the Orchestrator.
"""
from __future__ import annotations

import logging
import re
import json
import hashlib
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Iterable, Optional

# LR-003: cache TTL — rescan after 24 hours even without force=True
REGISTRY_CACHE_TTL_SECONDS = 86400  # 24 hours

log = logging.getLogger(__name__)


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
            # LR-003 FIX: respect TTL — rescan if cache is older than 24 hours
            cache_age = time.time() - self.cache_file.stat().st_mtime
            if cache_age > REGISTRY_CACHE_TTL_SECONDS:
                log.info("AgentRegistry: cache expired (%.1fh old), rescanning", cache_age / 3600)
            else:
                try:
                    cached = json.loads(self.cache_file.read_text(encoding="utf-8"))
                    self.agents = {
                        name: Agent(**data) for name, data in cached.items()
                    }
                    log.debug("AgentRegistry: loaded %d agents from cache", len(self.agents))
                    return self.agents
                except Exception as e:
                    # HR-002 FIX: delete corrupted cache so next run starts fresh
                    log.warning("AgentRegistry: corrupted cache (%s), deleting and rescanning", e)
                    try:
                        self.cache_file.unlink()
                    except OSError:
                        pass
                    # fall through to fresh scan

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
                    log.warning("AgentRegistry: skip %s: %s", md, exc)

        self._persist()
        return self.agents

    def _parse_agent(self, path: Path, division: str) -> Optional[Agent]:
        # HR-009 FIX: proper UnicodeDecodeError handling — skip corrupted files
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as e:
            log.warning("AgentRegistry: encoding error in %s: %s — skipping", path, e)
            return None
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
            # MR-007 FIX: support both YAML list format and comma-separated
            tools=self._parse_tools(meta.get("tools", "")),
            keywords=keywords[:30],
            sha256=sha,
        )

    @staticmethod
    def _parse_tools(raw: str) -> list[str]:
        """Parse tools field from either YAML list or comma-separated string.
        
        Supports:
          tools: computer, bash, browser          # comma-separated
          tools:\n  - computer\n  - bash          # YAML list
        """
        if not raw or not raw.strip():
            return []
        # YAML list format: contains newlines or starts with '-'
        if "\n" in raw or raw.strip().startswith("-"):
            tools = []
            for line in raw.splitlines():
                t = line.strip().lstrip("-").strip().strip('"').strip("'")
                if t:
                    tools.append(t)
            return tools
        # Comma-separated format
        return [t.strip() for t in raw.split(",") if t.strip()]

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
        cache_age_hours = None
        if self.cache_file.exists():
            cache_age_hours = round((time.time() - self.cache_file.stat().st_mtime) / 3600, 1)
        return {
            "total_agents": len(self.agents),
            "by_division": by_div,
            "cache_path": str(self.cache_file),
            "cache_age_hours": cache_age_hours,
            "cache_ttl_hours": REGISTRY_CACHE_TTL_SECONDS // 3600,
        }
