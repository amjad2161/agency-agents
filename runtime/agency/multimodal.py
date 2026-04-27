"""Multimodal input handler — normalises text, image, audio, and data inputs.

Provides a unified MultimodalPayload envelope that downstream modules consume.
Actual heavy processing (OCR, transcription) degrades gracefully to stubs.
"""

from __future__ import annotations

import base64
import json
import mimetypes
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from .logging import get_logger

log = get_logger()


class ModalityType(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    DOCUMENT = "document"
    STRUCTURED = "structured"   # JSON / CSV / table
    UNKNOWN = "unknown"


@dataclass
class MultimodalPayload:
    """Normalised input container for any modality.

    Attributes
    ----------
    modality:   detected or declared input type
    text:       extracted / provided text content
    raw_bytes:  raw binary data (None if text-only)
    mime_type:  MIME type string or empty
    metadata:   arbitrary extra info (dimensions, duration, etc.)
    source:     human-readable origin description
    created_at: unix timestamp
    """

    modality: ModalityType = ModalityType.TEXT
    text: str = ""
    raw_bytes: bytes | None = None
    mime_type: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    source: str = ""
    created_at: float = field(default_factory=time.time)

    def is_empty(self) -> bool:
        return not self.text and self.raw_bytes is None

    def to_dict(self) -> dict:
        d = {
            "modality": self.modality,
            "text": self.text,
            "mime_type": self.mime_type,
            "metadata": self.metadata,
            "source": self.source,
            "created_at": self.created_at,
            "has_bytes": self.raw_bytes is not None,
        }
        return d


class MultimodalProcessor:
    """Accept inputs in any modality, normalise to MultimodalPayload.

    Usage::

        proc = MultimodalProcessor()

        # text
        p = proc.from_text("Hello world")

        # file path
        p = proc.from_file(Path("image.png"))

        # base64-encoded bytes
        p = proc.from_base64(b64_string, mime_type="image/png")

        # structured data
        p = proc.from_structured({"key": "value"})

        # extract text from any payload
        text = proc.extract_text(p)
    """

    def __init__(
        self,
        ocr_backend: Any | None = None,
        transcription_backend: Any | None = None,
    ) -> None:
        self._ocr = ocr_backend
        self._transcription = transcription_backend

    # ── factory methods ───────────────────────────────────────────────────────

    def from_text(self, text: str, source: str = "direct") -> MultimodalPayload:
        return MultimodalPayload(
            modality=ModalityType.TEXT,
            text=text,
            mime_type="text/plain",
            source=source,
        )

    def from_file(self, path: Path) -> MultimodalPayload:
        """Load a file and produce an appropriate payload."""
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        mime, _ = mimetypes.guess_type(str(path))
        mime = mime or "application/octet-stream"
        raw = path.read_bytes()
        modality = self._detect_modality(mime)

        payload = MultimodalPayload(
            modality=modality,
            raw_bytes=raw,
            mime_type=mime,
            source=str(path),
            metadata={"filename": path.name, "size_bytes": len(raw)},
        )

        # Auto-extract text for known types
        payload.text = self._auto_extract_text(payload, mime, raw, path)
        return payload

    def from_base64(self, b64: str, mime_type: str = "", source: str = "base64") -> MultimodalPayload:
        """Decode base64 string into a payload."""
        raw = base64.b64decode(b64)
        mime = mime_type or "application/octet-stream"
        modality = self._detect_modality(mime)
        payload = MultimodalPayload(
            modality=modality,
            raw_bytes=raw,
            mime_type=mime,
            source=source,
            metadata={"size_bytes": len(raw)},
        )
        payload.text = self._auto_extract_text(payload, mime, raw, None)
        return payload

    def from_structured(
        self,
        data: dict | list,
        source: str = "structured",
    ) -> MultimodalPayload:
        """Wrap structured data (dict/list) as a payload."""
        text = json.dumps(data, indent=2, ensure_ascii=False)
        return MultimodalPayload(
            modality=ModalityType.STRUCTURED,
            text=text,
            mime_type="application/json",
            source=source,
            metadata={"type": type(data).__name__},
        )

    def from_url(self, url: str) -> MultimodalPayload:
        """Return a text payload describing the URL (no network call)."""
        return MultimodalPayload(
            modality=ModalityType.TEXT,
            text=f"[URL reference: {url}]",
            mime_type="text/uri-list",
            source=url,
        )

    # ── processing ────────────────────────────────────────────────────────────

    def extract_text(self, payload: MultimodalPayload) -> str:
        """Return the best available text representation of the payload."""
        if payload.text:
            return payload.text

        if payload.raw_bytes is None:
            return ""

        if payload.modality == ModalityType.IMAGE:
            return self._ocr_image(payload.raw_bytes, payload.mime_type)
        if payload.modality == ModalityType.AUDIO:
            return self._transcribe_audio(payload.raw_bytes, payload.mime_type)
        if payload.modality == ModalityType.DOCUMENT:
            return self._extract_document_text(payload.raw_bytes, payload.mime_type)

        try:
            return payload.raw_bytes.decode("utf-8", errors="replace")
        except Exception:
            return f"[binary data: {len(payload.raw_bytes)} bytes]"

    def describe(self, payload: MultimodalPayload) -> str:
        """Produce a one-line human description of the payload."""
        parts = [f"modality={payload.modality}"]
        if payload.mime_type:
            parts.append(f"mime={payload.mime_type}")
        if payload.text:
            parts.append(f"text_len={len(payload.text)}")
        if payload.raw_bytes:
            parts.append(f"bytes={len(payload.raw_bytes)}")
        if payload.source:
            parts.append(f"source={payload.source[:40]}")
        return "MultimodalPayload(" + ", ".join(parts) + ")"

    def combine(self, payloads: list[MultimodalPayload], separator: str = "\n\n") -> MultimodalPayload:
        """Merge multiple payloads into a single TEXT payload."""
        texts = [self.extract_text(p) for p in payloads]
        combined_text = separator.join(t for t in texts if t)
        return MultimodalPayload(
            modality=ModalityType.TEXT,
            text=combined_text,
            mime_type="text/plain",
            source="combined",
            metadata={"source_count": len(payloads)},
        )

    # ── internals ─────────────────────────────────────────────────────────────

    @staticmethod
    def _detect_modality(mime: str) -> ModalityType:
        mime_lower = mime.lower()
        if mime_lower.startswith("image/"):
            return ModalityType.IMAGE
        if mime_lower.startswith("audio/"):
            return ModalityType.AUDIO
        if mime_lower.startswith("video/"):
            return ModalityType.VIDEO
        if mime_lower in (
            "application/pdf",
            "application/msword",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ):
            return ModalityType.DOCUMENT
        if mime_lower in ("text/plain", "text/markdown", "text/html"):
            return ModalityType.TEXT
        if mime_lower in ("application/json", "text/csv", "text/tab-separated-values"):
            return ModalityType.STRUCTURED
        return ModalityType.UNKNOWN

    def _auto_extract_text(
        self,
        payload: MultimodalPayload,
        mime: str,
        raw: bytes,
        path: Path | None,
    ) -> str:
        if mime.startswith("text/"):
            return raw.decode("utf-8", errors="replace")
        if mime == "application/json":
            try:
                return json.dumps(json.loads(raw), indent=2)
            except Exception:
                return raw.decode("utf-8", errors="replace")
        return ""

    def _ocr_image(self, raw: bytes, mime_type: str) -> str:
        if self._ocr:
            try:
                return self._ocr(raw, mime_type)
            except Exception as exc:
                log.warning("multimodal: OCR failed — %s", exc)
        return f"[image/{len(raw)} bytes — OCR not available]"

    def _transcribe_audio(self, raw: bytes, mime_type: str) -> str:
        if self._transcription:
            try:
                return self._transcription(raw, mime_type)
            except Exception as exc:
                log.warning("multimodal: transcription failed — %s", exc)
        return f"[audio/{len(raw)} bytes — transcription not available]"

    def _extract_document_text(self, raw: bytes, mime_type: str) -> str:
        if mime_type == "application/pdf":
            # Try pdfminer if available
            try:
                import io
                from pdfminer.high_level import extract_text_to_fp  # type: ignore[import]
                buf = io.StringIO()
                extract_text_to_fp(io.BytesIO(raw), buf)
                return buf.getvalue()
            except ImportError:
                pass
            except Exception as exc:
                log.warning("multimodal: PDF extraction failed — %s", exc)
        return f"[document/{len(raw)} bytes — extraction not available]"
