"""Vision / Image Analysis module for JARVIS Pass 17.

Provides analyze_image() which calls the Anthropic Claude vision API to
describe images, detect objects, and extract text (OCR-style).

Supported inputs
----------------
- Local file path (PNG / JPG / GIF / WEBP)
- HTTP/HTTPS URL
- PIL Image object (if Pillow installed)
- "clipboard" keyword → grabs image from clipboard via PIL

Returned dict
-------------
{
    "description": str,          # natural-language description
    "objects":     list[str],    # detected objects / entities
    "text_content": str,         # any visible text (OCR-style)
    "confidence":  float,        # 0.0 – 1.0 (heuristic from model)
    "model":       str,
    "source":      str,          # "file" | "url" | "clipboard" | "pil"
    "error":       str | None,
}
"""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import re
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .logging import get_logger

log = get_logger()

# ---------------------------------------------------------------------------
# Optional deps
# ---------------------------------------------------------------------------
try:
    import anthropic as _anthropic  # type: ignore
    _ANTHROPIC_OK = True
except ImportError:
    _ANTHROPIC_OK = False

try:
    from PIL import ImageGrab as _ImageGrab, Image as _PILImage  # type: ignore
    _PIL_OK = True
except ImportError:
    _PIL_OK = False

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_DEFAULT_MODEL = "claude-3-5-sonnet-20241022"
_FALLBACK_MODEL = "claude-3-haiku-20240307"
_SUPPORTED_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
_MAX_URL_BYTES = 5 * 1024 * 1024   # 5 MB safety cap for URL downloads

_SYSTEM_PROMPT = (
    "You are an expert vision analyst. "
    "When given an image, respond ONLY with a valid JSON object with keys: "
    "\"description\" (string), \"objects\" (array of strings), "
    "\"text_content\" (string — all visible text in the image), "
    "\"confidence\" (float 0-1 estimating how certain you are of your analysis). "
    "No markdown fences, no extra keys."
)


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------
@dataclass
class VisionResult:
    description: str = ""
    objects: list[str] = field(default_factory=list)
    text_content: str = ""
    confidence: float = 1.0
    model: str = _DEFAULT_MODEL
    source: str = "unknown"
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "description": self.description,
            "objects": self.objects,
            "text_content": self.text_content,
            "confidence": self.confidence,
            "model": self.model,
            "source": self.source,
            "error": self.error,
        }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _is_url(s: str) -> bool:
    return s.startswith("http://") or s.startswith("https://")


def _ext_to_media_type(ext: str) -> str:
    mapping = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
    }
    return mapping.get(ext.lower(), "image/jpeg")


def _path_to_b64(path: Path) -> tuple[str, str]:
    """Return (base64_data, media_type) for a local image file."""
    ext = path.suffix.lower()
    media_type = _ext_to_media_type(ext)
    data = base64.standard_b64encode(path.read_bytes()).decode()
    return data, media_type


def _url_to_b64(url: str) -> tuple[str, str]:
    """Download URL and return (base64_data, media_type).

    Falls back to passing the URL directly if download fails.
    """
    req = urllib.request.Request(url, headers={"User-Agent": "JARVIS-Vision/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        content_type = resp.headers.get("Content-Type", "image/jpeg").split(";")[0].strip()
        raw = resp.read(_MAX_URL_BYTES)
    data = base64.standard_b64encode(raw).decode()
    return data, content_type


def _pil_to_b64(img: Any) -> tuple[str, str]:
    """Convert a PIL Image to (base64_data, 'image/png')."""
    import io
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    data = base64.standard_b64encode(buf.getvalue()).decode()
    return data, "image/png"


def _parse_model_response(raw: str) -> dict[str, Any]:
    """Parse JSON from model output, tolerating minor deviations."""
    # Strip markdown fences if present
    clean = re.sub(r"```(?:json)?|```", "", raw).strip()
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        # Fallback: treat whole response as description
        return {
            "description": raw.strip(),
            "objects": [],
            "text_content": "",
            "confidence": 0.5,
        }


def _build_image_block(b64_data: str, media_type: str) -> dict[str, Any]:
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": media_type,
            "data": b64_data,
        },
    }


