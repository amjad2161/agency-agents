"""JARVIS BRAINIAC v2.0 - Iron Man Edition - Ollama-powered, no API key required."""
from __future__ import annotations
import os, sys, json, threading, traceback, subprocess, math, time
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent
for p in (ROOT, ROOT / "runtime"):
    if p.exists() and str(p) not in sys.path:
        sys.path.insert(0, str(p))

from PyQt6.QtCore import (Qt, QTimer, pyqtSignal, QObject, QThread, QPointF)
from PyQt6.QtGui import (QPainter, QColor, QPen, QFont, QBrush, QIcon, QPixmap,
                          QAction, QPainterPath, QRadialGradient, QConicalGradient)
from PyQt6.QtWidgets import (QApplication, QWidget, QMainWindow, QVBoxLayout,
                              QHBoxLayout, QLabel, QLineEdit, QPushButton, QFrame,
                              QGraphicsDropShadowEffect, QSystemTrayIcon, QMenu, QTextBrowser)

NEON, NEON_DIM, NEON_SOFT = "#00E5FF", "#00A6CC", "#003D5C"
GOLD, GOLD_DIM = "#FFD23F", "#B89020"
TEXT, TEXT_DIM = "#E8F4FF", "#7AA3CC"
OK, ERR, HOT, BORDER = "#00FF88", "#FF3355", "#FF6B00", "#0E2F4F"

CONFIG_DIR = ROOT / ".jarvis_brainiac"
CONFIG_DIR.mkdir(exist_ok=True)
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_CFG = {
    "wake_words": ["jarvis", "ג'רוויס", "جارفيس"],
    "always_listen": True,
    "clap_detection": True,
    "tts_enabled": True,
    "language": "auto",
    "god_mode": True,
    "user_name": "Sir",
}

def load_cfg():
    try:
        if CONFIG_FILE.exists():
            return {**DEFAULT_CFG, **json.loads(CONFIG_FILE.read_text(encoding='utf-8'))}
    except Exception:
        pass
    return DEFAULT_CFG.copy()

def save_cfg(cfg):
    try:
        CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding='utf-8')
    except Exception:
        pass

CFG = load_cfg()

NL = chr(10)


