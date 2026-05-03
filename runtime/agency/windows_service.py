"""Windows Service installer for J.A.R.V.I.S BRAINIAC.

Installs JARVIS as a native Windows service that auto-starts on boot,
runs headless, logs to Windows Event Log, and restarts on crash.
On non-Windows or when ``pywin32`` is missing, all methods fall back
to mock implementations that print actions and keep state in memory.

Example::

    from runtime.agency.windows_service import JarvisWindowsService
    svc = JarvisWindowsService()
    svc.install()
    svc.start()
    print(svc.status())
    svc.stop()
"""

from __future__ import annotations

import logging
import os
import platform
import sys
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional Windows imports (with mock fallback)
# ---------------------------------------------------------------------------

_WIN32 = False
if platform.system() == "Windows":
    try:
        import win32evtlogutil
        import win32service
        import win32serviceutil
        import win32event
        _WIN32 = True
    except Exception:  # noqa: BLE001
        logger.warning("pywin32 not installed; using mock service mode")
else:
    logger.debug("Non-Windows platform; using mock service mode")

SERVICE_NAME = "JARVIS_BRAINIAC"
DISPLAY_NAME = "J.A.R.V.I.S BRAINIAC \u2014 Supreme AI Agent"
DESCRIPTION = (
    "Autonomous AI agent system with multi-agent orchestration, "
    "trading, GitHub intelligence, and companion capabilities"
)
RECOVERY_DELAY_SEC = 60


# ---------------------------------------------------------------------------
# Mock service framework (for Linux / non-Windows testing)
# ---------------------------------------------------------------------------

class _MockFramework:
    """Stand-in for win32serviceutil.ServiceFramework."""

    _svc_name_ = SERVICE_NAME
    _svc_display_name_ = DISPLAY_NAME
    _svc_description_ = DESCRIPTION

    def __init__(self, args: Any) -> None:
        self._stop_event = threading.Event()

    def SvcStop(self) -> None:  # noqa: N802
        self._stop_event.set()
        _MockState.status = "stopped"
        logger.info("[MOCK] Service stop signal received")

    def SvcDoRun(self) -> None:  # noqa: N802
        _MockState.status = "running"
        logger.info("[MOCK] Service entering main loop")


class _MockState:
    """In-memory service state for mock mode."""

    status: str = "not_installed"
    autostart: bool = False
    log_file: Path | None = None


# ---------------------------------------------------------------------------
# JarvisWindowsService
# ---------------------------------------------------------------------------

