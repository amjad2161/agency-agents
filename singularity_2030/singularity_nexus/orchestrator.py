from __future__ import annotations

from collections import defaultdict
from typing import Any

from .models import ExecutionProfile, SingularityCatalog


COMMON_DENOMINATOR = {
    "north_star": "A modular autonomous operating system for agents, tools, domains, and humans.",
    "themes": [
        "agentic orchestration",
        "tool-enabled autonomy",
        "human-in-the-loop operations",
        "domain-specific execution",
        "cross-harness portability",
        "observable and reversible automation",
    ],
    "operating_model": [
        "Every repository is treated as a replaceable module with a clear contract.",
        "Agent frameworks plan and delegate; domain applications execute bounded work.",
        "Dangerous domains require policy gates, test gates, and explicit operator control.",
        "Each module can run alone, but shared manifests make composition deterministic.",
    ],
}


PROFILES = {
    "full-stack-ai-ops": ExecutionProfile(
        slug="full-stack-ai-ops",
        name="Full Stack AI Operations",
        autonomy_level="supervised-autonomous",
        purpose="Run the agent, prompt, SDK, workflow, and application layer as one governed engineering system.",
        module_slugs=(
            "everything-claude-code",
            "skills",
            "claude-code",
            "agency-agents",
            "anthropic-sdk-typescript",
            "anthropic-quickstarts",
            "mythos",
            "superagi",
            "amjad2161",
            "comfyui",
            "cors-anywhere",
            "auto-save-sync",
        ),
        invariants=(
            "Quality gates run before irreversible changes.",
            "LLM/tool execution is routed through explicit module contracts.",
            "Applications keep their own deployment boundary and data ownership.",
        ),
    ),
    "real-world-autonomy": ExecutionProfile(
        slug="real-world-autonomy",
        name="Real World Autonomy",
        autonomy_level="operator-approved",
        purpose="Coordinate physical, financial, and operational systems without removing human safety control.",
        module_slugs=(
            "everything-claude-code",
            "agency-agents",
            "mythos",
            "amjad2161",
            "dji-owner",
            "autonomous-trading-engine",
            "tradingboy",
            "cors-anywhere",
        ),
        invariants=(
            "No live money or hardware movement without an approval gate.",
            "Simulation and backtest results must precede production execution.",
            "Safety, legal, and rollback plans are part of the execution contract.",
        ),
    ),
    "research-to-runtime": ExecutionProfile(
        slug="research-to-runtime",
        name="Research to Runtime",
        autonomy_level="analysis-first",
        purpose="Turn reference prompts, leaked architectures, quickstarts, and SDKs into legal production patterns.",
        module_slugs=(
            "system-prompts-and-models-of-ai-tools",
            "claude-code-abc",
            "claude-code",
            "anthropic-sdk-typescript",
            "anthropic-quickstarts",
            "skills",
            "everything-claude-code",
        ),
        invariants=(
            "Proprietary or leaked material remains research-only.",
            "Production code uses licensed SDKs, docs, and original implementation.",
            "Prompt/tool ideas are converted into tests and contracts before reuse.",
        ),
    ),
}


class SingularityOrchestrator:
    def __init__(self, catalog: SingularityCatalog):
        self.catalog = catalog

    def common_denominator(self) -> dict[str, Any]:
        return {
            **COMMON_DENOMINATOR,
            "layers": sorted({module.layer for module in self.catalog.modules}),
        }

    def capability_map(self) -> dict[str, list[str]]:
        grouped: dict[str, list[str]] = defaultdict(list)
        for module in self.catalog.modules:
            for capability in module.capabilities:
                grouped[capability].append(module.slug)
        return {capability: sorted(slugs) for capability, slugs in sorted(grouped.items())}

    def profile(self, slug: str) -> ExecutionProfile:
        if slug not in PROFILES:
            available = ", ".join(sorted(PROFILES))
            raise KeyError(f"Unknown profile '{slug}'. Available profiles: {available}")

        profile = PROFILES[slug]
        known_modules = {module.slug for module in self.catalog.modules}
        missing = [module_slug for module_slug in profile.module_slugs if module_slug not in known_modules]
        if missing:
            raise ValueError(f"Profile '{slug}' references unknown modules: {', '.join(missing)}")
        return profile

    def summary(self) -> dict[str, Any]:
        return {
            "modules": len(self.catalog.modules),
            "edges": len(self.catalog.integration_edges),
            "layers": sorted({module.layer for module in self.catalog.modules}),
            "profiles": sorted(PROFILES),
            "common_denominator": self.common_denominator(),
        }
