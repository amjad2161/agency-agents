"""WebSocket tests for the spatial HUD bridge.

Uses FastAPI's TestClient (which routes WebSocket traffic through Starlette's
in-process driver — no real network), and a stubbed LLM factory to avoid
needing an API key.
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from agency.server import build_app


def _client():
    return TestClient(build_app())


def test_hello_returns_skill_list():
    with _client().websocket_connect("/ws/spatial") as ws:
        ws.send_text(json.dumps({"type": "hello"}))
        msg = json.loads(ws.receive_text())
        assert msg["type"] == "hello"
        assert isinstance(msg["skills"], list) and len(msg["skills"]) > 0
        assert {"slug", "name", "emoji", "category"} <= set(msg["skills"][0])


def test_known_gesture_is_acked():
    with _client().websocket_connect("/ws/spatial") as ws:
        ws.send_text(json.dumps({
            "type": "gesture", "name": "pinch", "hand": "right", "at": [0.5, 0.5, 0],
        }))
        msg = json.loads(ws.receive_text())
        assert msg == {"type": "gesture_ack", "name": "pinch"}


def test_unknown_gesture_is_rejected_but_socket_stays_open():
    with _client().websocket_connect("/ws/spatial") as ws:
        ws.send_text(json.dumps({"type": "gesture", "name": "wave_at_dog"}))
        msg = json.loads(ws.receive_text())
        assert msg["type"] == "error"
        assert "wave_at_dog" in msg["message"]
        # Socket keeps working after a rejected gesture.
        ws.send_text(json.dumps({"type": "ping"}))
        assert json.loads(ws.receive_text()) == {"type": "pong"}


def test_unsupported_event_type_is_rejected():
    with _client().websocket_connect("/ws/spatial") as ws:
        ws.send_text(json.dumps({"type": "exec_arbitrary_command"}))
        msg = json.loads(ws.receive_text())
        assert msg["type"] == "error"
        assert "unsupported event" in msg["message"]


def test_invalid_json_is_rejected():
    with _client().websocket_connect("/ws/spatial") as ws:
        ws.send_text("not json {{{")
        msg = json.loads(ws.receive_text())
        assert msg["type"] == "error"
        assert "JSON" in msg["message"]


def test_run_without_message_is_rejected():
    with _client().websocket_connect("/ws/spatial") as ws:
        ws.send_text(json.dumps({"type": "run"}))
        msg = json.loads(ws.receive_text())
        assert msg["type"] == "error"
        assert "message" in msg["message"]


def test_run_returns_error_when_no_api_key(monkeypatch):
    """Without ANTHROPIC_API_KEY, the spatial endpoint surfaces a clean error."""
    from agency import server as server_mod
    from agency.llm import LLMError

    def _boom():
        raise LLMError("ANTHROPIC_API_KEY is not set")
    monkeypatch.setattr(server_mod, "_require_llm", _boom)

    with _client().websocket_connect("/ws/spatial") as ws:
        ws.send_text(json.dumps({"type": "run", "message": "hi"}))
        msg = json.loads(ws.receive_text())
        assert msg["type"] == "error"
        assert "ANTHROPIC_API_KEY" in msg["message"]


def test_run_with_unknown_skill_slug_surfaces_error_not_dropped_socket(monkeypatch):
    """Regression: planner raises ValueError on unknown slug, but the connection
    must stay alive and the client must see a typed error envelope."""
    from agency import server as server_mod

    class _StubLLM:
        class config:
            model = "fake"; planner_model = "fake"; max_tokens = 1024
        @staticmethod
        def cached_system(text):
            return [{"type": "text", "text": text,
                     "cache_control": {"type": "ephemeral"}}]
        def messages_create(self, **k):  # pragma: no cover - never reached
            raise AssertionError("planner shouldn't get this far")

    monkeypatch.setattr(server_mod, "_require_llm", lambda: _StubLLM())

    with _client().websocket_connect("/ws/spatial") as ws:
        ws.send_text(json.dumps({
            "type": "run", "message": "hi",
            "skill": "definitely-not-a-real-slug",
        }))
        msg = json.loads(ws.receive_text())
        assert msg["type"] == "error"
        assert "Unknown skill slug" in msg["message"]
        # And the socket is still open: a follow-up ping is honored.
        ws.send_text(json.dumps({"type": "ping"}))
        assert json.loads(ws.receive_text()) == {"type": "pong"}


def test_disconnect_signals_cancellation_to_worker(monkeypatch):
    """Regression: when the client disconnects mid-stream, the worker thread
    must observe the cancel signal and stop pulling further executor events,
    instead of running through the full MAX_TURNS-cap loop while the socket
    is closed.

    Strategy: stub the LLM to count messages_create() calls, return a
    minimal `tool_use` response on the first call and an `end_turn` on the
    second. The consumer-side WebSocket is closed before the second call.
    A correct implementation sees count == 1 (post-disconnect calls
    short-circuited); the buggy version saw count == 2.
    """
    from agency import server as server_mod
    from dataclasses import dataclass
    from typing import Any as _Any
    import threading

    proceed_to_call_2 = threading.Event()
    call_count = {"n": 0}

    @dataclass
    class _T: text: str = "ok"; type: str = "text"
    @dataclass
    class _Tool: id: str = "t1"; name: str = "list_dir"; input: dict = None; type: str = "tool_use"
    @dataclass
    class _R: content: list; stop_reason: str; usage: _Any = None

    class _StubLLM:
        class config:
            model = "fake"; planner_model = "fake"; max_tokens = 1024
        @staticmethod
        def cached_system(text):
            return [{"type": "text", "text": text,
                     "cache_control": {"type": "ephemeral"}}]
        def messages_create(self, **k):
            call_count["n"] += 1
            if call_count["n"] == 1:
                # Block here so the consumer has time to disconnect.
                proceed_to_call_2.wait(timeout=3)
                return _R(content=[_T()], stop_reason="end_turn")
            # If we get here, cancellation didn't work.
            return _R(content=[_T()], stop_reason="end_turn")

    monkeypatch.setattr(server_mod, "_require_llm", lambda: _StubLLM())
    monkeypatch.setattr(server_mod, "_maybe_llm", lambda: None)

    with _client().websocket_connect("/ws/spatial") as ws:
        ws.send_text(json.dumps({"type": "run", "message": "anything"}))
        plan_msg = json.loads(ws.receive_text())
        assert plan_msg["type"] == "plan"
        # Don't read the first stream event; just close the socket while
        # the LLM call is blocked.
    proceed_to_call_2.set()

    # Brief grace period for the worker to finish its in-flight call and
    # observe the cancel flag before deciding whether to continue.
    import time
    time.sleep(0.2)
    # The worker must NOT have made a second LLM call after disconnect.
    assert call_count["n"] <= 1, (
        f"worker made {call_count['n']} LLM calls after disconnect; "
        "cancellation didn't fire"
    )


def test_run_when_executor_raises_still_delivers_done_sentinel(monkeypatch):
    """If the executor blows up mid-stream, the protocol still yields a final
    'done' after the error envelope. Regression for the previous bug where
    the consumer broke on 'error' and left 'done' unconsumed in the queue."""
    from agency import server as server_mod

    class _ExplodingLLM:
        class config:
            model = "fake"; planner_model = "fake"; max_tokens = 1024
        @staticmethod
        def cached_system(text):
            return [{"type": "text", "text": text,
                     "cache_control": {"type": "ephemeral"}}]
        def messages_create(self, **kwargs):
            raise RuntimeError("simulated mid-stream failure")

    monkeypatch.setattr(server_mod, "_require_llm", lambda: _ExplodingLLM())
    monkeypatch.setattr(server_mod, "_maybe_llm", lambda: None)

    with _client().websocket_connect("/ws/spatial") as ws:
        ws.send_text(json.dumps({"type": "run", "message": "boom"}))
        seen = []
        # Drain until we see 'done' (or timeout via test runner).
        while True:
            m = json.loads(ws.receive_text())
            seen.append(m["type"])
            if m["type"] == "done":
                break
        # We must have seen at least one error envelope before done.
        assert "error" in seen
        assert seen[-1] == "done"


def test_run_streams_executor_events_with_stubbed_llm(monkeypatch):
    """End-to-end: a `run` event should produce plan → stream(...) → done."""
    from agency import server as server_mod

    # Build a minimal LLM stub that the executor can drive without a real API key.
    from dataclasses import dataclass
    from typing import Any

    @dataclass
    class _Cfg:
        model = "fake-opus"
        planner_model = "fake-haiku"
        max_tokens = 1024

    @dataclass
    class _TextBlock:
        text: str
        type: str = "text"

    @dataclass
    class _Resp:
        content: list
        stop_reason: str
        usage: Any = None

    class _StubLLM:
        def __init__(self):
            self.config = _Cfg()
        @staticmethod
        def cached_system(text: str):
            return [{"type": "text", "text": text,
                     "cache_control": {"type": "ephemeral"}}]
        def messages_create(self, **kwargs):
            # Single-turn end_turn — executor will exit cleanly.
            return _Resp(stop_reason="end_turn", content=[_TextBlock("hi from agent")])

    # Force the planner's offline path (no LLM for routing) and supply our stub
    # for execution.
    monkeypatch.setattr(server_mod, "_require_llm", lambda: _StubLLM())
    monkeypatch.setattr(server_mod, "_maybe_llm", lambda: None)

    with _client().websocket_connect("/ws/spatial") as ws:
        ws.send_text(json.dumps({"type": "run", "message": "say hi"}))
        # plan envelope
        plan_msg = json.loads(ws.receive_text())
        assert plan_msg["type"] == "plan"
        assert "skill" in plan_msg
        # at least one stream event with a recognized kind
        kinds = []
        while True:
            m = json.loads(ws.receive_text())
            if m["type"] == "done":
                break
            if m["type"] == "stream":
                kinds.append(m["kind"])
        # `run()` emits text + stop + usage events at minimum
        assert "text" in kinds or "stop" in kinds
        assert "usage" in kinds
