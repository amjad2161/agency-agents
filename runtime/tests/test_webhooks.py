"""Tests for WebhookDispatcher (Pass 14)."""
import json
import hashlib
import hmac
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from agency.webhooks import WebhookDispatcher


@pytest.fixture()
def dispatcher(tmp_path):
    return WebhookDispatcher(config_path=tmp_path / "webhooks.json")


def test_empty_list(dispatcher):
    assert dispatcher.list_webhooks() == []


def test_register(dispatcher):
    dispatcher.register("https://example.com/hook", "secret")
    hooks = dispatcher.list_webhooks()
    assert len(hooks) == 1
    assert hooks[0]["url"] == "https://example.com/hook"
    assert hooks[0]["secret"] == "***"


def test_register_update_existing(dispatcher):
    dispatcher.register("https://example.com/hook", "old")
    dispatcher.register("https://example.com/hook", "new")
    assert len(dispatcher.list_webhooks()) == 1


def test_remove(dispatcher):
    dispatcher.register("https://example.com/hook", "s")
    dispatcher.remove("https://example.com/hook")
    assert dispatcher.list_webhooks() == []


def test_dispatch_calls_endpoint(dispatcher, tmp_path):
    dispatcher.register("https://example.com/hook", "mysecret")
    mock_response = MagicMock()
    mock_response.status_code = 200
    with patch("urllib.request.urlopen", return_value=mock_response):
        results = dispatcher.dispatch("test.event", {"key": "value"})
    assert len(results) == 1


def test_dispatch_no_endpoints(dispatcher):
    results = dispatcher.dispatch("test.event", {})
    assert results == []


def test_persistence(tmp_path):
    path = tmp_path / "hooks.json"
    d1 = WebhookDispatcher(config_path=path)
    d1.register("https://a.com", "s1")
    d2 = WebhookDispatcher(config_path=path)
    assert len(d2.list_webhooks()) == 1
