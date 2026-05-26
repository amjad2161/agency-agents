"""Hardware/CAD bridges sub-package.

Each bridge in this package follows the same contract:

* A single class (e.g. :class:`DobotBridge`) wrapping a piece of physical
  hardware or external CAD/3D toolchain.
* A ``hardware_available`` (or equivalent ``*_available``) property that
  tells callers whether the real backend is reachable.
* An ``invoke(action: str, **kwargs)`` method that dispatches a string
  action name to a bound method, returning a JSON-serialisable dict.
* A graceful, deterministic *simulation* fallback when the real backend
  is missing — methods log what *would* happen and return realistic mock
  data so unit tests and CI work without any hardware.

Public factories
----------------

``get_dobot_bridge()``     -> :class:`DobotBridge`
``get_blender_bridge()``   -> :class:`BlenderBridge`
``get_cadam_bridge()``     -> :class:`CadamBridge`
"""

from __future__ import annotations

from .blender import BlenderBridge, get_blender_bridge
from .cadam import CadamBridge, get_cadam_bridge
from .dobot import DobotBridge, get_dobot_bridge

__all__ = [
    "BlenderBridge",
    "CadamBridge",
    "DobotBridge",
    "get_blender_bridge",
    "get_cadam_bridge",
    "get_dobot_bridge",
]
