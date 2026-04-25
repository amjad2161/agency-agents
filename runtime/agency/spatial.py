"""Spatial-computing bridge: webcam-driven 3D HUD over WebSocket.

The frontend (runtime/agency/static/spatial.html) runs MediaPipe Hands in
the browser, detects a small allowlist of gestures, and pushes events to the
WebSocket exposed here. The backend translates those events into the same
runtime actions the SSE chat already supports — *no new authority*. A pinch
on the holographic skill picker is exactly equivalent to clicking a skill in
the regular UI; an open-palm activation is equivalent to pressing "Send".

This module deliberately doesn't accept arbitrary "action" strings from the
client. It accepts a closed set of typed events; anything else is rejected.
"""

from __future__ import annotations

import asyncio
import json
import threading
from typing import Any, Awaitable, Callable

from fastapi import WebSocket, WebSocketDisconnect

from .executor import Executor
from .llm import AnthropicLLM, LLMError
from .memory import MemoryStore, Session
from .planner import Planner
from .skills import SkillRegistry

# Closed set of events the client may send.
_CLIENT_EVENTS = frozenset({
    "hello",        # initial handshake; client requests skill list
    "gesture",      # detected gesture (informational; logged, not executed)
    "run",          # explicit user action: run a skill against a request
    "ping",         # heartbeat
})

# Gesture vocabulary the client is expected to emit. Anything outside this set
# gets a typed `error` reply (the socket stays open). Keep this list aligned
# with the classifier in static/spatial.html.
KNOWN_GESTURES = frozenset({
    "pinch",        # thumb tip + index tip < threshold
    "open_palm",    # all 5 fingertips above wrist y
    "fist",         # all fingertips below midpoint of palm
    "point",        # only index extended
})


async def spatial_ws_handler(
    ws: WebSocket,
    *,
    registry: SkillRegistry,
    memory: MemoryStore,
    llm_factory: Callable[[], AnthropicLLM],
) -> None:
    """Run a single spatial-UI session against the runtime.

    Protocol (all JSON, line-delimited per WebSocket message):

    Client → Server:
        {"type": "hello"}
        {"type": "gesture", "name": "pinch", "hand": "right",
         "at": [x, y, z], "ts": 1700000000.0}
        {"type": "run", "message": "...", "skill": <slug?>, "session_id": <str?>}
        {"type": "ping"}

    Server → Client:
        {"type": "hello", "skills": [{slug,name,emoji,category}, ...]}
        {"type": "gesture_ack", "name": "pinch"}
        {"type": "plan", "skill": {...}, "rationale": "..."}
        {"type": "stream", "kind": "text_delta"|"tool_use"|..., "payload": ...}
        {"type": "done"}
        {"type": "error", "message": "..."}
        {"type": "pong"}
    """
    await ws.accept()
    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await _send(ws, {"type": "error", "message": "invalid JSON"})
                continue
            # Defensive: `type` can be any JSON value (list, dict, number, …).
            # `set` membership of an unhashable type would raise TypeError and
            # drop the socket. Coerce non-strings to None so the unsupported
            # branch fires cleanly.
            raw_t = msg.get("type") if isinstance(msg, dict) else None
            t = raw_t if isinstance(raw_t, str) else None
            if t not in _CLIENT_EVENTS:
                await _send(ws, {"type": "error",
                                 "message": f"unsupported event: {raw_t!r}"})
                continue

            # `t` is already validated as one of _CLIENT_EVENTS above.
            if t == "hello":
                await _send(ws, {
                    "type": "hello",
                    "skills": [
                        {"slug": s.slug, "name": s.name,
                         "emoji": s.emoji, "category": s.category}
                        for s in registry.all()
                    ],
                })
            elif t == "ping":
                await _send(ws, {"type": "pong"})
            elif t == "gesture":
                # Same defensive coerce: `name` could be any JSON value, and
                # an unhashable type would crash the membership check.
                raw_name = msg.get("name")
                name = raw_name if isinstance(raw_name, str) else None
                if name is not None and name in KNOWN_GESTURES:
                    await _send(ws, {"type": "gesture_ack", "name": name})
                else:
                    await _send(ws, {"type": "error",
                                     "message": f"unknown gesture: {raw_name!r}"})
            elif t == "run":
                # Surface ALL exceptions to the client, not just LLMError. The
                # most concrete way to hit this is `skill: "nonexistent"`,
                # which raises ValueError out of Planner.plan() — without this
                # wrapper that would silently kill the WebSocket.
                try:
                    await _handle_run(
                        ws, msg, registry=registry, memory=memory,
                        llm_factory=llm_factory,
                    )
                except WebSocketDisconnect:
                    raise
                except Exception as exc:  # noqa: BLE001 — surface to client
                    await _send(ws, {
                        "type": "error",
                        "message": f"{type(exc).__name__}: {exc}",
                    })
    except WebSocketDisconnect:
        return


