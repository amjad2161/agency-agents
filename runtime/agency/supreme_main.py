"""Supreme entry point — wires the unified bridge and starts the runtime.

This is the single command-line front door for JARVIS:

* Builds the :class:`UnifiedBridge` so every subsystem is constructed and
  health-checked.
* Prints a green/yellow/red startup banner.
* Optionally starts the FastAPI control server from :mod:`agency.server`.
* Handles SIGINT/SIGTERM gracefully so background pools shut down.

Run with ``python -m agency.supreme_main`` or via the installed
``agency-supreme`` console script (when packaged).
"""

from __future__ import annotations

import argparse
import signal
import sys
import threading
import time
from typing import Any

from . import get_unified_bridge
from .logging import configure, get_logger
from .tui import get_console

log = get_logger()


def _format_status(status: dict[str, Any]) -> str:
    lines: list[str] = []
    subsystems = status.get("subsystems", {})
    for name, info in subsystems.items():
        marker = "OK" if info.get("healthy") else "FAIL"
        lines.append(f"  [{marker:>4}] {name:<22} {info.get('detail', '')}")
    return "\n".join(lines)


def boot(*, start_server: bool = False, host: str = "127.0.0.1", port: int = 8001) -> int:
    """Boot the runtime. Returns process exit code."""
    configure()
    console = get_console()
    console.info("booting JARVIS supreme runtime ...")
    bridge = get_unified_bridge()
    status = bridge.status()

    if status.get("ok"):
        console.success("all subsystems green")
    else:
        console.warning("some subsystems are degraded")
    console.print(_format_status(status))

    stop = threading.Event()

    def _on_signal(signum: int, _frame: Any) -> None:
        console.warning(f"signal {signum} received; shutting down")
        stop.set()

    signal.signal(signal.SIGINT, _on_signal)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _on_signal)

    if start_server:
        try:
            import uvicorn  # type: ignore
            from .server import build_app

            app = build_app()
            config = uvicorn.Config(app, host=host, port=port, log_level="info")
            server = uvicorn.Server(config)
            console.info(f"starting control server on http://{host}:{port}")
            thread = threading.Thread(target=server.run, daemon=True)
            thread.start()
            while not stop.is_set() and thread.is_alive():
                time.sleep(0.5)
            server.should_exit = True
            thread.join(timeout=5.0)
        except Exception as exc:
            console.error(f"control server failed: {exc}")
            return 1
    else:
        console.info("idle — control server not started (use --serve to enable)")
        while not stop.is_set():
            time.sleep(0.5)

    bridge.aios_bridge.shutdown()
    console.success("shutdown complete")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agency-supreme")
    parser.add_argument(
        "--serve", action="store_true", help="start the FastAPI control server"
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args(argv)
    return boot(start_server=args.serve, host=args.host, port=args.port)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