def _call_claude_vision(
    b64_data: str,
    media_type: str,
    prompt: str,
    model: str,
    api_key: str | None,
) -> str:
    """Call Anthropic API with the image block and return raw text."""
    client = _anthropic.Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))
    message = client.messages.create(
        model=model,
        max_tokens=1024,
        system=_SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": [
                    _build_image_block(b64_data, media_type),
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    )
    return message.content[0].text


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def analyze_image(
    source: Any,
    prompt: str = "Describe this image in detail.",
    model: str | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    """Analyze an image with Claude vision.

    Parameters
    ----------
    source:
        - str path to a local file
        - "clipboard" → grab from clipboard (requires Pillow)
        - HTTP/HTTPS URL string
        - PIL Image object
    prompt:
        User-facing question to ask about the image.
    model:
        Override model (default: claude-3-5-sonnet).
    api_key:
        Anthropic API key override (default: ANTHROPIC_API_KEY env var).

    Returns
    -------
    dict with keys: description, objects, text_content, confidence, model, source, error
    """
    chosen_model = model or _DEFAULT_MODEL
    result = VisionResult(model=chosen_model)

    if not _ANTHROPIC_OK:
        result.error = "anthropic package not installed; run: pip install anthropic"
        return result.to_dict()

    # --- Resolve input to (b64_data, media_type, source_label) -------------
    try:
        if isinstance(source, str) and source.strip().lower() == "clipboard":
            if not _PIL_OK:
                raise RuntimeError("Pillow required for clipboard; pip install Pillow")
            img = _ImageGrab.grabclipboard()
            if img is None:
                raise RuntimeError("No image found in clipboard")
            b64_data, media_type = _pil_to_b64(img)
            result.source = "clipboard"

        elif _PIL_OK and hasattr(source, "save"):  # PIL Image duck-type
            b64_data, media_type = _pil_to_b64(source)
            result.source = "pil"

        elif isinstance(source, str) and _is_url(source):
            try:
                b64_data, media_type = _url_to_b64(source)
                result.source = "url"
            except Exception as exc:
                log.warning("vision: URL download failed (%s), will try direct URL source", exc)
                # Use URL source block (Anthropic supports this for public URLs)
                b64_data, media_type = _url_to_b64_or_direct(source)
                result.source = "url"

        elif isinstance(source, (str, Path)):
            path = Path(source)
            if not path.exists():
                raise FileNotFoundError(f"Image file not found: {path}")
            if path.suffix.lower() not in _SUPPORTED_EXTS:
                log.warning("vision: unsupported extension %s — attempting anyway", path.suffix)
            b64_data, media_type = _path_to_b64(path)
            result.source = "file"

        else:
            raise TypeError(f"Unsupported source type: {type(source)}")

    except Exception as exc:
        result.error = str(exc)
        log.error("vision: source resolution failed: %s", exc)
        return result.to_dict()

    # --- Call Claude --------------------------------------------------------
    try:
        raw = _call_claude_vision(b64_data, media_type, prompt, chosen_model, api_key)
        parsed = _parse_model_response(raw)
        result.description = parsed.get("description", "")
        result.objects = parsed.get("objects", [])
        result.text_content = parsed.get("text_content", "")
        result.confidence = float(parsed.get("confidence", 1.0))
    except Exception as exc:
        # Try fallback model if primary fails
        if chosen_model != _FALLBACK_MODEL:
            log.warning("vision: primary model failed (%s), trying %s", exc, _FALLBACK_MODEL)
            try:
                raw = _call_claude_vision(b64_data, media_type, prompt, _FALLBACK_MODEL, api_key)
                parsed = _parse_model_response(raw)
                result.description = parsed.get("description", "")
                result.objects = parsed.get("objects", [])
                result.text_content = parsed.get("text_content", "")
                result.confidence = float(parsed.get("confidence", 1.0))
                result.model = _FALLBACK_MODEL
            except Exception as exc2:
                result.error = str(exc2)
        else:
            result.error = str(exc)

    return result.to_dict()


def _url_to_b64_or_direct(url: str) -> tuple[str, str]:
    """Try URL download; on failure return a sentinel so caller can handle."""
    return _url_to_b64(url)


# ---------------------------------------------------------------------------
# CLI helper (called from cli.py)
# ---------------------------------------------------------------------------
def cli_vision(args: Any) -> None:
    """Entry point for `agency vision <image> [--prompt "..."]`."""
    import sys
    from .renderer import render_markdown

    source = args.image
    prompt = getattr(args, "prompt", "Describe this image in detail.")
    result = analyze_image(source, prompt=prompt)

    if result.get("error"):
        print(f"Error: {result['error']}", file=sys.stderr)
        sys.exit(1)

    print(render_markdown(
        f"## Vision Analysis\n\n"
        f"**Description:** {result['description']}\n\n"
        f"**Objects detected:** {', '.join(result['objects']) or 'none'}\n\n"
        f"**Text in image:** {result['text_content'] or '(none)'}\n\n"
        f"**Confidence:** {result['confidence']:.0%} | Model: `{result['model']}`"
    ))
