"""Bridges — external service adapters with stdlib-only HTTP."""
from bridges.gitnexus import GitNexusBridge, GitNexusError
from bridges.instagram import InstagramBridge, InstagramError

__all__ = [
    "GitNexusBridge",
    "GitNexusError",
    "InstagramBridge",
    "InstagramError",
]
