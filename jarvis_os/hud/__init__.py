"""JARVIS Iron Man HUD — PyQt6 implementation per JARVIS_HUD_Specification.md.

Concentric arc reactor + rotating data rings + voice waveform + glass-morphism panels.
"""
from .iron_hud import IronManHUD, ArcReactor, DataRings, VoiceWaveform, run_hud

__all__ = ["IronManHUD", "ArcReactor", "DataRings", "VoiceWaveform", "run_hud"]
