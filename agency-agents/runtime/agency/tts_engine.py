"""
tts_engine.py — Pass 22
TTSEngine: edge-tts → Coqui TTS → pyttsx3 → gTTS → espeak/say/PowerShell → Mock
Hebrew detection: if any char in א-ת → lang="he", voice="he-IL-AvriNeural"
"""
from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

# ── Hebrew detection ───────────────────────────────────────────────────────────

_HEB_RANGE = range(0x05D0, 0x05EB)  # א–ת

def _is_hebrew(text: str) -> bool:
    return any(ord(c) in _HEB_RANGE for c in text)

def _select_voice(text: str, lang: str) -> tuple[str, str]:
    """Returns (lang, voice_name)."""
    if lang == "he" or _is_hebrew(text):
        return "he", "he-IL-AvriNeural"
    return lang, "en-US-AriaNeural"

# ── backend detection ──────────────────────────────────────────────────────────

_EDGE_TTS_AVAILABLE = False
_COQUI_AVAILABLE = False
_PYTTSX3_AVAILABLE = False
_GTTS_AVAILABLE = False

try:
    import edge_tts as _edge_tts
    _EDGE_TTS_AVAILABLE = True
    logger.info("edge-tts available")
except ImportError:
    pass

try:
    from TTS.api import TTS as _CoquiTTS
    _COQUI_AVAILABLE = True
    logger.info("Coqui TTS available")
except ImportError:
    pass

try:
    import pyttsx3 as _pyttsx3
    _PYTTSX3_AVAILABLE = True
    logger.info("pyttsx3 available")
except ImportError:
    pass

try:
    from gtts import gTTS as _gTTS
    _GTTS_AVAILABLE = True
    logger.info("gTTS available")
except ImportError:
    pass


# ── Mock backend ───────────────────────────────────────────────────────────────

class _MockTTSBackend:
    name = "mock"

    def speak(self, text: str, lang: str = "he", voice: str = "") -> None:
        logger.info("[MockTTS] %s (lang=%s, voice=%s)", text, lang, voice)

    def list_voices(self) -> List[str]:
        return ["mock-voice-he", "mock-voice-en"]


# ── edge-tts backend ───────────────────────────────────────────────────────────

class _EdgeTTSBackend:
    name = "edge-tts"

    def speak(self, text: str, lang: str = "he", voice: str = "") -> None:
        asyncio.run(self._speak_async(text, lang, voice))

    async def _speak_async(self, text: str, lang: str, voice: str) -> None:
        if not voice:
            lang, voice = _select_voice(text, lang)
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tf:
            out_path = tf.name
        try:
            comm = _edge_tts.Communicate(text, voice)
            await comm.save(out_path)
            _play_audio(out_path)
        finally:
            try:
                os.unlink(out_path)
            except OSError:
                pass

    def list_voices(self) -> List[str]:
        try:
            loop = asyncio.new_event_loop()
            voices = loop.run_until_complete(_edge_tts.list_voices())
            loop.close()
            return [v["ShortName"] for v in voices]
        except Exception:
            return ["he-IL-AvriNeural", "en-US-AriaNeural"]


# ── pyttsx3 backend ────────────────────────────────────────────────────────────

class _Pyttsx3Backend:
    name = "pyttsx3"

    def __init__(self):
        self._engine = None

    def _get_engine(self):
        if self._engine is None:
            self._engine = _pyttsx3.init()
        return self._engine

    def speak(self, text: str, lang: str = "he", voice: str = "") -> None:
        engine = self._get_engine()
        voices = engine.getProperty("voices")
        if voices:
            # Prefer Hebrew voice if available
            if _is_hebrew(text) or lang == "he":
                heb = [v for v in voices if "he" in v.id.lower() or "hebrew" in v.name.lower()]
                if heb:
                    engine.setProperty("voice", heb[0].id)
            engine.say(text)
            engine.runAndWait()

    def list_voices(self) -> List[str]:
        engine = self._get_engine()
        return [v.name for v in engine.getProperty("voices")]


# ── gTTS backend ───────────────────────────────────────────────────────────────

class _GTTSBackend:
    name = "gtts"

    def speak(self, text: str, lang: str = "he", voice: str = "") -> None:
        if _is_hebrew(text):
            lang = "he"
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tf:
            out_path = tf.name
        try:
            tts = _gTTS(text=text, lang=lang)
            tts.save(out_path)
            _play_audio(out_path)
        finally:
            try:
                os.unlink(out_path)
            except OSError:
                pass

    def list_voices(self) -> List[str]:
        return ["he", "en"]


# ── Coqui TTS backend ──────────────────────────────────────────────────────────

class _CoquiTTSBackend:
    name = "coqui"

    def __init__(self):
        self._tts = None

    def _get_tts(self):
        if self._tts is None:
            self._tts = _CoquiTTS("tts_models/en/ljspeech/tacotron2-DDC", progress_bar=False)
        return self._tts

    def speak(self, text: str, lang: str = "he", voice: str = "") -> None:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
            out_path = tf.name
        try:
            self._get_tts().tts_to_file(text=text, file_path=out_path)
            _play_audio(out_path)
        finally:
            try:
                os.unlink(out_path)
            except OSError:
                pass

    def list_voices(self) -> List[str]:
        return ["tts_models/en/ljspeech/tacotron2-DDC"]


# ── Audio playback helper ──────────────────────────────────────────────────────

def _play_audio(path: str) -> None:
    """Cross-platform audio playback."""
    if sys.platform == "win32":
        try:
            subprocess.run(
                ["powershell", "-c", f'(New-Object Media.SoundPlayer "{path}").PlaySync()'],
                check=False, timeout=30
            )
            return
        except Exception:
            pass
        try:
            import winsound
            winsound.PlaySound(path, winsound.SND_FILENAME)
            return
        except Exception:
            pass
    elif sys.platform == "darwin":
        subprocess.run(["afplay", path], check=False, timeout=30)
        return
    # Linux
    for player in ("aplay", "paplay", "mpg123", "ffplay"):
        if subprocess.run(["which", player], capture_output=True).returncode == 0:
            subprocess.run([player, path], check=False, timeout=30)
            return
    logger.warning("No audio player found")


# ── Public facade ──────────────────────────────────────────────────────────────

class TTSEngine:
    """
    Facade. Backend priority:
    edge-tts → Coqui → pyttsx3 → gTTS → Mock
    """

    def __init__(self):
        if _EDGE_TTS_AVAILABLE:
            self._backend = _EdgeTTSBackend()
        elif _COQUI_AVAILABLE:
            self._backend = _CoquiTTSBackend()
        elif _PYTTSX3_AVAILABLE:
            self._backend = _Pyttsx3Backend()
        elif _GTTS_AVAILABLE:
            self._backend = _GTTSBackend()
        else:
            self._backend = _MockTTSBackend()
        logger.info("TTSEngine using backend: %s", self._backend.name)

    @property
    def backend_name(self) -> str:
        return self._backend.name

    def speak(self, text: str, lang: str = "he") -> None:
        """
        Speak text synchronously.
        Auto-detects Hebrew; overrides lang accordingly.
        """
        resolved_lang, voice = _select_voice(text, lang)
        self._backend.speak(text, resolved_lang, voice)

    def speak_async(self, text: str, lang: str = "he") -> threading.Thread:
        """
        Speak text in a background thread.
        Returns the thread (already started).
        """
        t = threading.Thread(target=self.speak, args=(text, lang), daemon=True)
        t.start()
        return t

    def list_voices(self) -> List[str]:
        """Return list of available voice names."""
        return self._backend.list_voices()
