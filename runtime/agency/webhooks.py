"""Webhook dispatcher: POST events to registered endpoints with HMAC signatures."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from pathlib import Path
from typing import Any


_DEFAULT_PATH = Path.home() / ".agency" / "webhooks.json"
_RETRY_DELAYS = (1, 2, 4)  # exponential backoff in seconds


class WebhookDispatcher:
    """Dispatch events to registered webhook endpoints.

    Endpoints are persisted in *config_path* (default ~/.agency/webhooks.json).
    Each entry has ``url`` and ``secret`` (used for HMAC-SHA256 signing).
    """

    def __init__(self, config_path: Path | None = None) -> None:
        self._path = Path(config_path) if config_path else _DEFAULT_PATH
        self._path.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, url: str, secret: str) -> dict:
        """Add a new webhook endpoint (or update secret if URL exists)."""
        endpoints = self._load()
        for ep in endpoints:
            if ep["url"] == url:
                ep["secret"] = secret
                self._save(endpoints)
                return {"status": "updated", "url": url}
        endpoints.append({"url": url, "secret": secret})
        self._save(endpoints)
        return {"status": "registered", "url": url}

    def list_webhooks(self) -> list[dict]:
        """Return registered endpoints (secret is masked)."""
        return [
            {"url": ep["url"], "secret": "***"}
            for ep in self._load()
        ]

    def remove(self, url: str) -> bool:
        """Remove an endpoint by URL; return True if it existed."""
        endpoints = self._load()
        filtered = [ep for ep in endpoints if ep["url"] != url]
        if len(filtered) == len(endpoints):
            return False
        self._save(filtered)
        return True

    # ------------------------------------------------------------------
    # Dispatching
    # ------------------------------------------------------------------

    def dispatch(self, event_type: str, payload: dict) -> list[dict]:
        """POST *payload* to every registered endpoint.

        Returns a list of result dicts (one per endpoint).
        """
        import urllib.error
        import urllib.request

        endpoints = self._load()
        body = json.dumps({"event": event_type, "payload": payload}).encode()
        results = []
        for ep in endpoints:
            result = self._post_with_retry(ep, body, event_type)
            results.append(result)
        return results

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _post_with_retry(self, ep: dict, body: bytes, event_type: str) -> dict:
        import urllib.error
        import urllib.request

        url = ep["url"]
        secret = ep.get("secret", "")
        sig = self._sign(body, secret)
        headers = {
            "Content-Type": "application/json",
            "X-Jarvis-Signature": sig,
            "X-Jarvis-Event": event_type,
        }
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")

        last_exc: Exception | None = None
        for attempt, delay in enumerate(_RETRY_DELAYS, start=1):
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
                    return {
                        "url": url,
                        "status": resp.status,
                        "attempts": attempt,
                        "ok": True,
                    }
            except (urllib.error.URLError, OSError) as exc:
                last_exc = exc
                if attempt < len(_RETRY_DELAYS):
                    time.sleep(delay)

        return {
            "url": url,
            "status": None,
            "attempts": len(_RETRY_DELAYS),
            "ok": False,
            "error": str(last_exc),
        }

    @staticmethod
    def _sign(body: bytes, secret: str) -> str:
        mac = hmac.new(secret.encode(), body, hashlib.sha256)
        return "sha256=" + mac.hexdigest()

    def _load(self) -> list[dict]:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def _save(self, endpoints: list[dict]) -> None:
        self._path.write_text(json.dumps(endpoints, indent=2), encoding="utf-8")