async def _handle_run(
    ws: WebSocket,
    msg: dict[str, Any],
    *,
    registry: SkillRegistry,
    memory: MemoryStore,
    llm_factory: Callable[[], AnthropicLLM],
) -> None:
    user_message = (msg.get("message") or "").strip()
    if not user_message:
        await _send(ws, {"type": "error", "message": "missing 'message' field"})
        return
    skill_hint = msg.get("skill") or None
    session_id = msg.get("session_id") or None

    try:
        llm = llm_factory()
    except LLMError as e:
        await _send(ws, {"type": "error", "message": str(e)})
        return

    loop = asyncio.get_running_loop()

    # Planner.plan() makes a synchronous HTTP call to Anthropic when it has to
    # disambiguate among multiple candidate skills (the common case). Running
    # it inline would freeze the asyncio loop — and every other open WebSocket
    # — for the duration of that ~1s request. Offload to a thread.
    plan = await loop.run_in_executor(
        None, lambda: Planner(registry, llm=llm).plan(
            user_message, hint_slug=skill_hint,
        ),
    )
    await _send(ws, {
        "type": "plan",
        "skill": {"slug": plan.skill.slug, "name": plan.skill.name,
                  "emoji": plan.skill.emoji},
        "rationale": plan.rationale,
    })

    session: Session | None = None
    if session_id:
        # memory.load() does disk IO; offload alongside the planner call.
        loaded = await loop.run_in_executor(None, memory.load, session_id)
        session = loaded or Session(
            session_id=session_id, skill_slug=plan.skill.slug,
        )

    executor = Executor(registry, llm, memory=memory)

    # The executor's stream() is sync; run it in a worker thread so the
    # WebSocket loop stays responsive (heartbeats, gesture events, etc.).
    # `cancel_event` lets us tell the worker to stop after the current
    # in-flight LLM turn if the WebSocket client disconnects — without it,
    # a closed socket still pays for up to MAX_TURNS Anthropic calls.
    queue: asyncio.Queue = asyncio.Queue()
    cancel_event = threading.Event()

    def _drain() -> None:
        try:
            for ev in executor.stream(plan.skill, user_message, session=session):
                if cancel_event.is_set():
                    return  # finally below still enqueues "done"
                loop.call_soon_threadsafe(
                    queue.put_nowait,
                    {"type": "stream", "kind": ev.kind, "payload": ev.payload},
                )
        except Exception as e:  # noqa: BLE001 - surface to client
            loop.call_soon_threadsafe(
                queue.put_nowait, {"type": "error", "message": str(e)},
            )
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, {"type": "done"})

    fut: Awaitable = loop.run_in_executor(None, _drain)
    # `_drain` always enqueues a final {"type": "done"} via its `finally`,
    # even on error — so we only break on "done" to guarantee the client
    # sees the protocol's terminal sentinel after any error envelope.
    try:
        while True:
            # Bounded wait so a stalled executor (e.g. first LLM call hung
            # on the network) doesn't keep us parked forever after the client
            # disconnects. We poll the WebSocket state on each tick and bail
            # out if it has gone away.
            try:
                item = await asyncio.wait_for(queue.get(), timeout=0.5)
            except asyncio.TimeoutError:
                if _is_websocket_disconnected(ws):
                    break
                continue
            await _send(ws, item)
            if item["type"] == "done":
                break
    finally:
        # Set the cancel flag on EVERY exit path — disconnect, asyncio
        # CancelledError (a BaseException, doesn't catch as Exception),
        # any other unexpected error, and even the normal "done" path
        # (no-op because _drain has already returned). This guarantees
        # the worker thread can never burn LLM turns on a dead socket.
        cancel_event.set()
        # Don't tie up the WS handler waiting for the worker to exit — a
        # blocking LLM call inside the SDK can't be interrupted from another
        # thread. Wait briefly so the cancel can land and the worker can
        # close out cleanly; otherwise let it finish in the background.
        try:
            await asyncio.wait_for(asyncio.shield(fut), timeout=1.0)
        except asyncio.TimeoutError:
            pass


def _is_websocket_disconnected(ws: WebSocket) -> bool:
    """Best-effort 'is the WS gone' check that doesn't depend on a send.

    Starlette tracks both `client_state` and `application_state`; when the
    client closes the TCP connection, `client_state` flips to DISCONNECTED.
    Falls back to False if either attribute is missing on a future
    framework version — better to keep the loop alive than to spuriously
    abort.
    """
    state = getattr(ws, "client_state", None)
    if state is None:
        return False
    name = getattr(state, "name", None)
    if name is not None:
        return name == "DISCONNECTED"
    return str(state).endswith("DISCONNECTED")


async def _send(ws: WebSocket, payload: dict[str, Any]) -> None:
    await ws.send_text(json.dumps(payload, default=str))
