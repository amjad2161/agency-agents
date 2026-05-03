"""Tests for InstagramBridge — mock urllib, no real network."""
from __future__ import annotations

import io
import json
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from bridges.instagram import InstagramBridge, InstagramError


def _mock_response(payload, status: int = 200):
    body = json.dumps(payload).encode("utf-8") if payload is not None else b""
    resp = MagicMock()
    resp.read.return_value = body
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    return resp


def _http_error(status: int, body: str = "{}"):
    return urllib.error.HTTPError(
        url="https://graph.facebook.com/x",
        code=status,
        msg="err",
        hdrs={},
        fp=io.BytesIO(body.encode("utf-8")),
    )


# ---------- mock fallback (no token) ----------

def test_get_media_list_mock_when_no_token(caplog):
    bridge = InstagramBridge(token="")
    with caplog.at_level("WARNING"):
        out = bridge.get_media_list(limit=3)
    assert len(out) == 3
    assert all(item["id"].startswith("mock_media_") for item in out)
    assert any("mock data" in r.message for r in caplog.records)


def test_get_insights_mock_when_no_token():
    bridge = InstagramBridge(token=None)
    out = bridge.get_insights("xyz")
    assert set(out.keys()) == {"reach", "impressions", "likes", "comments", "saves", "shares"}
    assert out["reach"] == 0


def test_get_account_info_mock_when_no_token():
    bridge = InstagramBridge(token=None)
    out = bridge.get_account_info()
    assert out["username"] == "mock_user"


def test_post_reel_mock_returns_mock_id(caplog):
    bridge = InstagramBridge(token=None)
    with caplog.at_level("WARNING"):
        out = bridge.post_reel("https://v.example/r.mp4", "cap")
    assert out == "mock_creation_id"


def test_get_reels_mock_filters_to_reels_type():
    bridge = InstagramBridge(token=None)
    out = bridge.get_reels(limit=2)
    assert all(item["media_type"] == "REELS" for item in out)


# ---------- token-required real path ----------

def test_get_media_list_with_token_normalizes():
    payload = {
        "data": [
            {
                "id": "1",
                "media_type": "REELS",
                "timestamp": "2026-01-01T00:00:00+0000",
                "permalink": "https://instagram.com/p/1",
                "caption": "x",
            },
            {"id": "2", "media_type": "IMAGE", "timestamp": "t", "permalink": "p"},
        ]
    }
    with patch("bridges.instagram.urllib.request.urlopen", return_value=_mock_response(payload)) as op:
        bridge = InstagramBridge(token="tok", ig_user_id="123")
        out = bridge.get_media_list(limit=10)
    assert len(out) == 2
    assert out[0] == {
        "id": "1",
        "media_type": "REELS",
        "timestamp": "2026-01-01T00:00:00+0000",
        "permalink": "https://instagram.com/p/1",
    }
    assert "access_token=tok" in op.call_args[0][0].full_url
    assert "/123/media" in op.call_args[0][0].full_url


def test_get_reels_with_token_filters_non_reels():
    payload = {
        "data": [
            {"id": "1", "media_type": "REELS", "timestamp": "t", "permalink": "p"},
            {"id": "2", "media_type": "IMAGE", "timestamp": "t", "permalink": "p"},
        ]
    }
    with patch("bridges.instagram.urllib.request.urlopen", return_value=_mock_response(payload)):
        bridge = InstagramBridge(token="tok")
        out = bridge.get_reels(limit=20)
    assert len(out) == 1
    assert out[0]["id"] == "1"


def test_get_insights_with_token_aggregates():
    payload = {
        "data": [
            {"name": "reach", "values": [{"value": 1000}]},
            {"name": "impressions", "values": [{"value": 1500}]},
            {"name": "likes", "values": [{"value": 200}]},
            {"name": "comments", "values": [{"value": 30}]},
            {"name": "saves", "values": [{"value": 10}]},
            {"name": "shares", "values": [{"value": 5}]},
            {"name": "unknown_metric", "values": [{"value": 99}]},
        ]
    }
    with patch("bridges.instagram.urllib.request.urlopen", return_value=_mock_response(payload)):
        bridge = InstagramBridge(token="tok")
        out = bridge.get_insights("media123")
    assert out == {
        "reach": 1000,
        "impressions": 1500,
        "likes": 200,
        "comments": 30,
        "saves": 10,
        "shares": 5,
    }


