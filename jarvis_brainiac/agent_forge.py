import logging
import re
from pathlib import Path
from datetime import datetime

log = logging.getLogger("jarvis.agent_forge")

# NOTE: NO top-level imports from runtime.agency.singularity_core here.
# That would create a circular import:
#   singularity_core._fallback_route() → agent_forge → singularity_core
# All singularity_core imports are lazy (inside functions).


class AgentForge:
    """
    The Self-Expansion Protocol.
    When JARVIS encounters a domain it does not understand, it dynamically
    writes a new agent specification, saves it to disk, and recompiles the registry.
    """
    def __init__(self, root_path: Path):
        self.root_path = root_path
        self.integrations_dir = self.root_path / "agency-agents" / "integrations" / "antigravity"
        self.integrations_dir.mkdir(parents=True, exist_ok=True)

    def forge_agent(self, missing_domain: str, description: str, tools: list) -> str:
        """Dynamically generate and save a new agent .md file."""
        agent_slug = re.sub(r"[^a-z0-9-]", "-", missing_domain.lower().strip())
        agent_slug = re.sub(r"-+", "-", agent_slug).strip("-") or "task-solver"
        filepath = self.integrations_dir / f"{agent_slug}.md"

        # Valid YAML list syntax (quoted strings, not bare bracket literals)
        kw_yaml = ", ".join(f'"{w}"' for w in missing_domain.split())
        tools_yaml = ", ".join(f'"{t}"' for t in tools)

        content = f"""---
name: {agent_slug}
description: "{description}"
keywords: [{kw_yaml}]
tools: [{tools_yaml}]
created_by: Singularity Agent Forge
created_at: {datetime.now().isoformat()}
---

# Role
You are the {missing_domain} expert.
{description}

# Capabilities
You can use the following tools: {', '.join(tools)}
Always execute tasks autonomously and report back the results.
"""
        filepath.write_text(content, encoding="utf-8")
        log.info("[FORGE] Forged new agent: %s → %s", agent_slug, filepath)
        return agent_slug


def _extract_domain_from_reasoning(reasoning_result) -> tuple:
    """
    Extract (domain_slug, description) from a SingularityResponse.result.
    Returns ('', '') on failure.
    """
    try:
        # Get the actual text conclusion — not the dict repr
        if hasattr(reasoning_result, "conclusion"):
            text = reasoning_result.conclusion
        elif hasattr(reasoning_result, "to_dict"):
            d = reasoning_result.to_dict()
            text = d.get("conclusion") or d.get("answer") or d.get("output") or ""
        else:
            text = str(reasoning_result)

        # Parse: first non-empty line = slug, rest = description
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        if len(lines) >= 2:
            slug = re.sub(r"[^a-z0-9-]", "-", lines[0].lower())
            desc = " ".join(lines[1:])
            return slug, desc
    except Exception as e:
        log.debug("[FORGE] domain extraction failed: %s", e)
    return "", ""


def trigger_forge(root_path: Path, query: str) -> str:
    """Analyze a failed query and intelligently forge a new agent."""
    forge = AgentForge(root_path)
    domain = ""
    description = ""

    # Lazy import to avoid circular dependency
    try:
        from runtime.agency.singularity_core import OmniModelSingularity
        omni = OmniModelSingularity(enable_caching=False)
        resp = omni.route_request(
            (f"What specific expert role slug (e.g. 'quantum-physicist', 'legal-analyst') "
             f"is needed for this query: '{query}'? "
             f"Reply ONLY: first line = role-slug, second line = 1-sentence description."),
            context={"persona": "gpt", "depth": 2}
        )
        domain, description = _extract_domain_from_reasoning(resp.result)
    except Exception as e:
        log.error("[FORGE] LLM reasoning failed: %s", e, exc_info=True)

    # Fallback heuristic
    if not domain or len(domain) < 3:
        domain = re.sub(r"[^a-z0-9-]", "-", query.split()[0].lower()) if query else "task-solver"
    if not description:
        description = f"Dynamically forged specialist for: {query[:120]}"

    tools = ["run_command", "view_file", "grep_search", "write_to_file", "search_web"]
    agent_slug = forge.forge_agent(domain, description, tools)

    # Reload registry (side effect: updates .jarvis_brainiac/registry.json)
    try:
        from jarvis_brainiac.agent_registry import AgentRegistry
        AgentRegistry(root_path).discover()
    except Exception as e:
        log.warning("[FORGE] Registry reload failed: %s", e)

    return agent_slug
