"""
task_planner.py — Task Planner & Decision Engine
================================================
Decomposes complex multi-step tasks into executable plan steps,
schedules sub-tasks, assigns them to the right expert agents,
tracks execution progress, and adapts plans dynamically when
constraints change.

Architecture
------------
* Plan          – top-level container for a decomposed goal
* PlanStep      – single unit of work inside a Plan
* TaskPlanner   – full implementation with LLM + template-based decomposition
* MockTaskPlanner – deterministic drop-in for testing / demos
* get_task_planner() – factory that returns the right implementation
"""

from __future__ import annotations

import copy
import json
import logging
import os
import re
import threading
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logger = logging.getLogger("jarvis.task_planner")

# ---------------------------------------------------------------------------
# Built-in plan templates
# ---------------------------------------------------------------------------
PLAN_TEMPLATES: Dict[str, List[str]] = {
    "software_project": [
        "requirements",
        "design",
        "implementation",
        "testing",
        "deployment",
    ],
    "legal_contract": [
        "gather_requirements",
        "research",
        "draft",
        "review",
        "finalize",
    ],
    "medical_research": [
        "symptoms",
        "literature_review",
        "diagnosis",
        "treatment_plan",
        "followup",
    ],
    "business_strategy": [
        "market_analysis",
        "swot",
        "strategy",
        "implementation",
        "metrics",
    ],
    "creative_project": [
        "brief",
        "concept",
        "design",
        "production",
        "delivery",
    ],
}

# ---------------------------------------------------------------------------
# Step-to-agent-type mapping (extendable)
# ---------------------------------------------------------------------------
STEP_AGENT_MAP: Dict[str, str] = {
    # Software
    "requirements": "analyst",
    "design": "architect",
    "implementation": "developer",
    "testing": "qa_engineer",
    "deployment": "devops",
    "code_review": "developer",
    "refactoring": "developer",
    "documentation": "technical_writer",
    # Legal
    "gather_requirements": "legal_analyst",
    "research": "legal_researcher",
    "draft": "contract_drafter",
    "review": "legal_reviewer",
    "finalize": "legal_lead",
    # Medical
    "symptoms": "clinician",
    "literature_review": "medical_researcher",
    "diagnosis": "diagnostician",
    "treatment_plan": "treatment_specialist",
    "followup": "care_coordinator",
    # Business
    "market_analysis": "market_analyst",
    "swot": "strategist",
    "strategy": "strategist",
    "metrics": "data_analyst",
    # Creative
    "brief": "creative_lead",
    "concept": "designer",
    "production": "producer",
    "delivery": "project_manager",
    # Generic fallbacks
    "analysis": "analyst",
    "planning": "planner",
    "execution": "executor",
    "verification": "verifier",
    "reporting": "reporter",
    "research": "researcher",
    "data_collection": "data_engineer",
    "modeling": "data_scientist",
    "evaluation": "evaluator",
    "optimization": "optimizer",
    "integration": "integrator",
    "monitoring": "operations",
    "maintenance": "operations",
    "support": "support_agent",
}

