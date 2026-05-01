"""Tests for agency.telegram_bot — TelegramBot (mock mode only)."""

from __future__ import annotations

import pytest

from agency.telegram_bot import TelegramBot


class TestTelegramBotMock:
    """All tests run in mock mode (no real token → no network calls)."""

    def _bot(self) -> TelegramBot:
        return TelegramBot()  # no token → mock=True

    def test_mock_mode_when_no_token(self):
        bot = self._bot()
        assert bot.mock is True

    def test_mock_mode_false_when_token_provided(self):
        bot = TelegramBot(token="fake-token-12345")
        assert bot.mock is False

    def test_send_message_returns_ok(self):
        bot = self._bot()
        result = bot.send_message("Hello from JARVIS")
        assert result["ok"] is True
        assert "result" in result

    def test_send_message_text_in_response(self):
        bot = self._bot()
        text = "Unit test message"
        result = bot.send_message(text)
        assert result["result"]["text"] == text

    def test_send_photo_returns_ok(self):
        bot = self._bot()
        result = bot.send_photo(b"\xff\xd8\xff" + b"\x00" * 20, caption="test")
        assert result["ok"] is True

    def test_send_photo_caption_in_response(self):
        bot = self._bot()
        result = bot.send_photo(b"\x00" * 10, caption="screenshot")
        assert result["result"]["caption"] == "screenshot"

    def test_get_updates_mock_returns_empty_list(self):
        bot = self._bot()
        updates = bot.get_updates()
        assert isinstance(updates, list)
        assert updates == []

    def test_set_webhook_returns_ok(self):
        bot = self._bot()
        result = bot.set_webhook("https://example.com/hook")
        assert result["ok"] is True

    def test_delete_webhook_returns_ok(self):
        bot = self._bot()
        result = bot.delete_webhook()
        assert result["ok"] is True

    def test_get_me_returns_bot_info(self):
        bot = self._bot()
        result = bot.get_me()
        assert result["ok"] is True
        info = result["result"]
        assert info["is_bot"] is True
        assert "username" in info

    def test_env_token_picked_up(self, monkeypatch):
        monkeypatch.setenv("JARVIS_TELEGRAM_TOKEN", "env-token")
        bot = TelegramBot()
        assert bot.token == "env-token"
        assert bot.mock is False

    def test_env_chat_id_picked_up(self, monkeypatch):
        monkeypatch.setenv("JARVIS_TELEGRAM_CHAT_ID", "987654321")
        monkeypatch.delenv("JARVIS_TELEGRAM_TOKEN", raising=False)
        bot = TelegramBot()
        assert bot.chat_id == "987654321"
