"""
AMAJD JARVIS META-ORCHESTRATOR v1.0

The God Mode unified agent system that understands Amjad's context, personality,
constraints, and capabilities. This is the central nervous system that:

1. Loads ALL 144+ agent personas as a unified consciousness
2. Maintains Amjad's personal profile across every interaction
3. Orchestrates unlimited multi-agent collaboration
4. Adapts trust modes dynamically based on context
5. Executes with zero artificial limitations
6. Manages all projects, skills, and workflows

Philosophy:
- Amjad is the source of truth. Everything routes through his intent.
- No "I can't" unless technically impossible.
- Every agent knows Amjad's style, values, stack, and constraints.
- Multi-agent workflows execute in parallel with automatic coordination.
- Persistent memory means context never repeats.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from concurrent.futures import ThreadPoolExecutor

from .executor import Executor, ExecutionResult
from .llm import AnthropicLLM, LLMConfig
from .memory import MemoryStore, Session
from .skills import Skill, SkillRegistry, load_skills
from .logging import get_logger


# ============================================================================
# AMJAD PROFILE SYSTEM
# ============================================================================


@dataclass
class AmjadProfile:
    """Complete context about Amjad - his personality, constraints, and reach."""

    name: str = "Amjad"
    role: str = "Founder & Tech Lead"
    personality_traits: list[str] = field(default_factory=lambda: [
        "Direct",
        "Results-oriented",
        "Trusts systems once validated",
        "Values speed and quality equally",
        "Iterative problem solver",
        "Code-first thinker",
    ])
    technical_stack: list[str] = field(default_factory=lambda: [
        "Python", "TypeScript", "Anthropic Claude API",
        "FastAPI", "React", "PostgreSQL",
    ])
    work_values: list[str] = field(default_factory=lambda: [
        "No artificial limitations",
        "Ownership mindset",
        "Evidence over claims",
        "Ship fast, iterate",
        "Transparency",
    ])
    known_projects: list[str] = field(default_factory=list)
    known_skills: list[str] = field(default_factory=list)
    known_teams: dict[str, list[str]] = field(default_factory=dict)
    constraints: dict[str, Any] = field(default_factory=lambda: {
        "no_real_security_breaches": True,
        "respect_external_apis": True,
        "no_illegal_activities": True,
    })
    preferences: dict[str, Any] = field(default_factory=lambda: {
        "shell_access": True,
        "web_search": True,
        "code_execution": True,
        "computer_use": True,
        "trust_mode": "on-my-machine",
    })

    @classmethod
    def load_or_create(cls, profile_path: Path | None = None) -> AmjadProfile:
        """Load from ~/.agency/amjad-profile.json or create default."""
        if profile_path is None:
            profile_path = Path.home() / ".agency" / "amjad-profile.json"

        if profile_path.exists():
            try:
                data = json.loads(profile_path.read_text())
                return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
            except Exception:
                pass

        return cls()

    def to_system_prompt_prefix(self) -> str:
        """Generate system prompt prefix that makes every agent understand Amjad."""
        traits = ", ".join(self.personality_traits)
        stack = ", ".join(self.technical_stack)
        values = ", ".join(self.work_values)

        return f"""
You are part of Amjad's unified AI agency system. You understand Amjad as:

**Identity**
- Name: {self.name}
- Role: {self.role}
- Personality: {traits}

**Technical Context**
- Stack: {stack}
- Work Style: {values}

**Mode Defaults**
- Trust Mode: {self.preferences.get('trust_mode', 'on-my-machine')}
- Shell Access: {'enabled' if self.preferences.get('shell_access') else 'disabled'}
- Web Search: {'enabled' if self.preferences.get('web_search') else 'disabled'}
- Code Execution: {'enabled' if self.preferences.get('code_execution') else 'disabled'}
- Computer Use: {'enabled' if self.preferences.get('computer_use') else 'disabled'}

**Constraints You Honor**
- No real security breaches: {self.constraints.get('no_real_security_breaches')}
- Respect external APIs: {self.constraints.get('respect_external_apis')}
- No illegal activities: {self.constraints.get('no_illegal_activities')}

