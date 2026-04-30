"""Multimodal output (Tier 3) — fuse text + diagram + audio + document.

Single entry-point that takes a request and produces a bundle containing
every modality requested. Pure-Python; each modality routes to its own
subsystem (drawing engine, document generator, voice synthesis).
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from typing import Any, Iterable

from .document_generator import Document, DocumentGenerator
from .drawing_engine import Diagram, DrawingEngine, quick_diagram
from .local_voice import LocalVoice, detect_language


SUPPORTED_MODALITIES: tuple[str, ...] = ("text", "diagram", "audio", "document")


@dataclass
class ModalityArtifact:
    kind: str
    mime: str
    payload: str  # base64 for binary, plain for text/markdown/svg
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class MultimodalBundle:
    request: str
    artifacts: list[ModalityArtifact] = field(default_factory=list)

    def by_kind(self, kind: str) -> ModalityArtifact | None:
        for a in self.artifacts:
            if a.kind == kind:
                return a
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "request": self.request,
            "artifacts": [a.to_dict() for a in self.artifacts],
        }


class MultimodalOutput:
    """Bundle text + diagram + audio + document for a single request."""

    def __init__(self, *, voice: LocalVoice | None = None,
                 docgen: DocumentGenerator | None = None,
                 draw: DrawingEngine | None = None) -> None:
        self.voice = voice or LocalVoice()
        self.docgen = docgen or DocumentGenerator()
        self.draw = draw or DrawingEngine()

    def render(self, request: str, *,
               text: str | None = None,
               diagram: Diagram | None = None,
               document: Document | None = None,
               document_format: str = "markdown",
               want: Iterable[str] = SUPPORTED_MODALITIES,
               voice: str | None = None) -> MultimodalBundle:
        bundle = MultimodalBundle(request=request)
        wants = {w.lower() for w in want}
        for w in wants:
            if w not in SUPPORTED_MODALITIES:
                raise ValueError(f"unknown modality {w!r}; "
                                 f"expected one of {SUPPORTED_MODALITIES}")

        if "text" in wants:
            text_payload = text or f"Response for: {request}"
            bundle.artifacts.append(ModalityArtifact(
                kind="text", mime="text/plain", payload=text_payload,
                meta={"language": detect_language(text_payload)},
            ))

        if "diagram" in wants:
            diagram = diagram or quick_diagram(
                "flowchart", title=request[:60] or "diagram",
                nodes=["Input", "Process", "Output"],
                edges=[("n0", "n1"), ("n1", "n2")],
            )
            svg = self.draw.render(diagram)
            bundle.artifacts.append(ModalityArtifact(
                kind="diagram", mime="image/svg+xml", payload=svg,
                meta={"diagram_kind": diagram.kind, "title": diagram.title},
            ))

        if "audio" in wants:
            spoken = text or request
            audio = self.voice.synthesize(spoken, voice=voice)
            bundle.artifacts.append(ModalityArtifact(
                kind="audio", mime="audio/wav",
                payload=base64.b64encode(audio).decode("ascii"),
                meta={"bytes": len(audio), "engine": self.voice.health()["tts"]},
            ))

        if "document" in wants:
            doc = document or Document(
                template="business-strategy",
                title=request[:80] or "JARVIS Output",
                sections=[("Summary", text or request)],
            )
            data = self.docgen.render(doc, fmt=document_format)
            mime = {
                "markdown": "text/markdown",
                "html": "text/html",
                "pdf": "application/pdf",
                "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            }.get(document_format, "application/octet-stream")
            try:
                payload = data.decode("utf-8")
                binary = False
            except UnicodeDecodeError:
                payload = base64.b64encode(data).decode("ascii")
                binary = True
            bundle.artifacts.append(ModalityArtifact(
                kind="document", mime=mime, payload=payload,
                meta={"template": doc.template, "format": document_format,
                      "binary": binary, "bytes": len(data)},
            ))

        return bundle
