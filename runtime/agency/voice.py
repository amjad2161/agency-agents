"""Voice / TTS module for JARVIS Pass 17.

Provides speak(text) that converts text to speech using the best available
engine on the current platform.

Fallback chain
--------------
1. pyttsx3         — offline, cross-platform, no API key needed
2. gTTS + playsound — online (Google), cross-platform
3. System command  — platform-specific:
     Linux/WSL  → espeak
     macOS      → say
     Windows    → PowerShell [System.Speech.Synthesis.SpeechSynthesizer]

Hebrew auto-detection: if text contains Hebrew Unicode characters the lang
is set to 'iw' (gTTS) or voice is set to Hebrew if available.
"""

from __future__ import annotations

import io
import logging
import os
import re
import subprocess
import sys
import tempfile
from enum import Enum
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional imports
# ---------------------------------------------------------------------------
try:
    import pyttsx3 as _pyttsx3  # type: ignore
    _PYTTSX3_OK = True
except ImportError:
    _PYTTSX3_OK = False

try:
    from gtts import gTTS as _gTTS  # type: ignore
    _GTTS_OK = True
except ImportError:
    _GTTS_OK = False

try:
    from playsound import playsound as _playsound  # type: ignore
    _PLAYSOUND_OK = True
except ImportError:
    _PLAYSOUND_OK = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_HEBREW_RE = re.compile(r"[֐-׿יִ-ﭏ]")


def _is_hebrew(text: str) -> bool:
    """Return True if text contains Hebrew characters."""
    return bool(_HEBREW_RE.search(text))


class TTSEngine(str, Enum):
    PYTTSX3 = "pyttsx3"
    GTTS = "gtts"
    ESPEAK = "espeak"
    SAY = "say"
    POWERSHELL = "powershell"
    NONE = "none"


def _detect_system_engine() -> TTSEngine:
    """Return the best available system TTS command."""
    if sys.platform == "darwin":
        return TTSEngine.SAY
    if sys.platform.startswith("win"):
        return TTSEngine.POWERSHELL
    # Linux / WSL
    try:
        subprocess.run(["espeak", "--version"], capture_output=True, check=True, timeout=3)
        return TTSEngine.ESPEAK
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        pass
    # espeak-ng
    try:
        subprocess.run(["espeak-ng", "--version"], capture_output=True, check=True, timeout=3)
        return TTSEngine.ESPEAK
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        pass
    return TTSEngine.NONE


# ---------------------------------------------------------------------------
# Engine implementations
# ---------------------------------------------------------------------------

def _speak_pyttsx3(text: str) -> bool:
    """Speak using pyttsx3. Returns True on success."""
    try:
        engine = _pyttsx3.init()
        if _is_hebrew(text):
            # Try to find a Hebrew voice
            voices = engine.getProperty("voices")
            for v in voices:
                if "hebrew" in (v.name or "").lower() or "he" in (v.id or "").lower():
                    engine.setProperty("voice", v.id)
                    break
        engine.say(text)
        engine.runAndWait()
        engine.stop()
        return True
    except Exception as exc:
        log.debug("pyttsx3 failed: %s", exc)
        return False


def _speak_gtts(text: str) -> bool:
    """Speak using gTTS + playsound (or afplay/mpg123 fallback). Returns True on success."""
    try:
        lang = "iw" if _is_hebrew(text) else "en"
        tts = _gTTS(text=text, lang=lang, slow=False)
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            tmp_path = f.name
        tts.save(tmp_path)
        played = False
        if _PLAYSOUND_OK:
            try:
                _playsound(tmp_path)
                played = True
            except Exception:
                pass
        if not played:
            # Try system player
            for cmd in (
                ["afplay", tmp_path],          # macOS
                ["mpg123", "-q", tmp_path],    # Linux
                ["mpg321", "-q", tmp_path],    # Linux alt
                ["vlc", "--intf", "dummy", "--play-and-exit", tmp_path],
            ):
                try:
                    subprocess.run(cmd, check=True, timeout=60, capture_output=True)
                    played = True
                    break
                except (FileNotFoundError, subprocess.CalledProcessError):
                    continue
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        return played
    except Exception as exc:
        log.debug("gTTS failed: %s", exc)
        return False


