"""Webhook notification dispatcher for the Agency runtime.

Supports HMAC-SHA256 signed POSTs for events:
  chat.complete | batch.complete | skill.error | dlq.item_added | ping

Config in ~/.agency/config.toml:
    [webhooks]
    url    = "https://example.com/hook"
    secret = "s3cr3t"
    events = ["chat.complete", "batch.complete"]
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional
import urllib.request
import urllib.error

logger = logging.getLogger(__name__)

VALID_EVENTS: frozenset = frozenset(
    {"chat.complete", "batch.complete", "skill.error", "dlq.item_added", "ping"}
)


@dataclass
class WebhookConfig:
    """Webhook delivery configuration."""
    url: str
    secret: str = ""
    events: List[str] = field(default_factory=list)

    def should_notify(self, event: str) -> bool:
        if not self.events:
            return True
        return event in self.events


class WebhookDispatcher:
    """Sends signed webhook POSTs, retrying up to 3x with exponential back-off."""

    def __init__(self, config: WebhookConfig) -> None:
        self.config = config

    def _sign(self, payload: bytes) -> str:
        if not self.config.secret:
            return ""
        digest = hmac.new(
            self.config.secret.encode("utf-8"), payload, hashlib.sha256
        ).hexdigest()
        return f"sha256={digest}"

    def _send_once(self, payload: bytes, signature: str) -> bool:
        headers: Dict[str, str] = {
            "Content-Type": "application/json",
            "User-Agent": "agency-webhook/1.0",
        }
        if signature:
            headers["X-Agency-Signature"] = signature
        req = urllib.request.Request(
            self.config.url, data=payload, headers=headers, method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return 200 <= resp.status < 300
        except urllib.error.HTTPError as exc:
            logger.debug("Webhook HTTP error %s: %s", exc.code, exc.reason)
            return False
        except Exception as exc:
            logger.debug("Webhook delivery error: %s", exc)
            return False

    def _deliver(self, event: str, data: dict) -> bool:
        payload = json.dumps(
            {"event": event, "data": data, "ts": time.time()}
        ).encode("utf-8")
        signature = self._sign(payload)
        for attempt in range(3):
            if self._send_once(payload, signature):
                logger.debug("Webhook delivered: %s (attempt %d)", event, attempt + 1)
                return True
            if attempt < 2:
                sleep_s = 2 ** attempt
                logger.debug("Webhook attempt %d failed; retrying in %ds", attempt + 1, sleep_s)
                time.sleep(sleep_s)
        logger.warning("Webhook delivery failed after 3 attempts: %s", event)
        return False

    def dispatch(self, event: str, data: Optional[dict] = None) -> None:
        """Non-blocking dispatch via daemon thread."""
        if event not in VALID_EVENTS:
            raise ValueError(f"Unknown webhook event: {event!r}")
        if not self.config.should_notify(event):
            return
        t = threading.Thread(target=self._deliver, args=(event, data or {}), daemon=True)
        t.start()

    def dispatch_sync(self, event: str, data: Optional[dict] = None) -> bool:
        """Synchronous dispatch for tests and CLI test command."""
        if event not in VALID_EVENTS:
            raise ValueError(f"Unknown webhook event: {event!r}")
        if not self.config.should_notify(event):
            return True  # filtered — not an error
        return self._deliver(event, data or {})


def _mini_toml_parse(raw: str) -> dict:
    result: dict = {}
    current_section: dict = result
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip()
            result.setdefault(section, {})
            current_section = result[section]
            continue
        if "=" in line:
            k, _, v = line.partition("=")
            k = k.strip()
            v = v.strip()
            if v.startswith("["):
                items = v.strip("[]").split(",")
                current_section[k] = [i.strip().strip('"').strip("'") for i in items if i.strip()]
            else:
                current_section[k] = v.strip('"').strip("'")
    return result


def load_webhook_config(config_path: Optional[str] = None) -> Optional[WebhookConfig]:
    """Load WebhookConfig from the agency config file."""
    import pathlib
    cfg_path = (
        pathlib.Path(config_path) if config_path
        else pathlib.Path.home() / ".agency" / "config.toml"
    )
    if not cfg_path.exists():
        return None
    try:
        raw_text = cfg_path.read_text(encoding="utf-8")
    except OSError:
        return None

    data: Optional[dict] = None
    try:
        import tomllib  # type: ignore
        data = tomllib.loads(raw_text)
    except ImportError:
        try:
            import tomli  # type: ignore
            data = tomli.loads(raw_text)
        except ImportError:
            data = _mini_toml_parse(raw_text)
    except Exception:
        return None

    if not isinstance(data, dict):
        return None
    wh = data.get("webhooks", {})
    if not isinstance(wh, dict):
        return None
    url = wh.get("url", "")
    if not url:
        return None
    return WebhookConfig(
        url=str(url),
        secret=str(wh.get("secret", "")),
        events=list(wh.get("events", [])),
    )
