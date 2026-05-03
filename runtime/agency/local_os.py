"""
OS Control module for JARVIS BRAINIAC.

Local OS control: mouse/keyboard automation, file ops, process management.
Trust-gated for safety. 100% local.
"""

from __future__ import annotations

import logging
import os
import platform
import shutil
import subprocess
import sys
import time
import typing as t
from pathlib import Path

logger = logging.getLogger(__name__)


# ─── Trust / safety constants ──────────────────────────────────────────────────

ALLOWLIST_CMDS = frozenset(
    {
        "echo",
        "cat",
        "ls",
        "pwd",
        "git",
        "python",
        "pytest",
        "dir",
        "type",
        "cd",
        "mkdir",
        "cp",
        "mv",
        "touch",
        "head",
        "tail",
        "grep",
        "find",
        "chmod",
        "chown",
        "wc",
        "sort",
        "uniq",
        "diff",
        "curl",
        "wget",
        "tar",
        "zip",
        "unzip",
        "df",
        "du",
        "ps",
        "top",
        "htop",
        "whoami",
        "date",
        "which",
        "file",
        "stat",
        "hostname",
        "uname",
        "pip",
        "npm",
        "node",
        "go",
        "rustc",
        "cargo",
    }
)

DENYLIST_PATTERNS = (
    "rm -rf",
    "rmdir /s /q",
    "format",
    "mkfs",
    "dd if=",
    "fdisk",
    "diskpart",
    ":(){ :|:& };:",
    "bomb",
    "del /f /s /q",
    "rd /s /q",
    "> /dev/sda",
    "> /dev/hda",
    "> /dev/nvme",
    "> /dev/mmcblk",
    "chmod -R 777 /",
    "chmod -R 000 /",
    "chown -R root /",
    "mkfs.ext",
    "mkfs.ntfs",
    "mkfs.fat",
    "wipefs",
    "shred -",
    "del /q /f /s",
    "rd /s /q c:\\",
)

RESTRICTED_PATHS = (
    "/etc",
    "/sys",
    "/proc",
    "/dev",
    "C:\\Windows",
    "C:\\Program Files",
    "C:\\Program Files (x86)",
    "/usr/bin",
    "/usr/sbin",
    "/bin",
    "/sbin",
    "/lib",
    "/lib64",
    "/boot",
    "/var/log",
)

TRUST_OFF = "OFF"
TRUST_ON_MY_MACHINE = "ON_MY_MACHINE"
TRUST_YOLO = "YOLO"


# ─── Safety helpers ────────────────────────────────────────────────────────────


def _check_restricted_path(path: str) -> None:
    """Raise RuntimeError if path points to a restricted system directory."""
    resolved = Path(path).resolve()
    for restricted in RESTRICTED_PATHS:
        rpath = Path(restricted).resolve()
        try:
            resolved.relative_to(rpath)
            raise RuntimeError(f"Access denied to restricted path: {path}")
        except ValueError:
            continue


def _validate_command(command: str) -> None:
    """Raise RuntimeError if command contains denied patterns."""
    lowered = command.lower()
    for pat in DENYLIST_PATTERNS:
        if pat.lower() in lowered:
            raise RuntimeError(f"Command denied by safety policy: {pat!r}")


def _get_command_binary(command: str) -> str:
    """Extract the binary name from a shell command (rough heuristic)."""
    stripped = command.strip()
    if not stripped:
        return ""
    # Handle quoted binaries and basic control characters
    first_token = stripped.split(";")[0].split("&&")[0].split("||")[0]
    first_token = first_token.strip().split()[0] if first_token else ""
    # Remove common shell prefixes
    for prefix in ("bash -c", "sh -c", "cmd /c", "cmd /k", "powershell -command", "pwsh -c"):
        if first_token.lower() == prefix.split()[0].lower():
            # Return the next meaningful token or just the first token
            parts = stripped.split()
            for i, p in enumerate(parts):
                if p.lower() == prefix.split()[0].lower() and i + 1 < len(parts):
                    return parts[i + 1].strip('"\'')
    return first_token.strip('"\'') if first_token else ""


