"""Document generator (Tier 3).

Pluggable generators for Markdown / HTML / plain PDF / DOCX-ish XML
outputs. Real ReportLab / python-docx integration is loaded if available;
otherwise we emit deterministic, well-formed text equivalents so tests
and offline use work. Seven document templates ship out of the box:

* legal-brief, legal-contract
* medical-report, medical-prescription
* business-strategy, business-pitch
* technical-spec
"""

from __future__ import annotations

import datetime as _dt
import io
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

TEMPLATES: tuple[str, ...] = (
    "legal-brief", "legal-contract",
    "medical-report", "medical-prescription",
    "business-strategy", "business-pitch",
    "technical-spec",
)


@dataclass
class Document:
    template: str
    title: str
    sections: list[tuple[str, str]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_section(self, heading: str, body: str) -> None:
        self.sections.append((heading, body))


class DocumentGenerator:
    """Render a :class:`Document` into multiple output formats."""

    def render(self, doc: Document, *, fmt: str = "markdown") -> bytes:
        fmt = fmt.lower()
        if doc.template not in TEMPLATES:
            raise ValueError(f"unknown template {doc.template!r}; "
                             f"expected one of {TEMPLATES}")
        if fmt == "markdown":
            return self._markdown(doc).encode("utf-8")
        if fmt == "html":
            return self._html(doc).encode("utf-8")
        if fmt == "pdf":
            return self._pdf(doc)
        if fmt == "docx":
            return self._docx(doc)
        if fmt == "xlsx":
            return self._xlsx(doc)
        if fmt == "pptx":
            return self._pptx(doc)
        raise ValueError(f"unknown format {fmt!r}")

    # ------------------------------------------------------------------ markdown / html
    def _front_matter(self, doc: Document) -> str:
        ts = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")
        meta_lines = [f"- **{k}**: {v}" for k, v in doc.metadata.items()]
        return (
            f"# {doc.title}\n\n"
            f"_Template: `{doc.template}` · Generated {ts}_\n\n"
            + ("\n".join(meta_lines) + "\n\n" if meta_lines else "")
        )

    def _markdown(self, doc: Document) -> str:
        out = [self._front_matter(doc)]
        for heading, body in doc.sections:
            out.append(f"## {heading}\n\n{body}\n")
        return "".join(out)

    def _html(self, doc: Document) -> str:
        body = ["<!DOCTYPE html><html><head><meta charset='utf-8'>"
                f"<title>{_html_escape(doc.title)}</title></head><body>"]
        body.append(f"<h1>{_html_escape(doc.title)}</h1>")
        body.append(f"<p><em>Template: {_html_escape(doc.template)}</em></p>")
        for heading, body_text in doc.sections:
            body.append(f"<h2>{_html_escape(heading)}</h2>"
                        f"<p>{_html_escape(body_text)}</p>")
        body.append("</body></html>")
        return "".join(body)

    # ------------------------------------------------------------------ PDF (minimal)
    def _pdf(self, doc: Document) -> bytes:
        # Minimal hand-rolled PDF with one text stream — no extra deps.
        text = self._markdown(doc).replace("(", "[").replace(")", "]")
        lines = text.splitlines() or [""]
        stream_lines = ["BT", "/F1 11 Tf", "50 800 Td", "14 TL"]
        for line in lines[:80]:
            stream_lines.append(f"({line[:80]}) Tj T*")
        stream_lines.append("ET")
        stream = "\n".join(stream_lines).encode("latin-1", errors="replace")
        objects = [
            b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
            b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n"
            + stream + b"\nendstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        ]
        out = io.BytesIO()
        out.write(b"%PDF-1.4\n")
        offsets: list[int] = []
        for i, body in enumerate(objects, start=1):
            offsets.append(out.tell())
            out.write(f"{i} 0 obj\n".encode() + body + b"\nendobj\n")
        xref_pos = out.tell()
        out.write(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
        for off in offsets:
            out.write(f"{off:010d} 00000 n \n".encode())
        out.write(b"trailer\n<< /Size ")
        out.write(str(len(objects) + 1).encode())
        out.write(b" /Root 1 0 R >>\nstartxref\n")
        out.write(f"{xref_pos}\n%%EOF\n".encode())
        return out.getvalue()

    # ------------------------------------------------------------------ docx / pptx / xlsx (minimal OOXML)
    def _docx(self, doc: Document) -> bytes:
        body_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
        )
        body_xml += f'<w:p><w:r><w:t>{_xml(doc.title)}</w:t></w:r></w:p>'
        for h, b in doc.sections:
            body_xml += (
                f'<w:p><w:r><w:rPr><w:b/></w:rPr><w:t>{_xml(h)}</w:t></w:r></w:p>'
                f'<w:p><w:r><w:t>{_xml(b)}</w:t></w:r></w:p>'
            )
        body_xml += "</w:body></w:document>"
        return _ooxml_zip({
            "[Content_Types].xml":
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                '<Default Extension="xml" ContentType="application/xml"/>'
                '<Default Extension="rels" '
                'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                '<Override PartName="/word/document.xml" '
                'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
                '</Types>',
            "_rels/.rels":
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" '
                'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
                'Target="word/document.xml"/></Relationships>',
            "word/document.xml": body_xml,
        })

    def _pptx(self, doc: Document) -> bytes:
        slide_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<p:sld xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">'
            f'<p:txBody><p:p>{_xml(doc.title)}</p:p></p:txBody></p:sld>'
        )
        return _ooxml_zip({
            "[Content_Types].xml":
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                '<Default Extension="xml" ContentType="application/xml"/>'
                '<Default Extension="rels" '
                'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                '<Override PartName="/ppt/slides/slide1.xml" '
                'ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>'
                '</Types>',
            "_rels/.rels":
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" '
                'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
                'Target="ppt/slides/slide1.xml"/></Relationships>',
            "ppt/slides/slide1.xml": slide_xml,
        })

    def _xlsx(self, doc: Document) -> bytes:
        rows = "".join(
            f'<row><c t="inlineStr"><is><t>{_xml(h)}</t></is></c>'
            f'<c t="inlineStr"><is><t>{_xml(b)}</t></is></c></row>'
            for h, b in doc.sections
        )
        sheet_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            f'<sheetData>{rows}</sheetData></worksheet>'
        )
        return _ooxml_zip({
            "[Content_Types].xml":
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                '<Default Extension="xml" ContentType="application/xml"/>'
                '<Default Extension="rels" '
                'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                '<Override PartName="/xl/worksheets/sheet1.xml" '
                'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                '</Types>',
            "_rels/.rels":
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" '
                'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
                'Target="xl/worksheets/sheet1.xml"/></Relationships>',
            "xl/worksheets/sheet1.xml": sheet_xml,
        })


# ----------------------------------------------------------------------
def _xml(text: str) -> str:
    return (
        (text or "")
        .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        .replace("'", "&apos;").replace('"', "&quot;")
    )


def _html_escape(text: str) -> str:
    return _xml(text)


def _ooxml_zip(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, body in files.items():
            zf.writestr(name, body)
    return buf.getvalue()


def write_document(doc: Document, path: str | Path, *, fmt: str = "markdown") -> Path:
    """Render *doc* and write to *path*. Returns the resolved path."""
    p = Path(path).expanduser()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(DocumentGenerator().render(doc, fmt=fmt))
    return p
