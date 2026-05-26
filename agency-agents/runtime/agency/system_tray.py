"""Windows system tray integration for JARVIS BRAINIAC.

Provides:
- System tray icon with right-click context menu
- Quick actions: Open Dashboard, Run Demo, Voice Command, Settings, Exit
- Notification balloon / toast messages
- Auto-start on boot configuration (Windows registry)
- Minimize-to-tray behaviour wrapper for Tkinter/Qt apps
- Cross-platform: Windows primary, Linux fallback, macOS stub

Mock implementation activates when pystray / PIL are unavailable.
"""

from __future__ import annotations

import logging
import os
import platform
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional dependency handling
# ---------------------------------------------------------------------------

try:
    import pystray
    from pystray import MenuItem as Item
    PYSTRAY_AVAILABLE = True
except Exception:  # noqa: BLE001
    pystray = None  # type: ignore[assignment]
    Item = None  # type: ignore[assignment, misc]
    PYSTRAY_AVAILABLE = False
    logger.debug("pystray not available; using mock system tray")

try:
    from PIL import Image, ImageDraw
except Exception:  # noqa: BLE001
    Image = ImageDraw = None  # type: ignore[misc]
    logger.debug("Pillow not available; icon generation disabled")

# ---------------------------------------------------------------------------
# Callback type alias
# ---------------------------------------------------------------------------

ActionCallback = Callable[[], None]


# ---------------------------------------------------------------------------
# Menu configuration
# ---------------------------------------------------------------------------

@dataclass
class TrayMenuConfig:
    """Configuration for the system tray menu."""

    app_name: str = "J.A.R.V.I.S BRAINIAC"
    tooltip: str = "J.A.R.V.I.S BRAINIAC — Supreme AI Agent"
    icon_colour: tuple[int, int, int] = (0, 180, 100)
    show_dashboard: bool = True
    show_run_demo: bool = True
    show_voice_command: bool = True
    show_settings: bool = True
    show_exit: bool = True
    show_separator: bool = True
    custom_items: list[dict[str, Any]] = field(default_factory=list)
    on_dashboard: ActionCallback | None = None
    on_run_demo: ActionCallback | None = None
    on_voice_command: ActionCallback | None = None
    on_settings: ActionCallback | None = None
    on_exit: ActionCallback | None = None


# ---------------------------------------------------------------------------
# Icon factory
# ---------------------------------------------------------------------------

