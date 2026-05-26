"""Discover and load persona files from the Agency repo as Skills."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator

import yaml  # type: ignore[import-untyped]

# Folders in the repo root that contain agent persona markdown files.
DEFAULT_CATEGORIES: tuple[str, ...] = (
    "academic",
    "design",
    "engineering",
    "finance",
    "game-development",
    "jarvis",
    "marketing",
    "paid-media",
    "product",
    "project-management",
    "sales",
    "science",
    "spatial-computing",
    "specialized",
    "strategy",
    "support",
    "testing",
)

_FRONTMATTER = re.compile(r"^---\r?\n(.*?)\r?\n---\r?\n(.*)$", re.DOTALL)


@dataclass(frozen=True)
class Skill:
    """A persona file parsed into a runnable skill."""

    slug: str
    name: str
    description: str
    category: str
    color: str
    emoji: str
    vibe: str
    body: str
    path: Path
    extra: dict = field(default_factory=dict)
    # Optional tool policy from frontmatter. If `tools_allowed` is set, only
    # those tool names are exposed to this skill. If `tools_denied` is set,
    # those names are removed. If both are absent, the skill gets every
    # builtin tool (status quo).
    tools_allowed: tuple[str, ...] | None = None
    tools_denied: tuple[str, ...] = ()

    @property
    def system_prompt(self) -> str:
        """The text we send to the LLM as the system prompt for this skill."""
        return self.body.strip()

    def summary(self) -> str:
        """One-line human-readable summary of this skill."""
        return f"{self.emoji} {self.name} ({self.category}) — {self.description}"

    def tool_is_allowed(self, name: str) -> bool:
        """Return True if `name` may be exposed to this skill."""
        if self.tools_allowed is not None and name not in self.tools_allowed:
            return False
        if name in self.tools_denied:
            return False
        return True


def _slugify(path: Path) -> str:
    return path.stem


def _parse_one(path: Path, category: str) -> Skill | None:
    text = path.read_text(encoding="utf-8")
    match = _FRONTMATTER.match(text)
    if not match:
        return None

    raw_meta, body = match.groups()
    try:
        meta = yaml.safe_load(raw_meta) or {}
    except yaml.YAMLError:
        return None
    if not isinstance(meta, dict):
        return None

    name = str(meta.get("name") or path.stem.replace("-", " ").title()).strip()
    description = str(meta.get("description") or "").strip()
    color = str(meta.get("color") or "white").strip()
    emoji = str(meta.get("emoji") or "🤖").strip()
    vibe = str(meta.get("vibe") or "").strip()
    tools_allowed = _parse_tool_list(meta.get("tools_allowed"))
    tools_denied = _parse_tool_list(meta.get("tools_denied")) or ()

    known = {"name", "description", "color", "emoji", "vibe",
             "tools_allowed", "tools_denied"}
    extra = {k: v for k, v in meta.items() if k not in known}

    return Skill(
        slug=_slugify(path),
        name=name,
        description=description,
        category=category,
        color=color,
        emoji=emoji,
        vibe=vibe,
        body=body,
        path=path,
        extra=extra,
        tools_allowed=tools_allowed,
        tools_denied=tools_denied,
    )


def _parse_tool_list(raw: Any) -> tuple[str, ...] | None:
    """Accept a YAML list, a comma-separated string, or None.

    Returns None when the field is absent (so callers can distinguish
    'no policy' from 'explicit empty list').
    """
    if raw is None:
        return None
    if isinstance(raw, str):
        items = [s.strip() for s in raw.split(",") if s.strip()]
        return tuple(items)
    if isinstance(raw, (list, tuple)):
        return tuple(str(x).strip() for x in raw if str(x).strip())
    return None


def discover_repo_root(start: Path | None = None) -> Path:
    """Walk up from `start` until we find a folder that looks like the Agency repo."""
    here = (start or Path(__file__)).resolve()
    for candidate in (here, *here.parents):
        if candidate.is_dir() and (candidate / "engineering").is_dir() and (candidate / "README.md").is_file():
            return candidate
    raise FileNotFoundError("Could not locate Agency repo root (no engineering/ found above this file).")


def load_skills(
    repo_root: Path | None = None,
    categories: Iterable[str] | None = None,
) -> list[Skill]:
    """Load every persona markdown file under the configured category folders."""
    root = (repo_root or discover_repo_root()).resolve()
    cats = list(categories) if categories is not None else list(DEFAULT_CATEGORIES)

    skills: list[Skill] = []
    seen: set[str] = set()
    for category in cats:
        cat_dir = root / category
        if not cat_dir.is_dir():
            continue
        for md in sorted(cat_dir.rglob("*.md")):
            if md.name.lower() == "readme.md":
                continue
            skill = _parse_one(md, category)
            if skill is None or skill.slug in seen:
                continue
            seen.add(skill.slug)
            skills.append(skill)
    return skills


class SkillRegistry:
    """In-memory index of loaded skills with simple lookup helpers."""

    def __init__(self, skills: list[Skill]):
        self._skills = list(skills)
        self._by_slug = {s.slug: s for s in self._skills}

    @classmethod
    def load(cls, repo_root: Path | None = None) -> "SkillRegistry":
        """Discover and load all skill markdown files from the repo."""
        return cls(load_skills(repo_root))

    def __len__(self) -> int:
        return len(self._skills)

    def __iter__(self) -> "Iterator[Skill]":
        return iter(self._skills)

    def all(self) -> list[Skill]:
        """Return every loaded skill as a list."""
        return list(self._skills)

    def by_slug(self, slug: str) -> Skill | None:
        """Return the skill matching *slug*, or None."""
        return self._by_slug.get(slug)

    def by_category(self, category: str) -> list[Skill]:
        """Return all skills in *category*."""
        return [s for s in self._skills if s.category == category]

    def categories(self) -> list[str]:
        """Return sorted list of all distinct category names."""
        return sorted({s.category for s in self._skills})

    def search(self, query: str, limit: int = 10) -> list[Skill]:
        """Naive keyword scoring over name + description + vibe."""
        q = query.lower().strip()
        if not q:
            return []
        terms = [t for t in re.split(r"\s+", q) if t]
        scored: list[tuple[int, Skill]] = []
        for s in self._skills:
            hay = f"{s.name}\n{s.description}\n{s.vibe}\n{s.slug}".lower()
            score = sum(hay.count(t) for t in terms)
            if score > 0:
                scored.append((score, s))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [s for _, s in scored[:limit]]


# ---------------------------------------------------------------------------
# SkillWatcher — hot-reload skill YAML/MD files without restart
# ---------------------------------------------------------------------------

import threading
import time as _time
from typing import Callable as _Callable

_POLL_INTERVAL_S = 5.0


class SkillWatcher:
    """Watch a skills directory and reload on file changes.

    Uses pure mtime-polling (no watchdog dependency) every
    *poll_interval_s* seconds.  When a change is detected, calls
    *on_reload(registry)* with the freshly-loaded registry.

    Usage::

        registry = SkillRegistry.load()

        def _on_change(new_registry: SkillRegistry) -> None:
            nonlocal registry
            registry = new_registry
            print("יחידת מיומנות נטענה מחדש")

        watcher = SkillWatcher(
            watch_dir=Path.home() / ".agency" / "skills",
            reload_fn=_on_change,
        )
        watcher.start()
        # ... later ...
        watcher.stop()
    """

    def __init__(
        self,
        watch_dir: Path,
        reload_fn: _Callable[["SkillRegistry"], None],
        repo_root: Path | None = None,
        poll_interval_s: float = _POLL_INTERVAL_S,
    ) -> None:
        self._watch_dir = watch_dir
        self._reload_fn = reload_fn
        self._repo_root = repo_root
        self._poll_interval = poll_interval_s
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_mtimes: dict[Path, float] = {}

    # ── public API ─────────────────────────────────────────────────────────

    def start(self) -> None:
        """Start the background polling thread."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._last_mtimes = self._snapshot()
        self._thread = threading.Thread(
            target=self._poll_loop, daemon=True, name="SkillWatcher"
        )
        self._thread.start()

    def stop(self) -> None:
        """Signal the polling thread to stop (non-blocking)."""
        self._stop_event.set()

    def join(self, timeout: float | None = None) -> None:
        """Wait for the polling thread to exit."""
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ── internals ──────────────────────────────────────────────────────────

    def _snapshot(self) -> dict[Path, float]:
        """Return {path: mtime} for all .md and .yaml files in watch_dir."""
        result: dict[Path, float] = {}
        if not self._watch_dir.is_dir():
            return result
        for ext in ("*.md", "*.yaml", "*.yml"):
            for p in self._watch_dir.rglob(ext):
                try:
                    result[p] = p.stat().st_mtime
                except OSError:
                    pass
        return result

    def _has_changed(self, new: dict[Path, float]) -> bool:
        if set(new.keys()) != set(self._last_mtimes.keys()):
            return True
        return any(new[p] != self._last_mtimes.get(p) for p in new)

    def _poll_loop(self) -> None:
        from .logging import get_logger as _get_logger
        log = _get_logger()
        while not self._stop_event.wait(timeout=self._poll_interval):
            try:
                current = self._snapshot()
                if self._has_changed(current):
                    log.info("SkillWatcher: שינוי זוהה — טוען מחדש מיומנויות")
                    self._last_mtimes = current
                    try:
                        new_registry = SkillRegistry.load(self._repo_root)
                        self._reload_fn(new_registry)
                        log.info(
                            "SkillWatcher: %d יחידות מיומנות נטענו מחדש",
                            len(new_registry),
                        )
                    except Exception as exc:  # noqa: BLE001
                        log.error("SkillWatcher: שגיאה בטעינה — %s", exc)
            except Exception as exc:  # noqa: BLE001
                log.error("SkillWatcher: שגיאה בלולאת הסקר — %s", exc)
