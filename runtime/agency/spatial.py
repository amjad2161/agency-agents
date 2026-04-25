"""Spatial-computing bridge: webcam-driven 3D HUD over WebSocket.

The frontend (runtime/agency/static/spatial.html) runs MediaPipe Holistic in
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
from typing import Any, Awaitable, Callable

from fastapi import WebSocket, WebSocketDisconnect

from .executor import Executor
from .llm import AnthropicLLM, LLMConfig, LLMError
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
# is logged and ignored on the server — the contract stays narrow.
KNOWN_GESTURES = frozenset({
    "pinch",        # thumb tip + index tip < threshold
    "open_palm",    # all 5 fingertips above wrist y
    "fist",         # all fingertips below midpoint of palm
    "swipe_left",
    "swipe_right",
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
            if not isinstance(msg, dict) or msg.get("type") not in _CLIENT_EVENTS:
                await _send(ws, {"type": "error",
                                 "message": f"unsupported event: {msg.get('type')!r}"})
                continue

            t = msg["type"]
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
                name = msg.get("name")
                if name in KNOWN_GESTURES:
                    await _send(ws, {"type": "gesture_ack", "name": name})
                else:
                    await _send(ws, {"type": "error",
                                     "message": f"unknown gesture: {name!r}"})
            elif t == "run":
                await _handle_run(
                    ws, msg, registry=registry, memory=memory, llm_factory=llm_factory,
                )
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

    plan = Planner(registry, llm=llm).plan(user_message, hint_slug=skill_hint)
    await _send(ws, {
        "type": "plan",
        "skill": {"slug": plan.skill.slug, "name": plan.skill.name,
                  "emoji": plan.skill.emoji},
        "rationale": plan.rationale,
    })

    session: Session | None = None
    if session_id:
        session = memory.load(session_id) or Session(
            session_id=session_id, skill_slug=plan.skill.slug,
        )

    executor = Executor(registry, llm, memory=memory)

    # The executor's stream() is sync; run it in a worker thread so the
    # WebSocket loop stays responsive (heartbeats, gesture events, etc.).
    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def _drain() -> None:
        try:
            for ev in executor.stream(plan.skill, user_message, session=session):
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
    while True:
        item = await queue.get()
        await _send(ws, item)
        if item["type"] in ("done", "error") and item["type"] == "done":
            break
        if item["type"] == "error":
            break
    await fut  # let the worker finish before returning


async def _send(ws: WebSocket, payload: dict[str, Any]) -> None:
    await ws.send_text(json.dumps(payload, default=str))
