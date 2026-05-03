"""
JARVIS BRAINIAC - External Repository Integration Bridges
=========================================================

This package contains bridge modules that connect JARVIS BRAINIAC with
external AI agent projects. Each bridge provides:

- Consistent interface wrapping external APIs
- Mock fallbacks when dependencies are not installed
- health_check() and metadata() methods
- Import-safe (no errors when external project not installed)

Available bridges:
    - agenticseek_bridge: AgenticSeek (Fosowl/agenticSeek) - local Manus AI
    - openmanus_bridge: OpenManus (FoundationAgents/OpenManus) - Manus replication
    - lemonai_bridge: Lemon AI (hexdocom/lemonai) - self-evolving AI agent
    - uifacts_bridge: UI-TARS (bytedance/UI-TARS) - multimodal GUI agent
    - opencode_bridge: opencode (opencode-ai/opencode) - coding agent

Usage:
    from external_integrations import get_agenticseek_bridge
    bridge = get_agenticseek_bridge()
    plan = bridge.plan_task("Build an API")
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

def _lazy_import(name: str):
    """Lazy import helper to avoid errors when dependencies are missing."""
    import importlib
    try:
        return importlib.import_module(f".{{name}}", package=__name__)
    except Exception:
        return None

# Import all bridge modules with graceful fallback
_agenticseek = _lazy_import("agenticseek_bridge")
_openmanus = _lazy_import("openmanus_bridge")
_lemonai = _lazy_import("lemonai_bridge")
_uitars = _lazy_import("uifacts_bridge")
_opencode = _lazy_import("opencode_bridge")


# Factory re-exports
def get_agenticseek_bridge(config: Optional[Dict[str, Any]] = None, verbose: bool = True):
    """Create an AgenticSeekBridge instance."""
    from .agenticseek_bridge import get_agenticseek_bridge as _factory
    return _factory(config=config, verbose=verbose)


def get_openmanus_bridge(config: Optional[Dict[str, Any]] = None, verbose: bool = True):
    """Create an OpenManusBridge instance."""
    from .openmanus_bridge import get_openmanus_bridge as _factory
    return _factory(config=config, verbose=verbose)


def get_lemonai_bridge(config: Optional[Dict[str, Any]] = None, verbose: bool = True):
    """Create a LemonAIBridge instance."""
    from .lemonai_bridge import get_lemonai_bridge as _factory
    return _factory(config=config, verbose=verbose)


def get_uitars_bridge(config: Optional[Dict[str, Any]] = None, verbose: bool = True):
    """Create a UITARSBridge instance."""
    from .uifacts_bridge import get_uitars_bridge as _factory
    return _factory(config=config, verbose=verbose)


def get_opencode_bridge(config: Optional[Dict[str, Any]] = None, verbose: bool = True):
    """Create an OpencodeBridge instance."""
    from .opencode_bridge import get_opencode_bridge as _factory
    return _factory(config=config, verbose=verbose)


def list_all_bridges() -> List[Dict[str, Any]]:
    """List metadata for all available bridges."""
    bridges = []
    for factory_name in [
        "get_agenticseek_bridge",
        "get_openmanus_bridge",
        "get_lemonai_bridge",
        "get_uitars_bridge",
        "get_opencode_bridge",
    ]:
        try:
            factory = globals()[factory_name]
            bridge = factory(verbose=False)
            bridges.append(bridge.metadata() | bridge.health_check())
        except Exception:
            pass
    return bridges


__all__ = [
    "get_agenticseek_bridge",
    "get_openmanus_bridge",
    "get_lemonai_bridge",
    "get_uitars_bridge",
    "get_opencode_bridge",
    "list_all_bridges",
]
