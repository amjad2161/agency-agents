"""Channel adapters — OpenClaw / DingTalk / Lark / Weibo / WeCom / WeChat / QQ.

Plug-in interface for chat channels JARVIS One can broadcast through.
Each channel is described as a :class:`ChannelSpec`. Real send adapters
require platform credentials and SDKs; this module ships only the
registry + a deterministic mock channel used in tests.

Add a real adapter by subclassing :class:`ChannelAdapter` and registering
it via :meth:`ChannelRegistry.register`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class ChannelSpec:
    slug: str
    name: str
    vendor: str
    transport: str
    docs_url: str = ""

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


# Reference catalogue from the JARVIS One spec.
CHANNELS: tuple[ChannelSpec, ...] = (
    ChannelSpec("dingtalk-deap", "DingTalk DEAP", "DingTalk-Real-AI",
                "https-webhook",
                "https://open.dingtalk.com/document/"),
    ChannelSpec("lark-openclaw", "Feishu / Lark", "openclaw-lark",
                "https-webhook",
                "https://open.larksuite.com/document/"),
    ChannelSpec("weibo-openclaw", "Weibo", "weibo-openclaw-plugin",
                "rest-api", ""),
    ChannelSpec("wecom-openclaw", "WeCom", "wecom-openclaw-plugin",
                "https-webhook", ""),
    ChannelSpec("weixin-openclaw", "WeChat", "openclaw-weixin",
                "https-webhook", ""),
    ChannelSpec("qqbot-openclaw", "QQ Bot", "openclaw-qqbot",
                "websocket", ""),
)


@dataclass
class ChannelMessage:
    channel: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ChannelDelivery:
    channel: str
    delivered: bool
    detail: str = ""


class ChannelAdapter(Protocol):
    spec: ChannelSpec

    def send(self, message: ChannelMessage) -> ChannelDelivery: ...


class MockChannelAdapter:
    """Deterministic adapter used by tests and offline demos."""

    def __init__(self, spec: ChannelSpec) -> None:
        self.spec = spec
        self.outbox: list[ChannelMessage] = []

    def send(self, message: ChannelMessage) -> ChannelDelivery:
        self.outbox.append(message)
        return ChannelDelivery(
            channel=self.spec.slug, delivered=True,
            detail=f"queued for {self.spec.vendor}",
        )


class ChannelRegistry:
    """Channel adapter registry with a mock-by-default policy."""

    def __init__(self) -> None:
        self._adapters: dict[str, ChannelAdapter] = {}
        for spec in CHANNELS:
            self._adapters[spec.slug] = MockChannelAdapter(spec)

    def register(self, adapter: ChannelAdapter) -> None:
        self._adapters[adapter.spec.slug] = adapter

    def get(self, slug: str) -> ChannelAdapter | None:
        return self._adapters.get(slug)

    def list_channels(self) -> list[dict[str, Any]]:
        return [a.spec.to_dict() for a in self._adapters.values()]

    def broadcast(self, text: str, *, channels: list[str] | None = None,
                  **metadata: Any) -> list[ChannelDelivery]:
        slugs = channels if channels else list(self._adapters)
        out: list[ChannelDelivery] = []
        for slug in slugs:
            adapter = self._adapters.get(slug)
            if adapter is None:
                out.append(ChannelDelivery(channel=slug, delivered=False,
                                           detail="unknown channel"))
                continue
            msg = ChannelMessage(channel=slug, text=text, metadata=metadata)
            out.append(adapter.send(msg))
        return out
