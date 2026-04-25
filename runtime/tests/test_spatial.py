"""WebSocket tests for the spatial HUD bridge.

Uses FastAPI's TestClient (which routes WebSocket traffic through Starlette's
in-process driver — no real network), and a stubbed LLM factory to avoid
needing an API key.
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from agency.server import build_app


def _client(monkeypatch=None):
    app = build_app()
    return TestClient(app)


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
