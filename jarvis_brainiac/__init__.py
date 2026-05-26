"""
JARVIS BRAINIAC — Singularity Orchestrator
==========================================
Unified entry point for the entire agency-agents ecosystem.

Architecture (v1.0.0-singularity):
    JARVIS BRAINIAC = AgentRegistry + Orchestrator + CloudSync + UnifiedMemory
                    + FreeLLM + IdeaToAgentsPipeline + WebsiteBuilder
                    + UnifiedMemoryEngine (cross-session persistence)
                       ↓ wraps ↓
                   agency-agents/runtime  (Pass 14-20 canonical modules)
                   jarvis/ (109 specialty mods)
                   integrations/ (12 tool adapters)

Single source of truth: GitHub `amjad2161/agency-agents` (501 files canonical)
Local workspace: this directory (synchronized via cloud_sync.py)
"""

__version__ = "1.0.0-singularity"
__author__ = "Amjad Mobarsham"
__github__ = "https://github.com/amjad2161/agency-agents"

from .agent_registry import AgentRegistry
from .orchestrator import Orchestrator
from .cloud_sync import CloudSync
from .memory import UnifiedMemory
from .free_llm import FreeLLM, get_llm, quick_chat
from .unified_memory_engine import UnifiedMemoryEngine, get_memory, quick_search

__all__ = [
    # Core
    "AgentRegistry",
    "Orchestrator",
    "CloudSync",
    "UnifiedMemory",
    # LLM
    "FreeLLM",
    "get_llm",
    "quick_chat",
    # Persistent Knowledge
    "UnifiedMemoryEngine",
    "get_memory",
    "quick_search",
]