def test_get_media_details_requires_id():
    bridge = InstagramBridge(token="tok")
    with pytest.raises(ValueError):
        bridge.get_media_details("")


def test_get_account_info_with_token():
    payload = {"id": "9", "username": "u", "followers_count": 42, "media_count": 7}
    with patch("bridges.instagram.urllib.request.urlopen", return_value=_mock_response(payload)):
        bridge = InstagramBridge(token="tok")
        out = bridge.get_account_info()
    assert out == {"id": "9", "username": "u", "followers_count": 42, "media_count": 7}


def test_post_reel_two_step_flow():
    container_resp = _mock_response({"id": "c1"})
    status_resp = _mock_response({"status_code": "FINISHED"})
    publish_resp = _mock_response({"id": "pub_99"})

    with patch(
        "bridges.instagram.urllib.request.urlopen",
        side_effect=[container_resp, status_resp, publish_resp],
    ) as op, patch("bridges.instagram.time.sleep"):
        bridge = InstagramBridge(token="tok", ig_user_id="me")
        out = bridge.post_reel("https://v.mp4", "cap", cover_image_url="https://c.jpg")

    assert out == "pub_99"
    # 1st call: container POST
    first = op.call_args_list[0][0][0]
    assert first.method == "POST"
    assert b"media_type=REELS" in first.data
    assert b"cover_url=" in first.data
    # 3rd call: publish POST
    third = op.call_args_list[2][0][0]
    assert b"creation_id=c1" in third.data


def test_post_reel_container_error_raises():
    container_resp = _mock_response({"id": "c1"})
    err_status = _mock_response({"status_code": "ERROR"})
    with patch(
        "bridges.instagram.urllib.request.urlopen",
        side_effect=[container_resp, err_status],
    ), patch("bridges.instagram.time.sleep"):
        bridge = InstagramBridge(token="tok")
        with pytest.raises(InstagramError):
            bridge.post_reel("https://v.mp4", "cap")


def test_post_reel_video_url_required():
    bridge = InstagramBridge(token="tok")
    with pytest.raises(ValueError):
        bridge.post_reel("", "cap")


# ---------- HTTP errors ----------

def test_http_error_wrapped():
    with patch(
        "bridges.instagram.urllib.request.urlopen",
        side_effect=_http_error(400, '{"error":{"message":"bad"}}'),
    ):
        bridge = InstagramBridge(token="tok")
        with pytest.raises(InstagramError) as ei:
            bridge.get_account_info()
    assert ei.value.status == 400


def test_network_error_wrapped():
    with patch(
        "bridges.instagram.urllib.request.urlopen",
        side_effect=urllib.error.URLError("dns"),
    ):
        bridge = InstagramBridge(token="tok")
        with pytest.raises(InstagramError) as ei:
            bridge.get_account_info()
    assert "network error" in str(ei.value)


# ---------- validation ----------

def test_get_media_list_invalid_limit():
    bridge = InstagramBridge(token="tok")
    with pytest.raises(ValueError):
        bridge.get_media_list(limit=0)
    with pytest.raises(ValueError):
        bridge.get_media_list(limit=500)


# ---------- invoke dispatcher ----------

def test_invoke_routes_account_info():
    bridge = InstagramBridge(token=None)
    out = bridge.invoke("get_account_info")
    assert out["username"] == "mock_user"


def test_invoke_unknown_raises():
    bridge = InstagramBridge(token=None)
    with pytest.raises(ValueError):
        bridge.invoke("nope")


def test_token_from_env(monkeypatch):
    monkeypatch.setenv("INSTAGRAM_ACCESS_TOKEN", "envtok")
    bridge = InstagramBridge()
    assert bridge.token == "envtok"
    assert bridge.has_token is True
