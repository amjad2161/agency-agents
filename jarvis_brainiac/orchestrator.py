"""
Orchestrator — the central JARVIS BRAINIAC router.

Routes natural-language requests to the best agent(s), composes multi-agent
workflows, and delegates to the upstream `runtime/agency/` Claude tool-use
loop when available.

Decision tree (deterministic, no LLM required for routing):
    1. Explicit ``@agent-name`` mention → that agent
    2. Multi-domain keyword detection → spawn parallel team
    3. Single best match (registry score) → that agent
    4. Fallback → JARVIS Core orchestrator persona
"""
from __future__ import annotations

import re
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .agent_registry import AgentRegistry, Agent


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
        Claude tool-use loop (runtime/agency/) can execute.
        """
        d = self.route(request)
        return {
            "request": request,
            "routing": d.to_dict(),
            "execution": "delegate-to-agency-runtime",
            "next_step": (
                f"runtime/agency/cli.py run --agent {d.primary.name} "
                f"--task {json.dumps(request)}"
                if d.primary else "no-agent-matched"
            ),
        }

    # -------------------------------------------------------------- diagnostics
    def health(self) -> dict:
        return {
            "version": "1.0.0-singularity",
            "registry": self.registry.stats(),
            "root": str(self.root),
            "team_triggers": list(TEAM_TRIGGERS.keys()),
        }
