"""Multimodal input normalization.

Accepts text, files, base64 blobs, structured payloads, and URLs;
returns a uniform `MultimodalInput` envelope the rest of the runtime
can shuttle into Anthropic message blocks or downstream tools.

Out of scope: actually rendering audio, OCR'ing images, transcribing
video. Those are owned by `tools.py` and external services. This
module is the *type-safe entry point* — the thing that says "here is
a piece of input, here's its modality, here's enough metadata to
decide what to do next."
"""

from __future__ import annotations

import base64
import binascii
import json
import mimetypes
import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Iterable


class ModalityType(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    DOCUMENT = "document"
    STRUCTURED = "structured"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class MultimodalInput:
    """A single input chunk. Immutable — combinations produce new
    instances via `MultimodalProcessor.combine()`."""

    modality: ModalityType
    payload: Any
    mime_type: str = ""
    source: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_textual(self) -> bool:
        return self.modality in (
            ModalityType.TEXT,
            ModalityType.DOCUMENT,
            ModalityType.STRUCTURED,
        )

    def to_dict(self) -> dict:
        return {
            "modality": self.modality.value,
            "payload": (
                self.payload
                if self.is_textual()
                else f"<{self.modality.value} bytes len={len(self.payload) if isinstance(self.payload, (bytes, bytearray)) else '?'}>"
            ),
            "mime_type": self.mime_type,
            "source": self.source,
            "metadata": dict(self.metadata),
        }


_MIME_TO_MODALITY: tuple[tuple[str, ModalityType], ...] = (
    ("text/", ModalityType.TEXT),
    ("image/", ModalityType.IMAGE),
    ("audio/", ModalityType.AUDIO),
    ("video/", ModalityType.VIDEO),
    ("application/pdf", ModalityType.DOCUMENT),
    ("application/msword", ModalityType.DOCUMENT),
    ("application/vnd.openxmlformats", ModalityType.DOCUMENT),
    ("application/vnd.ms-", ModalityType.DOCUMENT),
    ("application/json", ModalityType.STRUCTURED),
    ("application/xml", ModalityType.STRUCTURED),
    ("application/yaml", ModalityType.STRUCTURED),
    ("application/x-yaml", ModalityType.STRUCTURED),
)


def _modality_from_mime(mime: str) -> ModalityType:
    mime = (mime or "").lower()
    for prefix, modality in _MIME_TO_MODALITY:
        if mime.startswith(prefix):
            return modality
    return ModalityType.UNKNOWN


_STRUCTURED_EXTS = {".json", ".yaml", ".yml", ".toml", ".csv", ".tsv"}
_DOCUMENT_EXTS = {".pdf", ".docx", ".doc", ".pptx", ".xlsx", ".xls", ".odt", ".rtf"}
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff", ".heic"}
_AUDIO_EXTS = {".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac"}
_VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".avi"}


def _modality_from_path(path: Path) -> ModalityType:
    ext = path.suffix.lower()
    if ext in _STRUCTURED_EXTS:
        return ModalityType.STRUCTURED
    if ext in _DOCUMENT_EXTS:
        return ModalityType.DOCUMENT
    if ext in _IMAGE_EXTS:
        return ModalityType.IMAGE
    if ext in _AUDIO_EXTS:
        return ModalityType.AUDIO
    if ext in _VIDEO_EXTS:
        return ModalityType.VIDEO
    return ModalityType.TEXT  # default for unrecognized text-y files


