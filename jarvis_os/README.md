# JARVIS OS Integration

Three components turn JARVIS into a Windows OS-level assistant — no browser needed:

| Component | File | What it does |
|-----------|------|--------------|
| **Native chat** | `native_chat.py` | Tkinter window — dark theme, talks to local agency runtime |
| **System tray** | `tray.py` | Notification-area icon, auto-starts agency server, right-click menu |
| **Global hotkey** | `hotkey_listener.py` | Win+J anywhere → open chat |
| **Autostart** | `INSTALL_AUTOSTART.cmd` | Registers tray + hotkey to run on Windows boot |

## Install (one click)

Double-click `INSTALL_AUTOSTART.cmd` from the workspace folder. It:
1. Installs `pystray Pillow keyboard` into the agency venv
2. Adds `jarvis_tray.bat` to `shell:startup` (runs on every Windows boot)
3. Starts tray + hotkey listener now (no reboot needed)
4. Adds Start menu shortcut

After install:
- Tray icon (J) sits in notification area
- Server auto-starts in background
- Win+J opens the native chat from anywhere
- Right-click tray → Open Chat / Status / Restart server / Quit
