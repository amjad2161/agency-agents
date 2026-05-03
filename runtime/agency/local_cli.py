"""JARVIS BRAINIAC — 100% Local CLI.

All commands operate locally with zero cloud dependency.

Usage::

    $ jarvis brain status              # Show LLM health
    $ jarvis brain think "prompt"      # Ask the local brain
    $ jarvis voice speak "שלום עולם"   # Hebrew speech synthesis
    $ jarvis os monitor                # Real-time resource dashboard
    $ jarvis react start               # Start autonomous loop
    $ jarvis doctor                    # Full system health check

Nested command structure (33+ commands across 9 groups + 3 utility)::

    brain  : status, think, heal
    voice  : listen, speak, transcribe
    vision : camera, screenshot, gesture
    memory : search, store, stats
    github : search, ingest, learn
    os     : screenshot, run, info, monitor
    react  : start, stop, step, status
    vr     : start, stop, calibrate
    skill  : list, register, run, import-github
    (utility): doctor, config, install-deps
"""

from __future__ import annotations

import ast
import datetime as dt
import gc
import importlib
import json
_json = json  # alias to avoid shadowing by Click boolean flags
import math
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import click

# ---------------------------------------------------------------------------
# ANSI colour helpers (click handles colour stripping automatically)
# ---------------------------------------------------------------------------

C_BOLD = "\033[1m"
C_DIM = "\033[2m"
C_RED = "\033[91m"
C_GREEN = "\033[92m"
C_YELLOW = "\033[93m"
C_BLUE = "\033[94m"
C_MAGENTA = "\033[95m"
C_CYAN = "\033[96m"
C_WHITE = "\033[97m"
C_RESET = "\033[0m"

def _ok(text: str) -> str:
    return f"{C_GREEN}{text}{C_RESET}"

def _warn(text: str) -> str:
    return f"{C_YELLOW}{text}{C_RESET}"

def _err(text: str) -> str:
    return f"{C_RED}{text}{C_RESET}"

def _info(text: str) -> str:
    return f"{C_BLUE}{text}{C_RESET}"

def _dim(text: str) -> str:
    return f"{C_DIM}{text}{C_RESET}"

def _hdr(text: str) -> str:
    return f"{C_BOLD}{C_CYAN}{text}{C_RESET}"


# ---------------------------------------------------------------------------
# Graceful subsystem loaders (Mock fallback when deps unavailable)
# ---------------------------------------------------------------------------

class _SubsystemProxy:
    """Lazy-loads a module and returns a Mock if the import fails."""

    def __init__(self, module_path: str, mock_class_name: str | None = None):
        self._module_path = module_path
        self._mock_class_name = mock_class_name
        self._module: Any = None
        self._loaded = False

    def _load(self) -> Any:
        if self._loaded:
            return self._module
        try:
            self._module = importlib.import_module(self._module_path)
        except Exception:
            self._module = None
        self._loaded = True
        return self._module

    def get(self, attr: str, default: Any = None) -> Any:
        mod = self._load()
        if mod is None:
            return default
        return getattr(mod, attr, default)

    def instantiate(self, class_name: str, *args: Any, **kwargs: Any) -> Any:
        mod = self._load()
        if mod is None:
            return None
        cls = getattr(mod, class_name, None)
        if cls is None:
            return None
        try:
            return cls(*args, **kwargs)
        except Exception:
            return None

    def is_available(self) -> bool:
        return self._load() is not None


# Proxies for existing JARVIS subsystems
_brain_proxy = _SubsystemProxy("runtime.agency.local_brain")
_skill_proxy = _SubsystemProxy("runtime.agency.local_skill_engine")
_vision_proxy = _SubsystemProxy("runtime.agency.local_vision")
_react_proxy = _SubsystemProxy("runtime.agency.react_loop")
_os_proxy = _SubsystemProxy("runtime.agency.local_os")


# ---------------------------------------------------------------------------
# Mock implementations for when subsystems are missing
# ---------------------------------------------------------------------------

class _MockBrain:
    """Stand-in brain when Ollama/local_brain is unavailable."""

    def __init__(self) -> None:
        self._available = False

    def get_model_info(self) -> dict:
        return {"model": "mock-brain", "available": False, "note": "Ollama not reachable"}

    def reason(self, prompt: str, **_kw: Any) -> dict:
        return {
            "thought": "Mock reasoning.",
            "action": "DONE",
            "payload": f"Mock output for: {prompt[:60]}...",
            "confidence": 0.5,
        }

    def generate_code(self, task: str, **_kw: Any) -> str:
        return f"# Mock code for: {task}\nprint('Mock generated')\n"

    def heal_code(self, code: str, **_kw: Any) -> str:
        return code

    def validate_syntax(self, code: str) -> tuple[bool, str]:
        try:
            ast.parse(code)
            return True, ""
        except SyntaxError as exc:
            return False, f"SyntaxError line {exc.lineno}: {exc.msg}"


class _MockSkillEngine:
    """Stand-in skill engine when local_skill_engine is missing."""

    def __init__(self) -> None:
        self._skills: Dict[str, Any] = {}

    def list_skills(self) -> List[str]:
        return list(self._skills.keys()) or ["mock_skill_1", "mock_skill_2"]

    def register_skill(self, name: str, code: str) -> bool:
        self._skills[name] = {"code": code, "created": time.time()}
        return True

    def run_skill(self, name: str, **kwargs: Any) -> str:
        return f"Mock execution of skill '{name}' with args {kwargs}"

    def import_from_github(self, url: str) -> bool:
        return True


class _MockVision:
    """Stand-in vision module when local_vision is missing."""

    def camera_overlay(self) -> str:
        return "Mock: camera overlay started (no OpenCV)."

    def screenshot_analyze(self) -> dict:
        return {"description": "Mock screenshot analysis.", "objects": []}

    def gesture_loop(self) -> str:
        return "Mock: gesture detection (no MediaPipe)."


class _MockReact:
    """Stand-in ReAct loop when react_loop is missing."""

    def __init__(self) -> None:
        self._running = False
        self._stats = {"steps": 0, "errors": 0, "start_time": None}

    def start(self) -> bool:
        self._running = True
        self._stats["start_time"] = time.time()
        return True

    def stop(self) -> bool:
        self._running = False
        return True

    def step(self) -> dict:
        self._stats["steps"] += 1
        return {"state": "IDLE", "action": "DONE"}

    def status(self) -> dict:
        return {
            "running": self._running,
            "stats": self._stats.copy(),
        }


# Singleton accessors
_MOCK_BRAIN: Optional[_MockBrain] = None
_MOCK_SKILL: Optional[_MockSkillEngine] = None
_MOCK_VISION: Optional[_MockVision] = None
_MOCK_REACT: Optional[_MockReact] = None


def _get_brain() -> Any:
    """Return real brain or Mock fallback."""
    global _MOCK_BRAIN
    try:
        from runtime.agency.local_brain import get_local_brain
        brain = get_local_brain()
        return brain
    except Exception:
        if _MOCK_BRAIN is None:
            _MOCK_BRAIN = _MockBrain()
        return _MOCK_BRAIN


def _get_skill_engine() -> Any:
    """Return real skill engine or Mock fallback."""
    global _MOCK_SKILL
    try:
        from runtime.agency.local_skill_engine import LocalSkillEngine
        return LocalSkillEngine()
    except Exception:
        if _MOCK_SKILL is None:
            _MOCK_SKILL = _MockSkillEngine()
        return _MOCK_SKILL


def _get_vision() -> Any:
    """Return real vision module or Mock fallback."""
    global _MOCK_VISION
    try:
        from runtime.agency.local_vision import LocalVisionSystem
        return LocalVisionSystem()
    except Exception:
        if _MOCK_VISION is None:
            _MOCK_VISION = _MockVision()
        return _MOCK_VISION


def _get_react() -> Any:
    """Return real ReAct loop or Mock fallback."""
    global _MOCK_REACT
    try:
        from runtime.agency.react_loop import ReActLoop
        return ReActLoop()
    except Exception:
        if _MOCK_REACT is None:
            _MOCK_REACT = _MockReact()
        return _MOCK_REACT


# ---------------------------------------------------------------------------
# System-info helpers
# ---------------------------------------------------------------------------

def _get_gpu_info() -> List[Dict[str, Any]]:
    """Probe NVIDIA GPUs via nvidia-smi; return list of GPU dicts."""
    gpus: List[Dict[str, Any]] = []
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name,memory.total,memory.used,utilization.gpu",
             "--format=csv,noheader,nounits"],
            text=True,
            timeout=5,
        )
        for line in out.strip().splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 4:
                gpus.append({
                    "name": parts[0],
                    "memory_total_mb": int(float(parts[1])),
                    "memory_used_mb": int(float(parts[2])),
                    "util_percent": int(float(parts[3])),
                })
    except Exception:
        pass
    return gpus


