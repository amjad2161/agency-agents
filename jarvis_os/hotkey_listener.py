"""
JARVIS Global Hotkey — Win+J brings up native chat from anywhere in Windows.
Runs alongside tray.py.
"""
from __future__ import annotations
import os, sys, subprocess, threading
from pathlib import Path

try:
    import keyboard
except ImportError:
    print("ERROR: keyboard package required. Install:")
    print("  pip install keyboard")
    sys.exit(1)

HERE = Path(__file__).resolve().parent
AGENCY_ROOT = Path(os.environ.get("AGENCY_ROOT", Path.home() / "agency"))


def open_native_chat():
    chat = HERE / "native_chat.py"
    venv_pyw = AGENCY_ROOT / ".venv" / "Scripts" / "pythonw.exe"
    py = str(venv_pyw) if venv_pyw.exists() else sys.executable
    subprocess.Popen([py, str(chat)],
                     creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0)


def main():
    print("JARVIS hotkey listener — Win+J → open chat. Ctrl+C to stop.")
    keyboard.add_hotkey("windows+j", open_native_chat)
    keyboard.wait()  # block forever


if __name__ == "__main__":
    main()
