"""GitNexus bridge — GitHub REST API v3 client.

Stdlib-only (urllib). Public read works without token; writes and private
repos use GITHUB_TOKEN env var. Returns plain dicts/lists for ergonomic use.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"
DEFAULT_TIMEOUT = 10.0
USER_AGENT = "gitnexus-bridge/1.0"


class GitNexusError(Exception):
    """Raised on GitHub API failure."""

    def __init__(self, message: str, status: Optional[int] = None, body: Optional[str] = None):
        super().__init__(message)
        self.status = status
        self.body = body


class GitNexusBridge:
    """GitHub REST API v3 bridge."""

    def __init__(self, token: Optional[str] = None, timeout: float = DEFAULT_TIMEOUT):
        self.token = token if token is not None else os.environ.get("GITHUB_TOKEN")
        self.timeout = timeout

    # ---------- HTTP core ----------

    def _request(
        self,
        path: str,
        method: str = "GET",
        params: Optional[dict] = None,
        body: Optional[dict] = None,
    ) -> Any:
        url = path if path.startswith("http") else f"{GITHUB_API}{path}"
        if params:
            cleaned = {k: v for k, v in params.items() if v is not None}
            if cleaned:
                url = f"{url}?{urllib.parse.urlencode(cleaned)}"

        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": USER_AGENT,
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        data: Optional[bytes] = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                self._log_rate_limit(resp.headers)
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
            self._log_rate_limit(getattr(e, "headers", {}) or {})
            raise GitNexusError(
                f"GitHub API {method} {url} failed: {e.code} {e.reason}",
                status=e.code,
                body=err_body,
            ) from e
        except urllib.error.URLError as e:
            raise GitNexusError(f"GitHub API {method} {url} network error: {e.reason}") from e

    @staticmethod
    def _log_rate_limit(headers: Any) -> None:
        try:
            remaining = headers.get("X-RateLimit-Remaining") if headers else None
            limit = headers.get("X-RateLimit-Limit") if headers else None
            reset = headers.get("X-RateLimit-Reset") if headers else None
        except Exception:
            return
        if remaining is not None:
            logger.info("GitHub rate-limit: %s/%s reset=%s", remaining, limit, reset)

    # ---------- Public API ----------

    def search_repos(
        self,
        query: str,
        language: Optional[str] = None,
        stars_min: int = 0,
    ) -> list[dict]:
        if not query:
            raise ValueError("query required")
        q_parts = [query]
        if language:
            q_parts.append(f"language:{language}")
        if stars_min and stars_min > 0:
            q_parts.append(f"stars:>={int(stars_min)}")
        params = {"q": " ".join(q_parts), "per_page": 30}
        data = self._request("/search/repositories", params=params) or {}
        items = data.get("items", []) if isinstance(data, dict) else []
        return [
            {
                "name": it.get("full_name") or it.get("name"),
                "url": it.get("html_url"),
                "stars": it.get("stargazers_count", 0),
                "description": it.get("description") or "",
            }
            for it in items
        ]

    def get_repo_info(self, owner: str, repo: str) -> dict:
        if not owner or not repo:
            raise ValueError("owner and repo required")
        return self._request(f"/repos/{owner}/{repo}") or {}

    def list_issues(
        self,
        owner: str,
        repo: str,
        state: str = "open",
        labels: Optional[list[str]] = None,
    ) -> list[dict]:
        if not owner or not repo:
            raise ValueError("owner and repo required")
        if state not in ("open", "closed", "all"):
            raise ValueError("state must be open|closed|all")
        params: dict = {"state": state, "per_page": 50}
        if labels:
            params["labels"] = ",".join(labels)
        data = self._request(f"/repos/{owner}/{repo}/issues", params=params) or []
        return [i for i in data if "pull_request" not in i]

    def create_issue(
        self,
        owner: str,
        repo: str,
        title: str,
        body: str,
        labels: Optional[list[str]] = None,
    ) -> dict:
        if not self.token:
            raise GitNexusError("create_issue requires GITHUB_TOKEN")
        if not title:
            raise ValueError("title required")
        payload: dict = {"title": title, "body": body or ""}
        if labels:
            payload["labels"] = labels
        return self._request(f"/repos/{owner}/{repo}/issues", method="POST", body=payload) or {}

    def get_file_content(self, owner: str, repo: str, path: str, ref: str = "main") -> str:
        if not path:
            raise ValueError("path required")
        data = self._request(
            f"/repos/{owner}/{repo}/contents/{urllib.parse.quote(path)}",
            params={"ref": ref},
        ) or {}
        if isinstance(data, list):
            raise GitNexusError(f"path is directory: {path}")
        encoding = data.get("encoding")
        content = data.get("content", "")
        if encoding == "base64":
            return base64.b64decode(content).decode("utf-8", errors="replace")
        if encoding is None and content:
            return content
        raise GitNexusError(f"unsupported content encoding: {encoding}")

    def search_code(self, query: str, repo: Optional[str] = None) -> list[dict]:
        if not query:
            raise ValueError("query required")
        q = query if not repo else f"{query} repo:{repo}"
        data = self._request("/search/code", params={"q": q, "per_page": 30}) or {}
        items = data.get("items", []) if isinstance(data, dict) else []
        return [
            {
                "path": it.get("path"),
                "name": it.get("name"),
                "url": it.get("html_url"),
                "repository": (it.get("repository") or {}).get("full_name"),
            }
            for it in items
        ]

    # ---------- Dispatcher ----------

    def invoke(self, action: str, **kwargs) -> Any:
        actions = {
            "search_repos": self.search_repos,
            "get_repo_info": self.get_repo_info,
            "list_issues": self.list_issues,
            "create_issue": self.create_issue,
            "get_file_content": self.get_file_content,
            "search_code": self.search_code,
        }
        fn = actions.get(action)
        if fn is None:
            raise ValueError(f"unknown action: {action}. valid: {sorted(actions)}")
        return fn(**kwargs)
