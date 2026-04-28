"""Pass 12 tests — config file, retry/backoff, chat history, token tracking.

Run:
    cd runtime && PYTHONPYCACHEPREFIX=/tmp/fresh_pycache \
        python -m pytest tests/test_jarvis_pass12.py -q --tb=short --timeout=60
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import types
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _agency_dir_tmp(tmp_path: Path) -> Path:
    d = tmp_path / ".agency"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ===========================================================================
# 1. AgencyConfig — loading
# ===========================================================================

class TestAgencyConfigLoad:

    def test_load_returns_default_when_no_file(self, tmp_path):
        from agency.config import AgencyConfig
        cfg = AgencyConfig._from_file(tmp_path / "nonexistent.toml")
        assert cfg.model is None
        assert cfg.max_tokens is None

    def test_load_from_json(self, tmp_path):
        from agency.config import AgencyConfig
        p = tmp_path / "config.json"
        p.write_text(json.dumps({"model": "claude-haiku-4-5", "max_tokens": 4096}))
        cfg = AgencyConfig._from_file(p)
        assert cfg.model == "claude-haiku-4-5"
        assert cfg.max_tokens == 4096

    def test_load_from_toml_minimal_parser(self, tmp_path):
        from agency.config import AgencyConfig
        p = tmp_path / "config.toml"
        p.write_text('model = "claude-sonnet-4-6"\nmax_tokens = "8192"\n')
        cfg = AgencyConfig._from_file(p)
        assert cfg.model == "claude-sonnet-4-6"
        assert cfg.max_tokens == 8192

    def test_load_auto_detects_toml_before_json(self, tmp_path):
        from agency.config import AgencyConfig
        toml_p = tmp_path / "config.toml"
        json_p = tmp_path / "config.json"
        toml_p.write_text('model = "from-toml"\n')
        json_p.write_text(json.dumps({"model": "from-json"}))
        with patch("agency.config.config_path_toml", return_value=toml_p), \
             patch("agency.config.config_path_json", return_value=json_p):
            cfg = AgencyConfig.load()
        assert cfg.model == "from-toml"

    def test_load_falls_back_to_json_when_no_toml(self, tmp_path):
        from agency.config import AgencyConfig
        json_p = tmp_path / "config.json"
        json_p.write_text(json.dumps({"model": "from-json"}))
        with patch("agency.config.config_path_toml", return_value=tmp_path / "nope.toml"), \
             patch("agency.config.config_path_json", return_value=json_p):
            cfg = AgencyConfig.load()
        assert cfg.model == "from-json"

    def test_load_returns_empty_when_no_files(self, tmp_path):
        from agency.config import AgencyConfig
        with patch("agency.config.config_path_toml", return_value=tmp_path / "nope.toml"), \
             patch("agency.config.config_path_json", return_value=tmp_path / "nope.json"):
            cfg = AgencyConfig.load()
        assert cfg.model is None

    def test_unknown_keys_stored_in_hidden_dict(self, tmp_path):
        from agency.config import AgencyConfig
        p = tmp_path / "config.json"
        p.write_text(json.dumps({"model": "opus", "future_key": "foo"}))
        cfg = AgencyConfig._from_file(p)
        assert cfg._unknown.get("future_key") == "foo"

    def test_invalid_json_returns_default(self, tmp_path):
        from agency.config import AgencyConfig
        p = tmp_path / "config.json"
        p.write_text("{bad json}")
        cfg = AgencyConfig._from_file(p)
        assert cfg.model is None

    def test_temperature_parsed_as_float(self, tmp_path):
        from agency.config import AgencyConfig
        p = tmp_path / "config.json"
        p.write_text(json.dumps({"temperature": 0.7}))
        cfg = AgencyConfig._from_file(p)
        assert cfg.temperature == pytest.approx(0.7)

    def test_trust_mode_parsed(self, tmp_path):
        from agency.config import AgencyConfig
        p = tmp_path / "config.json"
        p.write_text(json.dumps({"trust_mode": "on-my-machine"}))
        cfg = AgencyConfig._from_file(p)
        assert cfg.trust_mode == "on-my-machine"


# ===========================================================================
# 2. AgencyConfig — save / round-trip
# ===========================================================================

class TestAgencyConfigSave:

    def test_save_toml_round_trip(self, tmp_path):
        from agency.config import AgencyConfig
        cfg = AgencyConfig(model="opus", max_tokens=1000, temperature=0.5)
        path = tmp_path / "out.toml"
        cfg.save_toml(path)
        reloaded = AgencyConfig._from_file(path)
        assert reloaded.model == "opus"
        assert reloaded.max_tokens == 1000

    def test_save_json_round_trip(self, tmp_path):
        from agency.config import AgencyConfig
        cfg = AgencyConfig(model="haiku", max_tokens=512, backend_url="http://localhost")
        path = tmp_path / "out.json"
        cfg.save_json(path)
        reloaded = AgencyConfig._from_file(path)
        assert reloaded.model == "haiku"
        assert reloaded.max_tokens == 512
        assert reloaded.backend_url == "http://localhost"

    def test_save_toml_skips_none_fields(self, tmp_path):
        from agency.config import AgencyConfig
        cfg = AgencyConfig(model="test")
        path = tmp_path / "out.toml"
        cfg.save_toml(path)
        content = path.read_text()
        assert "temperature" not in content
        assert "backend_url" not in content


# ===========================================================================
# 3. AgencyConfig — override precedence
# ===========================================================================

class TestAgencyConfigPrecedence:

    def test_env_beats_config_file(self, tmp_path):
        from agency.config import AgencyConfig
        from agency.llm import LLMConfig, DEFAULT_MODEL
        # Simulate: env has AGENCY_MODEL set, config file has different model
        p = tmp_path / "config.json"
        p.write_text(json.dumps({"model": "config-model"}))
        cfg_file = AgencyConfig._from_file(p)
        with patch.dict(os.environ, {"AGENCY_MODEL": "env-model"}, clear=False):
            llm_cfg = LLMConfig.from_env()
        # After from_env(), llm_cfg.model is "env-model"
        # apply_to_llm_config should NOT override it
        cfg_file.apply_to_llm_config(llm_cfg)
        assert llm_cfg.model == "env-model"

    def test_config_file_beats_default_when_no_env(self, tmp_path):
        from agency.config import AgencyConfig
        from agency.llm import LLMConfig, DEFAULT_MODEL
        p = tmp_path / "config.json"
        p.write_text(json.dumps({"model": "config-model"}))
        cfg_file = AgencyConfig._from_file(p)
        with patch.dict(os.environ, {}, clear=False):
            # ensure AGENCY_MODEL not set
            env_bak = os.environ.pop("AGENCY_MODEL", None)
            try:
                llm_cfg = LLMConfig.from_env()
                assert llm_cfg.model == DEFAULT_MODEL  # default before apply
                cfg_file.apply_to_llm_config(llm_cfg)
                assert llm_cfg.model == "config-model"
            finally:
                if env_bak is not None:
                    os.environ["AGENCY_MODEL"] = env_bak


# ===========================================================================
# 4. Retry / backoff logic
# ===========================================================================

def _make_exc(status_code: int) -> Exception:
    """Create a mock exception with a given status_code attribute."""
    exc = Exception(f"HTTP {status_code}")
    exc.status_code = status_code
    return exc


class TestRetryBackoff:

    def test_backoff_delay_increases(self):
        from agency.llm import _backoff_delay
        with patch("random.uniform", return_value=0.0):
            d0 = _backoff_delay(0)
            d1 = _backoff_delay(1)
            d2 = _backoff_delay(2)
        assert d0 < d1 < d2

    def test_is_retryable_rate_limit_429(self):
        from agency.llm import _is_retryable_rate_limit
        assert _is_retryable_rate_limit(_make_exc(429))

    def test_is_retryable_rate_limit_529(self):
        from agency.llm import _is_retryable_rate_limit
        assert _is_retryable_rate_limit(_make_exc(529))

    def test_is_not_retryable_404(self):
        from agency.llm import _is_retryable_rate_limit
        assert not _is_retryable_rate_limit(_make_exc(404))

    def test_is_retryable_server_error_500(self):
        from agency.llm import _is_retryable_server_error
        assert _is_retryable_server_error(_make_exc(500))

    def test_is_retryable_server_error_503(self):
        from agency.llm import _is_retryable_server_error
        assert _is_retryable_server_error(_make_exc(503))

    def test_529_not_counted_as_server_error(self):
        from agency.llm import _is_retryable_server_error
        assert not _is_retryable_server_error(_make_exc(529))

    def test_is_auth_error_401(self):
        from agency.llm import _is_auth_error
        assert _is_auth_error(_make_exc(401))

    def test_call_with_retry_succeeds_immediately(self):
        from agency.llm import _call_with_retry
        fn = MagicMock(return_value="ok")
        result = _call_with_retry(fn, "arg")
        assert result == "ok"
        fn.assert_called_once_with("arg")

    def test_call_with_retry_retries_429(self):
        from agency.llm import _call_with_retry, _RETRY_RATE_LIMIT_MAX
        call_count = 0

        def flaky():
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise _make_exc(429)
            return "success"

        with patch("time.sleep"):  # don't actually sleep
            result = _call_with_retry(flaky)
        assert result == "success"
        assert call_count == 3

    def test_call_with_retry_raises_after_max_429(self):
        from agency.llm import _call_with_retry, _RETRY_RATE_LIMIT_MAX
        exc = _make_exc(429)

        def always_429():
            raise exc

        with patch("time.sleep"), pytest.raises(Exception) as exc_info:
            _call_with_retry(always_429)
        assert exc_info.value is exc

    def test_call_with_retry_raises_hebrew_on_401(self):
        from agency.llm import _call_with_retry, LLMError

        def auth_fail():
            raise _make_exc(401)

        with pytest.raises(LLMError) as exc_info:
            _call_with_retry(auth_fail)
        # Hebrew error message
        assert "API" in str(exc_info.value) or "אימות" in str(exc_info.value)

    def test_call_with_retry_retries_500_twice(self):
        from agency.llm import _call_with_retry
        call_count = 0

        def flaky():
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise _make_exc(500)
            return "ok"

        with patch("time.sleep"):
            result = _call_with_retry(flaky)
        assert result == "ok"
        assert call_count == 3

    def test_call_with_retry_raises_after_max_500(self):
        from agency.llm import _call_with_retry, _RETRY_SERVER_ERROR_MAX

        def always_500():
            raise _make_exc(500)

        with patch("time.sleep"), pytest.raises(Exception):
            _call_with_retry(always_500)

    def test_non_retryable_404_raises_immediately(self):
        from agency.llm import _call_with_retry
        call_count = 0

        def four_oh_four():
            nonlocal call_count
            call_count += 1
            raise _make_exc(404)

        with pytest.raises(Exception):
            _call_with_retry(four_oh_four)
        assert call_count == 1  # no retries


# ===========================================================================
# 5. HistoryWriter
# ===========================================================================

class TestHistoryWriter:

    def test_context_manager_creates_file(self, tmp_path):
        from agency.history import HistoryWriter
        p = tmp_path / "session.jsonl"
        with HistoryWriter(path=p) as hw:
            hw.append("user", "hello")
        assert p.exists()

    def test_appends_valid_jsonl(self, tmp_path):
        from agency.history import HistoryWriter
        p = tmp_path / "session.jsonl"
        with HistoryWriter(path=p) as hw:
            hw.append("user", "test message")
            hw.append("assistant", "test reply")
        lines = p.read_text().strip().splitlines()
        assert len(lines) == 2
        obj = json.loads(lines[0])
        assert obj["role"] == "user"
        assert obj["content"] == "test message"
        assert "timestamp" in obj

    def test_fallback_append_without_context_manager(self, tmp_path):
        from agency.history import HistoryWriter
        p = tmp_path / "session2.jsonl"
        hw = HistoryWriter(path=p)
        hw.append("user", "standalone")
        lines = p.read_text().strip().splitlines()
        assert len(lines) == 1

    def test_list_sessions_newest_first(self, tmp_path):
        from agency.history import list_sessions, history_dir
        with patch("agency.history.history_dir", return_value=tmp_path):
            (tmp_path / "2026-01-01_100000.jsonl").write_text("")
            (tmp_path / "2026-01-02_100000.jsonl").write_text("")
            sessions = list_sessions(limit=5)
        assert sessions[0].name > sessions[1].name

    def test_read_session_parses_messages(self, tmp_path):
        from agency.history import HistoryWriter, read_session
        p = tmp_path / "s.jsonl"
        with HistoryWriter(path=p) as hw:
            hw.append("user", "q")
            hw.append("assistant", "a")
        msgs = read_session(p)
        assert len(msgs) == 2
        assert msgs[0]["role"] == "user"
        assert msgs[1]["role"] == "assistant"

    def test_session_summary_format(self, tmp_path):
        from agency.history import HistoryWriter, session_summary
        p = tmp_path / "2026-04-28_120000.jsonl"
        with HistoryWriter(path=p) as hw:
            hw.append("user", "what is the meaning of life")
            hw.append("assistant", "42")
        summary = session_summary(p)
        assert "2026-04-28" in summary
        assert "2 turns" in summary
        assert "what is" in summary


# ===========================================================================
# 6. Stats tracking
# ===========================================================================

class TestTokenStats:

    def _fresh_stats_path(self, tmp_path):
        return tmp_path / "stats.json"

    def test_record_usage_accumulates(self, tmp_path):
        from agency.stats import record_usage, get_stats
        stats_file = tmp_path / "stats.json"
        with patch("agency.stats.stats_path", return_value=stats_file):
            record_usage({"input_tokens": 100, "output_tokens": 50})
            record_usage({"input_tokens": 200, "output_tokens": 80})
            data = get_stats()
        assert data["input_tokens"] == 300
        assert data["output_tokens"] == 130
        assert data["total_calls"] == 2

    def test_record_usage_sdk_object(self, tmp_path):
        from agency.stats import record_usage, get_stats
        stats_file = tmp_path / "stats.json"
        usage = MagicMock()
        usage.input_tokens = 10
        usage.output_tokens = 5
        usage.cache_creation_input_tokens = 0
        usage.cache_read_input_tokens = 0
        with patch("agency.stats.stats_path", return_value=stats_file):
            record_usage(usage)
            data = get_stats()
        assert data["input_tokens"] == 10
        assert data["output_tokens"] == 5

    def test_reset_stats(self, tmp_path):
        from agency.stats import record_usage, reset_stats, get_stats
        stats_file = tmp_path / "stats.json"
        with patch("agency.stats.stats_path", return_value=stats_file):
            record_usage({"input_tokens": 999, "output_tokens": 1})
            reset_stats()
            data = get_stats()
        assert data["input_tokens"] == 0
        assert data["total_calls"] == 0

    def test_format_stats_includes_keys(self, tmp_path):
        from agency.stats import format_stats
        data = {
            "input_tokens": 1000,
            "output_tokens": 500,
            "cache_creation_input_tokens": 200,
            "cache_read_input_tokens": 50,
            "total_calls": 5,
            "first_call": "2026-01-01T00:00:00",
            "last_call": "2026-01-02T00:00:00",
        }
        out = format_stats(data)
        assert "1,000" in out or "1000" in out
        assert "total" in out.lower() and "calls" in out.lower()

    def test_stats_first_last_call_set(self, tmp_path):
        from agency.stats import record_usage, get_stats
        stats_file = tmp_path / "stats.json"
        with patch("agency.stats.stats_path", return_value=stats_file):
            record_usage({"input_tokens": 1, "output_tokens": 1})
            data = get_stats()
        assert data["first_call"] is not None
        assert data["last_call"] is not None

    def test_stats_file_persisted_as_json(self, tmp_path):
        from agency.stats import record_usage
        stats_file = tmp_path / "stats.json"
        with patch("agency.stats.stats_path", return_value=stats_file):
            record_usage({"input_tokens": 7, "output_tokens": 3})
        raw = json.loads(stats_file.read_text())
        assert raw["input_tokens"] == 7


# ===========================================================================
# 7. CLI commands — history & stats (smoke tests via subprocess not needed;
#    test through module imports to keep it fast and offline)
# ===========================================================================

class TestCLISmoke:

    def test_config_module_importable(self):
        from agency.config import AgencyConfig, agency_dir
        assert AgencyConfig is not None

    def test_history_module_importable(self):
        from agency.history import HistoryWriter, list_sessions, read_session
        assert HistoryWriter is not None

    def test_stats_module_importable(self):
        from agency.stats import record_usage, get_stats, reset_stats, format_stats
        assert record_usage is not None

    def test_llm_module_has_call_with_retry(self):
        from agency.llm import _call_with_retry
        assert callable(_call_with_retry)

    def test_llm_module_has_retry_constants(self):
        from agency.llm import (
            _RETRY_RATE_LIMIT_MAX,
            _RETRY_SERVER_ERROR_MAX,
            _RETRY_BASE_DELAY_S,
        )
        assert _RETRY_RATE_LIMIT_MAX >= 3
        assert _RETRY_SERVER_ERROR_MAX >= 2
        assert _RETRY_BASE_DELAY_S > 0

    def test_cli_has_history_command(self):
        """agency CLI must expose `history` group."""
        from agency.cli import main
        assert "history" in main.commands

    def test_cli_has_stats_command(self):
        """agency CLI must expose `stats` command."""
        from agency.cli import main
        assert "stats" in main.commands

    def test_agency_dir_creates_directory(self, tmp_path):
        from agency.config import agency_dir
        with patch("agency.config.Path.home", return_value=tmp_path):
            d = agency_dir()
        assert d.exists()

    def test_history_dir_creates_directory(self, tmp_path):
        from agency.history import history_dir
        with patch("agency.history.Path.home", return_value=tmp_path):
            d = history_dir()
        assert d.exists()
        assert d.name == "history"
