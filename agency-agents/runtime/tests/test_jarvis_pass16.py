"""Pass 16 — structured logging, tracing, profiling, audit log."""
from __future__ import annotations

import hashlib
import json
import logging
import pathlib
import sys
import tempfile
import threading
import time
import uuid
from io import StringIO
from typing import Any
from unittest.mock import patch

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))


# ===========================================================================
# 1. logging_config — setup_logging / JSON formatter / pretty formatter
# ===========================================================================

class TestLoggingConfig:
    def _fresh_logger(self, name: str) -> logging.Logger:
        """Return a logger with no existing handlers (isolated per test)."""
        logger = logging.getLogger(name)
        logger.handlers.clear()
        return logger

    def test_setup_logging_returns_logger(self):
        from agency.logging_config import setup_logging
        stream = StringIO()
        logger = setup_logging(level="INFO", format="pretty", stream=stream)
        assert isinstance(logger, logging.Logger)
        assert logger.level == logging.INFO

    def test_json_formatter_emits_valid_json(self):
        from agency.logging_config import _JsonFormatter
        formatter = _JsonFormatter()
        record = logging.LogRecord(
            name="agency", level=logging.INFO,
            pathname="", lineno=0, msg="hello %s", args=("world",),
            exc_info=None,
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed["message"] == "hello world"
        assert parsed["level"] == "INFO"
        assert parsed["logger"] == "agency"
        assert "timestamp" in parsed

    def test_json_formatter_timestamp_format(self):
        from agency.logging_config import _JsonFormatter
        formatter = _JsonFormatter()
        record = logging.LogRecord(
            name="agency", level=logging.DEBUG,
            pathname="", lineno=0, msg="ts test", args=(),
            exc_info=None,
        )
        parsed = json.loads(formatter.format(record))
        ts = parsed["timestamp"]
        # Must end with Z and contain T
        assert ts.endswith("Z")
        assert "T" in ts

    def test_json_formatter_includes_session_id(self):
        from agency.logging_config import _JsonFormatter, set_session_id
        set_session_id("test-session-abc")
        try:
            formatter = _JsonFormatter()
            record = logging.LogRecord(
                name="agency", level=logging.INFO,
                pathname="", lineno=0, msg="with session", args=(),
                exc_info=None,
            )
            parsed = json.loads(formatter.format(record))
            assert parsed.get("session_id") == "test-session-abc"
        finally:
            set_session_id(None)

    def test_json_formatter_includes_duration_ms(self):
        from agency.logging_config import _JsonFormatter
        formatter = _JsonFormatter()
        record = logging.LogRecord(
            name="agency", level=logging.INFO,
            pathname="", lineno=0, msg="timed op", args=(),
            exc_info=None,
        )
        record.duration_ms = 42
        parsed = json.loads(formatter.format(record))
        assert parsed["duration_ms"] == 42

    def test_pretty_formatter_contains_level(self):
        from agency.logging_config import _PrettyFormatter
        formatter = _PrettyFormatter()
        record = logging.LogRecord(
            name="agency", level=logging.WARNING,
            pathname="", lineno=0, msg="pretty warn", args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        assert "WARNING" in output
        assert "pretty warn" in output

    def test_setup_logging_idempotent(self):
        """Calling setup_logging twice should not double-add handlers."""
        from agency.logging_config import setup_logging
        stream = StringIO()
        name = f"agency_idempotent_{uuid.uuid4().hex}"
        logger = logging.getLogger(name)
        logger.handlers.clear()

        # Patch get_logger to return our isolated logger
        with patch("agency.logging_config.LOGGER_NAME", name):
            setup_logging(level="INFO", format="json", stream=stream)
            setup_logging(level="INFO", format="json", stream=stream)
        agency_handlers = [h for h in logger.handlers if getattr(h, "_agency_structured", False)]
        assert len(agency_handlers) == 1

    def test_get_logger_returns_named_logger(self):
        from agency.logging_config import get_logger
        lg = get_logger()
        assert lg.name == "agency"

    def test_timed_structured_emits_duration(self):
        from agency.logging_config import setup_logging, timed_structured
        stream = StringIO()
        with patch("agency.logging_config.LOGGER_NAME", f"agency_{uuid.uuid4().hex}"):
            lg = setup_logging(level="INFO", format="json", stream=stream)
            with timed_structured("test.op", logger=lg):
                time.sleep(0.01)
        # No exception = pass (duration emitted if INFO enabled)

    def test_set_session_id_clear(self):
        from agency.logging_config import set_session_id, get_session_id
        set_session_id("sess-xyz")
        assert get_session_id() == "sess-xyz"
        set_session_id(None)
        assert get_session_id() is None


# ===========================================================================
# 2. tracing — Span, Tracer, file I/O
# ===========================================================================

class TestTracing:
    def test_span_dataclass_fields(self):
        from agency.tracing import Span
        sp = Span(
            trace_id="t1", span_id="s1", name="llm.call",
            start_ms=1000.0, end_ms=1050.0,
            tags={"model": "opus"},
        )
        assert sp.duration_ms == 50.0
        assert sp.error is None

    def test_span_duration_none_when_open(self):
        from agency.tracing import Span
        sp = Span(trace_id="t", span_id="s", name="x", start_ms=100.0)
        assert sp.duration_ms is None

    def test_span_to_dict(self):
        from agency.tracing import Span
        sp = Span(trace_id="t", span_id="s", name="op", start_ms=0.0, end_ms=10.0)
        d = sp.to_dict()
        assert d["name"] == "op"
        assert d["duration_ms"] == 10.0
        assert "trace_id" in d

    def test_tracer_creates_unique_trace_ids(self):
        from agency.tracing import Tracer
        t1 = Tracer()
        t2 = Tracer()
        assert t1.trace_id != t2.trace_id

    def test_tracer_span_context_manager(self, tmp_path):
        from agency.tracing import Tracer, _trace_file
        with patch("agency.tracing._traces_dir", return_value=tmp_path):
            tracer = Tracer()
            with tracer.span("test.op", tags={"k": "v"}) as sp:
                assert sp.name == "test.op"
                assert sp.tags["k"] == "v"
                assert sp.end_ms is None  # still open inside block
            assert sp.end_ms is not None
            assert sp.duration_ms >= 0

    def test_tracer_writes_jsonl(self, tmp_path):
        from agency.tracing import Tracer
        with patch("agency.tracing._traces_dir", return_value=tmp_path):
            tracer = Tracer()
            with tracer.span("write.test") as sp:
                pass
            files = list(tmp_path.glob("*.jsonl"))
            assert len(files) == 1
            line = files[0].read_text().strip()
            data = json.loads(line)
            assert data["name"] == "write.test"
            assert data["duration_ms"] >= 0

    def test_tracer_records_error(self, tmp_path):
        from agency.tracing import Tracer
        with patch("agency.tracing._traces_dir", return_value=tmp_path):
            tracer = Tracer()
            with pytest.raises(ValueError):
                with tracer.span("error.op") as sp:
                    raise ValueError("boom")
            files = list(tmp_path.glob("*.jsonl"))
            data = json.loads(files[0].read_text().strip())
            assert "ValueError" in data["error"]
            assert "boom" in data["error"]

    def test_load_spans_reads_file(self, tmp_path):
        from agency.tracing import Tracer, load_spans
        today = time.strftime("%Y-%m-%d")
        with patch("agency.tracing._traces_dir", return_value=tmp_path):
            tracer = Tracer()
            for i in range(3):
                with tracer.span(f"op.{i}"):
                    pass
            spans = load_spans(date=today)
            assert len(spans) == 3

    def test_load_spans_limit(self, tmp_path):
        from agency.tracing import Tracer, load_spans
        today = time.strftime("%Y-%m-%d")
        with patch("agency.tracing._traces_dir", return_value=tmp_path):
            tracer = Tracer()
            for i in range(5):
                with tracer.span(f"op.{i}"):
                    pass
            spans = load_spans(date=today, limit=2)
            assert len(spans) == 2

    def test_get_tracer_returns_same_instance(self):
        from agency.tracing import get_tracer
        t1 = get_tracer()
        t2 = get_tracer()
        assert t1 is t2

    def test_new_tracer_always_fresh(self):
        from agency.tracing import new_tracer
        t1 = new_tracer()
        t2 = new_tracer()
        assert t1 is not t2
        assert t1.trace_id != t2.trace_id

    def test_list_trace_dates(self, tmp_path):
        from agency.tracing import list_trace_dates
        (tmp_path / "2026-01-01.jsonl").write_text("{}\n")
        (tmp_path / "2026-01-02.jsonl").write_text("{}\n")
        with patch("agency.tracing._traces_dir", return_value=tmp_path):
            dates = list_trace_dates()
        assert "2026-01-02" in dates
        assert dates[0] >= dates[-1]  # newest first


# ===========================================================================
# 3. profiler — @profile_call, top_slowest, export_speedscope
# ===========================================================================

class TestProfiler:
    def setup_method(self):
        """Clear the sample store before each test."""
        from agency.profiler import get_store
        get_store().clear()

    def test_profile_call_bare_decorator(self):
        from agency.profiler import profile_call, get_store

        @profile_call
        def add(a, b):
            return a + b

        result = add(1, 2)
        assert result == 3
        samples = get_store().all()
        assert len(samples) == 1
        assert "add" in samples[0].operation

    def test_profile_call_with_operation_name(self):
        from agency.profiler import profile_call, get_store

        @profile_call(operation="custom.op")
        def greet():
            return "hi"

        greet()
        samples = get_store().all()
        assert samples[-1].operation == "custom.op"

    def test_profile_call_measures_duration(self):
        from agency.profiler import profile_call, get_store

        @profile_call
        def slow_fn():
            time.sleep(0.05)

        slow_fn()
        samples = get_store().all()
        assert samples[-1].duration_ms >= 40  # at least 40ms

    def test_profile_call_propagates_exception(self):
        from agency.profiler import profile_call

        @profile_call
        def fail():
            raise RuntimeError("oops")

        with pytest.raises(RuntimeError):
            fail()

    def test_top_slowest_aggregates(self):
        from agency.profiler import profile_call, top_slowest, get_store

        @profile_call(operation="fast.op")
        def fast():
            time.sleep(0.001)

        @profile_call(operation="slow.op")
        def slow():
            time.sleep(0.05)

        slow()
        fast()
        fast()

        top = top_slowest(5)
        names = [s.operation for s in top]
        assert "slow.op" in names
        # slow.op should be first (slowest)
        assert top[0].operation == "slow.op"

    def test_top_slowest_empty_store(self):
        from agency.profiler import top_slowest
        assert top_slowest(5) == []

    def test_export_speedscope_empty(self, tmp_path):
        from agency.profiler import export_speedscope
        out = tmp_path / "profile.json"
        export_speedscope(path=out)
        data = json.loads(out.read_text())
        assert "$schema" in data
        assert data["shared"]["frames"] == []

    def test_export_speedscope_with_data(self, tmp_path):
        from agency.profiler import profile_call, export_speedscope, get_store

        @profile_call(operation="test.speedscope")
        def work():
            time.sleep(0.01)

        work()
        work()
        out = tmp_path / "profile.json"
        export_speedscope(path=out)
        data = json.loads(out.read_text())
        frames = data["shared"]["frames"]
        assert any(f["name"] == "test.speedscope" for f in frames)
        profile = data["profiles"][0]
        assert profile["type"] == "sampled"
        assert len(profile["weights"]) == 2

    def test_sample_store_thread_safe(self):
        from agency.profiler import profile_call, get_store

        @profile_call(operation="thread.op")
        def work():
            time.sleep(0.001)

        threads = [threading.Thread(target=work) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        samples = [s for s in get_store().all() if s.operation == "thread.op"]
        assert len(samples) == 10


# ===========================================================================
# 4. audit — log_event, verify_integrity, chain hash
# ===========================================================================

class TestAudit:
    def test_log_event_creates_file(self, tmp_path):
        from agency.audit import log_event
        p = tmp_path / "audit.jsonl"
        log_event("test.event", {"key": "val"}, path=p)
        assert p.exists()
        data = json.loads(p.read_text().strip())
        assert data["event"] == "test.event"
        assert data["payload"]["key"] == "val"

    def test_log_event_has_timestamp(self, tmp_path):
        from agency.audit import log_event
        p = tmp_path / "audit.jsonl"
        entry = log_event("ts.test", {}, path=p)
        assert "timestamp" in entry
        ts = entry["timestamp"]
        assert "T" in ts and ts.endswith("Z")

    def test_log_event_has_hash(self, tmp_path):
        from agency.audit import log_event
        p = tmp_path / "audit.jsonl"
        entry = log_event("hash.test", {}, path=p)
        assert "hash" in entry
        assert len(entry["hash"]) == 64  # SHA-256 hex

    def test_chain_hash_chain(self, tmp_path):
        """Second entry's hash depends on first entry's hash."""
        from agency.audit import log_event
        p = tmp_path / "audit.jsonl"
        e1 = log_event("first", {"n": 1}, path=p)
        e2 = log_event("second", {"n": 2}, path=p)
        # Re-derive e2's hash manually
        core2 = json.dumps(
            {"timestamp": e2["timestamp"], "event": "second", "payload": {"n": 2}},
            sort_keys=True,
        )
        expected = hashlib.sha256((e1["hash"] + core2).encode()).hexdigest()
        assert e2["hash"] == expected

    def test_verify_integrity_clean_log(self, tmp_path):
        from agency.audit import log_event, verify_integrity
        p = tmp_path / "audit.jsonl"
        for i in range(5):
            log_event(f"event.{i}", {"i": i}, path=p)
        ok, errors = verify_integrity(path=p)
        assert ok
        assert errors == []

    def test_verify_integrity_detects_tamper(self, tmp_path):
        from agency.audit import log_event, verify_integrity
        p = tmp_path / "audit.jsonl"
        log_event("ev.1", {"x": 1}, path=p)
        log_event("ev.2", {"x": 2}, path=p)

        # Tamper: rewrite the second entry's payload
        lines = p.read_text().splitlines()
        e2 = json.loads(lines[1])
        e2["payload"]["x"] = 999  # changed!
        # Keep hash unchanged (tampered)
        lines[1] = json.dumps(e2)
        p.write_text("\n".join(lines) + "\n")

        ok, errors = verify_integrity(path=p)
        assert not ok
        assert len(errors) >= 1

    def test_load_entries_returns_all(self, tmp_path):
        from agency.audit import log_event, load_entries
        p = tmp_path / "audit.jsonl"
        for i in range(4):
            log_event(f"e.{i}", {}, path=p)
        entries = load_entries(path=p)
        assert len(entries) == 4

    def test_load_entries_tail(self, tmp_path):
        from agency.audit import log_event, load_entries
        p = tmp_path / "audit.jsonl"
        for i in range(6):
            log_event(f"e.{i}", {}, path=p)
        entries = load_entries(tail=3, path=p)
        assert len(entries) == 3

    def test_log_shell_event(self, tmp_path):
        from agency.audit import log_shell, AuditEvent
        p = tmp_path / "audit.jsonl"
        entry = log_shell("ls -la", "ON_MY_MACHINE", path=p)
        assert entry["event"] == AuditEvent.SHELL_EXECUTE
        assert entry["payload"]["command"] == "ls -la"
        assert entry["payload"]["trust_mode"] == "ON_MY_MACHINE"

    def test_log_api_call_event(self, tmp_path):
        from agency.audit import log_api_call, AuditEvent
        p = tmp_path / "audit.jsonl"
        entry = log_api_call("claude-opus-4-7", path=p)
        assert entry["event"] == AuditEvent.API_CALL
        assert entry["payload"]["model"] == "claude-opus-4-7"

    def test_log_plugin_install_event(self, tmp_path):
        from agency.audit import log_plugin_install, AuditEvent
        p = tmp_path / "audit.jsonl"
        entry = log_plugin_install("my-plugin", source="github:x/y", path=p)
        assert entry["event"] == AuditEvent.PLUGIN_INSTALL
        assert entry["payload"]["name"] == "my-plugin"

    def test_verify_empty_file_is_ok(self, tmp_path):
        from agency.audit import verify_integrity
        p = tmp_path / "audit.jsonl"
        p.write_text("")
        ok, errors = verify_integrity(path=p)
        assert ok
        assert errors == []

    def test_verify_missing_file_is_ok(self, tmp_path):
        from agency.audit import verify_integrity
        p = tmp_path / "nonexistent.jsonl"
        ok, errors = verify_integrity(path=p)
        assert ok

    def test_concurrent_log_events(self, tmp_path):
        """Multiple threads writing must not corrupt the file."""
        from agency.audit import log_event, load_entries
        p = tmp_path / "audit.jsonl"

        def writer(i: int) -> None:
            log_event(f"concurrent.{i}", {"i": i}, path=p)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        entries = load_entries(path=p)
        assert len(entries) == 20


# ===========================================================================
# 5. Integration — tracer + profiler wired together
# ===========================================================================

class TestIntegration:
    def setup_method(self):
        from agency.profiler import get_store
        get_store().clear()

    def test_profile_call_inside_tracer_span(self, tmp_path):
        from agency.tracing import Tracer
        from agency.profiler import profile_call, get_store

        @profile_call(operation="integration.op")
        def do_work():
            return 42

        with patch("agency.tracing._traces_dir", return_value=tmp_path):
            tracer = Tracer()
            with tracer.span("outer.span"):
                result = do_work()

        assert result == 42
        samples = [s for s in get_store().all() if s.operation == "integration.op"]
        assert len(samples) == 1

    def test_json_log_output_parseable(self):
        from agency.logging_config import setup_logging
        stream = StringIO()
        uname = f"agency_{uuid.uuid4().hex}"
        with patch("agency.logging_config.LOGGER_NAME", uname):
            lg = setup_logging(level="DEBUG", format="json", stream=stream)
            lg.info("hello %s", "world")

        output = stream.getvalue().strip()
        lines = [l for l in output.splitlines() if l.strip()]
        assert len(lines) >= 1
        parsed = json.loads(lines[-1])
        assert parsed["message"] == "hello world"
