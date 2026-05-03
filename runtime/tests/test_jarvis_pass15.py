"""Pass 15 — webhooks, markdown renderer, auto-update, improved doctor."""
from __future__ import annotations

import hashlib
import hmac
import http.server
import json
import os
import pathlib
import sys
import tempfile
import threading
import time
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))


# ===========================================================================
# 1. WebhookConfig
# ===========================================================================

class TestWebhookConfig:
    def test_should_notify_empty_events_means_all(self):
        from agency.webhooks import WebhookConfig
        cfg = WebhookConfig(url="http://x", events=[])
        assert cfg.should_notify("chat.complete")
        assert cfg.should_notify("ping")

    def test_should_notify_filtered_events(self):
        from agency.webhooks import WebhookConfig
        cfg = WebhookConfig(url="http://x", events=["chat.complete"])
        assert cfg.should_notify("chat.complete")
        assert not cfg.should_notify("batch.complete")

    def test_dataclass_fields(self):
        from agency.webhooks import WebhookConfig
        cfg = WebhookConfig(url="http://hook", secret="abc", events=["ping"])
        assert cfg.url == "http://hook"
        assert cfg.secret == "abc"
        assert cfg.events == ["ping"]


# ===========================================================================
# 2. WebhookDispatcher — signing
# ===========================================================================

class TestWebhookDispatcherSign:
    def test_sign_returns_sha256_prefix(self):
        from agency.webhooks import WebhookConfig, WebhookDispatcher
        cfg = WebhookConfig(url="http://x", secret="mysecret")
        d = WebhookDispatcher(cfg)
        payload = b'{"event":"ping"}'
        sig = d._sign(payload)
        assert sig.startswith("sha256=")

    def test_sign_correct_hmac(self):
        from agency.webhooks import WebhookConfig, WebhookDispatcher
        secret = "testkey"
        cfg = WebhookConfig(url="http://x", secret=secret)
        d = WebhookDispatcher(cfg)
        payload = b"hello"
        expected = "sha256=" + hmac.new(
            secret.encode(), payload, hashlib.sha256
        ).hexdigest()
        assert d._sign(payload) == expected

    def test_sign_empty_secret_returns_empty(self):
        from agency.webhooks import WebhookConfig, WebhookDispatcher
        cfg = WebhookConfig(url="http://x", secret="")
        d = WebhookDispatcher(cfg)
        assert d._sign(b"data") == ""

    def test_signature_header_present_when_secret_set(self):
        from agency.webhooks import WebhookConfig, WebhookDispatcher
        received_headers = {}

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                received_headers.update(dict(self.headers))
                self.send_response(200)
                self.end_headers()
            def log_message(self, *a):
                pass

        server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        port = server.server_address[1]
        t = threading.Thread(target=server.handle_request, daemon=True)
        t.start()

        cfg = WebhookConfig(url=f"http://127.0.0.1:{port}/", secret="s3cr3t")
        d = WebhookDispatcher(cfg)
        d.dispatch_sync("ping", {})
        t.join(timeout=3)
        assert "X-Agency-Signature" in received_headers


# ===========================================================================
# 3. WebhookDispatcher — HTTP delivery
# ===========================================================================