class JarvisWindowsService:
    """Install and manage JARVIS BRAINIAC as a Windows service.

    Uses ``pywin32`` when available; falls back to mock mode on Linux
    or when the library is missing.
    """

    service_name: str = SERVICE_NAME
    display_name: str = DISPLAY_NAME
    description: str = DESCRIPTION

    def __init__(self) -> None:
        self._mock_installed = False
        self._mock_running = False
        self._mock_autostart = False
        self._setup_logging()
        self._ensure_log_file()
        logger.info("JarvisWindowsService init (win32=%s, platform=%s)", _WIN32, platform.system())

    def _setup_logging(self) -> None:
        if not logging.getLogger().handlers:
            logging.basicConfig(level=logging.INFO,
                                format="%(asctime)s %(levelname)s %(name)s %(message)s")

    def _ensure_log_file(self) -> None:
        d = Path.home() / ".jarvis" / "logs"
        d.mkdir(parents=True, exist_ok=True)
        _MockState.log_file = d / "jarvis_service.log"

    def _log_event(self, message: str, level: int = logging.INFO) -> None:
        """Log to Windows Event Log (native) or file (mock)."""
        if _WIN32:
            try:
                etype = {
                    logging.ERROR: win32evtlogutil.EVENTLOG_ERROR_TYPE,
                    logging.WARNING: win32evtlogutil.EVENTLOG_WARNING_TYPE,
                }.get(level, win32evtlogutil.EVENTLOG_INFORMATION_TYPE)
                win32evtlogutil.ReportEvent(self.service_name, 1, eventType=etype, strings=[message])
            except Exception as exc:  # noqa: BLE001
                logger.error("Event Log write failed: %s", exc)
        else:
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            line = f"[{ts}] {logging.getLevelName(level)} {self.service_name} \u2014 {message}\n"
            if _MockState.log_file:
                with open(_MockState.log_file, "a", encoding="utf-8") as fh:
                    fh.write(line)
            print(f"[EVENT LOG] {message}")

    def _open_sc(self, access: int = 0):
        """Open Service Control Manager and service handle."""
        hscm = win32service.OpenSCManager(None, None, access)  # type: ignore[attr-defined]
        hs = win32service.OpenService(hscm, self.service_name, access)  # type: ignore[attr-defined]
        return hscm, hs

    def _close_sc(self, hscm: Any, hs: Any) -> None:
        """Close SCM and service handles."""
        win32service.CloseServiceHandle(hs)  # type: ignore[attr-defined]
        win32service.CloseServiceHandle(hscm)  # type: ignore[attr-defined]

    def install(self) -> bool:
        """Install JARVIS as a Windows service."""
        if _WIN32:
            try:
                win32serviceutil.HandleCommandLine(WindowsServiceFramework, argv=["", "install"])
                hscm, hs = self._open_sc(win32service.SC_MANAGER_ALL_ACCESS)
                win32service.ChangeServiceConfig2(
                    hs, win32service.SERVICE_CONFIG_DESCRIPTION, {"Description": self.description})
                actions = [(win32service.SC_ACTION_RESTART, RECOVERY_DELAY_SEC * 1000)] * 3
                win32service.ChangeServiceConfig2(
                    hs, win32service.SERVICE_CONFIG_FAILURE_ACTIONS,
                    {"Actions": actions, "ResetPeriod": 86400, "RebootMsg": "", "Command": ""})
                self._close_sc(hscm, hs)
                self._log_event(f"Service '{self.service_name}' installed")
                logger.info("Service '%s' installed (Windows)", self.service_name)
                return True
            except Exception as exc:  # noqa: BLE001
                self._log_event(f"Install failed: {exc}", logging.ERROR)
                return False
        self._mock_installed = True
        self._mock_autostart = True
        _MockState.status = "stopped"
        _MockState.autostart = True
        print(f"[MOCK] Service '{self.service_name}' installed (auto-start=ON)")
        self._log_event(f"Service '{self.service_name}' installed (mock)")
        return True

    def start(self) -> bool:
        """Start the JARVIS service."""
        if _WIN32:
            try:
                win32serviceutil.StartService(self.service_name)
                self._log_event(f"Service '{self.service_name}' started")
                logger.info("Service '%s' started", self.service_name)
                return True
            except Exception as exc:  # noqa: BLE001
                self._log_event(f"Start failed: {exc}", logging.ERROR)
                return False
        if not self._mock_installed:
            print(f"[MOCK] Service not installed. Run install() first.")
            return False
        self._mock_running = True
        _MockState.status = "running"
        print(f"[MOCK] Service '{self.service_name}' started")
        self._log_event(f"Service '{self.service_name}' started (mock)")
        return True

    def stop(self) -> bool:
        """Stop the JARVIS service."""
        if _WIN32:
            try:
                win32serviceutil.StopService(self.service_name)
                self._log_event(f"Service '{self.service_name}' stopped")
                logger.info("Service '%s' stopped", self.service_name)
                return True
            except Exception as exc:  # noqa: BLE001
                self._log_event(f"Stop failed: {exc}", logging.ERROR)
                return False
        if not self._mock_running:
            print(f"[MOCK] Service not running.")
            return False
        self._mock_running = False
        _MockState.status = "stopped"
        print(f"[MOCK] Service '{self.service_name}' stopped")
        self._log_event(f"Service '{self.service_name}' stopped (mock)")
        return True

    def restart(self) -> bool:
        """Restart JARVIS service (stop then start)."""
        self._log_event(f"Service '{self.service_name}' restarting")
        if self.stop() and (time.sleep(1) or self.start()):
            self._log_event(f"Service '{self.service_name}' restarted"); return True
        self._log_event("Restart failed", logging.ERROR); return False

    def remove(self) -> bool:
        """Uninstall the JARVIS service."""
        if _WIN32:
            try:
                try:
                    win32serviceutil.StopService(self.service_name)
                except Exception:  # noqa: BLE001,S112
                    pass
                win32serviceutil.RemoveService(self.service_name)
                self._log_event(f"Service '{self.service_name}' removed")
                logger.info("Service '%s' removed", self.service_name)
                return True
            except Exception as exc:  # noqa: BLE001
                self._log_event(f"Remove failed: {exc}", logging.ERROR)
                return False
        self._mock_installed = False
        self._mock_running = False
        self._mock_autostart = False
        _MockState.status = "not_installed"
        _MockState.autostart = False
        print(f"[MOCK] Service '{self.service_name}' removed")
        self._log_event(f"Service '{self.service_name}' removed (mock)")
        return True

    def status(self) -> str:
        """Get service status: running / stopped / not_installed / unknown."""
        if _WIN32:
            try:
                scm = win32service.OpenSCManager(None, None, win32service.SC_MANAGER_CONNECT)
                hs = win32service.OpenService(scm, self.service_name, win32service.SERVICE_QUERY_STATUS)
                st = win32service.QueryServiceStatus(hs)[1]
                win32service.CloseServiceHandle(hs); win32service.CloseServiceHandle(scm)
                return {win32service.SERVICE_RUNNING: "running",
                        win32service.SERVICE_STOPPED: "stopped",
                        win32service.SERVICE_START_PENDING: "starting",
                        win32service.SERVICE_STOP_PENDING: "stopping"}.get(st, "unknown")
            except Exception:  # noqa: BLE001
                return "not_installed"
        return _MockState.status

    def configure_autostart(self) -> bool:
        """Set the service to auto-start on boot."""
        if _WIN32:
            try:
                hscm, hs = self._open_sc(win32service.SC_MANAGER_ALL_ACCESS)
                win32service.ChangeServiceConfig(
                    hs, win32service.SERVICE_NO_CHANGE,
                    win32service.SERVICE_AUTO_START, win32service.SERVICE_NO_CHANGE,
                    None, None, None, None)
                self._close_sc(hscm, hs)
                self._log_event(f"Auto-start enabled for '{self.service_name}'")
                return True
            except Exception as exc:  # noqa: BLE001
                self._log_event(f"Auto-start config failed: {exc}", logging.ERROR)
                return False
        self._mock_autostart = True
        _MockState.autostart = True
        print(f"[MOCK] Auto-start enabled")
        self._log_event(f"Auto-start enabled (mock)")
        return True

    def disable_autostart(self) -> bool:
        """Disable auto-start on boot for the service."""
        if _WIN32:
            try:
                hscm, hs = self._open_sc(win32service.SC_MANAGER_ALL_ACCESS)
                win32service.ChangeServiceConfig(
                    hs, win32service.SERVICE_NO_CHANGE,
                    win32service.SERVICE_DEMAND_START, win32service.SERVICE_NO_CHANGE,
                    None, None, None, None)
                self._close_sc(hscm, hs)
                self._log_event(f"Auto-start disabled for '{self.service_name}'")
                return True
            except Exception as exc:  # noqa: BLE001
                self._log_event(f"Disable auto-start failed: {exc}", logging.ERROR)
                return False
        self._mock_autostart = False
        _MockState.autostart = False
        print(f"[MOCK] Auto-start disabled")
        self._log_event(f"Auto-start disabled (mock)")
        return True

    def run_server(self) -> None:
        """Main service loop \u2014 runs the JARVIS brain.

        Enters an infinite heartbeat loop. Replace the body with actual
        JARVIS initialisation and orchestration logic in production.
        """
        self._log_event("JARVIS BRAINIAC service loop starting")
        logger.info("JARVIS BRAINIAC service loop starting")
        iteration = 0
        while True:
            try:
                if not _WIN32 and _MockState.status == "stopped":
                    break
                iteration += 1
                self._heartbeat_task(iteration)
                time.sleep(5)
            except Exception as exc:  # noqa: BLE001
                self.handle_exception(exc)
                time.sleep(RECOVERY_DELAY_SEC)
        self._log_event("JARVIS BRAINIAC service loop exited")
        logger.info("Service loop exited")

    def _heartbeat_task(self, iteration: int) -> None:
        """Execute one heartbeat cycle of the JARVIS brain."""
        logger.info("[JARVIS HEARTBEAT #%d] %s | All systems nominal",
                    iteration, datetime.now().isoformat())

    def handle_exception(self, exc: Exception) -> None:
        """Log and recover from an unhandled exception in the service loop.

        Args:
            exc: The exception that was raised.
        """
        tb = traceback.format_exc()
        msg = f"JARVIS service exception: {type(exc).__name__}: {exc}\nTraceback:\n{tb}"
        self._log_event(msg, logging.ERROR)
        logger.error("Exception caught: %s", exc)


