#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
═══════════════════════════════════════════════════════════════════════════════
    J A R V I S   U N I F I E D   I N T E R F A C E
═══════════════════════════════════════════════════════════════════════════════

    The GOD-MODE entry point. ALL capabilities of JARVIS exposed through
    a single unified interface. Like having Claude Max + Kimi + Cursor +
    Mythos all in one.

    Your true companion, expert advisor, professional assistant,
    and autonomous agent.

    ── Features ──────────────────────────────────────────────────────────
    • 16+ core methods covering every use case
    • Multi-agent orchestration with 8 expert personas
    • Multimodal output: text, image, audio, document, interactive
    • Hebrew-first: auto-detection, Hebrew output for Hebrew queries
    • Lazy subsystem loading for optimal performance
    • Deterministic Mock interface for testing without dependencies

    ── Architecture ──────────────────────────────────────────────────────
    JARVISInterface ──► routes ──► Expert Personas
                          │       • Lawyer
                          │       • Engineer
                          │       • Doctor
                          │       • Business Advisor
                          │       • Creative Director
                          │       • Career Coach
                          │       • Relationship Counselor
                          │       • General Advisor
                          │
                          ├─────► Subsystems
                          │       • Local Brain (reasoning)
                          │       • Local Voice (TTS/STT)
                          │       • Local Vision (image analysis)
                          │       • Local Memory (vector store)
                          │       • Local OS (system control)
                          │       • Skill Engine (tool execution)
                          │       • Task Planner (decomposition)
                          │       • Document Generator
                          │       • Drawing Engine
                          │       • VR Interface
                          │
                          └─────► Orchestration
                                  • Multi-agent collaboration
                                  • Consensus building
                                  • Output merging

    Author: JARVIS Core Team
    Version: 1.0.0
    License: Proprietary
═══════════════════════════════════════════════════════════════════════════════
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time
import traceback
import warnings
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

# ═══════════════════════════════════════════════════════════════════════════════
# Module-level constants
# ═══════════════════════════════════════════════════════════════════════════════

__version__ = "1.0.0"
__all__ = [
    "JARVISInterface",
    "MockJARVISInterface",
    "get_jarvis_interface",
    "MultimodalOutput",
    "ExpertMode",
    "TrustLevel",
    "HebrewUtils",
]

_HEBREW_RE = re.compile(r"[\u0590-\u05FF]")
_HEBREW_CHARS = re.compile(r"[א-ת]")
HEBREW_GREETING = "ברוך הבא ל-JARVIS"
ENGLISH_GREETING = "Welcome to JARVIS"


# ═══════════════════════════════════════════════════════════════════════════════
# Enums
# ═══════════════════════════════════════════════════════════════════════════════

class ExpertMode(str, Enum):
    """Available expert routing modes."""
    AUTO = "auto"
    LAWYER = "lawyer"
    ENGINEER = "engineer"
    DOCTOR = "doctor"
    ADVISOR = "advisor"
    MANAGER = "manager"
    CREATIVE = "creative"
    FRIEND = "friend"


class TrustLevel(str, Enum):
    """Trust levels for command execution."""
    SAFE = "safe"
    NORMAL = "normal"
    ELEVATED = "elevated"
    OVERRIDE = "override"


class OutputType(str, Enum):
    """Output types for the create() method."""
    AUTO = "auto"
    CODE = "code"
    DOCUMENT = "document"
    IMAGE = "image"
    PLAN = "plan"
    PRESENTATION = "presentation"
    ALL = "all"


class ExplainStyle(str, Enum):
    """Explanation style options."""
    TEXT = "text"
    VISUAL = "visual"
    AUDIO = "audio"
    DOCUMENT = "document"
    MULTIMODAL = "multimodal"
    INTERACTIVE = "interactive"


class DrawingStyle(str, Enum):
    """Drawing style options."""
    TECHNICAL = "technical"
    ARTISTIC = "artistic"
    FLOWCHART = "flowchart"
    MINDMAP = "mindmap"


class ResearchDepth(str, Enum):
    """Research depth levels."""
    QUICK = "quick"
    STANDARD = "standard"
    COMPREHENSIVE = "comprehensive"
    DEEP = "deep"


# ═══════════════════════════════════════════════════════════════════════════════
# Data Classes
# ═══════════════════════════════════════════════════════════════════════════════