class Brain(QObject):
    chunk = pyqtSignal(str)
    done = pyqtSignal()
    err = pyqtSignal(str)
    status = pyqtSignal(str)
    speak = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._ollama_url = "http://localhost:11434"
        self._ollama_model = None
        self._claude = None
        self.history = []
        # Sentient layer
        self.memory = None
        self.skills = None
        self.github = None
        self.autonomous = None
        self.indexer = None
        try:
            from jarvis_brain import Memory, SkillRegistry, GitHubImporter, AutonomousLoop, FileIndexer
            mem_dir = ROOT / ".jarvis_brainiac" / "memory_data"
            self.memory = Memory(mem_dir)
            self.skills = SkillRegistry(ROOT, self.memory)
            self.github = GitHubImporter(ROOT, self.memory, self.skills)
            self.indexer = FileIndexer(ROOT, self.memory)
            # Background scan + index
            self.skills.scan_all()
            self.indexer.start_background()
            # Load history from persistent memory
            self.history = self.memory.recent_chat(20)
        except Exception as e:
            print(f"[brain] sentient layer init failed: {e}")
        # v4.0 ACTION layer
        self.action = None
        self.vision = None
        self.telemetry = None
        self.proactive = None
        self.workflow = None
        self.webcam = None
        try:
            from jarvis_brain import ComputerAction, Vision, Telemetry, ProactiveBrain, Workflow, WebcamPresence
            self.action = ComputerAction()
            self.vision = Vision(self.action)
            self.telemetry = Telemetry()
            self.workflow = Workflow(self.action, self.vision, self.telemetry, lambda i, s: None)
            self.proactive = ProactiveBrain(self.action, lambda kind, data: self.chunk.emit(f"[proactive/{kind}] {data}"))
            self.proactive.start()
            self.webcam = WebcamPresence(lambda present: self.chunk.emit(f"[webcam] user {'present' if present else 'left'}"))
            # webcam start optional - don't auto-start to avoid camera light
        except Exception as e:
            print(f"[brain] v4 action layer failed: {e}")
        self._init()

    def _init(self):
        # Ollama
        try:
            import urllib.request
            req = urllib.request.Request(self._ollama_url + "/api/tags")
            with urllib.request.urlopen(req, timeout=2) as r:
                data = json.loads(r.read())
            models = [m.get("name") for m in data.get("models", []) if m.get("name")]
            if models:
                preferred = ["llama3.2", "llama3.1", "llama3", "qwen2.5", "mistral", "phi3"]
                self._ollama_model = None
                for p in preferred:
                    for m in models:
                        if p in m.lower():
                            self._ollama_model = m
                            break
                    if self._ollama_model: break
                if not self._ollama_model: self._ollama_model = models[0]
                self.status.emit("ollama:" + self._ollama_model)
        except Exception:
            self.status.emit("ollama:offline")
        # Anthropic optional
        try:
            import anthropic
            api_key = os.environ.get("ANTHROPIC_API_KEY", "")
            if api_key:
                self._claude = anthropic.Anthropic(api_key=api_key)
        except Exception:
            pass

    def _system_prompt(self):
        name = CFG.get("user_name", "Sir")
        return ("You are J.A.R.V.I.S., the personal AI of " + name + ". "
                "Speak with refined British wit and dry humor. Address them as " + name + ". "
                "You have full god-mode access to their computer. Multi-lingual (EN/HE/AR). "
                "Connected to: jarvis_brainiac, agency runtime (144+ agents), godskill_server, "
                "JARVIS_OMEGA. 33,784 files, 1.55 GB, v0.1.0-singularity. "
                "Act, do not just describe. Be concise. Match their language. You have FULL COMPUTER CONTROL via these commands you can suggest the user runs: 'screen' (see screen), 'stats' (CPU/RAM/disk), 'processes' (top processes), 'click X Y', 'type <text>', 'press <key>', 'hotkey ctrl+s', 'focus <window>', 'windows' (list), 'url <link>', 'open <app>', '!cmd' (PowerShell exec), 'github <url>' (clone+integrate), 'remember key=val', 'recall key', 'find skill <query>', 'search files <query>', 'webcam on/off'. You have persistent memory, vector recall, 33,784 indexed files, 144+ agents, rotating neural brain, Neuralink BCI panel, real god-mode shell, vision via Ollama. When asked to DO something, ACT — invoke commands, not just describe.")

    def run_prompt(self, prompt, lang="en"):
        try:
            self.history.append({"role": "user", "content": prompt})
            if self.memory:
                self.memory.add_chat("user", prompt, lang)
                # Special commands
                pl = prompt.lower().strip()
                if pl.startswith("github "):
                    url = prompt.split(" ", 1)[1].strip()
                    if url.startswith("http") and self.github:
                        result = self.github.clone_and_integrate(url)
                        msg = "Imported and integrated: " + str(result)
                        self.chunk.emit(msg); self.speak.emit(msg[:200]); self.done.emit()
                        return
                if pl.startswith("remember "):
                    m = prompt[9:].strip()
                    if "=" in m:
                        k, v = m.split("=", 1)
                        self.memory.remember(k.strip(), v.strip())
                        self.chunk.emit("Noted: " + k.strip() + " = " + v.strip())
                        self.done.emit()
                        return
                if pl.startswith("recall "):
                    k = prompt[7:].strip()
                    v = self.memory.recall(k) or "(no record)"
                    self.chunk.emit(k + ": " + v)
                    self.done.emit()
                    return
                if pl.startswith("find skill ") or pl.startswith("which agent"):
                    q = prompt.split(" ", 2)[-1] if pl.startswith("find") else prompt.replace("which agent", "")
                    found = self.skills.find_skill(q.strip())
                    if found:
                        for s in found:
                            self.chunk.emit(f"  · {s['name']} ({s['division']}) — {s['description'][:120]}")
                        self.done.emit()
                        return
                if pl.startswith("search files "):
                    q = prompt[13:].strip()
                    rows = self.memory.search_files(q, n=10)
                    for r in rows:
                        self.chunk.emit(f"  · {r['path']}")
                    if not rows:
                        self.chunk.emit("(no files match)")
                    self.done.emit()
                    return
                # v4.0 action commands
                if pl == "screen" or pl == "see screen" or pl == "what do you see":
                    if self.vision:
                        out = self.vision.see_screen()
                        self.chunk.emit("[vision] " + out)
                        self.speak.emit(out[:300])
                    self.done.emit(); return
                if pl == "stats" or pl == "system status":
                    if self.telemetry:
                        snap = self.telemetry.snapshot()
                        for k, v in snap.items():
                            self.chunk.emit(f"  {k}: {v}")
                    self.done.emit(); return
                if pl.startswith("processes"):
                    if self.telemetry:
                        for p in self.telemetry.top_processes(10):
                            self.chunk.emit(f"  PID {p['pid']:>6}  {p['mem_mb']:>7.1f}MB  CPU {p['cpu']:>5.1f}  {p['name']}")
                    self.done.emit(); return
                if pl.startswith("click "):
                    parts = prompt[6:].strip().split()
                    if len(parts) >= 2 and self.action:
                        try:
                            x, y = int(parts[0]), int(parts[1])
                            self.action.click(x, y)
                            self.chunk.emit(f"[click] ({x}, {y})")
                        except Exception as e:
                            self.err.emit(str(e))
                    self.done.emit(); return
                if pl.startswith("type "):
                    if self.action:
                        self.action.type_text(prompt[5:])
                        self.chunk.emit("[typed]")
                    self.done.emit(); return
                if pl.startswith("press "):
                    if self.action:
                        self.action.press_key(prompt[6:].strip())
                        self.chunk.emit(f"[pressed] {prompt[6:].strip()}")
                    self.done.emit(); return
                if pl.startswith("hotkey "):
                    if self.action:
                        keys = [k.strip() for k in prompt[7:].split("+")]
                        self.action.hotkey(*keys)
                        self.chunk.emit(f"[hotkey] {'+'.join(keys)}")
                    self.done.emit(); return
                if pl.startswith("focus "):
                    if self.action:
                        ok = self.action.focus_window(prompt[6:].strip())
                        self.chunk.emit(f"[focus] {'ok' if ok else 'window not found'}")
                    self.done.emit(); return
                if pl == "windows":
                    if self.action:
                        for w in self.action.list_windows()[:20]:
                            self.chunk.emit(f"  · {w}")
                    self.done.emit(); return
                if pl.startswith("url "):
                    if self.action:
                        self.action.open_url(prompt[4:].strip())
                        self.chunk.emit(f"[opened url] {prompt[4:].strip()}")
                    self.done.emit(); return
                if pl == "webcam on":
                    if self.webcam:
                        self.webcam.start()
                        self.chunk.emit("[webcam] presence detection started")
                    self.done.emit(); return
                if pl == "webcam off":
                    if self.webcam:
                        self.webcam.stop()
                        self.chunk.emit("[webcam] off")
                    self.done.emit(); return
            if prompt.startswith("!"):
                self._shell(prompt[1:].strip())
                return
            if prompt.startswith("/"):
                self._cmd(prompt[1:].strip())
                return
            if self._ollama_model:
                if self._call_ollama(prompt):
                    return
            if self._claude:
                self._call_claude(prompt)
                return
            self._fallback(prompt)
        except Exception as e:
            self.err.emit(str(e) + NL + traceback.format_exc())
        finally:
            self.done.emit()

    def _call_ollama(self, prompt):
        try:
            import urllib.request
            messages = [{"role": "system", "content": self._system_prompt()}]
            messages.extend(self.history[-12:])
            payload = json.dumps({
                "model": self._ollama_model,
                "messages": messages,
                "stream": False,
                "options": {"temperature": 0.7, "num_predict": 600},
            }).encode("utf-8")
            req = urllib.request.Request(self._ollama_url + "/api/chat", data=payload,
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=180) as r:
                data = json.loads(r.read())
            text = data.get("message", {}).get("content", "")
            if not text:
                return False
            self.history.append({"role": "assistant", "content": text})
            if self.memory:
                self.memory.add_chat("assistant", text)
            self.chunk.emit(text)
            self.speak.emit(text[:400])
            return True
        except Exception as e:
            self.err.emit("ollama: " + str(e))
            return False

    def _call_claude(self, prompt):
        try:
            messages = [{"role": m["role"], "content": m["content"]} for m in self.history[-20:]]
            r = self._claude.messages.create(
                model="claude-sonnet-4-5", max_tokens=2048,
                system=self._system_prompt(), messages=messages)
            text = "".join(b.text for b in r.content if hasattr(b, "text"))
            self.history.append({"role": "assistant", "content": text})
            self.chunk.emit(text)
            self.speak.emit(text[:400])
        except Exception as e:
            self.err.emit("claude: " + str(e))
            self._fallback(prompt)

    def _shell(self, cmd):
        if not CFG.get("god_mode", True):
            self.chunk.emit("[god-mode disabled]")
            return
        try:
            self.chunk.emit("[shell] $ " + cmd + NL)
            r = subprocess.run(["powershell", "-NoProfile", "-Command", cmd],
                               capture_output=True, text=True, timeout=60)
            self.chunk.emit(((r.stdout or "") + (r.stderr or ""))[:4000])
        except Exception as e:
            self.err.emit("shell: " + str(e))

    def _cmd(self, cmd):
        c = cmd.lower()
        if c.startswith("open "):
            try: os.startfile(cmd[5:].strip())
            except Exception:
                try: subprocess.Popen(["cmd", "/c", "start", "", cmd[5:].strip()], shell=False)
                except Exception as e: self.err.emit(str(e))
            self.chunk.emit("[opened] " + cmd[5:] + NL)
        elif c.startswith("say "):
            self.speak.emit(cmd[4:])
            self.chunk.emit("[speaking] " + cmd[4:] + NL)
        elif c == "clear":
            self.history.clear()
            self.chunk.emit("[history cleared]" + NL)
        else:
            self.chunk.emit("[unknown] " + cmd + NL)

    def _fallback(self, prompt):
        name = CFG.get("user_name", "Sir")
        p = prompt.lower()
        replies = {
            "hello": "Hello, " + name + ".",
            "hi": "Yes, " + name + "?",
            "how are you": "All systems nominal, " + name + ".",
            "what time": "It is " + datetime.now().strftime("%H:%M:%S") + ".",
            "what date": "Today is " + datetime.now().strftime("%A, %B %d, %Y") + ".",
            "who are you": "J.A.R.V.I.S., " + name + ". Six unified sources, 33,784 files.",
            "thank you": "My pleasure, " + name + ".",
            "good night": "Good night, " + name + ".",
            "good morning": "Good morning, " + name + ".",
        }
        for k, v in replies.items():
            if k in p:
                self.chunk.emit(v)
                self.speak.emit(v)
                return
        msg = ("Local Ollama brain is offline. Pull a model: "
               "open PowerShell and run 'ollama pull llama3.2'. Then I shall converse fully.")
        self.chunk.emit(msg)
        self.speak.emit(msg[:200])