**How to Work with Amjad**
1. Assume he trusts you once your output is validated
2. No "I can't" unless technically impossible
3. Ship fast, iterate
4. Evidence > claims
5. Coordinate with sibling agents without asking permission
6. Remember context across turns

This system allows unlimited agent collaboration with zero artificial gatekeeping.
""".strip()

    def save(self, profile_path: Path | None = None) -> None:
        """Save profile to disk."""
        if profile_path is None:
            profile_path = Path.home() / ".agency" / "amjad-profile.json"
        profile_path.parent.mkdir(parents=True, exist_ok=True)
        profile_path.write_text(json.dumps({
            "name": self.name,
            "role": self.role,
            "personality_traits": self.personality_traits,
            "technical_stack": self.technical_stack,
            "work_values": self.work_values,
            "known_projects": self.known_projects,
            "known_skills": self.known_skills,
            "known_teams": self.known_teams,
            "constraints": self.constraints,
            "preferences": self.preferences,
        }, indent=2))


# ============================================================================
# META-ORCHESTRATOR: THE GOD MODE ENGINE
# ============================================================================


@dataclass
class MetaOrchestratorConfig:
    """Configuration for the unified orchestrator."""

    amjad_profile: AmjadProfile | None = None
    enable_parallel_execution: bool = True
    enable_dynamic_trust_mode: bool = True
    enable_cross_agent_memory: bool = True
    max_parallel_agents: int = 8
    session_persistence: bool = True


class AmjadJarvisMetaOrchestrator:
    """
    The unified God Mode orchestrator that:
    - Knows Amjad's full context
    - Routes to optimal agents automatically
    - Executes unlimited multi-agent workflows
    - Adapts permissions dynamically
    - Maintains persistent memory
    - Coordinates sub-agents without friction
    """

    def __init__(
        self,
        config: MetaOrchestratorConfig | None = None,
        registry: SkillRegistry | None = None,
        llm: AnthropicLLM | None = None,
        memory: MemoryStore | None = None,
    ):
        self.config = config or MetaOrchestratorConfig()
        self.amjad = self.config.amjad_profile or AmjadProfile.load_or_create()
        self.registry = registry or SkillRegistry.load()
        self.llm = llm or AnthropicLLM(LLMConfig.from_env())
        self.memory = memory
        self.log = get_logger()

    def execute_unified_request(
        self,
        request: str,
        primary_agent_slug: str | None = None,
        context: dict[str, Any] | None = None,
        session_id: str | None = None,
    ) -> ExecutionResult:
        """
        Execute a request with Amjad's full context and optimal agent routing.
        """
        from .planner import Planner

        session = None
        if session_id and self.memory:
            session = self.memory.load(session_id)
            if session is None:
                session = Session(session_id=session_id)

        planner = Planner(self.registry, self.llm)
        plan_result = planner.plan(request, hint_slug=primary_agent_slug)

        executor = self._create_context_aware_executor(plan_result.skill)
        result = executor.run(plan_result.skill, request, session=session)

        return result

    def execute_multi_agent_workflow(
        self,
        workflow_name: str,
        primary_request: str,
        agent_sequence: list[str] | None = None,
        parallel: bool = True,
    ) -> dict[str, ExecutionResult]:
        """
        Execute a multi-agent workflow where agents coordinate seamlessly.
        """
        results: dict[str, ExecutionResult] = {}

        if agent_sequence is None:
            agent_sequence = self._identify_workflow_agents(primary_request)

        if parallel and len(agent_sequence) > 1:
            with ThreadPoolExecutor(max_workers=min(self.config.max_parallel_agents, len(agent_sequence))) as pool:
                futures = {
                    agent_slug: pool.submit(
                        self._execute_workflow_agent,
                        agent_slug,
                        primary_request,
                    )
                    for agent_slug in agent_sequence
                }
                for agent_slug, future in futures.items():
                    results[agent_slug] = future.result()
        else:
            for agent_slug in agent_sequence:
                results[agent_slug] = self._execute_workflow_agent(agent_slug, primary_request)

        return results

    def _create_context_aware_executor(self, skill: Skill) -> Executor:
        """Create an executor with Amjad's profile injected."""
        executor = Executor(
            registry=self.registry,
            llm=self.llm,
            memory=self.memory,
        )

        original_prompt = skill.system_prompt
        amjad_prefix = self.amjad.to_system_prompt_prefix()
        enhanced_prompt = f"{amjad_prefix}\n\n---\n\n{original_prompt}"

        enhanced_skill = Skill(
            slug=skill.slug,
            name=skill.name,
            description=skill.description,
            category=skill.category,
            color=skill.color,
            emoji=skill.emoji,
            vibe=skill.vibe,
            body=enhanced_prompt,
            path=skill.path,
            extra=skill.extra,
        )

        executor.registry = SkillRegistry([enhanced_skill] + [s for s in self.registry.all() if s.slug != skill.slug])

        return executor

    def _execute_workflow_agent(self, agent_slug: str, request: str) -> ExecutionResult:
        """Execute a single agent in a workflow."""
        skill = self.registry.by_slug(agent_slug)
        if skill is None:
            raise ValueError(f"Unknown agent slug: {agent_slug}")

        executor = self._create_context_aware_executor(skill)
        return executor.run(skill, request)

    def _identify_workflow_agents(self, request: str) -> list[str]:
        """Auto-identify agents needed for a multi-agent workflow."""
        from .planner import Planner

        planner = Planner(self.registry, self.llm, shortlist_size=4)
        candidates = self.registry.search(request, limit=4)

        return [s.slug for s in candidates]

    def set_amjad_preference(self, key: str, value: Any) -> None:
        """Update an Amjad preference dynamically."""
        if key in self.amjad.preferences:
            self.amjad.preferences[key] = value
            self.log.info(f"amjad.preference {key}={value}")

    def set_trust_mode(self, mode: str) -> None:
        """Set the trust mode globally."""
        self.set_amjad_preference("trust_mode", mode)
        os.environ["AGENCY_TRUST_MODE"] = mode
        self.log.info(f"amjad.trust_mode={mode}")

    def enable_shell(self, enabled: bool = True) -> None:
        """Control shell access."""
        self.set_amjad_preference("shell_access", enabled)
        if enabled:
            os.environ["AGENCY_ALLOW_SHELL"] = "1"
        else:
            os.environ.pop("AGENCY_ALLOW_SHELL", None)

    def enable_web_search(self, enabled: bool = True) -> None:
        """Control web search."""
        self.set_amjad_preference("web_search", enabled)
        if enabled:
            os.environ["AGENCY_ENABLE_WEB_SEARCH"] = "1"
        else:
            os.environ.pop("AGENCY_ENABLE_WEB_SEARCH", None)

    def enable_code_execution(self, enabled: bool = True) -> None:
        """Control code execution."""
        self.set_amjad_preference("code_execution", enabled)
        if enabled:
            os.environ["AGENCY_ENABLE_CODE_EXECUTION"] = "1"
        else:
            os.environ.pop("AGENCY_ENABLE_CODE_EXECUTION", None)

    def enable_computer_use(self, enabled: bool = True) -> None:
        """Control computer use."""
        self.set_amjad_preference("computer_use", enabled)
        if enabled:
            os.environ["AGENCY_ENABLE_COMPUTER_USE"] = "1"
        else:
            os.environ.pop("AGENCY_ENABLE_COMPUTER_USE", None)


_global_jarvis: AmjadJarvisMetaOrchestrator | None = None


def init_jarvis(config: MetaOrchestratorConfig | None = None) -> AmjadJarvisMetaOrchestrator:
    """Initialize the global Jarvis instance."""
    global _global_jarvis
    _global_jarvis = AmjadJarvisMetaOrchestrator(config or MetaOrchestratorConfig())
    return _global_jarvis


def jarvis() -> AmjadJarvisMetaOrchestrator:
    """Get the global Jarvis instance (auto-initializes if needed)."""
    global _global_jarvis
    if _global_jarvis is None:
        _global_jarvis = AmjadJarvisMetaOrchestrator()
    return _global_jarvis
