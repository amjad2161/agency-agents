"""
Network Monitor — Pass 23
Connectivity checking, ping, latency — stdlib only (no external deps).
"""

from __future__ import annotations
import socket
import time
import threading
import urllib.request
import urllib.error
from dataclasses import dataclass
from typing import Optional, Callable

# ── dataclasses ────────────────────────────────────────────────────────────────

@dataclass
class PingResult:
    host: str
    avg_ms: float
    packet_loss_pct: float


@dataclass
class ConnectivityResult:
    online: bool
    dns_ok: bool
    latency_ms: float
    isp: str

    def to_dict(self) -> dict:
        return {
            "online": self.online,
            "dns_ok": self.dns_ok,
            "latency_ms": self.latency_ms,
            "isp": self.isp,
        }


# ── helpers ────────────────────────────────────────────────────────────────────

_ANTHROPIC_HOST = "api.anthropic.com"
_DNS_HOST       = "8.8.8.8"
_CLOUDFLARE     = "1.1.1.1"
_TIMEOUT_S      = 3.0


def _tcp_ping_ms(host: str, port: int = 443, timeout: float = _TIMEOUT_S) -> Optional[float]:
    """Measure TCP connect time in ms. Returns None on failure."""
    try:
        t0 = time.monotonic()
        with socket.create_connection((host, port), timeout=timeout):
            pass
        return (time.monotonic() - t0) * 1000.0
    except Exception:
        return None


def _dns_ok() -> bool:
    """Check whether DNS resolution works."""
    try:
        socket.getaddrinfo("google.com", None, timeout=_TIMEOUT_S)
        return True
    except Exception:
        return False


def _detect_isp() -> str:
    """Best-effort ISP name via ip-api.com (with short timeout; may fail)."""
    try:
        req = urllib.request.Request(
            "http://ip-api.com/json/?fields=isp",
            headers={"User-Agent": "jarvis-netcheck/1.0"},
        )
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            import json
            data = json.loads(resp.read().decode())
            return data.get("isp", "unknown")
    except Exception:
        return "unknown"


# ── public class ───────────────────────────────────────────────────────────────

class NetworkMonitor:
    """
    stdlib-only connectivity monitor.
    `watch()` runs a background thread and invokes callback on status changes.
    """

    def __init__(self):
        self._watch_thread: Optional[threading.Thread] = None
        self._watch_stop  = threading.Event()
        self._last_status: Optional[ConnectivityResult] = None

    # ── public API ────────────────────────────────────────────────────────────

    def check_connectivity(self) -> ConnectivityResult:
        """Single-shot connectivity check."""
        dns = _dns_ok()

        # Latency = TCP connect to 8.8.8.8:53
        lat = _tcp_ping_ms(_DNS_HOST, port=53) or 0.0
        if lat == 0.0:
            lat = _tcp_ping_ms(_CLOUDFLARE, port=53) or 0.0

        online = dns and lat > 0.0
        isp = _detect_isp() if online else "offline"

        return ConnectivityResult(
            online=online,
            dns_ok=dns,
            latency_ms=lat,
            isp=isp,
        )

    def ping(self, host: str, count: int = 3) -> PingResult:
        """Simulate ping via repeated TCP connects (ICMP needs root)."""
        results = []
        for _ in range(count):
            ms = _tcp_ping_ms(host)
            if ms is not None:
                results.append(ms)

        if not results:
            return PingResult(host=host, avg_ms=0.0, packet_loss_pct=100.0)

        avg = sum(results) / len(results)
        loss = (count - len(results)) / count * 100.0
        return PingResult(host=host, avg_ms=avg, packet_loss_pct=loss)

    def get_latency_to_anthropic(self) -> float:
        """Returns latency in ms to api.anthropic.com. 0.0 if unreachable."""
        return _tcp_ping_ms(_ANTHROPIC_HOST, port=443) or 0.0

    def watch(
        self,
        interval_s: float = 30.0,
        callback: Optional[Callable[[ConnectivityResult], None]] = None,
    ) -> None:
        """
        Start a background thread that checks connectivity every `interval_s` seconds.
        Calls `callback(ConnectivityResult)` when status changes.
        """
        if self._watch_thread and self._watch_thread.is_alive():
            return  # already watching

        self._watch_stop.clear()

        def _loop():
            while not self._watch_stop.wait(timeout=interval_s):
                try:
                    result = self.check_connectivity()
                    if callback and self._status_changed(result):
                        callback(result)
                    self._last_status = result
                except Exception:
                    pass

        self._watch_thread = threading.Thread(target=_loop, daemon=True, name="jarvis-netwatch")
        self._watch_thread.start()

    def stop_watch(self) -> None:
        """Stop the background watcher thread."""
        self._watch_stop.set()
        if self._watch_thread:
            self._watch_thread.join(timeout=2.0)

    # ── internal ──────────────────────────────────────────────────────────────

    def _status_changed(self, result: ConnectivityResult) -> bool:
        if self._last_status is None:
            return True
        return self._last_status.online != result.online or \
               self._last_status.dns_ok != result.dns_ok


# ── CLI helper ─────────────────────────────────────────────────────────────────

def cli_netcheck() -> None:
    """jarvis netcheck — print connectivity status."""
    mon = NetworkMonitor()
    print("בודק קישוריות...")
    result = mon.check_connectivity()
    status = "✓ מחובר" if result.online else "✗ לא מחובר"
    print(f"  {status}")
    print(f"  DNS: {'✓' if result.dns_ok else '✗'}")
    print(f"  השהייה: {result.latency_ms:.1f} ms")
    print(f"  ספק: {result.isp}")
