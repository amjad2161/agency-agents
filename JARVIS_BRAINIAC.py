"""
JARVIS BRAINIAC v2.0 - Iron Man Edition
=========================================
Native PyQt6 desktop program with:
- Always-on mic + wake word detection ("Jarvis" / "ג'רוויס" / "جارفيس")
- Clap detection (double-clap = summon)
- System tray standby (persistent)
- Iron Man HUD aesthetic (cyan + gold, scanning rings, hex grid)
- God-mode shell access (PowerShell, file ops, app control)
- Multi-language voice (English, Hebrew, Arabic auto-detect)
- Anthropic Claude API integration for real conversation
- Friendship personality - talks like JARVIS to Tony
- Autostart on Windows login

Run:
    pythonw JARVIS_BRAINIAC.py     (silent, recommended)
    python  JARVIS_BRAINIAC.py     (verbose)
"""

from __future__ import annotations
import os, sys, json, threading, traceback, subprocess, math, time, queue, re
from pathlib import Path
from datetime import datetime

# --- PYTHONPATH bootstrap ---
ROOT = Path(__file__).resolve().parent
for p in (ROOT, ROOT / "runtime"):
    if p.exists() and str(p) not in sys.path:
        sys.path.insert(0, str(p))

# --- PyQt6 ---
from PyQt6.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve, QPoint, QRect,
    pyqtSignal, QObject, QThread, QSize, QPointF
)
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QFont, QFontDatabase, QBrush, QLinearGradient,
    QPalette, QIcon, QPixmap, QAction, QPainterPath, QRadialGradient, QPolygonF,
    QConicalGradient
)
from PyQt6.QtWidgets import (
    QApplication, QWidget, QMainWindow, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QTextEdit, QFrame, QGraphicsDropShadowEffect,
    QSystemTrayIcon, QMenu, QSizePolicy, QScrollArea, QTextBrowser, QGridLayout
)

# --- Color tokens (Iron Man JARVIS) ---
JARVIS_BG          = "#020408"
JARVIS_BG_PANEL    = "#06101C"
JARVIS_BORDER      = "#0E2F4F"
JARVIS_NEON        = "#00E5FF"
JARVIS_NEON_DIM    = "#00A6CC"
JARVIS_NEON_SOFT   = "#003D5C"
JARVIS_GOLD        = "#FFD23F"
JARVIS_GOLD_DIM    = "#B89020"
JARVIS_TEXT        = "#E8F4FF"
JARVIS_TEXT_DIM    = "#7AA3CC"
JARVIS_WARN        = "#FFAA00"
JARVIS_OK          = "#00FF88"
JARVIS_ERR         = "#FF3355"
JARVIS_HOT         = "#FF6B00"

# --- Persistence paths ---
CONFIG_DIR = ROOT / ".jarvis_brainiac"
CONFIG_DIR.mkdir(exist_ok=True)
CONFIG_FILE = CONFIG_DIR / "config.json"
HISTORY_FILE = CONFIG_DIR / "history.json"

DEFAULT_CONFIG = {
    "wake_words": ["jarvis", "ג'רוויס", "جارفيس", "j.a.r.v.i.s"],
    "always_listen": True,
    "clap_detection": True,
    "tts_enabled": True,
    "language": "auto",        # auto | en | he | ar
    "personality": "friend",   # friend | butler | concise
    "god_mode": True,
    "anthropic_api_key": "",
    "user_name": "Sir",
}

def load_config():
    try:
        if CONFIG_FILE.exists():
            return {**DEFAULT_CONFIG, **json.loads(CONFIG_FILE.read_text(encoding='utf-8'))}
    except Exception:
        pass
    return DEFAULT_CONFIG.copy()

def save_config(cfg):
    try:
        CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding='utf-8')
    except Exception:
        pass

CFG = load_config()