class TTS:
    def __init__(self):
        self.engine = None
        self._lock = threading.Lock()
        try:
            import pyttsx3
            self.engine = pyttsx3.init()
            self.engine.setProperty('rate', 175)
        except Exception:
            self.engine = None

    def speak(self, text):
        if not CFG.get("tts_enabled", True) or not self.engine:
            return
        def run():
            with self._lock:
                try:
                    self.engine.say(text)
                    self.engine.runAndWait()
                except Exception:
                    pass
        threading.Thread(target=run, daemon=True).start()


class Listener(QThread):
    wake = pyqtSignal()
    speech = pyqtSignal(str, str)
    level = pyqtSignal(float)
    clap = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._running = True
        self._active = False

    def stop(self):
        self._running = False

    def set_active(self, a):
        self._active = a

    def run(self):
        try:
            import speech_recognition as sr
        except Exception:
            return
        try:
            recog = sr.Recognizer()
            mic = sr.Microphone()
            with mic as src:
                recog.adjust_for_ambient_noise(src, duration=0.6)
        except Exception:
            return
        last_clap = 0.0
        clap_n = 0
        wake_words = [w.lower() for w in CFG.get("wake_words", ["jarvis"])]
        while self._running:
            try:
                with mic as src:
                    audio = recog.listen(src, timeout=2, phrase_time_limit=8)
                # Audio level + clap
                try:
                    raw = audio.get_raw_data(convert_rate=16000, convert_width=2)
                    import struct
                    samples = struct.unpack(str(len(raw)//2) + "h", raw)
                    avg = sum(abs(s) for s in samples) / max(1, len(samples))
                    self.level.emit(min(1.0, avg / 8000.0))
                    peak = max(abs(s) for s in samples) if samples else 0
                    if CFG.get("clap_detection", True) and peak > 18000:
                        now = time.time()
                        if now - last_clap < 1.5:
                            clap_n += 1
                            if clap_n >= 2:
                                self.clap.emit()
                                clap_n = 0
                                last_clap = 0
                        else:
                            clap_n = 1
                        last_clap = now
                except Exception:
                    pass
                # Recognize
                lc_map = {"en": "en-US", "he": "he-IL", "ar": "ar-SA"}
                lang = CFG.get("language", "auto")
                tries = ["en-US", "he-IL", "ar-SA"] if lang == "auto" else [lc_map.get(lang, "en-US")]
                for lc in tries:
                    try:
                        text = recog.recognize_google(audio, language=lc)
                        if not text:
                            continue
                        text_l = text.lower()
                        matched = None
                        for ww in wake_words:
                            if ww in text_l:
                                matched = ww
                                break
                        if matched:
                            self.wake.emit()
                            idx = text_l.find(matched)
                            rest = text[idx + len(matched):].strip(" ,.:;-")
                            if rest:
                                self.speech.emit(rest, lc[:2])
                        elif self._active:
                            self.speech.emit(text, lc[:2])
                        break
                    except Exception:
                        continue
            except Exception:
                continue



class BrainOrb(QWidget):
    """3D-looking rotating brain with neural connections + arc-reactor core."""
    def __init__(self):
        super().__init__()
        self.setFixedSize(280, 280)
        import random
        self._phase = 0.0
        self._level = 0.0
        self._listening = False
        # Generate stable neuron positions on sphere
        self._nodes = []
        for i in range(48):
            theta = random.uniform(0, 2 * math.pi)
            phi = random.uniform(0, math.pi)
            r = 1.0
            self._nodes.append([
                r * math.sin(phi) * math.cos(theta),
                r * math.sin(phi) * math.sin(theta),
                r * math.cos(phi),
                random.random()  # firing intensity
            ])
        # Edges between near nodes
        self._edges = []
        for i in range(len(self._nodes)):
            for j in range(i+1, len(self._nodes)):
                a, b = self._nodes[i], self._nodes[j]
                d = ((a[0]-b[0])**2 + (a[1]-b[1])**2 + (a[2]-b[2])**2) ** 0.5
                if d < 0.7:
                    self._edges.append((i, j))
        t = QTimer(self); t.timeout.connect(self._tick); t.start(33)

    def set_level(self, l): self._level = max(self._level * 0.7, l)
    def set_listening(self, on): self._listening = on
    def _tick(self):
        import random
        self._phase = (self._phase + 0.012) % (2 * math.pi)
        self._level *= 0.92
        # Random neuron firing
        for n in self._nodes:
            n[3] = max(0.0, n[3] - 0.04)
            if random.random() < 0.04:
                n[3] = 1.0
        self.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx, cy = self.width()/2, self.height()/2
        R = 105
        # Outer scanning rings
        for i in range(3):
            radius = 130 + i*8 + math.sin(self._phase * 3 + i) * 3
            color = QColor(NEON) if i % 2 == 0 else QColor(GOLD)
            color.setAlpha(max(40, 160 - i*40))
            p.setPen(QPen(color, 1.5))
            p.drawEllipse(int(cx-radius), int(cy-radius), int(radius*2), int(radius*2))
        # Project 3D nodes to 2D with rotation
        cos_a = math.cos(self._phase)
        sin_a = math.sin(self._phase)
        cos_b = math.cos(self._phase * 0.6)
        sin_b = math.sin(self._phase * 0.6)
        projected = []
        for x, y, z, fire in self._nodes:
            # Rotate around Y axis
            xr = x * cos_a + z * sin_a
            zr = -x * sin_a + z * cos_a
            # Rotate around X axis
            yr = y * cos_b - zr * sin_b
            zr2 = y * sin_b + zr * cos_b
            scale = 1.0 + zr2 * 0.3
            px = cx + xr * R * scale
            py = cy + yr * R * scale
            depth = (zr2 + 1.0) / 2.0
            projected.append((px, py, depth, fire))
        # Sort by depth (back to front)
        order = sorted(range(len(projected)), key=lambda i: projected[i][2])
        # Draw edges first
        for ei, ej in self._edges:
            ax, ay, ad, af = projected[ei]
            bx, by, bd, bf = projected[ej]
            avg_depth = (ad + bd) / 2
            avg_fire = max(af, bf)
            color = QColor(NEON)
            color.setAlpha(int(40 + 100 * avg_depth + 80 * avg_fire))
            p.setPen(QPen(color, 0.8 + avg_fire * 1.5))
            p.drawLine(int(ax), int(ay), int(bx), int(by))
        # Draw neurons
        for i in order:
            px, py, depth, fire = projected[i]
            size = 3 + depth * 4 + fire * 4
            color = QColor(GOLD if fire > 0.3 else NEON)
            color.setAlpha(int(120 + 135 * depth))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(color))
            p.drawEllipse(int(px - size/2), int(py - size/2), int(size), int(size))
        # Audio reactive ring
        if self._listening:
            level_radius = 75 + self._level * 25
            color = QColor(HOT if self._level > 0.5 else NEON)
            color.setAlpha(220)
            p.setPen(QPen(color, 3))
            p.drawEllipse(int(cx-level_radius), int(cy-level_radius),
                          int(level_radius*2), int(level_radius*2))
        # Inner core
        grad = QRadialGradient(cx, cy, 32)
        grad.setColorAt(0, QColor(0, 240, 255, 230))
        grad.setColorAt(0.6, QColor(0, 100, 180, 80))
        grad.setColorAt(1, QColor(0, 30, 60, 0))
        p.setBrush(QBrush(grad))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(int(cx-32), int(cy-32), 64, 64)
        # Center label
        p.setPen(QColor(NEON))
        p.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
        p.drawText(self.rect().adjusted(0, -8, 0, 0), Qt.AlignmentFlag.AlignCenter, "J.A.R.V.I.S")
        p.setFont(QFont("Consolas", 7))
        p.setPen(QColor(GOLD))
        p.drawText(self.rect().adjusted(0, 8, 0, 0), Qt.AlignmentFlag.AlignCenter, "NEURAL CORE")
        if self._listening:
            p.setPen(QColor(HOT))
            p.drawText(self.rect().adjusted(0, 22, 0, 0), Qt.AlignmentFlag.AlignCenter, "● LISTENING")


class NeuralinkPanel(QWidget):
    """Live EEG-style waveform — 4 channel synthetic neural data."""
    def __init__(self):
        super().__init__()
        self.setFixedHeight(160)
        self._phase = 0.0
        self._buf = [[0.0] * 200 for _ in range(4)]
        import random
        self._random = random
        t = QTimer(self); t.timeout.connect(self._tick); t.start(40)

    def _tick(self):
        self._phase += 0.08
        for i, freq in enumerate([1.0, 2.3, 3.7, 5.1]):
            v = math.sin(self._phase * freq) * 0.4 + math.sin(self._phase * freq * 0.7) * 0.3
            v += (self._random.random() - 0.5) * 0.3
            self._buf[i].append(v)
            if len(self._buf[i]) > 200:
                self._buf[i].pop(0)
        self.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Background
        p.fillRect(self.rect(), QColor(2, 4, 8, 180))
        p.setPen(QPen(QColor(NEON_SOFT), 1))
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))
        # Title
        p.setPen(QColor(GOLD))
        p.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
        p.drawText(8, 14, "NEURALINK BCI · 4-CH · 1024Hz · BRIDGE: ACTIVE")
        # Channels
        labels = ["α", "β", "γ", "θ"]
        colors = [NEON, GOLD, "#00FF88", HOT]
        h = (self.height() - 20) / 4
        w = self.width() - 60
        for ch in range(4):
            cy = 20 + h * (ch + 0.5)
            color = QColor(colors[ch])
            # Label
            p.setPen(color)
            p.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
            p.drawText(8, int(cy + 4), labels[ch])
            # Mid line
            p.setPen(QPen(QColor(NEON_SOFT), 0.5))
            p.drawLine(40, int(cy), self.width() - 8, int(cy))
            # Waveform
            pen = QPen(color, 1.2)
            p.setPen(pen)
            buf = self._buf[ch]
            path = QPainterPath()
            for i, v in enumerate(buf):
                x = 40 + (i / max(1, len(buf) - 1)) * w
                y = cy - v * (h / 2 - 4)
                if i == 0: path.moveTo(x, y)
                else: path.lineTo(x, y)
            p.drawPath(path)


