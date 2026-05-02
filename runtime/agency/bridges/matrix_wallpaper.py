"""Matrix-rain animated wallpaper bridge.

Generates a self-contained HTML page that runs a full-screen Matrix
"digital rain" animation on an HTML5 canvas. On Windows the bridge can
launch the page in a fullscreen browser kiosk and (best-effort) ask the
shell to set a static rendering as the desktop wallpaper via
``SystemParametersInfoW``.

The bridge is import-safe on every platform — Windows-only paths only
fire when ``set_as_wallpaper`` / ``start_screensaver`` is called and a
graceful no-op result is returned on other systems.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from ..logging import get_logger

log = get_logger()


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_COLOR = "#00ff41"
DEFAULT_SPEED = 1.0
DEFAULT_DENSITY = 0.8
DEFAULT_LANGUAGE = "mixed"

_VALID_LANGUAGES = {"mixed", "katakana", "ascii", "hebrew", "binary"}


# ---------------------------------------------------------------------------
# HTML template
# ---------------------------------------------------------------------------

_HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>JARVIS — Matrix Rain</title>
<style>
  html, body {
    margin: 0;
    padding: 0;
    height: 100%;
    width: 100%;
    background: #000;
    overflow: hidden;
    cursor: none;
  }
  canvas {
    display: block;
    position: fixed;
    inset: 0;
    width: 100vw;
    height: 100vh;
    background: #000;
  }
  #brand {
    position: fixed;
    bottom: 1.2rem;
    right: 1.6rem;
    font-family: "Consolas", "Courier New", monospace;
    font-size: 0.8rem;
    letter-spacing: 0.25em;
    color: __COLOR__;
    opacity: 0.55;
    text-shadow: 0 0 8px __COLOR__;
    pointer-events: none;
    user-select: none;
  }
</style>
</head>
<body>
<canvas id="rain"></canvas>
<div id="brand">JARVIS // MATRIX</div>
<script>
(function () {
  "use strict";
  var COLOR = "__COLOR__";
  var SPEED = __SPEED__;
  var DENSITY = __DENSITY__;
  var LANGUAGE = "__LANGUAGE__";

  var KATAKANA = "アイウエオカキクケコ" +
                 "サシスセソタチツテト" +
                 "ナニヌネノハヒフヘホ" +
                 "マミムメモヤユヨラリ";
  var HEBREW   = "אבגדהוזחטי" +
                 "כלמנסעפצקר" +
                 "שת";
  var ASCII    = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ$+*<>/?#@!&%";
  var BINARY   = "01";

  var glyphs;
  if (LANGUAGE === "katakana") glyphs = KATAKANA;
  else if (LANGUAGE === "ascii") glyphs = ASCII;
  else if (LANGUAGE === "hebrew") glyphs = HEBREW;
  else if (LANGUAGE === "binary") glyphs = BINARY;
  else glyphs = KATAKANA + ASCII + HEBREW;

  var canvas = document.getElementById("rain");
  var ctx = canvas.getContext("2d");
  var width = 0, height = 0, columns = 0, drops = [], speeds = [], heads = [];
  var fontSize = 18;

  function resize() {
    width = canvas.width = window.innerWidth * window.devicePixelRatio;
    height = canvas.height = window.innerHeight * window.devicePixelRatio;
    canvas.style.width = window.innerWidth + "px";
    canvas.style.height = window.innerHeight + "px";
    columns = Math.max(1, Math.floor(width / fontSize));
    drops = new Array(columns);
    speeds = new Array(columns);
    heads = new Array(columns);
    for (var i = 0; i < columns; i++) {
      drops[i] = Math.random() * -height;
      speeds[i] = (0.6 + Math.random() * 0.8) * SPEED;
      heads[i]  = Math.random() < DENSITY;
    }
  }

  function pickGlyph() {
    return glyphs.charAt(Math.floor(Math.random() * glyphs.length));
  }

  function frame() {
    ctx.fillStyle = "rgba(0,0,0,0.08)";
    ctx.fillRect(0, 0, width, height);

    ctx.font = fontSize + "px Consolas, 'Courier New', monospace";
    ctx.textBaseline = "top";

    for (var i = 0; i < columns; i++) {
      if (!heads[i]) continue;
      var x = i * fontSize;
      var y = drops[i];
      // bright head
      ctx.fillStyle = "#cfffd9";
      ctx.fillText(pickGlyph(), x, y);
      // trailing tail
      ctx.fillStyle = COLOR;
      ctx.fillText(pickGlyph(), x, y - fontSize);

      drops[i] += fontSize * speeds[i];
      if (drops[i] > height && Math.random() > 0.975) {
        drops[i] = -fontSize * (1 + Math.random() * 12);
        speeds[i] = (0.6 + Math.random() * 0.8) * SPEED;
      }
    }
    requestAnimationFrame(frame);
  }

  window.addEventListener("resize", resize);
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") window.close();
  });
  resize();
  frame();
})();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Bridge
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _Config:
    color: str
    speed: float
    density: float
    language: str


class MatrixWallpaperBridge:
    """Generate and run a Matrix rain wallpaper.

    The bridge has no side effects at import time. ``generate_html``
    writes a self-contained HTML file. ``set_as_wallpaper`` /
    ``start_screensaver`` launch a fullscreen browser kiosk on Windows
    (best-effort on other platforms — they still produce the HTML and
    return a structured result describing what happened).
    """

    def __init__(
        self,
        assets_dir: Optional[Path | str] = None,
    ) -> None:
        if assets_dir is None:
            assets_dir = Path("assets") / "wallpaper"
        self._assets_dir = Path(assets_dir)
        self._html_path: Optional[Path] = None
        self._process: Optional[subprocess.Popen[Any]] = None

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    @property
    def assets_dir(self) -> Path:
        return self._assets_dir

    @property
    def html_path(self) -> Optional[Path]:
        return self._html_path

    @property
    def is_running(self) -> bool:
        if self._process is None:
            return False
        return self._process.poll() is None

    @property
    def platform_supports_wallpaper(self) -> bool:
        return platform.system() == "Windows"

    def get_status(self) -> Dict[str, Any]:
        return {
            "running": self.is_running,
            "pid": self._process.pid if self.is_running and self._process else None,
            "html_path": str(self._html_path) if self._html_path else None,
            "platform": platform.system(),
            "wallpaper_supported": self.platform_supports_wallpaper,
        }

    # ------------------------------------------------------------------
    # HTML generation
    # ------------------------------------------------------------------

    def generate_html(
        self,
        color: str = DEFAULT_COLOR,
        speed: float = DEFAULT_SPEED,
        density: float = DEFAULT_DENSITY,
        language: str = DEFAULT_LANGUAGE,
    ) -> Path:
        """Write the Matrix-rain page to ``<assets_dir>/matrix.html``."""
        cfg = self._validate(color, speed, density, language)
        self._assets_dir.mkdir(parents=True, exist_ok=True)
        html = (
            _HTML_TEMPLATE
            .replace("__COLOR__", cfg.color)
            .replace("__SPEED__", _fmt_float(cfg.speed))
            .replace("__DENSITY__", _fmt_float(cfg.density))
            .replace("__LANGUAGE__", cfg.language)
        )
        out = self._assets_dir / "matrix.html"
        out.write_text(html, encoding="utf-8")
        self._html_path = out
        log.info("MatrixWallpaperBridge: wrote %s", out)
        return out

    def _validate(
        self,
        color: str,
        speed: float,
        density: float,
        language: str,
    ) -> _Config:
        if not isinstance(color, str) or not color.startswith("#") or len(color) not in (4, 7, 9):
            raise ValueError(f"color must be a hex string like '#00ff41', got {color!r}")
        try:
            int(color.lstrip("#"), 16)
        except ValueError as exc:
            raise ValueError(f"color is not valid hex: {color!r}") from exc
        sp = float(speed)
        if not (0.05 <= sp <= 10.0):
            raise ValueError(f"speed must be between 0.05 and 10.0, got {speed!r}")
        dn = float(density)
        if not (0.05 <= dn <= 1.0):
            raise ValueError(f"density must be between 0.05 and 1.0, got {density!r}")
        if language not in _VALID_LANGUAGES:
            raise ValueError(
                f"language must be one of {sorted(_VALID_LANGUAGES)}, got {language!r}"
            )
        return _Config(color=color, speed=sp, density=dn, language=language)

    # ------------------------------------------------------------------
    # Browser launch
    # ------------------------------------------------------------------

    def start_screensaver(
        self,
        duration_seconds: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Launch the Matrix page fullscreen in a kiosk-mode browser."""
        if self._html_path is None or not self._html_path.exists():
            self.generate_html()
        assert self._html_path is not None  # narrow for mypy
        url = self._html_path.resolve().as_uri()
        cmd = self._build_kiosk_command(url)
        if cmd is None:
            log.info("MatrixWallpaperBridge: no kiosk-capable browser found")
            return {
                "ok": False,
                "running": False,
                "reason": "no kiosk-capable browser found",
                "html_path": str(self._html_path),
            }
        try:
            self._process = subprocess.Popen(  # noqa: S603
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            log.warning("MatrixWallpaperBridge: kiosk launch failed (%s)", exc)
            return {
                "ok": False,
                "running": False,
                "reason": f"launch failed: {exc}",
                "html_path": str(self._html_path),
            }
        log.info("MatrixWallpaperBridge: kiosk launched pid=%s", self._process.pid)
        result: Dict[str, Any] = {
            "ok": True,
            "running": True,
            "pid": self._process.pid,
            "html_path": str(self._html_path),
            "command": list(cmd),
        }
        if duration_seconds is not None:
            result["duration_seconds"] = float(duration_seconds)
        return result

    def stop_screensaver(self) -> Dict[str, Any]:
        """Terminate the kiosk process if it is still running."""
        if self._process is None:
            return {"ok": True, "running": False, "reason": "no process"}
        if self._process.poll() is not None:
            pid = self._process.pid
            self._process = None
            return {"ok": True, "running": False, "pid": pid, "reason": "already exited"}
        pid = self._process.pid
        try:
            self._process.terminate()
            try:
                self._process.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                self._process.kill()
        except (OSError, subprocess.SubprocessError) as exc:
            log.warning("MatrixWallpaperBridge: terminate failed (%s)", exc)
            return {"ok": False, "running": False, "pid": pid, "reason": str(exc)}
        self._process = None
        return {"ok": True, "running": False, "pid": pid}

    def _build_kiosk_command(self, url: str) -> Optional[list[str]]:
        candidates = self._browser_candidates()
        for exe in candidates:
            resolved = shutil.which(exe) if not os.path.isabs(exe) else (exe if Path(exe).exists() else None)
            if resolved:
                return [resolved, "--kiosk", "--new-window", url]
        return None

    def _browser_candidates(self) -> list[str]:
        if platform.system() == "Windows":
            return [
                r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                "msedge",
                "chrome",
                "chromium",
            ]
        if platform.system() == "Darwin":
            return [
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
                "google-chrome",
                "chromium",
            ]
        return ["google-chrome", "chromium", "chromium-browser", "microsoft-edge"]

    # ------------------------------------------------------------------
    # Wallpaper (Windows-only static fallback)
    # ------------------------------------------------------------------

    def set_as_wallpaper(self) -> Dict[str, Any]:
        """Best-effort: set a static still of the matrix page as desktop wallpaper.

        Windows: writes a black bitmap to ``<assets_dir>/matrix.bmp`` and
        invokes ``SystemParametersInfoW(SPI_SETDESKWALLPAPER, ...)`` so
        the desktop background turns solid black; the live animation is
        then served via a separately launched kiosk window. On other
        platforms this is a no-op that still ensures the HTML is present.
        """
        if self._html_path is None or not self._html_path.exists():
            self.generate_html()
        assert self._html_path is not None

        if not self.platform_supports_wallpaper:
            return {
                "ok": False,
                "applied": False,
                "reason": f"unsupported platform: {platform.system()}",
                "html_path": str(self._html_path),
            }

        bmp = self._assets_dir / "matrix.bmp"
        try:
            _write_solid_black_bmp(bmp)
        except OSError as exc:
            log.warning("MatrixWallpaperBridge: bmp write failed (%s)", exc)
            return {"ok": False, "applied": False, "reason": str(exc)}

        try:
            import ctypes  # noqa: WPS433

            spi_setdeskwallpaper = 20
            spif_updateinifile = 0x01
            spif_sendwininichange = 0x02
            res = ctypes.windll.user32.SystemParametersInfoW(  # type: ignore[attr-defined]
                spi_setdeskwallpaper,
                0,
                str(bmp.resolve()),
                spif_updateinifile | spif_sendwininichange,
            )
            applied = bool(res)
        except (OSError, AttributeError) as exc:
            log.warning("MatrixWallpaperBridge: SystemParametersInfo failed (%s)", exc)
            return {
                "ok": False,
                "applied": False,
                "reason": str(exc),
                "bmp_path": str(bmp),
            }
        return {
            "ok": applied,
            "applied": applied,
            "bmp_path": str(bmp),
            "html_path": str(self._html_path),
        }

    # ------------------------------------------------------------------
    # Generic dispatch
    # ------------------------------------------------------------------

    def invoke(self, action: str, **kwargs: Any) -> Any:
        """Dispatch a string action name to its bound method."""
        registry: Dict[str, Callable[..., Any]] = {
            "generate_html": self.generate_html,
            "set_as_wallpaper": self.set_as_wallpaper,
            "start_screensaver": self.start_screensaver,
            "stop_screensaver": self.stop_screensaver,
            "get_status": self.get_status,
        }
        if action not in registry:
            raise ValueError(f"unknown matrix wallpaper action: {action!r}")
        fn = registry[action]
        result = fn(**kwargs)
        if isinstance(result, Path):
            return {"ok": True, "path": str(result)}
        return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt_float(value: float) -> str:
    return f"{float(value):.4f}"


def _write_solid_black_bmp(path: Path) -> None:
    """Write a 32x32 solid-black 24-bit BMP. Tiny; tile-able by Windows."""
    width, height = 32, 32
    row_bytes = ((width * 3 + 3) // 4) * 4
    pixel_data = bytes(row_bytes * height)
    file_size = 14 + 40 + len(pixel_data)
    header = bytes([
        0x42, 0x4D,
        file_size & 0xFF, (file_size >> 8) & 0xFF,
        (file_size >> 16) & 0xFF, (file_size >> 24) & 0xFF,
        0, 0, 0, 0,
        54, 0, 0, 0,
    ])
    dib = bytes([
        40, 0, 0, 0,
        width & 0xFF, (width >> 8) & 0xFF, 0, 0,
        height & 0xFF, (height >> 8) & 0xFF, 0, 0,
        1, 0,
        24, 0,
        0, 0, 0, 0,
        len(pixel_data) & 0xFF, (len(pixel_data) >> 8) & 0xFF,
        (len(pixel_data) >> 16) & 0xFF, (len(pixel_data) >> 24) & 0xFF,
        0x13, 0x0B, 0, 0,
        0x13, 0x0B, 0, 0,
        0, 0, 0, 0,
        0, 0, 0, 0,
    ])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(header + dib + pixel_data)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def get_matrix_wallpaper_bridge(
    assets_dir: Optional[Path | str] = None,
) -> MatrixWallpaperBridge:
    """Return a fresh :class:`MatrixWallpaperBridge`."""
    return MatrixWallpaperBridge(assets_dir=assets_dir)


__all__ = [
    "MatrixWallpaperBridge",
    "get_matrix_wallpaper_bridge",
    "DEFAULT_COLOR",
    "DEFAULT_SPEED",
    "DEFAULT_DENSITY",
    "DEFAULT_LANGUAGE",
]
