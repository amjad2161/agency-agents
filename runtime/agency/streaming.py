"""SSE streaming primitives.

Wire format (SSE):
    event: <type>
    data: <payload>
    id: <id>
    retry: <ms>
    \n

`stream_response` wraps any sync generator as an SSE iterator.
`async_stream_response` does the same for async iterators.
"""

from __future__ import annotations

import asyncio
import json
import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Iterator


@dataclass
class StreamEvent:
    """One SSE event."""

    event_type: str = "message"
    data: Any = ""
    id: str | None = None
    retry: int | None = None

    def to_sse(self) -> str:
        lines: list[str] = []
        if self.event_type and self.event_type != "message":
            lines.append(f"event: {self.event_type}")
        payload = self.data
        if isinstance(payload, (dict, list)):
            payload = json.dumps(payload)
        elif not isinstance(payload, str):
            payload = str(payload)
        # SSE spec — split multi-line payloads across data: lines
        for line in payload.splitlines() or [""]:
            lines.append(f"data: {line}")
        if self.id is not None:
            lines.append(f"id: {self.id}")
        if self.retry is not None:
            lines.append(f"retry: {self.retry}")
        return "\n".join(lines) + "\n\n"


class StreamBuffer:
    """Thread-safe FIFO buffer for tokens or events."""

    _SENTINEL = object()

    def __init__(self, maxsize: int = 0) -> None:
        self._q: "queue.Queue[Any]" = queue.Queue(maxsize=maxsize)
        self._closed = False
        self._lock = threading.Lock()

    def put(self, item: Any, timeout: float | None = None) -> None:
        with self._lock:
            if self._closed:
                raise RuntimeError("buffer closed")
        self._q.put(item, timeout=timeout)

    def get(self, timeout: float | None = None) -> Any:
        return self._q.get(timeout=timeout)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
        self._q.put(self._SENTINEL)

    @property
    def closed(self) -> bool:
        return self._closed

    def __iter__(self) -> Iterator[Any]:
        while True:
            item = self._q.get()
            if item is self._SENTINEL:
                return
            yield item


class SSEEmitter:
    """Formats values as SSE wire frames."""

    @staticmethod
    def emit(event: StreamEvent) -> str:
        return event.to_sse()

    @staticmethod
    def emit_token(token: str, event_id: str | None = None) -> str:
        return StreamEvent(event_type="token", data=token, id=event_id).to_sse()

    @staticmethod
    def emit_message(data: Any) -> str:
        return StreamEvent(event_type="message", data=data).to_sse()

    @staticmethod
    def emit_done(payload: str = "[DONE]") -> str:
        return StreamEvent(event_type="done", data=payload).to_sse()

    @staticmethod
    def emit_error(message: str) -> str:
        return StreamEvent(event_type="error", data=message).to_sse()

    @staticmethod
    def emit_keepalive() -> str:
        return ": keepalive\n\n"


def stream_response(generator: Iterator[Any]) -> Iterator[str]:
    """Wrap a sync generator producing tokens or StreamEvents as SSE."""
    for item in generator:
        if isinstance(item, StreamEvent):
            yield item.to_sse()
        elif isinstance(item, str):
            yield SSEEmitter.emit_token(item)
        elif isinstance(item, dict):
            yield SSEEmitter.emit_message(item)
        else:
            yield SSEEmitter.emit_token(str(item))
    yield SSEEmitter.emit_done()


async def async_stream_response(
    generator: AsyncIterator[Any] | Iterator[Any],
) -> AsyncIterator[str]:
    """Async variant — accepts either an async or sync iterator."""

    async def _run() -> AsyncIterator[Any]:
        if hasattr(generator, "__anext__"):
            async for item in generator:  # type: ignore[union-attr]
                yield item
        else:
            for item in generator:  # type: ignore[union-attr]
                yield item
                # Cooperative yield so we don't starve the loop
                await asyncio.sleep(0)

    async for item in _run():
        if isinstance(item, StreamEvent):
            yield item.to_sse()
        elif isinstance(item, str):
            yield SSEEmitter.emit_token(item)
        elif isinstance(item, dict):
            yield SSEEmitter.emit_message(item)
        else:
            yield SSEEmitter.emit_token(str(item))
    yield SSEEmitter.emit_done()


__all__ = [
    "StreamEvent",
    "StreamBuffer",
    "SSEEmitter",
    "stream_response",
    "async_stream_response",
]
