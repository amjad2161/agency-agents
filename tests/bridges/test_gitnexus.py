"""Tests for GitNexusBridge — mock urllib, no real network."""
from __future__ import annotations

import base64
import io
import json
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from bridges.gitnexus import GitNexusBridge, GitNexusError


def _mock_response(payload, status: int = 200, headers=None):
    body = json.dumps(payload).encode("utf-8") if payload is not None else b""
    resp = MagicMock()
    resp.read.return_value = body
    resp.headers = headers or {
        "X-RateLimit-Remaining": "59",
        "X-RateLimit-Limit": "60",
        "X-RateLimit-Reset": "1234567890",
    }
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    return resp


def _http_error(status: int, body: str = "{}"):
    err = urllib.error.HTTPError(
        url="https://api.github.com/x",
        code=status,
        msg="err",
        hdrs={"X-RateLimit-Remaining": "0"},
        fp=io.BytesIO(body.encode("utf-8")),
    )
    return err


# ---------- search_repos ----------

def test_search_repos_returns_normalized_items():
    payload = {
        "items": [
            {
                "full_name": "owner/repo",
                "html_url": "https://github.com/owner/repo",
                "stargazers_count": 100,
                "description": "desc",
            }
        ]
    }
    with patch("bridges.gitnexus.urllib.request.urlopen", return_value=_mock_response(payload)) as op:
        bridge = GitNexusBridge(token=None)
        out = bridge.search_repos("foo", language="python", stars_min=50)
    assert out == [
        {
            "name": "owner/repo",
            "url": "https://github.com/owner/repo",
            "stars": 100,
            "description": "desc",
        }
    ]
    called_url = op.call_args[0][0].full_url
    assert "language%3Apython" in called_url
    assert "stars%3A%3E%3D50" in called_url


def test_search_repos_empty_query_raises():
    bridge = GitNexusBridge(token=None)
    with pytest.raises(ValueError):
        bridge.search_repos("")


def test_search_repos_empty_items_returns_empty_list():
    with patch("bridges.gitnexus.urllib.request.urlopen", return_value=_mock_response({"items": []})):
        bridge = GitNexusBridge(token=None)
        assert bridge.search_repos("x") == []


# ---------- get_repo_info ----------

def test_get_repo_info_returns_dict():
    payload = {"full_name": "a/b", "stargazers_count": 1}
    with patch("bridges.gitnexus.urllib.request.urlopen", return_value=_mock_response(payload)):
        bridge = GitNexusBridge(token="t")
        out = bridge.get_repo_info("a", "b")
    assert out["full_name"] == "a/b"


def test_get_repo_info_missing_args_raises():
    bridge = GitNexusBridge(token=None)
    with pytest.raises(ValueError):
        bridge.get_repo_info("", "b")


def test_get_repo_info_404_raises_gitnexus_error():
    with patch("bridges.gitnexus.urllib.request.urlopen", side_effect=_http_error(404, '{"message":"Not Found"}')):
        bridge = GitNexusBridge(token=None)
        with pytest.raises(GitNexusError) as ei:
            bridge.get_repo_info("a", "b")
    assert ei.value.status == 404


# ---------- list_issues ----------

def test_list_issues_filters_pull_requests():
    payload = [
        {"number": 1, "title": "real issue"},
        {"number": 2, "title": "PR", "pull_request": {"url": "x"}},
    ]
    with patch("bridges.gitnexus.urllib.request.urlopen", return_value=_mock_response(payload)):
        bridge = GitNexusBridge(token=None)
        out = bridge.list_issues("a", "b")
    assert len(out) == 1
    assert out[0]["number"] == 1


def test_list_issues_invalid_state_raises():
    bridge = GitNexusBridge(token=None)
    with pytest.raises(ValueError):
        bridge.list_issues("a", "b", state="bogus")


