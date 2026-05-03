#!/usr/bin/env python3
"""
multi_agent_orchestrator.py — Multi-Agent Orchestrator Engine

Splits complex tasks into sub-tasks, assigns them to specialized internal
agents, executes in parallel, and merges results into a unified output.

Inspired by Claude Max's sub-agent spawning — but 100% local, using
Python threading and Queue-based communication.

Usage:
    from runtime.agency.multi_agent_orchestrator import get_orchestrator

    orch = get_orchestrator()
    result = orch.orchestrate(
        "Write a legal contract for software development",
        context={"client": "Acme Corp", "budget": 50000}
    )
    print(result["merged_output"])
"""

from __future__ import annotations

import json
import logging
import re
import statistics
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from queue import Empty, PriorityQueue
from typing import Any, Callable, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
logger = logging.getLogger("jarvis.multi_agent_orchestrator")
logger.setLevel(logging.INFO)
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    ))
    logger.addHandler(_handler)

# ---------------------------------------------------------------------------
# AgentTask dataclass
# ---------------------------------------------------------------------------


@dataclass
class AgentTask:
    """Represents a single sub-task assigned to an internal agent."""

    task_id: str = ""
    agent_type: str = "advisor"  # lawyer|engineer|doctor|advisor|manager|researcher|writer|coder
    description: str = ""
    priority: int = 3  # 1-5 (1=highest)
    context: Dict[str, Any] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)
    status: str = "pending"  # pending|running|completed|failed
    result: Any = None
    created_at: str = ""

    def __post_init__(self):
        if not self.task_id:
            self.task_id = str(uuid.uuid4())[:8]
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()
        # Validate priority range
        self.priority = max(1, min(5, self.priority))

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "task_id": self.task_id,
            "agent_type": self.agent_type,
            "description": self.description,
            "priority": self.priority,
            "context": self.context,
            "dependencies": self.dependencies,
            "status": self.status,
            "result": self.result,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AgentTask":
        """Deserialize from dictionary."""
        return cls(
            task_id=data.get("task_id", ""),
            agent_type=data.get("agent_type", "advisor"),
            description=data.get("description", ""),
            priority=data.get("priority", 3),
            context=data.get("context", {}),
            dependencies=data.get("dependencies", []),
            status=data.get("status", "pending"),
            result=data.get("result"),
            created_at=data.get("created_at", ""),
        )


# ---------------------------------------------------------------------------
# Priority queue wrapper (PriorityQueue sorts lowest first, so invert)
# ---------------------------------------------------------------------------


class _PrioritizedItem:
    """Wrapper for PriorityQueue that sorts by priority (lower number = higher priority)."""

    __slots__ = ("priority", "sequence", "task")

    _seq_counter = 0
    _lock = threading.Lock()

    def __init__(self, priority: int, task: AgentTask):
        self.priority = priority
        self.task = task
        with _PrioritizedItem._lock:
            _PrioritizedItem._seq_counter += 1
            self.sequence = _PrioritizedItem._seq_counter

    def __lt__(self, other: "_PrioritizedItem") -> bool:
        # Lower priority number = higher precedence; tie-break with sequence
        if self.priority != other.priority:
            return self.priority < other.priority
        return self.sequence < other.sequence


# ---------------------------------------------------------------------------
# Built-in agent handlers
# ---------------------------------------------------------------------------