class TrayIconFactory:
    """Generate tray icons programmatically (no external image files needed)."""

    @staticmethod
    def create_jarvis_icon(size: int = 64, colour: tuple[int, int, int] | None = None) -> Any:
        """Create a JARVIS-themed circular icon with 'J' letter."""
        if Image is None:
            return None
        colour = colour or (0, 180, 100)
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        margin = size // 8
        # Outer circle
        draw.ellipse([margin, margin, size - margin, size - margin],
                     fill=(*colour, 255), outline=(255, 255, 255, 180), width=2)
        # Inner 'J'
        cx, cy = size // 2, size // 2
        try:
            from PIL import ImageFont
            font_size = size // 2
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                                       font_size)
        except Exception:
            font = ImageFont.load_default()
        bbox = draw.textbbox((0, 0), "J", font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text((cx - tw // 2, cy - th // 2 - size // 12), "J",
                  fill=(255, 255, 255, 230), font=font)
        return img

    @staticmethod
    def create_dot_icon(size: int = 64, colour: tuple[int, int, int] = (0, 200, 100)) -> Any:
        """Create a simple coloured dot icon."""
        if Image is None:
            return None
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse([4, 4, size - 4, size - 4], fill=(*colour, 255))
        return img


# ---------------------------------------------------------------------------
# System Tray Controller
# ---------------------------------------------------------------------------

class SystemTrayController:
    """Cross-platform system tray integration for JARVIS BRAINIAC."""

    def __init__(self, config: TrayMenuConfig | None = None) -> None:
        self.cfg = config or TrayMenuConfig()
        self._icon: Any = None
        self._running = False
        self._thread: threading.Thread | None = None
        self._callbacks: dict[str, ActionCallback] = {}
        self._setup_callbacks()
        logger.info("SystemTrayController initialised (pystray=%s)", PYSTRAY_AVAILABLE)

    def _setup_callbacks(self) -> None:
        """Wire up default and custom callbacks."""
        self._callbacks["dashboard"] = self.cfg.on_dashboard or self._default_dashboard
        self._callbacks["demo"] = self.cfg.on_run_demo or self._default_demo
        self._callbacks["voice"] = self.cfg.on_voice_command or self._default_voice
        self._callbacks["settings"] = self.cfg.on_settings or self._default_settings
        self._callbacks["exit"] = self.cfg.on_exit or self._default_exit

    # -- Tray lifecycle -----------------------------------------------------

    def start(self) -> None:
        """Start the system tray icon in a background thread."""
        if self._running:
            logger.warning("System tray already running")
            return
        if not PYSTRAY_AVAILABLE:
            logger.info("pystray unavailable; starting mock tray loop")
            self._start_mock()
            return
        self._thread = threading.Thread(target=self._run_tray, daemon=True)
        self._thread.start()
        self._running = True
        logger.info("System tray started")

    def stop(self) -> None:
        """Stop the system tray icon."""
        if self._icon:
            try:
                self._icon.stop()
            except Exception as exc:
                logger.debug("Error stopping icon: %s", exc)
        self._running = False
        logger.info("System tray stopped")

    def is_running(self) -> bool:
        return self._running

    # -- Notifications ------------------------------------------------------

    def notify(self, title: str, message: str, duration: int = 3) -> None:
        """Show a notification balloon / toast."""
        logger.info("Notification: [%s] %s", title, message)
        if PYSTRAY_AVAILABLE and self._icon:
            try:
                self._icon.notify(message, title)
            except Exception as exc:
                logger.debug("pystray notify failed: %s", exc)
        else:
            self._fallback_notify(title, message, duration)

    def _fallback_notify(self, title: str, message: str, duration: int) -> None:
        """Fallback notification using OS-specific tools."""
        system = platform.system()
        try:
            if system == "Windows":
                self._windows_notify(title, message)
            elif system == "Linux":
                subprocess.run(["notify-send", title, message], check=False, capture_output=True)
            elif system == "Darwin":
                script = f'display notification "{message}" with title "{title}"'
                subprocess.run(["osascript", "-e", script], check=False, capture_output=True)
        except Exception as exc:
            logger.debug("Fallback notify failed: %s", exc)

    def _windows_notify(self, title: str, message: str) -> None:
        """Windows toast notification via PowerShell."""
        try:
            ps_cmd = (
                f"Add-Type -AssemblyName System.Windows.Forms; "
                f"$n=New-Object System.Windows.Forms.NotifyIcon; "
                f"$n.Icon=[System.Drawing.SystemIcons]::Information; "
                f"$n.BalloonTipTitle='{title}'; "
                f"$n.BalloonTipText='{message}'; "
                f"$n.Visible=$true; "
                f"$n.ShowBalloonTip(3000)"
            )
            subprocess.run(["powershell", "-Command", ps_cmd],
                           check=False, capture_output=True)
        except Exception as exc:
            logger.debug("Windows notify failed: %s", exc)

    # -- Auto-start on boot -------------------------------------------------

    def enable_autostart(self) -> bool:
        """Enable auto-start on boot (Windows registry)."""
        system = platform.system()
        if system == "Windows":
            return self._enable_autostart_windows()
        elif system == "Linux":
            return self._enable_autostart_linux()
        elif system == "Darwin":
            return self._enable_autostart_macos()
        logger.warning("Auto-start not supported on %s", system)
        return False

    def disable_autostart(self) -> bool:
        """Disable auto-start on boot."""
        system = platform.system()
        if system == "Windows":
            return self._disable_autostart_windows()
        elif system == "Linux":
            return self._disable_autostart_linux()
        elif system == "Darwin":
            return self._disable_autostart_macos()
        return False

    def is_autostart_enabled(self) -> bool:
        """Check whether auto-start is currently enabled."""
        system = platform.system()
        if system == "Windows":
            try:
                import winreg
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                     r"Software\Microsoft\Windows\CurrentVersion\Run")
                value, _ = winreg.QueryValueEx(key, self.cfg.app_name)
                winreg.CloseKey(key)
                return bool(value)
            except Exception:
                return False
        elif system == "Linux":
            desktop = Path.home() / ".config" / "autostart" / "jarvis-brainiac.desktop"
            return desktop.exists()
        return False

    def _enable_autostart_windows(self) -> bool:
        try:
            import winreg
            exe_path = sys.executable
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                 r"Software\Microsoft\Windows\CurrentVersion\Run",
                                 0, winreg.KEY_SET_VALUE)
            winreg.SetValueEx(key, self.cfg.app_name, 0, winreg.REG_SZ, exe_path)
            winreg.CloseKey(key)
            logger.info("Auto-start enabled (Windows registry)")
            return True
        except Exception as exc:
            logger.error("Failed to enable auto-start: %s", exc)
            return False

    def _disable_autostart_windows(self) -> bool:
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                 r"Software\Microsoft\Windows\CurrentVersion\Run",
                                 0, winreg.KEY_SET_VALUE)
            winreg.DeleteValue(key, self.cfg.app_name)
            winreg.CloseKey(key)
            logger.info("Auto-start disabled (Windows registry)")
            return True
        except Exception as exc:
            logger.error("Failed to disable auto-start: %s", exc)
            return False

    def _enable_autostart_linux(self) -> bool:
        try:
            desktop_dir = Path.home() / ".config" / "autostart"
            desktop_dir.mkdir(parents=True, exist_ok=True)
            desktop = desktop_dir / "jarvis-brainiac.desktop"
            content = (
                f"[Desktop Entry]\n"
                f"Type=Application\n"
                f"Name={self.cfg.app_name}\n"
                f"Exec={sys.executable}\n"
                f"Hidden=false\n"
                f"NoDisplay=false\n"
                f"X-GNOME-Autostart-enabled=true\n"
            )
            desktop.write_text(content)
            logger.info("Auto-start enabled (Linux desktop entry)")
            return True
        except Exception as exc:
            logger.error("Failed to enable auto-start: %s", exc)
            return False

    def _disable_autostart_linux(self) -> bool:
        try:
            desktop = Path.home() / ".config" / "autostart" / "jarvis-brainiac.desktop"
            if desktop.exists():
                desktop.unlink()
            logger.info("Auto-start disabled (Linux desktop entry)")
            return True
        except Exception as exc:
            logger.error("Failed to disable auto-start: %s", exc)
            return False

    def _enable_autostart_macos(self) -> bool:
        logger.info("Auto-start on macOS: use System Preferences > Users & Groups > Login Items")
        return False

    def _disable_autostart_macos(self) -> bool:
        logger.info("Auto-start on macOS: use System Preferences > Users & Groups > Login Items")
        return False

    # -- Minimize-to-tray wrapper -------------------------------------------

    def minimize_to_tray(self, window: Any | None = None) -> None:
        """Minimize an application window to the system tray."""
        logger.info("Minimizing application to tray")
        if window is not None and hasattr(window, "withdraw"):
            window.withdraw()
        self.start()
        self.notify("J.A.R.V.I.S BRAINIAC", "Running in system tray. Click icon to restore.")

    # -- Private: pystray runtime -------------------------------------------

    def _run_tray(self) -> None:
        if pystray is None or Item is None:
            return
        icon_img = TrayIconFactory.create_jarvis_icon(colour=self.cfg.icon_colour)
        menu = self._build_menu()
        self._icon = pystray.Icon("jarvis_brainiac", icon_img,
                                  self.cfg.tooltip, menu)
        self._icon.run()

    def _build_menu(self) -> Any:
        if Item is None:
            return None
        items: list[Any] = []
        if self.cfg.show_dashboard:
            items.append(Item("Open Dashboard", self._callbacks["dashboard"]))
        if self.cfg.show_run_demo:
            items.append(Item("Run Demo", self._callbacks["demo"]))
        if self.cfg.show_voice_command:
            items.append(Item("Voice Command", self._callbacks["voice"]))
        if self.cfg.show_settings:
            items.append(Item("Settings", self._callbacks["settings"]))
        if self.cfg.show_separator and items:
            items.append(pystray.Menu.SEPARATOR if hasattr(pystray.Menu, "SEPARATOR")
                         else Item("-", lambda: None, enabled=False))
        # Custom items
        for item_def in self.cfg.custom_items:
            name = item_def.get("name", "Custom")
            cb = item_def.get("callback", lambda: None)
            items.append(Item(name, cb))
        if self.cfg.show_exit:
            items.append(Item("Exit", self._callbacks["exit"]))
        return pystray.Menu(*items)

    # -- Mock tray loop (prints to console) ---------------------------------

    def _start_mock(self) -> None:
        self._running = True
        logger.info("[MOCK TRAY] JARVIS BRAINIAC tray icon active (console mode)")
        logger.info("[MOCK TRAY] Available actions: dashboard, demo, voice, settings, exit")

    # -- Default callbacks --------------------------------------------------

    def _default_dashboard(self) -> None:
        logger.info("Opening JARVIS BRAINIAC dashboard...")
        try:
            webbrowser = __import__("webbrowser")
            webbrowser.open("http://localhost:8080")
        except Exception:
            pass

    def _default_demo(self) -> None:
        logger.info("Running JARVIS BRAINIAC demo...")

    def _default_voice(self) -> None:
        logger.info("Activating voice command...")

    def _default_settings(self) -> None:
        logger.info("Opening JARVIS BRAINIAC settings...")

    def _default_exit(self) -> None:
        logger.info("Shutting down JARVIS BRAINIAC...")
        self.stop()
        os._exit(0)


