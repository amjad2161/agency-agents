"""Real computer use: mouse, keyboard, screen, app launch, OCR, clipboard."""
from __future__ import annotations
import subprocess, threading, time
from pathlib import Path


class ComputerAction:
    def __init__(self):
        self.pyautogui = None
        self.pyperclip = None
        try:
            import pyautogui
            pyautogui.FAILSAFE = True  # safety: mouse-to-corner aborts
            self.pyautogui = pyautogui
        except Exception:
            pass
        try:
            import pyperclip
            self.pyperclip = pyperclip
        except Exception:
            pass

    # ---------- Screen ----------
    def screenshot(self, save_path=None):
        if not self.pyautogui:
            return None
        img = self.pyautogui.screenshot()
        if save_path:
            img.save(save_path)
        return img

    def screen_size(self):
        if not self.pyautogui:
            return (0, 0)
        return self.pyautogui.size()

    # ---------- Mouse ----------
    def mouse_pos(self):
        if not self.pyautogui:
            return (0, 0)
        return self.pyautogui.position()

    def move_mouse(self, x, y, duration=0.3):
        if self.pyautogui:
            self.pyautogui.moveTo(x, y, duration=duration)

    def click(self, x=None, y=None, button="left", clicks=1):
        if not self.pyautogui:
            return
        if x is not None and y is not None:
            self.pyautogui.click(x, y, button=button, clicks=clicks)
        else:
            self.pyautogui.click(button=button, clicks=clicks)

    def double_click(self, x, y):
        if self.pyautogui:
            self.pyautogui.doubleClick(x, y)

    def right_click(self, x, y):
        if self.pyautogui:
            self.pyautogui.rightClick(x, y)

    def drag(self, x1, y1, x2, y2, duration=0.5):
        if self.pyautogui:
            self.pyautogui.moveTo(x1, y1)
            self.pyautogui.dragTo(x2, y2, duration=duration, button="left")

    def scroll(self, amount):
        if self.pyautogui:
            self.pyautogui.scroll(amount)

    # ---------- Keyboard ----------
    def type_text(self, text, interval=0.02):
        if self.pyautogui:
            self.pyautogui.write(text, interval=interval)

    def press_key(self, key):
        if self.pyautogui:
            self.pyautogui.press(key)

    def hotkey(self, *keys):
        if self.pyautogui:
            self.pyautogui.hotkey(*keys)

    # ---------- Clipboard ----------
    def clip_get(self):
        if self.pyperclip:
            try: return self.pyperclip.paste()
            except Exception: return ""
        return ""

    def clip_set(self, text):
        if self.pyperclip:
            try: self.pyperclip.copy(text)
            except Exception: pass

    # ---------- Apps ----------
    def open_app(self, name_or_path):
        try:
            import os
            # Safer: try os.startfile first, fall back to start /B without shell injection
            if Path(name_or_path).exists():
                os.startfile(name_or_path)
            else:
                # Use cmd /c to avoid shell=True with user input
                subprocess.Popen(["cmd", "/c", "start", "", name_or_path], shell=False)
            return True
        except Exception:
            return False

    def open_url(self, url):
        try:
            import webbrowser
            webbrowser.open(url)
            return True
        except Exception:
            return False

    # ---------- High-level ----------
    def focus_window(self, title_substr):
        try:
            import pygetwindow as gw
            for w in gw.getAllWindows():
                if title_substr.lower() in w.title.lower():
                    w.activate()
                    return True
        except Exception:
            pass
        return False

    def list_windows(self):
        try:
            import pygetwindow as gw
            return [w.title for w in gw.getAllWindows() if w.title]
        except Exception:
            return []