def test_list_issues_passes_labels():
    with patch("bridges.gitnexus.urllib.request.urlopen", return_value=_mock_response([])) as op:
        bridge = GitNexusBridge(token=None)
        bridge.list_issues("a", "b", labels=["bug", "p0"])
    url = op.call_args[0][0].full_url
    assert "labels=bug%2Cp0" in url


# ---------- create_issue ----------

def test_create_issue_requires_token():
    bridge = GitNexusBridge(token=None)
    with pytest.raises(GitNexusError):
        bridge.create_issue("a", "b", "t", "body")


def test_create_issue_posts_json_body():
    payload = {"number": 7, "title": "t"}
    with patch("bridges.gitnexus.urllib.request.urlopen", return_value=_mock_response(payload)) as op:
        bridge = GitNexusBridge(token="tok")
        out = bridge.create_issue("a", "b", "t", "body", labels=["bug"])
    req = op.call_args[0][0]
    assert req.method == "POST"
    sent = json.loads(req.data.decode("utf-8"))
    assert sent == {"title": "t", "body": "body", "labels": ["bug"]}
    assert out["number"] == 7
    assert req.headers["Authorization"] == "Bearer tok"


def test_create_issue_empty_title_raises():
    bridge = GitNexusBridge(token="tok")
    with pytest.raises(ValueError):
        bridge.create_issue("a", "b", "", "body")


# ---------- get_file_content ----------

def test_get_file_content_decodes_base64():
    raw = "hello\nworld"
    payload = {
        "encoding": "base64",
        "content": base64.b64encode(raw.encode("utf-8")).decode("ascii"),
    }
    with patch("bridges.gitnexus.urllib.request.urlopen", return_value=_mock_response(payload)):
        bridge = GitNexusBridge(token=None)
        out = bridge.get_file_content("a", "b", "README.md", ref="dev")
    assert out == raw


def test_get_file_content_directory_response_raises():
    with patch("bridges.gitnexus.urllib.request.urlopen", return_value=_mock_response([{"name": "x"}])):
        bridge = GitNexusBridge(token=None)
        with pytest.raises(GitNexusError):
            bridge.get_file_content("a", "b", "src")


def test_get_file_content_unsupported_encoding_raises():
    payload = {"encoding": "utf-8-rare", "content": "x"}
    with patch("bridges.gitnexus.urllib.request.urlopen", return_value=_mock_response(payload)):
        bridge = GitNexusBridge(token=None)
        with pytest.raises(GitNexusError):
            bridge.get_file_content("a", "b", "f")


# ---------- search_code ----------

def test_search_code_returns_normalized_matches():
    payload = {
        "items": [
            {
                "name": "foo.py",
                "path": "src/foo.py",
                "html_url": "https://x",
                "repository": {"full_name": "a/b"},
            }
        ]
    }
    with patch("bridges.gitnexus.urllib.request.urlopen", return_value=_mock_response(payload)) as op:
        bridge = GitNexusBridge(token="tok")
        out = bridge.search_code("def main", repo="a/b")
    assert out[0]["repository"] == "a/b"
    assert "repo%3Aa%2Fb" in op.call_args[0][0].full_url


# ---------- invoke dispatcher ----------

def test_invoke_routes_to_action():
    with patch("bridges.gitnexus.urllib.request.urlopen", return_value=_mock_response({"items": []})):
        bridge = GitNexusBridge(token=None)
        out = bridge.invoke("search_repos", query="hello")
    assert out == []


def test_invoke_unknown_action_raises():
    bridge = GitNexusBridge(token=None)
    with pytest.raises(ValueError):
        bridge.invoke("nope")


# ---------- network errors ----------

def test_network_error_wrapped():
    with patch(
        "bridges.gitnexus.urllib.request.urlopen",
        side_effect=urllib.error.URLError("dns failure"),
    ):
        bridge = GitNexusBridge(token=None)
        with pytest.raises(GitNexusError) as ei:
            bridge.get_repo_info("a", "b")
    assert "network error" in str(ei.value)


def test_token_from_env(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "envtok")
    bridge = GitNexusBridge()
    assert bridge.token == "envtok"