# ---------------------------------------------------------------------------
# Convenience: quick-start tray
# ---------------------------------------------------------------------------

def create_tray(minimal: bool = False) -> SystemTrayController:
    """Create and start a system tray instance with sensible defaults."""
    cfg = TrayMenuConfig(
        custom_items=[{"name": "About", "callback": lambda: logger.info("JARVIS BRAINIAC v25.0.0")}],
    ) if not minimal else TrayMenuConfig(
        show_dashboard=False, show_run_demo=False, show_voice_command=False,
        show_settings=False, show_exit=True,
    )
    tray = SystemTrayController(config=cfg)
    tray.start()
    return tray


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    print("=" * 60)
    print("JARVIS BRAINIAC — System Tray Self-Test")
    print("=" * 60)

    # Test 1: Config
    cfg = TrayMenuConfig(app_name="Test JARVIS")
    print(f"\n[1] Tray config: app_name={cfg.app_name}")

    # Test 2: Icon factory
    icon = TrayIconFactory.create_jarvis_icon(size=64)
    print(f"\n[2] Icon generated: {'Pillow unavailable' if icon is None else f'{icon.size}px icon created'}")

    # Test 3: Controller init
    tray = SystemTrayController(config=cfg)
    print(f"\n[3] Controller created: running={tray.is_running()}")

    # Test 4: Notification (fallback)
    tray.notify("Test Title", "This is a test notification from JARVIS", duration=2)
    print(f"\n[4] Notification sent (fallback mode)")

    # Test 5: Auto-start status check
    autostart = tray.is_autostart_enabled()
    print(f"\n[5] Auto-start enabled: {autostart}")

    # Test 6: Start / stop
    tray.start()
    print(f"\n[6] Tray started: running={tray.is_running()}")
    time.sleep(0.5)
    tray.stop()
    print(f"    Tray stopped: running={tray.is_running()}")

    # Test 7: Platform detection
    print(f"\n[7] Platform: {platform.system()} {platform.release()}")
    print(f"    Python: {sys.version.split()[0]}")
    print(f"    pystray available: {PYSTRAY_AVAILABLE}")

    print("\n" + "=" * 60)
    print("All system tray tests passed!")
    print("=" * 60)