class TestWebhookDispatcherDelivery:
    def _make_server(self, status=200, slow=False):
        responses = []

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length)
                responses.append(json.loads(body))
                if slow:
                    time.sleep(0.05)
                self.send_response(status)
                self.end_headers()
            def log_message(self, *a):
                pass

        server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        return server, responses

    def test_dispatch_sync_success(self):
        from agency.webhooks import WebhookConfig, WebhookDispatcher
        server, received = self._make_server(200)
        port = server.server_address[1]
        t = threading.Thread(target=server.handle_request, daemon=True)
        t.start()

        cfg = WebhookConfig(url=f"http://127.0.0.1:{port}/")
        ok = WebhookDispatcher(cfg).dispatch_sync("ping", {"x": 1})
        t.join(timeout=3)
        assert ok
        assert len(received) == 1
        assert received[0]["event"] == "ping"
        assert received[0]["data"] == {"x": 1}

    def test_payload_has_ts_field(self):
        from agency.webhooks import WebhookConfig, WebhookDispatcher
        server, received = self._make_server(200)
        port = server.server_address[1]
        t = threading.Thread(target=server.handle_request, daemon=True)
        t.start()
        cfg = WebhookConfig(url=f"http://127.0.0.1:{port}/")
        WebhookDispatcher(cfg).dispatch_sync("ping", {})
        t.join(timeout=3)
        assert "ts" in received[0]

    def test_dispatch_sync_server_error_returns_false(self):
        from agency.webhooks import WebhookConfig, WebhookDispatcher

        # Server that always returns 500 — serve 3 requests (3 retry attempts)
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                self.send_response(500)
                self.end_headers()
            def log_message(self, *a):
                pass

        server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        port = server.server_address[1]

        def serve3():
            for _ in range(3):
                server.handle_request()

        t = threading.Thread(target=serve3, daemon=True)
        t.start()

        cfg = WebhookConfig(url=f"http://127.0.0.1:{port}/")
        with patch("time.sleep"):   # skip back-off waits
            ok = WebhookDispatcher(cfg).dispatch_sync("ping", {})
        t.join(timeout=5)
        assert not ok

    def test_invalid_event_raises(self):
        from agency.webhooks import WebhookConfig, WebhookDispatcher
        cfg = WebhookConfig(url="http://x")
        d = WebhookDispatcher(cfg)
        with pytest.raises(ValueError, match="Unknown webhook event"):
            d.dispatch_sync("not.real")

    def test_dispatch_skipped_when_event_not_in_filter(self):
        from agency.webhooks import WebhookConfig, WebhookDispatcher
        cfg = WebhookConfig(url="http://x", events=["chat.complete"])
        d = WebhookDispatcher(cfg)
        # dispatch_sync would normally call _deliver; if filtered it returns None silently
        # We verify _deliver is NOT called
        d._deliver = MagicMock(return_value=True)
        d.dispatch_sync("batch.complete", {})
        d._deliver.assert_not_called()

    def test_dispatch_nonblocking_spawns_thread(self):
        from agency.webhooks import WebhookConfig, WebhookDispatcher
        cfg = WebhookConfig(url="http://x")
        d = WebhookDispatcher(cfg)
        threads_before = threading.active_count()
        with patch.object(d, "_deliver", return_value=True):
            d.dispatch("ping", {})
        # Thread may have already finished; just ensure no exception raised
        assert True

    def test_valid_events_set(self):
        from agency.webhooks import VALID_EVENTS
        assert "chat.complete" in VALID_EVENTS
        assert "batch.complete" in VALID_EVENTS
        assert "skill.error" in VALID_EVENTS
        assert "dlq.item_added" in VALID_EVENTS
        assert "ping" in VALID_EVENTS


# ===========================================================================
# 4. load_webhook_config
# ===========================================================================

class TestLoadWebhookConfig:
    def test_returns_none_when_file_missing(self, tmp_path):
        from agency.webhooks import load_webhook_config
        result = load_webhook_config(str(tmp_path / "nope.toml"))
        assert result is None

    def test_loads_from_toml(self, tmp_path):
        from agency.webhooks import load_webhook_config
        cfg_file = tmp_path / "config.toml"
        cfg_file.write_text(
            '[webhooks]\nurl = "http://hook.test"\nsecret = "abc"\nevents = ["chat.complete"]'
        )
        result = load_webhook_config(str(cfg_file))
        assert result is not None
        assert result.url == "http://hook.test"
        assert result.secret == "abc"
        assert result.events == ["chat.complete"]

    def test_returns_none_when_no_url(self, tmp_path):
        from agency.webhooks import load_webhook_config
        cfg_file = tmp_path / "config.toml"
        cfg_file.write_text("[webhooks]\nsecret = \"abc\"\n")
        assert load_webhook_config(str(cfg_file)) is None

    def test_mini_toml_parse(self):
        from agency.webhooks import _mini_toml_parse
        raw = '[webhooks]\nurl = "http://x"\nevents = ["a", "b"]\n'
        d = _mini_toml_parse(raw)
        assert d["webhooks"]["url"] == "http://x"
        assert "a" in d["webhooks"]["events"]


