from singularity_nexus.catalog import load_catalog
from singularity_nexus.orchestrator import SingularityOrchestrator


def build_orchestrator() -> SingularityOrchestrator:
    return SingularityOrchestrator(load_catalog())


def test_common_denominator_captures_shared_vision():
    common = build_orchestrator().common_denominator()

    assert common["north_star"] == "A modular autonomous operating system for agents, tools, domains, and humans."
    assert "agentic orchestration" in common["themes"]
    assert "tool-enabled autonomy" in common["themes"]
    assert "human-in-the-loop operations" in common["themes"]
    assert "domain-specific execution" in common["themes"]


def test_profile_builds_hermetic_stack_from_independent_modules():
    profile = build_orchestrator().profile("full-stack-ai-ops")

    assert profile.name == "Full Stack AI Operations"
    assert profile.module_slugs[0] == "everything-claude-code"
    assert "agency-agents" in profile.module_slugs
    assert "amjad2161" in profile.module_slugs
    assert "superagi" in profile.module_slugs
    assert profile.autonomy_level == "supervised-autonomous"


def test_capability_map_groups_projects_by_reusable_power():
    capability_map = build_orchestrator().capability_map()

    assert "agent-orchestration" in capability_map
    assert {"agency-agents", "mythos", "superagi"}.issubset(set(capability_map["agent-orchestration"]))
    assert "creative-generation" in capability_map
    assert "comfyui" in capability_map["creative-generation"]
    assert "real-world-operations" in capability_map
    assert {"dji-owner", "autonomous-trading-engine"}.issubset(set(capability_map["real-world-operations"]))
