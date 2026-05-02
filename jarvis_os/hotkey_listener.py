"""
JARVIS Global Hotkey — Win+J brings up native chat from anywhere in Windows.
Runs alongside tray.py.
"""
from __future__ import annotations
import os
import sys
import subprocess
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
AGENCY_ROOT = Path(os.environ.get("AGENCY_ROOT", Path.home() / "agency")).expanduser()
LOG_DIR = AGENCY_ROOT / "logs"
HOTKEY_LOG = LOG_DIR / "jarvis_hotkey.log"

# Debounce window so mashing Win+J doesn't spawn N chat windows.
_DEBOUNCE_S = 0.7
_last_fire = 0.0


def _log(msg: str) -> None:
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with open(HOTKEY_LOG, "a", encoding="utf-8") as f:
            f.write(msg.rstrip() + "\n")
    except Exception:
        pass
    # Also surface to stderr; under pythonw.exe this is discarded but harmless.
    try:
        print(msg, file=sys.stderr)
    except Exception:
        pass


try:
    import keyboard  # type: ignore
except ImportError:
    _log(
        "ERROR: keyboard package required. Install:\n"
        "  pip install keyboard\n"
        "Note: on Linux this package needs root; on Windows it does not."
    )
    sys.exit(1)


def open_native_chat():
    global _last_fire
    now = time.monotonic()
    if now - _last_fire < _DEBOUNCE_S:
        return
    _last_fire = now

    chat = HERE / "native_chat.py"
    venv_pyw = AGENCY_ROOT / ".venv" / "Scripts" / "pythonw.exe"
    py = str(venv_pyw) if venv_pyw.exists() else sys.executable
    try:
        subprocess.Popen(
            [py, str(chat)],
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
        )
    except Exception:
        _log("Failed to launch native_chat:\n" + traceback.format_exc())


def main():
    if os.name != "nt":
        # The Win+J hotkey is Windows-specific and the `keyboard` package
        # requires root on Linux. Exit cleanly on other platforms rather than
        # silently capturing all keystrokes.
        _log(
            "JARVIS hotkey listener is Windows-only "
            "(skipping on platform: " + sys.platform + ")"
        )
        return

    print("JARVIS hotkey listener — Win+J → open chat. Ctrl+C to stop.")
    try:
        keyboard.add_hotkey("windows+j", open_native_chat)
    except Exception:
        _log("Failed to register Win+J hotkey:\n" + traceback.format_exc())
        return
    try:
        keyboard.wait()  # block forever
    except KeyboardInterrupt:
        return


if __name__ == "__main__":
    main()