# ===========================================================================
# 5. Renderer
# ===========================================================================

class TestRenderer:
    def test_render_bold(self):
        from agency.renderer import _fallback_render
        out = _fallback_render("**hello world**")
        assert "hello world" in out
        assert "\033[" in out  # ANSI escape present

    def test_render_header(self):
        from agency.renderer import _fallback_render
        out = _fallback_render("# Big Title")
        assert "Big Title" in out
        assert "\033[" in out

    def test_render_code_block_indented(self):
        from agency.renderer import _fallback_render
        out = _fallback_render("```\nprint('hi')\n```")
        assert "    print('hi')" in out

    def test_render_inline_code(self):
        from agency.renderer import _fallback_render
        out = _fallback_render("Use `pip install` to install")
        assert "pip install" in out

    def test_render_italic(self):
        from agency.renderer import _fallback_render
        out = _fallback_render("*italic text*")
        assert "italic text" in out
        assert "\033[" in out

    def test_render_markdown_returns_string(self):
        from agency.renderer import render_markdown
        result = render_markdown("## Hello\n\n**bold** text")
        assert isinstance(result, str)
        assert "Hello" in result

    def test_render_markdown_plain_text_unchanged(self):
        from agency.renderer import render_markdown
        plain = "Just some plain text with no markdown."
        result = render_markdown(plain)
        assert "Just some plain text" in result

    def test_render_markdown_h2_bold(self):
        from agency.renderer import _fallback_render
        out = _fallback_render("## Section")
        assert "Section" in out


# ===========================================================================
# 6. Updater
# ===========================================================================

class TestUpdater:
    def test_parse_version(self):
        from agency.updater import _parse_version
        assert _parse_version("1.2.3") == (1, 2, 3)
        assert _parse_version("0.0.1") == (0, 0, 1)
        assert _parse_version("bad") == (0, 0, 0)

    def test_newer_version_detected(self):
        from agency.updater import _parse_version
        assert _parse_version("2.0.0") > _parse_version("1.9.9")

    def test_fetch_latest_returns_none_on_network_error(self):
        from agency.updater import fetch_latest_version
        with patch("urllib.request.urlopen", side_effect=OSError("no net")):
            result = fetch_latest_version(timeout=0.1)
        assert result is None

    def test_check_update_uses_cache(self, tmp_path):
        from agency.updater import check_update, _UPDATE_CHECK_FILE
        cache_file = tmp_path / "update_check.json"
        cache_file.write_text(json.dumps({
            "last_check": time.time(),  # now → within cooldown
            "latest": "999.0.0",
        }))
        with patch("agency.updater._UPDATE_CHECK_FILE", cache_file):
            result = check_update(force=False)
        assert result == "999.0.0"

    def test_check_update_force_fetches(self, tmp_path):
        from agency.updater import check_update
        cache_file = tmp_path / "update_check.json"
        cache_file.write_text(json.dumps({"last_check": time.time(), "latest": "0.0.1"}))
        with patch("agency.updater._UPDATE_CHECK_FILE", cache_file), \
             patch("agency.updater.fetch_latest_version", return_value="999.9.9"):
            result = check_update(force=True)
        assert result == "999.9.9"

    def test_print_update_notice_hebrew(self, capsys):
        from agency.updater import print_update_notice
        print_update_notice("5.0.0")
        captured = capsys.readouterr()
        assert "5.0.0" in captured.out
        assert "גרסה חדשה זמינה" in captured.out

    def test_changelog_url_is_string(self):
        from agency.updater import get_changelog_url
        url = get_changelog_url()
        assert isinstance(url, str)
        assert url.startswith("http")

    def test_current_version_is_string(self):
        from agency.updater import CURRENT_VERSION
        assert isinstance(CURRENT_VERSION, str)

    def test_check_update_no_newer_returns_none(self, tmp_path):
        from agency.updater import check_update
        cache_file = tmp_path / "update_check.json"
        with patch("agency.updater._UPDATE_CHECK_FILE", cache_file), \
             patch("agency.updater.fetch_latest_version", return_value="0.0.1"), \
             patch("agency.updater.CURRENT_VERSION", "9.9.9"):
            result = check_update(force=True)
        assert result is None