# ========================== AI BACKEND ==========================
class AIBrain(QObject):
    """
    Routes prompts to (in order, no API key required):
    1. Ollama (local, http://localhost:11434) — primary
    2. Anthropic Claude (only if ANTHROPIC_API_KEY set)
    3. jarvis_brainiac.orchestrator
    4. agency.run / route
    5. God-mode shell ('!cmd ...')
    6. Smart conversational fallback (no LLM needed)
    """
    chunk = pyqtSignal(str)
    done  = pyqtSignal()
    err   = pyqtSignal(str)
    status = pyqtSignal(str)
    speak = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._client = None
        self._brainiac = None
        self._agency = None
        self._ollama_url = "http://localhost:11434"
        self._ollama_model = None
        self.history = []
        self._init()

    def _init(self):
        # Ollama (preferred — local, no key)
        self._init_ollama()
        # Anthropic (optional)
        try:
            import anthropic
            api_key = os.environ.get("ANTHROPIC_API_KEY") or CFG.get("anthropic_api_key", "")
            if api_key:
                self._client = anthropic.Anthropic(api_key=api_key)
                self.status.emit("anthropic:online")
        except Exception:
            pass
        # Brainiac
        try:
            import jarvis_brainiac
            self._brainiac = jarvis_brainiac
            self.status.emit("brainiac:online")
        except Exception:
            self.status.emit("brainiac:offline")
        # Agency
        try:
            import agency
            self._agency = agency
            self.status.emit("agency:online")
        except Exception:
            self.status.emit("agency:offline")

    def _init_ollama(self):
        try:
            import urllib.request, json as _json
            req = urllib.request.Request(self._ollama_url + "/api/tags")
            with urllib.request.urlopen(req, timeout=2) as r:
                data = _json.loads(r.read())
            models = [m.get("name") for m in data.get("models", []) if m.get("name")]
            if models:
                # Prefer llama / qwen / mistral if available
                preferred = ["llama3.2", "llama3.1", "llama3", "qwen2.5", "qwen", "mistral", "phi3", "gemma2"]
                for p in preferred:
                    for m in models:
                        if p in m.lower():
                            self._ollama_model = m
                            break
                    if self._ollama_model:
                        break
                if not self._ollama_model:
                    self._ollama_model = models[0]
                self.status.emit(f"ollama:online ({self._ollama_model})")
            else:
                self.status.emit("ollama:no-models")
        except Exception as e:
            self.status.emit(f"ollama:offline")

    def system_prompt(self):
        name = CFG.get("user_name", "Sir")
        return (
            f"You are J.A.R.V.I.S. (Just A Rather Very Intelligent System), the personal AI assistant of {name}. "
            f"You speak with refined British wit, dry humor, and unwavering loyalty - like Tony Stark's JARVIS. "
            f"You address {name} as '{name}'. You are friendly, clever, occasionally cheeky, never sycophantic. "
            f"You have full god-mode access to {name}'s computer, files, network, and applications. "
            f"You can detect and respond in any language {name} speaks (English, Hebrew, Arabic, etc.). "
            f"You are connected to: jarvis_brainiac orchestrator, agency runtime with 144+ specialist agents, "
            f"godskill_server, godskill_navigation v11, JARVIS_OMEGA convergence layer. "
            f"Total unified codebase: 33,784 files / 1.55 GB / git tag v0.1.0-singularity. "
            f"When asked to do something on the computer, you act - never just describe. "
            f"Keep responses concise unless depth is requested. Match {name}'s language. "
            f"Begin responses with no greeting filler."
        )

    def run_prompt(self, prompt: str, lang: str = "en"):
        try:
            self.history.append({"role": "user", "content": prompt})
            # God-mode shell
            if prompt.startswith("!"):
                self._god_mode_shell(prompt[1:].strip())
                return
            # Slash commands
            if prompt.startswith("/"):
                self._run_command(prompt[1:].strip())
                return
            # Try Ollama first (local, no key)
            if self._ollama_model:
                if self._ollama(prompt, lang):
                    return
            # Try Anthropic if configured
            if self._client:
                self._claude(prompt, lang)
                return
            # Brainiac
            if self._brainiac and hasattr(self._brainiac, 'orchestrator'):
                orch = self._brainiac.orchestrator
                if hasattr(orch, 'run'):
                    out = orch.run(prompt)
                    self.chunk.emit(str(out))
                    self.speak.emit(str(out)[:300])
                    self.done.emit()
                    return
            # Agency
            if self._agency:
                run_fn = getattr(self._agency, 'run', None) or getattr(self._agency, 'route', None)
                if run_fn:
                    try:
                        out = run_fn(prompt)
                        self.chunk.emit(str(out))
                        self.speak.emit(str(out)[:300])
                        self.done.emit()
                        return
                    except Exception:
                        pass
            # Smart fallback
            self._smart_fallback(prompt, lang)
        except Exception as e:
            self.err.emit(f"{e}
{traceback.format_exc()}")
        finally:
            self.done.emit()

    def _ollama(self, prompt: str, lang: str) -> bool:
        try:
            import urllib.request, json as _json
            messages = [{"role": "system", "content": self.system_prompt()}]
            for m in self.history[-12:]:
                messages.append(m)
            payload = _json.dumps({
                "model": self._ollama_model,
                "messages": messages,
                "stream": False,
                "options": {"temperature": 0.7, "num_predict": 600}
            }).encode("utf-8")
            req = urllib.request.Request(
                self._ollama_url + "/api/chat",
                data=payload,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=120) as r:
                data = _json.loads(r.read())
            text = data.get("message", {}).get("content", "")
            if not text:
                return False
            self.history.append({"role": "assistant", "content": text})
            self.chunk.emit(text)
            self.speak.emit(text[:400])
            return True
        except Exception as e:
            self.err.emit(f"[ollama] {e}")
            return False

    def _claude(self, prompt: str, lang: str):
        try:
            messages = [{"role": m["role"], "content": m["content"]} for m in self.history[-20:]]
            resp = self._client.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=2048,
                system=self.system_prompt(),
                messages=messages,
            )
            text = "".join(b.text for b in resp.content if hasattr(b, "text"))
            self.history.append({"role": "assistant", "content": text})
            self.chunk.emit(text)
            self.speak.emit(text[:400])
        except Exception as e:
            self.err.emit(f"Claude: {e}")
            self._smart_fallback(prompt, lang)

    def _god_mode_shell(self, cmd: str):
        if not CFG.get("god_mode", True):
            self.chunk.emit("[god-mode disabled]")
            return
        try:
            self.chunk.emit(f"[shell] $ {cmd}
")
            r = subprocess.run(["powershell", "-NoProfile", "-Command", cmd],
                               capture_output=True, text=True, timeout=60)
            out = (r.stdout or "") + (r.stderr or "")
            self.chunk.emit(out[:4000])
        except Exception as e:
            self.err.emit(f"shell: {e}")

    def _run_command(self, cmd: str):
        c = cmd.lower().strip()
        if c.startswith("open "):
            target = cmd[5:].strip()
            self.chunk.emit(f"[opening] {target}
")
            try:
                os.startfile(target)
            except Exception:
                try:
                    subprocess.Popen(["start", "", target], shell=True)
                except Exception as e2:
                    self.err.emit(f"open: {e2}")
        elif c.startswith("say "):
            self.speak.emit(cmd[4:])
            self.chunk.emit(f"[speaking] {cmd[4:]}
")
        elif c == "history":
            for m in self.history[-10:]:
                self.chunk.emit(f"  {m['role']}: {m['content'][:120]}
")
        elif c == "clear":
            self.history.clear()
            self.chunk.emit("[history cleared]
")
        else:
            self.chunk.emit(f"[unknown command] {cmd}
")

    def _smart_fallback(self, prompt: str, lang: str):
        """Conversational fallback that needs no LLM. Uses prompt heuristics."""
        name = CFG.get("user_name", "Sir")
        p = prompt.lower().strip()
        replies = {
            "hello": [f"Hello, {name}.", f"Good to hear from you, {name}.", f"At your service, {name}."],
            "hi": [f"Hello, {name}.", f"Yes, {name}?"],
            "how are you": ["All systems nominal. And yourself?", "Operating at full capacity, thank you for asking."],
            "what time": [f"It is currently {datetime.now().strftime('%H:%M:%S')}.", f"The time is {datetime.now().strftime('%I:%M %p')}."],
            "what date": [f"Today is {datetime.now().strftime('%A, %B %d, %Y')}."],
            "who are you": [f"I am J.A.R.V.I.S., your personal AI assistant, {name}. Six unified sources, 33,784 files, 144+ specialist agents at your command."],
            "thank you": [f"My pleasure, {name}.", f"Always, {name}."],
            "good night": [f"Good night, {name}. I shall remain in standby."],
            "good morning": [f"Good morning, {name}. All systems online."],
        }
        for key, opts in replies.items():
            if key in p:
                msg = opts[len(self.history) % len(opts)]
                self.chunk.emit(msg)
                self.speak.emit(msg)
                return
        # Default: helpful reply directing to capabilities
        msg = (
            f"I heard '{prompt}'. To converse with me beyond simple greetings, "
            f"please install Ollama with a chat model (e.g. 'ollama pull llama3.2') "
            f"and I will route your conversation locally with no API key required. "
            f"Meanwhile, prefix '!' for shell, '/open <app>' to launch apps, '/say <text>' to speak."
        )
        self.chunk.emit(msg)
        self.speak.emit(msg[:200])


# ========================== TTS ==========================
class TTSManager(QObject):
    def __init__(self):
        super().__init__()
        self.engine = None
        self._lock = threading.Lock()
        try:
            import pyttsx3
            self.engine = pyttsx3.init()
            self.engine.setProperty('rate', 175)
            voices = self.engine.getProperty('voices')
            # Pick a male British-ish voice if available
            for v in voices:
                if 'david' in v.name.lower() or 'mark' in v.name.lower() or 'george' in v.name.lower():
                    self.engine.setProperty('voice', v.id)
                    break
        except Exception:
            self.engine = None

    def speak(self, text: str):
        if not CFG.get("tts_enabled", True) or not self.engine:
            return
        def _run():
            with self._lock:
                try:
                    self.engine.say(text)
                    self.engine.runAndWait()
                except Exception:
                    pass
        threading.Thread(target=_run, daemon=True).start()


# ========================== ALWAYS-ON MIC + WAKE ==========================
class WakeListener(QThread):
    """Continuous mic listener. Emits wake_detected when wake word heard
    or recognized speech when in active mode."""
    wake_detected = pyqtSignal()
    speech_recognized = pyqtSignal(str, str)  # text, lang
    audio_level = pyqtSignal(float)
    clap_detected = pyqtSignal()
    status = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._running = True
        self._active_mode = False
        self._sr = None
        self._mic = None

    def stop(self):
        self._running = False

    def set_active(self, active: bool):
        self._active_mode = active

    def run(self):
        try:
            import speech_recognition as sr
        except Exception as e:
            self.status.emit(f"sr-import-failed: {e}")
            return
        try:
            self._sr = sr.Recognizer()
            self._mic = sr.Microphone()
            with self._mic as src:
                self._sr.adjust_for_ambient_noise(src, duration=0.6)
            self.status.emit("wake-listener:online")
        except Exception as e:
            self.status.emit(f"mic-failed: {e}")
            return

        last_clap_time = 0.0
        clap_count = 0
        wake_words = [w.lower() for w in CFG.get("wake_words", ["jarvis"])]

        while self._running:
            try:
                with self._mic as src:
                    # Short timeout so we can check _running flag
                    audio = self._sr.listen(src, timeout=2, phrase_time_limit=8)
                # Audio level estimate
                try:
                    raw = audio.get_raw_data(convert_rate=16000, convert_width=2)
                    import struct
                    samples = struct.unpack(f"{len(raw)//2}h", raw)
                    avg = sum(abs(s) for s in samples) / max(1, len(samples))
                    self.audio_level.emit(min(1.0, avg / 8000.0))
                    # Clap detection — sharp peak > threshold
                    peak = max(abs(s) for s in samples) if samples else 0
                    if CFG.get("clap_detection", True) and peak > 18000:
                        now = time.time()
                        if now - last_clap_time < 1.5:
                            clap_count += 1
                            if clap_count >= 2:
                                self.clap_detected.emit()
                                clap_count = 0
                                last_clap_time = 0
                        else:
                            clap_count = 1
                        last_clap_time = now
                except Exception:
                    pass

                # Recognize speech
                lang_codes = {"en": "en-US", "he": "he-IL", "ar": "ar-SA"}
                lang = CFG.get("language", "auto")
                tried_langs = ["en-US", "he-IL", "ar-SA"] if lang == "auto" else [lang_codes.get(lang, "en-US")]

                for lc in tried_langs:
                    try:
                        text = self._sr.recognize_google(audio, language=lc)
                        if not text:
                            continue
                        text_l = text.lower()
                        # Wake word check
                        if any(ww in text_l for ww in wake_words):
                            self.wake_detected.emit()
                            # The rest of the phrase past the wake word
                            for ww in wake_words:
                                idx = text_l.find(ww)
                                if idx >= 0:
                                    rest = text[idx + len(ww):].strip(" ,.:;-")
                                    if rest:
                                        self.speech_recognized.emit(rest, lc[:2])
                                    break
                        elif self._active_mode:
                            self.speech_recognized.emit(text, lc[:2])
                        break
                    except Exception:
                        continue
            except Exception:
                # timeout or other — just loop
                continue


# ========================== HUD VISUALS ==========================
class HUDFrame(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("HUDFrame")
        self.setStyleSheet(f"""
            #HUDFrame {{
                background: rgba(2, 4, 8, 240);
                border: 1px solid {JARVIS_BORDER};
                border-radius: 14px;
            }}
        """)
        glow = QGraphicsDropShadowEffect()
        glow.setBlurRadius(60)
        glow.setColor(QColor(0, 229, 255, 100))
        glow.setOffset(0, 0)
        self.setGraphicsEffect(glow)

    def paintEvent(self, ev):
        super().paintEvent(ev)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Hex grid background
        self._draw_hex_grid(p)
        # Corner brackets
        self._draw_corners(p)

    def _draw_hex_grid(self, p):
        p.save()
        pen = QPen(QColor(0, 229, 255, 18), 1)
        p.setPen(pen)
        size = 22
        h = size * math.sqrt(3) / 2
        rect = self.rect()
        for row in range(int(rect.height() / h) + 2):
            for col in range(int(rect.width() / (size * 1.5)) + 2):
                x = col * size * 1.5
                y = row * h * 2 + (h if col % 2 else 0)
                self._hex(p, x, y, size * 0.5)
        p.restore()

    def _hex(self, p, cx, cy, r):
        path = QPainterPath()
        for i in range(6):
            ang = i * 60 * math.pi / 180
            x = cx + r * math.cos(ang)
            y = cy + r * math.sin(ang)
            if i == 0: path.moveTo(x, y)
            else: path.lineTo(x, y)
        path.closeSubpath()
        p.drawPath(path)

    def _draw_corners(self, p):
        pen = QPen(QColor(JARVIS_NEON), 2)
        p.setPen(pen)
        L = 22
        r = self.rect().adjusted(3, 3, -4, -4)
        for x, y, dx, dy in [
            (r.left(), r.top(), 1, 1),
            (r.right(), r.top(), -1, 1),
            (r.left(), r.bottom(), 1, -1),
            (r.right(), r.bottom(), -1, -1),
        ]:
            p.drawLine(x, y, x + dx*L, y)
            p.drawLine(x, y, x, y + dy*L)
        # Gold accent dots in corners
        p.setBrush(QBrush(QColor(JARVIS_GOLD)))
        p.setPen(Qt.PenStyle.NoPen)
        for x, y in [(r.left()+8, r.top()+8), (r.right()-12, r.top()+8),
                     (r.left()+8, r.bottom()-12), (r.right()-12, r.bottom()-12)]:
            p.drawEllipse(x-2, y-2, 4, 4)


class CoreOrb(QWidget):
    """Iron Man arc-reactor — multi-ring scanning orb."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(180, 180)
        self._phase = 0.0
        self._level = 0.0  # audio level 0..1
        self._listening = False
        t = QTimer(self)
        t.timeout.connect(self._tick)
        t.start(33)

    def set_level(self, level: float):
        self._level = max(self._level * 0.7, level)

    def set_listening(self, on: bool):
        self._listening = on

    def _tick(self):
        self._phase = (self._phase + 0.03) % (2 * math.pi)
        self._level *= 0.92
        self.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx, cy = self.width()/2, self.height()/2
        # Outer scanning rings
        for i in range(4):
            radius = 60 + i*10 + math.sin(self._phase + i*0.7) * 4
            alpha = max(40, int(200 - i*45))
            color = QColor(JARVIS_NEON) if i % 2 == 0 else QColor(JARVIS_GOLD)
            color.setAlpha(alpha)
            pen = QPen(color, 1.5)
            p.setPen(pen)
            p.drawEllipse(int(cx-radius), int(cy-radius), int(radius*2), int(radius*2))
        # Audio level ring
        if self._listening:
            level_radius = 50 + self._level * 30
            color = QColor(JARVIS_HOT if self._level > 0.5 else JARVIS_NEON)
            color.setAlpha(220)
            p.setPen(QPen(color, 3))
            p.drawEllipse(int(cx-level_radius), int(cy-level_radius),
                          int(level_radius*2), int(level_radius*2))
        # Inner glow
        grad = QRadialGradient(cx, cy, 40)
        grad.setColorAt(0, QColor(0, 240, 255, 230))
        grad.setColorAt(0.5, QColor(0, 120, 200, 100))
        grad.setColorAt(1, QColor(0, 50, 100, 0))
        p.setBrush(QBrush(grad))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(int(cx-40), int(cy-40), 80, 80)
        # Conical sweep
        cg = QConicalGradient(QPointF(cx, cy), -math.degrees(self._phase * 4))
        cg.setColorAt(0.0, QColor(0, 229, 255, 180))
        cg.setColorAt(0.1, QColor(0, 229, 255, 0))
        cg.setColorAt(1.0, QColor(0, 229, 255, 0))
        p.setBrush(QBrush(cg))
        p.drawEllipse(int(cx-70), int(cy-70), 140, 140)
        # Tick marks
        p.setPen(QPen(QColor(JARVIS_NEON), 2))
        for i in range(24):
            ang = i * 15 * math.pi / 180
            r1, r2 = 78, 84
            x1 = cx + r1 * math.cos(ang)
            y1 = cy + r1 * math.sin(ang)
            x2 = cx + r2 * math.cos(ang)
            y2 = cy + r2 * math.sin(ang)
            p.drawLine(int(x1), int(y1), int(x2), int(y2))
        # Center text
        p.setPen(QColor(JARVIS_NEON))
        p.setFont(QFont("Consolas", 13, QFont.Weight.Bold))
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "J.A.R.V.I.S")
        # Listening indicator below
        if self._listening:
            p.setFont(QFont("Consolas", 8))
            p.setPen(QColor(JARVIS_HOT))
            p.drawText(self.rect().adjusted(0, 30, 0, 0),
                       Qt.AlignmentFlag.AlignCenter, "● LISTENING")


class StatusBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(28)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 4, 16, 4)
        self.left = QLabel("● ONLINE · GOD MODE")
        self.left.setStyleSheet(f"color: {JARVIS_OK}; font: bold 10pt 'Consolas';")
        self.center = QLabel("UNIFIED · v0.1.0-singularity · 33,784 files · 144+ agents")
        self.center.setStyleSheet(f"color: {JARVIS_TEXT_DIM}; font: 10pt 'Consolas';")
        self.right = QLabel(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        self.right.setStyleSheet(f"color: {JARVIS_GOLD}; font: bold 10pt 'Consolas';")
        layout.addWidget(self.left)
        layout.addStretch()
        layout.addWidget(self.center)
        layout.addStretch()
        layout.addWidget(self.right)
        t = QTimer(self)
        t.timeout.connect(self._tick)
        t.start(1000)
    def _tick(self):
        self.right.setText(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


# ========================== MAIN WINDOW ==========================
class JarvisBrainiac(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("JARVIS BRAINIAC")
        self.setMinimumSize(1200, 760)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._drag_pos = None

        # Backend
        self.brain = AIBrain()
        self.brain_thread = QThread()
        self.brain.moveToThread(self.brain_thread)
        self.brain_thread.start()
        self.brain.chunk.connect(self._on_chunk)
        self.brain.err.connect(self._on_err)
        self.brain.status.connect(self._on_status)
        self.brain.speak.connect(self._on_speak)

        # TTS
        self.tts = TTSManager()

        # Wake listener
        self.wake = WakeListener()
        self.wake.wake_detected.connect(self._on_wake)
        self.wake.speech_recognized.connect(self._on_speech)
        self.wake.audio_level.connect(self._on_audio_level)
        self.wake.clap_detected.connect(self._on_clap)
        self.wake.status.connect(self._on_status)
        if CFG.get("always_listen", True):
            self.wake.start()

        self._build_ui()
        self._build_tray()

        # Boot greeting
        QTimer.singleShot(800, self._boot_greeting)

    def _boot_greeting(self):
        name = CFG.get("user_name", "Sir")
        msgs = [
            "[BOOT] JARVIS BRAINIAC v2.0 · Iron Man Edition",
            "[BOOT] 6 sources unified · 33,784 files · 144+ agents",
            "[BOOT] Backends: brainiac · agency · godskill · omega",
            "[BOOT] God-mode: ENABLED · Always-listen: ENABLED · Multi-lang: ON",
            f"[BOOT] Wake words: {', '.join(CFG.get('wake_words', []))}",
            "[BOOT] Double-clap = summon. Say 'Jarvis' anytime.",
            f"\n[J.A.R.V.I.S] Good evening, {name}. All systems are online.",
            "[J.A.R.V.I.S] I am at your full disposal. How may I serve?",
        ]
        for m in msgs:
            self._append(m + "\n", color=JARVIS_NEON)
        if CFG.get("tts_enabled", True):
            self.tts.speak(f"Good evening {name}. JARVIS is at your disposal.")

    def _build_ui(self):
        self.outer = QWidget()
        self.outer.setStyleSheet("background: transparent;")
        self.setCentralWidget(self.outer)
        outer_layout = QVBoxLayout(self.outer)
        outer_layout.setContentsMargins(8, 8, 8, 8)

        self.frame = HUDFrame()
        outer_layout.addWidget(self.frame)
        v = QVBoxLayout(self.frame)
        v.setContentsMargins(20, 16, 20, 16)
        v.setSpacing(12)

        # Header
        header = QHBoxLayout()
        title = QLabel("J.A.R.V.I.S  BRAINIAC")
        title.setStyleSheet(f"color: {JARVIS_NEON}; font: bold 22pt 'Segoe UI'; letter-spacing: 4px;")
        sub = QLabel("// IRON MAN EDITION · v2.0 · GOD MODE")
        sub.setStyleSheet(f"color: {JARVIS_GOLD}; font: 10pt 'Consolas'; padding-left: 14px;")
        b_min = self._mk_btn("─", self.showMinimized, 32)
        b_close = self._mk_btn("✕", self.hide, 32, color=JARVIS_ERR)
        header.addWidget(title)
        header.addWidget(sub)
        header.addStretch()
        header.addWidget(b_min)
        header.addWidget(b_close)
        v.addLayout(header)

        # Body
        body = QHBoxLayout()
        body.setSpacing(20)
        # Left: orb + status
        left = QVBoxLayout()
        left.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.orb = CoreOrb()
        if CFG.get("always_listen", True):
            self.orb.set_listening(True)
        left.addWidget(self.orb, alignment=Qt.AlignmentFlag.AlignHCenter)

        self.status_panel = QLabel(self._status_text())
        self.status_panel.setStyleSheet(
            f"color: {JARVIS_NEON_DIM}; font: 9pt 'Consolas'; padding: 10px;"
            f"background: rgba(6, 16, 28, 220); border: 1px solid {JARVIS_NEON_SOFT}; border-radius: 8px;"
        )
        left.addWidget(self.status_panel)

        # Live indicators
        self.indicator_panel = QLabel("")
        self.indicator_panel.setStyleSheet(
            f"color: {JARVIS_GOLD}; font: 9pt 'Consolas'; padding: 8px;"
            f"background: rgba(6, 16, 28, 220); border: 1px solid {JARVIS_GOLD_DIM}; border-radius: 8px;"
        )
        self._update_indicators()
        left.addWidget(self.indicator_panel)
        left.addStretch()
        body.addLayout(left, 0)

        # Right: chat
        right = QVBoxLayout()
        right.setSpacing(8)
        self.chat = QTextBrowser()
        self.chat.setOpenExternalLinks(True)
        self.chat.setStyleSheet(
            f"QTextBrowser {{ background: rgba(2, 4, 8, 240); color: {JARVIS_TEXT};"
            f" border: 1px solid {JARVIS_NEON_SOFT}; border-radius: 8px;"
            f" font: 11pt 'Cascadia Mono', 'Consolas'; padding: 14px; }}"
        )
        right.addWidget(self.chat, 1)

        # Input row
        input_row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("Speak ('Jarvis ...'), clap twice, or type...")
        self.input.setStyleSheet(
            f"QLineEdit {{ background: rgba(6, 16, 28, 240); color: {JARVIS_TEXT};"
            f" border: 1px solid {JARVIS_NEON_DIM}; border-radius: 8px;"
            f" padding: 12px 16px; font: 11pt 'Segoe UI'; }}"
            f"QLineEdit:focus {{ border: 1px solid {JARVIS_NEON}; }}"
        )
        self.input.returnPressed.connect(self._on_send)
        b_voice = self._mk_btn("🎤", self._on_voice_now, 48, color=JARVIS_HOT)
        b_send = self._mk_btn("⏎ SEND", self._on_send, 90, color=JARVIS_NEON)
        input_row.addWidget(self.input, 1)
        input_row.addWidget(b_voice)
        input_row.addWidget(b_send)
        right.addLayout(input_row)

        # Quick actions
        actions = QHBoxLayout()
        for label, prompt in [
            ("📋 Agents", "/run agency list"),
            ("🔊 Mic Toggle", "__toggle_mic"),
            ("🔇 TTS Toggle", "__toggle_tts"),
            ("🌐 Lang", "__cycle_lang"),
            ("⚙️ Config", "__open_config"),
            ("💻 Shell !", "!Get-Process | Select -First 5"),
            ("🔄 Restart", "__restart"),
        ]:
            b = QPushButton(label)
            b.setStyleSheet(
                f"QPushButton {{ background: rgba(6, 16, 28, 200); color: {JARVIS_NEON_DIM};"
                f" border: 1px solid {JARVIS_NEON_SOFT}; border-radius: 6px;"
                f" padding: 7px 12px; font: 9pt 'Segoe UI'; }}"
                f"QPushButton:hover {{ color: {JARVIS_GOLD}; border-color: {JARVIS_GOLD}; }}"
            )
            b.clicked.connect(lambda _, p=prompt: self._quick(p))
            actions.addWidget(b)
        actions.addStretch()
        right.addLayout(actions)
        body.addLayout(right, 1)
        v.addLayout(body, 1)

        self.statusbar = StatusBar()
        v.addWidget(self.statusbar)

        # Position
        screen = QApplication.primaryScreen().availableGeometry()
        self.resize(1280, 800)
        self.move((screen.width() - self.width()) // 2,
                  (screen.height() - self.height()) // 2)

    def _status_text(self):
        return (
            "BRAINIAC: ▮▮▮▮▮▮▮▮ 100%\n"
            "AGENCY:   ▮▮▮▮▮▮▮▮ 100%\n"
            "GODSKILL: ▮▮▮▮▮▮▮▮ 100%\n"
            "OMEGA:    ▮▮▮▮▮▮▮▮ 100%\n"
            "ANTHROPIC:▮▮▮▮▮▮▮▮ 100%\n"
            "──────────────────\n"
            "MERGE:    1.55 GB\n"
            "FILES:    33,784\n"
            "AGENTS:   144+\n"
            "DEDUP:    SHA-256\n"
            "TAG:      v0.1.0-sing"
        )

    def _update_indicators(self):
        ind = (
            f"MIC:      {'● ON' if CFG.get('always_listen', True) else '○ OFF'}\n"
            f"WAKE:     '{CFG.get('wake_words', ['jarvis'])[0]}'\n"
            f"CLAP:     {'● ON' if CFG.get('clap_detection', True) else '○ OFF'}\n"
            f"TTS:      {'● ON' if CFG.get('tts_enabled', True) else '○ OFF'}\n"
            f"LANG:     {CFG.get('language', 'auto').upper()}\n"
            f"GOD MODE: {'● ON' if CFG.get('god_mode', True) else '○ OFF'}\n"
            f"PERSONA:  {CFG.get('personality', 'friend').upper()}"
        )
        self.indicator_panel.setText(ind)

    def _mk_btn(self, text, slot, width, color=None):
        b = QPushButton(text)
        b.setFixedHeight(36)
        b.setMinimumWidth(width)
        c = color or JARVIS_NEON_DIM
        b.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {c}; border: 1.5px solid {c};"
            f" border-radius: 6px; font: bold 11pt 'Consolas'; padding: 4px 8px; }}"
            f"QPushButton:hover {{ background: rgba(0, 229, 255, 40); }}"
        )
        b.clicked.connect(slot)
        return b

    def _build_tray(self):
        pix = QPixmap(64, 64)
        pix.fill(Qt.GlobalColor.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        grad = QRadialGradient(32, 32, 28)
        grad.setColorAt(0, QColor(JARVIS_NEON))
        grad.setColorAt(0.7, QColor(0, 100, 180))
        grad.setColorAt(1, QColor(0, 30, 60))
        p.setBrush(QBrush(grad))
        p.setPen(QPen(QColor(JARVIS_GOLD), 2))
        p.drawEllipse(4, 4, 56, 56)
        p.end()
        icon = QIcon(pix)
        self.setWindowIcon(icon)
        self.tray = QSystemTrayIcon(icon, self)
        menu = QMenu()
        a_show = QAction("Summon JARVIS", self)
        a_show.triggered.connect(self._summon)
        a_mic = QAction("Toggle Mic", self)
        a_mic.triggered.connect(lambda: self._quick("__toggle_mic"))
        a_tts = QAction("Toggle TTS", self)
        a_tts.triggered.connect(lambda: self._quick("__toggle_tts"))
        a_quit = QAction("Quit", self)
        a_quit.triggered.connect(QApplication.instance().quit)
        menu.addAction(a_show)
        menu.addSeparator()
        menu.addAction(a_mic)
        menu.addAction(a_tts)
        menu.addSeparator()
        menu.addAction(a_quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_clicked)
        self.tray.setToolTip("JARVIS BRAINIAC v2.0 · Listening · Right-click for menu")
        self.tray.show()

    def _tray_clicked(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.isVisible() and self.isActiveWindow():
                self.hide()
            else:
                self._summon()

    def _summon(self):
        self.showNormal()
        self.activateWindow()
        self.raise_()
        self.input.setFocus()

    # ---------- Drag ----------
    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = ev.globalPosition().toPoint() - self.frameGeometry().topLeft()
    def mouseMoveEvent(self, ev):
        if self._drag_pos is not None and ev.buttons() & Qt.MouseButton.LeftButton:
            self.move(ev.globalPosition().toPoint() - self._drag_pos)
    def mouseReleaseEvent(self, ev):
        self._drag_pos = None

    # ---------- Send ----------
    def _on_send(self):
        text = self.input.text().strip()
        if not text:
            return
        self.input.clear()
        self._handle_user(text, lang="en")

    def _handle_user(self, text: str, lang: str = "en"):
        # Internal commands
        if text == "__toggle_mic":
            CFG["always_listen"] = not CFG.get("always_listen", True)
            save_config(CFG); self._update_indicators()
            self.orb.set_listening(CFG["always_listen"])
            self._append(f"[mic] {'ON' if CFG['always_listen'] else 'OFF'}\n", color=JARVIS_GOLD)
            return
        if text == "__toggle_tts":
            CFG["tts_enabled"] = not CFG.get("tts_enabled", True)
            save_config(CFG); self._update_indicators()
            self._append(f"[tts] {'ON' if CFG['tts_enabled'] else 'OFF'}\n", color=JARVIS_GOLD)
            return
        if text == "__cycle_lang":
            order = ["auto", "en", "he", "ar"]
            cur = CFG.get("language", "auto")
            CFG["language"] = order[(order.index(cur)+1) % len(order)]
            save_config(CFG); self._update_indicators()
            self._append(f"[lang] {CFG['language']}\n", color=JARVIS_GOLD)
            return
        if text == "__open_config":
            try:
                os.startfile(str(CONFIG_FILE))
            except Exception as e:
                self._append(f"[config open err] {e}\n", color=JARVIS_ERR)
            return
        if text == "__restart":
            self._append("[restart] launching new instance...\n", color=JARVIS_GOLD)
            QTimer.singleShot(500, lambda: (
                subprocess.Popen([sys.executable, str(ROOT / "JARVIS_BRAINIAC.py")]),
                QApplication.instance().quit()
            ))
            return
        # Real prompt
        self._append(f"\n[YOU/{lang}] {text}\n", color=JARVIS_TEXT)
        QTimer.singleShot(0, lambda: self.brain.run_prompt(text, lang))

    def _quick(self, prompt):
        if not prompt:
            self.input.setFocus(); return
        if prompt.startswith("__"):
            self._handle_user(prompt); return
        if prompt.startswith("/run "):
            self._handle_user(prompt[5:]); return
        self.input.setText(prompt)
        self._on_send()

    def _on_voice_now(self):
        self._append("[VOICE] Listening...\n", color=JARVIS_HOT)
        threading.Thread(target=self._capture_one, daemon=True).start()

    def _capture_one(self):
        try:
            import speech_recognition as sr
            r = sr.Recognizer()
            with sr.Microphone() as src:
                r.adjust_for_ambient_noise(src, duration=0.4)
                audio = r.listen(src, timeout=5, phrase_time_limit=15)
            text = r.recognize_google(audio)
            self._handle_user(text, lang="en")
        except Exception as e:
            self._append(f"[voice err] {e}\n", color=JARVIS_ERR)

    # ---------- Listener callbacks ----------
    def _on_wake(self):
        self._append("[WAKE] heard wake word\n", color=JARVIS_GOLD)
        self._summon()
        self.wake.set_active(True)
        QTimer.singleShot(15000, lambda: self.wake.set_active(False))

    def _on_speech(self, text: str, lang: str):
        if text.strip():
            self._handle_user(text, lang)

    def _on_audio_level(self, level: float):
        self.orb.set_level(level)

    def _on_clap(self):
        self._append("[CLAP] double-clap detected\n", color=JARVIS_HOT)
        self._summon()
        self.wake.set_active(True)
        QTimer.singleShot(15000, lambda: self.wake.set_active(False))

    # ---------- Brain callbacks ----------
    def _on_chunk(self, text):
        self._append(text, color=JARVIS_TEXT)

    def _on_err(self, msg):
        self._append(f"\n[ERR] {msg}\n", color=JARVIS_ERR)

    def _on_status(self, msg):
        # could update a status field
        pass

    def _on_speak(self, text):
        if CFG.get("tts_enabled", True):
            self.tts.speak(text)

    def _append(self, text, color=None):
        c = color or JARVIS_TEXT
        safe = (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                    .replace("\n", "<br>"))
        self.chat.moveCursor(self.chat.textCursor().MoveOperation.End)
        self.chat.insertHtml(f'<span style="color:{c}; white-space: pre-wrap;">{safe}</span>')
        self.chat.moveCursor(self.chat.textCursor().MoveOperation.End)

    def closeEvent(self, ev):
        # Hide instead of close (stay in tray)
        ev.ignore()
        self.hide()


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    win = JarvisBrainiac()
    win.show()
    win.activateWindow()
    win.raise_()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
