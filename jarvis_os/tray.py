"""
JARVIS System Tray — pystray icon in Windows notification area.
Right-click menu: Open Chat, Status, Restart Server, Quit.
Auto-starts the agency server if not running.
"""
from __future__ import annotations
import os
import sys
import json
import time
import threading
import subprocess
import urllib.request
from pathlib import Path

try:
    import pystray
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("ERROR: pystray and Pillow required. Install:")
    print("  pip install pystray Pillow")
    sys.exit(1)

AGENCY_URL = os.environ.get("JARVIS_URL", "http://127.0.0.1:8765")
AGENCY_ROOT = Path(os.environ.get("AGENCY_ROOT", Path.home() / "agency"))
HERE = Path(__file__).resolve().parent

server_process: subprocess.Popen | None = None


def _make_icon(color="#58a6ff", text="J"):
    """Render a simple icon programmatically."""
    img = Image.new("RGBA", (64, 64), (13, 17, 23, 255))
    d = ImageDraw.Draw(img)
    d.ellipse([4, 4, 60, 60], fill=color)
    try:
        font = ImageFont.truetype("arial.ttf", 36)
    except Exception:
        font = ImageFont.load_default()
    bbox = d.textbbox((0, 0), text, font=font)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    d.text(((64 - w) / 2 - bbox[0], (64 - h) / 2 - bbox[1]),
           text, fill="white", font=font)
    return img


def is_server_alive() -> bool:
    try:
        with urllib.request.urlopen(f"{AGENCY_URL}/api/health", timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


def start_server():
    global server_process
    if is_server_alive():
        return
    venv_py = AGENCY_ROOT / ".venv" / "Scripts" / "python.exe"
    py = str(venv_py) if venv_py.exists() else sys.executable
    cmd = [py, "-m", "agency", "serve"]
    server_process = subprocess.Popen(
        cmd, cwd=str(AGENCY_ROOT),
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    # Wait up to 15s for server to come up
    for _ in range(30):
        if is_server_alive():
            break
        time.sleep(0.5)


def stop_server():
    global server_process
    if server_process:
        server_process.terminate()
        server_process = None


def open_chat(icon, item):
    chat_script = HERE / "native_chat.py"
    venv_pyw = AGENCY_ROOT / ".venv" / "Scripts" / "pythonw.exe"
    if venv_pyw.exists():
        py = str(venv_pyw)
    else:
        # Fall back to pythonw next to the current interpreter; otherwise current python.
        candidate = Path(sys.executable).with_name("pythonw.exe")
        py = str(candidate) if candidate.exists() else sys.executable
    subprocess.Popen([py, str(chat_script)],
                     creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0)


def show_status(icon, item):
    alive = is_server_alive()
    icon.notify(
        f"Server: {'✓ alive' if alive else '✗ down'}\nURL: {AGENCY_URL}",
        title="JARVIS Status",
    )


def restart_server(icon, item):
    icon.notify("Restarting server...", title="JARVIS")
    stop_server()
    time.sleep(1)
    threading.Thread(target=start_server, daemon=True).start()


def quit_jarvis(icon, item):
    stop_server()
    icon.stop()


def main():
    # Auto-start server in background
    threading.Thread(target=start_server, daemon=True).start()

    menu = pystray.Menu(
        pystray.MenuItem("Open Chat", open_chat, default=True),
        pystray.MenuItem("Status", show_status),
        pystray.MenuItem("Restart server", restart_server),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit JARVIS", quit_jarvis),
    )
    icon = pystray.Icon("jarvis", _make_icon(), "JARVIS BRAINIAC v25", menu)
    icon.run()


if __name__ == "__main__":
    main()