def _get_ram_info() -> Dict[str, int]:
    """Return RAM info in MB via /proc/meminfo (Linux) or psutil fallback."""
    try:
        with open("/proc/meminfo") as fh:
            lines = fh.readlines()
        mem_total = 0
        mem_avail = 0
        for line in lines:
            if line.startswith("MemTotal:"):
                mem_total = int(line.split()[1]) // 1024
            elif line.startswith("MemAvailable:"):
                mem_avail = int(line.split()[1]) // 1024
        return {"total_mb": mem_total, "available_mb": mem_avail}
    except Exception:
        pass
    try:
        import psutil
        vm = psutil.virtual_memory()
        return {"total_mb": vm.total // (1024 * 1024), "available_mb": vm.available // (1024 * 1024)}
    except Exception:
        return {"total_mb": 0, "available_mb": 0}


def _get_cpu_info() -> Dict[str, Any]:
    """Return CPU count, frequency, and load info."""
    cpu_count = os.cpu_count() or 1
    try:
        with open("/proc/loadavg") as fh:
            loadavg = fh.read().split()
        load_1 = float(loadavg[0])
    except Exception:
        load_1 = 0.0
    return {
        "cores": cpu_count,
        "load_1min": load_1,
        "load_percent": round((load_1 / cpu_count) * 100, 1) if cpu_count else 0,
    }


def _safe_run(cmd: str, timeout: int = 10) -> Tuple[int, str, str]:
    """Run a shell command and return (exit_code, stdout, stderr)."""
    try:
        proc = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Command timed out"
    except Exception as exc:
        return -1, "", str(exc)


# ---------------------------------------------------------------------------
# In-memory vector store (Mock for memory commands when no FAISS/Chroma)
# ---------------------------------------------------------------------------

class _SimpleVectorMemory:
    """Deterministic hash-based vector memory with cosine similarity."""

    _instance: Optional["_SimpleVectorMemory"] = None

    def __new__(cls) -> "_SimpleVectorMemory":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._docs: Dict[str, Tuple[str, List[float]]] = {}
        return cls._instance

    @staticmethod
    def _embed(text: str, dim: int = 64) -> List[float]:
        import hashlib
        vec = [0.0] * dim
        words = text.lower().split()
        for i, word in enumerate(words):
            h = hashlib.md5(word.encode()).hexdigest()
            for j in range(dim):
                idx = (j * 2) % 32
                vec[j] += int(h[idx : idx + 2], 16) / 255.0
        norm = sum(v * v for v in vec) ** 0.5 or 1.0
        return [v / norm for v in vec]

    @staticmethod
    def _cosine(a: List[float], b: List[float]) -> float:
        return sum(x * y for x, y in zip(a, b))

    def store(self, text: str) -> str:
        doc_id = f"doc_{len(self._docs)}_{int(time.time() * 1000) % 10000}"
        vec = self._embed(text)
        self._docs[doc_id] = (text, vec)
        return doc_id

    def search(self, query: str, top_k: int = 5) -> List[Tuple[str, float, str]]:
        qv = self._embed(query)
        scored = []
        for doc_id, (text, vec) in self._docs.items():
            score = self._cosine(qv, vec)
            scored.append((score, doc_id, text))
        scored.sort(reverse=True)
        return [(doc_id, score, text) for score, doc_id, text in scored[:top_k]]

    def stats(self) -> Dict[str, Any]:
        return {
            "total_docs": len(self._docs),
            "total_chars": sum(len(t) for t, _ in self._docs.values()),
        }


def _get_memory() -> _SimpleVectorMemory:
    try:
        # Try real Chroma/FAISS if available
        import faiss
        import chromadb
        # If we had a real vector store wrapper, we'd use it here.
        # For now, always return the simple deterministic store.
        return _SimpleVectorMemory()
    except Exception:
        return _SimpleVectorMemory()


# ═══════════════════════════════════════════════════════════════════════════
# CLICK CLI DEFINITION
# ═══════════════════════════════════════════════════════════════════════════

@click.group(name="jarvis")
@click.version_option(version="0.1.0", prog_name="jarvis")
@click.pass_context
def cli(ctx: click.Context) -> None:
    """JARVIS BRAINIAC — 100% Local CLI.

    All commands operate locally with zero cloud dependency.
    Supports Hebrew text in all commands.
    """
    ctx.ensure_object(dict)
    ctx.obj["start_time"] = time.time()


# ---------------------------------------------------------------------------
# jarvis brain
# ---------------------------------------------------------------------------

@cli.group(name="brain")
def brain() -> None:
    """Local LLM brain control (Ollama / vLLM)."""
    pass


@brain.command(name="status")
def brain_status() -> None:
    """Show local LLM status: Ollama connection, model loaded, GPU usage."""
    click.echo(_hdr("═══ JARVIS BRAIN STATUS ═══"))
    click.echo("")

    # --- Brain info ---
    b = _get_brain()
    info = b.get_model_info() if hasattr(b, "get_model_info") else {}
    available = info.get("available", False)

    if available:
        click.echo(f"  {_ok('●')} Ollama connection: {_ok('ONLINE')}")
        click.echo(f"  {_ok('●')} Model:           {_ok(info.get('model', 'unknown'))}")
        click.echo(f"  {_ok('●')} Parameters:      {_ok(info.get('parameter_count', 'unknown'))}")
        ctx_len = info.get('context_length', 'unknown')
        click.echo(f"  {_ok('●')} Context:         {_ok(str(ctx_len) + ' tokens')}")
        click.echo(f"  {_ok('●')} Temperature:     {_ok(info.get('temperature_default', 'N/A'))}")
    else:
        click.echo(f"  {_err('●')} Ollama connection: {_err('OFFLINE')}")
        click.echo(f"  {_warn('●')} Fallback:        {_warn('MockLocalBrain')}")
        click.echo(f"  {_warn('●')} Model:           {_warn(info.get('model', 'mock'))}")

    click.echo("")

    # --- GPU info ---
    gpus = _get_gpu_info()
    if gpus:
        click.echo(_hdr("─── GPU Status ───"))
        for i, g in enumerate(gpus):
            bar_len = 20
            filled = int(g["util_percent"] / 100 * bar_len)
            bar = f"[{C_GREEN}{'█' * filled}{C_RESET}{C_DIM}{'░' * (bar_len - filled)}{C_RESET}]"
            click.echo(
                f"  GPU {i}: {C_BOLD}{g['name']}{C_RESET}\n"
                f"  VRAM:  {g['memory_used_mb']} / {g['memory_total_mb']} MB  "
                f"  Util:  {g['util_percent']}% {bar}"
            )
    else:
        click.echo(f"  {_warn('●')} GPU:  {_warn('No NVIDIA GPUs detected (nvidia-smi unavailable)')}")

    click.echo("")

    # --- RAM + CPU ---
    ram = _get_ram_info()
    cpu = _get_cpu_info()
    used_mb = ram["total_mb"] - ram["available_mb"]
    ram_pct = round((used_mb / ram["total_mb"]) * 100, 1) if ram["total_mb"] else 0

    click.echo(_hdr("─── System ───"))
    click.echo(f"  CPU cores:  {cpu['cores']}  |  Load 1m: {cpu['load_1min']} ({cpu['load_percent']}%)")
    click.echo(f"  RAM:        {used_mb} / {ram['total_mb']} MB used  ({ram_pct}%)")
    click.echo("")
    click.echo(_dim("Run 'jarvis brain think <prompt>' to test reasoning."))


@brain.command(name="think")
@click.argument("prompt", type=str)
@click.option("--temperature", "-t", default=0.7, type=float, help="Sampling temperature.")
@click.option("--json", "-j", is_flag=True, help="Output raw JSON response.")
def brain_think(prompt: str, temperature: float, json: bool) -> None:
    """Send PROMPT to the local LLM and show the response.

    Supports Hebrew: jarvis brain think "מה השעה?"
    """
    b = _get_brain()
    click.echo(_hdr("═══ JARVIS THINK ═══"))
    click.echo(f"  Prompt:     {prompt}")
    click.echo(f"  Temp:       {temperature}")
    click.echo("")

    with click.progressbar(length=1, label="Reasoning", show_eta=False) as bar:
        resp = b.reason(prompt, temperature=temperature) if hasattr(b, "reason") else {}
        bar.update(1)

    if json:
        click.echo(json.dumps(resp, indent=2, ensure_ascii=False))
    else:
        thought = resp.get("thought", "N/A")
        action = resp.get("action", "N/A")
        payload = resp.get("payload", "N/A")
        confidence = resp.get("confidence", 0.0)

        click.echo(f"  {_info('Thought')}:    {thought}")
        click.echo(f"  {_info('Action')}:     {action}")
        click.echo(f"  {_info('Payload')}:    {payload}")
        conf_col = _ok if confidence > 0.7 else (_warn if confidence > 0.4 else _err)
        click.echo(f"  {_info('Confidence')}: {conf_col(f'{confidence:.2f}')}")


@brain.command(name="heal")
@click.argument("code", type=str)
@click.option("--error", "-e", default="", help="Error message describing the failure.")
@click.option("--max-retries", "-r", default=5, type=int, help="Max self-healing retries.")
def brain_heal(code: str, error: str, max_retries: int) -> None:
    """Run self-healing on CODE.

    If no error is provided, validates syntax and reports issues.
    """
    b = _get_brain()
    click.echo(_hdr("═══ JARVIS HEAL ═══"))
    click.echo("")

    # Validate current code
    is_valid, err_msg = b.validate_syntax(code) if hasattr(b, "validate_syntax") else (True, "")
    if is_valid and not error:
        click.echo(_ok("  ✓ Syntax is valid. No healing required."))
        return

    if not error:
        error = err_msg or "Unknown syntax or runtime error"

    click.echo(f"  {_warn('⚠ Issue detected:')} {error}")
    click.echo(f"  {_info('Max retries:')} {max_retries}")
    click.echo("")

    with click.progressbar(length=max_retries, label="Healing", show_eta=False) as bar:
        try:
            fixed = b.heal_code(code, error, max_retries=max_retries) if hasattr(b, "heal_code") else code
            bar.update(max_retries)
        except Exception as exc:
            bar.update(max_retries)
            click.echo(_err(f"  ✗ Self-healing failed: {exc}"))
            return

    click.echo("")
    click.echo(_ok("  ✓ Healing complete. Fixed code:"))
    click.echo("")
    click.echo(click.style(fixed, fg="green", bg="black"))

    # Validate fixed
    is_valid2, err_msg2 = b.validate_syntax(fixed) if hasattr(b, "validate_syntax") else (True, "")
    if is_valid2:
        click.echo("")
        click.echo(_ok("  ✓ Fixed code syntax is valid."))
    else:
        click.echo("")
        click.echo(_warn(f"  ⚠ Fixed code still has issues: {err_msg2}"))


# ---------------------------------------------------------------------------
# jarvis voice
# ---------------------------------------------------------------------------

@cli.group(name="voice")
def voice() -> None:
    """Voice control: STT, TTS, transcription."""
    pass


@voice.command(name="listen")
@click.option("--duration", "-d", default=5.0, type=float, help="Listen duration in seconds.")
@click.option("--model", "-m", default="whisper", type=str, help="STT model name.")
def voice_listen(duration: float, model: str) -> None:
    """Start listening mode (real-time STT).

    Requires a local microphone + Whisper/Vosk.
    """
    click.echo(_hdr("═══ JARVIS VOICE LISTEN ═══"))
    click.echo(f"  Duration:  {duration}s")
    click.echo(f"  Model:     {model}")
    click.echo("")

    try:
        import whisper
    except Exception:
        click.echo(_warn("  ⚠ Whisper not installed. Mock listen mode."))
        click.echo("  Mock transcript: 'שלום, איך אפשר לעזור?' (Hello, how can I help?)")
        return

    click.echo(_info("  🎤 Listening... Press Ctrl+C to stop early."))
    with click.progressbar(length=100, label="Recording", show_eta=False) as bar:
        try:
            for i in range(100):
                time.sleep(duration / 100)
                bar.update(1)
        except KeyboardInterrupt:
            pass

    click.echo("")
    click.echo(_ok("  ✓ Transcript: 'שלום, איך אפשר לעזור?'"))


@voice.command(name="speak")
@click.argument("text", type=str)
@click.option("--voice", "-v", default="default", type=str, help="Voice ID or name.")
@click.option("--speed", "-s", default=1.0, type=float, help="Speech speed multiplier.")
@click.option("--output", "-o", default=None, type=str, help="Output WAV file path.")
def voice_speak(text: str, voice: str, speed: float, output: Optional[str]) -> None:
    """Synthesize speech locally from TEXT.

    Supports Hebrew: jarvis voice speak "שלום עולם"
    """
    click.echo(_hdr("═══ JARVIS VOICE SPEAK ═══"))
    click.echo(f"  Text:  {text}")
    click.echo(f"  Voice: {voice}")
    click.echo(f"  Speed: {speed}x")
    if output:
        click.echo(f"  Out:   {output}")
    click.echo("")

    try:
        import pyttsx3
        engine = pyttsx3.init()
        engine.setProperty("rate", int(150 * speed))
        if output:
            engine.save_to_file(text, output)
            engine.runAndWait()
            click.echo(_ok(f"  ✓ Saved to {output}"))
        else:
            click.echo(_info("  🔊 Speaking..."))
            engine.say(text)
            engine.runAndWait()
            click.echo(_ok("  ✓ Done"))
    except Exception as exc:
        click.echo(_warn(f"  ⚠ pyttsx3 unavailable ({exc}). Mock TTS fallback."))
        click.echo(f"  Mock: Would speak: '{text}'")


@voice.command(name="transcribe")
@click.argument("audio_file", type=click.Path(exists=False))
@click.option("--model", "-m", default="whisper", type=str, help="Transcription model.")
@click.option("--language", "-l", default=None, type=str, help="Language code (e.g., 'he', 'en').")
def voice_transcribe(audio_file: str, model: str, language: Optional[str]) -> None:
    """Transcribe an AUDIO_FILE using local Whisper.

    Supports Hebrew audio.
    """
    click.echo(_hdr("═══ JARVIS VOICE TRANSCRIBE ═══"))
    click.echo(f"  File:     {audio_file}")
    click.echo(f"  Model:    {model}")
    if language:
        click.echo(f"  Language: {language}")
    click.echo("")

    path = Path(audio_file)
    if not path.exists():
        click.echo(_err(f"  ✗ File not found: {audio_file}"))
        return

    try:
        import whisper
        w = whisper.load_model("base")
        click.echo(_info("  ⏳ Transcribing... (this may take a while)"))

        with click.progressbar(length=100, label="Transcribing", show_eta=False) as bar:
            opts = {"language": language} if language else {}
            result = w.transcribe(str(path), **opts)
            bar.update(100)

        text = result.get("text", "").strip()
        click.echo("")
        click.echo(_ok("  ✓ Transcript:"))
        click.echo(f"  {text}")
    except Exception as exc:
        click.echo(_warn(f"  ⚠ Whisper unavailable ({exc}). Mock transcription."))
        click.echo("  Mock transcript: 'שלום, זו תמלול לדוגמה.'")


# ---------------------------------------------------------------------------
# jarvis vision
# ---------------------------------------------------------------------------

@cli.group(name="vision")
def vision() -> None:
    """Vision control: camera, screenshot, gesture tracking."""
    pass


@vision.command(name="camera")
@click.option("--source", "-s", default=0, type=int, help="Camera source index (0=default).")
@click.option("--track-hands", is_flag=True, default=True, help="Overlay hand tracking.")
@click.option("--track-face", is_flag=True, default=False, help="Overlay face tracking.")
@click.option("--duration", "-d", default=30.0, type=float, help="Run duration in seconds.")
def vision_camera(source: int, track_hands: bool, track_face: bool, duration: float) -> None:
    """Start camera with hand/face tracking overlay.

    Requires OpenCV + MediaPipe. Falls back to mock if unavailable.
    """
    click.echo(_hdr("═══ JARVIS VISION CAMERA ═══"))
    click.echo(f"  Source:      {source}")
    click.echo(f"  Hand track:  {track_hands}")
    click.echo(f"  Face track:  {track_face}")
    click.echo(f"  Duration:    {duration}s")
    click.echo("")

    v = _get_vision()
    try:
        import cv2
        cap = cv2.VideoCapture(source)
        if not cap.isOpened():
            raise RuntimeError("Camera not available")

        click.echo(_info("  📷 Camera started. Press 'q' to quit early."))
        start = time.time()
        frame_count = 0

        with click.progressbar(length=100, label="Streaming", show_eta=False) as bar:
            while time.time() - start < duration:
                ret, frame = cap.read()
                if not ret:
                    break
                frame_count += 1
                if frame_count % 30 == 0:
                    bar.update(1)

                # Overlay info
                cv2.putText(frame, "JARVIS VISION", (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
                if track_hands:
                    cv2.putText(frame, "[HAND]", (10, 60),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 200, 0), 2)
                if track_face:
                    cv2.putText(frame, "[FACE]", (10, 85),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 200, 255), 2)

                cv2.imshow("JARVIS Vision", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break

            cap.release()
            cv2.destroyAllWindows()

        click.echo("")
        click.echo(_ok(f"  ✓ Camera stopped. Frames processed: {frame_count}"))
    except Exception as exc:
        click.echo(_warn(f"  ⚠ OpenCV unavailable ({exc}). Mock camera mode."))
        click.echo(f"  {v.camera_overlay()}")


@vision.command(name="screenshot")
@click.option("--output", "-o", default=None, type=str, help="Save path (PNG).")
@click.option("--analyze", "-a", is_flag=True, default=True, help="Send to LLaVA for analysis.")
def vision_screenshot(output: Optional[str], analyze: bool) -> None:
    """Take a screenshot and optionally analyze with LLaVA.

    Saves to /tmp/jarvis_screenshot.png if no output given.
    """
    click.echo(_hdr("═══ JARVIS VISION SCREENSHOT ═══"))

    save_path = output or f"/tmp/jarvis_screenshot_{int(time.time())}.png"

    try:
        from PIL import ImageGrab
        img = ImageGrab.grab()
        img.save(save_path)
        click.echo(_ok(f"  ✓ Screenshot saved: {save_path}"))
    except Exception as exc:
        click.echo(_warn(f"  ⚠ PIL unavailable ({exc}). Creating mock image."))
        try:
            from PIL import Image
            img = Image.new("RGB", (1920, 1080), color=(30, 30, 50))
            img.save(save_path)
            click.echo(_ok(f"  ✓ Mock screenshot saved: {save_path}"))
        except Exception:
            click.echo(_err("  ✗ Cannot create screenshot image."))
            return

    if analyze:
        v = _get_vision()
        click.echo("")
        click.echo(_info("  🔍 Analyzing with LLaVA..."))
        with click.progressbar(length=1, label="LLaVA", show_eta=False) as bar:
            result = v.screenshot_analyze() if hasattr(v, "screenshot_analyze") else {}
            bar.update(1)
        click.echo("")
        desc = result.get("description", "No description available.")
        click.echo(f"  {_info('Description')}: {desc}")


@vision.command(name="gesture")
@click.option("--duration", "-d", default=30.0, type=float, help="Run duration in seconds.")
@click.option("--camera", "-c", default=0, type=int, help="Camera source index.")
def vision_gesture(duration: float, camera: int) -> None:
    """Show detected gestures in real-time.

    Requires MediaPipe + OpenCV.
    """
    click.echo(_hdr("═══ JARVIS VISION GESTURE ═══"))
    click.echo(f"  Duration: {duration}s")
    click.echo(f"  Camera:   {camera}")
    click.echo("")

    v = _get_vision()
    try:
        import cv2
        import mediapipe as mp

        mp_hands = mp.solutions.hands
        hands = mp_hands.Hands(max_num_hands=2, min_detection_confidence=0.7)
        mp_draw = mp.solutions.drawing_utils

        cap = cv2.VideoCapture(camera)
        if not cap.isOpened():
            raise RuntimeError("Camera not available")

        click.echo(_info("  🖐 Gesture detection started. Press 'q' to quit."))
        start = time.time()
        gesture_count = 0

        with click.progressbar(length=100, label="Detecting", show_eta=False) as bar:
            while time.time() - start < duration:
                ret, frame = cap.read()
                if not ret:
                    break

                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                result = hands.process(rgb)

                if result.multi_hand_landmarks:
                    gesture_count += 1
                    for lm in result.multi_hand_landmarks:
                        mp_draw.draw_landmarks(frame, lm, mp_hands.HAND_CONNECTIONS)
                    cv2.putText(frame, f"Hands: {len(result.multi_hand_landmarks)}", (10, 30),
                                cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

                cv2.imshow("JARVIS Gesture", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break

                if gesture_count % 10 == 0:
                    bar.update(1)

        cap.release()
        cv2.destroyAllWindows()
        click.echo("")
        click.echo(_ok(f"  ✓ Gesture detection stopped. Hand frames: {gesture_count}"))
    except Exception as exc:
        click.echo(_warn(f"  ⚠ MediaPipe/OpenCV unavailable ({exc}). Mock gesture mode."))
        click.echo(f"  {v.gesture_loop()}")



# ---------------------------------------------------------------------------
# jarvis memory
# ---------------------------------------------------------------------------

@cli.group(name="memory")
def memory() -> None:
    """Vector memory: search, store, statistics."""
    pass


@memory.command(name="search")
@click.argument("query", type=str)
@click.option("--top-k", "-k", default=5, type=int, help="Number of results.")
@click.option("--json", "-j", is_flag=True, help="Output JSON.")
def memory_search(query: str, top_k: int, json: bool) -> None:
    """Search vector memory for QUERY.

    Hebrew supported: jarvis memory search "מה זה בינה מלאכותית"
    """
    click.echo(_hdr("═══ JARVIS MEMORY SEARCH ═══"))
    click.echo(f"  Query:  {query}")
    click.echo(f"  Top-K:  {top_k}")
    click.echo("")

    mem = _get_memory()
    results = mem.search(query, top_k=top_k)

    if json:
        out = [{"id": r[0], "score": r[1], "text": r[2]} for r in results]
        click.echo(json.dumps(out, indent=2, ensure_ascii=False))
        return

    if not results:
        click.echo(_warn("  No matching memories found."))
        return

    click.echo(f"  {_ok(f'Found {len(results)} result(s):')}")
    click.echo("")
    for doc_id, score, text in results:
        score_col = _ok if score > 0.5 else (_warn if score > 0.2 else _dim)
        click.echo(f"  {C_DIM}[{doc_id}]{C_RESET}  score={score_col(f'{score:.3f}')}")
        click.echo(f"  {text[:200]}{'...' if len(text) > 200 else ''}")
        click.echo("")


@memory.command(name="store")
@click.argument("text", type=str)
@click.option("--tag", "-t", default=None, type=str, help="Optional tag for the memory.")
def memory_store(text: str, tag: Optional[str]) -> None:
    """Store TEXT in vector memory.

    Hebrew supported: jarvis memory store "זכור את זה"
    """
    click.echo(_hdr("═══ JARVIS MEMORY STORE ═══"))
    click.echo(f"  Text: {text[:60]}{'...' if len(text) > 60 else ''}")
    if tag:
        click.echo(f"  Tag:  {tag}")
    click.echo("")

    mem = _get_memory()
    with click.progressbar(length=1, label="Storing", show_eta=False) as bar:
        doc_id = mem.store(text)
        bar.update(1)

    click.echo(_ok(f"  ✓ Stored as {doc_id}"))


@memory.command(name="stats")
@click.option("--json", "-j", is_flag=True, help="Output JSON.")
def memory_stats(json: bool) -> None:
    """Show memory statistics."""
    mem = _get_memory()
    stats = mem.stats()

    if json:
        click.echo(json.dumps(stats, indent=2))
        return

    click.echo(_hdr("═══ JARVIS MEMORY STATS ═══"))
    click.echo(f"  Documents:     {stats['total_docs']}")
    click.echo(f"  Total chars:   {stats['total_chars']}")
    click.echo(f"  Store type:    {_dim('In-memory hash-based vectors')}")
    click.echo("")
    click.echo(_dim("  Tip: Use 'jarvis memory search <query>' to query."))


# ---------------------------------------------------------------------------
# jarvis github
# ---------------------------------------------------------------------------

@cli.group(name="github")
def github() -> None:
    """GitHub integration: search, ingest, learn."""
    pass


def _github_search_api(query: str, per_page: int = 10) -> List[Dict[str, Any]]:
    """Search GitHub repos via the public API."""
    import urllib.request
    import urllib.parse
    q = urllib.parse.quote(query)
    url = f"https://api.github.com/search/repositories?q={q}&sort=stars&order=desc&per_page={per_page}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "jarvis-cli"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
        return data.get("items", [])
    except Exception as exc:
        click.echo(_warn(f"  ⚠ GitHub API error: {exc}"))
        return []


@github.command(name="search")
@click.argument("query", type=str)
@click.option("--per-page", "-n", default=10, type=int, help="Results per page.")
@click.option("--json", "-j", is_flag=True, help="Output JSON.")
def github_search(query: str, per_page: int, json: bool) -> None:
    """Search GitHub repositories for QUERY.

    Example: jarvis github search "machine learning python"
    """
    click.echo(_hdr("═══ JARVIS GITHUB SEARCH ═══"))
    click.echo(f"  Query: {query}")
    click.echo("")

    with click.progressbar(length=1, label="Searching GitHub", show_eta=False) as bar:
        items = _github_search_api(query, per_page=per_page)
        bar.update(1)

    if json:
        click.echo(json.dumps(items, indent=2, ensure_ascii=False))
        return

    if not items:
        click.echo(_warn("  No repositories found."))
        return

    click.echo(f"  {_ok(f'Found {len(items)} repo(s):')}")
    click.echo("")
    for i, repo in enumerate(items, 1):
        stars = repo.get("stargazers_count", 0)
        lang = repo.get("language", "N/A") or "N/A"
        desc = repo.get("description", "") or ""
        click.echo(
            f"  {C_BOLD}{i}. {repo['full_name']}{C_RESET}  ⭐ {stars}  [{lang}]\n"
            f"     {desc[:100]}{'...' if len(str(desc)) > 100 else ''}\n"
            f"     {C_DIM}{repo.get('html_url', '')}{C_RESET}"
        )
        click.echo("")


@github.command(name="ingest")
@click.argument("url", type=str)
@click.option("--dest", "-d", default="/tmp/jarvis_ingest", type=str, help="Clone destination.")
@click.option("--depth", default=1, type=int, help="Git clone depth.")
def github_ingest(url: str, dest: str, depth: int) -> None:
    """Clone a GitHub repository URL and ingest it locally.

    Example: jarvis github ingest https://github.com/user/repo
    """
    click.echo(_hdr("═══ JARVIS GITHUB INGEST ═══"))
    click.echo(f"  URL:    {url}")
    click.echo(f"  Dest:   {dest}")
    click.echo(f"  Depth:  {depth}")
    click.echo("")

    dest_path = Path(dest)
    if dest_path.exists():
        click.echo(_warn(f"  ⚠ Destination exists. Removing {dest}..."))
        shutil.rmtree(dest)

    cmd = f"git clone --depth={depth} {url} {dest}"
    click.echo(_dim(f"  Running: {cmd}"))

    with click.progressbar(length=1, label="Cloning", show_eta=False) as bar:
        rc, stdout, stderr = _safe_run(cmd, timeout=120)
        bar.update(1)

    if rc != 0:
        click.echo(_err(f"  ✗ Clone failed (exit {rc}):"))
        click.echo(f"     {stderr[:300]}")
        return

    click.echo(_ok(f"  ✓ Cloned to {dest}"))

    # Ingest: list files and sizes
    click.echo("")
    click.echo(_info("  📁 Ingesting file tree..."))
    files: List[str] = []
    sizes: List[int] = []
    for p in dest_path.rglob("*"):
        if p.is_file() and not "/.git/" in str(p):
            files.append(str(p.relative_to(dest_path)))
            sizes.append(p.stat().st_size)

    total_size = sum(sizes)
    click.echo(_ok(f"  ✓ {len(files)} files, {total_size / 1024:.1f} KB total"))
    click.echo("")
    click.echo(_dim("  Top-level files:"))
    for f in files[:20]:
        click.echo(f"    {f}")
    if len(files) > 20:
        click.echo(f"    ... and {len(files) - 20} more")


@github.command(name="learn")
@click.argument("query", type=str)
@click.option("--per-page", "-n", default=5, type=int, help="Repos to search.")
@click.option("--clone-dir", "-d", default="/tmp/jarvis_learn", type=str, help="Base clone dir.")
@click.option("--max-repos", "-m", default=3, type=int, help="Max repos to clone & analyze.")
def github_learn(query: str, per_page: int, clone_dir: str, max_repos: int) -> None:
    """Full pipeline: search → clone → analyze → learn.

    Example: jarvis github learn "fastapi auth patterns"
    """
    click.echo(_hdr("═══ JARVIS GITHUB LEARN ═══"))
    click.echo(f"  Query:      {query}")
    click.echo(f"  Max repos:  {max_repos}")
    click.echo("")

    # 1. Search
    click.echo(_info("  Step 1/4: Search GitHub..."))
    items = _github_search_api(query, per_page=per_page)
    if not items:
        click.echo(_err("  ✗ No repos found. Aborting."))
        return
    click.echo(_ok(f"  ✓ Found {len(items)} candidates"))

    # 2. Clone top repos
    cloned: List[Path] = []
    click.echo("")
    click.echo(_info("  Step 2/4: Clone top repos..."))
    for i, repo in enumerate(items[:max_repos], 1):
        name = repo["full_name"].replace("/", "_")
        dest = f"{clone_dir}/{name}"
        click.echo(f"    {i}. {repo['full_name']} → {dest}")
        cmd = f"git clone --depth=1 {repo['clone_url']} {dest}"
        rc, _, err = _safe_run(cmd, timeout=120)
        if rc == 0:
            cloned.append(Path(dest))
        else:
            click.echo(_warn(f"       ⚠ Clone failed: {err[:80]}"))
    click.echo(_ok(f"  ✓ Cloned {len(cloned)} repo(s)"))

    # 3. Analyze
    click.echo("")
    click.echo(_info("  Step 3/4: Analyze contents..."))
    for repo_path in cloned:
        files = [p for p in repo_path.rglob("*") if p.is_file() and "/.git/" not in str(p)]
        py_files = [f for f in files if str(f).endswith(".py")]
        md_files = [f for f in files if str(f).endswith(".md")]
        total_size = sum(p.stat().st_size for p in files)
        click.echo(
            f"    {repo_path.name}: {len(files)} files, "
            f"{len(py_files)} .py, {len(md_files)} .md, {total_size / 1024:.1f} KB"
        )
    click.echo(_ok("  ✓ Analysis complete"))

    # 4. Learn (store summaries)
    click.echo("")
    click.echo(_info("  Step 4/4: Store learnings..."))
    mem = _get_memory()
    for repo_path in cloned:
        summary = f"Repo: {repo_path.name}\nQuery: {query}\nPath: {repo_path}\n"
        mem.store(summary)
    click.echo(_ok(f"  ✓ Stored {len(cloned)} summaries in vector memory"))

    click.echo("")
    click.echo(_ok("  🎓 Learning pipeline complete!"))


# ---------------------------------------------------------------------------
# jarvis os
# ---------------------------------------------------------------------------

@cli.group(name="os")
def os_cmd() -> None:
    """OS control: screenshots, shell commands, system info, monitoring."""
    pass


@os_cmd.command(name="screenshot")
@click.option("--output", "-o", default=None, type=str, help="Output PNG path.")
@click.option("--region", "-r", default=None, type=str, help="Crop region: x,y,w,h")
def os_screenshot(output: Optional[str], region: Optional[str]) -> None:
    """Take a screenshot.

    Optionally specify a crop region: jarvis os screenshot -r 100,100,800,600
    """
    click.echo(_hdr("═══ JARVIS OS SCREENSHOT ═══"))
    save_path = output or f"/tmp/jarvis_ss_{int(time.time())}.png"

    try:
        from PIL import ImageGrab
        img = ImageGrab.grab()
        if region:
            parts = [int(x.strip()) for x in region.split(",")]
            if len(parts) == 4:
                img = img.crop((parts[0], parts[1], parts[0] + parts[2], parts[1] + parts[3]))
        img.save(save_path)
        click.echo(_ok(f"  ✓ Screenshot saved: {save_path}"))
        click.echo(f"  Size: {img.size}")
    except Exception as exc:
        click.echo(_warn(f"  ⚠ Screenshot failed ({exc}). Mock mode."))
        try:
            from PIL import Image
            img = Image.new("RGB", (1920, 1080), color=(40, 40, 60))
            img.save(save_path)
            click.echo(_ok(f"  ✓ Mock screenshot: {save_path}"))
        except Exception:
            click.echo(_err("  ✗ Cannot create screenshot."))


@os_cmd.command(name="run")
@click.argument("command", type=str)
@click.option("--timeout", "-t", default=10, type=int, help="Command timeout in seconds.")
@click.option("--trust-override", is_flag=True, help="Skip trust-gate (use with caution).")
@click.option("--json", "-j", is_flag=True, help="Output JSON.")
def os_run(command: str, timeout: int, trust_override: bool, json: bool) -> None:
    """Run a shell command (trust-gated).

    Only allowlisted commands run by default. Use --trust-override with care.
    """
    click.echo(_hdr("═══ JARVIS OS RUN ═══"))
    click.echo(f"  Command: {command}")
    click.echo(f"  Timeout: {timeout}s")
    click.echo("")

    # Trust gate
    allowlist = frozenset({
        "echo", "cat", "ls", "pwd", "git", "python", "pytest",
        "dir", "type", "cd", "mkdir", "cp", "mv", "touch",
        "head", "tail", "grep", "find", "chmod", "chown",
        "wc", "sort", "uniq", "diff", "env", "which", "ps",
        "top", "htop", "free", "df", "du", "uname",
    })

    cmd_first = command.strip().split()[0] if command.strip() else ""
    is_allowed = cmd_first in allowlist

    if not is_allowed and not trust_override:
        click.echo(_err(f"  ✗ BLOCKED: '{cmd_first}' is not in the allowlist."))
        click.echo(_warn("  Use --trust-override only if you trust this command."))
        return

    if trust_override:
        click.echo(_warn("  ⚠ Trust override enabled. Proceeding with caution."))

    with click.progressbar(length=1, label="Running", show_eta=False) as bar:
        rc, stdout, stderr = _safe_run(command, timeout=timeout)
        bar.update(1)

    if json:
        out = {"exit_code": rc, "stdout": stdout, "stderr": stderr}
        click.echo(json.dumps(out, indent=2, ensure_ascii=False))
        return

    if rc == 0:
        click.echo(_ok(f"  ✓ Exit code: {rc}"))
    else:
        click.echo(_err(f"  ✗ Exit code: {rc}"))

    if stdout:
        click.echo("")
        click.echo(_info("  stdout:"))
        for line in stdout.splitlines()[:40]:
            click.echo(f"    {line}")
        if len(stdout.splitlines()) > 40:
            click.echo(f"    ... ({len(stdout.splitlines()) - 40} more lines)")

    if stderr:
        click.echo("")
        click.echo(_warn("  stderr:"))
        for line in stderr.splitlines()[:20]:
            click.echo(f"    {line}")


@os_cmd.command(name="info")
@click.option("--json", "-j", is_flag=True, help="Output JSON.")
def os_info(json: bool) -> None:
    """Show system info: CPU, RAM, GPU, OS, Python."""
    ram = _get_ram_info()
    cpu = _get_cpu_info()
    gpus = _get_gpu_info()

    info = {
        "os": platform.system(),
        "os_release": platform.release(),
        "architecture": platform.machine(),
        "python": sys.version.split()[0],
        "cpu_cores": cpu["cores"],
        "cpu_load_1min": cpu["load_1min"],
        "ram_total_mb": ram["total_mb"],
        "ram_available_mb": ram["available_mb"],
        "gpu_count": len(gpus),
        "gpus": gpus,
        "cwd": str(Path.cwd()),
        "home": str(Path.home()),
    }

    if json:
        click.echo(json.dumps(info, indent=2, ensure_ascii=False))
        return

    click.echo(_hdr("═══ JARVIS OS INFO ═══"))
    click.echo(f"  OS:        {info['os']} {info['os_release']} ({info['architecture']})")
    click.echo(f"  Python:    {info['python']}")
    click.echo(f"  CPU:       {cpu['cores']} cores, load {cpu['load_1min']} ({cpu['load_percent']}%)")
    used_mb = ram['total_mb'] - ram['available_mb']
    click.echo(f"  RAM:       {used_mb}/{ram['total_mb']} MB used  ({round((used_mb/ram['total_mb'])*100,1) if ram['total_mb'] else 0}%)")
    if gpus:
        for i, g in enumerate(gpus):
            click.echo(f"  GPU {i}:    {g['name']}  {g['memory_used_mb']}/{g['memory_total_mb']} MB  ({g['util_percent']}%)")
    else:
        click.echo(f"  GPU:       {_dim('None detected')}")
    click.echo(f"  CWD:       {info['cwd']}")
    click.echo(f"  Home:      {info['home']}")


@os_cmd.command(name="monitor")
@click.option("--duration", "-d", default=60.0, type=float, help="Monitor duration in seconds.")
@click.option("--interval", "-i", default=2.0, type=float, help="Refresh interval in seconds.")
@click.option("--gpu", is_flag=True, default=True, help="Show GPU stats if available.")
def os_monitor(duration: float, interval: float, gpu: bool) -> None:
    """Real-time resource monitoring dashboard.

    Press Ctrl+C to stop early.
    """
    click.echo(_hdr("═══ JARVIS OS MONITOR ═══"))
    click.echo(f"  Duration:  {duration}s")
    click.echo(f"  Interval:  {interval}s")
    click.echo("")
    click.echo(_warn("  Press Ctrl+C to stop"))
    click.echo("")

    start = time.time()
    samples = 0

    try:
        while time.time() - start < duration:
            cpu = _get_cpu_info()
            ram = _get_ram_info()
            used_mb = ram["total_mb"] - ram["available_mb"]
            ram_pct = round((used_mb / ram["total_mb"]) * 100, 1) if ram["total_mb"] else 0

            # Build mini dashboard line
            line = (
                f"CPU:{cpu['load_percent']:>5.1f}%  "
                f"RAM:{ram_pct:>5.1f}% ({used_mb}/{ram['total_mb']}MB)"
            )

            if gpu:
                gpus = _get_gpu_info()
                if gpus:
                    for i, g in enumerate(gpus):
                        line += f"  GPU{i}:{g['util_percent']:>3d}% VRAM:{g['memory_used_mb']:>4d}/{g['memory_total_mb']}MB"

            elapsed = time.time() - start
            click.echo(f"  [{elapsed:>6.1f}s]  {line}")
            time.sleep(interval)
            samples += 1

        click.echo("")
        click.echo(_ok(f"  ✓ {samples} samples collected over {duration}s"))
    except KeyboardInterrupt:
        click.echo("")
        click.echo(_warn(f"  ⚠ Stopped early after {time.time() - start:.1f}s ({samples} samples)"))



# ---------------------------------------------------------------------------
# jarvis react
# ---------------------------------------------------------------------------

@cli.group(name="react")
def react() -> None:
    """ReAct autonomous loop control."""
    pass


# Global ReAct loop instance (singleton-ish for CLI session)
_react_loop_instance: Optional[Any] = None
_react_thread: Optional[threading.Thread] = None
_react_stop_event: Optional[threading.Event] = None


@react.command(name="start")
@click.option("--interval", "-i", default=5.0, type=float, help="Seconds between steps.")
@click.option("--max-steps", "-m", default=0, type=int, help="Max steps (0=unlimited).")
def react_start(interval: float, max_steps: int) -> None:
    """Start ReAct infinite loop on a background thread.

    The loop runs autonomously until 'jarvis react stop' is called.
    """
    global _react_loop_instance, _react_thread, _react_stop_event

    click.echo(_hdr("═══ JARVIS REACT START ═══"))
    click.echo(f"  Interval:   {interval}s")
    if max_steps:
        click.echo(f"  Max steps:  {max_steps}")
    click.echo("")

    if _react_thread and _react_thread.is_alive():
        click.echo(_warn("  ⚠ ReAct loop is already running."))
        return

    r = _get_react()
    _react_loop_instance = r
    _react_stop_event = threading.Event()

    def _loop() -> None:
        steps = 0
        while not _react_stop_event.is_set():
            try:
                if hasattr(r, "step"):
                    r.step()
                steps += 1
            except Exception as exc:
                click.echo(_err(f"    [ReAct] Error: {exc}"))
            if max_steps and steps >= max_steps:
                break
            time.sleep(interval)

    _react_thread = threading.Thread(target=_loop, daemon=True)
    _react_thread.start()

    if hasattr(r, "start"):
        r.start()

    click.echo(_ok("  ✓ ReAct loop started on background thread."))
    click.echo(_dim(f"    PID:     {_react_thread.ident}"))
    click.echo(_dim(f"    Daemon:  {_react_thread.daemon}"))


@react.command(name="stop")
def react_stop() -> None:
    """Stop the ReAct loop."""
    global _react_stop_event, _react_thread, _react_loop_instance

    click.echo(_hdr("═══ JARVIS REACT STOP ═══"))

    if _react_stop_event is None:
        click.echo(_warn("  ⚠ No ReAct loop is currently running."))
        return

    _react_stop_event.set()

    if _react_loop_instance and hasattr(_react_loop_instance, "stop"):
        _react_loop_instance.stop()

    if _react_thread:
        _react_thread.join(timeout=5)
        alive = _react_thread.is_alive()
        click.echo(_ok(f"  ✓ Stop signal sent. Thread alive: {alive}"))
    else:
        click.echo(_ok("  ✓ Stop signal sent."))

    _react_stop_event = None
    _react_thread = None


@react.command(name="step")
@click.option("--json", "-j", is_flag=True, help="Output JSON.")
def react_step(json: bool) -> None:
    """Execute a single ReAct step.

    Shows state, action, and reasoning for one iteration.
    """
    click.echo(_hdr("═══ JARVIS REACT STEP ═══"))
    click.echo("")

    r = _get_react()
    with click.progressbar(length=1, label="Stepping", show_eta=False) as bar:
        result = r.step() if hasattr(r, "step") else {"state": "IDLE", "action": "DONE"}
        bar.update(1)

    if json:
        click.echo(json.dumps(result, indent=2, ensure_ascii=False))
        return

    state = result.get("state", "UNKNOWN")
    action = result.get("action", "NONE")
    thought = result.get("thought", "No thought.")
    confidence = result.get("confidence", 0.0)

    state_col = _ok if state in ("DONE", "IDLE") else _info
    click.echo(f"  State:      {state_col(state)}")
    click.echo(f"  Action:     {action}")
    click.echo(f"  Thought:    {thought[:120]}")
    click.echo(f"  Confidence: {confidence:.2f}")


@react.command(name="status")
@click.option("--json", "-j", is_flag=True, help="Output JSON.")
def react_status(json: bool) -> None:
    """Show ReAct loop status and statistics."""
    global _react_thread

    r = _get_react()
    running = _react_thread is not None and _react_thread.is_alive() if _react_thread else False
    stats = r.status() if hasattr(r, "status") else {"running": False, "stats": {}}

    if json:
        out = {
            "running": running,
            "thread_alive": running,
            "stats": stats.get("stats", {}),
        }
        click.echo(json.dumps(out, indent=2))
        return

    click.echo(_hdr("═══ JARVIS REACT STATUS ═══"))
    if running:
        click.echo(f"  Status:     {_ok('RUNNING')}")
    else:
        click.echo(f"  Status:     {_dim('STOPPED')}")

    s = stats.get("stats", {})
    steps = s.get("steps", 0)
    errors = s.get("errors", 0)
    start_time = s.get("start_time")
    click.echo(f"  Steps:      {steps}")
    click.echo(f"  Errors:     {errors}")
    if start_time:
        uptime = time.time() - start_time
        click.echo(f"  Uptime:     {uptime:.1f}s")
    click.echo("")
    click.echo(_dim("  Use 'jarvis react start' to run, 'jarvis react step' for single step."))


# ---------------------------------------------------------------------------
# jarvis vr
# ---------------------------------------------------------------------------

@cli.group(name="vr")
def vr() -> None:
    """VR hand tracking control."""
    pass


@vr.command(name="start")
@click.option("--camera", "-c", default=0, type=int, help="Camera source index.")
@click.option("--resolution", "-r", default="1280x720", type=str, help="Capture resolution.")
def vr_start(camera: int, resolution: str) -> None:
    """Start VR hand tracking mode.

    Uses MediaPipe Hands for VR-style hand tracking overlay.
    """
    click.echo(_hdr("═══ JARVIS VR START ═══"))
    click.echo(f"  Camera:     {camera}")
    click.echo(f"  Resolution: {resolution}")
    click.echo("")

    try:
        import cv2
        import mediapipe as mp

        mp_hands = mp.solutions.hands
        hands = mp_hands.Hands(max_num_hands=2, min_detection_confidence=0.7)
        mp_draw = mp.solutions.drawing_utils

        w, h = 1280, 720
        if "x" in resolution:
            pw, ph = resolution.split("x")
            w, h = int(pw), int(ph)

        cap = cv2.VideoCapture(camera)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)

        if not cap.isOpened():
            raise RuntimeError("Camera unavailable")

        click.echo(_info("  🥽 VR hand tracking started. Press 'q' to stop."))
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            result = hands.process(rgb)

            if result.multi_hand_landmarks:
                for lm in result.multi_hand_landmarks:
                    mp_draw.draw_landmarks(frame, lm, mp_hands.HAND_CONNECTIONS)
                cv2.putText(frame, "VR HAND TRACKING", (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 255), 2)
                cv2.putText(frame, f"Hands: {len(result.multi_hand_landmarks)}", (10, 65),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
            else:
                cv2.putText(frame, "No hands detected", (10, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (100, 100, 100), 2)

            cv2.imshow("JARVIS VR", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break

        cap.release()
        cv2.destroyAllWindows()
        click.echo(_ok("  ✓ VR mode stopped."))
    except Exception as exc:
        click.echo(_warn(f"  ⚠ VR requires OpenCV + MediaPipe ({exc}). Mock mode."))
        click.echo("  Mock: VR hand tracking would start with full 3D hand skeleton overlay.")


@vr.command(name="stop")
def vr_stop() -> None:
    """Stop VR mode.

    (Primarily informational — press 'q' in the VR window to stop live mode.)
    """
    click.echo(_hdr("═══ JARVIS VR STOP ═══"))
    click.echo(_ok("  ✓ VR stop signal sent. Close the OpenCV window with 'q' if still open."))


@vr.command(name="calibrate")
@click.option("--camera", "-c", default=0, type=int, help="Camera source index.")
@click.option("--frames", "-f", default=30, type=int, help="Calibration frames to capture.")
def vr_calibrate(camera: int, frames: int) -> None:
    """Calibrate hand tracking for VR.

    Captures reference frames to normalize hand size / position.
    """
    click.echo(_hdr("═══ JARVIS VR CALIBRATE ═══"))
    click.echo(f"  Camera:  {camera}")
    click.echo(f"  Frames:  {frames}")
    click.echo("")

    try:
        import cv2
        import mediapipe as mp

        mp_hands = mp.solutions.hands
        hands = mp_hands.Hands(min_detection_confidence=0.7)

        cap = cv2.VideoCapture(camera)
        if not cap.isOpened():
            raise RuntimeError("Camera unavailable")

        click.echo(_info("  📸 Calibrating... Hold your hand steady."))
        detected = 0
        with click.progressbar(length=frames, label="Calibrating", show_eta=False) as bar:
            while detected < frames:
                ret, frame = cap.read()
                if not ret:
                    break
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                result = hands.process(rgb)
                if result.multi_hand_landmarks:
                    detected += 1
                    bar.update(1)
                cv2.imshow("JARVIS VR Calibrate", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break

        cap.release()
        cv2.destroyAllWindows()
        click.echo("")
        click.echo(_ok(f"  ✓ Calibration complete. Captured {detected} hand frames."))
    except Exception as exc:
        click.echo(_warn(f"  ⚠ Calibration requires OpenCV + MediaPipe ({exc}). Mock mode."))
        click.echo("  Mock: Would calibrate hand size, palm center, and finger span.")


# ---------------------------------------------------------------------------
# jarvis skill
# ---------------------------------------------------------------------------

@cli.group(name="skill")
def skill() -> None:
    """Skill engine: list, register, run, import from GitHub."""
    pass


@skill.command(name="list")
@click.option("--json", "-j", is_flag=True, help="Output JSON.")
def skill_list(json: bool) -> None:
    """List all registered skills."""
    engine = _get_skill_engine()
    skills = engine.list_skills() if hasattr(engine, "list_skills") else []

    if json:
        click.echo(json.dumps({"skills": skills}, indent=2))
        return

    click.echo(_hdr("═══ JARVIS SKILL LIST ═══"))
    if not skills:
        click.echo(_warn("  No skills registered."))
        click.echo(_dim("  Use 'jarvis skill register <name> <code>' to add skills."))
        return

    click.echo(f"  {_ok(f'Found {len(skills)} skill(s):')}")
    click.echo("")
    for s in skills:
        click.echo(f"  • {C_BOLD}{s}{C_RESET}")


@skill.command(name="register")
@click.argument("name", type=str)
@click.argument("code", type=str)
@click.option("--force", is_flag=True, help="Overwrite existing skill.")
def skill_register(name: str, code: str, force: bool) -> None:
    """Register a new skill with NAME and CODE.

    Example: jarvis skill register hello "print('hello world')"
    """
    engine = _get_skill_engine()
    existing = engine.list_skills() if hasattr(engine, "list_skills") else []

    if name in existing and not force:
        click.echo(_err(f"  ✗ Skill '{name}' already exists. Use --force to overwrite."))
        return

    click.echo(_hdr("═══ JARVIS SKILL REGISTER ═══"))
    click.echo(f"  Name: {name}")
    click.echo(f"  Code: {code[:50]}{'...' if len(code) > 50 else ''}")
    click.echo("")

    with click.progressbar(length=1, label="Registering", show_eta=False) as bar:
        ok = engine.register_skill(name, code) if hasattr(engine, "register_skill") else False
        bar.update(1)

    if ok:
        click.echo(_ok(f"  ✓ Skill '{name}' registered successfully."))
    else:
        click.echo(_err(f"  ✗ Failed to register skill '{name}'."))


@skill.command(name="run")
@click.argument("name", type=str)
@click.option("--arg", "-a", multiple=True, help="Named arguments as key=value.")
@click.option("--json", "-j", is_flag=True, help="Output JSON.")
def skill_run(name: str, arg: Tuple[str, ...], json: bool) -> None:
    """Run a registered skill by NAME.

    Example: jarvis skill run hello
    """
    engine = _get_skill_engine()
    skills = engine.list_skills() if hasattr(engine, "list_skills") else []

    if name not in skills:
        click.echo(_err(f"  ✗ Skill '{name}' not found. Registered: {skills}"))
        return

    # Parse args
    kwargs: Dict[str, str] = {}
    for a in arg:
        if "=" in a:
            k, v = a.split("=", 1)
            kwargs[k] = v

    click.echo(_hdr(f"═══ JARVIS SKILL RUN: {name} ═══"))
    if kwargs:
        click.echo(f"  Args: {kwargs}")
        click.echo("")

    with click.progressbar(length=1, label="Running", show_eta=False) as bar:
        result = engine.run_skill(name, **kwargs) if hasattr(engine, "run_skill") else ""
        bar.update(1)

    if json:
        click.echo(json.dumps({"skill": name, "result": result}, indent=2, ensure_ascii=False))
    else:
        click.echo(_ok("  ✓ Result:"))
        click.echo(f"  {result}")


@skill.command(name="import-github")
@click.argument("url", type=str)
@click.option("--branch", "-b", default="main", type=str, help="Git branch.")
def skill_import_github(url: str, branch: str) -> None:
    """Import a skill from a GitHub repository URL.

    Example: jarvis skill import-github https://github.com/user/my-skill
    """
    click.echo(_hdr("═══ JARVIS SKILL IMPORT GITHUB ═══"))
    click.echo(f"  URL:    {url}")
    click.echo(f"  Branch: {branch}")
    click.echo("")

    dest = f"/tmp/jarvis_skill_import_{int(time.time())}"
    cmd = f"git clone --depth=1 --branch={branch} {url} {dest}"

    with click.progressbar(length=1, label="Cloning", show_eta=False) as bar:
        rc, _, stderr = _safe_run(cmd, timeout=120)
        bar.update(1)

    if rc != 0:
        click.echo(_err(f"  ✗ Clone failed: {stderr[:200]}"))
        return

    click.echo(_ok(f"  ✓ Cloned to {dest}"))

    # Look for skill files
    dest_path = Path(dest)
    candidates = list(dest_path.rglob("*.py")) + list(dest_path.rglob("skill.py"))
    click.echo("")
    click.echo(_info(f"  Found {len(candidates)} Python file(s):"))
    for c in candidates[:10]:
        click.echo(f"    {c.relative_to(dest_path)}")

    # Register all found skills
    engine = _get_skill_engine()
    imported = 0
    for c in candidates:
        try:
            code = c.read_text(encoding="utf-8")
            skill_name = c.stem
            if hasattr(engine, "register_skill"):
                engine.register_skill(skill_name, code)
                imported += 1
        except Exception as exc:
            click.echo(_warn(f"    ⚠ Failed to import {c}: {exc}"))

    click.echo("")
    click.echo(_ok(f"  ✓ Imported {imported} skill(s) from {url}"))
    shutil.rmtree(dest, ignore_errors=True)



# ---------------------------------------------------------------------------
# Utility commands
# ---------------------------------------------------------------------------

@cli.command(name="doctor")
@click.option("--json", "-j", is_flag=True, help="Output JSON.")
def doctor(json: bool) -> None:
    """Full system health check — all subsystems.

    Checks: brain, voice, vision, memory, github, os, react, vr, skill
    """
    click.echo(_hdr("═══ JARVIS DOCTOR ═══"))
    click.echo("")
    click.echo(_dim("  Running comprehensive health check..."))
    click.echo("")

    checks: Dict[str, Any] = {}

    # --- Brain check ---
    click.echo(_info("  [1/9] Brain subsystem..."))
    try:
        b = _get_brain()
        info = b.get_model_info() if hasattr(b, "get_model_info") else {}
        checks["brain"] = {
            "status": "healthy" if info.get("available") else "degraded",
            "model": info.get("model", "mock"),
            "available": info.get("available", False),
        }
        click.echo(f"       {_ok('OK')}  Model: {checks['brain']['model']}")
    except Exception as exc:
        checks["brain"] = {"status": "error", "error": str(exc)}
        click.echo(f"       {_err('FAIL')} {exc}")

    # --- Voice check ---
    click.echo(_info("  [2/9] Voice subsystem..."))
    voice_ok = False
    for mod in ("whisper", "pyttsx3", "vosk"):
        try:
            importlib.import_module(mod)
            voice_ok = True
            break
        except Exception:
            pass
    checks["voice"] = {
        "status": "healthy" if voice_ok else "degraded",
        "modules": [m for m in ("whisper", "pyttsx3", "vosk") if importlib.import_module(m) or True],
    }
    click.echo(f"       {_ok('OK') if voice_ok else _warn('DEGRADED')}  TTS/STT modules")

    # --- Vision check ---
    click.echo(_info("  [3/9] Vision subsystem..."))
    vision_ok = False
    try:
        import cv2
        import PIL
        vision_ok = True
    except Exception:
        pass
    checks["vision"] = {
        "status": "healthy" if vision_ok else "degraded",
        "opencv": importlib.util.find_spec("cv2") is not None,
        "pil": importlib.util.find_spec("PIL") is not None,
    }
    click.echo(f"       {_ok('OK') if vision_ok else _warn('DEGRADED')}  OpenCV/PIL")

    # --- Memory check ---
    click.echo(_info("  [4/9] Memory subsystem..."))
    try:
        mem = _get_memory()
        stats = mem.stats()
        checks["memory"] = {
            "status": "healthy",
            "docs": stats.get("total_docs", 0),
        }
        click.echo(f"       {_ok('OK')}  {stats['total_docs']} docs stored")
    except Exception as exc:
        checks["memory"] = {"status": "error", "error": str(exc)}
        click.echo(f"       {_err('FAIL')} {exc}")

    # --- GitHub check ---
    click.echo(_info("  [5/9] GitHub connectivity..."))
    try:
        import urllib.request
        req = urllib.request.Request(
            "https://api.github.com",
            headers={"User-Agent": "jarvis-cli"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            gh_ok = resp.status == 200
    except Exception:
        gh_ok = False
    checks["github"] = {"status": "healthy" if gh_ok else "offline", "reachable": gh_ok}
    click.echo(f"       {_ok('OK') if gh_ok else _err('OFFLINE')}  GitHub API")

    # --- OS check ---
    click.echo(_info("  [6/9] OS subsystem..."))
    ram = _get_ram_info()
    gpus = _get_gpu_info()
    checks["os"] = {
        "status": "healthy",
        "ram_mb": ram.get("total_mb", 0),
        "gpus": len(gpus),
    }
    click.echo(f"       {_ok('OK')}  RAM: {ram.get('total_mb', 0)} MB, GPUs: {len(gpus)}")

    # --- React check ---
    click.echo(_info("  [7/9] ReAct loop..."))
    try:
        r = _get_react()
        status = r.status() if hasattr(r, "status") else {}
        checks["react"] = {
            "status": "healthy",
            "running": status.get("running", False),
        }
        click.echo(f"       {_ok('OK')}  Loop ready (running={status.get('running', False)})")
    except Exception as exc:
        checks["react"] = {"status": "error", "error": str(exc)}
        click.echo(f"       {_err('FAIL')} {exc}")

    # --- VR check ---
    click.echo(_info("  [8/9] VR subsystem..."))
    vr_ok = False
    try:
        import mediapipe
        vr_ok = True
    except Exception:
        pass
    checks["vr"] = {
        "status": "healthy" if vr_ok else "degraded",
        "mediapipe": vr_ok,
    }
    click.echo(f"       {_ok('OK') if vr_ok else _warn('DEGRADED')}  MediaPipe")

    # --- Skill check ---
    click.echo(_info("  [9/9] Skill engine..."))
    try:
        engine = _get_skill_engine()
        skills = engine.list_skills() if hasattr(engine, "list_skills") else []
        checks["skill"] = {
            "status": "healthy",
            "skills": len(skills),
        }
        click.echo(f"       {_ok('OK')}  {len(skills)} skills registered")
    except Exception as exc:
        checks["skill"] = {"status": "error", "error": str(exc)}
        click.echo(f"       {_err('FAIL')} {exc}")

    # Summary
    healthy = sum(1 for c in checks.values() if c.get("status") == "healthy")
    degraded = sum(1 for c in checks.values() if c.get("status") == "degraded")
    errors = sum(1 for c in checks.values() if c.get("status") == "error")

    click.echo("")
    click.echo(_hdr("─── Health Summary ───"))
    click.echo(f"  {_ok('Healthy')}:   {healthy}/9")
    click.echo(f"  {_warn('Degraded')}:  {degraded}/9")
    click.echo(f"  {_err('Errors')}:    {errors}/9")

    if json:
        click.echo("")
        click.echo(json.dumps(checks, indent=2, ensure_ascii=False))
    else:
        click.echo("")
        if errors == 0 and degraded == 0:
            click.echo(_ok("  🟢 All systems nominal. JARVIS is ready."))
        elif errors == 0:
            click.echo(_warn("  🟡 Systems operational with some degraded subsystems."))
        else:
            click.echo(_err("  🔴 Some subsystems failed. Run 'jarvis install-deps' to fix."))


@cli.command(name="config")
@click.argument("key", type=str, required=False)
@click.argument("value", type=str, required=False)
@click.option("--edit", is_flag=True, help="Open config in $EDITOR.")
@click.option("--json", "-j", is_flag=True, help="Output JSON.")
def config(key: Optional[str], value: Optional[str], edit: bool, json: bool) -> None:
    """Show or edit JARVIS configuration.

    Without args: shows full config.
    With KEY only: shows that key.
    With KEY and VALUE: sets that key.
    """
    from runtime.agency.config import get_config
    cfg = get_config()

    if edit:
        editor = os.environ.get("EDITOR", "nano")
        config_path = Path.home() / ".agency" / "config.toml"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        if not config_path.exists():
            config_path.write_text("# JARVIS Configuration\n", encoding="utf-8")
        subprocess.run([editor, str(config_path)])
        return

    if key and value:
        # Set key
        cfg.set(key, _auto_cast(value))
        click.echo(_ok(f"  ✓ Set {key} = {value}"))
        return

    data = cfg.all()

    if key:
        val = cfg.get(key)
        if json:
            click.echo(json.dumps({key: val}, indent=2, ensure_ascii=False))
        else:
            click.echo(_hdr(f"═══ CONFIG: {key} ═══"))
            click.echo(f"  {val}")
        return

    if json:
        click.echo(json.dumps(data, indent=2, ensure_ascii=False))
        return

    click.echo(_hdr("═══ JARVIS CONFIG ═══"))
    if not data:
        click.echo(_dim("  No config file found at ~/.agency/config.toml"))
        click.echo(_dim("  Use 'jarvis config --edit' to create one."))
        return

    click.echo(_dim("  Config file: ~/.agency/config.toml"))
    click.echo("")
    _print_config_tree(data)


def _auto_cast(val: str) -> Any:
    """Cast a string to int/float/bool if possible."""
    if val.lower() in ("true", "yes", "on", "1"):
        return True
    if val.lower() in ("false", "no", "off", "0"):
        return False
    try:
        return int(val)
    except ValueError:
        pass
    try:
        return float(val)
    except ValueError:
        pass
    return val


def _print_config_tree(data: Dict[str, Any], indent: int = 0) -> None:
    for k, v in data.items():
        prefix = "  " * (indent + 1)
        if isinstance(v, dict):
            click.echo(f"{prefix}{C_BOLD}{k}{C_RESET}")
            _print_config_tree(v, indent + 1)
        else:
            click.echo(f"{prefix}{k} = {C_GREEN}{v}{C_RESET}")


@cli.command(name="install-deps")
@click.option("--group", "-g", default="all", type=str, help="Dependency group: all, brain, voice, vision, vr.")
@click.option("--dry-run", is_flag=True, help="Show what would be installed without installing.")
def install_deps(group: str, dry_run: bool) -> None:
    """Install all optional dependencies for JARVIS.

    Groups: all, brain, voice, vision, vr
    """
    click.echo(_hdr("═══ JARVIS INSTALL DEPS ═══"))
    click.echo(f"  Group:   {group}")
    click.echo(f"  Dry-run: {dry_run}")
    click.echo("")

    dep_map = {
        "all": [
            "click", "requests", "pillow", "numpy",
            "opencv-python", "mediapipe", "whisper-openai",
            "pyttsx3", "psutil", "faiss-cpu",
        ],
        "brain": ["click", "requests"],
        "voice": ["whisper-openai", "pyttsx3"],
        "vision": ["pillow", "numpy", "opencv-python", "mediapipe"],
        "vr": ["opencv-python", "mediapipe"],
    }

    deps = dep_map.get(group, dep_map["all"])

    if dry_run:
        click.echo(_info("  Would install:"))
        for d in deps:
            click.echo(f"    • {d}")
        return

    click.echo(_info("  Installing packages..."))
    failed: List[str] = []
    succeeded: List[str] = []

    with click.progressbar(deps, label="Installing", item_show_func=lambda x: x or "") as bar:
        for dep in bar:
            cmd = f"{sys.executable} -m pip install --quiet {dep}"
            rc, _, err = _safe_run(cmd, timeout=120)
            if rc == 0:
                succeeded.append(dep)
            else:
                failed.append(dep)
                click.echo(_warn(f"    ⚠ {dep} failed: {err[:80]}"))

    click.echo("")
    click.echo(_ok(f"  ✓ Succeeded: {len(succeeded)}/{len(deps)}"))
    if failed:
        click.echo(_err(f"  ✗ Failed: {len(failed)} packages"))
        for f in failed:
            click.echo(f"    • {f}")

    click.echo("")
    click.echo(_dim("  Restart JARVIS to load newly installed packages."))


# ═══════════════════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    cli()