# ---------------------------------------------------------------------------
# Keyword-based template detection
# ---------------------------------------------------------------------------
TEMPLATE_KEYWORDS: Dict[str, List[str]] = {
    "software_project": [
        "app", "application", "software", "code", "program",
        "system", "platform", "api", "backend", "frontend",
        "mobile", "web", "build", "develop", "implement",
        "feature", "module", "service", "microservice", "database",
    ],
    "legal_contract": [
        "contract", "agreement", "legal", "law", "clause",
        "terms", "compliance", "regulation", "policy",
        "negotiate", "liability", "jurisdiction", "nda",
    ],
    "medical_research": [
        "medical", "healthcare", "patient", "diagnosis",
        "treatment", "clinical", "symptom", "disease",
        "drug", "therapy", "health", "hospital", "medicine",
    ],
    "business_strategy": [
        "strategy", "market", "business", "competitor",
        "revenue", "growth", "swot", "forecast",
        "sales", "marketing", "product", "launch",
    ],
    "creative_project": [
        "creative", "design", "brand", "logo", "video",
        "content", "campaign", "advertisement", "art",
        "prototype", "mockup", "visual", "media",
    ],
}


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------
def _now_iso() -> str:
    """Return current UTC time as ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _generate_id(prefix: str = "plan") -> str:
    """Generate a short unique identifier."""
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _detect_template(goal: str) -> Optional[str]:
    """
    Detect which built-in template best matches *goal* by keyword
    frequency. Returns the template key or None.
    """
    goal_lower = goal.lower()
    scores: Dict[str, int] = defaultdict(int)
    for template_key, keywords in TEMPLATE_KEYWORDS.items():
        for kw in keywords:
            if kw in goal_lower:
                scores[template_key] += 1
    if not scores:
        return None
    return max(scores, key=scores.get)


def _assign_agent(step_name: str) -> str:
    """Map a step name / type to an agent type."""
    # Direct match
    if step_name in STEP_AGENT_MAP:
        return STEP_AGENT_MAP[step_name]
    # Partial match (longest prefix)
    for key in sorted(STEP_AGENT_MAP, key=len, reverse=True):
        if key in step_name or step_name in key:
            return STEP_AGENT_MAP[key]
    # Default fallback
    return "generalist"


def _estimate_step_minutes(step_name: str, template: Optional[str] = None) -> int:
    """Heuristic estimation of step duration in minutes."""
    base_estimates: Dict[str, int] = {
        "requirements": 60,
        "gather_requirements": 45,
        "design": 90,
        "implementation": 180,
        "testing": 120,
        "deployment": 60,
        "research": 90,
        "literature_review": 120,
        "draft": 120,
        "review": 60,
        "finalize": 30,
        "symptoms": 30,
        "diagnosis": 45,
        "treatment_plan": 60,
        "followup": 30,
        "market_analysis": 120,
        "swot": 60,
        "strategy": 90,
        "metrics": 45,
        "brief": 30,
        "concept": 60,
        "production": 180,
        "delivery": 30,
    }
    # Direct lookup
    if step_name in base_estimates:
        return base_estimates[step_name]
    # Partial lookup
    for key, val in base_estimates.items():
        if key in step_name or step_name in key:
            return val
    # Template-based default
    if template == "software_project":
        return 90
    elif template == "legal_contract":
        return 75
    elif template == "medical_research":
        return 50
    elif template == "business_strategy":
        return 80
    elif template == "creative_project":
        return 70
    return 60  # Generic default


def _build_step_dependencies(
    step_ids: List[str], template: Optional[str] = None
) -> Dict[str, List[str]]:
    """
    Construct a simple dependency graph where each step may depend
    on one or more earlier steps based on template ordering.
    """
    deps: Dict[str, List[str]] = {sid: [] for sid in step_ids}
    if len(step_ids) <= 1:
        return deps
    # By default, each step depends on the immediately preceding step.
    # Override with template-aware logic.
    for idx, sid in enumerate(step_ids):
        if idx == 0:
            continue
        if template == "software_project":
            # Testing can start when implementation is partially done
            if "testing" in sid and idx > 0:
                deps[sid] = [step_ids[idx - 1]]
                # Testing also depends on design knowledge
                if idx >= 2:
                    deps[sid].append(step_ids[idx - 2])
            else:
                deps[sid] = [step_ids[idx - 1]]
        elif template == "legal_contract":
            # Review depends on draft
            if "review" in sid:
                # Find draft step
                draft_candidates = [s for s in step_ids if "draft" in s]
                if draft_candidates:
                    deps[sid] = draft_candidates[:1]
                else:
                    deps[sid] = [step_ids[idx - 1]]
            else:
                deps[sid] = [step_ids[idx - 1]]
        else:
            deps[sid] = [step_ids[idx - 1]]
    return deps


def _topological_sort(
    step_ids: List[str], deps: Dict[str, List[str]]
) -> List[str]:
    """
    Return a topologically sorted ordering of step_ids.
    Raises ValueError if a cycle is detected.
    """
    in_degree: Dict[str, int] = {sid: 0 for sid in step_ids}
    adj: Dict[str, List[str]] = {sid: [] for sid in step_ids}
    for sid, dep_list in deps.items():
        for d in dep_list:
            if d in adj:
                adj[d].append(sid)
                in_degree[sid] += 1
    queue = deque([sid for sid in step_ids if in_degree[sid] == 0])
    result: List[str] = []
    while queue:
        node = queue.popleft()
        result.append(node)
        for neighbor in adj[node]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)
    if len(result) != len(step_ids):
        raise ValueError("Cycle detected in plan dependencies")
    return result


def _compute_critical_path(
    steps: List[PlanStep], plan_deps: Dict[str, List[str]]
) -> List[str]:
    """
    Identify the critical path: the longest dependency chain through
    the plan. Uses a simplified critical-path method (CPM) assuming
    each step takes its estimated_minutes.
    """
    if not steps:
        return []
    step_map = {s.step_id: s for s in steps}
    step_ids = [s.step_id for s in steps]

    # Earliest start / finish
    es: Dict[str, int] = {sid: 0 for sid in step_ids}
    ef: Dict[str, int] = {sid: 0 for sid in step_ids}
    topo = _topological_sort(step_ids, plan_deps)

    for sid in topo:
        dur = step_map[sid].estimated_minutes
        pred_finish = 0
        for pred in plan_deps.get(sid, []):
            if pred in ef and ef[pred] > pred_finish:
                pred_finish = ef[pred]
        es[sid] = pred_finish
        ef[sid] = pred_finish + dur

    max_ef = max(ef.values()) if ef else 0

    # Latest start / finish
    ls: Dict[str, int] = {sid: max_ef for sid in step_ids}
    lf: Dict[str, int] = {sid: max_ef for sid in step_ids}

    for sid in reversed(topo):
        dur = step_map[sid].estimated_minutes
        successors = [
            s for s in step_ids if sid in plan_deps.get(s, [])
        ]
        if successors:
            min_ls = min(ls.get(s, max_ef) for s in successors)
            lf[sid] = min_ls
            ls[sid] = lf[sid] - dur
        else:
            lf[sid] = max_ef
            ls[sid] = lf[sid] - dur

    # Slack = 0 => critical
    critical = []
    for sid in step_ids:
        slack = ls[sid] - es[sid]
        if slack == 0:
            critical.append(sid)

    # Preserve topological order in output
    critical_ordered = [sid for sid in topo if sid in critical]
    return critical_ordered


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------
@dataclass
class PlanStep:
    """A single executable unit of work within a Plan."""

    step_id: str
    description: str
    agent_type: str
    estimated_minutes: int
    status: str = "pending"  # pending|in_progress|completed|failed|blocked
    dependencies: List[str] = field(default_factory=list)
    result: Any = None
    actual_minutes: int = 0
    priority: int = 3  # 1 (highest) – 5 (lowest)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PlanStep":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class Plan:
    """Top-level container for a decomposed task / goal."""

    plan_id: str
    goal: str
    steps: List[PlanStep]
    estimated_duration_minutes: int
    required_agents: List[str]
    dependencies: Dict[str, List[str]]
    status: str = "draft"  # draft|active|completed|failed|paused
    created_at: str = ""
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain dictionary (JSON-friendly)."""
        return {
            "plan_id": self.plan_id,
            "goal": self.goal,
            "steps": [s.to_dict() for s in self.steps],
            "estimated_duration_minutes": self.estimated_duration_minutes,
            "required_agents": self.required_agents,
            "dependencies": self.dependencies,
            "status": self.status,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Plan":
        """Deserialize from a plain dictionary."""
        steps = [PlanStep.from_dict(s) for s in data.get("steps", [])]
        return cls(
            plan_id=data["plan_id"],
            goal=data["goal"],
            steps=steps,
            estimated_duration_minutes=data.get("estimated_duration_minutes", 0),
            required_agents=data.get("required_agents", []),
            dependencies=data.get("dependencies", {}),
            status=data.get("status", "draft"),
            created_at=data.get("created_at", _now_iso()),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            metadata=data.get("metadata", {}),
        )


# ---------------------------------------------------------------------------
# TaskPlanner
# ---------------------------------------------------------------------------
class TaskPlanner:
    """
    Decomposes complex tasks into executable steps,
    assigns them to expert agents, tracks progress,
    and adapts plans dynamically when constraints change.

    Parameters
    ----------
    orchestrator : object, optional
        A MultiAgentOrchestrator (or compatible) instance that provides
        ``dispatch(agent_type, task_description) -> result``.
    storage_path : str | None
        Directory where plan JSON snapshots are persisted.
        If *None*, plans are held only in memory.
    """

    def __init__(
        self,
        orchestrator: Any = None,
        storage_path: Optional[str] = None,
    ) -> None:
        self.orchestrator = orchestrator
        self.plans: Dict[str, Plan] = {}
        self._lock = threading.RLock()
        self._execution_threads: Dict[str, threading.Thread] = {}

        # Storage
        if storage_path:
            self.storage_path = Path(storage_path)
        else:
            self.storage_path = Path(
                os.environ.get("JARVIS_STORAGE", "/mnt/agents/output/jarvis/data")
            ) / "plans"
        self.storage_path.mkdir(parents=True, exist_ok=True)

        # Load previously persisted plans
        self._load_all_plans()

        logger.info(
            "TaskPlanner initialised (storage=%s, orchestrator=%s)",
            self.storage_path,
            "yes" if orchestrator else "no",
        )

    # -- Persistence helpers ------------------------------------------------

    def _plan_file(self, plan_id: str) -> Path:
        return self.storage_path / f"{plan_id}.json"

    def _persist(self, plan: Plan) -> None:
        """Write *plan* to disk as JSON."""
        try:
            self._plan_file(plan.plan_id).write_text(
                json.dumps(plan.to_dict(), indent=2, default=str),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.warning("Failed to persist plan %s: %s", plan.plan_id, exc)

    def _load_all_plans(self) -> None:
        """Restore plans from disk on startup."""
        if not self.storage_path.exists():
            return
        for fpath in self.storage_path.glob("*.json"):
            try:
                data = json.loads(fpath.read_text(encoding="utf-8"))
                plan = Plan.from_dict(data)
                self.plans[plan.plan_id] = plan
            except Exception as exc:
                logger.warning("Failed to load plan from %s: %s", fpath, exc)

    # -- Public API ---------------------------------------------------------

    def create_plan(self, goal: str, constraints: Optional[Dict[str, Any]] = None) -> Plan:
        """
        Decompose *goal* into a structured :class:`Plan`.

        The method uses a hybrid approach:
        1. Detect the closest built-in template by keyword matching.
        2. Expand template steps into full :class:`PlanStep` objects.
        3. Assign agent types, estimate durations, and build a
           dependency graph.
        4. If an orchestrator with an *llm_decompose* capability is
           available, augment / refine the steps.

        Parameters
        ----------
        goal : str
            High-level natural-language description of the task.
        constraints : dict, optional
            Additional constraints (budget, deadline, resource limits)
            that are stored in plan metadata.

        Returns
        -------
        Plan
        """
        with self._lock:
            plan_id = _generate_id("plan")
            template_key = _detect_template(goal)
            template_steps = (
                PLAN_TEMPLATES.get(template_key, []).copy()
                if template_key
                else []
            )

            # If no template matched, create a generic multi-step plan
            if not template_steps:
                template_steps = [
                    "analysis",
                    "planning",
                    "execution",
                    "verification",
                    "reporting",
                ]
                template_key = None

            # Build PlanStep objects
            steps: List[PlanStep] = []
            step_ids: List[str] = []
            for idx, step_name in enumerate(template_steps):
                sid = _generate_id("step")
                step_ids.append(sid)
                description = f"{step_name.replace('_', ' ').title()} for: {goal}"
                agent = _assign_agent(step_name)
                est = _estimate_step_minutes(step_name, template_key)
                steps.append(
                    PlanStep(
                        step_id=sid,
                        description=description,
                        agent_type=agent,
                        estimated_minutes=est,
                        priority=1 if idx == 0 else (2 if idx < 3 else 3),
                    )
                )

            # Dependency graph
            deps = _build_step_dependencies(step_ids, template_key)
            for sid, dep_list in deps.items():
                for st in steps:
                    if st.step_id == sid:
                        st.dependencies = dep_list[:]
                        break

            # Collect required agents (unique, preserve order)
            seen_agents: set = set()
            required_agents: List[str] = []
            for s in steps:
                if s.agent_type not in seen_agents:
                    seen_agents.add(s.agent_type)
                    required_agents.append(s.agent_type)

            # Total duration estimate (parallel-aware via critical path)
            critical = _compute_critical_path(steps, deps)
            critical_duration = sum(
                next(s.estimated_minutes for s in steps if s.step_id == cid)
                for cid in critical
            ) if critical else sum(s.estimated_minutes for s in steps)

            plan = Plan(
                plan_id=plan_id,
                goal=goal,
                steps=steps,
                estimated_duration_minutes=critical_duration,
                required_agents=required_agents,
                dependencies=deps,
                status="draft",
                created_at=_now_iso(),
                metadata={
                    "template": template_key,
                    "constraints": constraints or {},
                    "version": "1.0",
                },
            )

            self.plans[plan_id] = plan
            self._persist(plan)
            logger.info(
                "Created plan %s with %d steps (template=%s)",
                plan_id,
                len(steps),
                template_key,
            )
            return plan

    def execute_plan(self, plan_id: str) -> Dict[str, Any]:
        """
        Execute *plan_id* step by step.

        Steps that have no unresolved dependencies are started in
        parallel.  The method blocks until all steps finish (or the
        plan is paused / cancelled).

        Returns
        -------
        dict
            Summary with ``status``, ``completed_steps``,
            ``failed_steps``, ``total_minutes``.
        """
        with self._lock:
            plan = self._get_plan(plan_id)
            if plan.status == "active":
                logger.warning("Plan %s is already running", plan_id)
                return {"status": "already_running", "plan_id": plan_id}
            if plan.status in ("completed", "cancelled"):
                return {"status": "terminal_state", "plan_id": plan_id}

            plan.status = "active"
            plan.started_at = _now_iso()
            self._persist(plan)

        logger.info("Executing plan %s", plan_id)

        # Work-loop: repeatedly find ready steps and execute them
        completed = 0
        failed = 0
        total_actual = 0

        while True:
            with self._lock:
                plan = self._get_plan(plan_id)
                if plan.status in ("paused", "cancelled"):
                    logger.info("Plan %s %s", plan_id, plan.status)
                    break

                ready_steps = self._find_ready_steps(plan)
                if not ready_steps and self._all_terminal(plan):
                    break

            if not ready_steps:
                time.sleep(0.1)
                continue

            # Execute ready steps (simple sequential loop for safety;
            # can be extended to true ThreadPoolExecutor parallelism)
            for step in ready_steps:
                with self._lock:
                    if plan.status in ("paused", "cancelled"):
                        break
                    step.status = "in_progress"
                    self._persist(plan)

                result = self._execute_step(plan_id, step)

                with self._lock:
                    plan = self._get_plan(plan_id)
                    # Re-fetch the step object from the plan
                    for st in plan.steps:
                        if st.step_id == step.step_id:
                            st.actual_minutes = result.get("duration_min", 0)
                            total_actual += st.actual_minutes
                            if result.get("success"):
                                st.status = "completed"
                                st.result = result.get("output")
                                completed += 1
                            else:
                                st.status = "failed"
                                st.result = result.get("error", "unknown error")
                                failed += 1
                            break
                    self._persist(plan)

        # Finalise
        with self._lock:
            plan = self._get_plan(plan_id)
            if plan.status == "active":
                plan.status = "completed" if failed == 0 else "failed"
                plan.completed_at = _now_iso()
            summary = {
                "plan_id": plan_id,
                "status": plan.status,
                "completed_steps": completed,
                "failed_steps": failed,
                "total_steps": len(plan.steps),
                "total_actual_minutes": total_actual,
            }
            self._persist(plan)

        logger.info("Plan %s finished: %s", plan_id, summary)
        return summary

    def get_plan_status(self, plan_id: str) -> Dict[str, Any]:
        """
        Return a detailed status snapshot of *plan_id* including every
        step's current state.
        """
        with self._lock:
            plan = self._get_plan(plan_id)
            return {
                "plan_id": plan.plan_id,
                "goal": plan.goal,
                "status": plan.status,
                "created_at": plan.created_at,
                "started_at": plan.started_at,
                "completed_at": plan.completed_at,
                "estimated_duration_minutes": plan.estimated_duration_minutes,
                "required_agents": plan.required_agents,
                "step_summary": [
                    {
                        "step_id": s.step_id,
                        "description": s.description,
                        "agent_type": s.agent_type,
                        "status": s.status,
                        "priority": s.priority,
                        "estimated_minutes": s.estimated_minutes,
                        "actual_minutes": s.actual_minutes,
                        "dependencies": s.dependencies,
                    }
                    for s in plan.steps
                ],
                "dependencies": plan.dependencies,
                "metadata": plan.metadata,
            }

    def adapt_plan(self, plan_id: str, new_constraint: str) -> Plan:
        """
        Adjust an existing plan when a new constraint emerges.

        The method:
        1. Records the constraint in metadata.
        2. Re-orders steps by priority if the constraint is urgent.
        3. Reassigns agents if the constraint implies a skill change.
        4. Recomputes the duration estimate.

        Parameters
        ----------
        plan_id : str
        new_constraint : str
            Natural-language description of the new constraint.

        Returns
        -------
        Plan
            The mutated (and persisted) plan.
        """
        with self._lock:
            plan = self._get_plan(plan_id)
            plan.metadata.setdefault("adaptations", []).append(
                {"constraint": new_constraint, "at": _now_iso()}
            )

            urgency = self._classify_urgency(new_constraint)

            # Reorder: bump high-priority steps earlier when urgent
            if urgency >= 4:
                plan.steps.sort(key=lambda s: (s.priority, s.estimated_minutes))
                # Rebuild step_ids in new order
                new_step_ids = [s.step_id for s in plan.steps]
                plan.dependencies = _build_step_dependencies(
                    new_step_ids, plan.metadata.get("template")
                )
                for st in plan.steps:
                    st.dependencies = plan.dependencies.get(st.step_id, [])

            # Reassign agents based on constraint keywords
            for st in plan.steps:
                reassigned = self._maybe_reassign(st, new_constraint)
                if reassigned:
                    st.agent_type = reassigned

            # Recompute required agents
            seen: set = set()
            plan.required_agents = []
            for s in plan.steps:
                if s.agent_type not in seen:
                    seen.add(s.agent_type)
                    plan.required_agents.append(s.agent_type)

            # Recompute duration estimate
            plan.estimated_duration_minutes = self.estimate_total_duration(
                plan_id
            )

            self._persist(plan)
            logger.info(
                "Adapted plan %s for constraint: %s", plan_id, new_constraint
            )
            return plan

    def get_critical_path(self, plan_id: str) -> List[str]:
        """
        Return the list of step IDs on the critical path.
        These steps dictate the minimum possible plan duration.
        """
        with self._lock:
            plan = self._get_plan(plan_id)
            return _compute_critical_path(plan.steps, plan.dependencies)

    def estimate_total_duration(self, plan_id: str) -> int:
        """
        Estimate total plan duration in minutes, accounting for
        parallel execution via critical-path analysis.
        """
        with self._lock:
            plan = self._get_plan(plan_id)
            critical = _compute_critical_path(plan.steps, plan.dependencies)
            if not critical:
                return sum(s.estimated_minutes for s in plan.steps)
            return sum(
                next(s.estimated_minutes for s in plan.steps if s.step_id == cid)
                for cid in critical
            )

    def list_active_plans(self) -> List[Dict[str, Any]]:
        """Return metadata for every plan with status ``active``."""
        with self._lock:
            return [
                {
                    "plan_id": p.plan_id,
                    "goal": p.goal,
                    "status": p.status,
                    "started_at": p.started_at,
                    "progress_pct": self._progress_pct(p),
                }
                for p in self.plans.values()
                if p.status == "active"
            ]

    def pause_plan(self, plan_id: str) -> None:
        """Transition plan to ``paused``. Running steps are allowed to finish."""
        with self._lock:
            plan = self._get_plan(plan_id)
            if plan.status == "active":
                plan.status = "paused"
                self._persist(plan)
                logger.info("Plan %s paused", plan_id)

    def resume_plan(self, plan_id: str) -> None:
        """Transition a ``paused`` plan back to ``active``."""
        with self._lock:
            plan = self._get_plan(plan_id)
            if plan.status == "paused":
                plan.status = "active"
                self._persist(plan)
                logger.info("Plan %s resumed", plan_id)

    def cancel_plan(self, plan_id: str) -> None:
        """Transition plan to ``cancelled``. Irreversible."""
        with self._lock:
            plan = self._get_plan(plan_id)
            if plan.status not in ("completed", "cancelled"):
                plan.status = "cancelled"
                plan.completed_at = _now_iso()
                # Mark in-progress steps as failed
                for st in plan.steps:
                    if st.status == "in_progress":
                        st.status = "failed"
                        st.result = "cancelled"
                self._persist(plan)
                logger.info("Plan %s cancelled", plan_id)

    # -- Internal helpers ---------------------------------------------------

    def _get_plan(self, plan_id: str) -> Plan:
        if plan_id not in self.plans:
            raise KeyError(f"Plan not found: {plan_id}")
        return self.plans[plan_id]

    def _find_ready_steps(self, plan: Plan) -> List[PlanStep]:
        """Return steps whose dependencies are all completed."""
        completed_ids = {
            s.step_id for s in plan.steps if s.status == "completed"
        }
        ready: List[PlanStep] = []
        for st in plan.steps:
            if st.status not in ("pending", "blocked"):
                continue
            unresolved = [d for d in st.dependencies if d not in completed_ids]
            if not unresolved:
                ready.append(st)
            else:
                # Update status to blocked if it was pending
                if st.status == "pending":
                    st.status = "blocked"
        return ready

    def _all_terminal(self, plan: Plan) -> bool:
        """Check whether every step is in a terminal state."""
        terminal = {"completed", "failed"}
        return all(s.status in terminal for s in plan.steps)

    def _execute_step(
        self, plan_id: str, step: PlanStep
    ) -> Dict[str, Any]:
        """
        Execute a single step.

        If an orchestrator is attached and exposes ``dispatch``, it is
        used; otherwise a deterministic simulation is performed.
        """
        start_ts = time.time()
        logger.info(
            "[Plan %s] Step %s -> %s (%s)",
            plan_id,
            step.step_id,
            step.agent_type,
            step.description[:60],
        )

        try:
            if self.orchestrator and hasattr(
                self.orchestrator, "dispatch"
            ):
                output = self.orchestrator.dispatch(
                    agent_type=step.agent_type,
                    task_description=step.description,
                )
                success = True
                error = None
            else:
                # Simulation mode
                time.sleep(0.01)  # tiny delay to mimic work
                output = (
                    f"Simulated result for '{step.description}' "
                    f"by {step.agent_type}"
                )
                success = True
                error = None
        except Exception as exc:
            success = False
            output = None
            error = str(exc)
            logger.exception("Step %s failed", step.step_id)

        elapsed = int((time.time() - start_ts) / 60) or 1
        return {
            "success": success,
            "output": output,
            "error": error,
            "duration_min": elapsed,
        }

    @staticmethod
    def _classify_urgency(constraint: str) -> int:
        """
        Heuristic urgency score (1-5) based on keyword matching in the
        constraint text.
        """
        c = constraint.lower()
        urgent_kws = [
            "asap", "urgent", "immediately", "critical", "deadline",
            "emergency", "blocker", "now", "today",
        ]
        score = 1
        for kw in urgent_kws:
            if kw in c:
                score += 2
        return min(score, 5)

    @staticmethod
    def _maybe_reassign(step: PlanStep, constraint: str) -> Optional[str]:
        """
        Return a new agent type if the constraint implies the step
        should be handled by a different expert.
        """
        c = constraint.lower()
        # Security-related constraint -> security expert
        if any(k in c for k in ("security", "secure", "vulnerability", "penetration")):
            if step.agent_type in ("developer", "architect"):
                return "security_engineer"
        # Performance constraint -> performance specialist
        if any(k in c for k in ("performance", "speed", "latency", "optimize")):
            if step.agent_type in ("developer", "architect"):
                return "performance_engineer"
        # UX constraint -> UX designer
        if any(k in c for k in ("ux", "user experience", "usability", "accessibility")):
            if step.agent_type in ("designer", "developer"):
                return "ux_designer"
        # Compliance constraint -> compliance officer
        if any(k in c for k in ("compliance", "regulatory", "gdpr", "hipaa")):
            if step.agent_type in ("developer", "analyst"):
                return "compliance_officer"
        return None

    @staticmethod
    def _progress_pct(plan: Plan) -> float:
        if not plan.steps:
            return 100.0
        terminal = {"completed", "failed"}
        done = sum(1 for s in plan.steps if s.status in terminal)
        return round(done / len(plan.steps) * 100, 1)

    # -- Bulk helpers -------------------------------------------------------

    def delete_plan(self, plan_id: str) -> None:
        """Remove a plan from memory and disk."""
        with self._lock:
            if plan_id in self.plans:
                del self.plans[plan_id]
            pf = self._plan_file(plan_id)
            if pf.exists():
                pf.unlink()
            logger.info("Deleted plan %s", plan_id)

    def list_all_plans(self) -> List[Dict[str, Any]]:
        """Return a lightweight summary of every known plan."""
        with self._lock:
            return [
                {
                    "plan_id": p.plan_id,
                    "goal": p.goal,
                    "status": p.status,
                    "step_count": len(p.steps),
                    "estimated_duration_minutes": p.estimated_duration_minutes,
                    "created_at": p.created_at,
                }
                for p in self.plans.values()
            ]

    def clone_plan(self, plan_id: str, new_goal: Optional[str] = None) -> Plan:
        """Create a deep copy of an existing plan with a new ID."""
        with self._lock:
            original = self._get_plan(plan_id)
            data = original.to_dict()
            data["plan_id"] = _generate_id("plan")
            data["goal"] = new_goal or original.goal
            data["status"] = "draft"
            data["created_at"] = _now_iso()
            data["started_at"] = None
            data["completed_at"] = None
            # Reset step states
            for s in data["steps"]:
                s["status"] = "pending"
                s["result"] = None
                s["actual_minutes"] = 0
            cloned = Plan.from_dict(data)
            self.plans[cloned.plan_id] = cloned
            self._persist(cloned)
            logger.info(
                "Cloned plan %s -> %s", plan_id, cloned.plan_id
            )
            return cloned


# ---------------------------------------------------------------------------
# MockTaskPlanner — deterministic drop-in
# ---------------------------------------------------------------------------
class MockTaskPlanner(TaskPlanner):
    """
    A deterministic subclass of :class:`TaskPlanner` that never calls
    an external orchestrator and uses fixed durations / results.
    Useful for unit tests and demos.
    """

    def __init__(self, storage_path: Optional[str] = None) -> None:
        # Explicitly skip TaskPlanner.__init__ storage logic so we stay pure
        self.plans: Dict[str, Plan] = {}
        self._lock = threading.RLock()
        self.orchestrator = None
        self.storage_path = None  # Never persist in mock mode

    def create_plan(self, goal: str, constraints: Optional[Dict[str, Any]] = None) -> Plan:
        """Create a deterministic 5-step plan."""
        with self._lock:
            plan_id = f"mock_plan_{len(self.plans) + 1:03d}"
            template_key = _detect_template(goal)
            step_names = (
                PLAN_TEMPLATES.get(template_key, []).copy()
                if template_key
                else ["analysis", "planning", "execution", "verification", "reporting"]
            )

            steps: List[PlanStep] = []
            step_ids: List[str] = []
            for idx, name in enumerate(step_names):
                sid = f"mock_step_{plan_id}_{idx + 1}"
                step_ids.append(sid)
                steps.append(
                    PlanStep(
                        step_id=sid,
                        description=f"{name.replace('_', ' ').title()} for: {goal}",
                        agent_type=_assign_agent(name),
                        estimated_minutes=10 * (idx + 1),  # deterministic: 10,20,30...
                        priority=idx + 1,
                    )
                )

            deps = _build_step_dependencies(step_ids, template_key)
            for st in steps:
                st.dependencies = deps.get(st.step_id, [])

            required = []
            seen: set = set()
            for s in steps:
                if s.agent_type not in seen:
                    seen.add(s.agent_type)
                    required.append(s.agent_type)

            critical = _compute_critical_path(steps, deps)
            critical_dur = sum(
                next(s.estimated_minutes for s in steps if s.step_id == cid)
                for cid in critical
            ) if critical else sum(s.estimated_minutes for s in steps)

            plan = Plan(
                plan_id=plan_id,
                goal=goal,
                steps=steps,
                estimated_duration_minutes=critical_dur,
                required_agents=required,
                dependencies=deps,
                status="draft",
                created_at="2024-01-01T00:00:00+00:00",  # fixed for determinism
                metadata={"template": template_key, "mode": "mock"},
            )
            self.plans[plan_id] = plan
            return plan

    def execute_plan(self, plan_id: str) -> Dict[str, Any]:
        """Simulate execution with deterministic outcomes."""
        with self._lock:
            plan = self._get_plan(plan_id)
            plan.status = "active"
            plan.started_at = _now_iso()

            for st in plan.steps:
                st.status = "in_progress"
                st.result = f"mock_result:{st.step_id}"
                st.actual_minutes = st.estimated_minutes
                st.status = "completed"

            plan.status = "completed"
            plan.completed_at = _now_iso()

            return {
                "plan_id": plan_id,
                "status": "completed",
                "completed_steps": len(plan.steps),
                "failed_steps": 0,
                "total_steps": len(plan.steps),
                "total_actual_minutes": sum(s.actual_minutes for s in plan.steps),
            }


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------
_TASK_PLANNER_SINGLETON: Optional[TaskPlanner] = None


def get_task_planner(
    orchestrator: Any = None,
    mock: bool = False,
    storage_path: Optional[str] = None,
) -> TaskPlanner:
    """
    Factory that returns a :class:`TaskPlanner` (or
    :class:`MockTaskPlanner` when *mock* is ``True``).

    Without arguments the first call creates the singleton instance;
    subsequent calls return the cached instance.
    """
    global _TASK_PLANNER_SINGLETON
    if mock:
        return MockTaskPlanner(storage_path=storage_path)
    if _TASK_PLANNER_SINGLETON is None:
        _TASK_PLANNER_SINGLETON = TaskPlanner(
            orchestrator=orchestrator,
            storage_path=storage_path,
        )
    return _TASK_PLANNER_SINGLETON


def reset_task_planner() -> None:
    """Clear the singleton (mostly useful in tests)."""
    global _TASK_PLANNER_SINGLETON
    _TASK_PLANNER_SINGLETON = None


# ---------------------------------------------------------------------------
# Quick self-test when run as ``python task_planner.py``
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    # Demo 1: Default planner (no orchestrator)
    planner = get_task_planner()
    plan = planner.create_plan("Build a mobile app for healthcare")
    print(f"Plan: {len(plan.steps)} steps")
    print("Agents:", plan.required_agents)
    print("Template:", plan.metadata.get("template"))
    print("Estimated duration (min):", plan.estimated_duration_minutes)

    # Show dependency graph
    print("\nDependencies:")
    for sid, deps in plan.dependencies.items():
        desc = next(s.description for s in plan.steps if s.step_id == sid)
        print(f"  {desc[:50]:50} <- {deps}")

    # Critical path
    cp = planner.get_critical_path(plan.plan_id)
    print(f"\nCritical path ({len(cp)} steps):")
    for cid in cp:
        desc = next(s.description for s in plan.steps if s.step_id == cid)
        print(f"  - {desc}")

    # Demo 2: Mock planner
    mock = get_task_planner(mock=True)
    mplan = mock.create_plan("Draft a legal contract for software licensing")
    result = mock.execute_plan(mplan.plan_id)
    print(f"\nMock execution: {result}")

    # Demo 3: Adapt plan
    adapted = planner.adapt_plan(plan.plan_id, "Add security hardening ASAP")
    print(f"\nAdapted plan agents: {adapted.required_agents}")
    print(f"Adapted estimated duration: {adapted.estimated_duration_minutes} min")

    # Cleanup
    planner.delete_plan(plan.plan_id)
    reset_task_planner()
    print("\nAll demos completed successfully.")
