"""Instagram Reels bridge — Graph API v20.0 client.

Stdlib-only (urllib). Token via INSTAGRAM_ACCESS_TOKEN. Without token, returns
mock data with WARNING log so dev/test flows still work.
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional

logger = logging.getLogger(__name__)

GRAPH_API = "https://graph.facebook.com/v20.0"
DEFAULT_TIMEOUT = 10.0
USER_AGENT = "instagram-reels-bridge/1.0"
DEFAULT_MEDIA_FIELDS = "id,media_type,media_url,permalink,timestamp,caption,thumbnail_url"


class InstagramError(Exception):
    """Raised on Instagram Graph API failure."""

    def __init__(self, message: str, status: Optional[int] = None, body: Optional[str] = None):
        super().__init__(message)
        self.status = status
        self.body = body


class InstagramBridge:
    """Instagram Graph API v20.0 bridge."""

    def __init__(
        self,
        token: Optional[str] = None,
        ig_user_id: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        self.token = token if token is not None else os.environ.get("INSTAGRAM_ACCESS_TOKEN")
        self.ig_user_id = ig_user_id or os.environ.get("INSTAGRAM_USER_ID", "me")
        self.timeout = timeout

    @property
    def has_token(self) -> bool:
        return bool(self.token)

    # ---------- HTTP core ----------

    def _request(
        self,
        path: str,
        method: str = "GET",
        params: Optional[dict] = None,
        body: Optional[dict] = None,
    ) -> Any:
        if not self.token:
            raise InstagramError("INSTAGRAM_ACCESS_TOKEN not set")
        url = path if path.startswith("http") else f"{GRAPH_API}{path}"
        merged = dict(params or {})
        merged["access_token"] = self.token
        cleaned = {k: v for k, v in merged.items() if v is not None}
        url = f"{url}?{urllib.parse.urlencode(cleaned)}"

        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        data: Optional[bytes] = None
        if body is not None:
            data = urllib.parse.urlencode(body).encode("utf-8")
            headers["Content-Type"] = "application/x-www-form-urlencoded"

        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
                if not raw:
                    return None
                return json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as e:
            err_body = ""
            try:
                err_body = e.read().decode("utf-8", errors="replace")
            except Exception:
                pass
            raise InstagramError(
                f"Instagram API {method} {path} failed: {e.code} {e.reason}",
                status=e.code,
                body=err_body,
            ) from e
        except urllib.error.URLError as e:
            raise InstagramError(f"Instagram API {method} {path} network error: {e.reason}") from e

    # ---------- Mock fallback ----------

    @staticmethod
    def _mock_media_item(idx: int = 0, media_type: str = "REELS") -> dict:
        return {
            "id": f"mock_media_{idx}",
            "media_type": media_type,
            "timestamp": "2026-01-01T00:00:00+0000",
            "permalink": f"https://instagram.com/p/mock_{idx}/",
        }

    def _warn_mock(self, fn: str) -> None:
        logger.warning("INSTAGRAM_ACCESS_TOKEN not set — %s returning mock data", fn)

    # ---------- Public API ----------

    def get_media_list(self, limit: int = 20) -> list[dict]:
        if limit < 1 or limit > 100:
            raise ValueError("limit must be 1..100")
        if not self.token:
            self._warn_mock("get_media_list")
            return [self._mock_media_item(i) for i in range(min(limit, 5))]
        data = self._request(
            f"/{self.ig_user_id}/media",
            params={"fields": DEFAULT_MEDIA_FIELDS, "limit": limit},
        ) or {}
        items = data.get("data", []) if isinstance(data, dict) else []
        return [
            {
                "id": it.get("id"),
                "media_type": it.get("media_type"),
                "timestamp": it.get("timestamp"),
                "permalink": it.get("permalink"),
            }
            for it in items
        ]

    def get_media_details(self, media_id: str) -> dict:
        if not media_id:
            raise ValueError("media_id required")
        if not self.token:
            self._warn_mock("get_media_details")
            return self._mock_media_item(0)
        return self._request(f"/{media_id}", params={"fields": DEFAULT_MEDIA_FIELDS}) or {}

    def get_insights(self, media_id: str) -> dict:
        if not media_id:
            raise ValueError("media_id required")
        if not self.token:
            self._warn_mock("get_insights")
            return {
                "reach": 0,
                "impressions": 0,
                "likes": 0,
                "comments": 0,
                "saves": 0,
                "shares": 0,
            }
        metrics = "reach,impressions,likes,comments,saves,shares"
        data = self._request(f"/{media_id}/insights", params={"metric": metrics}) or {}
        out = {"reach": 0, "impressions": 0, "likes": 0, "comments": 0, "saves": 0, "shares": 0}
        for entry in data.get("data", []) if isinstance(data, dict) else []:
            name = entry.get("name")
            values = entry.get("values") or []
            value = values[0].get("value") if values and isinstance(values[0], dict) else 0
            if name in out:
                out[name] = value or 0
        return out

    def get_reels(self, limit: int = 20) -> list[dict]:
        if limit < 1 or limit > 100:
            raise ValueError("limit must be 1..100")
        if not self.token:
            self._warn_mock("get_reels")
            return [self._mock_media_item(i, "REELS") for i in range(min(limit, 3))]
        items = self.get_media_list(limit=limit)
        return [m for m in items if m.get("media_type") == "REELS"]

    def post_reel(
        self,
        video_url: str,
        caption: str,
        cover_image_url: Optional[str] = None,
    ) -> str:
        if not video_url:
            raise ValueError("video_url required")
        if not self.token:
            self._warn_mock("post_reel")
            return "mock_creation_id"
        # Step 1: create media container
        params: dict = {
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption or "",
        }
        if cover_image_url:
            params["cover_url"] = cover_image_url
        container = self._request(f"/{self.ig_user_id}/media", method="POST", body=params) or {}
        creation_id = container.get("id")
        if not creation_id:
            raise InstagramError("media container missing id", body=json.dumps(container))
        # Step 2: poll status, then publish
        self._wait_for_container(creation_id)
        published = self._request(
            f"/{self.ig_user_id}/media_publish",
            method="POST",
            body={"creation_id": creation_id},
        ) or {}
        return published.get("id") or creation_id

    def _wait_for_container(self, creation_id: str, max_attempts: int = 30, delay: float = 2.0) -> None:
        for _ in range(max_attempts):
            status = self._request(
                f"/{creation_id}", params={"fields": "status_code"}
            ) or {}
            code = status.get("status_code")
            if code == "FINISHED":
                return
            if code == "ERROR":
                raise InstagramError(f"container processing failed: {status}")
            time.sleep(delay)
        raise InstagramError("container processing timeout")

    def get_account_info(self) -> dict:
        if not self.token:
            self._warn_mock("get_account_info")
            return {
                "id": "mock_account_id",
                "username": "mock_user",
                "followers_count": 0,
                "media_count": 0,
            }
        data = self._request(
            f"/{self.ig_user_id}",
            params={"fields": "id,username,followers_count,media_count"},
        ) or {}
        return {
            "id": data.get("id"),
            "username": data.get("username"),
            "followers_count": data.get("followers_count", 0),
            "media_count": data.get("media_count", 0),
        }

    # ---------- Dispatcher ----------

    def invoke(self, action: str, **kwargs) -> Any:
        actions = {
            "get_media_list": self.get_media_list,
            "get_media_details": self.get_media_details,
            "get_insights": self.get_insights,
            "get_reels": self.get_reels,
            "post_reel": self.post_reel,
            "get_account_info": self.get_account_info,
        }
        fn = actions.get(action)
        if fn is None:
            raise ValueError(f"unknown action: {action}. valid: {sorted(actions)}")
        return fn(**kwargs)
