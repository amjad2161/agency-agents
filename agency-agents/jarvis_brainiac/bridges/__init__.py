"""JARVIS Brainiac bridges — external system adapters (15 bridges)."""
from .base import Bridge, BridgeRegistry, BridgeStatus
from .blender import BlenderBridge
from .cadam import CadamBridge
from .dobot import DobotBridge
from .lyra2 import Lyra2Bridge
from .matrix_wallpaper import MatrixWallpaperBridge
from .metaverse import MetaverseBridge
from .personas import PersonasBridge
from .rtk_ai import RtkAiBridge
from .scifi_ui import ScifiUiBridge
from .working_demos import WorkingDemosBridge

__all__ = [
    "Bridge", "BridgeRegistry", "BridgeStatus",
    "BlenderBridge", "CadamBridge", "DobotBridge", "Lyra2Bridge",
    "MatrixWallpaperBridge", "MetaverseBridge", "PersonasBridge",
    "RtkAiBridge", "ScifiUiBridge", "WorkingDemosBridge",
]


def default_registry() -> BridgeRegistry:
    """Return a registry preloaded with all 10 stub bridges."""
    reg = BridgeRegistry()
    for cls in (BlenderBridge, CadamBridge, DobotBridge, Lyra2Bridge,
                MatrixWallpaperBridge, MetaverseBridge, PersonasBridge,
                RtkAiBridge, ScifiUiBridge, WorkingDemosBridge):
        reg.register(cls())
    return reg
