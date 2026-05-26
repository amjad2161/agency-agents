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

## Notes & caveats

- **Platform.** The tray + hotkey + autostart pieces are Windows-only. On
  non-Windows platforms `hotkey_listener.py` exits cleanly and the `.bat`
  launchers are not used.
- **`keyboard` package.** Provides the global Win+J hotkey via a low-level
  keyboard hook. Some antivirus/EDR products flag this. On Linux the same
  package requires root (it taps `/dev/input/*`); the listener won't be
  started there.
- **Server logs.** When the tray spawns `agency serve`, stdout/stderr are
  written to `%AGENCY_ROOT%\logs\jarvis_tray_server.log`. Hotkey errors go to
  `jarvis_hotkey.log` in the same folder.
- **`AGENCY_ROOT` override.** Set `AGENCY_ROOT` in your environment before
  running `INSTALL_AUTOSTART.cmd` or the launcher `.bat` files to pick a
  non-default install location (default: `%USERPROFILE%\agency`).
- **Reinstall safety.** Re-running the installer renames any existing
  `jarvis_os/` directory to `jarvis_os.bak.<timestamp>` rather than deleting
  it, so local edits aren't lost.