def _speak_espeak(text: str) -> bool:
    """Speak using espeak / espeak-ng. Returns True on success."""
    lang_flag = "he" if _is_hebrew(text) else "en"
    for exe in ("espeak-ng", "espeak"):
        try:
            subprocess.run(
                [exe, "-v", lang_flag, text],
                check=True,
                timeout=60,
                capture_output=True,
            )
            return True
        except FileNotFoundError:
            continue
        except subprocess.CalledProcessError as exc:
            log.debug("espeak failed: %s", exc)
    return False


def _speak_say(text: str) -> bool:
    """Speak using macOS `say`. Returns True on success."""
    try:
        cmd = ["say"]
        if _is_hebrew(text):
            # macOS voice for Hebrew
            cmd += ["-v", "Carmit"]
        cmd.append(text)
        subprocess.run(cmd, check=True, timeout=60, capture_output=True)
        return True
    except Exception as exc:
        log.debug("say failed: %s", exc)
        return False


def _speak_powershell(text: str) -> bool:
    """Speak on Windows using PowerShell SpeechSynthesizer. Returns True on success."""
    # Escape single quotes
    safe_text = text.replace("'", "\\'")
    ps_script = (
        "Add-Type -AssemblyName System.Speech; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        f"$s.Speak('{safe_text}')"
    )
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
            check=True,
            timeout=120,
            capture_output=True,
        )
        return True
    except Exception as exc:
        log.debug("PowerShell TTS failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_engine() -> TTSEngine:
    """Return the highest-priority available TTS engine."""
    if _PYTTSX3_OK:
        return TTSEngine.PYTTSX3
    if _GTTS_OK:
        return TTSEngine.GTTS
    return _detect_system_engine()


def speak(text: str, engine: TTSEngine | str | None = None) -> bool:
    """Convert *text* to speech.

    Parameters
    ----------
    text:   Text to speak. Hebrew auto-detected.
    engine: Force a specific engine (optional).

    Returns
    -------
    True if speech was produced, False if all engines failed.
    """
    if not text or not text.strip():
        return False

    if engine is not None:
        chosen = TTSEngine(engine) if isinstance(engine, str) else engine
    else:
        chosen = detect_engine()

    log.debug("TTS: engine=%s text=%r", chosen, text[:60])

    dispatch: dict[TTSEngine, Any] = {
        TTSEngine.PYTTSX3:   _speak_pyttsx3,
        TTSEngine.GTTS:      _speak_gtts,
        TTSEngine.ESPEAK:    _speak_espeak,
        TTSEngine.SAY:       _speak_say,
        TTSEngine.POWERSHELL: _speak_powershell,
        TTSEngine.NONE:      lambda t: False,
    }

    fn = dispatch.get(chosen)
    if fn is None:
        log.error("Unknown TTS engine: %s", chosen)
        return False

    success = fn(text)
    if success:
        return True

    # --- Fallback chain -----------------------------------------------------
    log.warning("TTS engine %s failed, trying fallbacks", chosen)
    fallback_order = [
        TTSEngine.PYTTSX3,
        TTSEngine.GTTS,
        _detect_system_engine(),
    ]
    for fb in fallback_order:
        if fb == chosen or fb == TTSEngine.NONE:
            continue
        fb_fn = dispatch.get(fb)
        if fb_fn and fb_fn(text):
            log.info("TTS: fallback to %s succeeded", fb)
            return True

    log.error("TTS: all engines failed for text of length %d", len(text))
    return False


# ---------------------------------------------------------------------------
# CLI helper
# ---------------------------------------------------------------------------
def cli_speak(args: Any) -> None:
    """Entry point for `agency speak "text"`."""
    text = " ".join(args.text) if isinstance(args.text, list) else args.text
    ok = speak(text)
    if not ok:
        print("Warning: TTS unavailable — install pyttsx3 or gtts", file=sys.stderr)
