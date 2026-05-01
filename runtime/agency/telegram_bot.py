"""Telegram bot integration.

Sends and receives messages via the Telegram Bot API.  When the token is
not configured the class runs in *mock* mode: all API calls return
deterministic stub responses so the module is fully usable in tests and
offline environments.
"""

from __future__ import annotations

import os
import time
from typing import Any


_TELEGRAM_API = "https://api.telegram.org/bot"


class TelegramBot:
    """Send/receive Telegram messages via Bot API.

    Reads ``JARVIS_TELEGRAM_TOKEN`` and ``JARVIS_TELEGRAM_CHAT_ID`` from
    the environment.  When the token is absent or empty, *mock* mode is
    enabled: every method returns a realistic-looking stub response
    without making any network calls.
    """

    def __init__(
        self,
        token: str | None = None,
        chat_id: str | None = None,
    ) -> None:
        self.token: str = token or os.environ.get("JARVIS_TELEGRAM_TOKEN", "")
        self.chat_id: str = (
            chat_id or os.environ.get("JARVIS_TELEGRAM_CHAT_ID", "")
        )
        self.mock: bool = not bool(self.token)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _base_url(self) -> str:
        return f"{_TELEGRAM_API}{self.token}"

    def _post(self, method: str, data: dict[str, Any]) -> dict[str, Any]:
        """POST to ``/<method>`` and return parsed JSON."""
        import urllib.request
        import urllib.parse
        import json

        url = f"{self._base_url()}/{method}"
        payload = json.dumps(data).encode()
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read())
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "description": str(exc)}

    def _get(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """GET ``/<method>`` with optional query params."""
        import urllib.request
        import urllib.parse
        import json

        url = f"{self._base_url()}/{method}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        try:
            with urllib.request.urlopen(url, timeout=10) as resp:
                return json.loads(resp.read())
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "description": str(exc)}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def send_message(self, text: str, chat_id: str | None = None) -> dict[str, Any]:
        """Send a text message to *chat_id* (defaults to ``self.chat_id``)."""
        target = chat_id or self.chat_id
        if self.mock:
            return {
                "ok": True,
                "result": {
                    "message_id": 1,
                    "chat": {"id": target or "mock_chat"},
                    "text": text,
                    "date": int(time.time()),
                },
            }
        return self._post("sendMessage", {"chat_id": target, "text": text})

    def send_photo(
        self,
        photo_bytes: bytes,
        caption: str = "",
        chat_id: str | None = None,
    ) -> dict[str, Any]:
        """Send a photo (raw bytes) with an optional caption."""
        target = chat_id or self.chat_id
        if self.mock:
            return {
                "ok": True,
                "result": {
                    "message_id": 2,
                    "chat": {"id": target or "mock_chat"},
                    "caption": caption,
                    "photo": [{"file_size": len(photo_bytes)}],
                    "date": int(time.time()),
                },
            }
        # Real path: multipart/form-data upload
        import urllib.request
        import json

        boundary = "----JarvisFormBoundary"
        body_parts: list[bytes] = []
        # chat_id field
        body_parts.append(
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="chat_id"\r\n\r\n'
            f"{target}\r\n".encode()
        )
        if caption:
            body_parts.append(
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="caption"\r\n\r\n'
                f"{caption}\r\n".encode()
            )
        body_parts.append(
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="photo"; filename="photo.jpg"\r\n'
            f"Content-Type: image/jpeg\r\n\r\n".encode() + photo_bytes + b"\r\n"
        )
        body_parts.append(f"--{boundary}--\r\n".encode())
        body = b"".join(body_parts)
        url = f"{self._base_url()}/sendPhoto"
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read())
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "description": str(exc)}

    def get_updates(self, offset: int = 0, limit: int = 10) -> list[dict[str, Any]]:
        """Fetch pending updates (mock: empty list)."""
        if self.mock:
            return []
        result = self._get("getUpdates", {"offset": offset, "limit": limit})
        return result.get("result", [])

    def set_webhook(self, url: str) -> dict[str, Any]:
        """Register a webhook URL."""
        if self.mock:
            return {"ok": True, "result": True, "description": "Webhook was set"}
        return self._post("setWebhook", {"url": url})

    def delete_webhook(self) -> dict[str, Any]:
        """Remove the current webhook."""
        if self.mock:
            return {"ok": True, "result": True, "description": "Webhook was deleted"}
        return self._post("deleteWebhook", {})

    def get_me(self) -> dict[str, Any]:
        """Return basic bot info."""
        if self.mock:
            return {
                "ok": True,
                "result": {
                    "id": 123456789,
                    "is_bot": True,
                    "first_name": "JARVIS",
                    "username": "jarvis_bot",
                },
            }
        return self._get("getMe")
