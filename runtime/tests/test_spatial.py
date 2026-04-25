"""WebSocket tests for the spatial HUD bridge (Holistic edition).

Uses FastAPI's TestClient (Starlette in-process driver — no real network) and
stubbed LLM factories to avoid needing an API key.

Covers:
  - hello / ping protocol basics
  - Original 4-gesture vocabulary: pinch, open_palm, fist, point
  - New 3-gesture vocabulary: thumbs_up, two_fingers, victory
  - hologram_action event (new in the Holistic upgrade)
  - Unknown gesture / event rejection
  - Invalid JSON rejection
  - run without message rejection
  - run without API key surfaces a clean error
  - Unknown skill slug surfaces typed error, socket stays open
  - Disconnect cancels the worker thread
  - Non-disconnect send failure also sets cancel_event
  - Executor mid-stream failure still delivers 'done' sentinel
  - End-to-end run with stub LLM streams plan → stream → done
  - hologram_action with missing message is rejected
  - hologram_action end-to-end dispatches as a run
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from agency.server import build_app
from agency.spatial import KNOWN_GESTURES


def _client():
    return TestClient(build_app())


# ===== protocol basics ====================================================

def test_hello_returns_skill_list():
    with _client().websocket_connect("/ws/spatial") as ws:
        ws.send_text(json.dumps({"type": "hello"}))
        msg = json.loads(ws.receive_text())
        assert msg["type"] == "hello"
        assert isinstance(msg["skills"], list) and len(msg["skills"]) > 0
        assert {"slug", "name", "emoji", "category"} <= set(msg["skills"][0])


def test_ping_returns_pong():
    with _client().websocket_connect("/ws/spatial") as ws:
        ws.send_text(json.dumps({"type": "ping"}))
        assert json.loads(ws.receive_text()) == {"type": "pong"}


# ===== original gesture vocabulary ========================================

def test_pinch_gesture_is_acked():
    with _client().websocket_connect("/ws/spatial") as ws:
        ws.send_text(json.dumps({
            "type": "gesture", "name": "pinch", "hand": "right",
            "at": [0.5, 0.5, 0],
        }))
        msg = json.loads(ws.receive_text())
        assert msg == {"type": "gesture_ack", "name": "pinch"}


def test_open_palm_gesture_is_acked():
    with _client().websocket_connect("/ws/spatial") as ws:
        ws.send_text(json.dumps({"type": "gesture", "name": "open_palm", "hand": "right"}))
        msg = json.loads(ws.receive_text())
        assert msg == {"type": "gesture_ack", "name": "open_palm"}


def test_fist_gesture_is_acked():
    with _client().websocket_connect("/ws/spatial") as ws:
        ws.send_text(json.dumps({"type": "gesture", "name": "fist", "hand": "right"}))
        assert json.loads(ws.receive_text()) == {"type": "gesture_ack", "name": "fist"}


def test_point_gesture_is_acked():
    with _client().websocket_connect("/ws/spatial") as ws:
        ws.send_text(json.dumps({"type": "gesture", "name": "point", "hand": "right"}))
        assert json.loads(ws.receive_text()) == {"type": "gesture_ack", "name": "point"}


# ===== NEW gesture vocabulary (Holistic upgrade) ==========================

def test_thumbs_up_gesture_is_acked():
    with _client().websocket_connect("/ws/spatial") as ws:
        ws.send_text(json.dumps({
            "type": "gesture", "name": "thumbs_up", "hand": "right",
            "at": [0.5, 0.3, 0],
        }))
        assert json.loads(ws.receive_text()) == {"type": "gesture_ack", "name": "thumbs_up"}


def test_two_fingers_gesture_is_acked():
    with _client().websocket_connect("/ws/spatial") as ws:
        ws.send_text(json.dumps({
            "type": "gesture", "name": "two_fingers", "hand": "right",
        }))
        assert json.loads(ws.receive_text()) == {"type": "gesture_ack", "name": "two_fingers"}


def test_victory_gesture_is_acked():
    with _client().websocket_connect("/ws/spatial") as ws:
        ws.send_text(json.dumps({
            "type": "gesture", "name": "victory", "hand": "right",
            "at": [0.5, 0.4, 0],
        }))
        assert json.loads(ws.receive_text()) == {"type": "gesture_ack", "name": "victory"}


def test_all_known_gestures_are_in_vocabulary():
    """Smoke-check: every gesture in KNOWN_GESTURES is accepted by the WS handler."""
    with _client().websocket_connect("/ws/spatial") as ws:
        for name in sorted(KNOWN_GESTURES):
            ws.send_text(json.dumps({"type": "gesture", "name": name, "hand": "right"}))
            msg = json.loads(ws.receive_text())
            assert msg == {"type": "gesture_ack", "name": name}, \
                f"gesture {name!r} was not acked: {msg}"


# ===== rejection cases ====================================================

def test_unknown_gesture_is_rejected_but_socket_stays_open():
    with _client().websocket_connect("/ws/spatial") as ws:
        ws.send_text(json.dumps({"type": "gesture", "name": "wave_at_the_dog"}))
        msg = json.loads(ws.receive_text())
        assert msg["type"] == "error"
        assert "wave_at_the_dog" in msg["message"]
        # Socket still works.
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


# ===== hologram_action ====================================================

def test_hologram_action_without_message_is_rejected():
    with _client().websocket_connect("/ws/spatial") as ws:
        ws.send_text(json.dumps({"type": "hologram_action", "node_id": "chip_foo"}))
        msg = json.loads(ws.receive_text())
        assert msg["type"] == "error"
        assert "message" in msg["message"]


def test_hologram_action_without_api_key_returns_error(monkeypatch):
    """hologram_action proxies through _handle_run; surfaces LLM errors cleanly."""
    from agency import server as server_mod
    from agency.llm import LLMError

    def _boom():
        raise LLMError("ANTHROPIC_API_KEY is not set")
    monkeypatch.setattr(server_mod, "_require_llm", _boom)

    with _client().websocket_connect("/ws/spatial") as ws:
        ws.send_text(json.dumps({
            "type": "hologram_action",
            "node_id": "chip_engineering-ai-engineer",
            "message": "write a hello world program",
            "skill": None,
        }))
        msg = json.loads(ws.receive_text())
        assert msg["type"] == "error"
        assert "ANTHROPIC_API_KEY" in msg["message"]


def test_hologram_action_end_to_end_with_stub_llm(monkeypatch):
    """hologram_action with a real message behaves identically to 'run'."""
    from agency import server as server_mod
    from dataclasses import dataclass
    from typing import Any

    @dataclass
    class _Cfg:
        model = "fake"; planner_model = "fake"; max_tokens = 1024

    @dataclass
    class _TextBlock:
        text: str; type: str = "text"

    @dataclass
    class _Resp:
        content: list; stop_reason: str; usage: Any = None

    class _StubLLM:
        config = _Cfg()
        @staticmethod
        def cached_system(text):
            return [{"type": "text", "text": text,
                     "cache_control": {"type": "ephemeral"}}]
        def messages_create(self, **_kw):
            return _Resp(stop_reason="end_turn",
                         content=[_TextBlock("hologram result text")])

    monkeypatch.setattr(server_mod, "_require_llm", lambda: _StubLLM())
    monkeypatch.setattr(server_mod, "_maybe_llm", lambda: None)

    with _client().websocket_connect("/ws/spatial") as ws:
        ws.send_text(json.dumps({
            "type": "hologram_action",
            "node_id": "chip_xyz",
            "message": "do a thing",
        }))
        plan_msg = json.loads(ws.receive_text())
        assert plan_msg["type"] == "plan"
        seen = []
        while True:
            m = json.loads(ws.receive_text())
            seen.append(m["type"])
            if m["type"] == "done":
                break
        assert "stream" in seen or "done" in seen


# ===== run without API key ================================================

def test_run_returns_error_when_no_api_key(monkeypatch):
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
    from agency import server as server_mod

    class _StubLLM:
        class config:
            model = "fake"; planner_model = "fake"; max_tokens = 1024
        @staticmethod
        def cached_system(text):
            return [{"type": "text", "text": text,
                     "cache_control": {"type": "ephemeral"}}]
        def messages_create(self, **_k):  # pragma: no cover
            raise AssertionError("should not reach")

    monkeypatch.setattr(server_mod, "_require_llm", lambda: _StubLLM())

    with _client().websocket_connect("/ws/spatial") as ws:
        ws.send_text(json.dumps({
            "type": "run", "message": "hi",
            "skill": "definitely-not-a-real-slug",
        }))
        msg = json.loads(ws.receive_text())
        assert msg["type"] == "error"
        assert "Unknown skill slug" in msg["message"]
        # Socket still works after error.
        ws.send_text(json.dumps({"type": "ping"}))
        assert json.loads(ws.receive_text()) == {"type": "pong"}


# ===== cancellation / resilience ==========================================

def test_disconnect_signals_cancellation_to_worker(monkeypatch):
    from agency import server as server_mod
    from dataclasses import dataclass
    from typing import Any
    import threading

    proceed_to_call_2 = threading.Event()
    call_count = {"n": 0}

    @dataclass
    class _T: text: str = "ok"; type: str = "text"
    @dataclass
    class _R: content: list; stop_reason: str; usage: Any = None

    class _StubLLM:
        class config:
            model = "fake"; planner_model = "fake"; max_tokens = 1024
        @staticmethod
        def cached_system(text):
            return [{"type": "text", "text": text,
                     "cache_control": {"type": "ephemeral"}}]
        def messages_create(self, **_k):
            call_count["n"] += 1
            if call_count["n"] == 1:
                proceed_to_call_2.wait(timeout=3)
                return _R(content=[_T()], stop_reason="end_turn")
            return _R(content=[_T()], stop_reason="end_turn")

    monkeypatch.setattr(server_mod, "_require_llm", lambda: _StubLLM())
    monkeypatch.setattr(server_mod, "_maybe_llm", lambda: None)

    with _client().websocket_connect("/ws/spatial") as ws:
        ws.send_text(json.dumps({"type": "run", "message": "anything"}))
        plan_msg = json.loads(ws.receive_text())
        assert plan_msg["type"] == "plan"
    proceed_to_call_2.set()

    import time; time.sleep(0.2)
    assert call_count["n"] <= 1, (
        f"worker made {call_count['n']} LLM calls after disconnect"
    )


def test_send_failure_other_than_disconnect_still_cancels_worker(monkeypatch):
    from agency import server as server_mod
    from agency import spatial as spatial_mod
    from dataclasses import dataclass
    from typing import Any
    import threading, time

    proceed_to_call_2 = threading.Event()
    call_count = {"n": 0}

    @dataclass
    class _T: text: str = "ok"; type: str = "text"
    @dataclass
    class _R: content: list; stop_reason: str; usage: Any = None

    class _StubLLM:
        class config:
            model = "fake"; planner_model = "fake"; max_tokens = 1024
        @staticmethod
        def cached_system(text):
            return [{"type": "text", "text": text,
                     "cache_control": {"type": "ephemeral"}}]
        def messages_create(self, **_k):
            call_count["n"] += 1
            if call_count["n"] == 1:
                proceed_to_call_2.wait(timeout=3)
            return _R(content=[_T()], stop_reason="end_turn")

    monkeypatch.setattr(server_mod, "_require_llm", lambda: _StubLLM())
    monkeypatch.setattr(server_mod, "_maybe_llm", lambda: None)

    real_send = spatial_mod._send
    sends = {"n": 0}

    async def _exploding_send(ws_ref, payload):
        sends["n"] += 1
        if sends["n"] == 2:
            raise RuntimeError("simulated send failure")
        await real_send(ws_ref, payload)

    monkeypatch.setattr(spatial_mod, "_send", _exploding_send)

    with _client().websocket_connect("/ws/spatial") as ws:
        ws.send_text(json.dumps({"type": "run", "message": "anything"}))
        try:
            json.loads(ws.receive_text())
        except Exception:
            pass

    proceed_to_call_2.set()
    time.sleep(0.2)
    assert call_count["n"] <= 1


def test_run_when_executor_raises_still_delivers_done_sentinel(monkeypatch):
    from agency import server as server_mod

    class _ExplodingLLM:
        class config:
            model = "fake"; planner_model = "fake"; max_tokens = 1024
        @staticmethod
        def cached_system(text):
            return [{"type": "text", "text": text,
                     "cache_control": {"type": "ephemeral"}}]
        def messages_create(self, **_kw):
            raise RuntimeError("simulated mid-stream failure")

    monkeypatch.setattr(server_mod, "_require_llm", lambda: _ExplodingLLM())
    monkeypatch.setattr(server_mod, "_maybe_llm", lambda: None)

    with _client().websocket_connect("/ws/spatial") as ws:
        ws.send_text(json.dumps({"type": "run", "message": "boom"}))
        seen = []
        while True:
            m = json.loads(ws.receive_text())
            seen.append(m["type"])
            if m["type"] == "done":
                break
        assert "error" in seen
        assert seen[-1] == "done"


def test_run_streams_executor_events_with_stubbed_llm(monkeypatch):
    from agency import server as server_mod
    from dataclasses import dataclass
    from typing import Any

    @dataclass
    class _Cfg:
        model = "fake-opus"; planner_model = "fake-haiku"; max_tokens = 1024

    @dataclass
    class _TextBlock:
        text: str; type: str = "text"

    @dataclass
    class _Resp:
        content: list; stop_reason: str; usage: Any = None

    class _StubLLM:
        config = _Cfg()
        @staticmethod
        def cached_system(text):
            return [{"type": "text", "text": text,
                     "cache_control": {"type": "ephemeral"}}]
        def messages_create(self, **_kw):
            return _Resp(stop_reason="end_turn",
                         content=[_TextBlock("hi from agent")])

    monkeypatch.setattr(server_mod, "_require_llm", lambda: _StubLLM())
    monkeypatch.setattr(server_mod, "_maybe_llm", lambda: None)

    with _client().websocket_connect("/ws/spatial") as ws:
        ws.send_text(json.dumps({"type": "run", "message": "say hi"}))
        plan_msg = json.loads(ws.receive_text())
        assert plan_msg["type"] == "plan"
        assert "skill" in plan_msg
        kinds = []
        while True:
            m = json.loads(ws.receive_text())
            if m["type"] == "done":
                break
            if m["type"] == "stream":
                kinds.append(m["kind"])
        assert "text" in kinds or "stop" in kinds
        assert "usage" in kinds
