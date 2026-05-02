"""
JARVIS System Tray — pystray icon in Windows notification area.
Right-click menu: Open Chat, Status, Restart Server, Quit.
Auto-starts the agency server if not running.
"""
from __future__ import annotations
import os
import sys
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
AGENCY_ROOT = Path(os.environ.get("AGENCY_ROOT", Path.home() / "agency")).expanduser()
HERE = Path(__file__).resolve().parent
LOG_DIR = AGENCY_ROOT / "logs"
SERVER_LOG = LOG_DIR / "jarvis_tray_server.log"

server_process: subprocess.Popen | None = None
_server_lock = threading.Lock()
_server_owned = False  # True when *this* process spawned the server


def _make_icon(color="#58a6ff", text="J"):
    """Render a simple icon programmatically."""
    img = Image.new("RGBA", (64, 64), (13, 17, 23, 255))
    d = ImageDraw.Draw(img)
    d.ellipse([4, 4, 60, 60], fill=color)
    font = None
    # Try a small list of common fonts; fall back to PIL's bitmap font as a
    # last resort. The bitmap font renders tiny on a 64x64 icon, so we only
    # use it when nothing else is available.
    for candidate in ("arial.ttf", "segoeui.ttf", "DejaVuSans-Bold.ttf", "DejaVuSans.ttf"):
        try:
            font = ImageFont.truetype(candidate, 36)
            break
        except Exception:
            continue
    if font is None:
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


def _open_server_log():
    """Open SERVER_LOG for append, creating the parent dir; return file handle or None."""
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        return open(SERVER_LOG, "ab")
    except Exception:
        return None


def start_server(notify=None):
    """Spawn `agency serve` if not already running.

    Holds an internal lock so concurrent callers don't race to spawn duplicate
    servers. Returns True if a server is alive at the end of the call.
    """
    global server_process, _server_owned
    with _server_lock:
        if is_server_alive():
            return True
        venv_py = AGENCY_ROOT / ".venv" / "Scripts" / "python.exe"
        py = str(venv_py) if venv_py.exists() else sys.executable
        cmd = [py, "-m", "agency", "serve"]
        log_fp = _open_server_log()
        try:
            server_process = subprocess.Popen(
                cmd, cwd=str(AGENCY_ROOT),
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
                stdout=log_fp or subprocess.DEVNULL,
                stderr=subprocess.STDOUT if log_fp else subprocess.DEVNULL,
            )
            _server_owned = True
        except Exception as e:
            if log_fp:
                log_fp.close()
            if notify:
                try:
                    notify(f"Failed to start server: {e}")
                except Exception:
                    pass
            return False
        finally:
            # Once Popen has duplicated the descriptor into the child, the
            # parent's copy can be closed; the child keeps writing to the log.
            if log_fp:
                try:
                    log_fp.close()
                except Exception:
                    pass
        # Wait up to 15s for server to come up
        for _ in range(30):
            if is_server_alive():
                return True
            time.sleep(0.5)
    if notify:
        try:
            notify(f"Server did not become healthy within 15s.\nSee {SERVER_LOG}")
        except Exception:
            pass
    return False


def stop_server() -> bool:
    """Terminate a server we spawned. Returns False if the live server is foreign."""
    global server_process, _server_owned
    with _server_lock:
        if server_process and _server_owned:
            try:
                server_process.terminate()
            except Exception:
                pass
            server_process = None
            _server_owned = False
            return True
        # No owned process; if a server is alive, it was started elsewhere.
        return not is_server_alive()


def open_chat(icon, item):
    chat_script = HERE / "native_chat.py"
    venv_pyw = AGENCY_ROOT / ".venv" / "Scripts" / "pythonw.exe"
    use_console_python = False
    if venv_pyw.exists():
        py = str(venv_pyw)
    else:
        # Fall back to pythonw next to the current interpreter; otherwise current python.
        candidate = Path(sys.executable).with_name("pythonw.exe")
        if candidate.exists():
            py = str(candidate)
        else:
            py = sys.executable
            use_console_python = True
    creationflags = 0
    if os.name == "nt":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP
        if use_console_python:
            # Avoid flashing a console window when we had to fall back to python.exe.
            creationflags |= getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    subprocess.Popen([py, str(chat_script)], creationflags=creationflags)


def show_status(icon, item):
    alive = is_server_alive()
    icon.notify(
        f"Server: {'✓ alive' if alive else '✗ down'}\nURL: {AGENCY_URL}",
        title="JARVIS Status",
    )


def restart_server(icon, item):
    icon.notify("Restarting server...", title="JARVIS")

    def _restart():
        stopped = stop_server()
        if not stopped:
            try:
                icon.notify(
                    "A server is running but was not started by this tray; "
                    "leaving it alone.",
                    title="JARVIS",
                )
            except Exception:
                pass
            return
        time.sleep(1)
        ok = start_server(notify=lambda msg: icon.notify(msg, title="JARVIS"))
        if ok:
            try:
                icon.notify("Server restarted.", title="JARVIS")
            except Exception:
                pass

    threading.Thread(target=_restart, daemon=True).start()


def quit_jarvis(icon, item):
    stop_server()
    icon.stop()


def main():
    # Auto-start server in background. Notifications are deferred until the
    # icon is running, so we just log on failure here.
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