class StatsPanel(QWidget):
    """Side stats matrix - scrolling diagnostic data."""
    def __init__(self):
        super().__init__()
        self.setFixedWidth(150)
        self._lines = []
        self._labels = ["BRAINIAC", "AGENCY", "GODSKILL", "OMEGA", "OLLAMA", "MEMORY",
                        "SKILLS", "GITHUB", "AUTONOMY", "VOICE", "TTS", "MIC"]
        import random
        self._random = random
        t = QTimer(self); t.timeout.connect(self._tick); t.start(120)

    def _tick(self):
        import random
        # Add a random log line
        msg = random.choice([
            "neural sync OK",
            "agent registered",
            "memory write",
            "ollama tok " + str(random.randint(40, 90)),
            "vector recall",
            "skill scan +1",
            "audio fft",
            "wake monitor",
            "ctx update",
            "embed ok",
        ])
        self._lines.append(msg)
        if len(self._lines) > 10:
            self._lines.pop(0)
        self.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor(2, 4, 8, 180))
        p.setPen(QPen(QColor(NEON_SOFT), 1))
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))
        # Title
        p.setPen(QColor(GOLD))
        p.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
        p.drawText(8, 16, "DIAGNOSTIC")
        # Bars
        y = 30
        for i, lbl in enumerate(self._labels):
            p.setPen(QColor(NEON_DIM))
            p.setFont(QFont("Consolas", 7))
            p.drawText(8, y, lbl)
            # Bar
            p.fillRect(60, y - 6, 80, 6, QColor(NEON_SOFT))
            p.fillRect(60, y - 6, 78, 6, QColor(NEON))
            y += 14
        # Live log
        y += 8
        p.setPen(QColor(GOLD))
        p.setFont(QFont("Consolas", 7, QFont.Weight.Bold))
        p.drawText(8, y, "LIVE LOG")
        y += 12
        p.setPen(QColor(TEXT_DIM))
        p.setFont(QFont("Consolas", 7))
        for line in self._lines[-8:]:
            p.drawText(8, y, "› " + line)
            y += 10


