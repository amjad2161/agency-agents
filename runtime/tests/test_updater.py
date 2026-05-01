"""Tests for updater (Pass 15)."""
import json
import time
from pathlib import Path
from unittest.mock import patch
import pytest
from agency.updater import get_current_version, check_for_updates


def test_get_current_version():
    v = get_current_version()
    assert isinstance(v, str)
    assert len(v) > 0


def test_check_for_updates_returns_dict(tmp_path):
    cache = tmp_path / "update.json"
    with patch("agency.updater._fetch_latest_pypi", return_value="9.9.9"):
        result = check_for_updates(cache_path=cache)
    assert "current" in result
    assert "latest" in result
    assert "update_available" in result


def test_update_available_when_newer(tmp_path):
    cache = tmp_path / "update.json"
    with patch("agency.updater._fetch_latest_pypi", return_value="9.9.9"):
        result = check_for_updates(cache_path=cache)
    assert result["update_available"] is True
    assert "message" in result


def test_no_update_when_same(tmp_path):
    cache = tmp_path / "update.json"
    current = get_current_version()
    with patch("agency.updater._fetch_latest_pypi", return_value=current):
        result = check_for_updates(cache_path=cache)
    assert result["update_available"] is False


def test_uses_cache(tmp_path):
    cache = tmp_path / "update.json"
    # Write a fresh cache entry
    cache.write_text(json.dumps({"latest": "0.1.0", "checked_at": time.time()}))
    with patch("agency.updater._fetch_latest_pypi", return_value="99.0.0") as mock_fetch:
        result = check_for_updates(cache_path=cache)
    # Cache is fresh — fetch should NOT have been called
    mock_fetch.assert_not_called()
    assert result["latest"] == "0.1.0"


def test_expired_cache_refetches(tmp_path):
    cache = tmp_path / "update.json"
    old_ts = time.time() - 90_000  # 25 hours ago
    cache.write_text(json.dumps({"latest": "0.0.1", "checked_at": old_ts}))
    with patch("agency.updater._fetch_latest_pypi", return_value="1.2.3") as mock_fetch:
        result = check_for_updates(cache_path=cache)
    mock_fetch.assert_called_once()
    assert result["latest"] == "1.2.3"
