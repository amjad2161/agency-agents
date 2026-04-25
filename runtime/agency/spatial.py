"""Spatial-computing bridge: webcam-driven 3D HUD over WebSocket.

The frontend (runtime/agency/static/spatial.html) runs MediaPipe Holistic in
the browser — tracking 33 body-pose landmarks, 468 face landmarks and 21-point
per-hand tracking — and pushes events here. The backend translates those
events into the same runtime actions the SSE chat already supports.

No new authority is granted: a pinch on a holographic skill chip is exactly
equivalent to selecting a skill in the regular UI; an open-palm activation is
equivalent to pressing "Send". The `hologram_action` event lets the frontend
dispatch a run request that was triggered by physical interaction with a
spawned 3D node, not new authority — just a richer input surface.

This module deliberately accepts a closed set of typed events; anything else
is rejected and the socket stays open.
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
    "hello",           # initial handshake; client requests skill list
    "gesture",         # detected gesture (informational; logged, not executed)
    "run",             # explicit user action: run a skill against a request
    "hologram_action", # user interacted with a spawned holographic node
    "ping",            # heartbeat
})

# Gesture vocabulary the client is expected to emit.  Anything outside this set
# gets a typed `error` reply (the socket stays open).  Keep this list aligned
# with the classifier in static/spatial.html.
KNOWN_GESTURES = frozenset({
    "pinch",        # thumb tip + index tip close → select / confirm
    "open_palm",    # all 5 fingertips above wrist y → send / activate
    "fist",         # all fingertips below palm midpoint → clear
    "point",        # only index extended → navigate / highlight
    "thumbs_up",    # thumb extended up, others curled → approve / confirm
    "two_fingers",  # index + middle extended, others curled → expand / menu
    "victory",      # index + middle extended and spread wide → spawn hologram
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
        {"type": "hologram_action", "node_id": "...", "message": "...",
         "skill": <slug?>, "session_id": <str?>}
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
            t = msg.get("type") if isinstance(msg, dict) else None
            if t not in _CLIENT_EVENTS:
                await _send(ws, {"type": "error",
                                 "message": f"unsupported event: {t!r}"})
                continue

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
            elif t in ("run", "hologram_action"):
                # `hologram_action` carries the same required fields as `run`
                # plus an optional `node_id` (informational, ignored by the
                # backend but preserved so front-end logs are coherent).
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

    # Planner.plan() may make a synchronous HTTP call to Anthropic; offload to
    # a thread so the asyncio loop stays responsive for other open sockets.
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
        loaded = await loop.run_in_executor(None, memory.load, session_id)
        session = loaded or Session(
            session_id=session_id, skill_slug=plan.skill.slug,
        )

    executor = Executor(registry, llm, memory=memory)

    queue: asyncio.Queue = asyncio.Queue()
    cancel_event = threading.Event()

    def _drain() -> None:
        try:
            for ev in executor.stream(plan.skill, user_message, session=session):
                if cancel_event.is_set():
                    return
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
    try:
        while True:
            item = await queue.get()
            await _send(ws, item)
            if item["type"] == "done":
                break
    finally:
        cancel_event.set()
        await fut


async def _send(ws: WebSocket, payload: dict[str, Any]) -> None:
    await ws.send_text(json.dumps(payload, default=str))
