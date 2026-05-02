"""Visual / 3D bridges — browser-renderable outputs.

Each bridge generates self-contained HTML files (CDN-loaded JS libs)
written to ``assets/`` for direct viewing in any modern browser.

Bridges
-------
- NeuralAvatarBridge  — 3D animated avatar (Three.js)
- JarvsVisualization  — charts and graphs (Chart.js / D3.js)
- CubeSandboxBridge   — physics sandbox (Three.js + cannon.js)
"""

from .neural_avatar import NeuralAvatarBridge
from .jarvs import JarvsVisualization
from .cubesandbox import CubeSandboxBridge

__all__ = [
    "NeuralAvatarBridge",
    "JarvsVisualization",
    "CubeSandboxBridge",
]