# ─── LocalOSController ─────────────────────────────────────────────────────────


class LocalOSController:
    """
    Local OS control: mouse/keyboard automation, file ops, process management.
    Trust-gated for safety. 100% local.
    """

    def __init__(self, trust_mode: str = TRUST_ON_MY_MACHINE) -> None:
        self.trust_mode = trust_mode
        self._pyautogui: t.Any = None
        self._ctypes: t.Any = None
        self._psutil: t.Any = None
        self._wmi: t.Any = None
        self._gpus: list = []
        self._ensure_libs()

    # ─── Lazy library loading ──────────────────────────────────────────────────

    def _ensure_libs(self) -> None:
        """Import optional heavy libs on first use to keep import fast."""
        if self.trust_mode == TRUST_OFF:
            return
        try:
            import pyautogui

            self._pyautogui = pyautogui
            self._pyautogui.FAILSAFE = True  # move mouse to corner to abort
        except Exception as exc:  # noqa: BLE001
            logger.debug("pyautogui not available: %s", exc)
        try:
            import ctypes

            self._ctypes = ctypes
        except Exception as exc:  # noqa: BLE001
            logger.debug("ctypes not available: %s", exc)
        try:
            import psutil

            self._psutil = psutil
        except Exception as exc:  # noqa: BLE001
            logger.debug("psutil not available: %s", exc)
        try:
            if platform.system() == "Windows":
                import wmi

                self._wmi = wmi.WMI()
        except Exception as exc:  # noqa: BLE001
            logger.debug("wmi not available: %s", exc)
        # GPU libs
        try:
            import GPUtil  # type: ignore[import-untyped]

            self._gpus = GPUtil.getGPUs()
        except Exception as exc:  # noqa: BLE001
            logger.debug("GPUtil not available: %s", exc)

    def _check_trust(self, action: str) -> None:
        if self.trust_mode == TRUST_OFF:
            raise RuntimeError(f"OS control is disabled (trust_mode=OFF). Action: {action}")
        if self.trust_mode == TRUST_YOLO:
            logger.warning("YOLO mode — executing %s without allowlist checks", action)
            return
        # ON_MY_MACHINE — proceed, individual methods enforce allowlist where needed

    # ─── Mouse / Keyboard ──────────────────────────────────────────────────────

    def move_mouse(self, x: int, y: int, duration: float = 0.5) -> None:
        """Move mouse to coordinates."""
        self._check_trust("move_mouse")
        if self._pyautogui:
            self._pyautogui.moveTo(x, y, duration=duration)
        elif self._ctypes and platform.system() == "Windows":
            # Windows native fallback
            self._ctypes.windll.user32.SetCursorPos(x, y)
        else:
            logger.warning("No mouse backend available (missing pyautogui/ctypes).")

    def click(self, x: int | None = None, y: int | None = None, button: str = "left") -> None:
        """Click at position (current if x,y not provided)."""
        self._check_trust("click")
        if x is not None and y is not None:
            self.move_mouse(x, y)
        if self._pyautogui:
            self._pyautogui.click(button=button)
        else:
            logger.warning("No click backend available (missing pyautogui).")

    def type_text(self, text: str, interval: float = 0.01) -> None:
        """Type text with optional interval between keystrokes.
        Hebrew / Unicode support via pyautogui.write (unicode) or ctypes fallback.
        """
        self._check_trust("type_text")
        if self._pyautogui:
            self._pyautogui.write(text, interval=interval)
        elif self._ctypes and platform.system() == "Windows":
            # Fallback: use SendInput for Unicode keystrokes
            self._send_unicode_keys_windows(text)
        else:
            logger.warning("No typing backend available (missing pyautogui).")

    def _send_unicode_keys_windows(self, text: str) -> None:
        """Send Unicode keystrokes via Windows SendInput (ctypes fallback)."""
        if self._ctypes is None:
            return
        INPUT_KEYBOARD = 1
        KEYEVENTF_UNICODE = 0x0004
        KEYEVENTF_KEYUP = 0x0002
        # Define minimal INPUT / KEYBDINPUT structures
        class KEYBDINPUT(t.Structure):  # type: ignore[valid-type,misc]
            _fields_ = [
                ("wVk", t.c_ushort),
                ("wScan", t.c_ushort),
                ("dwFlags", t.c_ulong),
                ("time", t.c_ulong),
                ("dwExtraInfo", t.c_ulonglong),
            ]

        class INPUT_I(t.Union):  # type: ignore[valid-type,misc]
            _fields_ = [("ki", KEYBDINPUT), ("mi", t.c_char * 32), ("hi", t.c_char * 32)]

        class INPUT(t.Structure):  # type: ignore[valid-type,misc]
            _fields_ = [("type", t.c_ulong), ("ii", INPUT_I)]

        user32 = self._ctypes.windll.user32
        for ch in text:
            inp = INPUT()
            inp.type = INPUT_KEYBOARD
            inp.ii.ki = KEYBDINPUT(0, ord(ch), KEYEVENTF_UNICODE, 0, 0)
            user32.SendInput(1, self._ctypes.byref(inp), self._ctypes.sizeof(INPUT))
            inp2 = INPUT()
            inp2.type = INPUT_KEYBOARD
            inp2.ii.ki = KEYBDINPUT(0, ord(ch), KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0, 0)
            user32.SendInput(1, self._ctypes.byref(inp2), self._ctypes.sizeof(INPUT))

    def press_key(self, key: str) -> None:
        """Press single key (Enter, Escape, F1, etc.)."""
        self._check_trust("press_key")
        if self._pyautogui:
            self._pyautogui.press(key)
        else:
            logger.warning("No keypress backend available (missing pyautogui).")

    # ─── Screenshot ────────────────────────────────────────────────────────────

    def take_screenshot(self, path: str | None = None) -> str:
        """Capture screenshot and return saved image path."""
        self._check_trust("take_screenshot")
        if path is None:
            path = f"/tmp/jarvis_screenshot_{int(time.time())}.png"
        # Ensure directory exists
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        if self._pyautogui:
            img = self._pyautogui.screenshot()
            img.save(path)
        else:
            # Fallback using PIL
            from PIL import ImageGrab  # type: ignore[import-untyped]

            img = ImageGrab.grab()
            img.save(path)
        return path

    # ─── Command execution ─────────────────────────────────────────────────────

    def run_command(
        self,
        command: str,
        shell: bool = True,
        timeout: int = 30,
    ) -> dict:
        """Execute shell command with trust validation.

        Returns {"stdout": "...", "stderr": "...", "returncode": 0}
        """
        self._check_trust("run_command")
        _validate_command(command)
        if self.trust_mode == TRUST_ON_MY_MACHINE:
            binary = _get_command_binary(command)
            if binary and binary not in ALLOWLIST_CMDS:
                raise RuntimeError(
                    f"Command binary '{binary}' not in allowlist. "
                    f"Allowed: {', '.join(sorted(ALLOWLIST_CMDS))}"
                )
        logger.info("Executing command: %s", command)
        result = subprocess.run(
            command,
            shell=shell,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=os.getcwd(),
        )
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }

    # ─── File operations ───────────────────────────────────────────────────────

    def read_file(self, path: str) -> str:
        """Read file contents. Validates path is not in restricted areas."""
        self._check_trust("read_file")
        _check_restricted_path(path)
        resolved = Path(path).resolve()
        if not resolved.exists():
            raise FileNotFoundError(f"File not found: {path}")
        if not resolved.is_file():
            raise ValueError(f"Not a file: {path}")
        # Prevent reading huge files
        size = resolved.stat().st_size
        if size > 50 * 1024 * 1024:  # 50 MB
            raise RuntimeError(f"File too large to read: {size} bytes")
        with open(resolved, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()

    def write_file(self, path: str, content: str) -> None:
        """Write content to file. Creates directories if needed."""
        self._check_trust("write_file")
        _check_restricted_path(path)
        resolved = Path(path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        with open(resolved, "w", encoding="utf-8") as f:
            f.write(content)

    def list_directory(self, path: str = ".") -> list[dict]:
        """List files in directory."""
        self._check_trust("list_directory")
        _check_restricted_path(path)
        resolved = Path(path).resolve()
        if not resolved.exists():
            raise FileNotFoundError(f"Directory not found: {path}")
        if not resolved.is_dir():
            raise ValueError(f"Not a directory: {path}")
        entries = []
        for entry in resolved.iterdir():
            stat = entry.stat()
            entries.append(
                {
                    "name": entry.name,
                    "path": str(entry),
                    "is_file": entry.is_file(),
                    "is_dir": entry.is_dir(),
                    "size": stat.st_size,
                    "modified": stat.st_mtime,
                }
            )
        return entries

    # ─── System info ───────────────────────────────────────────────────────────

    def get_system_info(self) -> dict:
        """Return OS, CPU, RAM, GPU, disk usage."""
        info: dict = {
            "os": platform.system(),
            "os_release": platform.release(),
            "os_version": platform.version(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "hostname": platform.node(),
            "python_version": sys.version,
        }
        # CPU
        if self._psutil:
            info["cpu_count_logical"] = self._psutil.cpu_count(logical=True)
            info["cpu_count_physical"] = self._psutil.cpu_count(logical=False)
            info["cpu_freq_mhz"] = (
                self._psutil.cpu_freq()._asdict() if self._psutil.cpu_freq() else {}
            )
        # RAM
        if self._psutil:
            vm = self._psutil.virtual_memory()._asdict()
            info["ram_total_mb"] = round(vm.get("total", 0) / (1024 * 1024), 2)
            info["ram_available_mb"] = round(vm.get("available", 0) / (1024 * 1024), 2)
        # Disk
        if self._psutil:
            disk = self._psutil.disk_usage("/")._asdict() if hasattr(self._psutil, "disk_usage") else {}
            info["disk_total_gb"] = round(disk.get("total", 0) / (1024**3), 2)
            info["disk_used_gb"] = round(disk.get("used", 0) / (1024**3), 2)
            info["disk_free_gb"] = round(disk.get("free", 0) / (1024**3), 2)
        # GPU
        if self._gpus:
            info["gpus"] = [
                {
                    "id": gpu.id,
                    "name": gpu.name,
                    "load": f"{gpu.load * 100:.1f}%" if gpu.load else "N/A",
                    "memory_used_mb": gpu.memoryUsed,
                    "memory_total_mb": gpu.memoryTotal,
                    "temperature_c": gpu.temperature,
                }
                for gpu in self._gpus
            ]
        elif self._wmi:
            try:
                gpus = self._wmi.Win32_VideoController()
                info["gpus"] = [{"name": g.Name} for g in gpus]
            except Exception as exc:  # noqa: BLE001
                info["gpus"] = [f"wmi error: {exc}"]
        else:
            info["gpus"] = []
        return info

    def monitor_resources(self) -> dict:
        """Return current CPU%, RAM%, GPU%, disk I/O."""
        data: dict = {"timestamp": time.time()}
        if self._psutil:
            data["cpu_percent"] = self._psutil.cpu_percent(interval=0.1)
            vm = self._psutil.virtual_memory()._asdict()
            data["ram_percent"] = vm.get("percent", 0)
            data["ram_used_mb"] = round(vm.get("used", 0) / (1024 * 1024), 2)
            data["ram_available_mb"] = round(vm.get("available", 0) / (1024 * 1024), 2)
            try:
                disk_io = self._psutil.disk_io_counters()._asdict()
                data["disk_read_mb"] = round(disk_io.get("read_bytes", 0) / (1024 * 1024), 2)
                data["disk_write_mb"] = round(disk_io.get("write_bytes", 0) / (1024 * 1024), 2)
            except Exception as exc:  # noqa: BLE001
                data["disk_io_error"] = str(exc)
        else:
            data["cpu_percent"] = None
            data["ram_percent"] = None
        if self._gpus:
            data["gpu_percent"] = [
                {
                    "id": gpu.id,
                    "name": gpu.name,
                    "load": f"{gpu.load * 100:.1f}%" if gpu.load else "N/A",
                    "memory_used_mb": gpu.memoryUsed,
                    "memory_total_mb": gpu.memoryTotal,
                }
                for gpu in self._gpus
            ]
        else:
            data["gpu_percent"] = []
        return data

    # ─── Process management ──────────────────────────────────────────────────

    def kill_process(self, pid: int) -> None:
        """Kill process by PID (with confirmation if trust_mode != YOLO)."""
        self._check_trust("kill_process")
        if self.trust_mode != TRUST_YOLO:
            # Require explicit confirmation in non-YOLO modes
            raise RuntimeError(
                f"kill_process requires YOLO trust_mode or manual confirmation. "
                f"Current trust_mode={self.trust_mode}. "
                f"Call with trust_mode='YOLO' only if you are absolutely sure."
            )
        if self._psutil:
            try:
                proc = self._psutil.Process(pid)
                proc.terminate()
                gone, alive = self._psutil.wait_procs([proc], timeout=3)
                if alive:
                    proc.kill()
            except self._psutil.NoSuchProcess:
                raise RuntimeError(f"No process with PID {pid}")
        else:
            # Fallback using os.kill
            try:
                os.kill(pid, 15)  # SIGTERM
                time.sleep(0.5)
                # Check if still alive
                os.kill(pid, 0)
                os.kill(pid, 9)  # SIGKILL
            except OSError:
                pass


# ─── MockOSController ──────────────────────────────────────────────────────────


class MockOSController:
    """
    Same interface as LocalOSController, but all operations are simulated.
    Logs actions instead of executing. Returns mock data.
    """

    def __init__(self, trust_mode: str = TRUST_ON_MY_MACHINE) -> None:
        self.trust_mode = trust_mode
        self._log: list[dict] = []
        self._mock_files: dict[str, str] = {}
        self._mock_dirs: dict[str, list[str]] = {".": ["mock_file.txt"]}
        self._mouse_pos = (0, 0)
        logger.info("MockOSController initialized (trust_mode=%s)", trust_mode)

    def _record(self, action: str, **kwargs: t.Any) -> None:
        entry = {"action": action, "timestamp": time.time(), **kwargs}
        self._log.append(entry)
        logger.info("[MOCK] %s: %s", action, kwargs)

    # ─── Mouse / Keyboard (mock) ─────────────────────────────────────────────

    def move_mouse(self, x: int, y: int, duration: float = 0.5) -> None:
        self._record("move_mouse", x=x, y=y, duration=duration)
        self._mouse_pos = (x, y)

    def click(self, x: int | None = None, y: int | None = None, button: str = "left") -> None:
        self._record("click", x=x, y=y, button=button)
        if x is not None and y is not None:
            self._mouse_pos = (x, y)

    def type_text(self, text: str, interval: float = 0.01) -> None:
        self._record("type_text", text_len=len(text), interval=interval)

    def press_key(self, key: str) -> None:
        self._record("press_key", key=key)

    # ─── Screenshot (mock) ───────────────────────────────────────────────────

    def take_screenshot(self, path: str | None = None) -> str:
        p = path or f"/tmp/jarvis_mock_screenshot_{int(time.time())}.png"
        self._record("take_screenshot", path=p)
        # Create a tiny dummy PNG
        try:
            from PIL import Image  # type: ignore[import-untyped]

            Path(p).parent.mkdir(parents=True, exist_ok=True)
            img = Image.new("RGB", (1, 1), color=(0, 0, 0))
            img.save(p)
        except Exception:
            Path(p).parent.mkdir(parents=True, exist_ok=True)
            with open(p, "wb") as f:
                f.write(b"\x89PNG\r\n\x1a\n")  # Minimal PNG header
        return p

    # ─── Command execution (mock) ────────────────────────────────────────────

    def run_command(self, command: str, shell: bool = True, timeout: int = 30) -> dict:
        self._record("run_command", command=command, shell=shell, timeout=timeout)
        return {
            "stdout": f"[MOCK] Executed: {command}",
            "stderr": "",
            "returncode": 0,
        }

    # ─── File operations (mock) ──────────────────────────────────────────────

    def read_file(self, path: str) -> str:
        self._record("read_file", path=path)
        if path in self._mock_files:
            return self._mock_files[path]
        return f"[MOCK] Contents of {path}\nLine 1\nLine 2\n"

    def write_file(self, path: str, content: str) -> None:
        self._record("write_file", path=path, content_len=len(content))
        self._mock_files[path] = content
        parent = str(Path(path).parent)
        self._mock_dirs.setdefault(parent, []).append(Path(path).name)

    def list_directory(self, path: str = ".") -> list[dict]:
        self._record("list_directory", path=path)
        files = self._mock_dirs.get(path, ["mock_a.txt", "mock_b.txt"])
        return [
            {
                "name": f,
                "path": str(Path(path) / f),
                "is_file": True,
                "is_dir": False,
                "size": 1024,
                "modified": time.time(),
            }
            for f in files
        ]

    # ─── System info (mock) ──────────────────────────────────────────────────

    def get_system_info(self) -> dict:
        self._record("get_system_info")
        return {
            "os": "MockOS",
            "os_release": "1.0",
            "os_version": "mock",
            "machine": "x86_64",
            "processor": "Mock CPU @ 3.00GHz",
            "hostname": "mock-host",
            "python_version": sys.version,
            "cpu_count_logical": 8,
            "cpu_count_physical": 4,
            "ram_total_mb": 16384.0,
            "ram_available_mb": 8192.0,
            "disk_total_gb": 512.0,
            "disk_used_gb": 256.0,
            "disk_free_gb": 256.0,
            "gpus": [{"name": "Mock GPU", "memory_total_mb": 4096}],
        }

    def monitor_resources(self) -> dict:
        self._record("monitor_resources")
        return {
            "timestamp": time.time(),
            "cpu_percent": 12.5,
            "ram_percent": 45.0,
            "ram_used_mb": 7372.8,
            "ram_available_mb": 8192.0,
            "disk_read_mb": 0.0,
            "disk_write_mb": 0.0,
            "gpu_percent": [
                {"id": 0, "name": "Mock GPU", "load": "12.5%", "memory_used_mb": 512, "memory_total_mb": 4096}
            ],
        }

    # ─── Process management (mock) ───────────────────────────────────────────

    def kill_process(self, pid: int) -> None:
        self._record("kill_process", pid=pid)
        logger.info("[MOCK] Process %d terminated (simulated)", pid)

    # ─── Utility ───────────────────────────────────────────────────────────────

    def get_log(self) -> list[dict]:
        """Return the full mock action log."""
        return self._log.copy()


# ─── Factory ───────────────────────────────────────────────────────────────────


def get_os_controller(trust_mode: str = TRUST_ON_MY_MACHINE, mock: bool = False) -> LocalOSController | MockOSController:
    """
    Factory returning an OS controller with trust validation.

    Parameters
    ----------
    trust_mode: str
        "OFF" | "ON_MY_MACHINE" | "YOLO"
    mock: bool
        If True, returns MockOSController regardless of trust_mode.

    Returns
    -------
    LocalOSController or MockOSController
    """
    if mock:
        return MockOSController(trust_mode=trust_mode)
    return LocalOSController(trust_mode=trust_mode)