class MultimodalProcessor:
    """Stateless factory for `MultimodalInput`."""

    @staticmethod
    def from_text(text: str, *, source: str = "inline") -> MultimodalInput:
        if not isinstance(text, str):
            raise TypeError("text must be a str")
        return MultimodalInput(
            modality=ModalityType.TEXT,
            payload=text,
            mime_type="text/plain",
            source=source,
        )

    @staticmethod
    def from_file(path: str | os.PathLike) -> MultimodalInput:
        p = Path(path)
        if not p.is_file():
            raise FileNotFoundError(f"not a file: {p}")
        mime, _ = mimetypes.guess_type(str(p))
        modality = (
            _modality_from_mime(mime) if mime else ModalityType.UNKNOWN
        )
        if modality is ModalityType.UNKNOWN:
            modality = _modality_from_path(p)
        if modality.is_textual() if hasattr(modality, "is_textual") else (
            modality in (ModalityType.TEXT, ModalityType.STRUCTURED)
        ):
            try:
                payload: Any = p.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                payload = p.read_bytes()
                modality = ModalityType.UNKNOWN
        elif modality is ModalityType.TEXT:
            payload = p.read_text(encoding="utf-8", errors="replace")
        else:
            payload = p.read_bytes()
        return MultimodalInput(
            modality=modality,
            payload=payload,
            mime_type=mime or "",
            source=str(p),
            metadata={"size_bytes": p.stat().st_size},
        )

    @staticmethod
    def from_base64(
        data: str, mime_type: str, *, source: str = "base64"
    ) -> MultimodalInput:
        try:
            raw = base64.b64decode(data, validate=True)
        except (ValueError, binascii.Error) as e:
            raise ValueError(f"invalid base64: {e}") from e
        modality = _modality_from_mime(mime_type)
        payload: Any = raw
        if modality in (ModalityType.TEXT, ModalityType.STRUCTURED):
            try:
                payload = raw.decode("utf-8")
            except UnicodeDecodeError:
                pass
        return MultimodalInput(
            modality=modality,
            payload=payload,
            mime_type=mime_type,
            source=source,
            metadata={"size_bytes": len(raw)},
        )

    @staticmethod
    def from_structured(data: Any, *, source: str = "inline") -> MultimodalInput:
        try:
            payload = json.dumps(data, ensure_ascii=False, sort_keys=True)
        except (TypeError, ValueError) as e:
            raise ValueError(f"data not JSON-serializable: {e}") from e
        return MultimodalInput(
            modality=ModalityType.STRUCTURED,
            payload=payload,
            mime_type="application/json",
            source=source,
            metadata={"original_type": type(data).__name__},
        )

    @staticmethod
    def from_url(url: str, *, timeout_s: float = 10.0) -> MultimodalInput:
        if not (url.startswith("http://") or url.startswith("https://")):
            raise ValueError("url must be http or https")
        try:
            import httpx  # type: ignore
        except ImportError as e:
            raise RuntimeError(
                "from_url requires httpx — `pip install httpx`"
            ) from e
        try:
            from .tools import _is_metadata_host, _is_private_host  # type: ignore
        except ImportError:
            _is_private_host = lambda h: False  # noqa: E731
            _is_metadata_host = lambda h: False  # noqa: E731
        parsed = httpx.URL(url)
        host = parsed.host or ""
        if not host:
            raise ValueError("url has no host")
        if _is_metadata_host(host) or _is_private_host(host):
            raise PermissionError(
                f"refusing to fetch private/metadata host {host!r}"
            )
        with httpx.Client(timeout=timeout_s, follow_redirects=True) as client:
            resp = client.get(url)
            resp.raise_for_status()
            mime = resp.headers.get("content-type", "").split(";")[0].strip()
            modality = _modality_from_mime(mime)
            if modality in (ModalityType.TEXT, ModalityType.STRUCTURED):
                payload: Any = resp.text
            else:
                payload = resp.content
        return MultimodalInput(
            modality=modality,
            payload=payload,
            mime_type=mime,
            source=url,
            metadata={"status_code": resp.status_code},
        )

    @staticmethod
    def extract_text(inp: MultimodalInput) -> str:
        """Best-effort textual rendering. Returns the payload directly
        if it's already a string; a tagged stub for binary modalities."""
        if isinstance(inp.payload, str):
            return inp.payload
        if isinstance(inp.payload, (bytes, bytearray)):
            try:
                return inp.payload.decode("utf-8")
            except UnicodeDecodeError:
                size = len(inp.payload)
                return f"<{inp.modality.value} blob bytes={size} mime={inp.mime_type}>"
        try:
            return json.dumps(inp.payload, ensure_ascii=False)
        except (TypeError, ValueError):
            return str(inp.payload)

    @staticmethod
    def combine(inputs: Iterable[MultimodalInput]) -> MultimodalInput:
        """Join textual inputs into one TEXT envelope. Non-text inputs
        are summarized via `extract_text`. Useful for shoving a mixed
        stream into a model that only accepts plain text."""
        seq = list(inputs)
        if not seq:
            raise ValueError("no inputs to combine")
        chunks = []
        sources = []
        for inp in seq:
            chunks.append(MultimodalProcessor.extract_text(inp))
            if inp.source:
                sources.append(inp.source)
        return MultimodalInput(
            modality=ModalityType.TEXT,
            payload="\n\n".join(chunks),
            mime_type="text/plain",
            source=", ".join(sources),
            metadata={"combined_from": len(seq)},
        )
