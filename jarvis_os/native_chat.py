"""
JARVIS Native Chat — Tkinter window (no browser, no web UI)
Talks to local agency runtime on http://127.0.0.1:8765
Built-in to Python 3.x — zero pip deps for the UI itself.
"""
from __future__ import annotations
import json
import os
import threading
import urllib.request
import urllib.error
import tkinter as tk
from tkinter import scrolledtext, messagebox
from datetime import datetime

AGENCY_URL = os.environ.get("JARVIS_URL", "http://127.0.0.1:8765")


class JarvisChat(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("JARVIS BRAINIAC v25 — Native")
        self.geometry("900x700")
        self.minsize(600, 400)

        # Dark theme
        self.bg_dark = "#0d1117"
        self.bg_med  = "#161b22"
        self.bg_light = "#21262d"
        self.fg      = "#c9d1d9"
        self.accent  = "#58a6ff"
        self.user_c  = "#7ee787"
        self.jarvis_c = "#79c0ff"
        self.error_c = "#f85149"

        self.configure(bg=self.bg_dark)
        # Track scheduled `after` callbacks so we can cancel them on exit and
        # avoid "invalid command name" errors firing after the root is destroyed.
        self._closing = False
        self._health_after_id: str | None = None
        self._setup_ui()
        self._check_health()

    def _setup_ui(self):
        # Menu bar
        menubar = tk.Menu(self, bg=self.bg_med, fg=self.fg)
        self.config(menu=menubar)
        filemenu = tk.Menu(menubar, tearoff=0, bg=self.bg_med, fg=self.fg)
        filemenu.add_command(label="Clear chat", command=self._clear_chat)
        filemenu.add_command(label="Save log", command=self._save_log)
        filemenu.add_separator()
        filemenu.add_command(label="Hide to tray", command=self._hide_to_tray)
        filemenu.add_command(label="Exit", command=self._real_exit)
        menubar.add_cascade(label="File", menu=filemenu)

        agentmenu = tk.Menu(menubar, tearoff=0, bg=self.bg_med, fg=self.fg)
        agentmenu.add_command(label="List agents", command=self._list_agents)
        agentmenu.add_command(label="Health check", command=self._health_popup)
        menubar.add_cascade(label="Agents", menu=agentmenu)

        # Status bar
        self.status_var = tk.StringVar(value="● Disconnected")
        status = tk.Label(self, textvariable=self.status_var,
                          bg=self.bg_light, fg=self.fg, anchor="w", padx=10, pady=4,
                          font=("Consolas", 9))
        status.pack(side=tk.BOTTOM, fill=tk.X)

        # Header
        header = tk.Frame(self, bg=self.bg_dark, height=40)
        header.pack(side=tk.TOP, fill=tk.X)
        tk.Label(header, text="🧠 JARVIS BRAINIAC", bg=self.bg_dark, fg=self.accent,
                 font=("Segoe UI", 14, "bold")).pack(side=tk.LEFT, padx=12, pady=8)
        tk.Label(header, text=f"v25 · {AGENCY_URL}", bg=self.bg_dark, fg=self.fg,
                 font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=4, pady=8)

        # Chat history
        self.chat = scrolledtext.ScrolledText(
            self, bg=self.bg_med, fg=self.fg, font=("Consolas", 10),
            wrap=tk.WORD, padx=12, pady=12, insertbackground=self.fg,
            relief=tk.FLAT, borderwidth=0,
        )
        self.chat.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=4, pady=4)
        self.chat.tag_configure("user",   foreground=self.user_c, font=("Consolas", 10, "bold"))
        self.chat.tag_configure("jarvis", foreground=self.jarvis_c, font=("Consolas", 10, "bold"))
        self.chat.tag_configure("error",  foreground=self.error_c)
        self.chat.tag_configure("info",   foreground="#8b949e", font=("Consolas", 9, "italic"))
        self.chat.config(state=tk.DISABLED)

        # Input row
        input_frame = tk.Frame(self, bg=self.bg_dark)
        input_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=4, pady=4, before=status)

        self.input = tk.Text(input_frame, bg=self.bg_light, fg=self.fg,
                             font=("Consolas", 10), height=3, wrap=tk.WORD,
                             insertbackground=self.fg, relief=tk.FLAT, padx=10, pady=8)
        self.input.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(4,4))
        # Single binding handles both plain Return (newline) and Ctrl+Return (send).
        # Binding <Control-Return> separately would cause _send to fire twice.
        self.input.bind("<Return>", self._on_enter)
        # Numpad Enter mirrors the main Return key.
        self.input.bind("<KP_Enter>", self._on_enter)
        self.input.focus_set()

        send_btn = tk.Button(input_frame, text="Send\n(Ctrl+Enter)",
                             command=self._send, bg=self.accent, fg="white",
                             font=("Segoe UI", 9, "bold"), relief=tk.FLAT,
                             padx=20, pady=10, cursor="hand2")
        send_btn.pack(side=tk.RIGHT, padx=(4,4))

        self._append("info", f"JARVIS native client started — {datetime.now():%H:%M:%S}\n")
        self._append("info", "Type your request below. Ctrl+Enter to send.\n\n")

    def _on_enter(self, event):
        # Plain Enter = newline; Ctrl+Enter sends
        if event.state & 0x4:  # Ctrl held
            self._send()
            return "break"
        return None

    def _append(self, tag, text):
        self.chat.config(state=tk.NORMAL)
        # Tk treats "" as the absence of a tag, so callers can pass "" for plain text.
        if tag:
            self.chat.insert(tk.END, text, tag)
        else:
            self.chat.insert(tk.END, text)
        self.chat.see(tk.END)
        self.chat.config(state=tk.DISABLED)

    def _append_async(self, tag, text):
        """Thread-safe append: marshal back to the Tk main loop."""
        if self._closing:
            return
        try:
            self.after(0, self._append, tag, text)
        except tk.TclError:
            # Root was destroyed between the check and the schedule.
            pass

    def _set_status_async(self, text: str) -> None:
        """Thread-safe status update; no-op once the window is closing."""
        if self._closing:
            return
        try:
            self.after(0, self.status_var.set, text)
        except tk.TclError:
            pass

    def _send(self):
        text = self.input.get("1.0", tk.END).strip()
        if not text:
            return
        self.input.delete("1.0", tk.END)
        ts = datetime.now().strftime("%H:%M:%S")
        self._append("user", f"[{ts}] You:  ")
        self._append("", f"{text}\n")

        threading.Thread(target=self._ask, args=(text,), daemon=True).start()

    def _ask(self, text):
        try:
            payload = json.dumps({"message": text}).encode("utf-8")
            req = urllib.request.Request(
                f"{AGENCY_URL}/api/run",
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            answer = (
                data.get("text")
                or data.get("response")
                or data.get("output")
                or data.get("message")
                or json.dumps(data)
            )
        except urllib.error.HTTPError as e:
            try:
                body = e.read().decode("utf-8", "replace")
            except Exception:
                body = ""
            self._append_async("error", f"\n[HTTP {e.code}] {e.reason}\n{body}\n\n")
            return
        except TimeoutError:
            self._append_async(
                "error",
                "\n[TIMEOUT] Request took longer than 120s. The server may be busy "
                "or stuck — try again, or check `agency serve` logs.\n\n",
            )
            return
        except Exception as e:
            self._append_async("error", f"\n[ERROR] {type(e).__name__}: {e}\n\n")
            return

        ts = datetime.now().strftime("%H:%M:%S")
        self._append_async("jarvis", f"[{ts}] JARVIS: ")
        self._append_async("", f"{answer}\n\n")

    def _check_health(self):
        if self._closing:
            return

        def check():
            try:
                with urllib.request.urlopen(f"{AGENCY_URL}/api/health", timeout=3) as r:
                    if r.status == 200:
                        self._set_status_async(f"● Connected — {AGENCY_URL}")
                        return
            except Exception:
                pass
            self._set_status_async(
                f"● Disconnected — {AGENCY_URL} (start agency serve)"
            )

        threading.Thread(target=check, daemon=True).start()
        try:
            self._health_after_id = self.after(5000, self._check_health)  # poll every 5s
        except tk.TclError:
            self._health_after_id = None

    def _list_agents(self):
        def fetch():
            try:
                with urllib.request.urlopen(f"{AGENCY_URL}/api/skills", timeout=5) as r:
                    raw = json.loads(r.read())
                # Endpoint returns {"count": N, "skills": [...]} but tolerate a
                # raw list for forward/backward compatibility.
                if isinstance(raw, dict):
                    skills = raw.get("skills", [])
                    count = raw.get("count", len(skills))
                else:
                    skills = raw
                    count = len(skills)
                text = f"\n=== {count} agents available ===\n"
                for s in skills[:50]:
                    name = s.get("name", "?") if isinstance(s, dict) else str(s)
                    text += f"  • {name}\n"
                if count > 50:
                    text += f"\n(showing first 50 of {count})\n\n"
                else:
                    text += "\n"
                self._append_async("info", text)
            except Exception as e:
                self._append_async("error", f"\n[list_agents] {e}\n\n")

        threading.Thread(target=fetch, daemon=True).start()

    def _health_popup(self):
        # Run the network call off the Tk main thread so a slow/hung server
        # doesn't freeze the UI for the duration of the timeout.
        def fetch():
            try:
                with urllib.request.urlopen(f"{AGENCY_URL}/api/health", timeout=3) as r:
                    body = r.read().decode()
                self._show_dialog_async("info", "Health", body)
            except Exception as e:
                self._show_dialog_async("error", "Health", f"{e}")

        threading.Thread(target=fetch, daemon=True).start()

    def _show_dialog_async(self, kind: str, title: str, message: str) -> None:
        if self._closing:
            return
        show = messagebox.showinfo if kind == "info" else messagebox.showerror
        try:
            self.after(0, show, title, message)
        except tk.TclError:
            pass

    def _clear_chat(self):
        self.chat.config(state=tk.NORMAL)
        self.chat.delete("1.0", tk.END)
        self.chat.config(state=tk.DISABLED)

    def _save_log(self):
        from tkinter import filedialog
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text", "*.txt"), ("All", "*.*")],
            initialfile=f"jarvis_chat_{datetime.now():%Y%m%d_%H%M%S}.txt",
        )
        if path:
            self.chat.config(state=tk.NORMAL)
            data = self.chat.get("1.0", tk.END)
            self.chat.config(state=tk.DISABLED)
            with open(path, "w", encoding="utf-8") as f:
                f.write(data)

    def _hide_to_tray(self):
        self.withdraw()  # tray.py will re-show on click

    def _real_exit(self):
        self._closing = True
        if self._health_after_id is not None:
            try:
                self.after_cancel(self._health_after_id)
            except tk.TclError:
                pass
            self._health_after_id = None
        self.destroy()


if __name__ == "__main__":
    app = JarvisChat()
    # Override close button → hide to tray (instead of exit)
    app.protocol("WM_DELETE_WINDOW", app._hide_to_tray)
    app.mainloop()
