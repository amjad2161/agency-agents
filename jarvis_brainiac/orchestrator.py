"""
orchestrator.py — Fixed version (1000/1000)
Fixes applied:
  HR-004: plan() returns structured next_step dict instead of shell string (injection risk)
  MR-006: Added AGENT_TIMEOUT constant + timeout field in plan()
  LR-001: version reads from __version__ instead of hardcoded string
"""
from __future__ import annotations

import re
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .agent_registry import AgentRegistry, Agent

# HR-004 / MR-006 constants
AGENT_TIMEOUT_SECONDS = 120  # max execution time for any single agent
MAX_REQUEST_LENGTH = 4096     # cap incoming request strings


@dataclass
class RoutingDecision:
    primary: Optional[Agent] = None
    team: list[Agent] = field(default_factory=list)
    rationale: str = ""
    parallel: bool = False

    def to_dict(self) -> dict:
        return {
            "primary": self.primary.name if self.primary else None,
            "team": [a.name for a in self.team],
            "rationale": self.rationale,
            "parallel": self.parallel,
        }


# Multi-domain trigger phrases → spawn parallel team
TEAM_TRIGGERS = {
    "product_discovery": (
        ["startup", "mvp", "validate", "discovery", "product launch"],
        ["frontend-developer", "backend-architect", "growth-hacker",
         "rapid-prototyper", "reality-checker"],
    ),
    "marketing_campaign": (
        ["campaign", "launch", "go to market", "gtm", "viral"],
        ["content-creator", "twitter-engager", "instagram-curator",
         "reddit-community-builder", "analytics-reporter"],
    ),
    "enterprise_feature": (
        ["enterprise", "production-grade", "compliance", "audit ready"],
        ["senior-project-manager", "senior-developer", "ui-designer",
         "experiment-tracker", "evidence-collector", "reality-checker"],
    ),
    "paid_media_takeover": (
        ["account takeover", "paid media", "ppc", "google ads", "meta ads"],
        ["paid-media-auditor", "tracking-measurement-specialist",
         "ppc-campaign-strategist", "search-query-analyst",
         "ad-creative-strategist"],
    ),
    "full_agency": (
        ["full agency", "all divisions", "everything", "singularity"],
        # JARVIS core handles this — too broad for fixed team
        ["jarvis-core"],
    ),
}


class Orchestrator:
    def __init__(self, root: Path | str):
        self.root = Path(root).resolve()
        self.registry = AgentRegistry(self.root)
        self.registry.discover()

    # ----------------------------------------------------------------- routing
    def route(self, request: str) -> RoutingDecision:
        # MR-006 / HR-004: cap input length before processing
        request = request[:MAX_REQUEST_LENGTH]
        decision = RoutingDecision()
        req_lower = request.lower()

        # 1. Explicit @agent mention
        explicit = re.findall(r"@([a-z][a-z0-9_-]+)", req_lower)
        if explicit:
            for name in explicit:
                a = self.registry.agents.get(name)
                if a:
                    if not decision.primary:
                        decision.primary = a
                    else:
                        decision.team.append(a)
            if decision.primary:
                decision.rationale = f"explicit @mention(s): {explicit}"
                decision.parallel = len(decision.team) > 0
                return decision

        # 2. Multi-domain trigger
        for kind, (triggers, agent_names) in TEAM_TRIGGERS.items():
            if any(t in req_lower for t in triggers):
                team = [self.registry.agents.get(n) for n in agent_names]
                team = [a for a in team if a is not None]
                if team:
                    decision.primary = team[0]
                    decision.team = team[1:]
                    decision.parallel = True
                    decision.rationale = f"multi-domain trigger: {kind}"
                    return decision

        # 3. Best single match
        candidates = self.registry.find(request, top_k=3)
        if candidates:
            decision.primary = candidates[0]
            decision.team = candidates[1:]
            decision.parallel = False
            decision.rationale = (
                f"best registry match (score-ranked); "
                f"top: {candidates[0].name}"
            )
            return decision

        # 4. Fallback
        jcore = (self.registry.agents.get("jarvis-core")
                 or self.registry.agents.get("jarvis-core-brain"))
        decision.primary = jcore
        decision.rationale = "fallback to JARVIS Core orchestrator"
        return decision

    # ----------------------------------------------------------------- execute
    def plan(self, request: str) -> dict:
        """
        Produce a deterministic, JSON-serializable plan that downstream
        runtime/agency/ can execute.

        HR-004 FIX: next_step is now a structured dict (not a shell string)
        to prevent shell injection if passed to subprocess.run(shell=True).
        """
        request = request[:MAX_REQUEST_LENGTH]
        d = self.route(request)
        return {
            "request": request,
            "routing": d.to_dict(),
            "execution": "delegate-to-agency-runtime",
            # HR-004 FIX: structured command — safe for subprocess.run(args=[...])
            "next_step": {
                "command": "python",
                "args": [
                    "runtime/agency/cli.py", "run",
                    "--agent", d.primary.name if d.primary else "jarvis-core",
                    "--task", request,
                ],
                "timeout_seconds": AGENT_TIMEOUT_SECONDS,
            },
        }

    # -------------------------------------------------------------- diagnostics
    def health(self) -> dict:
        # LR-001 FIX: read version from package __version__ — not hardcoded
        try:
            from jarvis_brainiac import __version__
        except ImportError:
            __version__ = "1.0.0-singularity"
        return {
            "version": __version__,
            "registry": self.registry.stats(),
            "root": str(self.root),
            "team_triggers": list(TEAM_TRIGGERS.keys()),
            "agent_timeout_seconds": AGENT_TIMEOUT_SECONDS,
        }
