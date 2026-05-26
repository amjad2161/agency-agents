"""Proactive autonomy: clipboard monitor, idle detection, event-driven suggestions."""
from __future__ import annotations
import threading, time
from datetime import datetime


class ProactiveBrain:
    def __init__(self, action, on_observation):
        self.action = action
        self.on_obs = on_observation
        self._running = False
        self._last_clip = ""
        self._last_active = time.time()
        self._mood = "calm"  # calm, focused, alert, helpful

    @property
    def mood(self): return self._mood

    def set_mood(self, m): self._mood = m

    def start(self):
        if self._running: return
        self._running = True
        threading.Thread(target=self._clip_loop, daemon=True).start()
        threading.Thread(target=self._idle_loop, daemon=True).start()

    def stop(self):
        self._running = False

    def _clip_loop(self):
        while self._running:
            try:
                txt = self.action.clip_get() if self.action else ""
                if txt and txt != self._last_clip and len(txt) > 20:
                    self._last_clip = txt
                    if txt.startswith("http") and ("github.com" in txt or "youtube.com" in txt):
                        self.on_obs("clipboard_url", txt[:200])
                    elif len(txt) > 200:
                        self.on_obs("clipboard_text", txt[:200])
            except Exception:
                pass
            time.sleep(2)

    def _idle_loop(self):
        prev_pos = None
        while self._running:
            try:
                if self.action and self.action.pyautogui:
                    pos = self.action.mouse_pos()
                    if pos != prev_pos:
                        self._last_active = time.time()
                        prev_pos = pos
                idle = time.time() - self._last_active
                if idle > 600 and idle % 600 < 6:  # every 10 minutes idle
                    self.on_obs("user_idle", str(int(idle/60)) + " minutes")
            except Exception:
                pass
            time.sleep(5)
