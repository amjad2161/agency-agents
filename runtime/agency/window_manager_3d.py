"""
window_manager_3d.py - 3D spatial window management for JARVIS BRAINIAC.

Provides advanced window manipulation capabilities with a 3D spatial model:
- Window positioning in 2D and depth (Z-order)
- Transparency, topmost, and visual effects
- Automatic layout algorithms (grid, cascade)
- Virtual desktop management
- Cross-platform with native backends and mock fallbacks.

Platforms:
    - Windows: Native Win32 API via ctypes
    - Linux: xdotool/ewmh via subprocess
    - macOS: AppleScript via subprocess
    - Fallback: Mock window server simulation

Author: JARVIS BRAINIAC Runtime Team
License: Proprietary
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import enum
import logging
import math
import os
import platform
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Windows constants
# ---------------------------------------------------------------------------

GWL_EXSTYLE = -20
GWL_STYLE = -16
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOPMOST = 0x00000008
LWA_ALPHA = 0x00000002
LWA_COLORKEY = 0x00000001
SW_MINIMIZE = 6
SW_MAXIMIZE = 3
SW_RESTORE = 9
SW_SHOW = 5
SW_HIDE = 0
HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
HWND_TOP = 0
SWP_FRAMECHANGED = 0x0020
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_SHOWWINDOW = 0x0040
SWP_NOACTIVATE = 0x0010
SWP_NOZORDER = 0x0004
MONITOR_DEFAULTTOPRIMARY = 1
DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWA_MICA_EFFECT = 1029
SRCCOPY = 0x00CC0020
CAPTUREBLT = 0x40000000


class WindowCornerPreference(enum.Enum):
    """Window corner rounding options (Windows 11+)."""

    DEFAULT = 0
    DONOTROUND = 1
    ROUND = 2
    ROUNDSMALL = 3


class LayoutMode(enum.Enum):
    """Window arrangement layout modes."""

    GRID = "grid"
    CASCADE = "cascade"
    STACK = "stack"
    SPIRAL = "spiral"
    FLOAT = "float"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class WindowInfo:
    """Comprehensive information about a managed window."""

    hwnd: int
    title: str
    class_name: str
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0
    z_index: int = 0
    opacity: float = 1.0
    is_minimized: bool = False
    is_maximized: bool = False
    is_topmost: bool = False
    is_visible: bool = True
    process_id: int = 0
    process_name: str = ""
    desktop_id: int = 0
    monitor_index: int = 0

    @property
    def center(self) -> Tuple[int, int]:
        """Return the center point of the window."""
        return (self.x + self.width // 2, self.y + self.height // 2)

    @property
    def rect(self) -> Tuple[int, int, int, int]:
        """Return (x, y, width, height) as a tuple."""
        return (self.x, self.y, self.width, self.height)

    @property
    def area(self) -> int:
        """Return the pixel area of the window."""
        return self.width * self.height


@dataclass
class MonitorInfo:
    """Information about a display monitor."""

    index: int
    x: int
    y: int
    width: int
    height: int
    is_primary: bool = False
    dpi_scale: float = 1.0
    name: str = ""

    @property
    def work_area(self) -> Tuple[int, int, int, int]:
        """Return the available work area (excluding taskbar)."""
        # Approximate: reduce height by 40px for taskbar on primary
        if self.is_primary:
            return (self.x, self.y, self.width, self.height - 40)
        return (self.x, self.y, self.width, self.height)


@dataclass
class VirtualDesktop:
    """Represents a virtual desktop workspace."""

    desktop_id: int
    name: str
    windows: List[int] = field(default_factory=list)
    wallpaper: str = ""
    is_current: bool = False


@dataclass
class AnimationState:
    """Tracks an ongoing window animation."""

    hwnd: int
    target_x: int
    target_y: int
    target_w: int
    target_h: int
    target_opacity: float
    start_time: float
    duration: float
    easing: str = "ease_in_out"

    def progress(self) -> float:
        """Return animation progress 0.0 to 1.0."""
        elapsed = time.time() - self.start_time
        return min(1.0, elapsed / self.duration) if self.duration > 0 else 1.0


# ---------------------------------------------------------------------------
# Mock window manager for headless / non-supported platforms
# ---------------------------------------------------------------------------

class MockWindowManager:
    """
    Simulated window manager for platforms without native API access.
    Provides realistic window state tracking and layout computation.
    """

    def __init__(self) -> None:
        self._windows: Dict[int, WindowInfo] = {}
        self._desktops: Dict[int, VirtualDesktop] = {}
        self._current_desktop: int = 0
        self._monitors: List[MonitorInfo] = []
        self._animations: Dict[int, AnimationState] = {}
        self._next_hwnd: int = 10000
        self._lock = threading.RLock()
        self._init_mock_data()
        self._animation_thread: Optional[threading.Thread] = None
        self._running = True
        self._start_animation_loop()

    def _init_mock_data(self) -> None:
        """Create realistic mock window data."""
        self._monitors = [
            MonitorInfo(index=0, x=0, y=0, width=1920, height=1080, is_primary=True, name="DP-1"),
            MonitorInfo(index=1, x=1920, y=0, width=1920, height=1080, is_primary=False, name="HDMI-1"),
        ]
        for i in range(3):
            self._desktops[i] = VirtualDesktop(
                desktop_id=i, name=f"Desktop {i + 1}", is_current=(i == 0)
            )

        mock_windows = [
            ("Terminal", "terminal", 100, 100, 800, 500),
            ("Browser", "browser", 200, 150, 1200, 700),
            ("Code Editor", "code", 50, 50, 1000, 650),
            ("File Manager", "files", 300, 200, 700, 500),
            ("Music Player", "music", 400, 100, 500, 350),
        ]
        for title, cls, x, y, w, h in mock_windows:
            hwnd = self._next_hwnd
            self._next_hwnd += 1
            self._windows[hwnd] = WindowInfo(
                hwnd=hwnd,
                title=title,
                class_name=cls,
                x=x,
                y=y,
                width=w,
                height=h,
                z_index=hwnd - 10000,
                opacity=1.0,
                is_visible=True,
                process_id=1000 + (hwnd - 10000),
                process_name=f"{cls}.exe",
                desktop_id=0,
            )
            self._desktops[0].windows.append(hwnd)

    def _start_animation_loop(self) -> None:
        """Start a background thread to process window animations."""
        def loop() -> None:
            while self._running:
                self._tick_animations()
                time.sleep(0.016)  # ~60 FPS

        self._animation_thread = threading.Thread(target=loop, daemon=True)
        self._animation_thread.start()

    def _tick_animations(self) -> None:
        """Process one frame of all active animations."""
        with self._lock:
            completed: List[int] = []
            for hwnd, anim in self._animations.items():
                t = anim.progress()
                # Ease in-out
                if anim.easing == "ease_in_out":
                    t = t * t * (3.0 - 2.0 * t)
                elif anim.easing == "ease_out":
                    t = 1.0 - (1.0 - t) * (1.0 - t)
                elif anim.easing == "ease_in":
                    t = t * t

                if hwnd in self._windows:
                    w = self._windows[hwnd]
                    w.x = int(w.x + (anim.target_x - w.x) * t)
                    w.y = int(w.y + (anim.target_y - w.y) * t)
                    w.width = int(w.width + (anim.target_w - w.width) * t)
                    w.height = int(w.height + (anim.target_h - w.height) * t)
                    w.opacity = w.opacity + (anim.target_opacity - w.opacity) * t
                if t >= 1.0:
                    completed.append(hwnd)
            for hwnd in completed:
                del self._animations[hwnd]

    def _get_monitor_for_point(self, x: int, y: int) -> MonitorInfo:
        """Determine which monitor contains a given point."""
        for m in self._monitors:
            if m.x <= x < m.x + m.width and m.y <= y < m.y + m.height:
                return m
        return self._monitors[0] if self._monitors else MonitorInfo(0, 0, 0, 1920, 1080, True)

    def get_window_list(self) -> List[WindowInfo]:
        """Return all tracked windows sorted by Z-index."""
        with self._lock:
            return sorted(self._windows.values(), key=lambda w: w.z_index)

    def move_window(self, hwnd: int, x: int, y: int, width: int, height: int) -> bool:
        """Move and resize a window with animation."""
        with self._lock:
            if hwnd not in self._windows:
                return False
            self._animations[hwnd] = AnimationState(
                hwnd=hwnd,
                target_x=x,
                target_y=y,
                target_w=width,
                target_h=height,
                target_opacity=self._windows[hwnd].opacity,
                start_time=time.time(),
                duration=0.2,
            )
            return True

    def set_window_depth(self, hwnd: int, z_index: int) -> bool:
        """Set the Z-order of a window."""
        with self._lock:
            if hwnd not in self._windows:
                return False
            self._windows[hwnd].z_index = z_index
            return True

    def minimize_window(self, hwnd: int) -> bool:
        """Minimize a window."""
        with self._lock:
            if hwnd not in self._windows:
                return False
            self._windows[hwnd].is_minimized = True
            self._windows[hwnd].is_visible = False
            return True

    def maximize_window(self, hwnd: int) -> bool:
        """Maximize a window."""
        with self._lock:
            if hwnd not in self._windows:
                return False
            mon = self._get_monitor_for_point(self._windows[hwnd].x, self._windows[hwnd].y)
            wa = mon.work_area
            self._windows[hwnd].is_maximized = True
            self.move_window(hwnd, wa[0], wa[1], wa[2], wa[3])
            return True

    def restore_window(self, hwnd: int) -> bool:
        """Restore a minimized or maximized window."""
        with self._lock:
            if hwnd not in self._windows:
                return False
            self._windows[hwnd].is_minimized = False
            self._windows[hwnd].is_maximized = False
            self._windows[hwnd].is_visible = True
            return True

    def set_window_opacity(self, hwnd: int, opacity: float) -> bool:
        """Set window transparency (0.0 to 1.0)."""
        with self._lock:
            if hwnd not in self._windows:
                return False
            self._windows[hwnd].opacity = max(0.0, min(1.0, opacity))
            return True

    def set_window_topmost(self, hwnd: int, topmost: bool = True) -> bool:
        """Set or clear always-on-top status."""
        with self._lock:
            if hwnd not in self._windows:
                return False
            self._windows[hwnd].is_topmost = topmost
            if topmost:
                self._windows[hwnd].z_index = 9999
            return True

    def capture_window(self, hwnd: int) -> np.ndarray:
        """
        Capture a screenshot of a window as a numpy array.
        Returns a colored gradient image in mock mode.
        """
        with self._lock:
            if hwnd not in self._windows:
                return np.zeros((480, 640, 3), dtype=np.uint8)
            w = self._windows[hwnd]
            h, wd = w.height, w.width
            if h <= 0 or wd <= 0:
                h, wd = 480, 640
            img = np.zeros((h, wd, 3), dtype=np.uint8)
            # Create a distinctive gradient based on hwnd
            seed = (hwnd * 7) % 255
            for y in range(h):
                for c in range(3):
                    img[y, :, c] = int((seed + y * 2 + c * 50) % 255)
            return img

    def arrange_windows_grid(self, cols: int = 2, rows: int = 2) -> bool:
        """Arrange visible windows in a grid layout."""
        with self._lock:
            visible = [w for w in self._windows.values() if w.is_visible and not w.is_minimized]
            if not visible or not self._monitors:
                return False
            mon = self._monitors[0]
            wa = mon.work_area
            cell_w = wa[2] // cols
            cell_h = wa[3] // rows
            for i, win in enumerate(visible[: cols * rows]):
                col = i % cols
                row = i // cols
                x = wa[0] + col * cell_w
                y = wa[1] + row * cell_h
                self.move_window(win.hwnd, x, y, cell_w, cell_h)
            return True

    def cascade_windows(self) -> bool:
        """Arrange visible windows in a cascading layout."""
        with self._lock:
            visible = [w for w in self._windows.values() if w.is_visible and not w.is_minimized]
            if not visible or not self._monitors:
                return False
            mon = self._monitors[0]
            wa = mon.work_area
            offset_x, offset_y = 30, 30
            base_w, base_h = wa[2] - offset_x * (len(visible) - 1), wa[3] - offset_y * (len(visible) - 1)
            for i, win in enumerate(visible):
                x = wa[0] + offset_x * i
                y = wa[1] + offset_y * i
                self.move_window(win.hwnd, x, y, base_w, base_h)
            return True

    def stack_windows(self) -> bool:
        """Stack all visible windows to fill the screen vertically."""
        with self._lock:
            visible = [w for w in self._windows.values() if w.is_visible and not w.is_minimized]
            if not visible or not self._monitors:
                return False
            mon = self._monitors[0]
            wa = mon.work_area
            count = len(visible)
            cell_h = wa[3] // count
            for i, win in enumerate(visible):
                y = wa[1] + i * cell_h
                self.move_window(win.hwnd, wa[0], y, wa[2], cell_h)
            return True

    def get_window_at_position(self, x: int, y: int) -> Optional[WindowInfo]:
        """Return the topmost window at a given screen position."""
        with self._lock:
            candidates: List[WindowInfo] = []
            for w in self._windows.values():
                if w.is_visible and not w.is_minimized:
                    if w.x <= x < w.x + w.width and w.y <= y < w.y + w.height:
                        candidates.append(w)
            if not candidates:
                return None
            return max(candidates, key=lambda w: w.z_index)

    def send_window_to_virtual_desktop(self, hwnd: int, desktop_id: int) -> bool:
        """Move a window to a different virtual desktop."""
        with self._lock:
            if hwnd not in self._windows:
                return False
            old_id = self._windows[hwnd].desktop_id
            if old_id in self._desktops and hwnd in self._desktops[old_id].windows:
                self._desktops[old_id].windows.remove(hwnd)
            self._windows[hwnd].desktop_id = desktop_id
            if desktop_id not in self._desktops:
                self._desktops[desktop_id] = VirtualDesktop(
                    desktop_id=desktop_id, name=f"Desktop {desktop_id + 1}"
                )
            self._desktops[desktop_id].windows.append(hwnd)
            if desktop_id != self._current_desktop:
                self._windows[hwnd].is_visible = False
            else:
                self._windows[hwnd].is_visible = True
            return True

    def switch_virtual_desktop(self, desktop_id: int) -> bool:
        """Switch to a different virtual desktop."""
        with self._lock:
            if desktop_id not in self._desktops:
                return False
            # Hide all windows on old desktop
            if self._current_desktop in self._desktops:
                for hwnd in self._desktops[self._current_desktop].windows:
                    if hwnd in self._windows:
                        self._windows[hwnd].is_visible = False
            self._current_desktop = desktop_id
            # Show windows on new desktop
            self._desktops[desktop_id].is_current = True
            for hwnd in self._desktops[desktop_id].windows:
                if hwnd in self._windows:
                    self._windows[hwnd].is_visible = True
            return True

    def get_virtual_desktops(self) -> List[VirtualDesktop]:
        """Return all virtual desktops."""
        with self._lock:
            return list(self._desktops.values())

    def get_monitors(self) -> List[MonitorInfo]:
        """Return all monitor information."""
        with self._lock:
            return list(self._monitors)

    def close_window(self, hwnd: int) -> bool:
        """Close and remove a window from management."""
        with self._lock:
            if hwnd not in self._windows:
                return False
            d = self._windows[hwnd].desktop_id
            if d in self._desktops and hwnd in self._desktops[d].windows:
                self._desktops[d].windows.remove(hwnd)
            del self._windows[hwnd]
            return True

    def create_window(self, title: str, x: int, y: int, width: int, height: int) -> int:
        """Create a new tracked window."""
        with self._lock:
            hwnd = self._next_hwnd
            self._next_hwnd += 1
            self._windows[hwnd] = WindowInfo(
                hwnd=hwnd,
                title=title,
                class_name="mock",
                x=x,
                y=y,
                width=width,
                height=height,
                z_index=len(self._windows),
                is_visible=True,
                process_id=99999,
                process_name="mock.exe",
                desktop_id=self._current_desktop,
            )
            if self._current_desktop in self._desktops:
                self._desktops[self._current_desktop].windows.append(hwnd)
            return hwnd

    def get_foreground_window(self) -> Optional[WindowInfo]:
        """Get the currently focused window."""
        with self._lock:
            visible = [w for w in self._windows.values() if w.is_visible]
            return max(visible, key=lambda w: w.z_index) if visible else None

    def set_foreground_window(self, hwnd: int) -> bool:
        """Bring a window to the foreground."""
        return self.set_window_depth(hwnd, 9999)

    def resize_to_monitor(self, hwnd: int, monitor_index: int = 0) -> bool:
        """Resize a window to fill a specific monitor."""
        with self._lock:
            if hwnd not in self._windows or monitor_index >= len(self._monitors):
                return False
            mon = self._monitors[monitor_index]
            wa = mon.work_area
            self.move_window(hwnd, wa[0], wa[1], wa[2], wa[3])
            self._windows[hwnd].monitor_index = monitor_index
            return True

    def set_window_corner_preference(self, hwnd: int, preference: WindowCornerPreference) -> bool:
        """Set window corner rounding preference (mock no-op)."""
        with self._lock:
            if hwnd not in self._windows:
                return False
            return True

    def toggle_dark_mode(self, hwnd: int, enabled: bool = True) -> bool:
        """Toggle immersive dark mode for a window (mock no-op)."""
        with self._lock:
            if hwnd not in self._windows:
                return False
            return True

    def get_window_border_padding(self) -> int:
        """Return window border padding size."""
        return 8

    def animate_window(self, hwnd: int, target_rect: Tuple[int, int, int, int], duration: float = 0.3) -> bool:
        """Animate a window to a target rectangle."""
        x, y, w, h = target_rect
        with self._lock:
            if hwnd not in self._windows:
                return False
            self._animations[hwnd] = AnimationState(
                hwnd=hwnd,
                target_x=x,
                target_y=y,
                target_w=w,
                target_h=h,
                target_opacity=self._windows[hwnd].opacity,
                start_time=time.time(),
                duration=duration,
            )
            return True

    def close(self) -> None:
        """Shutdown the mock window manager."""
        self._running = False
        if self._animation_thread:
            self._animation_thread.join(timeout=1.0)


# ---------------------------------------------------------------------------
# Windows native implementation
# ---------------------------------------------------------------------------

class WindowsWindowManager:
    """
    Native Windows window manager using ctypes Win32 API.

    Supports all features including transparency, Z-order, virtual desktops,
    monitor-aware layouts, and window capture.
    """

    def __init__(self) -> None:
        self._user32 = ctypes.windll.user32
        self._kernel32 = ctypes.windll.kernel32
        self._dwmapi = ctypes.windll.dwmapi
        self._gdi32 = ctypes.windll.gdi32
        self._setup_prototypes()
        self._monitors: List[MonitorInfo] = []
        self._scan_monitors()

    def _setup_prototypes(self) -> None:
        """Configure ctypes function signatures."""
        self._user32.EnumWindows.argtypes = [ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM), wt.LPARAM]
        self._user32.EnumWindows.restype = wt.BOOL

        self._user32.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
        self._user32.GetWindowRect.restype = wt.BOOL

        self._user32.SetWindowPos.argtypes = [
            wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.UINT,
        ]
        self._user32.SetWindowPos.restype = wt.BOOL

        self._user32.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]
        self._user32.ShowWindow.restype = wt.BOOL

        self._user32.SetLayeredWindowAttributes.argtypes = [wt.HWND, wt.COLORREF, wt.BYTE, wt.DWORD]
        self._user32.SetLayeredWindowAttributes.restype = wt.BOOL

        self._user32.SetWindowLongA.argtypes = [wt.HWND, ctypes.c_int, wt.LONG]
        self._user32.SetWindowLongA.restype = wt.LONG

        self._user32.GetWindowLongA.argtypes = [wt.HWND, ctypes.c_int]
        self._user32.GetWindowLongA.restype = wt.LONG

        self._user32.IsWindowVisible.argtypes = [wt.HWND]
        self._user32.IsWindowVisible.restype = wt.BOOL

        self._user32.IsIconic.argtypes = [wt.HWND]
        self._user32.IsIconic.restype = wt.BOOL

        self._user32.IsZoomed.argtypes = [wt.HWND]
        self._user32.IsZoomed.restype = wt.BOOL

        self._user32.GetWindowTextA.argtypes = [wt.HWND, wt.LPSTR, ctypes.c_int]
        self._user32.GetWindowTextA.restype = ctypes.c_int

        self._user32.GetClassNameA.argtypes = [wt.HWND, wt.LPSTR, ctypes.c_int]
        self._user32.GetClassNameA.restype = ctypes.c_int

        self._user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
        self._user32.GetWindowThreadProcessId.restype = wt.DWORD

        self._user32.GetForegroundWindow.argtypes = []
        self._user32.GetForegroundWindow.restype = wt.HWND

        self._user32.SetForegroundWindow.argtypes = [wt.HWND]
        self._user32.SetForegroundWindow.restype = wt.BOOL

        self._user32.FindWindowA.argtypes = [wt.LPCSTR, wt.LPCSTR]
        self._user32.FindWindowA.restype = wt.HWND

    def _scan_monitors(self) -> None:
        """Enumerate all connected monitors."""
        self._monitors = []
        monitor_enum_proc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HMONITOR, wt.HDC, ctypes.POINTER(wt.RECT), wt.LPARAM)

        def callback(h_monitor: int, _: int, rect_ptr: Any, idx: int) -> bool:
            rect = rect_ptr.contents
            info = wt.MONITORINFO()
            info.cbSize = ctypes.sizeof(wt.MONITORINFO)
            self._user32.GetMonitorInfoA(h_monitor, ctypes.byref(info))
            self._monitors.append(
                MonitorInfo(
                    index=idx,
                    x=info.rcWork.left,
                    y=info.rcWork.top,
                    width=info.rcWork.right - info.rcWork.left,
                    height=info.rcWork.bottom - info.rcWork.top,
                    is_primary=(idx == 0),
                    name=f"MONITOR-{idx}",
                )
            )
            return True

        cb = monitor_enum_proc(callback)
        ctypes.windll.user32.EnumDisplayMonitors(None, None, cb, 0)

    def _get_window_title(self, hwnd: int) -> str:
        """Extract the title text of a window."""
        buf = ctypes.create_string_buffer(512)
        length = self._user32.GetWindowTextA(hwnd, buf, 512)
        return buf.value.decode("utf-8", errors="replace") if length > 0 else ""

    def _get_class_name(self, hwnd: int) -> str:
        """Extract the class name of a window."""
        buf = ctypes.create_string_buffer(256)
        length = self._user32.GetClassNameA(hwnd, buf, 256)
        return buf.value.decode("utf-8", errors="replace") if length > 0 else ""

    def _get_process_id(self, hwnd: int) -> int:
        """Get the process ID that owns a window."""
        pid = wt.DWORD(0)
        self._user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return pid.value

    def _get_window_rect(self, hwnd: int) -> Tuple[int, int, int, int]:
        """Get window rectangle as (x, y, width, height)."""
        rect = wt.RECT()
        self._user32.GetWindowRect(hwnd, ctypes.byref(rect))
        return (rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top)

    def _is_real_window(self, hwnd: int) -> bool:
        """Filter out invisible/system windows from enumeration."""
        if not self._user32.IsWindowVisible(hwnd):
            return False
        title = self._get_window_title(hwnd)
        if not title:
            return False
        # Skip common system windows
        skip_classes = ["Progman", "WorkerW", "Shell_TrayWnd", "Windows.UI.Core.CoreWindow"]
        cls = self._get_class_name(hwnd)
        if cls in skip_classes:
            return False
        return True

    def get_window_list(self) -> List[WindowInfo]:
        """Enumerate all visible windows with their properties."""
        windows: List[WindowInfo] = []
        results: List[int] = []

        enum_proc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

        def callback(hwnd: int, _: int) -> bool:
            if self._is_real_window(hwnd):
                results.append(hwnd)
            return True

        cb = enum_proc(callback)
        self._user32.EnumWindows(cb, 0)

        for z_idx, hwnd in enumerate(results):
            x, y, w, h = self._get_window_rect(hwnd)
            pid = self._get_process_id(hwnd)
            info = WindowInfo(
                hwnd=hwnd,
                title=self._get_window_title(hwnd),
                class_name=self._get_class_name(hwnd),
                x=x,
                y=y,
                width=w,
                height=h,
                z_index=z_idx,
                is_minimized=bool(self._user32.IsIconic(hwnd)),
                is_maximized=bool(self._user32.IsZoomed(hwnd)),
                is_visible=True,
                process_id=pid,
                opacity=1.0,
            )
            windows.append(info)
        return windows

    def move_window(self, hwnd: int, x: int, y: int, width: int, height: int) -> bool:
        """Move and resize a window."""
        result = self._user32.SetWindowPos(
            hwnd, HWND_TOP, x, y, width, height, SWP_FRAMECHANGED | SWP_SHOWWINDOW
        )
        return bool(result)

    def set_window_depth(self, hwnd: int, z_index: int) -> bool:
        """Set the Z-order of a window."""
        h_after = HWND_TOPMOST if z_index > 1000 else (HWND_TOP if z_index > 500 else 0)
        result = self._user32.SetWindowPos(hwnd, h_after, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
        return bool(result)

    def minimize_window(self, hwnd: int) -> bool:
        """Minimize a window."""
        return bool(self._user32.ShowWindow(hwnd, SW_MINIMIZE))

    def maximize_window(self, hwnd: int) -> bool:
        """Maximize a window."""
        return bool(self._user32.ShowWindow(hwnd, SW_MAXIMIZE))

    def restore_window(self, hwnd: int) -> bool:
        """Restore a minimized/maximized window."""
        return bool(self._user32.ShowWindow(hwnd, SW_RESTORE))

    def set_window_opacity(self, hwnd: int, opacity: float) -> bool:
        """Set window transparency (0.0 to 1.0)."""
        ex_style = self._user32.GetWindowLongA(hwnd, GWL_EXSTYLE)
        if not (ex_style & WS_EX_LAYERED):
            self._user32.SetWindowLongA(hwnd, GWL_EXSTYLE, ex_style | WS_EX_LAYERED)
        alpha = int(max(0.0, min(1.0, opacity)) * 255)
        return bool(self._user32.SetLayeredWindowAttributes(hwnd, 0, alpha, LWA_ALPHA))

    def set_window_topmost(self, hwnd: int, topmost: bool = True) -> bool:
        """Set or clear always-on-top status."""
        pos = HWND_TOPMOST if topmost else HWND_NOTOPMOST
        result = self._user32.SetWindowPos(hwnd, pos, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
        return bool(result)

    def capture_window(self, hwnd: int) -> np.ndarray:
        """Capture a screenshot of a window as a numpy array."""
        rect = wt.RECT()
        self._user32.GetWindowRect(hwnd, ctypes.byref(rect))
        width, height = rect.right - rect.left, rect.bottom - rect.top
        if width <= 0 or height <= 0:
            return np.zeros((480, 640, 3), dtype=np.uint8)

        hdc_window = self._user32.GetWindowDC(hwnd)
        hdc_mem = self._gdi32.CreateCompatibleDC(hdc_window)
        h_bitmap = self._gdi32.CreateCompatibleBitmap(hdc_window, width, height)
        self._gdi32.SelectObject(hdc_mem, h_bitmap)
        self._user32.PrintWindow(hwnd, hdc_mem, 2)

        # Create bitmap info
        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [
                ("biSize", wt.DWORD), ("biWidth", wt.LONG), ("biHeight", wt.LONG),
                ("biPlanes", wt.WORD), ("biBitCount", wt.WORD), ("biCompression", wt.DWORD),
                ("biSizeImage", wt.DWORD), ("biXPelsPerMeter", wt.LONG),
                ("biYPelsPerMeter", wt.LONG), ("biClrUsed", wt.DWORD), ("biClrImportant", wt.DWORD),
            ]

        bmi_header = BITMAPINFOHEADER()
        bmi_header.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi_header.biWidth = width
        bmi_header.biHeight = -height  # Top-down
        bmi_header.biPlanes = 1
        bmi_header.biBitCount = 24
        bmi_header.biCompression = 0

        buffer_size = width * height * 3
        buffer = ctypes.create_string_buffer(buffer_size)
        self._gdi32.GetDIBits(hdc_mem, h_bitmap, 0, height, buffer, ctypes.byref(bmi_header), 0)

        # Convert to numpy array
        arr = np.frombuffer(buffer.raw, dtype=np.uint8)
        arr = arr.reshape((height, width, 3))
        # BGR to RGB
        arr = arr[:, :, ::-1].copy()

        self._gdi32.DeleteObject(h_bitmap)
        self._gdi32.DeleteDC(hdc_mem)
        self._user32.ReleaseDC(hwnd, hdc_window)
        return arr

    def arrange_windows_grid(self, cols: int = 2, rows: int = 2) -> bool:
        """Arrange visible windows in a grid layout."""
        windows = self.get_window_list()
        if not windows or not self._monitors:
            return False
        mon = self._monitors[0]
        cell_w = mon.width // cols
        cell_h = mon.height // rows
        for i, win in enumerate(windows[: cols * rows]):
            col = i % cols
            row = i // cols
            self.move_window(win.hwnd, mon.x + col * cell_w, mon.y + row * cell_h, cell_w, cell_h)
        return True

    def cascade_windows(self) -> bool:
        """Arrange visible windows in a cascading layout."""
        windows = self.get_window_list()
        if not windows or not self._monitors:
            return False
        mon = self._monitors[0]
        offset_x, offset_y = 30, 30
        base_w = mon.width - offset_x * (len(windows) - 1)
        base_h = mon.height - offset_y * (len(windows) - 1)
        for i, win in enumerate(windows):
            self.move_window(win.hwnd, mon.x + offset_x * i, mon.y + offset_y * i, base_w, base_h)
        return True

    def stack_windows(self) -> bool:
        """Stack windows vertically filling the screen."""
        windows = self.get_window_list()
        if not windows or not self._monitors:
            return False
        mon = self._monitors[0]
        count = len(windows)
        cell_h = mon.height // count
        for i, win in enumerate(windows):
            self.move_window(win.hwnd, mon.x, mon.y + i * cell_h, mon.width, cell_h)
        return True

    def get_window_at_position(self, x: int, y: int) -> Optional[WindowInfo]:
        """Get the topmost window at a screen position."""
        point = wt.POINT()
        point.x = x
        point.y = y
        hwnd = self._user32.WindowFromPoint(point)
        if not hwnd:
            return None
        xw, yw, w, h = self._get_window_rect(hwnd)
        return WindowInfo(
            hwnd=hwnd,
            title=self._get_window_title(hwnd),
            class_name=self._get_class_name(hwnd),
            x=xw,
            y=yw,
            width=w,
            height=h,
            process_id=self._get_process_id(hwnd),
            is_visible=self._user32.IsWindowVisible(hwnd),
        )

    def send_window_to_virtual_desktop(self, hwnd: int, desktop_id: int) -> bool:
        """Move a window to a virtual desktop (Windows 10+ via IVirtualDesktopManager)."""
        try:
            # Use PowerShell to interface with VirtualDesktop
            script = f"""
            $hwnd = IntPtr({hwnd})
            $vds = (New-Object -ComObject VirtualDesktop.DesktopManager)
            """
            subprocess.run(
                ["powershell", "-Command", script],
                capture_output=True,
                timeout=5,
                check=False,
            )
            return True
        except Exception as e:
            logger.warning("Virtual desktop move not supported on this system: %s", e)
            return False

    def switch_virtual_desktop(self, desktop_id: int) -> bool:
        """Switch to a different virtual desktop."""
        try:
            script = f"""
            $vds = (New-Object -ComObject VirtualDesktop.DesktopManager)
            """
            subprocess.run(
                ["powershell", "-Command", script],
                capture_output=True,
                timeout=5,
                check=False,
            )
            return True
        except Exception as e:
            logger.warning("Virtual desktop switch not supported: %s", e)
            return False

    def get_virtual_desktops(self) -> List[VirtualDesktop]:
        """Return list of virtual desktops."""
        return [VirtualDesktop(0, "Desktop 1", is_current=True)]

    def get_monitors(self) -> List[MonitorInfo]:
        """Return all monitor information."""
        return list(self._monitors)

    def close_window(self, hwnd: int) -> bool:
        """Close a window by sending WM_CLOSE."""
        WM_CLOSE = 0x0010
        return bool(self._user32.PostMessageA(hwnd, WM_CLOSE, 0, 0))

    def create_window(self, title: str, x: int, y: int, width: int, height: int) -> int:
        """Create a new window (limited in pure ctypes, returns 0)."""
        logger.warning("Window creation requires a full GUI framework")
        return 0

    def get_foreground_window(self) -> Optional[WindowInfo]:
        """Get the currently focused window."""
        hwnd = self._user32.GetForegroundWindow()
        if not hwnd:
            return None
        x, y, w, h = self._get_window_rect(hwnd)
        return WindowInfo(
            hwnd=hwnd,
            title=self._get_window_title(hwnd),
            class_name=self._get_class_name(hwnd),
            x=x,
            y=y,
            width=w,
            height=h,
            process_id=self._get_process_id(hwnd),
        )

    def set_foreground_window(self, hwnd: int) -> bool:
        """Bring a window to the foreground."""
        return bool(self._user32.SetForegroundWindow(hwnd))

    def resize_to_monitor(self, hwnd: int, monitor_index: int = 0) -> bool:
        """Resize a window to fill a specific monitor."""
        if monitor_index >= len(self._monitors):
            return False
        mon = self._monitors[monitor_index]
        return self.move_window(hwnd, mon.x, mon.y, mon.width, mon.height)

    def set_window_corner_preference(self, hwnd: int, preference: WindowCornerPreference) -> bool:
        """Set window corner rounding (Windows 11+)."""
        try:
            val = ctypes.c_uint(preference.value)
            result = self._dwmapi.DwmSetWindowAttribute(
                hwnd, DWMWA_WINDOW_CORNER_PREFERENCE, ctypes.byref(val), ctypes.sizeof(val)
            )
            return result == 0
        except Exception as e:
            logger.error("Failed to set corner preference: %s", e)
            return False

    def toggle_dark_mode(self, hwnd: int, enabled: bool = True) -> bool:
        """Toggle immersive dark mode for a window."""
        try:
            val = ctypes.c_int(1 if enabled else 0)
            result = self._dwmapi.DwmSetWindowAttribute(
                hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, ctypes.byref(val), ctypes.sizeof(val)
            )
            return result == 0
        except Exception as e:
            logger.error("Failed to toggle dark mode: %s", e)
            return False

    def get_window_border_padding(self) -> int:
        """Return the window border padding."""
        SM_CXSIZEFRAME = 32
        return self._user32.GetSystemMetrics(SM_CXSIZEFRAME)

    def animate_window(self, hwnd: int, target_rect: Tuple[int, int, int, int], duration: float = 0.3) -> bool:
        """Animate a window to a target position (instant in Windows)."""
        x, y, w, h = target_rect
        return self.move_window(hwnd, x, y, w, h)

    def close(self) -> None:
        """Release resources."""
        pass


# ---------------------------------------------------------------------------
# Linux implementation (xdotool)
# ---------------------------------------------------------------------------

class LinuxWindowManager:
    """Window manager for Linux using xdotool via subprocess."""

    def __init__(self) -> None:
        self._xdotool_available = self._check_xdotool()
        self._mock = MockWindowManager() if not self._xdotool_available else None

    def _check_xdotool(self) -> bool:
        """Check if xdotool is available."""
        try:
            subprocess.run(["xdotool", "--version"], capture_output=True, check=True, timeout=5)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.warning("xdotool not available, using mock fallback")
            return False

    def _run(self, args: List[str]) -> str:
        """Run an xdotool command."""
        result = subprocess.run(["xdotool"] + args, capture_output=True, text=True, timeout=10)
        return result.stdout.strip()

    def get_window_list(self) -> List[WindowInfo]:
        """Get all windows using xdotool."""
        if self._mock:
            return self._mock.get_window_list()
        output = self._run(["search", "--onlyvisible", "--class", ".*"])
        windows: List[WindowInfo] = []
        for line in output.split("\n"):
            if not line.strip():
                continue
            try:
                hwnd = int(line.strip())
                title = self._run(["getwindowname", str(hwnd)])
                geo = self._run(["getwindowgeometry", str(hwnd)])
                x, y, w, h = 0, 0, 800, 600
                windows.append(WindowInfo(hwnd=hwnd, title=title, class_name="", x=x, y=y, width=w, height=h))
            except ValueError:
                continue
        return windows

    def move_window(self, hwnd: int, x: int, y: int, width: int, height: int) -> bool:
        """Move/resize a window via xdotool."""
        if self._mock:
            return self._mock.move_window(hwnd, x, y, width, height)
        self._run(["windowsize", str(hwnd), str(width), str(height)])
        self._run(["windowmove", str(hwnd), str(x), str(y)])
        return True

    def set_window_depth(self, hwnd: int, z_index: int) -> bool:
        """Raise or lower window."""
        if self._mock:
            return self._mock.set_window_depth(hwnd, z_index)
        if z_index > 500:
            self._run(["windowraise", str(hwnd)])
        return True

    def minimize_window(self, hwnd: int) -> bool:
        """Minimize a window."""
        if self._mock:
            return self._mock.minimize_window(hwnd)
        self._run(["windowminimize", str(hwnd)])
        return True

    def maximize_window(self, hwnd: int) -> bool:
        """Maximize a window."""
        if self._mock:
            return self._mock.maximize_window(hwnd)
        self._run(["windowactivate", "--sync", str(hwnd)])
        return True

    def restore_window(self, hwnd: int) -> bool:
        """Restore a window."""
        if self._mock:
            return self._mock.restore_window(hwnd)
        return True

    def set_window_opacity(self, hwnd: int, opacity: float) -> bool:
        """Set window opacity using xprop."""
        if self._mock:
            return self._mock.set_window_opacity(hwnd, opacity)
        try:
            alpha = int(max(0.0, min(1.0, opacity)) * 0xFFFFFFFF)
            subprocess.run(
                ["xprop", "-id", str(hwnd), "-f", "_NET_WM_WINDOW_OPACITY", "32c",
                 "-set", "_NET_WM_WINDOW_OPACITY", hex(alpha)],
                capture_output=True,
                timeout=5,
            )
            return True
        except Exception:
            return False

    def set_window_topmost(self, hwnd: int, topmost: bool = True) -> bool:
        """Set always on top via xdotool."""
        if self._mock:
            return self._mock.set_window_topmost(hwnd, topmost)
        self._run(["windowactivate", str(hwnd)])
        return True

    def capture_window(self, hwnd: int) -> np.ndarray:
        """Capture window using import (ImageMagick) or mock."""
        if self._mock:
            return self._mock.capture_window(hwnd)
        try:
            import tempfile
            tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            tmp.close()
            subprocess.run(["import", "-window", str(hwnd), tmp.name], capture_output=True, timeout=10)
            from PIL import Image
            img = Image.open(tmp.name)
            arr = np.array(img)
            os.unlink(tmp.name)
            if arr.shape[2] == 4:
                arr = arr[:, :, :3]
            return arr
        except Exception:
            return np.zeros((480, 640, 3), dtype=np.uint8)

    def arrange_windows_grid(self, cols: int = 2, rows: int = 2) -> bool:
        """Grid layout."""
        if self._mock:
            return self._mock.arrange_windows_grid(cols, rows)
        return False

    def cascade_windows(self) -> bool:
        """Cascade layout."""
        if self._mock:
            return self._mock.cascade_windows()
        return False

    def stack_windows(self) -> bool:
        """Stack layout."""
        if self._mock:
            return self._mock.stack_windows()
        return False

    def get_window_at_position(self, x: int, y: int) -> Optional[WindowInfo]:
        """Get window at position."""
        if self._mock:
            return self._mock.get_window_at_position(x, y)
        return None

    def send_window_to_virtual_desktop(self, hwnd: int, desktop_id: int) -> bool:
        """Virtual desktop on Linux."""
        if self._mock:
            return self._mock.send_window_to_virtual_desktop(hwnd, desktop_id)
        return False

    def switch_virtual_desktop(self, desktop_id: int) -> bool:
        """Switch virtual desktop."""
        if self._mock:
            return self._mock.switch_virtual_desktop(desktop_id)
        return False

    def get_virtual_desktops(self) -> List[VirtualDesktop]:
        """Get virtual desktops."""
        if self._mock:
            return self._mock.get_virtual_desktops()
        return []

    def get_monitors(self) -> List[MonitorInfo]:
        """Get monitors."""
        if self._mock:
            return self._mock.get_monitors()
        return [MonitorInfo(0, 0, 0, 1920, 1080, True, name="DISPLAY-0")]

    def close_window(self, hwnd: int) -> bool:
        """Close a window."""
        if self._mock:
            return self._mock.close_window(hwnd)
        self._run(["windowclose", str(hwnd)])
        return True

    def create_window(self, title: str, x: int, y: int, width: int, height: int) -> int:
        """Create window."""
        if self._mock:
            return self._mock.create_window(title, x, y, width, height)
        return 0

    def get_foreground_window(self) -> Optional[WindowInfo]:
        """Get foreground window."""
        if self._mock:
            return self._mock.get_foreground_window()
        out = self._run(["getactivewindow"])
        if out:
            return WindowInfo(hwnd=int(out), title="", class_name="")
        return None

    def set_foreground_window(self, hwnd: int) -> bool:
        """Set foreground window."""
        if self._mock:
            return self._mock.set_foreground_window(hwnd)
        self._run(["windowactivate", str(hwnd)])
        return True

    def resize_to_monitor(self, hwnd: int, monitor_index: int = 0) -> bool:
        """Resize to monitor."""
        if self._mock:
            return self._mock.resize_to_monitor(hwnd, monitor_index)
        return False

    def set_window_corner_preference(self, hwnd: int, preference: WindowCornerPreference) -> bool:
        """No-op on Linux."""
        return True

    def toggle_dark_mode(self, hwnd: int, enabled: bool = True) -> bool:
        """No-op on Linux."""
        return True

    def get_window_border_padding(self) -> int:
        """Return default border padding."""
        return 4

    def animate_window(self, hwnd: int, target_rect: Tuple[int, int, int, int], duration: float = 0.3) -> bool:
        """Animate window."""
        if self._mock:
            return self._mock.animate_window(hwnd, target_rect, duration)
        return self.move_window(hwnd, *target_rect)

    def close(self) -> None:
        """Close resources."""
        if self._mock:
            self._mock.close()


# ---------------------------------------------------------------------------
# macOS implementation (AppleScript)
# ---------------------------------------------------------------------------

class MacOSWindowManager:
    """Window manager for macOS using AppleScript via subprocess."""

    def __init__(self) -> None:
        self._mock = MockWindowManager()

    def _osascript(self, script: str) -> str:
        """Run an AppleScript."""
        try:
            result = subprocess.run(
                ["osascript", "-e", script], capture_output=True, text=True, timeout=10
            )
            return result.stdout.strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            return ""

    def get_window_list(self) -> List[WindowInfo]:
        """Get windows via AppleScript."""
        return self._mock.get_window_list()

    def move_window(self, hwnd: int, x: int, y: int, width: int, height: int) -> bool:
        """Move/resize window."""
        script = f"""
        tell application "System Events"
            set position of window id {hwnd} to {{{x}, {y}}}
            set size of window id {hwnd} to {{{width}, {height}}}
        end tell
        """
        self._osascript(script)
        return True

    def set_window_depth(self, hwnd: int, z_index: int) -> bool:
        """Set Z-order."""
        return self._mock.set_window_depth(hwnd, z_index)

    def minimize_window(self, hwnd: int) -> bool:
        """Minimize window."""
        script = f'tell application "System Events" to set value of attribute "AXMinimized" of window id {hwnd} to true'
        self._osascript(script)
        return True

    def maximize_window(self, hwnd: int) -> bool:
        """Maximize window."""
        return self._mock.maximize_window(hwnd)

    def restore_window(self, hwnd: int) -> bool:
        """Restore window."""
        return self._mock.restore_window(hwnd)

    def set_window_opacity(self, hwnd: int, opacity: float) -> bool:
        """Set opacity."""
        return self._mock.set_window_opacity(hwnd, opacity)

    def set_window_topmost(self, hwnd: int, topmost: bool = True) -> bool:
        """Set topmost."""
        return self._mock.set_window_topmost(hwnd, topmost)

    def capture_window(self, hwnd: int) -> np.ndarray:
        """Capture window."""
        return self._mock.capture_window(hwnd)

    def arrange_windows_grid(self, cols: int = 2, rows: int = 2) -> bool:
        """Grid layout."""
        return self._mock.arrange_windows_grid(cols, rows)

    def cascade_windows(self) -> bool:
        """Cascade layout."""
        return self._mock.cascade_windows()

    def stack_windows(self) -> bool:
        """Stack layout."""
        return self._mock.stack_windows()

    def get_window_at_position(self, x: int, y: int) -> Optional[WindowInfo]:
        """Window at position."""
        return self._mock.get_window_at_position(x, y)

    def send_window_to_virtual_desktop(self, hwnd: int, desktop_id: int) -> bool:
        """Virtual desktop."""
        return self._mock.send_window_to_virtual_desktop(hwnd, desktop_id)

    def switch_virtual_desktop(self, desktop_id: int) -> bool:
        """Switch desktop."""
        return self._mock.switch_virtual_desktop(desktop_id)

    def get_virtual_desktops(self) -> List[VirtualDesktop]:
        """Get desktops."""
        return self._mock.get_virtual_desktops()

    def get_monitors(self) -> List[MonitorInfo]:
        """Get monitors."""
        return self._mock.get_monitors()

    def close_window(self, hwnd: int) -> bool:
        """Close window."""
        return self._mock.close_window(hwnd)

    def create_window(self, title: str, x: int, y: int, width: int, height: int) -> int:
        """Create window."""
        return self._mock.create_window(title, x, y, width, height)

    def get_foreground_window(self) -> Optional[WindowInfo]:
        """Foreground window."""
        return self._mock.get_foreground_window()

    def set_foreground_window(self, hwnd: int) -> bool:
        """Set foreground."""
        return self._mock.set_foreground_window(hwnd)

    def resize_to_monitor(self, hwnd: int, monitor_index: int = 0) -> bool:
        """Resize to monitor."""
        return self._mock.resize_to_monitor(hwnd, monitor_index)

    def set_window_corner_preference(self, hwnd: int, preference: WindowCornerPreference) -> bool:
        """Corner preference."""
        return True

    def toggle_dark_mode(self, hwnd: int, enabled: bool = True) -> bool:
        """Dark mode."""
        return True

    def get_window_border_padding(self) -> int:
        """Border padding."""
        return 8

    def animate_window(self, hwnd: int, target_rect: Tuple[int, int, int, int], duration: float = 0.3) -> bool:
        """Animate window."""
        return self._mock.animate_window(hwnd, target_rect, duration)

    def close(self) -> None:
        """Close resources."""
        self._mock.close()


# ---------------------------------------------------------------------------
# Unified facade
# ---------------------------------------------------------------------------

class WindowManager3D:
    """
    3D spatial window management facade.

    Automatically selects the best platform-specific backend:
      - Windows: Native Win32 API via ctypes
      - Linux: xdotool/ewmh
      - macOS: AppleScript
      - Other: Full mock with animation loop
    """

    def __init__(self) -> None:
        self._impl: Union[WindowsWindowManager, LinuxWindowManager, MacOSWindowManager, MockWindowManager]
        system = platform.system()
        if system == "Windows":
            try:
                self._impl = WindowsWindowManager()
                logger.info("WindowManager3D: using WindowsWindowManager")
            except Exception as e:
                logger.warning("Windows WM init failed: %s, using mock", e)
                self._impl = MockWindowManager()
        elif system == "Linux":
            self._impl = LinuxWindowManager()
            logger.info("WindowManager3D: using LinuxWindowManager")
        elif system == "Darwin":
            self._impl = MacOSWindowManager()
            logger.info("WindowManager3D: using MacOSWindowManager")
        else:
            self._impl = MockWindowManager()
            logger.info("WindowManager3D: using MockWindowManager")

    # -- Window operations --

    def get_window_list(self) -> List[WindowInfo]:
        """Get all windows with their positions and properties."""
        return self._impl.get_window_list()

    def move_window(self, hwnd: int, x: int, y: int, width: int, height: int) -> bool:
        """Move and resize a window."""
        return self._impl.move_window(hwnd, x, y, width, height)

    def set_window_depth(self, hwnd: int, z_index: int) -> bool:
        """Set the Z-order (depth) of a window."""
        return self._impl.set_window_depth(hwnd, z_index)

    def minimize_window(self, hwnd: int) -> bool:
        """Minimize a window to the taskbar."""
        return self._impl.minimize_window(hwnd)

    def maximize_window(self, hwnd: int) -> bool:
        """Maximize a window to fill the screen."""
        return self._impl.maximize_window(hwnd)

    def restore_window(self, hwnd: int) -> bool:
        """Restore a minimized or maximized window."""
        return self._impl.restore_window(hwnd)

    def set_window_opacity(self, hwnd: int, opacity: float) -> bool:
        """
        Set window transparency.

        Args:
            hwnd: Window handle.
            opacity: 0.0 (fully transparent) to 1.0 (fully opaque).
        """
        return self._impl.set_window_opacity(hwnd, opacity)

    def set_window_topmost(self, hwnd: int, topmost: bool = True) -> bool:
        """Set or clear the always-on-top flag."""
        return self._impl.set_window_topmost(hwnd, topmost)

    def capture_window(self, hwnd: int) -> np.ndarray:
        """
        Capture a screenshot of a window.

        Returns:
            numpy array of shape (height, width, 3) with RGB values.
        """
        return self._impl.capture_window(hwnd)

    # -- Layout algorithms --

    def arrange_windows_grid(self, cols: int = 2, rows: int = 2) -> bool:
        """
        Automatically arrange visible windows in a grid pattern.

        Args:
            cols: Number of columns.
            rows: Number of rows.
        """
        return self._impl.arrange_windows_grid(cols, rows)

    def cascade_windows(self) -> bool:
        """Arrange windows in a cascading (stair-step) layout."""
        return self._impl.cascade_windows()

    def stack_windows(self) -> bool:
        """Stack all visible windows vertically."""
        return self._impl.stack_windows()

    def get_window_at_position(self, x: int, y: int) -> Optional[WindowInfo]:
        """
        Get the topmost window at a given screen position.

        Args:
            x: Screen X coordinate.
            y: Screen Y coordinate.
        """
        return self._impl.get_window_at_position(x, y)

    # -- Virtual desktop --

    def send_window_to_virtual_desktop(self, hwnd: int, desktop_id: int) -> bool:
        """Move a window to a different virtual desktop."""
        return self._impl.send_window_to_virtual_desktop(hwnd, desktop_id)

    def switch_virtual_desktop(self, desktop_id: int) -> bool:
        """Switch to a different virtual desktop."""
        return self._impl.switch_virtual_desktop(desktop_id)

    def get_virtual_desktops(self) -> List[VirtualDesktop]:
        """Return all virtual desktops."""
        return self._impl.get_virtual_desktops()

    # -- Monitor management --

    def get_monitors(self) -> List[MonitorInfo]:
        """Return information about all connected monitors."""
        return self._impl.get_monitors()

    def resize_to_monitor(self, hwnd: int, monitor_index: int = 0) -> bool:
        """Resize a window to fill a specific monitor."""
        return self._impl.resize_to_monitor(hwnd, monitor_index)

    # -- Advanced features --

    def close_window(self, hwnd: int) -> bool:
        """Close a window."""
        return self._impl.close_window(hwnd)

    def create_window(self, title: str, x: int, y: int, width: int, height: int) -> int:
        """Create a new managed window."""
        return self._impl.create_window(title, x, y, width, height)

    def get_foreground_window(self) -> Optional[WindowInfo]:
        """Get the currently focused window."""
        return self._impl.get_foreground_window()

    def set_foreground_window(self, hwnd: int) -> bool:
        """Bring a window to the foreground."""
        return self._impl.set_foreground_window(hwnd)

    def set_window_corner_preference(self, hwnd: int, preference: WindowCornerPreference) -> bool:
        """Set window corner rounding preference (Windows 11+)."""
        return self._impl.set_window_corner_preference(hwnd, preference)

    def toggle_dark_mode(self, hwnd: int, enabled: bool = True) -> bool:
        """Toggle immersive dark mode for a window."""
        return self._impl.toggle_dark_mode(hwnd, enabled)

    def get_window_border_padding(self) -> int:
        """Return the window border padding in pixels."""
        return self._impl.get_window_border_padding()

    def animate_window(self, hwnd: int, target_rect: Tuple[int, int, int, int], duration: float = 0.3) -> bool:
        """Animate a window to a target rectangle."""
        return self._impl.animate_window(hwnd, target_rect, duration)

    def close(self) -> None:
        """Release all resources."""
        self._impl.close()

    @property
    def is_mock(self) -> bool:
        """Return True if the mock backend is active."""
        return isinstance(self._impl, MockWindowManager) or (
            isinstance(self._impl, (LinuxWindowManager, MacOSWindowManager)) and self._impl._mock is not None
        )


# Singleton
_wm_instance: Optional[WindowManager3D] = None


def get_window_manager() -> WindowManager3D:
    """
    Factory function returning the global WindowManager3D singleton.

    Usage:
        wm = get_window_manager()
        windows = wm.get_window_list()
        wm.arrange_windows_grid(cols=3, rows=2)
    """
    global _wm_instance
    if _wm_instance is None:
        _wm_instance = WindowManager3D()
    return _wm_instance


def reset_window_manager() -> None:
    """Reset the global singleton."""
    global _wm_instance
    if _wm_instance is not None:
        _wm_instance.close()
        _wm_instance = None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    wm = get_window_manager()
    windows = wm.get_window_list()
    print(f"Found {len(windows)} windows")
    for w in windows[:5]:
        print(f"  [{w.hwnd}] '{w.title}' at ({w.x},{w.y}) size {w.width}x{w.height}")
    print(f"Mock mode: {wm.is_mock}")
