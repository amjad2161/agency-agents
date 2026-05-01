"""Network health and latency monitor.

Checks reachability and response latency for a configurable list of
hosts/URLs.  Uses only the standard library (socket + urllib) so no
additional dependencies are needed.

Tests should mock socket/urllib calls to avoid real network I/O.
"""

from __future__ import annotations

import socket
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any


_DEFAULT_TARGETS = ["8.8.8.8", "1.1.1.1"]
_ONLINE_CHECK_HOST = "8.8.8.8"
_ONLINE_CHECK_PORT = 53


class NetworkMonitor:
    """Check network health and measure latency."""

    def __init__(self, targets: list[str] | None = None) -> None:
        self.targets: list[str] = targets if targets is not None else list(_DEFAULT_TARGETS)

    # ------------------------------------------------------------------
    # Ping / TCP connect
    # ------------------------------------------------------------------

    def ping(self, host: str, timeout_s: float = 2.0) -> dict[str, Any]:
        """Try a TCP connection to *host* on port 80 (ICMP requires root).

        Returns::

            {host: str, reachable: bool, latency_ms: float | None}
        """
        t0 = time.monotonic()
        try:
            with socket.create_connection((host, 80), timeout=timeout_s):
                latency_ms = (time.monotonic() - t0) * 1000
            return {"host": host, "reachable": True, "latency_ms": round(latency_ms, 2)}
        except OSError:
            return {"host": host, "reachable": False, "latency_ms": None}

    # ------------------------------------------------------------------
    # HTTP HEAD check
    # ------------------------------------------------------------------

    def check_http(self, url: str, timeout_s: float = 5.0) -> dict[str, Any]:
        """Send an HTTP HEAD request to *url* and report status + latency.

        Returns::

            {url: str, status_code: int | None, latency_ms: float | None, ok: bool}
        """
        t0 = time.monotonic()
        req = urllib.request.Request(url, method="HEAD")
        try:
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                status_code = resp.status
                latency_ms = (time.monotonic() - t0) * 1000
                ok = 200 <= status_code < 400
            return {
                "url": url,
                "status_code": status_code,
                "latency_ms": round(latency_ms, 2),
                "ok": ok,
            }
        except urllib.error.HTTPError as exc:
            latency_ms = (time.monotonic() - t0) * 1000
            ok = 200 <= exc.code < 400
            return {
                "url": url,
                "status_code": exc.code,
                "latency_ms": round(latency_ms, 2),
                "ok": ok,
            }
        except Exception:  # noqa: BLE001
            return {"url": url, "status_code": None, "latency_ms": None, "ok": False}

    # ------------------------------------------------------------------
    # Full report
    # ------------------------------------------------------------------

    def full_report(self) -> dict[str, Any]:
        """Check all configured targets.

        Returns::

            {online: bool, targets: [ping_result, ...], ts: str}
        """
        results: list[dict[str, Any]] = []
        for target in self.targets:
            if target.startswith("http://") or target.startswith("https://"):
                results.append(self.check_http(target))
            else:
                results.append(self.ping(target))

        online = any(
            r.get("reachable", False) or r.get("ok", False) for r in results
        )
        return {
            "online": online,
            "targets": results,
            "ts": datetime.now(timezone.utc).isoformat(),
        }

    # ------------------------------------------------------------------
    # Quick online check
    # ------------------------------------------------------------------

    def is_online(self) -> bool:
        """Quick connectivity check: attempt TCP connect to 8.8.8.8:53."""
        try:
            with socket.create_connection(
                (_ONLINE_CHECK_HOST, _ONLINE_CHECK_PORT), timeout=2.0
            ):
                return True
        except OSError:
            return False
