"""Hardware/CAD/media bridges sub-package.

Each bridge follows the same contract:

* A single class wrapping a piece of physical hardware, an external
  toolchain, or a media/codec backend.
* An ``invoke(action: str, **kwargs)`` dispatcher that returns a
  JSON-serialisable result for tool routing.
* Graceful, deterministic *simulation/mock* fallbacks when the real
  backend is missing — so unit tests and CI work without hardware.

Public factories
----------------

``get_matrix_wallpaper_bridge()`` -> :class:`MatrixWallpaperBridge`
``get_lyra2_bridge()``            -> :class:`Lyra2Bridge`
``get_metaverse_bridge()``        -> :class:`MetaverseBridge`
"""

from __future__ import annotations

from .lyra2 import Lyra2Bridge, get_lyra2_bridge
from .matrix_wallpaper import MatrixWallpaperBridge, get_matrix_wallpaper_bridge
from .metaverse import MetaverseBridge, get_metaverse_bridge

__all__ = [
    "Lyra2Bridge",
    "MatrixWallpaperBridge",
    "MetaverseBridge",
    "get_lyra2_bridge",
    "get_matrix_wallpaper_bridge",
    "get_metaverse_bridge",
]