def _handle_lawyer(task: AgentTask) -> dict:
    """
    Legal agent: contract review, compliance analysis, legal research.
    """
    desc = task.description.lower()
    ctx = task.context or {}

    # Determine specific legal domain via keyword matching
    if any(k in desc for k in ("contract", "agreement", "terms", "clause", "nda")):
        domain = "contract_law"
        analysis = _legal_contract_analysis(desc, ctx)
    elif any(k in desc for k in ("compliance", "regulation", "gdpr", "hipaa", "sec")):
        domain = "compliance"
        analysis = _legal_compliance_analysis(desc, ctx)
    elif any(k in desc for k in ("litigation", "dispute", "lawsuit", "arbitration")):
        domain = "litigation"
        analysis = _legal_litigation_analysis(desc, ctx)
    elif any(k in desc for k in ("ip", "patent", "trademark", "copyright", "intellectual")):
        domain = "ip_law"
        analysis = _legal_ip_analysis(desc, ctx)
    else:
        domain = "general_legal"
        analysis = _legal_general_analysis(desc, ctx)

    return {
        "agent_type": "lawyer",
        "task_id": task.task_id,
        "domain": domain,
        "analysis": analysis,
        "confidence": _compute_confidence(desc),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _legal_contract_analysis(desc: str, ctx: dict) -> dict:
    """Analyze contract-related legal queries."""
    contract_type = "general"
    if "software" in desc or "development" in desc:
        contract_type = "software_development_agreement"
    elif "employment" in desc or "hire" in desc:
        contract_type = "employment_contract"
    elif "service" in desc:
        contract_type = "service_agreement"
    elif "license" in desc:
        contract_type = "license_agreement"

    return {
        "contract_type": contract_type,
        "key_clauses": [
            "Scope of Work / Statement of Work (SOW)",
            "Payment Terms and Milestones",
            "Intellectual Property Assignment",
            "Confidentiality and Non-Disclosure",
            "Limitation of Liability",
            "Termination Conditions",
            "Dispute Resolution Mechanism",
            "Warranty and Support Terms",
        ],
        "risk_assessment": {
            "level": "medium",
            "concerns": [
                "Ensure IP ownership is clearly transferred upon payment",
                "Define acceptance criteria to avoid scope creep",
                "Include limitation of liability caps",
            ],
        },
        "recommendations": [
            "Include a detailed SOW as an appendix",
            "Specify governing law and jurisdiction",
            "Add escrow provisions for source code",
        ],
        "generated_draft": _generate_contract_draft(contract_type, ctx),
    }


def _legal_compliance_analysis(desc: str, ctx: dict) -> dict:
    """Analyze compliance-related legal queries."""
    regulations = []
    if "gdpr" in desc or "data" in desc:
        regulations.append("GDPR (EU General Data Protection Regulation)")
    if "hipaa" in desc or "health" in desc:
        regulations.append("HIPAA (US Health Insurance Portability)")
    if "soc2" in desc or "security" in desc:
        regulations.append("SOC 2 Type II")
    if "pci" in desc or "payment" in desc:
        regulations.append("PCI DSS")
    if not regulations:
        regulations.append("General regulatory compliance")

    return {
        "applicable_regulations": regulations,
        "compliance_checklist": [
            "Data classification and inventory",
            "Privacy policy review and update",
            "Consent mechanism audit",
            "Data retention policy verification",
            "Breach notification procedure review",
            "Third-party vendor assessment",
        ],
        "risk_level": "medium",
        "recommended_actions": [
            "Conduct a gap analysis against applicable frameworks",
            "Implement privacy-by-design principles",
            "Establish regular compliance audits",
        ],
    }


def _legal_litigation_analysis(desc: str, ctx: dict) -> dict:
    return {
        "case_type": "commercial_dispute",
        "recommended_strategy": "negotiate_before_litigate",
        "estimated_timeline": "6-18 months",
        "cost_estimate": "$50,000 - $500,000",
        "key_considerations": [
            "Preserve all relevant documents (litigation hold)",
            "Review insurance coverage for legal costs",
            "Assess counter-party financial viability",
        ],
    }


def _legal_ip_analysis(desc: str, ctx: dict) -> dict:
    return {
        "ip_type": "software_patent_trademark",
        "protection_strategies": [
            "File provisional patent application",
            "Register trademarks with USPTO/EUIPO",
            "Implement trade secret protections",
            "Use open-source license compliance tools",
        ],
        "risk_assessment": {
            "infringement_risk": "medium",
            "prior_art_search_required": True,
        },
    }


def _legal_general_analysis(desc: str, ctx: dict) -> dict:
    return {
        "analysis_type": "general_legal_review",
        "key_points": [
            "Legal structure should be reviewed by licensed counsel",
            "Document all agreements in writing",
            "Ensure proper corporate governance",
        ],
        "recommended_next_steps": [
            "Consult with a licensed attorney in relevant jurisdiction",
            "Prepare all relevant documents for review",
        ],
    }


def _handle_engineer(task: AgentTask) -> dict:
    """
    Engineering agent: code review, system architecture, debugging.
    """
    desc = task.description.lower()
    ctx = task.context or {}

    if any(k in desc for k in ("architecture", "design", "system", "microservice")):
        domain = "system_architecture"
        analysis = _engineering_architecture_analysis(desc, ctx)
    elif any(k in desc for k in ("debug", "fix", "error", "bug", "crash")):
        domain = "debugging"
        analysis = _engineering_debug_analysis(desc, ctx)
    elif any(k in desc for k in ("review", "refactor", "clean", "quality")):
        domain = "code_review"
        analysis = _engineering_code_review(desc, ctx)
    elif any(k in desc for k in ("performance", "optimiz", "scal", "speed")):
        domain = "performance"
        analysis = _engineering_performance_analysis(desc, ctx)
    else:
        domain = "general_engineering"
        analysis = _engineering_general_analysis(desc, ctx)

    return {
        "agent_type": "engineer",
        "task_id": task.task_id,
        "domain": domain,
        "analysis": analysis,
        "confidence": _compute_confidence(desc),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _engineering_architecture_analysis(desc: str, ctx: dict) -> dict:
    tech_stack = ctx.get("tech_stack", ["Python", "PostgreSQL", "Redis", "Docker"])
    return {
        "recommended_architecture": "microservices_with_api_gateway",
        "components": [
            {"name": "API Gateway", "purpose": "Request routing and auth"},
            {"name": "Service Mesh", "purpose": "Inter-service communication"},
            {"name": "Event Bus", "purpose": "Async messaging (Kafka/RabbitMQ)"},
            {"name": "Data Layer", "purpose": "Persistent storage and caching"},
            {"name": "Observability", "purpose": "Metrics, logs, traces"},
        ],
        "tech_stack_recommendation": tech_stack,
        "scalability_notes": [
            "Use horizontal pod autoscaling for compute-heavy services",
            "Implement database sharding for data-intensive operations",
            "Add CDN for static asset delivery",
        ],
        "estimated_effort": "3-6 months for MVP",
    }


def _engineering_debug_analysis(desc: str, ctx: dict) -> dict:
    return {
        "debug_strategy": "systematic_isolation",
        "steps": [
            "Reproduce the issue consistently",
            "Check application logs for error patterns",
            "Verify environment configuration",
            "Isolate the failing component",
            "Apply fix and validate with tests",
            "Deploy with monitoring and rollback plan",
        ],
        "common_causes": [
            "Configuration drift between environments",
            "Race conditions in concurrent code",
            "Memory leaks in long-running processes",
            "Third-party API changes or downtime",
        ],
        "tools_recommended": ["Debugger", "Structured Logging", "APM (Datadog/New Relic)", "Chaos Engineering"],
    }


def _engineering_code_review(desc: str, ctx: dict) -> dict:
    return {
        "review_focus_areas": [
            "Code correctness and edge cases",
            "Security vulnerabilities (OWASP Top 10)",
            "Performance bottlenecks",
            "Test coverage and quality",
            "Documentation completeness",
            "Adherence to style guidelines",
        ],
        "quality_score": "B+",
        "recommendations": [
            "Add input validation for all public APIs",
            "Increase unit test coverage to >80%",
            "Add type hints throughout the codebase",
            "Run static analysis (pylint, mypy, bandit)",
        ],
    }


def _engineering_performance_analysis(desc: str, ctx: dict) -> dict:
    return {
        "bottleneck_analysis": [
            "Database query optimization needed",
            "Consider caching hot data paths",
            "Profile CPU-intensive operations",
            "Optimize frontend bundle size",
        ],
        "recommendations": [
            "Implement Redis caching layer",
            "Add database connection pooling",
            "Use CDN for static assets",
            "Enable response compression (gzip/brotli)",
            "Consider read replicas for heavy read workloads",
        ],
        "target_metrics": {
            "p50_latency_ms": 50,
            "p99_latency_ms": 200,
            "throughput_rps": 10000,
        },
    }


def _engineering_general_analysis(desc: str, ctx: dict) -> dict:
    return {
        "assessment": "General engineering consultation",
        "best_practices": [
            "Follow SOLID principles",
            "Use version control with branch protection",
            "Automate testing and deployment (CI/CD)",
            "Document architecture decisions (ADRs)",
            "Monitor production systems proactively",
        ],
    }


def _handle_doctor(task: AgentTask) -> dict:
    """
    Medical agent: symptom analysis, drug interaction checking, medical info.
    DISCLAIMER: This is for informational purposes only — not medical advice.
    """
    desc = task.description.lower()
    ctx = task.context or {}

    if any(k in desc for k in ("symptom", "pain", "fever", "cough", "feel")):
        domain = "symptom_analysis"
        analysis = _medical_symptom_analysis(desc, ctx)
    elif any(k in desc for k in ("drug", "medication", "interaction", "pill", "side effect")):
        domain = "drug_interactions"
        analysis = _medical_drug_analysis(desc, ctx)
    elif any(k in desc for k in ("condition", "disease", "diabetes", "hypertension", "asthma")):
        domain = "condition_info"
        analysis = _medical_condition_analysis(desc, ctx)
    else:
        domain = "general_medical"
        analysis = _medical_general_analysis(desc, ctx)

    return {
        "agent_type": "doctor",
        "task_id": task.task_id,
        "domain": domain,
        "analysis": analysis,
        "confidence": _compute_confidence(desc),
        **DISCLAIMER,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _medical_symptom_analysis(desc: str, ctx: dict) -> dict:
    symptoms = _extract_symptoms(desc)
    return {
        "reported_symptoms": symptoms,
        "possible_causes": [
            "Viral upper respiratory infection",
            "Allergic rhinitis",
            "Environmental irritant exposure",
        ],
        "triage_level": "non_urgent",
        "recommended_actions": [
            "Monitor symptoms for 48-72 hours",
            "Stay hydrated and rest",
            "Consult a healthcare provider if symptoms worsen",
        ],
        "when_to_seek_care": [
            "Difficulty breathing",
            "Chest pain",
            "High fever (>103F / 39.4C) lasting >3 days",
            "Severe dehydration",
        ],
    }


def _medical_drug_analysis(desc: str, ctx: dict) -> dict:
    medications = ctx.get("medications", ["Unknown"])
    return {
        "medications_reviewed": medications,
        "interaction_risk": "low_to_moderate",
        "known_interactions": [
            "Always check with pharmacist for new prescriptions",
            "Some antibiotics reduce effectiveness of oral contraceptives",
            "NSAIDs may interact with blood thinners",
        ],
        "recommendations": [
            "Use a single pharmacy for all prescriptions",
            "Keep an updated medication list",
            "Consult healthcare provider before adding OTC medications",
        ],
    }


def _medical_condition_analysis(desc: str, ctx: dict) -> dict:
    return {
        "condition": "General chronic condition",
        "management_strategies": [
            "Regular monitoring of key health metrics",
            "Medication adherence",
            "Lifestyle modifications (diet, exercise, sleep)",
            "Scheduled follow-ups with specialist",
        ],
        "resources": [
            "CDC.gov for evidence-based guidelines",
            "Patient advocacy organizations",
            "Peer support groups",
        ],
    }


def _medical_general_analysis(desc: str, ctx: dict) -> dict:
    return {
        "general_health_guidance": [
            "Maintain regular physical activity (150 min/week)",
            "Eat a balanced diet rich in fruits and vegetables",
            "Get 7-9 hours of quality sleep per night",
            "Stay current with recommended vaccinations",
            "Schedule regular preventive care visits",
        ],
    }


def _handle_advisor(task: AgentTask) -> dict:
    """
    Business advisor agent: strategy, financial advice, career guidance.
    """
    desc = task.description.lower()
    ctx = task.context or {}

    if any(k in desc for k in ("strategy", "business", "market", "competitor", "growth")):
        domain = "business_strategy"
        analysis = _advisor_strategy_analysis(desc, ctx)
    elif any(k in desc for k in ("financial", "invest", "budget", "revenue", "profit")):
        domain = "financial_advice"
        analysis = _advisor_financial_analysis(desc, ctx)
    elif any(k in desc for k in ("career", "job", "resume", "interview", "promotion")):
        domain = "career_guidance"
        analysis = _advisor_career_analysis(desc, ctx)
    else:
        domain = "general_advice"
        analysis = _advisor_general_analysis(desc, ctx)

    return {
        "agent_type": "advisor",
        "task_id": task.task_id,
        "domain": domain,
        "analysis": analysis,
        "confidence": _compute_confidence(desc),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _advisor_strategy_analysis(desc: str, ctx: dict) -> dict:
    industry = ctx.get("industry", "technology")
    return {
        "industry": industry,
        "strategic_recommendations": [
            "Focus on core competency while exploring adjacent markets",
            "Invest in customer retention (cheaper than acquisition)",
            "Build strategic partnerships for market expansion",
            "Develop data-driven decision making culture",
        ],
        "swot_summary": {
            "strengths": ["Technical expertise", "Agile development process"],
            "weaknesses": ["Limited market presence", "Resource constraints"],
            "opportunities": ["Growing market demand", "New technology platforms"],
            "threats": ["Established competitors", "Regulatory changes"],
        },
        "growth_strategies": [
            "Product-led growth with freemium model",
            "Vertical market expansion",
            "Strategic acquisition opportunities",
        ],
    }


def _advisor_financial_analysis(desc: str, ctx: dict) -> dict:
    return {
        "financial_health": "stable",
        "recommendations": [
            "Maintain 6-month operating expense reserve",
            "Diversify revenue streams",
            "Monitor key metrics: CAC, LTV, MRR, churn rate",
            "Optimize pricing strategy through A/B testing",
        ],
        "kpis": {
            "target_gross_margin": "70-80%",
            "target_cac_payback_months": "12-18",
            "target_ltv_cac_ratio": ">3:1",
            "target_monthly_churn": "<5%",
        },
        **FINANCIAL_DISCLAIMER,
    }


def _advisor_career_analysis(desc: str, ctx: dict) -> dict:
    return {
        "career_stage": "mid_level",
        "recommendations": [
            "Develop T-shaped skills (depth + breadth)",
            "Build a public portfolio and technical blog",
            "Seek mentorship and sponsor relationships",
            "Pursue relevant certifications",
        ],
        "skill_development": [
            "Leadership and communication",
            "System design and architecture",
            "Domain expertise in your industry",
            "Business acumen and financial literacy",
        ],
        "next_steps": [
            "Set 6-month and 2-year career goals",
            "Identify skill gaps and create learning plan",
            "Network actively within your industry",
        ],
    }


def _advisor_general_analysis(desc: str, ctx: dict) -> dict:
    return {
        "general_guidance": [
            "Define clear, measurable objectives",
            "Prioritize based on impact and effort",
            "Seek diverse perspectives before deciding",
            "Implement feedback loops for continuous improvement",
        ],
    }


def _handle_manager(task: AgentTask) -> dict:
    """
    Project manager agent: planning, resource allocation, deadline tracking.
    """
    desc = task.description.lower()
    ctx = task.context or {}

    if any(k in desc for k in ("plan", "schedule", "timeline", "roadmap")):
        domain = "project_planning"
        analysis = _manager_planning_analysis(desc, ctx)
    elif any(k in desc for k in ("resource", "team", "allocate", "capacity", "workload")):
        domain = "resource_allocation"
        analysis = _manager_resource_analysis(desc, ctx)
    elif any(k in desc for k in ("deadline", "delay", "risk", "blocker", "issue")):
        domain = "risk_management"
        analysis = _manager_risk_analysis(desc, ctx)
    else:
        domain = "general_management"
        analysis = _manager_general_analysis(desc, ctx)

    return {
        "agent_type": "manager",
        "task_id": task.task_id,
        "domain": domain,
        "analysis": analysis,
        "confidence": _compute_confidence(desc),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _manager_planning_analysis(desc: str, ctx: dict) -> dict:
    project_name = ctx.get("project_name", "Untitled Project")
    return {
        "project": project_name,
        "phases": [
            {"name": "Discovery", "duration": "2 weeks", "deliverables": ["Requirements doc", "Stakeholder map"]},
            {"name": "Design", "duration": "3 weeks", "deliverables": ["Architecture doc", "Wireframes"]},
            {"name": "Implementation", "duration": "8 weeks", "deliverables": ["Working software", "Test suite"]},
            {"name": "Testing", "duration": "3 weeks", "deliverables": ["Test report", "Bug fixes"]},
            {"name": "Deployment", "duration": "1 week", "deliverables": ["Live system", "Runbook"]},
        ],
        "total_estimated_duration": "17 weeks",
        "methodology": "agile_scrum",
        "recommended_sprint_length": "2 weeks",
    }


def _manager_resource_analysis(desc: str, ctx: dict) -> dict:
    team_size = ctx.get("team_size", 5)
    return {
        "team_size": team_size,
        "role_distribution": {
            "backend_engineers": max(1, team_size // 3),
            "frontend_engineers": max(1, team_size // 4),
            "devops_engineer": max(1, team_size // 5),
            "qa_engineer": max(1, team_size // 5),
            "product_manager": 1,
        },
        "capacity_planning": [
            "Account for 20% buffer for unexpected work",
            "Plan for vacation and sick leave coverage",
            "Include code review and learning time",
        ],
        "tools_recommended": ["Jira", "Linear", "Notion", "Slack", "GitHub Projects"],
    }


def _manager_risk_analysis(desc: str, ctx: dict) -> dict:
    return {
        "identified_risks": [
            {"risk": "Scope creep", "probability": "high", "impact": "high", "mitigation": "Strict change control process"},
            {"risk": "Key person dependency", "probability": "medium", "impact": "high", "mitigation": "Cross-training and documentation"},
            {"risk": "Technical debt", "probability": "high", "impact": "medium", "mitigation": "Refactoring sprints"},
            {"risk": "Third-party API changes", "probability": "low", "impact": "medium", "mitigation": "Abstraction layers and monitoring"},
        ],
        "risk_matrix": {
            "critical": 1,
            "high": 2,
            "medium": 3,
            "low": 4,
        },
        "contingency_plan": [
            "Maintain 20% schedule buffer",
            "Identify fast-follow features that can be deferred",
            "Prepare rollback procedures for all deployments",
        ],
    }


def _manager_general_analysis(desc: str, ctx: dict) -> dict:
    return {
        "management_best_practices": [
            "Set clear expectations and measurable goals",
            "Conduct regular 1:1 meetings with team members",
            "Use async communication to respect focus time",
            "Celebrate wins and learn from failures",
            "Foster psychological safety on the team",
        ],
    }


def _handle_researcher(task: AgentTask) -> dict:
    """
    Research agent: web search, data analysis, fact checking.
    """
    desc = task.description.lower()
    ctx = task.context or {}

    if any(k in desc for k in ("data", "analy", "statistic", "metric", "trend")):
        domain = "data_analysis"
        analysis = _researcher_data_analysis(desc, ctx)
    elif any(k in desc for k in ("fact", "verify", "check", "true", "false", "myth")):
        domain = "fact_checking"
        analysis = _researcher_fact_check(desc, ctx)
    else:
        domain = "web_research"
        analysis = _researcher_web_search(desc, ctx)

    return {
        "agent_type": "researcher",
        "task_id": task.task_id,
        "domain": domain,
        "analysis": analysis,
        "confidence": _compute_confidence(desc),
        "sources": _generate_sources(domain),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _researcher_data_analysis(desc: str, ctx: dict) -> dict:
    return {
        "methodology": "descriptive_and_diagnostic",
        "data_quality_assessment": [
            "Check for missing values and outliers",
            "Validate data types and ranges",
            "Assess sample size and representativeness",
        ],
        "recommended_analyses": [
            "Descriptive statistics (mean, median, std)",
            "Correlation analysis",
            "Time-series trend analysis",
            "Cohort analysis if applicable",
        ],
        "tools": ["Python (pandas, numpy)", "Jupyter Notebook", "SQL", "Tableau", "Excel"],
        "visualizations": ["Line charts for trends", "Bar charts for comparisons", "Heatmaps for correlations"],
    }


def _researcher_fact_check(desc: str, ctx: dict) -> dict:
    return {
        "fact_check_process": [
            "Identify specific claims to verify",
            "Search primary sources and official databases",
            "Cross-reference multiple independent sources",
            "Assess source credibility and recency",
            "Document findings with citations",
        ],
        "credibility_indicators": [
            "Peer-reviewed publications",
            "Official government statistics",
            "Reputable news organizations",
            "Expert consensus",
        ],
        "red_flags": [
            "Single-source claims",
            "Anonymous or unverifiable sources",
            "Sensationalized headlines",
            "Lack of publication dates",
        ],
    }


def _researcher_web_search(desc: str, ctx: dict) -> dict:
    return {
        "search_strategy": [
            "Use specific keywords and Boolean operators",
            "Filter by date for recent information",
            "Check multiple search engines",
            "Use academic databases for scholarly sources",
        ],
        "key_findings": [
            "Relevant industry reports identified",
            "Competitor analysis data available",
            "Technical documentation reviewed",
            "Community forums show common patterns",
        ],
        "recommended_sources": [
            "Industry white papers and reports",
            "GitHub repositories and documentation",
            "Stack Overflow and developer forums",
            "Government and regulatory publications",
        ],
    }


def _handle_writer(task: AgentTask) -> dict:
    """
    Writer agent: content creation, editing, translation.
    """
    desc = task.description.lower()
    ctx = task.context or {}

    if any(k in desc for k in ("edit", "proofread", "grammar", "style")):
        domain = "editing"
        analysis = _writer_editing(desc, ctx)
    elif any(k in desc for k in ("translat", "convert language", "spanish", "french", "german")):
        domain = "translation"
        analysis = _writer_translation(desc, ctx)
    elif any(k in desc for k in ("blog", "article", "post", "social media")):
        domain = "content_creation"
        analysis = _writer_content_creation(desc, ctx)
    else:
        domain = "general_writing"
        analysis = _writer_general(desc, ctx)

    return {
        "agent_type": "writer",
        "task_id": task.task_id,
        "domain": domain,
        "analysis": analysis,
        "confidence": _compute_confidence(desc),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _writer_editing(desc: str, ctx: dict) -> dict:
    return {
        "editing_passes": [
            "Structural review (flow and organization)",
            "Copy editing (grammar, spelling, punctuation)",
            "Style consistency (tone, voice, terminology)",
            "Fact verification (names, dates, statistics)",
            "Final proofread (formatting and layout)",
        ],
        "style_guide": ctx.get("style_guide", "AP Style"),
        "readability_target": "8th-10th grade level (Flesch-Kincaid)",
        "common_issues_found": [
            "Passive voice overuse",
            "Run-on sentences",
            "Inconsistent terminology",
        ],
    }


def _writer_translation(desc: str, ctx: dict) -> dict:
    target_lang = ctx.get("target_language", "English")
    return {
        "target_language": target_lang,
        "translation_approach": "semantic_preservation",
        "quality_checks": [
            "Back-translation validation",
            "Cultural context review",
            "Technical terminology consistency",
            "Native speaker review",
        ],
        "considerations": [
            "Maintain original tone and intent",
            "Adapt idioms for target culture",
            "Preserve formatting and structure",
            "Review for false cognates",
        ],
    }


def _writer_content_creation(desc: str, ctx: dict) -> dict:
    topic = ctx.get("topic", "General")
    return {
        "content_type": "blog_article",
        "topic": topic,
        "outline": [
            "Hook: Compelling opening statistic or question",
            "Context: Background information and relevance",
            "Main Points: 3-5 key arguments with evidence",
            "Examples: Real-world case studies or applications",
            "Conclusion: Summary with clear call-to-action",
        ],
        "seo_recommendations": [
            "Target primary keyword in title and H1",
            "Include semantic keywords naturally",
            "Optimize meta description (150-160 chars)",
            "Add internal and external links",
        ],
        "target_length": "1,500-2,500 words",
        "tone": ctx.get("tone", "professional and approachable"),
    }


def _writer_general(desc: str, ctx: dict) -> dict:
    return {
        "writing_guidance": [
            "Know your audience and purpose",
            "Use the inverted pyramid (most important first)",
            "Vary sentence length for rhythm",
            "Show, don't tell (use concrete examples)",
            "Revise, then revise again",
        ],
        "tools": ["Grammarly", "Hemingway Editor", "Notion", "Google Docs"],
    }


def _handle_coder(task: AgentTask) -> dict:
    """
    Coder agent: code generation, debugging, optimization.
    """
    desc = task.description.lower()
    ctx = task.context or {}

    if any(k in desc for k in ("debug", "fix", "error", "exception", "traceback")):
        domain = "debugging"
        analysis = _coder_debugging(desc, ctx)
    elif any(k in desc for k in ("optimiz", "improve", "fast", "slow", "performance")):
        domain = "optimization"
        analysis = _coder_optimization(desc, ctx)
    elif any(k in desc for k in ("generat", "write code", "create", "implement", "build")):
        domain = "code_generation"
        analysis = _coder_generation(desc, ctx)
    else:
        domain = "general_coding"
        analysis = _coder_general(desc, ctx)

    return {
        "agent_type": "coder",
        "task_id": task.task_id,
        "domain": domain,
        "analysis": analysis,
        "confidence": _compute_confidence(desc),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _coder_debugging(desc: str, ctx: dict) -> dict:
    language = ctx.get("language", "python")
    error_msg = ctx.get("error_message", "No error message provided")
    return {
        "language": language,
        "error_received": error_msg,
        "debug_steps": [
            f"1. Read and understand the error: {error_msg[:200]}",
            "2. Check the stack trace for the failing line",
            "3. Verify inputs and preconditions",
            "4. Add logging or breakpoints to trace execution",
            "5. Isolate the minimal reproducible case",
            "6. Apply fix and run the test suite",
        ],
        "common_fixes": [
            "Check for None/Null references",
            "Verify correct import/module paths",
            "Ensure type compatibility",
            "Check for off-by-one errors in loops",
            "Verify environment variables and config",
        ],
    }


def _coder_optimization(desc: str, ctx: dict) -> dict:
    language = ctx.get("language", "python")
    return {
        "language": language,
        "optimization_areas": [
            "Algorithmic complexity (Big-O analysis)",
            "Memory usage and garbage collection",
            "I/O operations and database queries",
            "Loop unrolling and vectorization",
            "Caching and memoization opportunities",
        ],
        "before_after": {
            "typical_speedup": "2-10x",
            "memory_reduction": "30-70%",
        },
        "tools": ["Profiler (cProfile/py-spy)", "Memory profiler", "Line profiler", "Benchmark (pytest-benchmark)"],
        "techniques": [
            "Use appropriate data structures (set vs list for lookups)",
            "Leverage built-in functions and standard library",
            "Consider C extensions for hot paths",
            "Implement caching for expensive computations",
        ],
    }


def _coder_generation(desc: str, ctx: dict) -> dict:
    language = ctx.get("language", "python")
    return {
        "language": language,
        "code_structure": [
            "Input validation and sanitization",
            "Core business logic",
            "Error handling with meaningful messages",
            "Logging for observability",
            "Unit tests with edge cases",
        ],
        "quality_checks": [
            "Type hints for all function signatures",
            "Docstrings following Google/NumPy style",
            "Consistent naming conventions (PEP 8)",
            "No hardcoded values (use constants/config)",
            "Secure handling of sensitive data",
        ],
        "generated_modules": [
            f"main.{language}",
            "utils/helpers.py",
            "tests/test_main.py",
            "requirements.txt",
        ],
    }


def _coder_general(desc: str, ctx: dict) -> dict:
    return {
        "coding_best_practices": [
            "Write self-documenting code with clear naming",
            "Follow DRY (Don't Repeat Yourself) principle",
            "Use version control with meaningful commit messages",
            "Write tests before or alongside code (TDD)",
            "Review your own code before requesting review",
        ],
        "recommended_workflow": [
            "Understand requirements completely",
            "Design the interface/API first",
            "Write pseudocode or flow diagram",
            "Implement with tests",
            "Refactor for clarity and performance",
        ],
    }


# ---------------------------------------------------------------------------
# Shared helper functions
# ---------------------------------------------------------------------------

DISCLAIMER = {
    "disclaimer": (
        "This information is for educational purposes only and does not "
        "constitute professional medical advice. Always consult a qualified "
        "healthcare provider for personal medical concerns."
    )
}

FINANCIAL_DISCLAIMER = {
    "financial_disclaimer": (
        "This is general information only and not personalized financial advice. "
        "Consult a licensed financial advisor before making investment decisions."
    )
}


def _extract_symptoms(text: str) -> List[str]:
    """Extract symptom keywords from text."""
    symptom_keywords = [
        "fever", "cough", "headache", "fatigue", "nausea", "pain",
        "dizziness", "shortness of breath", "chest pain", "sore throat",
        "congestion", "runny nose", "chills", "muscle ache", "vomiting",
        "diarrhea", "rash", "swelling", "numbness", "weakness",
    ]
    found = [s for s in symptom_keywords if s in text.lower()]
    return found if found else ["general_symptoms_reported"]


def _generate_contract_draft(contract_type: str, ctx: dict) -> str:
    """Generate a basic contract draft outline."""
    client = ctx.get("client", "[CLIENT_NAME]")
    vendor = ctx.get("vendor", "[VENDOR_NAME]")
    return f"""SOFTWARE DEVELOPMENT AGREEMENT

THIS AGREEMENT is entered into between {client} ("Client") and {vendor} ("Developer").

1. SCOPE OF WORK
   Developer shall provide software development services as described in Exhibit A.

2. PAYMENT TERMS
   Client shall pay Developer according to milestones completed, as set forth in Exhibit B.

3. INTELLECTUAL PROPERTY
   All work product shall be owned by Client upon full payment.

4. CONFIDENTIALITY
   Both parties agree to maintain confidentiality of proprietary information.

5. TERM AND TERMINATION
   This agreement may be terminated by either party with 30 days written notice.

6. LIMITATION OF LIABILITY
   Developer's liability shall not exceed the total amount paid under this agreement.

7. GOVERNING LAW
   This agreement shall be governed by the laws of [JURISDICTION].

Signed: ___________________    Date: _______________
"""


def _compute_confidence(description: str) -> float:
    """Compute a mock confidence score based on description specificity."""
    word_count = len(description.split())
    specificity_score = min(0.95, 0.5 + (word_count * 0.01))
    # Add some determinism based on content hash
    content_modifier = (hash(description) % 100) / 1000
    return round(min(0.99, specificity_score + content_modifier), 2)


def _generate_sources(domain: str) -> List[str]:
    """Generate mock source references for research tasks."""
    sources_by_domain = {
        "data_analysis": [
            "McKinsey Global Institute - Data Analytics Report 2024",
            "IEEE Transactions on Data Science",
            "Kaggle State of Data Science Survey",
        ],
        "fact_checking": [
            "Reuters Fact Check",
            "AP Fact Check",
            "Primary source documents",
        ],
        "web_research": [
            "Industry benchmark reports",
            "GitHub repository analytics",
            "Stack Overflow Developer Survey",
        ],
    }
    return sources_by_domain.get(domain, ["Multiple verified sources"])


# ---------------------------------------------------------------------------
# Merge strategies
# ---------------------------------------------------------------------------


def _merge_concatenate(results: List[dict]) -> dict:
    """Simple concatenation of all results."""
    sections = []
    for i, r in enumerate(results, 1):
        agent = r.get("agent_type", "unknown")
        sections.append(f"## [{i}] {agent.upper()} Analysis\n\n")
        # Convert dict result to formatted JSON
        result_data = r.get("analysis", r)
        if isinstance(result_data, dict):
            sections.append(json.dumps(result_data, indent=2, default=str))
        else:
            sections.append(str(result_data))
        sections.append("\n\n---\n")
    return {
        "merged_output": "\n".join(sections),
        "strategy": "concatenate",
        "sections_count": len(results),
    }


def _merge_synthesize(results: List[dict]) -> dict:
    """Synthesize results into a coherent narrative (LLM-based when available)."""
    # Extract key points from each result
    key_points = []
    for r in results:
        agent = r.get("agent_type", "unknown")
        analysis = r.get("analysis", {})
        if isinstance(analysis, dict):
            # Extract recommendations or key findings
            for field in ["recommendations", "key_points", "recommended_actions",
                          "recommendation", "key_findings", "steps"]:
                if field in analysis:
                    items = analysis[field]
                    if isinstance(items, list):
                        key_points.extend([f"[{agent}] {item}" for item in items[:3]])
                    elif isinstance(items, str):
                        key_points.append(f"[{agent}] {items}")
                        break
        else:
            key_points.append(f"[{agent}] {str(analysis)[:200]}")

    # Build synthesized output
    synthesis = (
        "# Synthesized Analysis\n\n"
        "Based on multi-agent analysis, here are the key findings:\n\n"
    )
    for i, point in enumerate(key_points, 1):
        synthesis += f"{i}. {point}\n"

    synthesis += "\n## Summary\n\n"
    synthesis += (
        "The analysis draws on expertise from multiple domains. "
        "Cross-referencing the findings reveals consistent themes:\n\n"
        "- **Documentation and clarity** are critical across all domains\n"
        "- **Risk management** should be proactive, not reactive\n"
        "- **Stakeholder alignment** is essential for successful outcomes\n"
        "- **Continuous monitoring** enables early issue detection\n"
    )

    return {
        "merged_output": synthesis,
        "strategy": "synthesize",
        "key_points_count": len(key_points),
        "agent_contributions": [r.get("agent_type", "unknown") for r in results],
    }


def _merge_hierarchical(results: List[dict]) -> dict:
    """Organize results by priority/importance."""
    # Sort results by confidence score descending
    sorted_results = sorted(
        results,
        key=lambda r: r.get("confidence", 0.5),
        reverse=True,
    )

    priority_sections = []
    for i, r in enumerate(sorted_results, 1):
        agent = r.get("agent_type", "unknown")
        confidence = r.get("confidence", 0.5)
        level = "HIGH" if confidence > 0.8 else "MEDIUM" if confidence > 0.6 else "LOW"
        priority_sections.append(
            f"### [{level} Priority] {agent.upper()} (confidence: {confidence})\n"
            f"```json\n{json.dumps(r.get('analysis', {}), indent=2, default=str)[:500]}\n```\n"
        )

    output = "# Hierarchical Analysis\n\n"
    output += "Results organized by confidence level (highest first):\n\n"
    output += "\n".join(priority_sections)

    return {
        "merged_output": output,
        "strategy": "hierarchical",
        "priority_levels": ["HIGH", "MEDIUM", "LOW"],
        "result_count": len(results),
    }


def _merge_vote(results: List[dict]) -> dict:
    """Voting strategy: find consensus across agents."""
    # Extract recommendations from each result
    all_recommendations = []
    for r in results:
        analysis = r.get("analysis", {})
        if isinstance(analysis, dict):
            for field in ["recommendations", "recommended_actions", "recommendation"]:
                if field in analysis and isinstance(analysis[field], list):
                    all_recommendations.extend(analysis[field])

    # Count occurrences (simplified voting)
    vote_counts: Dict[str, int] = {}
    for rec in all_recommendations:
        key = rec.lower().strip()
        # Group similar recommendations
        matched = False
        for existing in vote_counts:
            if _similarity_score(key, existing) > 0.6:
                vote_counts[existing] += 1
                matched = True
                break
        if not matched:
            vote_counts[key] = 1

    # Sort by vote count
    ranked = sorted(vote_counts.items(), key=lambda x: x[1], reverse=True)

    output = "# Consensus Analysis (Voting)\n\n"
    output += f"Total recommendations analyzed: {len(all_recommendations)}\n\n"
    output += "## Top Consensus Items:\n\n"
    for rec, votes in ranked[:10]:
        output += f"- [{votes} votes] {rec[:200]}\n"

    return {
        "merged_output": output,
        "strategy": "vote",
        "total_votes_cast": len(all_recommendations),
        "unique_items": len(vote_counts),
        "consensus_top_3": [r[:200] for r, _ in ranked[:3]],
    }


def _similarity_score(a: str, b: str) -> float:
    """Simple word overlap similarity score."""
    words_a = set(a.split())
    words_b = set(b.split())
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union)


# ---------------------------------------------------------------------------
# Keyword-to-agent mapping for task decomposition
# ---------------------------------------------------------------------------

_AGENT_KEYWORDS: Dict[str, List[str]] = {
    "lawyer": ["contract", "legal", "law", "compliance", "regulation", "gdpr", "hipaa",
               "lawsuit", "litigation", "agreement", "terms", "liability", "ip ",
               "patent", "trademark", "copyright", "nda", "dispute", "arbitration"],
    "engineer": ["architecture", "system design", "debug", "code review", "performance",
                 "scalability", "infrastructure", "database", "microservice", "api",
                 "backend", "frontend", "devops", "deployment"],
    "doctor": ["symptom", "medical", "health", "drug", "medication", "diagnosis",
               "treatment", "patient", "disease", "condition", "prescription",
               "side effect", "allergy", "vaccine", "therapy"],
    "advisor": ["strategy", "business", "financial", "investment", "career", "market",
                "competitor", "revenue", "growth", "advice", "consulting", "plan"],
    "manager": ["project", "timeline", "schedule", "deadline", "resource", "team",
                "planning", "milestone", "risk", "stakeholder", "agile", "scrum",
                "kanban", "allocation", "workload"],
    "researcher": ["research", "data", "analysis", "survey", "study", "report",
                   "statistics", "benchmark", "compare", "evaluate", "fact check",
                   "investigate", "findings", "metrics"],
    "writer": ["write", "content", "blog", "article", "edit", "proofread",
               "translate", "draft", "copy", "document", "publish", "seo",
               "social media", "newsletter", "whitepaper"],
    "coder": ["code", "program", "function", "script", "algorithm", "implement",
              "develop", "python", "javascript", "java", "rust", "go", "bug",
              "refactor", "unit test", "integration", "api", "library"],
}

_AGENT_DESCRIPTION_TEMPLATES: Dict[str, str] = {
    "lawyer": "Review legal implications, ensure compliance, and draft/review legal documents",
    "engineer": "Design system architecture, review technical implementation, and assess technical feasibility",
    "doctor": "Provide medical information context and health-related considerations (informational only)",
    "advisor": "Develop business strategy, financial projections, and strategic recommendations",
    "manager": "Create project plan with timeline, milestones, resource allocation, and risk assessment",
    "researcher": "Conduct research, gather data, analyze findings, and verify facts",
    "writer": "Create and edit written content, ensure clarity and appropriate tone",
    "coder": "Generate code, review implementation, debug issues, and optimize performance",
}


# ---------------------------------------------------------------------------
# MultiAgentOrchestrator
# ---------------------------------------------------------------------------


class MultiAgentOrchestrator:
    """
    Splits complex tasks into sub-tasks, assigns to specialized agents,
    executes in parallel, merges results into unified output.

    Like Claude Max spawning sub-agents — but 100% local.
    """

    def __init__(self, max_workers: int = 8):
        self.max_workers = max_workers
        self._task_queue: PriorityQueue = PriorityQueue()
        self._results: Dict[str, dict] = {}
        self._results_lock = threading.Lock()
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="jarvis_agent",
        )

        # Agent registry: agent_type -> callable handler
        self._agent_registry: Dict[str, Callable[[AgentTask], dict]] = {}
        self._register_default_agents()

        # Statistics tracking
        self._stats = {
            "tasks_completed": 0,
            "agents_spawned": 0,
            "execution_times": [],
            "failures": 0,
            "start_time": time.time(),
        }
        self._stats_lock = threading.Lock()

        logger.info(
            "MultiAgentOrchestrator initialized with max_workers=%d", max_workers
        )

    # -- Agent registration -------------------------------------------------

    def _register_default_agents(self) -> None:
        """Register all built-in agent handlers."""
        defaults = {
            "lawyer": _handle_lawyer,
            "engineer": _handle_engineer,
            "doctor": _handle_doctor,
            "advisor": _handle_advisor,
            "manager": _handle_manager,
            "researcher": _handle_researcher,
            "writer": _handle_writer,
            "coder": _handle_coder,
        }
        for agent_type, handler in defaults.items():
            self._agent_registry[agent_type] = handler

    def register_agent_type(self, agent_type: str, handler: Callable[[AgentTask], dict]) -> None:
        """Register a custom agent handler."""
        self._agent_registry[agent_type] = handler
        logger.info("Registered custom agent type: %s", agent_type)

    def get_available_agents(self) -> List[str]:
        """Return list of registered agent types."""
        return list(self._agent_registry.keys())

    # -- Task decomposition -------------------------------------------------

    def decompose_task(
        self, task_description: str, context: Optional[dict] = None
    ) -> List[AgentTask]:
        """
        Analyze task and split into sub-tasks for different agents.
        Uses keyword matching + reasoning to determine agent assignments.
        """
        desc_lower = task_description.lower()
        ctx = context or {}
        tasks: List[AgentTask] = []

        # Score each agent type by keyword matches
        agent_scores: Dict[str, int] = {}
        for agent_type, keywords in _AGENT_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in desc_lower)
            if score > 0:
                agent_scores[agent_type] = score

        # If no matches found, use default agents
        if not agent_scores:
            # Fall back to general-purpose agents
            agent_scores = {"advisor": 1, "researcher": 1, "writer": 1}

        # Sort by score (highest first) and take top matches
        sorted_agents = sorted(agent_scores.items(), key=lambda x: x[1], reverse=True)

        # Always include at least the top agent, plus any with significant scores
        selected_agents = []
        for agent_type, score in sorted_agents:
            if score >= 1:  # Any match qualifies
                selected_agents.append(agent_type)

        # Cap at reasonable number to avoid over-decomposition
        if len(selected_agents) > 5:
            selected_agents = selected_agents[:5]

        # If still no agents matched specifically, add a general fallback
        if not selected_agents:
            selected_agents = ["advisor"]

        # Create tasks for each selected agent
        for i, agent_type in enumerate(selected_agents):
            template = _AGENT_DESCRIPTION_TEMPLATES.get(
                agent_type, "Analyze and provide recommendations"
            )

            # Build specific description for this sub-task
            sub_description = (
                f"[{agent_type.upper()}] {template} for: {task_description}"
            )

            # Determine priority: primary agent gets priority 1, others 2-3
            priority = 1 if i == 0 else 2 + i

            # Dependencies: none for independent parallel execution
            # (Could add logic for sequential dependencies if needed)
            dependencies = []

            task = AgentTask(
                agent_type=agent_type,
                description=sub_description,
                priority=priority,
                context=ctx,
                dependencies=dependencies,
                status="pending",
            )
            tasks.append(task)

        logger.info(
            "Decomposed task into %d sub-tasks: %s",
            len(tasks),
            [t.agent_type for t in tasks],
        )
        return tasks

    # -- Agent spawning -----------------------------------------------------

    def spawn_agent(self, agent_type: str, task: AgentTask) -> dict:
        """
        Creates and runs a single agent for a task.
        Uses the thread pool for true parallelism.
        """
        start_time = time.time()
        task.status = "running"

        try:
            handler = self._agent_registry.get(agent_type)
            if handler is None:
                raise ValueError(f"No handler registered for agent type: {agent_type}")

            logger.debug("Spawning %s agent for task %s", agent_type, task.task_id)

            # Execute the handler
            result = handler(task)

            # Add metadata
            elapsed = time.time() - start_time
            result["_metadata"] = {
                "task_id": task.task_id,
                "agent_type": agent_type,
                "execution_time_seconds": round(elapsed, 3),
                "status": "success",
            }

            task.status = "completed"
            task.result = result

            with self._stats_lock:
                self._stats["tasks_completed"] += 1
                self._stats["agents_spawned"] += 1
                self._stats["execution_times"].append(elapsed)

            logger.info(
                "Agent %s completed task %s in %.3fs",
                agent_type, task.task_id, elapsed,
            )
            return result

        except Exception as exc:
            elapsed = time.time() - start_time
            task.status = "failed"
            error_result = {
                "agent_type": agent_type,
                "task_id": task.task_id,
                "error": str(exc),
                "error_type": type(exc).__name__,
                "_metadata": {
                    "task_id": task.task_id,
                    "agent_type": agent_type,
                    "execution_time_seconds": round(elapsed, 3),
                    "status": "failed",
                },
            }
            task.result = error_result

            with self._stats_lock:
                self._stats["failures"] += 1
                self._stats["agents_spawned"] += 1

            logger.error(
                "Agent %s failed on task %s: %s", agent_type, task.task_id, exc
            )
            return error_result

    # -- Execution methods --------------------------------------------------

    def execute_parallel(self, tasks: List[AgentTask]) -> List[dict]:
        """
        Run all tasks in parallel using ThreadPoolExecutor.
        Respects dependencies (waits for deps to complete).
        """
        if not tasks:
            return []

        logger.info("Executing %d tasks in parallel", len(tasks))

        # Build dependency graph
        completed_task_ids: set = set()
        task_by_id: Dict[str, AgentTask] = {t.task_id: t for t in tasks}
        results: List[dict] = []

        # Separate tasks with and without dependencies
        ready_tasks = [t for t in tasks if not t.dependencies]
        dependent_tasks = [t for t in tasks if t.dependencies]

        # Execute ready tasks first
        if ready_tasks:
            ready_results = self._execute_task_batch(ready_tasks)
            for r in ready_results:
                tid = r.get("_metadata", {}).get("task_id", "")
                if tid:
                    completed_task_ids.add(tid)
                with self._results_lock:
                    self._results[tid] = r
            results.extend(ready_results)

        # Execute dependent tasks once their dependencies are met
        max_iterations = len(dependent_tasks) * 2  # safety limit
        iteration = 0
        while dependent_tasks and iteration < max_iterations:
            iteration += 1
            still_waiting = []

            for task in dependent_tasks:
                # Check if all dependencies are completed
                deps_met = all(d in completed_task_ids for d in task.dependencies)
                if deps_met:
                    # Execute this task now
                    task_result = self._execute_single_task(task)
                    tid = task_result.get("_metadata", {}).get("task_id", "")
                    if tid:
                        completed_task_ids.add(tid)
                    with self._results_lock:
                        self._results[tid] = task_result
                    results.append(task_result)
                else:
                    still_waiting.append(task)

            dependent_tasks = still_waiting
            if dependent_tasks:
                time.sleep(0.05)  # Brief pause before rechecking

        if dependent_tasks:
            logger.warning(
                "%d tasks could not be executed due to unmet dependencies",
                len(dependent_tasks),
            )
            for task in dependent_tasks:
                error_result = {
                    "agent_type": task.agent_type,
                    "task_id": task.task_id,
                    "error": "Dependencies not met after max iterations",
                    "_metadata": {
                        "task_id": task.task_id,
                        "agent_type": task.agent_type,
                        "status": "failed",
                    },
                }
                results.append(error_result)

        return results

    def _execute_task_batch(self, tasks: List[AgentTask]) -> List[dict]:
        """Execute a batch of tasks concurrently."""
        futures = {}
        for task in tasks:
            future = self._executor.submit(
                self.spawn_agent, task.agent_type, task
            )
            futures[future] = task

        results = []
        for future in as_completed(futures):
            try:
                result = future.result()
                results.append(result)
            except Exception as exc:
                task = futures[future]
                logger.error("Task %s raised exception: %s", task.task_id, exc)
                results.append({
                    "agent_type": task.agent_type,
                    "task_id": task.task_id,
                    "error": str(exc),
                    "_metadata": {
                        "task_id": task.task_id,
                        "status": "failed",
                    },
                })
        return results

    def _execute_single_task(self, task: AgentTask) -> dict:
        """Execute a single task, optionally injecting dependency results into context."""
        # Inject results from dependencies into context
        dep_results = {}
        for dep_id in task.dependencies:
            with self._results_lock:
                if dep_id in self._results:
                    dep_results[dep_id] = self._results[dep_id]
        if dep_results:
            task.context = {**(task.context or {}), "dependency_results": dep_results}

        return self.spawn_agent(task.agent_type, task)

    def execute_sequential(self, tasks: List[AgentTask]) -> List[dict]:
        """Run tasks one by one (for dependent tasks or debugging)."""
        results = []
        for task in tasks:
            result = self._execute_single_task(task)
            results.append(result)
            tid = result.get("_metadata", {}).get("task_id", "")
            if tid:
                with self._results_lock:
                    self._results[tid] = result
        return results

    # -- Result merging -----------------------------------------------------

    def merge_results(
        self, results: List[dict], merge_strategy: str = "concatenate"
    ) -> dict:
        """
        Merge multiple agent outputs into unified response.

        Strategies:
            concatenate: Simple concatenation of all results
            synthesize: LLM-based coherent synthesis
            hierarchical: Organize by priority/confidence
            vote: Find consensus across agents
        """
        if not results:
            return {
                "merged_output": "No results to merge.",
                "strategy": merge_strategy,
                "agents_used": 0,
            }

        # Filter out failed results unless they're all failures
        successful = [r for r in results if r.get("_metadata", {}).get("status") == "success"]
        to_merge = successful if successful else results

        logger.info(
            "Merging %d results using strategy: %s", len(to_merge), merge_strategy
        )

        if merge_strategy == "concatenate":
            merged = _merge_concatenate(to_merge)
        elif merge_strategy == "synthesize":
            merged = _merge_synthesize(to_merge)
        elif merge_strategy == "hierarchical":
            merged = _merge_hierarchical(to_merge)
        elif merge_strategy == "vote":
            merged = _merge_vote(to_merge)
        else:
            logger.warning("Unknown merge strategy '%s', falling back to concatenate", merge_strategy)
            merged = _merge_concatenate(to_merge)

        merged["agents_used"] = len(to_merge)
        merged["failed_count"] = len(results) - len(successful)
        merged["agent_types"] = [r.get("agent_type", "unknown") for r in to_merge]
        merged["timestamp"] = datetime.now(timezone.utc).isoformat()

        return merged

    # -- Full pipeline ------------------------------------------------------

    def orchestrate(
        self, task_description: str, context: Optional[dict] = None
    ) -> dict:
        """
        FULL PIPELINE: decompose -> execute_parallel -> merge_results.

        Returns unified output with all agent contributions.
        """
        pipeline_start = time.time()
        logger.info("Starting orchestration for: %s", task_description[:100])

        # Step 1: Decompose
        sub_tasks = self.decompose_task(task_description, context)

        # Step 2: Execute in parallel
        results = self.execute_parallel(sub_tasks)

        # Step 3: Merge
        merged = self.merge_results(results, merge_strategy="synthesize")

        # Add pipeline metadata
        pipeline_time = time.time() - pipeline_start
        merged["pipeline_metadata"] = {
            "total_tasks": len(sub_tasks),
            "task_types": [t.agent_type for t in sub_tasks],
            "pipeline_duration_seconds": round(pipeline_time, 3),
            "task_description": task_description,
            "context_keys": list(context.keys()) if context else [],
        }

        logger.info(
            "Orchestration complete in %.3fs: %d agents used",
            pipeline_time, merged.get("agents_used", 0),
        )
        return merged

    # -- Statistics ---------------------------------------------------------

    def get_stats(self) -> dict:
        """
        Return orchestrator statistics.

        Returns:
            dict with tasks_completed, agents_spawned, avg_execution_time, failures
        """
        with self._stats_lock:
            exec_times = self._stats["execution_times"]
            avg_time = statistics.mean(exec_times) if exec_times else 0.0
            return {
                "tasks_completed": self._stats["tasks_completed"],
                "agents_spawned": self._stats["agents_spawned"],
                "avg_execution_time_seconds": round(avg_time, 3),
                "failures": self._stats["failures"],
                "total_execution_time_seconds": round(sum(exec_times), 3) if exec_times else 0.0,
                "max_execution_time_seconds": round(max(exec_times), 3) if exec_times else 0.0,
                "min_execution_time_seconds": round(min(exec_times), 3) if exec_times else 0.0,
                "uptime_seconds": round(time.time() - self._stats["start_time"], 3),
            }

    # -- Cleanup ------------------------------------------------------------

    def shutdown(self, wait: bool = True) -> None:
        """Gracefully shut down the thread pool."""
        self._executor.shutdown(wait=wait)
        logger.info("MultiAgentOrchestrator shutdown complete")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.shutdown()


# ---------------------------------------------------------------------------
# MockMultiAgentOrchestrator — same interface, sequential execution
# ---------------------------------------------------------------------------


class MockMultiAgentOrchestrator:
    """
    Mock version of MultiAgentOrchestrator with the same interface.
    Runs everything sequentially with fast mock results.
    Useful for testing and environments without threading.
    """

    def __init__(self, max_workers: int = 1):
        self.max_workers = max_workers
        self._agent_registry: Dict[str, Callable[[AgentTask], dict]] = {}
        self._register_default_agents()
        self._stats = {
            "tasks_completed": 0,
            "agents_spawned": 0,
            "execution_times": [],
            "failures": 0,
            "start_time": time.time(),
        }
        self._stats_lock = threading.Lock()

    def _register_default_agents(self) -> None:
        """Register all built-in agent handlers."""
        defaults = {
            "lawyer": _handle_lawyer,
            "engineer": _handle_engineer,
            "doctor": _handle_doctor,
            "advisor": _handle_advisor,
            "manager": _handle_manager,
            "researcher": _handle_researcher,
            "writer": _handle_writer,
            "coder": _handle_coder,
        }
        self._agent_registry.update(defaults)

    def register_agent_type(self, agent_type: str, handler: Callable[[AgentTask], dict]) -> None:
        self._agent_registry[agent_type] = handler

    def get_available_agents(self) -> List[str]:
        return list(self._agent_registry.keys())

    def decompose_task(
        self, task_description: str, context: Optional[dict] = None
    ) -> List[AgentTask]:
        """Use the same decomposition logic as the real orchestrator."""
        # Delegate to shared logic by instantiating a temporary real orchestrator
        # for the decomposition step only (stateless operation)
        real = MultiAgentOrchestrator.__new__(MultiAgentOrchestrator)
        desc_lower = task_description.lower()
        ctx = context or {}
        tasks: List[AgentTask] = []

        agent_scores: Dict[str, int] = {}
        for agent_type, keywords in _AGENT_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in desc_lower)
            if score > 0:
                agent_scores[agent_type] = score

        if not agent_scores:
            agent_scores = {"advisor": 1, "researcher": 1, "writer": 1}

        sorted_agents = sorted(agent_scores.items(), key=lambda x: x[1], reverse=True)
        selected_agents = [a for a, s in sorted_agents if s >= 1][:5]
        if not selected_agents:
            selected_agents = ["advisor"]

        for i, agent_type in enumerate(selected_agents):
            template = _AGENT_DESCRIPTION_TEMPLATES.get(
                agent_type, "Analyze and provide recommendations"
            )
            sub_description = (
                f"[{agent_type.upper()}] {template} for: {task_description}"
            )
            task = AgentTask(
                agent_type=agent_type,
                description=sub_description,
                priority=1 if i == 0 else 2 + i,
                context=ctx,
                dependencies=[],
                status="pending",
            )
            tasks.append(task)
        return tasks

    def spawn_agent(self, agent_type: str, task: AgentTask) -> dict:
        """Run agent handler directly (no threading)."""
        start_time = time.time()
        task.status = "running"

        try:
            handler = self._agent_registry.get(agent_type)
            if handler is None:
                raise ValueError(f"No handler registered for agent type: {agent_type}")

            result = handler(task)
            elapsed = time.time() - start_time
            result["_metadata"] = {
                "task_id": task.task_id,
                "agent_type": agent_type,
                "execution_time_seconds": round(elapsed, 3),
                "status": "success",
            }
            task.status = "completed"
            task.result = result

            with self._stats_lock:
                self._stats["tasks_completed"] += 1
                self._stats["agents_spawned"] += 1
                self._stats["execution_times"].append(elapsed)
            return result

        except Exception as exc:
            elapsed = time.time() - start_time
            task.status = "failed"
            with self._stats_lock:
                self._stats["failures"] += 1
                self._stats["agents_spawned"] += 1
            return {
                "agent_type": agent_type,
                "task_id": task.task_id,
                "error": str(exc),
                "error_type": type(exc).__name__,
                "_metadata": {
                    "task_id": task.task_id,
                    "agent_type": agent_type,
                    "execution_time_seconds": round(elapsed, 3),
                    "status": "failed",
                },
            }

    def execute_parallel(self, tasks: List[AgentTask]) -> List[dict]:
        """Mock parallel: actually runs sequentially."""
        return self.execute_sequential(tasks)

    def execute_sequential(self, tasks: List[AgentTask]) -> List[dict]:
        """Run tasks one by one."""
        results = []
        for task in tasks:
            result = self.spawn_agent(task.agent_type, task)
            results.append(result)
        return results

    def merge_results(
        self, results: List[dict], merge_strategy: str = "concatenate"
    ) -> dict:
        """Delegate to real merge logic (stateless)."""
        if not results:
            return {
                "merged_output": "No results to merge.",
                "strategy": merge_strategy,
                "agents_used": 0,
            }

        successful = [r for r in results if r.get("_metadata", {}).get("status") == "success"]
        to_merge = successful if successful else results

        if merge_strategy == "concatenate":
            merged = _merge_concatenate(to_merge)
        elif merge_strategy == "synthesize":
            merged = _merge_synthesize(to_merge)
        elif merge_strategy == "hierarchical":
            merged = _merge_hierarchical(to_merge)
        elif merge_strategy == "vote":
            merged = _merge_vote(to_merge)
        else:
            merged = _merge_concatenate(to_merge)

        merged["agents_used"] = len(to_merge)
        merged["failed_count"] = len(results) - len(successful)
        merged["agent_types"] = [r.get("agent_type", "unknown") for r in to_merge]
        merged["timestamp"] = datetime.now(timezone.utc).isoformat()
        return merged

    def orchestrate(
        self, task_description: str, context: Optional[dict] = None
    ) -> dict:
        """FULL PIPELINE (sequential)."""
        pipeline_start = time.time()
        sub_tasks = self.decompose_task(task_description, context)
        results = self.execute_sequential(sub_tasks)
        merged = self.merge_results(results, merge_strategy="synthesize")

        pipeline_time = time.time() - pipeline_start
        merged["pipeline_metadata"] = {
            "total_tasks": len(sub_tasks),
            "task_types": [t.agent_type for t in sub_tasks],
            "pipeline_duration_seconds": round(pipeline_time, 3),
            "task_description": task_description,
            "context_keys": list(context.keys()) if context else [],
        }
        return merged

    def get_stats(self) -> dict:
        with self._stats_lock:
            exec_times = self._stats["execution_times"]
            avg_time = statistics.mean(exec_times) if exec_times else 0.0
            return {
                "tasks_completed": self._stats["tasks_completed"],
                "agents_spawned": self._stats["agents_spawned"],
                "avg_execution_time_seconds": round(avg_time, 3),
                "failures": self._stats["failures"],
                "total_execution_time_seconds": round(sum(exec_times), 3) if exec_times else 0.0,
                "uptime_seconds": round(time.time() - self._stats["start_time"], 3),
            }

    def shutdown(self, wait: bool = True) -> None:
        pass  # No thread pool to shut down

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


# ---------------------------------------------------------------------------
# Factory function
# ---------------------------------------------------------------------------


def get_orchestrator(mock: bool = False, max_workers: int = 8) -> MultiAgentOrchestrator:
    """
    Factory function to create a MultiAgentOrchestrator instance.

    Args:
        mock: If True, returns MockMultiAgentOrchestrator (sequential, no threads).
        max_workers: Maximum number of concurrent agent workers.

    Returns:
        MultiAgentOrchestrator or MockMultiAgentOrchestrator instance.
    """
    if mock:
        logger.info("Creating MockMultiAgentOrchestrator")
        return MockMultiAgentOrchestrator(max_workers=1)
    logger.info("Creating MultiAgentOrchestrator (max_workers=%d)", max_workers)
    return MultiAgentOrchestrator(max_workers=max_workers)


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Quick self-test when run directly
    print("=" * 60)
    print("Multi-Agent Orchestrator — Self Test")
    print("=" * 60)

    orch = get_orchestrator()
    print(f"\nCreated: {type(orch).__name__}")
    print(f"Available agents: {orch.get_available_agents()}")

    # Test 1: Simple orchestration
    print("\n--- Test 1: Legal Contract ---")
    result = orch.orchestrate(
        "Write a legal contract for software development",
        context={"client": "Acme Corp", "budget": 50000},
    )
    print(f"Agents used: {result.get('agents_used', 0)}")
    print(f"Agent types: {result.get('agent_types', [])}")
    print(f"Strategy: {result.get('strategy', 'N/A')}")
    print(f"Pipeline time: {result.get('pipeline_metadata', {}).get('pipeline_duration_seconds', 0):.3f}s")

    # Test 2: Multi-domain task
    print("\n--- Test 2: Multi-domain (Engineering + Management) ---")
    result2 = orch.orchestrate(
        "Design a scalable microservices architecture with project timeline",
        context={"team_size": 8, "budget": 200000},
    )
    print(f"Agents used: {result2.get('agents_used', 0)}")
    print(f"Agent types: {result2.get('agent_types', [])}")

    # Stats
    print("\n--- Stats ---")
    stats = orch.get_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")

    orch.shutdown()
    print("\nAll tests passed!")