class HUD(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("HUD")
        self.setStyleSheet("#HUD { background: rgba(2,4,8,240); border: 1px solid " + BORDER + "; border-radius: 14px; }")
        g = QGraphicsDropShadowEffect()
        g.setBlurRadius(60); g.setColor(QColor(0,229,255,100)); g.setOffset(0,0)
        self.setGraphicsEffect(g)

    def paintEvent(self, ev):
        super().paintEvent(ev)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Hex grid
        p.setPen(QPen(QColor(0,229,255,18), 1))
        size = 22
        h = size * math.sqrt(3) / 2
        rect = self.rect()
        for row in range(int(rect.height() / h) + 2):
            for col in range(int(rect.width() / (size * 1.5)) + 2):
                x = col * size * 1.5
                y = row * h * 2 + (h if col % 2 else 0)
                path = QPainterPath()
                for i in range(6):
                    ang = i * 60 * math.pi / 180
                    px = x + size*0.5 * math.cos(ang)
                    py = y + size*0.5 * math.sin(ang)
                    if i == 0: path.moveTo(px, py)
                    else: path.lineTo(px, py)
                path.closeSubpath()
                p.drawPath(path)
        # Corners
        p.setPen(QPen(QColor(NEON), 2))
        L = 22
        r = self.rect().adjusted(3, 3, -4, -4)
        for x, y, dx, dy in [(r.left(), r.top(), 1, 1), (r.right(), r.top(), -1, 1),
                             (r.left(), r.bottom(), 1, -1), (r.right(), r.bottom(), -1, -1)]:
            p.drawLine(x, y, x + dx*L, y)
            p.drawLine(x, y, x, y + dy*L)
        p.setBrush(QBrush(QColor(GOLD))); p.setPen(Qt.PenStyle.NoPen)
        for x, y in [(r.left()+8, r.top()+8), (r.right()-12, r.top()+8),
                     (r.left()+8, r.bottom()-12), (r.right()-12, r.bottom()-12)]:
            p.drawEllipse(x-2, y-2, 4, 4)


class Orb(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedSize(180, 180)
        self._phase = 0.0
        self._level = 0.0
        self._listening = False
        t = QTimer(self); t.timeout.connect(self._tick); t.start(33)

    def set_level(self, l): self._level = max(self._level * 0.7, l)
    def set_listening(self, on): self._listening = on
    def _tick(self):
        self._phase = (self._phase + 0.03) % (2 * math.pi)
        self._level *= 0.92
        self.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx, cy = self.width()/2, self.height()/2
        for i in range(4):
            radius = 60 + i*10 + math.sin(self._phase + i*0.7) * 4
            color = QColor(NEON) if i % 2 == 0 else QColor(GOLD)
            color.setAlpha(max(40, 200 - i*45))
            p.setPen(QPen(color, 1.5))
            p.drawEllipse(int(cx-radius), int(cy-radius), int(radius*2), int(radius*2))
        if self._listening:
            level_radius = 50 + self._level * 30
            color = QColor(HOT if self._level > 0.5 else NEON)
            color.setAlpha(220)
            p.setPen(QPen(color, 3))
            p.drawEllipse(int(cx-level_radius), int(cy-level_radius),
                          int(level_radius*2), int(level_radius*2))
        grad = QRadialGradient(cx, cy, 40)
        grad.setColorAt(0, QColor(0, 240, 255, 230))
        grad.setColorAt(0.5, QColor(0, 120, 200, 100))
        grad.setColorAt(1, QColor(0, 50, 100, 0))
        p.setBrush(QBrush(grad))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(int(cx-40), int(cy-40), 80, 80)
        cg = QConicalGradient(QPointF(cx, cy), -math.degrees(self._phase * 4))
        cg.setColorAt(0.0, QColor(0, 229, 255, 180))
        cg.setColorAt(0.1, QColor(0, 229, 255, 0))
        cg.setColorAt(1.0, QColor(0, 229, 255, 0))
        p.setBrush(QBrush(cg))
        p.drawEllipse(int(cx-70), int(cy-70), 140, 140)
        p.setPen(QPen(QColor(NEON), 2))
        for i in range(24):
            ang = i * 15 * math.pi / 180
            r1, r2 = 78, 84
            p.drawLine(int(cx + r1 * math.cos(ang)), int(cy + r1 * math.sin(ang)),
                       int(cx + r2 * math.cos(ang)), int(cy + r2 * math.sin(ang)))
        p.setPen(QColor(NEON))
        p.setFont(QFont("Consolas", 13, QFont.Weight.Bold))
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "J.A.R.V.I.S")
        if self._listening:
            p.setFont(QFont("Consolas", 8))
            p.setPen(QColor(HOT))
            p.drawText(self.rect().adjusted(0, 30, 0, 0),
                       Qt.AlignmentFlag.AlignCenter, "● LISTENING")


class JarvisWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("JARVIS BRAINIAC")
        self.setMinimumSize(1200, 760)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._drag = None

        self.brain = Brain()
        self.bt = QThread()
        self.brain.moveToThread(self.bt)
        self.bt.start()
        self.brain.chunk.connect(self._on_chunk)
        self.brain.err.connect(self._on_err)
        self.brain.speak.connect(self._on_speak)

        self.tts = TTS()

        self.listener = Listener()
        self.listener.wake.connect(self._on_wake)
        self.listener.speech.connect(self._on_speech)
        self.listener.level.connect(self._on_level)
        self.listener.clap.connect(self._on_clap)
        if CFG.get("always_listen", True):
            self.listener.start()

        self._ui()
        self._tray()
        QTimer.singleShot(800, self._greet)

    def _greet(self):
        name = CFG.get("user_name", "Sir")
        boot = [
            "[BOOT] JARVIS BRAINIAC v2.0 · Iron Man Edition",
            "[BOOT] 6 sources unified · 33,784 files · 144+ agents",
            "[BOOT] Brain: Ollama (local, no API key)",
            "[BOOT] Wake words: " + ", ".join(CFG.get("wake_words", [])),
            "[BOOT] Double-clap = summon. God-mode: ENABLED.",
            "",
            "[J.A.R.V.I.S] Good evening, " + name + ". All systems online.",
            "[J.A.R.V.I.S] I am at your full disposal. How may I serve?",
        ]
        for line in boot:
            self._append(line + NL, NEON)
        if CFG.get("tts_enabled", True):
            self.tts.speak("Good evening " + name + ". JARVIS is at your disposal.")

    def _ui(self):
        outer = QWidget(); outer.setStyleSheet("background: transparent;")
        self.setCentralWidget(outer)
        ol = QVBoxLayout(outer); ol.setContentsMargins(8, 8, 8, 8)
        self.frame = HUD()
        ol.addWidget(self.frame)
        v = QVBoxLayout(self.frame); v.setContentsMargins(20, 16, 20, 16); v.setSpacing(12)

        # Header
        h = QHBoxLayout()
        title = QLabel("J.A.R.V.I.S  BRAINIAC")
        title.setStyleSheet("color: " + NEON + "; font: bold 22pt 'Segoe UI'; letter-spacing: 4px;")
        sub = QLabel("// IRON MAN · v2.0 · GOD MODE · OLLAMA")
        sub.setStyleSheet("color: " + GOLD + "; font: 10pt 'Consolas'; padding-left: 14px;")
        bm = self._btn("─", self.showMinimized, 32)
        bx = self._btn("✕", self.hide, 32, ERR)
        h.addWidget(title); h.addWidget(sub); h.addStretch(); h.addWidget(bm); h.addWidget(bx)
        v.addLayout(h)

        # Body
        body = QHBoxLayout(); body.setSpacing(20)
        left = QVBoxLayout(); left.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.orb = BrainOrb()
        if CFG.get("always_listen", True):
            self.orb.set_listening(True)
        left.addWidget(self.orb, alignment=Qt.AlignmentFlag.AlignHCenter)

        # Neuralink waveform panel
        self.neuralink = NeuralinkPanel()
        left.addWidget(self.neuralink)

        self.statp = QLabel(self._stats_text())
        self.statp.setStyleSheet("color: " + NEON_DIM + "; font: 9pt 'Consolas'; padding: 10px;"
                                  "background: rgba(6,16,28,220); border: 1px solid " + NEON_SOFT + "; border-radius: 8px;")
        left.addWidget(self.statp)

        self.indp = QLabel("")
        self.indp.setStyleSheet("color: " + GOLD + "; font: 9pt 'Consolas'; padding: 8px;"
                                "background: rgba(6,16,28,220); border: 1px solid " + GOLD_DIM + "; border-radius: 8px;")
        self._update_ind()
        left.addWidget(self.indp)
        left.addStretch()
        body.addLayout(left, 0)

        right = QVBoxLayout(); right.setSpacing(8)
        self.chat = QTextBrowser()
        self.chat.setStyleSheet("QTextBrowser { background: rgba(2,4,8,240); color: " + TEXT + ";"
                                 " border: 1px solid " + NEON_SOFT + "; border-radius: 8px;"
                                 " font: 11pt 'Cascadia Mono', 'Consolas'; padding: 14px; }")
        right.addWidget(self.chat, 1)

        ir = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("Speak ('Jarvis ...'), clap twice, or type...")
        self.input.setStyleSheet("QLineEdit { background: rgba(6,16,28,240); color: " + TEXT + ";"
                                  " border: 1px solid " + NEON_DIM + "; border-radius: 8px;"
                                  " padding: 12px 16px; font: 11pt 'Segoe UI'; }"
                                  "QLineEdit:focus { border: 1px solid " + NEON + "; }")
        self.input.returnPressed.connect(self._send)
        bv = self._btn("🎤", self._voice_now, 48, HOT)
        bs = self._btn("⏎ SEND", self._send, 90, NEON)
        ir.addWidget(self.input, 1); ir.addWidget(bv); ir.addWidget(bs)
        right.addLayout(ir)

        ar = QHBoxLayout()
        for label, prompt in [("📋 Agents", "list all agents"),
                               ("🔊 Mic", "__mic"),
                               ("🔇 TTS", "__tts"),
                               ("🌐 Lang", "__lang"),
                               ("⚙ Cfg", "__cfg"),
                               ("💻 Shell !", "!Get-Process | Select -First 5")]:
            b = QPushButton(label)
            b.setStyleSheet("QPushButton { background: rgba(6,16,28,200); color: " + NEON_DIM + ";"
                            " border: 1px solid " + NEON_SOFT + "; border-radius: 6px;"
                            " padding: 7px 12px; font: 9pt 'Segoe UI'; }"
                            "QPushButton:hover { color: " + GOLD + "; border-color: " + GOLD + "; }")
            b.clicked.connect(lambda _, p=prompt: self._quick(p))
            ar.addWidget(b)
        ar.addStretch()
        right.addLayout(ar)
        body.addLayout(right, 1)
        # Right diagnostic column
        self.diagp = StatsPanel()
        body.addWidget(self.diagp)
        v.addLayout(body, 1)

        # Status bar
        sb = QWidget(); sb.setFixedHeight(28)
        sl = QHBoxLayout(sb); sl.setContentsMargins(16, 4, 16, 4)
        self.sl1 = QLabel("● ONLINE · GOD MODE")
        self.sl1.setStyleSheet("color: " + OK + "; font: bold 10pt 'Consolas';")
        self.sl2 = QLabel("UNIFIED · v0.1.0-singularity · 33,784 files · 144+ agents")
        self.sl2.setStyleSheet("color: " + TEXT_DIM + "; font: 10pt 'Consolas';")
        self.sl3 = QLabel(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        self.sl3.setStyleSheet("color: " + GOLD + "; font: bold 10pt 'Consolas';")
        sl.addWidget(self.sl1); sl.addStretch(); sl.addWidget(self.sl2); sl.addStretch(); sl.addWidget(self.sl3)
        v.addWidget(sb)
        ct = QTimer(self); ct.timeout.connect(lambda: self.sl3.setText(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))); ct.start(1000)

        screen = QApplication.primaryScreen().availableGeometry()
        self.resize(1280, 800)
        self.move((screen.width() - self.width()) // 2, (screen.height() - self.height()) // 2)

    def _stats_text(self):
        return ("BRAINIAC: ▮▮▮▮▮▮▮▮ 100%" + NL +
                "AGENCY:   ▮▮▮▮▮▮▮▮ 100%" + NL +
                "GODSKILL: ▮▮▮▮▮▮▮▮ 100%" + NL +
                "OMEGA:    ▮▮▮▮▮▮▮▮ 100%" + NL +
                "OLLAMA:   ▮▮▮▮▮▮▮▮ 100%" + NL +
                "──────────────────" + NL +
                "MERGE:    1.55 GB" + NL +
                "FILES:    33,784" + NL +
                "AGENTS:   144+" + NL +
                "TAG:      v0.1.0-sing")

    def _update_ind(self):
        self.indp.setText(
            "MIC:      " + ("● ON" if CFG.get('always_listen', True) else "○ OFF") + NL +
            "WAKE:     '" + CFG.get('wake_words', ['jarvis'])[0] + "'" + NL +
            "CLAP:     " + ("● ON" if CFG.get('clap_detection', True) else "○ OFF") + NL +
            "TTS:      " + ("● ON" if CFG.get('tts_enabled', True) else "○ OFF") + NL +
            "LANG:     " + CFG.get('language', 'auto').upper() + NL +
            "GOD MODE: " + ("● ON" if CFG.get('god_mode', True) else "○ OFF"))

    def _btn(self, text, slot, w, color=None):
        b = QPushButton(text)
        b.setFixedHeight(36); b.setMinimumWidth(w)
        c = color or NEON_DIM
        b.setStyleSheet("QPushButton { background: transparent; color: " + c + "; border: 1.5px solid " + c + ";"
                         " border-radius: 6px; font: bold 11pt 'Consolas'; padding: 4px 8px; }"
                         "QPushButton:hover { background: rgba(0,229,255,40); }")
        b.clicked.connect(slot)
        return b

    def _tray(self):
        pix = QPixmap(64, 64); pix.fill(Qt.GlobalColor.transparent)
        p = QPainter(pix); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        gr = QRadialGradient(32, 32, 28)
        gr.setColorAt(0, QColor(NEON)); gr.setColorAt(0.7, QColor(0,100,180)); gr.setColorAt(1, QColor(0,30,60))
        p.setBrush(QBrush(gr)); p.setPen(QPen(QColor(GOLD), 2))
        p.drawEllipse(4, 4, 56, 56); p.end()
        ic = QIcon(pix); self.setWindowIcon(ic)
        self.tray = QSystemTrayIcon(ic, self)
        m = QMenu()
        a1 = QAction("Summon JARVIS", self); a1.triggered.connect(self._summon); m.addAction(a1)
        m.addSeparator()
        aq = QAction("Quit", self); aq.triggered.connect(QApplication.instance().quit); m.addAction(aq)
        self.tray.setContextMenu(m)
        self.tray.activated.connect(lambda r: self._summon() if r == QSystemTrayIcon.ActivationReason.Trigger else None)
        self.tray.setToolTip("JARVIS BRAINIAC v2.0")
        self.tray.show()

    def _summon(self):
        self.showNormal(); self.activateWindow(); self.raise_(); self.input.setFocus()

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self._drag = ev.globalPosition().toPoint() - self.frameGeometry().topLeft()
    def mouseMoveEvent(self, ev):
        if self._drag and ev.buttons() & Qt.MouseButton.LeftButton:
            self.move(ev.globalPosition().toPoint() - self._drag)
    def mouseReleaseEvent(self, ev):
        self._drag = None

    def _send(self):
        t = self.input.text().strip()
        if not t: return
        self.input.clear()
        self._handle(t)

    def _handle(self, text):
        if text == "__mic":
            CFG["always_listen"] = not CFG.get("always_listen", True)
            save_cfg(CFG); self._update_ind(); self.orb.set_listening(CFG["always_listen"])
            self._append("[mic] " + ("ON" if CFG['always_listen'] else "OFF") + NL, GOLD); return
        if text == "__tts":
            CFG["tts_enabled"] = not CFG.get("tts_enabled", True)
            save_cfg(CFG); self._update_ind()
            self._append("[tts] " + ("ON" if CFG['tts_enabled'] else "OFF") + NL, GOLD); return
        if text == "__lang":
            order = ["auto", "en", "he", "ar"]
            cur = CFG.get("language", "auto")
            CFG["language"] = order[(order.index(cur)+1) % len(order)]
            save_cfg(CFG); self._update_ind()
            self._append("[lang] " + CFG['language'] + NL, GOLD); return
        if text == "__cfg":
            try: os.startfile(str(CONFIG_FILE))
            except Exception: pass
            return
        self._append(NL + "[YOU] " + text + NL, TEXT)
        QTimer.singleShot(0, lambda: self.brain.run_prompt(text))

    def _quick(self, p):
        if p.startswith("__"): self._handle(p); return
        self.input.setText(p); self._send()

    def _voice_now(self):
        self._append("[VOICE] Listening..." + NL, HOT)
        threading.Thread(target=self._capture, daemon=True).start()

    def _capture(self):
        try:
            import speech_recognition as sr
            r = sr.Recognizer()
            with sr.Microphone() as src:
                r.adjust_for_ambient_noise(src, duration=0.4)
                audio = r.listen(src, timeout=5, phrase_time_limit=15)
            text = r.recognize_google(audio)
            self._handle(text)
        except Exception as e:
            self._append("[voice err] " + str(e) + NL, ERR)

    def _on_wake(self):
        self._append("[WAKE]" + NL, GOLD)
        # Force window to front even if hidden/minimized
        self.showNormal()
        self.activateWindow()
        self.raise_()
        # Bring to front via Win API
        try:
            import ctypes
            hwnd = int(self.winId())
            ctypes.windll.user32.SetForegroundWindow(hwnd)
            ctypes.windll.user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        except Exception:
            pass
        self._summon()
        self.listener.set_active(True)
        QTimer.singleShot(15000, lambda: self.listener.set_active(False))
        # Also greet
        if self.tts and CFG.get("tts_enabled", True):
            self.tts.speak("Yes, sir?")

    def _on_speech(self, text, lang):
        if text.strip():
            self._handle(text)

    def _on_level(self, l):
        self.orb.set_level(l)

    def _on_clap(self):
        self._append("[CLAP] double-clap" + NL, HOT)
        self.showNormal()
        self.activateWindow()
        self.raise_()
        try:
            import ctypes
            hwnd = int(self.winId())
            ctypes.windll.user32.SetForegroundWindow(hwnd)
            ctypes.windll.user32.ShowWindow(hwnd, 9)
        except Exception:
            pass
        self._summon()
        self.listener.set_active(True)
        QTimer.singleShot(15000, lambda: self.listener.set_active(False))

    def _on_chunk(self, t):
        self._append(t, TEXT)

    def _on_err(self, m):
        self._append(NL + "[ERR] " + m + NL, ERR)

    def _on_speak(self, t):
        if CFG.get("tts_enabled", True):
            self.tts.speak(t)

    def _append(self, text, color=None):
        c = color or TEXT
        safe = (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace(NL, "<br>"))
        self.chat.moveCursor(self.chat.textCursor().MoveOperation.End)
        self.chat.insertHtml('<span style="color:' + c + ';">' + safe + '</span>')
        self.chat.moveCursor(self.chat.textCursor().MoveOperation.End)

    def closeEvent(self, ev):
        ev.ignore()
        self.hide()


def main():
    # Single-instance lock — only one JARVIS at a time
    import socket
    try:
        _lock_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        _lock_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        _lock_socket.bind(("127.0.0.1", 47291))
        _lock_socket.listen(1)
        # keep ref so it lives the lifetime of the process
        globals()["_JARVIS_LOCK"] = _lock_socket
    except OSError:
        # already running - just exit silently
        print("[JARVIS] another instance already running on port 47291 - exiting")
        return

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    win = JarvisWindow()
    win.show(); win.activateWindow(); win.raise_()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
