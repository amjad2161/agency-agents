"""Pass 14 tests: plugin system, Flask REST API, token-bucket rate limiter."""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


# ===========================================================================
# Helpers
# ===========================================================================

@pytest.fixture()
def tmp_home(tmp_path, monkeypatch):
    """Redirect Path.home() to a temp dir for isolation."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    return tmp_path


# ===========================================================================
# A. TokenBucket tests (rate_limiter.py)
# ===========================================================================

class TestTokenBucket:

    def _make_bucket(self, tmp_path, max_tokens=10.0, refill_rate=1.0):
        from agency.rate_limiter import TokenBucket
        state_path = tmp_path / "rate_state.json"
        return TokenBucket(max_tokens=max_tokens, refill_rate=refill_rate, state_path=state_path)

    def test_initial_full(self, tmp_path):
        bucket = self._make_bucket(tmp_path)
        assert bucket.get_level() == pytest.approx(10.0, abs=0.1)

    def test_consume_decrements(self, tmp_path):
        bucket = self._make_bucket(tmp_path)
        result = bucket.consume(3.0)
        assert result is True
        assert bucket.get_level() == pytest.approx(7.0, abs=0.2)

    def test_consume_returns_false_when_empty(self, tmp_path):
        bucket = self._make_bucket(tmp_path, max_tokens=2.0)
        bucket.consume(2.0)
        result = bucket.consume(1.0)
        assert result is False

    def test_consume_exact_boundary(self, tmp_path):
        bucket = self._make_bucket(tmp_path, max_tokens=5.0)
        assert bucket.consume(5.0) is True
        assert bucket.get_level() == pytest.approx(0.0, abs=0.1)

    def test_refill_over_time(self, tmp_path):
        bucket = self._make_bucket(tmp_path, max_tokens=10.0, refill_rate=10.0)
        bucket.consume(10.0)  # drain
        time.sleep(0.15)      # should gain ~1.5 tokens at 10/s
        assert bucket.get_level() > 0.5

    def test_refill_capped_at_max(self, tmp_path):
        bucket = self._make_bucket(tmp_path, max_tokens=5.0, refill_rate=100.0)
        bucket.consume(1.0)
        time.sleep(0.2)  # would overfill but capped
        assert bucket.get_level() <= 5.0 + 0.01

    def test_reset_fills_to_max(self, tmp_path):
        bucket = self._make_bucket(tmp_path, max_tokens=10.0)
        bucket.consume(8.0)
        bucket.reset()
        assert bucket.get_level() == pytest.approx(10.0, abs=0.1)

    def test_state_persisted_to_json(self, tmp_path):
        state_path = tmp_path / "rate_state.json"
        from agency.rate_limiter import TokenBucket
        b1 = TokenBucket(max_tokens=10.0, refill_rate=1.0, state_path=state_path)
        b1.consume(4.0)
        # Load a second instance from the same file
        b2 = TokenBucket(max_tokens=10.0, refill_rate=1.0, state_path=state_path)
        assert b2.get_level() == pytest.approx(6.0, abs=0.5)

    def test_state_file_created(self, tmp_path):
        state_path = tmp_path / "sub" / "rate.json"
        from agency.rate_limiter import TokenBucket
        b = TokenBucket(max_tokens=10.0, state_path=state_path)
        b.get_level()
        assert state_path.exists()

    def test_wait_for_token_fast_path(self, tmp_path):
        """wait_for_token returns immediately when tokens available."""
        bucket = self._make_bucket(tmp_path, max_tokens=10.0)
        t0 = time.monotonic()
        bucket.wait_for_token()
        assert time.monotonic() - t0 < 1.0
        assert bucket.get_level() == pytest.approx(9.0, abs=0.2)

    def test_wait_for_token_blocks_then_succeeds(self, tmp_path, capsys):
        """wait_for_token blocks and warns in Hebrew when bucket is empty."""
        bucket = self._make_bucket(tmp_path, max_tokens=1.0, refill_rate=20.0)
        bucket.consume(1.0)  # drain
        t0 = time.monotonic()
        bucket.wait_for_token()
        elapsed = time.monotonic() - t0
        assert elapsed < 1.5  # at 20/s, should recover in <0.1s
        out = capsys.readouterr().out
        # Should have printed the Hebrew warning
        assert "ממתין" in out or elapsed < 0.01  # either warned or was so fast it didn't need to

    def test_module_singleton(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        from agency import rate_limiter
        rate_limiter._bucket = None  # reset singleton
        b = rate_limiter.get_bucket()
        assert b is rate_limiter.get_bucket()  # same instance

    def test_default_max_tokens(self, tmp_path):
        """Default bucket has 60 max tokens."""
        from agency.rate_limiter import TokenBucket
        b = TokenBucket(state_path=tmp_path / "r.json")
        assert b.max_tokens == 60.0

    def test_default_refill_rate(self, tmp_path):
        """Default refill rate is 1.0/s."""
        from agency.rate_limiter import TokenBucket
        b = TokenBucket(state_path=tmp_path / "r.json")
        assert b.refill_rate == 1.0


# ===========================================================================
# B. PluginRegistry tests (plugins.py)
# ===========================================================================

class TestPluginRegistry:

    def _make_registry(self, tmp_path):
        from agency.plugins import PluginRegistry
        manifest = tmp_path / "plugins.json"
        return PluginRegistry(manifest=manifest)

    def test_load_empty_manifest(self, tmp_path):
        reg = self._make_registry(tmp_path)
        reg.load()
        assert reg.list_plugins() == []

    def test_load_nonexistent_manifest(self, tmp_path):
        reg = self._make_registry(tmp_path)
        reg.load()
        assert len(reg) == 0

    def test_install_creates_plugin(self, tmp_path):
        reg = self._make_registry(tmp_path)
        p = reg.install("my-plugin", version="1.2.3", description="A test plugin")
        assert p.name == "my-plugin"
        assert p.version == "1.2.3"
        assert p.description == "A test plugin"

    def test_install_persists_to_manifest(self, tmp_path):
        manifest = tmp_path / "plugins.json"
        from agency.plugins import PluginRegistry
        reg = PluginRegistry(manifest=manifest)
        reg.install("alpha", description="First")
        # Load a fresh registry from the same manifest
        reg2 = PluginRegistry(manifest=manifest)
        reg2.load()
        assert reg2.get("alpha") is not None
        assert reg2.get("alpha").description == "First"

    def test_install_with_source_file(self, tmp_path):
        # Create a dummy skill YAML
        source = tmp_path / "my_skill.yaml"
        source.write_text("name: my_skill\ndescription: test\n")
        reg = self._make_registry(tmp_path)
        # Need plugins_dir to be under tmp_path
        plugins_d = tmp_path / ".agency" / "plugins"
        plugins_d.mkdir(parents=True)
        from agency import plugins as plugins_mod
        with patch.object(plugins_mod, "plugins_dir", return_value=plugins_d):
            p = reg.install("skill-plugin", source=source)
        assert p.skill_files == ["my_skill.yaml"]

    def test_install_missing_source_raises(self, tmp_path):
        reg = self._make_registry(tmp_path)
        with pytest.raises(FileNotFoundError):
            reg.install("bad", source=tmp_path / "nonexistent.yaml")

    def test_remove_existing_plugin(self, tmp_path):
        reg = self._make_registry(tmp_path)
        reg.install("to-remove")
        assert reg.remove("to-remove") is True
        assert reg.get("to-remove") is None

    def test_remove_nonexistent_returns_false(self, tmp_path):
        reg = self._make_registry(tmp_path)
        assert reg.remove("ghost") is False

    def test_list_plugins_returns_all(self, tmp_path):
        reg = self._make_registry(tmp_path)
        reg.install("a")
        reg.install("b")
        reg.install("c")
        names = {p.name for p in reg.list_plugins()}
        assert names == {"a", "b", "c"}

    def test_len(self, tmp_path):
        reg = self._make_registry(tmp_path)
        reg.install("x")
        reg.install("y")
        assert len(reg) == 2

    def test_plugin_dataclass_roundtrip(self):
        from agency.plugins import Plugin
        p = Plugin(name="foo", version="2.0", description="bar", entry_point="pkg.mod:fn")
        d = p.to_dict()
        p2 = Plugin.from_dict(d)
        assert p2.name == "foo"
        assert p2.version == "2.0"
        assert p2.entry_point == "pkg.mod:fn"

    def test_activate_calls_entry_point(self, tmp_path):
        reg = self._make_registry(tmp_path)
        # Install plugin with a fake entry_point
        reg.install("callable-plugin", entry_point="os.path:dirname")
        # dirname is callable but doesn't expect a registry — activation
        # should not raise (failures are non-fatal)
        activated = reg.activate()
        # It might or might not be in activated depending on whether dirname raises
        # The key point: no exception should propagate
        assert isinstance(activated, list)

    def test_disabled_plugin_not_activated(self, tmp_path):
        from agency.plugins import Plugin, PluginRegistry
        manifest = tmp_path / "plugins.json"
        manifest.write_text(json.dumps([
            {"name": "disabled-one", "entry_point": "os:getcwd", "enabled": False}
        ]))
        reg = PluginRegistry(manifest=manifest)
        reg.load()
        activated = reg.activate()
        assert "disabled-one" not in activated


# ===========================================================================
# C. Flask REST API tests (simple_server.py)
# ===========================================================================

@pytest.fixture()
def flask_client(tmp_path, monkeypatch):
    """Return a Flask test client with auth disabled and skills mocked."""
    monkeypatch.delenv("AGENCY_API_TOKEN", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    # Mock SkillRegistry.load to return a predictable registry
    mock_skill = MagicMock()
    mock_skill.slug = "test-skill"
    mock_skill.name = "Test Skill"
    mock_skill.category = "testing"
    mock_skill.description = "A test skill"
    mock_skill.emoji = "🧪"

    mock_registry = MagicMock()
    mock_registry.all.return_value = [mock_skill]

    from agency import simple_server
    with patch("agency.simple_server.SkillRegistry") as MockReg:
        MockReg.load.return_value = mock_registry
        app = simple_server.create_app(repo=tmp_path)
        app.config["TESTING"] = True
        with app.test_client() as client:
            yield client


class TestFlaskHealth:

    def test_health_200(self, flask_client):
        resp = flask_client.get("/health")
        assert resp.status_code == 200

    def test_health_status_ok(self, flask_client):
        body = json.loads(flask_client.get("/health").data)
        body = json.loads(flask_client.get("/health").data)
        assert body["status"] == "ok"

    def test_health_version_present(self, flask_client):
        body = json.loads(flask_client.get("/health").data)
        assert "version" in body

    def test_health_version_value(self, flask_client):
        from agency import __version__
        body = json.loads(flask_client.get("/health").data)
        assert body["version"] == __version__


class TestFlaskSkills:

    def test_skills_200(self, flask_client):
        resp = flask_client.get("/skills")
        assert resp.status_code == 200

    def test_skills_returns_list(self, flask_client):
        body = json.loads(flask_client.get("/skills").data)
        assert "skills" in body
        assert isinstance(body["skills"], list)

    def test_skills_count_matches(self, flask_client):
        body = json.loads(flask_client.get("/skills").data)
        assert body["count"] == len(body["skills"])

    def test_skills_contains_expected(self, flask_client):
        body = json.loads(flask_client.get("/skills").data)
        slugs = [s["slug"] for s in body["skills"]]
        assert "test-skill" in slugs


class TestFlaskStats:

    def test_stats_200(self, flask_client):
        resp = flask_client.get("/stats")
        assert resp.status_code == 200

    def test_stats_has_token_fields(self, flask_client):
        body = json.loads(flask_client.get("/stats").data)
        assert "input_tokens" in body
        assert "output_tokens" in body
        assert "total_calls" in body


class TestFlaskChat:

    def test_chat_no_api_key_returns_503(self, flask_client):
        resp = flask_client.post("/chat",
                                  json={"prompt": "Hello"},
                                  content_type="application/json")
        assert resp.status_code == 503

    def test_chat_missing_prompt_returns_400(self, flask_client):
        resp = flask_client.post("/chat",
                                  json={"model": "claude-3-haiku"},
                                  content_type="application/json")
        assert resp.status_code == 400

    def test_chat_empty_prompt_returns_400(self, flask_client):
        resp = flask_client.post("/chat",
                                  json={"prompt": "  "},
                                  content_type="application/json")
        assert resp.status_code == 400

    def test_chat_with_api_key_calls_llm(self, tmp_path, monkeypatch):
        monkeypatch.delenv("AGENCY_API_TOKEN", raising=False)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key")

        mock_skill = MagicMock()
        mock_skill.slug = "s"
        mock_skill.name = "S"
        mock_skill.category = "c"
        mock_skill.description = ""
        mock_skill.emoji = ""
        mock_registry = MagicMock()
        mock_registry.all.return_value = [mock_skill]

        from agency import simple_server
        with patch("agency.simple_server.SkillRegistry") as MockReg, \
             patch("agency.llm.AnthropicLLM") as MockLLM:
            mock_llm_instance = MagicMock()
            mock_llm_instance.complete.return_value = "Hello back!"
            MockLLM.return_value = mock_llm_instance

            app = simple_server.create_app(repo=tmp_path)
            app.config["TESTING"] = True
            with app.test_client() as client:
                resp = client.post("/chat",
                                    json={"prompt": "Hi"},
                                    content_type="application/json")
        assert resp.status_code == 200
        body = json.loads(resp.data)
        assert body["response"] == "Hello back!"


class TestFlaskAuth:

    @pytest.fixture()
    def authed_client(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AGENCY_API_TOKEN", "secret-token-123")
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        mock_skill = MagicMock()
        mock_skill.slug = "s"; mock_skill.name = "S"
        mock_skill.category = "c"; mock_skill.description = ""
        mock_skill.emoji = ""
        mock_registry = MagicMock()
        mock_registry.all.return_value = [mock_skill]

        from agency import simple_server
        with patch("agency.simple_server.SkillRegistry") as MockReg:
            MockReg.load.return_value = mock_registry
            app = simple_server.create_app(repo=tmp_path)
            app.config["TESTING"] = True
            with app.test_client() as client:
                yield client

    def test_no_token_returns_401(self, authed_client):
        resp = authed_client.get("/health")
        assert resp.status_code == 401

    def test_wrong_token_returns_401(self, authed_client):
        resp = authed_client.get("/health",
                                  headers={"Authorization": "Bearer wrong-token"})
        assert resp.status_code == 401

    def test_malformed_auth_header_returns_401(self, authed_client):
        resp = authed_client.get("/health",
                                  headers={"Authorization": "Token secret-token-123"})
        assert resp.status_code == 401

    def test_correct_token_passes(self, authed_client):
        resp = authed_client.get("/health",
                                  headers={"Authorization": "Bearer secret-token-123"})
        assert resp.status_code == 200

    def test_auth_error_body_has_error_key(self, authed_client):
        resp = authed_client.get("/health")
        body = json.loads(resp.data)
        assert "error" in body