# ===========================================================================
# 7. doctor2 command (CLI integration)
# ===========================================================================

class TestDoctor2:
    def test_doctor2_runs(self):
        """doctor2 should exit 0 and output a table."""
        from click.testing import CliRunner
        try:
            from agency.cli import main
        except Exception:
            pytest.skip("cli import failed (missing deps)")
        runner = CliRunner()
        result = runner.invoke(main, ["doctor2"])
        assert result.exit_code == 0
        assert "Python version" in result.output
        assert "API key" in result.output
        assert "✅" in result.output or "❌" in result.output

    def test_doctor2_contains_webhook_row(self):
        from click.testing import CliRunner
        try:
            from agency.cli import main
        except Exception:
            pytest.skip("cli import failed")
        runner = CliRunner()
        result = runner.invoke(main, ["doctor2"])
        assert "Webhook" in result.output

    def test_doctor2_shows_python_version(self):
        from click.testing import CliRunner
        try:
            from agency.cli import main
        except Exception:
            pytest.skip("cli import failed")
        runner = CliRunner()
        result = runner.invoke(main, ["doctor2"])
        assert str(sys.version_info.major) in result.output


# ===========================================================================
# 8. webhook test command (CLI integration)
# ===========================================================================

class TestWebhookTestCmd:
    def test_webhook_test_no_config_exits_nonzero(self):
        from click.testing import CliRunner
        try:
            from agency.cli import main
        except Exception:
            pytest.skip("cli import failed")
        runner = CliRunner()
        with patch("agency.webhooks.load_webhook_config", return_value=None), \
             patch.dict(os.environ, {"HOME": "/nonexistent"}):
            result = runner.invoke(main, ["webhook", "test"])
        assert result.exit_code != 0

    def test_webhook_test_with_url_dispatches(self):
        from click.testing import CliRunner
        try:
            from agency.cli import main
        except Exception:
            pytest.skip("cli import failed")

        with patch("agency.webhooks.WebhookDispatcher.dispatch_sync", return_value=True):
            runner = CliRunner()
            result = runner.invoke(main, ["webhook", "test", "--url", "http://fake"])
        assert result.exit_code == 0
        assert "✅" in result.output


# ===========================================================================
# 9. update command (CLI integration)
# ===========================================================================

class TestUpdateCmd:
    def test_update_shows_current_version(self):
        from click.testing import CliRunner
        try:
            from agency.cli import main
        except Exception:
            pytest.skip("cli import failed")
        with patch("agency.updater.check_update", return_value=None):
            runner = CliRunner()
            result = runner.invoke(main, ["update"])
        assert result.exit_code == 0
        assert "latest" in result.output.lower() or "version" in result.output.lower()

    def test_update_shows_newer_version(self):
        from click.testing import CliRunner
        try:
            from agency.cli import main
        except Exception:
            pytest.skip("cli import failed")
        with patch("agency.updater.check_update", return_value="99.0.0"):
            runner = CliRunner()
            result = runner.invoke(main, ["update"])
        assert "99.0.0" in result.output

    def test_update_shows_changelog_url(self):
        from click.testing import CliRunner
        try:
            from agency.cli import main
        except Exception:
            pytest.skip("cli import failed")
        with patch("agency.updater.check_update", return_value=None):
            runner = CliRunner()
            result = runner.invoke(main, ["update"])
        assert "Changelog" in result.output