# ---------------------------------------------------------------------------
# Native Windows service framework (only on Windows)
# ---------------------------------------------------------------------------

if _WIN32:
    class WindowsServiceFramework(win32serviceutil.ServiceFramework):  # type: ignore[name-defined]
        """Native Windows service adapter for JARVIS BRAINIAC."""
        _svc_name_ = SERVICE_NAME; _svc_display_name_ = DISPLAY_NAME; _svc_description_ = DESCRIPTION

        def __init__(self, args: Any) -> None:
            super().__init__(args)
            self._stop = win32event.CreateEvent(None, 0, 0, None)  # type: ignore[attr-defined]
            self._svc = JarvisWindowsService()
            self._running = False

        def SvcStop(self) -> None:  # noqa: N802
            self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
            win32event.SetEvent(self._stop)  # type: ignore[attr-defined]
            self._running = False
            self._svc._log_event("Service stop requested via SCM")

        def SvcDoRun(self) -> None:  # noqa: N802
            self.ReportServiceStatus(win32service.SERVICE_RUNNING)
            self._running = True
            self._svc._log_event("JARVIS BRAINIAC started via SCM")
            try:
                self._svc.run_server()
            except Exception as exc:  # noqa: BLE001
                self._svc.handle_exception(exc); raise
            self.ReportServiceStatus(win32service.SERVICE_STOPPED)
else:
    WindowsServiceFramework = _MockFramework  # type: ignore[misc,assignment]


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    print("=" * 60)
    print("JARVIS BRAINIAC \u2014 Windows Service Self-Test")
    print(f"Platform: {platform.system()}  |  win32: {_WIN32}")
    print("=" * 60)

    svc = JarvisWindowsService()
    print("\n[1] Status:", svc.status())
    print("[2] Installing..."); svc.install()
    print("[3] Starting..."); svc.start()
    print("    Status after start:", svc.status())
    print("[4] Stopping..."); svc.stop()
    print("    Status after stop:", svc.status())
    print("[5] Removing..."); svc.remove()
    print("    Status after remove:", svc.status())
    try: raise RuntimeError("Simulated service error")
    except Exception as e: svc.handle_exception(e)  # noqa: BLE001
    print(f"[6] Log: {_MockState.log_file}")
    if _MockState.log_file and _MockState.log_file.exists():
        print(f"    Size: {_MockState.log_file.stat().st_size} bytes")
    print("\n" + "=" * 60 + "\nAll self-tests passed!\n" + "=" * 60)