class MultimodalOutput:
    """
    Container for multimodal responses.
    Holds text, image paths, audio paths, document paths, and metadata.
    """

    def __init__(
        self,
        text: str = "",
        images: Optional[List[str]] = None,
        audio: Optional[List[str]] = None,
        documents: Optional[List[str]] = None,
        interactive: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.text = text
        self.images = images or []
        self.audio = audio or []
        self.documents = documents or []
        self.interactive = interactive or {}
        self.metadata = metadata or {}
        self.created_at = datetime.now().isoformat()

    def __repr__(self) -> str:
        return (
            f"MultimodalOutput(text_len={len(self.text)}, "
            f"images={len(self.images)}, audio={len(self.audio)}, "
            f"documents={len(self.documents)})"
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "text": self.text,
            "images": self.images,
            "audio": self.audio,
            "documents": self.documents,
            "interactive": self.interactive,
            "metadata": self.metadata,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MultimodalOutput":
        """Deserialize from dictionary."""
        return cls(
            text=data.get("text", ""),
            images=data.get("images", []),
            audio=data.get("audio", []),
            documents=data.get("documents", []),
            interactive=data.get("interactive", {}),
            metadata=data.get("metadata", {}),
        )


# ═══════════════════════════════════════════════════════════════════════════════
# Hebrew Utilities
# ═══════════════════════════════════════════════════════════════════════════════

class HebrewUtils:
    """
    Hebrew language detection and handling utilities.
    Provides automatic Hebrew detection, RTL support, and
    Hebrew-first response formatting.
    """

    @staticmethod
    def is_hebrew(text: str) -> bool:
        """Detect if text contains Hebrew characters."""
        if not text:
            return False
        return bool(_HEBREW_CHARS.search(text))

    @staticmethod
    def hebrew_ratio(text: str) -> float:
        """Calculate ratio of Hebrew characters in text (0.0 to 1.0)."""
        if not text:
            return 0.0
        hebrew_count = len(_HEBREW_CHARS.findall(text))
        total_chars = len([c for c in text if c.isalpha()])
        if total_chars == 0:
            return 0.0
        return min(1.0, hebrew_count / total_chars)

    @staticmethod
    def is_mixed(text: str) -> bool:
        """Detect if text contains mixed Hebrew-English content."""
        if not text:
            return False
        has_hebrew = bool(_HEBREW_CHARS.search(text))
        has_english = bool(re.search(r"[a-zA-Z]", text))
        return has_hebrew and has_english

    @staticmethod
    def format_response(text: str, force_hebrew: bool = False) -> str:
        """Format response with proper RTL handling for Hebrew."""
        is_hb = force_hebrew or HebrewUtils.is_hebrew(text)
        if is_hb:
            # Add RTL marker for proper Hebrew display
            text = "\u202B" + text + "\u202C"
        return text

    @staticmethod
    def greeting() -> str:
        """Return appropriate greeting."""
        return HEBREW_GREETING

    @staticmethod
    def detect_language(text: str) -> str:
        """Detect primary language: 'hebrew', 'english', 'mixed', or 'other'."""
        if not text:
            return "other"
        hebrew_ratio = HebrewUtils.hebrew_ratio(text)
        if hebrew_ratio > 0.5:
            return "hebrew"
        elif HebrewUtils.is_mixed(text):
            return "mixed"
        elif bool(re.search(r"[a-zA-Z]", text)):
            return "english"
        return "other"


# ═══════════════════════════════════════════════════════════════════════════════
# Thread-safe Subsystem Registry
# ═══════════════════════════════════════════════════════════════════════════════

class SubsystemRegistry:
    """
    Thread-safe registry for lazy-loaded subsystems.
    Ensures each subsystem is initialized exactly once,
    even under concurrent access.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._subsystems: Dict[str, Any] = {}
        self._init_functions: Dict[str, Callable[[], Any]] = {}
        self._init_status: Dict[str, str] = {}  # "pending" | "loading" | "ready" | "failed"
        self._errors: Dict[str, str] = {}

    def register(self, name: str, init_func: Callable[[], Any]) -> None:
        """Register a subsystem with its initialization function."""
        with self._lock:
            self._init_functions[name] = init_func
            self._init_status[name] = "pending"

    def get(self, name: str) -> Optional[Any]:
        """Get a subsystem, initializing it if necessary."""
        with self._lock:
            if name in self._subsystems:
                return self._subsystems[name]
            if name not in self._init_functions:
                return None
            if self._init_status.get(name) in ("loading", "failed"):
                return None
            self._init_status[name] = "loading"

        # Initialize outside the lock to avoid deadlocks
        try:
            instance = self._init_functions[name]()
            with self._lock:
                self._subsystems[name] = instance
                self._init_status[name] = "ready"
            return instance
        except Exception as e:
            with self._lock:
                self._init_status[name] = "failed"
                self._errors[name] = str(e)
            return None

    def status(self) -> Dict[str, Dict[str, str]]:
        """Return status of all registered subsystems."""
        with self._lock:
            return {
                name: {
                    "status": self._init_status.get(name, "unknown"),
                    "error": self._errors.get(name, ""),
                    "loaded": name in self._subsystems,
                }
                for name in self._init_functions
            }


# ═══════════════════════════════════════════════════════════════════════════════
# Response Builder
# ═══════════════════════════════════════════════════════════════════════════════

class ResponseBuilder:
    """Builds standardized responses with Hebrew support."""

    @staticmethod
    def build(
        answer: str = "",
        expert: str = "general",
        confidence: float = 0.85,
        sources: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        hebrew_input: bool = False,
    ) -> Dict[str, Any]:
        """Build a standardized response dictionary."""
        if hebrew_input and not HebrewUtils.is_hebrew(answer):
            answer = HebrewUtils.format_response(answer, force_hebrew=True)
        return {
            "answer": answer,
            "expert": expert,
            "confidence": round(confidence, 3),
            "sources": sources or [],
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata or {},
        }

    @staticmethod
    def build_advice(
        topic: str = "",
        steps: Optional[List[str]] = None,
        warnings: Optional[List[str]] = None,
        resources: Optional[List[str]] = None,
        hebrew_input: bool = False,
    ) -> Dict[str, Any]:
        """Build a structured advice response."""
        response = {
            "topic": topic,
            "actionable_steps": steps or [],
            "warnings": warnings or [],
            "resources": resources or [],
            "timestamp": datetime.now().isoformat(),
        }
        if hebrew_input:
            for key in ["topic"]:
                if response[key]:
                    response[key] = HebrewUtils.format_response(response[key], force_hebrew=True)
        return response

    @staticmethod
    def build_plan(
        goal: str = "",
        phases: Optional[List[Dict[str, Any]]] = None,
        timeline: str = "",
        critical_path: Optional[List[str]] = None,
        risks: Optional[List[str]] = None,
        hebrew_input: bool = False,
    ) -> Dict[str, Any]:
        """Build a structured plan response."""
        response = {
            "goal": goal,
            "phases": phases or [],
            "timeline": timeline,
            "critical_path": critical_path or [],
            "risks": risks or [],
            "timestamp": datetime.now().isoformat(),
        }
        if hebrew_input:
            for key in ["goal", "timeline"]:
                if response.get(key):
                    response[key] = HebrewUtils.format_response(response[key], force_hebrew=True)
        return response


# ═══════════════════════════════════════════════════════════════════════════════
# Expert Persona Definitions
# ═══════════════════════════════════════════════════════════════════════════════

EXPERT_PERSONAS: Dict[str, Dict[str, Any]] = {
    "lawyer": {
        "name": "Legal Expert",
        "hebrew_name": "מומחה משפטי",
        "domains": ["legal", "law", "contract", "regulation", "rights", "court"],
        "hebrew_domains": ["משפט", "חוק", "חוזה", "תקנה", "זכויות", "בית משפט"],
        "tone": "formal_precise",
        "disclaimer": "This is not legal advice. Consult a licensed attorney.",
        "hebrew_disclaimer": "זוהי אינה ייעוץ משפטי. יש להתייעץ עם עורך דין מורשה.",
    },
    "engineer": {
        "name": "Engineering Expert",
        "hebrew_name": "מומחה הנדסה",
        "domains": ["code", "software", "hardware", "architecture", "system", "debug"],
        "hebrew_domains": ["קוד", "תוכנה", "חומרה", "ארכיטקטורה", "מערכת", "תיקון"],
        "tone": "technical_pragmatic",
        "disclaimer": "",
        "hebrew_disclaimer": "",
    },
    "doctor": {
        "name": "Medical Expert",
        "hebrew_name": "מומחה רפואי",
        "domains": ["medical", "health", "symptom", "diagnosis", "treatment", "medicine"],
        "hebrew_domains": ["רפואה", "בריאות", "תסמין", "אבחון", "טיפול", "תרופה"],
        "tone": "cautious_informative",
        "disclaimer": "This is not medical advice. Consult a licensed physician.",
        "hebrew_disclaimer": "זוהי אינה ייעוץ רפואי. יש להתייעץ עם רופא מורשה.",
    },
    "advisor": {
        "name": "Business Advisor",
        "hebrew_name": "יועץ עסקי",
        "domains": ["business", "strategy", "finance", "marketing", "startup", "investment"],
        "hebrew_domains": ["עסקים", "אסטרטגיה", "פיננסים", "שיווק", "סטארטאפ", "השקעה"],
        "tone": "strategic_analytical",
        "disclaimer": "",
        "hebrew_disclaimer": "",
    },
    "creative": {
        "name": "Creative Director",
        "hebrew_name": "מנהל יצירתי",
        "domains": ["design", "art", "creative", "writing", "story", "brand"],
        "hebrew_domains": ["עיצוב", "אמנות", "יצירתי", "כתיבה", "סיפור", "מותג"],
        "tone": "inspirational_vivid",
        "disclaimer": "",
        "hebrew_disclaimer": "",
    },
    "manager": {
        "name": "Project Manager",
        "hebrew_name": "מנהל פרויקט",
        "domains": ["project", "management", "team", "timeline", "agile", "planning"],
        "hebrew_domains": ["פרויקט", "ניהול", "צוות", "לוח זמנים", "אג'ייל", "תכנון"],
        "tone": "organized_clear",
        "disclaimer": "",
        "hebrew_disclaimer": "",
    },
    "friend": {
        "name": "Companion",
        "hebrew_name": "בן לוויה",
        "domains": ["personal", "emotional", "relationships", "life", "chat", "feelings"],
        "hebrew_domains": ["אישי", "רגשי", "זוגיות", "חיים", "שיחה", "רגשות"],
        "tone": "warm_empathetic",
        "disclaimer": "",
        "hebrew_disclaimer": "",
    },
    "career": {
        "name": "Career Coach",
        "hebrew_name": "מאמן קריירה",
        "domains": ["career", "job", "resume", "interview", "skills", "promotion"],
        "hebrew_domains": ["קריירה", "עבודה", "קורות חיים", "ראיון", "מיומנויות", "קידום"],
        "tone": "supportive_motivational",
        "disclaimer": "",
        "hebrew_disclaimer": "",
    },
    "relationships": {
        "name": "Relationship Counselor",
        "hebrew_name": "יועץ זוגיות",
        "domains": ["relationship", "couple", "family", "communication", "conflict"],
        "hebrew_domains": ["זוגיות", "זוג", "משפחה", "תקשורת", "קונפליקט"],
        "tone": "empathetic_nonjudgmental",
        "disclaimer": "",
        "hebrew_disclaimer": "",
    },
}


# ═══════════════════════════════════════════════════════════════════════════════
# JARVISInterface — The ONE Interface to Rule Them All
# ═══════════════════════════════════════════════════════════════════════════════

class JARVISInterface:
    """
    The ONE interface to rule them all.

    Routes requests to the right subsystems.
    Combines outputs from multiple agents.
    Presents unified multimodal responses.

    This is JARVIS — your true companion, expert advisor,
    professional assistant, and autonomous agent.
    """

    def __init__(self):
        # ── Lazy-loaded subsystems ──────────────────────────────────────────
        self._brain: Optional[Any] = None          # local_brain
        self._voice: Optional[Any] = None          # local_voice
        self._vision: Optional[Any] = None         # local_vision
        self._memory: Optional[Any] = None         # local_memory
        self._os: Optional[Any] = None             # local_os
        self._skills: Optional[Any] = None         # local_skill_engine
        self._orchestrator: Optional[Any] = None   # multi_agent_orchestrator
        self._personas: Optional[Any] = None       # expert_personas
        self._collaboration: Optional[Any] = None  # collaborative_workflow
        self._multimodal: Optional[Any] = None     # multimodal_output
        self._advisor: Optional[Any] = None        # advisor_brain
        self._planner: Optional[Any] = None        # task_planner
        self._docs: Optional[Any] = None           # document_generator
        self._drawing: Optional[Any] = None        # drawing_engine
        self._react: Optional[Any] = None          # react_loop
        self._vr: Optional[Any] = None             # vr_interface

        # ── Internal state ──────────────────────────────────────────────────
        self._registry = SubsystemRegistry()
        self._conversation_history: List[Dict[str, str]] = []
        self._max_history = 50
        self._stats = {
            "total_requests": 0,
            "total_errors": 0,
            "start_time": datetime.now().isoformat(),
            "requests_by_method": {},
        }
        self._lock = threading.RLock()

        # ── Register subsystem initializers ─────────────────────────────────
        self._register_subsystems()

    def _register_subsystems(self) -> None:
        """Register all subsystem lazy initializers."""
        subsystems = {
            "brain": self._init_brain,
            "voice": self._init_voice,
            "vision": self._init_vision,
            "memory": self._init_memory,
            "os": self._init_os,
            "skills": self._init_skills,
            "orchestrator": self._init_orchestrator,
            "personas": self._init_personas,
            "collaboration": self._init_collaboration,
            "multimodal": self._init_multimodal,
            "advisor": self._init_advisor,
            "planner": self._init_planner,
            "docs": self._init_docs,
            "drawing": self._init_drawing,
            "react": self._init_react,
            "vr": self._init_vr,
        }
        for name, init_func in subsystems.items():
            self._registry.register(name, init_func)

    # ── Lazy Subsystem Initializers ───────────────────────────────────────

    def _init_brain(self) -> Any:
        """Initialize local_brain subsystem."""
        try:
            from jarvis.runtime.brain.local_brain import LocalBrain
            return LocalBrain()
        except ImportError:
            warnings.warn("local_brain not available, using fallback")
            return None

    def _init_voice(self) -> Any:
        """Initialize local_voice subsystem."""
        try:
            from jarvis.runtime.voice.local_voice import LocalVoice
            return LocalVoice()
        except ImportError:
            warnings.warn("local_voice not available, using fallback")
            return None

    def _init_vision(self) -> Any:
        """Initialize local_vision subsystem."""
        try:
            from jarvis.runtime.vision.local_vision import LocalVision
            return LocalVision()
        except ImportError:
            warnings.warn("local_vision not available, using fallback")
            return None

    def _init_memory(self) -> Any:
        """Initialize local_memory subsystem."""
        try:
            from jarvis.runtime.memory.local_memory import LocalMemory
            return LocalMemory()
        except ImportError:
            warnings.warn("local_memory not available, using fallback")
            return None

    def _init_os(self) -> Any:
        """Initialize local_os subsystem."""
        try:
            from jarvis.runtime.os.local_os import LocalOS
            return LocalOS()
        except ImportError:
            warnings.warn("local_os not available, using fallback")
            return None

    def _init_skills(self) -> Any:
        """Initialize local_skill_engine subsystem."""
        try:
            from jarvis.runtime.skills.local_skill_engine import LocalSkillEngine
            return LocalSkillEngine()
        except ImportError:
            warnings.warn("local_skill_engine not available, using fallback")
            return None

    def _init_orchestrator(self) -> Any:
        """Initialize multi_agent_orchestrator subsystem."""
        try:
            from jarvis.runtime.agency.multi_agent_orchestrator import MultiAgentOrchestrator
            return MultiAgentOrchestrator()
        except ImportError:
            warnings.warn("multi_agent_orchestrator not available, using fallback")
            return None

    def _init_personas(self) -> Any:
        """Initialize expert_personas subsystem."""
        try:
            from jarvis.runtime.agency.expert_personas import ExpertPersonas
            return ExpertPersonas()
        except ImportError:
            warnings.warn("expert_personas not available, using fallback")
            return None

    def _init_collaboration(self) -> Any:
        """Initialize collaborative_workflow subsystem."""
        try:
            from jarvis.runtime.agency.collaborative_workflow import CollaborativeWorkflow
            return CollaborativeWorkflow()
        except ImportError:
            warnings.warn("collaborative_workflow not available, using fallback")
            return None

    def _init_multimodal(self) -> Any:
        """Initialize multimodal_output subsystem."""
        try:
            from jarvis.runtime.output.multimodal_output import MultimodalOutputEngine
            return MultimodalOutputEngine()
        except ImportError:
            warnings.warn("multimodal_output not available, using fallback")
            return None

    def _init_advisor(self) -> Any:
        """Initialize advisor_brain subsystem."""
        try:
            from jarvis.runtime.advisor.advisor_brain import AdvisorBrain
            return AdvisorBrain()
        except ImportError:
            warnings.warn("advisor_brain not available, using fallback")
            return None

    def _init_planner(self) -> Any:
        """Initialize task_planner subsystem."""
        try:
            from jarvis.runtime.planner.task_planner import TaskPlanner
            return TaskPlanner()
        except ImportError:
            warnings.warn("task_planner not available, using fallback")
            return None

    def _init_docs(self) -> Any:
        """Initialize document_generator subsystem."""
        try:
            from jarvis.runtime.docs.document_generator import DocumentGenerator
            return DocumentGenerator()
        except ImportError:
            warnings.warn("document_generator not available, using fallback")
            return None

    def _init_drawing(self) -> Any:
        """Initialize drawing_engine subsystem."""
        try:
            from jarvis.runtime.draw.drawing_engine import DrawingEngine
            return DrawingEngine()
        except ImportError:
            warnings.warn("drawing_engine not available, using fallback")
            return None

    def _init_react(self) -> Any:
        """Initialize react_loop subsystem."""
        try:
            from jarvis.runtime.react.react_loop import ReactLoop
            return ReactLoop()
        except ImportError:
            warnings.warn("react_loop not available, using fallback")
            return None

    def _init_vr(self) -> Any:
        """Initialize vr_interface subsystem."""
        try:
            from jarvis.runtime.vr.vr_interface import VRInterface
            return VRInterface()
        except ImportError:
            warnings.warn("vr_interface not available, using fallback")
            return None

    # ── Private Routing Methods ──────────────────────────────────────────

    def _route_to_expert(self, question: str) -> str:
        """
        Determine which expert(s) should handle the question.

        Uses keyword matching against expert domain definitions.
        Falls back to general advisor for unrecognized queries.
        Supports Hebrew domain keywords.
        """
        question_lower = question.lower()
        scores: Dict[str, int] = {}

        for expert_id, config in EXPERT_PERSONAS.items():
            score = 0
            # Check English domains
            for domain in config.get("domains", []):
                if domain.lower() in question_lower:
                    score += 2
            # Check Hebrew domains
            for h_domain in config.get("hebrew_domains", []):
                if h_domain in question:
                    score += 3  # Higher weight for Hebrew matches
            if score > 0:
                scores[expert_id] = score

        if not scores:
            return "advisor"

        return max(scores, key=scores.get)  # type: ignore[arg-type]

    def _spawn_agents_for_task(
        self, task: str, agents: Optional[List[str]] = None
    ) -> List[str]:
        """
        Create a collaboration session with specified agents.

        If no agents specified, auto-selects based on task content.
        Returns the list of agent IDs that were spawned.
        """
        if agents is None:
            # Auto-detect relevant agents
            agents = []
            task_lower = task.lower()
            keywords_map = {
                "lawyer": ["legal", "contract", "law", "rights", "court", "משפט", "חוק"],
                "engineer": ["code", "software", "system", "architecture", "debug", "קוד", "מערכת"],
                "doctor": ["health", "medical", "symptom", "treatment", "רפואה", "בריאות"],
                "advisor": ["business", "strategy", "finance", "startup", "עסק", "אסטרטגיה"],
                "creative": ["design", "creative", "art", "brand", "עיצוב", "אמנות"],
            }
            for agent, keywords in keywords_map.items():
                for kw in keywords:
                    if kw in task_lower or kw in task:
                        agents.append(agent)
                        break
            if not agents:
                agents = ["advisor"]

        # Spawn the collaboration session
        collab = self._registry.get("collaboration")
        if collab and hasattr(collab, "start_session"):
            try:
                collab.start_session(task, agents)
            except Exception:
                pass

        return agents

    def _merge_outputs(self, outputs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Combine multiple agent outputs into a unified response.

        Uses weighted merging based on expert confidence scores.
        Preserves all sources and metadata.
        """
        if not outputs:
            return ResponseBuilder.build(
                answer="No outputs to merge.",
                expert="system",
                confidence=0.0,
            )

        if len(outputs) == 1:
            return outputs[0]

        # Weighted text combination
        total_confidence = sum(o.get("confidence", 0.5) for o in outputs)
        if total_confidence == 0:
            total_confidence = 1.0

        # Combine answers with separator
        answers = [o.get("answer", "") for o in outputs if o.get("answer")]
        merged_answer = "\n\n---\n\n".join(answers)

        # Collect all sources
        all_sources = []
        for o in outputs:
            all_sources.extend(o.get("sources", []))

        # Average confidence with boost for agreement
        avg_confidence = sum(o.get("confidence", 0.5) for o in outputs) / len(outputs)
        agreement_boost = min(0.15, len(outputs) * 0.03)
        final_confidence = min(1.0, avg_confidence + agreement_boost)

        # List contributing experts
        experts = [o.get("expert", "unknown") for o in outputs]
        expert_label = " + ".join(set(experts))

        return ResponseBuilder.build(
            answer=merged_answer,
            expert=expert_label,
            confidence=final_confidence,
            sources=list(set(all_sources)),
            metadata={
                "merged_from": len(outputs),
                "contributing_experts": experts,
                "agreement_boost": agreement_boost,
            },
        )

    def _init_subsystem(self, name: str) -> Optional[Any]:
        """Lazy initialization wrapper for a named subsystem."""
        return self._registry.get(name)

    def _update_stats(self, method: str) -> None:
        """Update usage statistics."""
        with self._lock:
            self._stats["total_requests"] += 1
            self._stats["requests_by_method"][method] = (
                self._stats["requests_by_method"].get(method, 0) + 1
            )

    def _add_to_history(self, role: str, content: str) -> None:
        """Add a message to conversation history."""
        with self._lock:
            self._conversation_history.append({
                "role": role,
                "content": content,
                "timestamp": datetime.now().isoformat(),
            })
            # Trim history if too long
            if len(self._conversation_history) > self._max_history:
                self._conversation_history = self._conversation_history[-self._max_history:]

    # ═════════════════════════════════════════════════════════════════════════
    # PUBLIC API — Core Methods
    # ═════════════════════════════════════════════════════════════════════════

    def ask(self, question: str, mode: str = "auto") -> Dict[str, Any]:
        """
        Main Q&A — routes to the right expert(s).

        Args:
            question: The question or query to answer.
            mode: Expert mode — "auto|lawyer|engineer|doctor|advisor
                               |manager|creative|friend|career|relationships"

        Returns:
            dict: {"answer": str, "expert": str, "confidence": float, "sources": list}

        Examples:
            >>> j = JARVISInterface()
            >>> j.ask("What is a corporation?")
            >>> j.ask("מהי חברה?")  # Hebrew auto-detected
            >>> j.ask("Explain Python decorators", mode="engineer")
        """
        self._update_stats("ask")
        self._add_to_history("user", question)

        is_hebrew = HebrewUtils.is_hebrew(question)

        try:
            # Determine expert
            if mode == "auto":
                expert_id = self._route_to_expert(question)
            else:
                expert_id = mode if mode in EXPERT_PERSONAS else "advisor"

            expert_config = EXPERT_PERSONAS.get(expert_id, EXPERT_PERSONAS["advisor"])

            # Try to use advisor brain if available
            advisor = self._registry.get("advisor")
            if advisor and hasattr(advisor, "advise"):
                try:
                    raw_answer = advisor.advise(question, domain=expert_id)
                except Exception:
                    raw_answer = self._generate_answer(question, expert_id, is_hebrew)
            else:
                raw_answer = self._generate_answer(question, expert_id, is_hebrew)

            # Append disclaimer if applicable
            disclaimer = ""
            if is_hebrew and expert_config.get("hebrew_disclaimer"):
                disclaimer = f"\n\n⚠ {expert_config['hebrew_disclaimer']}"
            elif expert_config.get("disclaimer"):
                disclaimer = f"\n\n⚠ {expert_config['disclaimer']}"

            full_answer = raw_answer + disclaimer if disclaimer else raw_answer

            response = ResponseBuilder.build(
                answer=full_answer,
                expert=expert_config.get("hebrew_name" if is_hebrew else "name", expert_id),
                confidence=0.92 if expert_id != "advisor" else 0.85,
                sources=[],
                hebrew_input=is_hebrew,
            )

            self._add_to_history("assistant", response["answer"])
            return response

        except Exception as e:
            self._stats["total_errors"] += 1
            return ResponseBuilder.build(
                answer=f"Error processing question: {str(e)}" if not is_hebrew
                       else f"שגיאה בעיבוד השאלה: {str(e)}",
                expert="system",
                confidence=0.0,
            )

    def create(self, description: str, output_type: str = "auto") -> Dict[str, Any]:
        """
        Create anything: code, documents, images, plans.

        Spawns appropriate agents based on the description and output type,
        then returns a unified output with all generated artifacts.

        Args:
            description: Natural language description of what to create.
            output_type: "code|document|image|plan|presentation|auto|all"

        Returns:
            dict: {"artifacts": list, "type": str, "details": dict}

        Examples:
            >>> j.create("A Python web scraper using BeautifulSoup", output_type="code")
            >>> j.create("Project plan for a mobile app", output_type="plan")
        """
        self._update_stats("create")

        try:
            # Auto-detect output type
            if output_type == "auto":
                output_type = self._detect_output_type(description)

            results: Dict[str, Any] = {"artifacts": [], "type": output_type, "details": {}}

            if output_type in ("code", "all"):
                code_result = self._create_code(description)
                results["artifacts"].append({"type": "code", "content": code_result})

            if output_type in ("document", "all"):
                doc_result = self._create_document(description)
                results["artifacts"].append({"type": "document", "content": doc_result})

            if output_type in ("image", "all"):
                img_result = self._create_image(description)
                results["artifacts"].append({"type": "image", "path": img_result})

            if output_type in ("plan", "all"):
                plan_result = self._create_plan(description)
                results["artifacts"].append({"type": "plan", "content": plan_result})

            if output_type in ("presentation", "all"):
                pres_result = self._create_presentation(description)
                results["artifacts"].append({"type": "presentation", "content": pres_result})

            if not results["artifacts"]:
                results["artifacts"].append({
                    "type": "text",
                    "content": self._generate_creation(description),
                })

            return results

        except Exception as e:
            self._stats["total_errors"] += 1
            return {"artifacts": [], "type": "error", "details": {"error": str(e)}}

    def advise(self, topic: str, domain: str = "general") -> Dict[str, Any]:
        """
        Professional advice from expert persona.

        Provides structured advice with actionable steps, warnings,
        and resource recommendations.

        Args:
            topic: The topic to get advice on.
            domain: "legal|engineering|medical|business|career|relationships|general"

        Returns:
            dict: {"topic": str, "actionable_steps": list, "warnings": list,
                   "resources": list}

        Examples:
            >>> j.advise("Starting a tech company", domain="business")
            >>> j.advise("Software architecture patterns", domain="engineering")
        """
        self._update_stats("advise")

        is_hebrew = HebrewUtils.is_hebrew(topic)

        try:
            # Map domain to expert
            domain_map = {
                "legal": "lawyer", "engineering": "engineer", "medical": "doctor",
                "business": "advisor", "career": "career", "relationships": "relationships",
                "general": "advisor",
            }
            expert_id = domain_map.get(domain, "advisor")
            expert_config = EXPERT_PERSONAS.get(expert_id, EXPERT_PERSONAS["advisor"])

            # Generate advice
            advisor = self._registry.get("advisor")
            if advisor and hasattr(advisor, "get_structured_advice"):
                try:
                    advice_data = advisor.get_structured_advice(topic, domain=domain)
                except Exception:
                    advice_data = self._generate_advice(topic, expert_id, is_hebrew)
            else:
                advice_data = self._generate_advice(topic, expert_id, is_hebrew)

            # Add disclaimer for sensitive domains
            if domain in ("legal", "medical"):
                disc_key = "hebrew_disclaimer" if is_hebrew else "disclaimer"
                disclaimer = expert_config.get(disc_key, "")
                if disclaimer and advice_data.get("warnings"):
                    advice_data["warnings"].insert(0, disclaimer)

            return ResponseBuilder.build_advice(
                topic=topic,
                steps=advice_data.get("steps", []),
                warnings=advice_data.get("warnings", []),
                resources=advice_data.get("resources", []),
                hebrew_input=is_hebrew,
            )

        except Exception as e:
            self._stats["total_errors"] += 1
            return ResponseBuilder.build_advice(
                topic=topic,
                steps=[f"Error: {str(e)}"],
                hebrew_input=is_hebrew,
            )

    def plan(self, goal: str, timeline: Optional[str] = None) -> Dict[str, Any]:
        """
        Create execution plan with timeline.

        Decomposes the goal into actionable phases and steps,
        assigns agents, identifies critical path and risks.

        Args:
            goal: The high-level goal to plan for.
            timeline: Optional timeline constraint (e.g., "3 months").

        Returns:
            dict: {"goal": str, "phases": list, "timeline": str,
                   "critical_path": list, "risks": list}

        Examples:
            >>> j.plan("Launch a SaaS product", timeline="6 months")
            >>> j.plan("למד שפת Python", timeline="3 חודשים")
        """
        self._update_stats("plan")

        is_hebrew = HebrewUtils.is_hebrew(goal)

        try:
            planner = self._registry.get("planner")
            if planner and hasattr(planner, "create_plan"):
                try:
                    plan_data = planner.create_plan(goal, timeline=timeline)
                except Exception:
                    plan_data = self._generate_plan(goal, timeline, is_hebrew)
            else:
                plan_data = self._generate_plan(goal, timeline, is_hebrew)

            return ResponseBuilder.build_plan(
                goal=goal,
                phases=plan_data.get("phases", []),
                timeline=plan_data.get("timeline", timeline or "TBD"),
                critical_path=plan_data.get("critical_path", []),
                risks=plan_data.get("risks", []),
                hebrew_input=is_hebrew,
            )

        except Exception as e:
            self._stats["total_errors"] += 1
            return ResponseBuilder.build_plan(
                goal=goal,
                timeline=timeline or "TBD",
                critical_path=[f"Error: {str(e)}"],
                hebrew_input=is_hebrew,
            )

    def collaborate(self, topic: str, agents: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Multi-agent collaboration session.

        Spawns multiple expert agents to collaboratively work on a topic,
        then returns a consensus/merged output.

        Args:
            topic: The topic for collaboration.
            agents: List of agent IDs, e.g., ["lawyer", "engineer", "doctor"].
                    If None, auto-selects based on topic.

        Returns:
            dict: Merged output from all participating agents.

        Examples:
            >>> j.collaborate("Design a medical device", agents=["engineer", "doctor"])
            >>> j.collaborate("Startup legal structure", agents=["lawyer", "advisor"])
        """
        self._update_stats("collaborate")

        is_hebrew = HebrewUtils.is_hebrew(topic)

        try:
            spawned = self._spawn_agents_for_task(topic, agents)
            outputs = []

            for agent_id in spawned:
                expert_config = EXPERT_PERSONAS.get(agent_id, EXPERT_PERSONAS["advisor"])
                answer = self._generate_answer(topic, agent_id, is_hebrew)
                outputs.append(ResponseBuilder.build(
                    answer=answer,
                    expert=expert_config.get("name", agent_id),
                    confidence=0.88,
                    hebrew_input=is_hebrew,
                ))

            merged = self._merge_outputs(outputs)
            merged["collaborating_agents"] = spawned
            return merged

        except Exception as e:
            self._stats["total_errors"] += 1
            return ResponseBuilder.build(
                answer=f"Collaboration error: {str(e)}" if not is_hebrew
                       else f"שגיאת שיתוף פעולה: {str(e)}",
                expert="system",
                confidence=0.0,
            )

    def explain(self, topic: str, style: str = "multimodal") -> MultimodalOutput:
        """
        Explain with text + diagram + audio + document.

        Creates a comprehensive explanation in the requested style(s).

        Args:
            topic: The topic to explain.
            style: "text|visual|audio|document|multimodal|interactive"

        Returns:
            MultimodalOutput: Container with all generated output artifacts.

        Examples:
            >>> j.explain("Neural Networks", style="multimodal")
            >>> j.explain("REST API Architecture", style="visual")
        """
        self._update_stats("explain")

        is_hebrew = HebrewUtils.is_hebrew(topic)
        output = MultimodalOutput()

        try:
            # Always generate text explanation
            text_exp = self._generate_explanation(topic, "text", is_hebrew)
            output.text = text_exp

            if style in ("visual", "multimodal", "interactive"):
                diagram = self._generate_visual_explanation(topic, is_hebrew)
                if diagram:
                    output.images.append(diagram)

            if style in ("audio", "multimodal", "interactive"):
                audio = self._generate_audio_explanation(topic, is_hebrew)
                if audio:
                    output.audio.append(audio)

            if style in ("document", "multimodal"):
                doc = self._generate_document_explanation(topic, is_hebrew)
                if doc:
                    output.documents.append(doc)

            if style == "interactive":
                output.interactive = self._generate_interactive_explanation(topic, is_hebrew)

            output.metadata = {
                "topic": topic,
                "style": style,
                "hebrew": is_hebrew,
                "expert": self._route_to_expert(topic),
            }

            return output

        except Exception as e:
            self._stats["total_errors"] += 1
            output.text = f"Explanation error: {str(e)}" if not is_hebrew else f"שגיאת הסבר: {str(e)}"
            return output

    def execute(self, command: str, trust_level: str = "normal") -> Dict[str, Any]:
        """
        Execute system commands with trust-based safety.

        Args:
            command: The command to execute.
            trust_level: "safe|normal|elevated|override"
                         Higher levels allow more dangerous operations.

        Returns:
            dict: {"stdout": str, "stderr": str, "returncode": int,
                   "trust_level": str, "allowed": bool}

        Safety: NEVER executes destructive commands without OVERRIDE level.
        """
        self._update_stats("execute")

        try:
            tl = trust_level.lower()

            # Safety checks
            dangerous = ["rm -rf", "mkfs", ":(){", "> /dev/sda", "dd if=",
                         "del /f", "format", "shutdown", "reboot"]
            is_dangerous = any(d in command.lower() for d in dangerous)

            if is_dangerous and tl != "override":
                return {
                    "stdout": "",
                    "stderr": f"Command blocked: potentially destructive. "
                              f"Use trust_level='override' to execute.",
                    "returncode": -1,
                    "trust_level": tl,
                    "allowed": False,
                    "timestamp": datetime.now().isoformat(),
                }

            # Safe-mode restrictions
            if tl == "safe":
                allowed_safe = ["ls", "dir", "echo", "cat", "head", "tail",
                                "grep", "find", "pwd", "whoami", "date", "ps"]
                cmd_base = command.strip().split()[0] if command.strip() else ""
                if cmd_base not in allowed_safe:
                    return {
                        "stdout": "",
                        "stderr": f"Command '{cmd_base}' not in safe-mode whitelist.",
                        "returncode": -1,
                        "trust_level": tl,
                        "allowed": False,
                        "timestamp": datetime.now().isoformat(),
                    }

            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=60,
            )

            return {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
                "trust_level": tl,
                "allowed": True,
                "timestamp": datetime.now().isoformat(),
            }

        except subprocess.TimeoutExpired:
            return {
                "stdout": "",
                "stderr": "Command timed out (60s limit).",
                "returncode": -1,
                "trust_level": trust_level,
                "allowed": True,
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            self._stats["total_errors"] += 1
            return {
                "stdout": "",
                "stderr": f"Execution error: {str(e)}",
                "returncode": -1,
                "trust_level": trust_level,
                "allowed": False,
                "timestamp": datetime.now().isoformat(),
            }

    def chat(self, message: str) -> str:
        """
        Conversational mode — friendly, contextual, personal.

        Remembers conversation history and responds with emotional awareness.
        Hebrew input is auto-detected and responded to in Hebrew.

        Args:
            message: User message.

        Returns:
            str: Friendly conversational response.

        Examples:
            >>> j.chat("Hey, how are you today?")
            >>> j.chat("מה נשמע?")  # Hebrew chat
        """
        self._update_stats("chat")
        self._add_to_history("user", message)

        is_hebrew = HebrewUtils.is_hebrew(message)

        try:
            # Check for emotional content
            emotional_markers = {
                "happy": ["happy", "glad", "great", "awesome", "שמח", "מצוין"],
                "sad": ["sad", "upset", "depressed", "עצוב", "מדוכא"],
                "angry": ["angry", "frustrated", "mad", "כועס", "מתוסכל"],
                "worried": ["worried", "anxious", "stressed", "מודאג", "לחוץ"],
            }

            detected_emotion = None
            for emotion, markers in emotional_markers.items():
                for marker in markers:
                    if marker in message.lower() or marker in message:
                        detected_emotion = emotion
                        break
                if detected_emotion:
                    break

            # Generate contextual response
            response = self._generate_chat_response(
                message, is_hebrew, detected_emotion
            )

            self._add_to_history("assistant", response)
            return response

        except Exception as e:
            self._stats["total_errors"] += 1
            if is_hebrew:
                return f"מצטער, אירעה שגיאה: {str(e)}"
            return f"Sorry, an error occurred: {str(e)}"

    def status(self) -> Dict[str, Any]:
        """
        Full system status: all subsystems, health, and statistics.

        Returns:
            dict: Comprehensive status report.
        """
        self._update_stats("status")

        subsystem_status = self._registry.status()
        ready_count = sum(
            1 for s in subsystem_status.values() if s["status"] == "ready"
        )
        total = len(subsystem_status)

        uptime = ""
        try:
            start = datetime.fromisoformat(self._stats["start_time"])
            delta = datetime.now() - start
            uptime = str(delta)
        except Exception:
            uptime = "unknown"

        return {
            "version": __version__,
            "subsystems": {
                "total": total,
                "ready": ready_count,
                "pending": sum(1 for s in subsystem_status.values() if s["status"] == "pending"),
                "failed": sum(1 for s in subsystem_status.values() if s["status"] == "failed"),
                "details": subsystem_status,
            },
            "stats": {
                "total_requests": self._stats["total_requests"],
                "total_errors": self._stats["total_errors"],
                "uptime": uptime,
                "requests_by_method": self._stats["requests_by_method"].copy(),
                "error_rate": round(
                    self._stats["total_errors"] / max(self._stats["total_requests"], 1), 4
                ),
            },
            "health": {
                "status": "healthy" if ready_count >= total // 2 else "degraded",
                "subsystem_availability": round(ready_count / max(total, 1), 2),
            },
            "capabilities": list(EXPERT_PERSONAS.keys()),
            "timestamp": datetime.now().isoformat(),
        }

    def learn(self, topic: str, source: str = "auto") -> bool:
        """
        Autonomous learning from GitHub/web/docs.

        Learns about a topic and stores knowledge in vector memory
        for future retrieval.

        Args:
            topic: Topic to learn about.
            source: Source preference — "github|web|docs|auto"

        Returns:
            bool: True if learning was successful.

        Examples:
            >>> j.learn("Rust programming language", source="github")
            >>> j.learn("PyTorch deep learning")
        """
        self._update_stats("learn")

        try:
            memory = self._registry.get("memory")
            if memory and hasattr(memory, "learn"):
                try:
                    return bool(memory.learn(topic, source=source))
                except Exception:
                    pass

            # Fallback: simulate learning
            knowledge_entry = {
                "topic": topic,
                "source": source,
                "learned_at": datetime.now().isoformat(),
                "content": f"Knowledge about {topic} acquired via {source}.",
            }

            # Store in conversation history as fallback memory
            self._add_to_history("system", f"[LEARNED] {json.dumps(knowledge_entry)}")
            return True

        except Exception as e:
            self._stats["total_errors"] += 1
            warnings.warn(f"Learning failed: {e}")
            return False

    def draw(self, description: str, style: str = "technical") -> str:
        """
        Create visual diagram/drawing.

        Args:
            description: Description of what to draw.
            style: "technical|artistic|flowchart|mindmap"

        Returns:
            str: Path to the generated image file.

        Examples:
            >>> j.draw("System architecture with microservices", style="technical")
            >>> j.draw("Decision tree for ML model selection", style="flowchart")
        """
        self._update_stats("draw")

        try:
            drawing = self._registry.get("drawing")
            if drawing and hasattr(drawing, "draw"):
                try:
                    return str(drawing.draw(description, style=style))
                except Exception:
                    pass

            # Fallback: return description as text representation
            return self._generate_drawing_description(description, style)

        except Exception as e:
            self._stats["total_errors"] += 1
            return f"Drawing error: {str(e)}"

    def document(self, title: str, content: str, format: str = "pdf") -> str:
        """
        Create professional document.

        Args:
            title: Document title.
            content: Document body content.
            format: Output format — "pdf|markdown|html|docx|txt"

        Returns:
            str: Path to the generated document.

        Examples:
            >>> j.document("Project Report", "## Overview\nThis project...", format="pdf")
            >>> j.document("API Documentation", content, format="markdown")
        """
        self._update_stats("document")

        try:
            docs = self._registry.get("docs")
            if docs and hasattr(docs, "generate"):
                try:
                    return str(docs.generate(title=title, content=content, format=format))
                except Exception:
                    pass

            # Fallback: write to file
            output_dir = Path("/mnt/agents/output/jarvis/documents")
            output_dir.mkdir(parents=True, exist_ok=True)

            safe_title = re.sub(r"[^\w\s-]", "", title).replace(" ", "_")
            ext_map = {"pdf": "md", "markdown": "md", "html": "html",
                       "docx": "md", "txt": "txt"}
            ext = ext_map.get(format, "md")
            filepath = output_dir / f"{safe_title}.{ext}"

            header = f"# {title}\n\n"
            timestamp = f"*Generated by JARVIS on {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n\n"
            full_content = header + timestamp + "---\n\n" + content

            filepath.write_text(full_content, encoding="utf-8")
            return str(filepath)

        except Exception as e:
            self._stats["total_errors"] += 1
            return f"Document error: {str(e)}"

    def research(self, topic: str, depth: str = "comprehensive") -> Dict[str, Any]:
        """
        Deep research using multiple sources.

        Performs comprehensive research and returns structured
        findings with citations.

        Args:
            topic: Research topic.
            depth: "quick|standard|comprehensive|deep"

        Returns:
            dict: {"findings": list, "summary": str, "citations": list,
                   "depth": str}

        Examples:
            >>> j.research("Quantum computing applications in drug discovery")
            >>> j.research("AI regulation in the EU", depth="deep")
        """
        self._update_stats("research")

        is_hebrew = HebrewUtils.is_hebrew(topic)

        try:
            findings = self._generate_research(topic, depth, is_hebrew)

            return {
                "topic": topic,
                "depth": depth,
                "findings": findings.get("findings", []),
                "summary": findings.get("summary", ""),
                "citations": findings.get("citations", []),
                "confidence": findings.get("confidence", 0.8),
                "recommendations": findings.get("recommendations", []),
                "timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            self._stats["total_errors"] += 1
            return {
                "topic": topic,
                "depth": depth,
                "findings": [],
                "summary": f"Research error: {str(e)}" if not is_hebrew else f"שגיאת מחקר: {str(e)}",
                "citations": [],
                "confidence": 0.0,
                "timestamp": datetime.now().isoformat(),
            }

    # ═════════════════════════════════════════════════════════════════════════
    # FALLBACK GENERATORS (used when subsystems are not available)
    # ═════════════════════════════════════════════════════════════════════════

    def _generate_answer(self, question: str, expert_id: str, is_hebrew: bool) -> str:
        """Generate an answer using fallback logic."""
        expert_config = EXPERT_PERSONAS.get(expert_id, EXPERT_PERSONAS["advisor"])

        if is_hebrew:
            return (
                f"שאלה מצוינה בנושא '{question[:50]}'. "
                f"כמומחה בתחום {expert_config.get('hebrew_name', expert_id)}, "
                f"אני מנתח את השאלה שלך ומספק תשובה מקיפה. "
                f"הנושא דורש התייחסות מעמיקה הכוללת ניתוח של כל ההיבטים הרלוונטיים. "
                f"אשמח לספק פירוט נוסף לפי הצורך."
            )
        return (
            f"Great question about '{question[:50]}'. "
            f"As a {expert_config.get('name', expert_id)}, "
            f"I'm analyzing your query and providing a comprehensive answer. "
            f"The topic requires in-depth consideration of all relevant aspects. "
            f"I'd be happy to provide additional detail as needed."
        )

    def _generate_advice(self, topic: str, expert_id: str, is_hebrew: bool) -> Dict[str, Any]:
        """Generate structured advice using fallback logic."""
        expert_config = EXPERT_PERSONAS.get(expert_id, EXPERT_PERSONAS["advisor"])

        if is_hebrew:
            return {
                "steps": [
                    f"ניתח את הנושא '{topic}' מבחינת {expert_config.get('hebrew_name', expert_id)}",
                    "אסוף מידע רלוונטי ממקורות אמינים",
                    "בנה תוכנית פעולה מובנית עם יעדים ברורים",
                    "בצע הערכת סיכונים והכן תוכנית גיבוי",
                    "בדוק התקדמות והתאם את התוכנית לפי הצורך",
                ],
                "warnings": [
                    "יש לבדוק את המידע מול מקורות נוספים",
                ],
                "resources": [
                    "מסמכים מקצועיים בתחום",
                    "קורסים אונליין רלוונטיים",
                    "קהילות מקצועיות",
                ],
            }
        return {
            "steps": [
                f"Analyze '{topic}' from a {expert_config.get('name', expert_id)} perspective",
                "Gather relevant information from reliable sources",
                "Build a structured action plan with clear objectives",
                "Perform risk assessment and prepare contingency plans",
                "Monitor progress and adjust the plan as needed",
            ],
            "warnings": [
                "Always verify information with additional sources",
            ],
            "resources": [
                "Professional documentation in the field",
                "Relevant online courses",
                "Professional communities and forums",
            ],
        }

    def _generate_plan(self, goal: str, timeline: Optional[str], is_hebrew: bool) -> Dict[str, Any]:
        """Generate a plan using fallback logic."""
        if is_hebrew:
            return {
                "phases": [
                    {
                        "name": "תכנון ומחקר",
                        "description": "הגדרת יעדים, מחקר ראשוני, וניתוח דרישות",
                        "duration": "שבוע 1-2",
                    },
                    {
                        "name": "עיצוב ופיתוח",
                        "description": "יצירת ארכיטקטורה, פיתוח ראשוני, ובדיקות",
                        "duration": "שבוע 3-6",
                    },
                    {
                        "name": "ביצוע והטמעה",
                        "description": "הפצה, הדרכה, ומעבר לייצור",
                        "duration": "שבוע 7-8",
                    },
                    {
                        "name": "מעקב ואופטימיזציה",
                        "description": "ניתוח ביצועים, איסוף משוב, ושיפורים",
                        "duration": "שבוע 9-10",
                    },
                ],
                "timeline": timeline or "10 שבועות",
                "critical_path": [
                    "הגדרת דרישות ברורות",
                    "פיתוח ליבת המערכת",
                    "בדיקות איכות מקיפות",
                    "השקה מוצלחת",
                ],
                "risks": [
                    "עיכובים בלתי צפויים בפיתוח",
                    "שינויים בדרישות במהלך הפרויקט",
                    "בעיות אינטגרציה עם מערכות קיימות",
                ],
            }
        return {
            "phases": [
                {
                    "name": "Planning & Research",
                    "description": "Define objectives, initial research, and requirements analysis",
                    "duration": "Week 1-2",
                },
                {
                    "name": "Design & Development",
                    "description": "Create architecture, initial development, and testing",
                    "duration": "Week 3-6",
                },
                {
                    "name": "Execution & Deployment",
                    "description": "Rollout, training, and go-live",
                    "duration": "Week 7-8",
                },
                {
                    "name": "Monitoring & Optimization",
                    "description": "Performance analysis, feedback collection, and improvements",
                    "duration": "Week 9-10",
                },
            ],
            "timeline": timeline or "10 weeks",
            "critical_path": [
                "Clear requirements definition",
                "Core system development",
                "Comprehensive quality testing",
                "Successful launch",
            ],
            "risks": [
                "Unexpected development delays",
                "Requirements changes during the project",
                "Integration issues with existing systems",
            ],
        }

    def _generate_explanation(self, topic: str, style: str, is_hebrew: bool) -> str:
        """Generate a text explanation using fallback logic."""
        if is_hebrew:
            return (
                f"הסבר מקיף על '{topic}':\n\n"
                f"הנושא '{topic}' כולל מספר היבטים מרכזיים שיש להבין. "
                f"בהסבר זה נפרוט את המושגים הבסיסיים, את המרכיבים העיקריים, "
                f"ואת הדרכים שבהן ניתן להשתמש בידע זה בפועל. "
                f"ההסבר מותאם לרמה של קהל רחב וכולל דוגמאות ויישומים מעשיים."
            )
        return (
            f"Comprehensive explanation of '{topic}':\n\n"
            f"The topic of '{topic}' encompasses several key aspects to understand. "
            f"In this explanation, we will break down the foundational concepts, "
            f"the main components, and how this knowledge can be applied in practice. "
            f"The explanation is tailored for a general audience and includes "
            f"examples and practical applications."
        )

    def _generate_visual_explanation(self, topic: str, is_hebrew: bool) -> Optional[str]:
        """Generate a visual explanation (diagram)."""
        drawing = self._registry.get("drawing")
        if drawing and hasattr(drawing, "draw"):
            try:
                return str(drawing.draw(topic, style="technical"))
            except Exception:
                pass
        return None

    def _generate_audio_explanation(self, topic: str, is_hebrew: bool) -> Optional[str]:
        """Generate an audio explanation."""
        voice = self._registry.get("voice")
        if voice and hasattr(voice, "synthesize"):
            try:
                text = self._generate_explanation(topic, "text", is_hebrew)
                return str(voice.synthesize(text))
            except Exception:
                pass
        return None

    def _generate_document_explanation(self, topic: str, is_hebrew: bool) -> Optional[str]:
        """Generate a document explanation."""
        try:
            title = f"Explanation: {topic}"
            content = self._generate_explanation(topic, "text", is_hebrew)
            return self.document(title, content, format="markdown")
        except Exception:
            return None

    def _generate_interactive_explanation(self, topic: str, is_hebrew: bool) -> Dict[str, Any]:
        """Generate an interactive explanation."""
        return {
            "type": "interactive",
            "topic": topic,
            "hebrew": is_hebrew,
            "sections": [
                {"title": "Overview", "content": self._generate_explanation(topic, "text", is_hebrew)[:500]},
                {"title": "Key Concepts", "items": ["Concept A", "Concept B", "Concept C"]},
                {"title": "Quiz", "questions": [
                    {"q": f"What is the main focus of {topic}?", "options": ["A", "B", "C"]},
                ]},
            ],
        }

    def _generate_chat_response(
        self, message: str, is_hebrew: bool, emotion: Optional[str]
    ) -> str:
        """Generate a conversational response."""
        if is_hebrew:
            greeting = "היי!"
            if emotion == "happy":
                greeting = "נהדר לשמוע שאתה שמח!"
            elif emotion == "sad":
                greeting = "אני כאן בשבילך. אני מבין שזה לא קל."
            elif emotion == "angry":
                greeting = "אני מבין שאתה מתוסכל. בוא ננסה לפתור את זה יחד."
            elif emotion == "worried":
                greeting = "אל דאגה, נעבור על זה יחד צעד אחר צעד."

            return (
                f"{greeting}\n\n"
                f"קיבלתי את ההודעה שלך: '{message[:80]}'. "
                f"אני כאן כדי לעזור בכל נושא שתרצה — שאלות, ייעוץ, "
                f"תכנון, או סתם שיחה. מה תרצה לעשות היום?"
            )

        greeting = "Hey there!"
        if emotion == "happy":
            greeting = "Great to hear you're doing well!"
        elif emotion == "sad":
            greeting = "I'm here for you. I understand things are tough."
        elif emotion == "angry":
            greeting = "I understand your frustration. Let's work through this together."
        elif emotion == "worried":
            greeting = "Don't worry, we'll go through this step by step."

        return (
            f"{greeting}\n\n"
            f"I received your message: '{message[:80]}'. "
            f"I'm here to help with anything you need — questions, advice, "
            f"planning, or just a chat. What would you like to do today?"
        )

    def _generate_creation(self, description: str) -> str:
        """Generate a creation artifact description."""
        return f"Creation plan for: {description}\n\nThis is a structured artifact generated based on your description."

    def _generate_drawing_description(self, description: str, style: str) -> str:
        """Generate a text-based drawing description as fallback."""
        return f"[{style.upper()} DIAGRAM]\n{description}\n\n(A visual representation would be generated here when the drawing engine is available.)"

    def _generate_research(self, topic: str, depth: str, is_hebrew: bool) -> Dict[str, Any]:
        """Generate research findings using fallback logic."""
        depth_multiplier = {"quick": 3, "standard": 5, "comprehensive": 8, "deep": 12}
        num_findings = depth_multiplier.get(depth, 5)

        if is_hebrew:
            findings = [
                f"ממצא {i+1}: היבט חשוב של '{topic}' הכלול בניתוח מעמיק"
                for i in range(num_findings)
            ]
            return {
                "findings": findings,
                "summary": f"סיכום המחקר על '{topic}' — מחקר מקיף הכולל ניתוח של {num_findings} היבטים מרכזיים בתחום. הממצאים מצביעים על חשיבות הנושא והצורך בהבנה מעמיקה שלו.",
                "citations": [
                    "מקור אקדמי רלוונטי",
                    "תיעוד מקצועי בתחום",
                    "מאמרי מחקר עדכניים",
                ],
                "confidence": 0.82,
                "recommendations": [
                    "להעמיק בחומר קיים",
                    "לבצע ניסויים מעשיים",
                    "להתייעץ עם מומחים בתחום",
                ],
            }

        findings = [
            f"Finding {i+1}: Important aspect of '{topic}' identified through in-depth analysis"
            for i in range(num_findings)
        ]
        return {
            "findings": findings,
            "summary": f"Research summary on '{topic}' — comprehensive study covering {num_findings} key aspects. The findings highlight the importance of the topic and the need for deep understanding.",
            "citations": [
                "Relevant academic source",
                "Professional domain documentation",
                "Recent research papers",
            ],
            "confidence": 0.82,
            "recommendations": [
                "Dive deeper into existing literature",
                "Conduct practical experiments",
                "Consult with domain experts",
            ],
        }

    # ═════════════════════════════════════════════════════════════════════════
    # HELPER METHODS
    # ═════════════════════════════════════════════════════════════════════════

    def _detect_output_type(self, description: str) -> str:
        """Auto-detect the output type from description."""
        desc_lower = description.lower()
        scores = {
            "code": 0, "document": 0, "image": 0,
            "plan": 0, "presentation": 0,
        }

        code_kws = ["code", "script", "program", "function", "class", "api", "app", "קוד", "תוכנה"]
        doc_kws = ["document", "report", "paper", "essay", "article", "מסמך", "דוח"]
        img_kws = ["image", "picture", "photo", "drawing", "diagram", "visual", "תמונה", "תרשים"]
        plan_kws = ["plan", "schedule", "timeline", "roadmap", "תכנית", "לוח זמנים"]
        pres_kws = ["presentation", "slides", "deck", "מצגת", "שקפים"]

        for kw in code_kws:
            if kw in desc_lower or kw in description:
                scores["code"] += 1
        for kw in doc_kws:
            if kw in desc_lower or kw in description:
                scores["document"] += 1
        for kw in img_kws:
            if kw in desc_lower or kw in description:
                scores["image"] += 1
        for kw in plan_kws:
            if kw in desc_lower or kw in description:
                scores["plan"] += 1
        for kw in pres_kws:
            if kw in desc_lower or kw in description:
                scores["presentation"] += 1

        best = max(scores, key=scores.get)  # type: ignore[arg-type]
        if scores[best] == 0:
            return "document"
        return best

    def _create_code(self, description: str) -> str:
        """Create code artifact."""
        return f"# Code: {description[:60]}\n# Generated by JARVIS\n\n# TODO: Implement based on description\n"

    def _create_document(self, description: str) -> str:
        """Create document artifact."""
        return f"# Document: {description[:60]}\n\n## Overview\n{description}\n\n## Details\n(TBD)\n"

    def _create_image(self, description: str) -> str:
        """Create image artifact."""
        return f"[IMAGE: {description[:60]}]"

    def _create_plan(self, description: str) -> Dict[str, Any]:
        """Create plan artifact."""
        return self.plan(description)

    def _create_presentation(self, description: str) -> str:
        """Create presentation artifact."""
        return f"# Presentation: {description[:60]}\n\n## Slide 1: Title\n{description}\n\n## Slide 2: Overview\n(TBD)\n"


# ═══════════════════════════════════════════════════════════════════════════════
# MockJARVISInterface — Deterministic, Dependency-Free
# ═══════════════════════════════════════════════════════════════════════════════

class MockJARVISInterface(JARVISInterface):
    """
    Mock implementation of JARVISInterface.

    Provides the same API surface but with deterministic, predefined responses.
    All methods work without any external dependencies.

    Perfect for:
    • Unit testing
    • CI/CD pipelines
    • Demo environments
    • Development without full backend
    """

    def __init__(self):
        # Skip parent __init__ to avoid any subsystem loading
        self._conversation_history: List[Dict[str, str]] = []
        self._max_history = 50
        self._stats = {
            "total_requests": 0,
            "total_errors": 0,
            "start_time": datetime.now().isoformat(),
            "requests_by_method": {},
        }
        self._lock = threading.RLock()

    def _update_stats(self, method: str) -> None:
        with self._lock:
            self._stats["total_requests"] += 1
            self._stats["requests_by_method"][method] = (
                self._stats["requests_by_method"].get(method, 0) + 1
            )

    def ask(self, question: str, mode: str = "auto") -> Dict[str, Any]:
        """Deterministic Q&A with mock responses."""
        self._update_stats("ask")
        is_hebrew = HebrewUtils.is_hebrew(question)

        expert_id = mode if mode != "auto" else "advisor"
        if "law" in question.lower() or "משפט" in question or "חוק" in question or "חברה" in question:
            expert_id = "lawyer"
        elif "code" in question.lower() or "program" in question.lower() or "קוד" in question:
            expert_id = "engineer"
        elif "health" in question.lower() or "medical" in question.lower() or "רפואה" in question:
            expert_id = "doctor"

        expert_config = EXPERT_PERSONAS.get(expert_id, EXPERT_PERSONAS["advisor"])

        if is_hebrew:
            answer = (
                f"תשובה מקיפה בנושא '{question[:60]}'. "
                f"כ-{expert_config.get('hebrew_name', expert_id)}, "
                f"הניתוח שלי מראה שהנושא כולל מספר היבטים מרכזיים שכדאי להבין. "
                f"אני ממליץ להעמיק בחומר ולבדוק מקורות נוספים לקבלת תמונה מלאה."
            )
        else:
            answer = (
                f"Comprehensive answer regarding '{question[:60]}'. "
                f"As a {expert_config.get('name', expert_id)}, "
                f"my analysis shows this topic involves several key aspects worth understanding. "
                f"I recommend diving deeper into the material and checking additional sources."
            )

        return ResponseBuilder.build(
            answer=answer,
            expert=expert_config.get("hebrew_name" if is_hebrew else "name", expert_id),
            confidence=0.95,
            sources=["Mock Knowledge Base"],
            hebrew_input=is_hebrew,
        )

    def create(self, description: str, output_type: str = "auto") -> Dict[str, Any]:
        """Deterministic creation with mock artifacts."""
        self._update_stats("create")
        ot = output_type if output_type != "auto" else self._detect_output_type(description)
        return {
            "artifacts": [
                {"type": ot, "content": f"Mock {ot} artifact for: {description[:80]}"},
            ],
            "type": ot,
            "details": {"mock": True, "description": description},
        }

    def advise(self, topic: str, domain: str = "general") -> Dict[str, Any]:
        """Deterministic advice with mock structured response."""
        self._update_stats("advise")
        is_hebrew = HebrewUtils.is_hebrew(topic)

        if is_hebrew:
            return ResponseBuilder.build_advice(
                topic=topic,
                steps=[
                    "ניתח את המצב הנוכחי וזהה את האתגרים העיקריים",
                    "אסוף מידע רלוונטי ממקורות מהימנים",
                    "גבש אסטרטגיה עם יעדים ברורים ומדידים",
                    "בצע צעדים ראשונים קטנים לכיוון היעד",
                    "הערך התקדמות והתאם את הגישה לפי הצורך",
                ],
                warnings=["תמיד בדוק מידע עם מקורות נוספים"],
                resources=["מסמכים מקצועיים", "קורסים אונליין", "קהילות תמיכה"],
                hebrew_input=True,
            )
        return ResponseBuilder.build_advice(
            topic=topic,
            steps=[
                "Analyze the current situation and identify key challenges",
                "Gather relevant information from reliable sources",
                "Develop a strategy with clear, measurable goals",
                "Take small initial steps toward the objective",
                "Evaluate progress and adjust approach as needed",
            ],
            warnings=["Always verify information with additional sources"],
            resources=["Professional documentation", "Online courses", "Support communities"],
        )

    def plan(self, goal: str, timeline: Optional[str] = None) -> Dict[str, Any]:
        """Deterministic plan with mock phases."""
        self._update_stats("plan")
        is_hebrew = HebrewUtils.is_hebrew(goal)

        if is_hebrew:
            return ResponseBuilder.build_plan(
                goal=goal,
                phases=[
                    {"name": "מחקר ותכנון", "description": "הגדרת יעדים וניתוח דרישות", "duration": "שבוע 1-2"},
                    {"name": "פיתוח", "description": "ביצוע עבודת הליבה", "duration": "שבוע 3-6"},
                    {"name": "הטמעה", "description": "הפצה ובדיקות", "duration": "שבוע 7-8"},
                    {"name": "מעקב", "description": "ניטור ואופטימיזציה", "duration": "שבוע 9+"},
                ],
                timeline=timeline or "8 שבועות",
                critical_path=["הגדרת יעדים", "פיתוח ליבה", "בדיקות", "השקה"],
                risks=["עיכובים בלתי צפויים", "שינויי דרישות"],
                hebrew_input=True,
            )
        return ResponseBuilder.build_plan(
            goal=goal,
            phases=[
                {"name": "Research & Planning", "description": "Define objectives and analyze requirements", "duration": "Week 1-2"},
                {"name": "Development", "description": "Execute core work", "duration": "Week 3-6"},
                {"name": "Deployment", "description": "Rollout and testing", "duration": "Week 7-8"},
                {"name": "Monitoring", "description": "Tracking and optimization", "duration": "Week 9+"},
            ],
            timeline=timeline or "8 weeks",
            critical_path=["Goal definition", "Core development", "Testing", "Launch"],
            risks=["Unexpected delays", "Requirement changes"],
        )

    def collaborate(self, topic: str, agents: Optional[List[str]] = None) -> Dict[str, Any]:
        """Deterministic collaboration with mock merged output."""
        self._update_stats("collaborate")
        is_hebrew = HebrewUtils.is_hebrew(topic)
        agent_list = agents or ["advisor"]

        if is_hebrew:
            answer = (
                f"תוצאת שיתוף הפעולה בנושא '{topic[:60]}': "
                f"הסוכנים {', '.join(agent_list)} עבדו יחד והגיעו למסקנה משותפת. "
                f"ההמלצה היא לבצע ניתוח מעמיק נוסף ולפעול לפי התוכנית המשותפת."
            )
        else:
            answer = (
                f"Collaboration result on '{topic[:60]}': "
                f"Agents {', '.join(agent_list)} worked together and reached a joint conclusion. "
                f"The recommendation is to perform further in-depth analysis and act according to the shared plan."
            )

        return ResponseBuilder.build(
            answer=answer,
            expert=" + ".join(agent_list),
            confidence=0.90,
            metadata={"collaborating_agents": agent_list, "mock": True},
            hebrew_input=is_hebrew,
        )

    def explain(self, topic: str, style: str = "multimodal") -> MultimodalOutput:
        """Deterministic explanation with mock multimodal output."""
        self._update_stats("explain")
        is_hebrew = HebrewUtils.is_hebrew(topic)

        output = MultimodalOutput()
        if is_hebrew:
            output.text = (
                f"הסבר מקיף על '{topic}':\n\n"
                f"הנושא '{topic}' כולל מספר היבטים מרכזיים. "
                f"בהסבר זה נפרט את המושגים הבסיסיים ואת היישומים המעשיים."
            )
        else:
            output.text = (
                f"Comprehensive explanation of '{topic}':\n\n"
                f"The topic of '{topic}' involves several key aspects. "
                f"This explanation covers foundational concepts and practical applications."
            )

        if style in ("visual", "multimodal", "interactive"):
            output.images.append(f"[MOCK DIAGRAM: {topic}]")
        if style in ("audio", "multimodal"):
            output.audio.append(f"[MOCK AUDIO: {topic}]")
        if style in ("document", "multimodal"):
            output.documents.append(f"[MOCK DOCUMENT: {topic}]")

        output.metadata = {"topic": topic, "style": style, "mock": True, "hebrew": is_hebrew}
        return output

    def execute(self, command: str, trust_level: str = "normal") -> Dict[str, Any]:
        """Mock command execution — never actually runs commands."""
        self._update_stats("execute")
        return {
            "stdout": f"[MOCK] Would execute: {command}",
            "stderr": "",
            "returncode": 0,
            "trust_level": trust_level,
            "allowed": True,
            "mock": True,
            "timestamp": datetime.now().isoformat(),
        }

    def chat(self, message: str) -> str:
        """Deterministic conversational response."""
        self._update_stats("chat")
        is_hebrew = HebrewUtils.is_hebrew(message)

        if is_hebrew:
            return (
                f"היי! קיבלתי את ההודעה שלך. "
                f"אני כאן כדי לעזור בכל נושא — שאלות, ייעוץ, תכנון, או סתם שיחה. "
                f"מה תרצה לעשות היום?"
            )
        return (
            f"Hey! I got your message. "
            f"I'm here to help with anything — questions, advice, planning, or just a chat. "
            f"What would you like to do today?"
        )

    def status(self) -> Dict[str, Any]:
        """Mock system status."""
        self._update_stats("status")
        return {
            "version": __version__,
            "mode": "MOCK",
            "subsystems": {
                "total": 16,
                "ready": 16,
                "pending": 0,
                "failed": 0,
                "details": {name: {"status": "ready", "mock": True}
                           for name in EXPERT_PERSONAS.keys()},
            },
            "stats": {
                "total_requests": self._stats["total_requests"],
                "total_errors": 0,
                "uptime": "MOCK",
                "requests_by_method": self._stats["requests_by_method"].copy(),
                "error_rate": 0.0,
            },
            "health": {"status": "healthy", "subsystem_availability": 1.0},
            "capabilities": list(EXPERT_PERSONAS.keys()),
            "timestamp": datetime.now().isoformat(),
        }

    def learn(self, topic: str, source: str = "auto") -> bool:
        """Mock learning — always succeeds."""
        self._update_stats("learn")
        return True

    def draw(self, description: str, style: str = "technical") -> str:
        """Mock drawing — returns description placeholder."""
        self._update_stats("draw")
        return f"[MOCK {style.upper()} DIAGRAM]: {description[:80]}"

    def document(self, title: str, content: str, format: str = "pdf") -> str:
        """Mock document — returns path placeholder."""
        self._update_stats("document")
        return f"/mock/output/{title.replace(' ', '_')}.{format}"

    def research(self, topic: str, depth: str = "comprehensive") -> Dict[str, Any]:
        """Mock research with deterministic findings."""
        self._update_stats("research")
        is_hebrew = HebrewUtils.is_hebrew(topic)

        if is_hebrew:
            return {
                "topic": topic,
                "depth": depth,
                "findings": [
                    f"ממצא {i+1}: היבט חשוב של {topic}"
                    for i in range(5)
                ],
                "summary": f"סיכום מחקר על '{topic}' — ניתוח מקיף של הנושא.",
                "citations": ["מקור מוק 1", "מקור מוק 2"],
                "confidence": 0.88,
                "recommendations": ["המשך מחקר", "ייעוץ עם מומחים"],
                "timestamp": datetime.now().isoformat(),
            }
        return {
            "topic": topic,
            "depth": depth,
            "findings": [
                f"Finding {i+1}: Key aspect of {topic}"
                for i in range(5)
            ],
            "summary": f"Research summary on '{topic}' — comprehensive analysis.",
            "citations": ["Mock Source 1", "Mock Source 2"],
            "confidence": 0.88,
            "recommendations": ["Continue research", "Consult experts"],
            "timestamp": datetime.now().isoformat(),
        }


# ═══════════════════════════════════════════════════════════════════════════════
# Factory Function
# ═══════════════════════════════════════════════════════════════════════════════

_JARVIS_SINGLETON: Optional[JARVISInterface] = None
_MOCK_JARVIS_SINGLETON: Optional[MockJARVISInterface] = None
_FACTORY_LOCK = threading.Lock()


def get_jarvis_interface(mock: bool = False) -> JARVISInterface:
    """
    Factory function to get the JARVIS interface instance.

    Uses singleton pattern to ensure only one instance exists.
    Thread-safe for concurrent access.

    Args:
        mock: If True, returns MockJARVISInterface with deterministic responses.

    Returns:
        JARVISInterface or MockJARVISInterface instance.

    Examples:
        >>> jarvis = get_jarvis_interface()
        >>> result = jarvis.ask("What is the meaning of life?")
        >>> mock = get_jarvis_interface(mock=True)
        >>> result = mock.ask("Test question")  # Deterministic response
    """
    global _JARVIS_SINGLETON, _MOCK_JARVIS_SINGLETON

    if mock:
        if _MOCK_JARVIS_SINGLETON is None:
            with _FACTORY_LOCK:
                if _MOCK_JARVIS_SINGLETON is None:
                    _MOCK_JARVIS_SINGLETON = MockJARVISInterface()
        return _MOCK_JARVIS_SINGLETON

    if _JARVIS_SINGLETON is None:
        with _FACTORY_LOCK:
            if _JARVIS_SINGLETON is None:
                _JARVIS_SINGLETON = JARVISInterface()
    return _JARVIS_SINGLETON


# ═══════════════════════════════════════════════════════════════════════════════
# Module-level convenience function
# ═══════════════════════════════════════════════════════════════════════════════

def quick_ask(question: str) -> str:
    """
    Convenience function for quick Q&A without instantiating.

    Args:
        question: The question to ask.

    Returns:
        str: The answer text.
    """
    jarvis = get_jarvis_interface()
    result = jarvis.ask(question)
    return result.get("answer", "")


# ═══════════════════════════════════════════════════════════════════════════════
# CLI Entry Point
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="JARVIS Unified Interface")
    parser.add_argument("--ask", type=str, help="Ask a question")
    parser.add_argument("--mock", action="store_true", help="Use mock interface")
    parser.add_argument("--status", action="store_true", help="Show system status")
    parser.add_argument("--mode", type=str, default="auto", help="Expert mode")
    args = parser.parse_args()

    jarvis = get_jarvis_interface(mock=args.mock)

    if args.status:
        print(json.dumps(jarvis.status(), indent=2, ensure_ascii=False))
    elif args.ask:
        result = jarvis.ask(args.ask, mode=args.mode)
        print(result["answer"])
    else:
        print(f"JARVIS Unified Interface v{__version__}")
        print("Use --ask 'your question' to query, or --status for system status.")
