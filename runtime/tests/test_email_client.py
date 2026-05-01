"""Tests for email_client.py — EmailClient (mock mode)."""

from __future__ import annotations

import pytest

from agency.email_client import EmailClient


@pytest.fixture
def client():
    # No env vars set → mock mode
    return EmailClient(config={})


def test_mode_is_mock(client):
    assert client.mode == "mock"


def test_send_returns_dict(client):
    result = client.send("user@example.com", "Test Subject", "Hello body")
    assert isinstance(result, dict)


def test_send_status_mock(client):
    result = client.send("a@b.com", "S", "B")
    assert result["status"] == "mock"


def test_send_has_message_id(client):
    result = client.send("a@b.com", "S", "B")
    assert "message_id" in result
    assert result["message_id"].startswith("<")


def test_fetch_inbox_returns_list(client):
    msgs = client.fetch_inbox()
    assert isinstance(msgs, list)


def test_fetch_inbox_default_has_items(client):
    msgs = client.fetch_inbox()
    assert len(msgs) > 0


def test_fetch_inbox_fields(client):
    msgs = client.fetch_inbox(unread_only=False)
    for msg in msgs:
        assert "from" in msg
        assert "subject" in msg
        assert "uid" in msg


def test_fetch_inbox_unread_only(client):
    # Initially all mocked messages are unread
    msgs = client.fetch_inbox(unread_only=True)
    assert all(not m.get("read", False) for m in msgs)


def test_fetch_inbox_limit(client):
    msgs = client.fetch_inbox(limit=1)
    assert len(msgs) <= 1


def test_mark_read_returns_true(client):
    msgs = client.fetch_inbox(unread_only=False)
    uid = msgs[0]["uid"]
    result = client.mark_read(uid)
    assert result is True


def test_mark_read_affects_unread_filter(client):
    msgs = client.fetch_inbox(unread_only=False)
    uid = msgs[0]["uid"]
    client.mark_read(uid)
    unread = client.fetch_inbox(unread_only=True)
    assert not any(m["uid"] == uid for m in unread)


def test_mark_read_nonexistent_returns_false(client):
    result = client.mark_read(999999)
    assert result is False


def test_delete_returns_true(client):
    msgs = client.fetch_inbox(unread_only=False)
    uid = msgs[0]["uid"]
    result = client.delete(uid)
    assert result is True


def test_delete_removes_message(client):
    msgs_before = client.fetch_inbox(unread_only=False)
    uid = msgs_before[0]["uid"]
    client.delete(uid)
    msgs_after = client.fetch_inbox(unread_only=False)
    assert not any(m["uid"] == uid for m in msgs_after)


def test_delete_nonexistent_returns_false(client):
    result = client.delete(999999)
    assert result is False


def test_live_mode_requires_config():
    """Client with credentials switches to live mode (don't actually connect)."""
    c = EmailClient(config={
        "user": "test@example.com",
        "password": "secret",
        "smtp_host": "smtp.example.com",
        "imap_host": "imap.example.com",
    })
    assert c.mode == "live"
