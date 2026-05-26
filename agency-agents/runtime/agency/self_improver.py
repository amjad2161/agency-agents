"""Self-improvement system — Pass 21.

JARVIS analyses its own routing performance (using traces written by Pass 16
Tracer) and proposes new KEYWORD_SLUG_BOOST entries for skills that are being
routed slowly or incorrectly.

Classes
-------
    ImprovementSuggestion  — a proposed new keyword→slug boost entry
    SelfImprover           — analyses traces and patches jarvis_brain.py

CLI
---
    agency improve [--dry-run] [--threshold 100]
    agency improve --report

Usage (library)
---------------
    from agency.self_improver import SelfImprover

    imp = SelfImprover()
    slow = imp.analyze_slow_routes()          # list of slow skill slugs
    sugg = imp.suggest_boost_keys("devops")   # list of suggestions
    imp.auto_improve(dry_run=True)            # full pipeline (read-only)
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class ImprovementSuggestion:
    """A single proposed keyword→slug boost improvement."""

    keyword: str
    slug: str
    weight: float
    reason: str
    source_span_name: str = ""
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "keyword": self.keyword,
            "slug": self.slug,
            "weight": self.weight,
            "reason": self.reason,
            "source_span_name": self.source_span_name,
            "created_at": self.created_at,
        }


# ---------------------------------------------------------------------------
# Improvement log
# ---------------------------------------------------------------------------

_DEFAULT_LOG = Path.home() / ".agency" / "improvement_log.jsonl"


def _append_log(entry: Dict[str, Any], log_path: Path = _DEFAULT_LOG) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")


def _read_log(log_path: Path = _DEFAULT_LOG) -> List[Dict[str, Any]]:
    if not log_path.exists():
        return []
    entries: List[Dict[str, Any]] = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return entries


# ---------------------------------------------------------------------------
# Core engine
# ---------------------------------------------------------------------------

# Heuristic map: skill slug fragments → related keywords to suggest
_SLUG_KEYWORD_HINTS: Dict[str, List[str]] = {
    "devops":      ["kubectl", "k8s", "ci/cd", "github-actions", "docker-compose"],
    "robotics":    ["joint", "kinematics", "servo", "actuator", "imu", "urdf"],
    "ml":          ["pytorch", "tensorflow", "gradient", "backprop", "neural", "epoch"],
    "data":        ["pandas", "dbt", "spark", "airflow", "datalake"],
    "finance":     ["equity", "bond", "irr", "wacc", "p&l"],
    "security":    ["cve", "pentest", "owasp", "jwt", "rbac", "iam"],
    "frontend":    ["react", "nextjs", "css", "webpack", "vite", "tsx"],
    "backend":     ["fastapi", "django", "grpc", "rest", "graphql"],
    "embedded":    ["uart", "spi", "i2c", "gpio", "microcontroller", "stm32"],
    "nlp":         ["bert", "transformer", "attention", "tokenizer", "llama"],
    "twin":        ["digital-twin", "iot", "sensor-fusion", "mqtt"],
    "platform":    ["eks", "gke", "aks", "argocd", "flux"],
}


class SelfImprover:
    """Analyses JARVIS traces and proposes routing improvements.

    Parameters
    ----------
    brain_path:
        Path to ``jarvis_brain.py``. Defaults to the sibling file in the
        same package.
    trace_dir:
        Directory containing JSONL trace files (``~/.agency/traces/`` by
        default).
    log_path:
        Path to the improvement log JSONL file.
    """

    def __init__(
        self,
        brain_path: Optional[Path] = None,
        trace_dir: Optional[Path] = None,
        log_path: Optional[Path] = None,
    ) -> None:
        self.brain_path = brain_path or (
            Path(__file__).parent / "jarvis_brain.py"
        )
        self.trace_dir = trace_dir or (Path.home() / ".agency" / "traces")
        self.log_path = log_path or _DEFAULT_LOG

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze_slow_routes(self, threshold_ms: float = 100.0) -> List[str]:
        """Return list of skill slugs whose spans exceeded *threshold_ms*.

        Reads today's trace file (and yesterday's if today is empty).
        Returns de-duplicated slugs, ordered by mean latency descending.
        """
        spans = self._load_recent_spans()
        slow: Dict[str, List[float]] = {}
        for span in spans:
            duration = span.get("duration_ms")
            name = span.get("name", "")
            # Span names look like "skill.route.<slug>" or "route.<slug>"
            slug = self._extract_slug_from_span(name)
            if slug and duration is not None and float(duration) > threshold_ms:
                slow.setdefault(slug, []).append(float(duration))
        # Sort by mean latency descending
        ranked = sorted(slow.keys(), key=lambda s: -sum(slow[s]) / len(slow[s]))
        return ranked

    def suggest_boost_keys(
        self, slow_skill_slug: str, n: int = 3
    ) -> List[ImprovementSuggestion]:
        """Generate keyword boost suggestions for *slow_skill_slug*.

        Looks up slug hints and returns up to *n* suggestions ranked by
        estimated impact.
        """
        suggestions: List[ImprovementSuggestion] = []
        # Find matching hint entries
        for slug_frag, keywords in _SLUG_KEYWORD_HINTS.items():
            if slug_frag in slow_skill_slug or slow_skill_slug in slug_frag:
                for kw in keywords[:n]:
                    suggestions.append(ImprovementSuggestion(
                        keyword=kw,
                        slug=slow_skill_slug,
                        weight=6.0,
                        reason=(
                            f"Slug '{slow_skill_slug}' had high latency; "
                            f"keyword '{kw}' likely improves routing precision."
                        ),
                        source_span_name=f"route.{slow_skill_slug}",
                    ))
                break
        # Generic fallback: extract tokens from slug name
        if not suggestions:
            tokens = re.split(r"[-_]", slow_skill_slug)
            for tok in tokens[:n]:
                if len(tok) >= 3:
                    suggestions.append(ImprovementSuggestion(
                        keyword=tok,
                        slug=slow_skill_slug,
                        weight=4.0,
                        reason=(
                            f"Auto-derived token '{tok}' from slug "
                            f"'{slow_skill_slug}'."
                        ),
                        source_span_name=f"route.{slow_skill_slug}",
                    ))
        return suggestions[:n]

    def apply_suggestion(self, suggestion: ImprovementSuggestion) -> bool:
        """Write *suggestion* into ``KEYWORD_SLUG_BOOST`` in jarvis_brain.py.

        Performs a minimal text-based patch: if the keyword already exists it
        updates the weight; otherwise it appends a new entry in the correct
        section. Returns ``True`` on success, ``False`` if the file could not
        be modified (e.g., read-only).
        """
        if not self.brain_path.exists():
            return False

        src = self.brain_path.read_text(encoding="utf-8")

        # Check if keyword already present
        pattern = re.compile(
            r'("' + re.escape(suggestion.keyword) + r'"\s*:\s*\{[^}]*\})',
        )
        if pattern.search(src):
            # Already present — skip to avoid duplicate entries
            _append_log(
                {**suggestion.to_dict(), "action": "skipped_duplicate"},
                self.log_path,
            )
            return True

        # Find the KEYWORD_SLUG_BOOST dict and inject after the opening brace
        insert_line = (
            f'    "{suggestion.keyword}": '
            f'{{"{suggestion.slug}": {suggestion.weight}}},  '
            f'# auto-added {suggestion.created_at[:10]}\n'
        )
        marker = "KEYWORD_SLUG_BOOST: dict[str, dict[str, float]] = {"
        if marker not in src:
            # Fallback marker
            marker = "KEYWORD_SLUG_BOOST = {"
        if marker not in src:
            return False

        new_src = src.replace(marker, marker + "\n" + insert_line, 1)
        try:
            self.brain_path.write_text(new_src, encoding="utf-8")
            _append_log(
                {**suggestion.to_dict(), "action": "applied"},
                self.log_path,
            )
            return True
        except OSError:
            return False

    def auto_improve(
        self,
        threshold_ms: float = 100.0,
        dry_run: bool = True,
        max_suggestions: int = 10,
    ) -> List[ImprovementSuggestion]:
        """Full pipeline: analyze → suggest → (optionally) apply.

        Parameters
        ----------
        threshold_ms:
            Span duration threshold to flag a route as slow.
        dry_run:
            If ``True``, generate suggestions but do NOT write to the brain.
        max_suggestions:
            Cap total suggestions produced.

        Returns list of suggestions (applied or proposed).
        """
        slow_slugs = self.analyze_slow_routes(threshold_ms)
        all_suggestions: List[ImprovementSuggestion] = []

        for slug in slow_slugs:
            suggestions = self.suggest_boost_keys(slug, n=3)
            all_suggestions.extend(suggestions)
            if len(all_suggestions) >= max_suggestions:
                break

        all_suggestions = all_suggestions[:max_suggestions]

        if not dry_run:
            for sugg in all_suggestions:
                self.apply_suggestion(sugg)

        return all_suggestions

    def improvement_report(self) -> List[Dict[str, Any]]:
        """Return the full improvement history from the log."""
        return _read_log(self.log_path)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _load_recent_spans(self) -> List[Dict[str, Any]]:
        """Load spans from today (and yesterday as fallback)."""
        from datetime import date, timedelta
        spans: List[Dict[str, Any]] = []
        for delta in (0, 1):
            day = (date.today() - timedelta(days=delta)).isoformat()
            path = self.trace_dir / f"{day}.jsonl"
            if path.exists():
                for line in path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line:
                        try:
                            spans.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
                if spans:
                    break
        return spans

    def _extract_slug_from_span(self, name: str) -> Optional[str]:
        """Extract a skill slug from a span name like 'skill.route.devops'."""
        parts = name.split(".")
        if len(parts) >= 2 and parts[0] in ("skill", "route", "router"):
            return parts[-1]
        if "route" in name:
            # e.g. "route.devops"
            idx = name.find("route.")
            tail = name[idx + len("route."):]
            if tail:
                return tail.split(".")[0]
        return None
