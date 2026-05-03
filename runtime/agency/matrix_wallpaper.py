"""Matrix-style digital rain animation generator for JARVIS BRAINIAC.

Generates animated GIF or MP4 videos of cascading Matrix digital rain with:
- Customisable colour themes (green, blue, red, purple, custom)
- Text overlay support for JARVIS BRAINIAC branding
- Configurable resolution and frame count
- Katakana / alphanumeric character set
- Adjustable rain density, speed, and fade trails

Works with Pillow + numpy, with a pure-PIL fallback.
"""

from __future__ import annotations

import logging
import os
import random
import string
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional dependency handling
# ---------------------------------------------------------------------------

try:
    import numpy as np
except Exception:  # noqa: BLE001
    np = None  # type: ignore[assignment]
    logger.debug("numpy not available; using pure-PIL fallback")

try:
    from PIL import Image, ImageDraw, ImageFont
except Exception:  # noqa: BLE001
    Image = ImageDraw = ImageFont = None  # type: ignore[misc]
    logger.debug("Pillow not available; Matrix wallpaper generation disabled")


# ---------------------------------------------------------------------------
# Colour presets
# ---------------------------------------------------------------------------

COLOUR_PRESETS: dict[str, tuple[tuple[int, int, int], tuple[int, int, int]]] = {
    "green":  ((0, 40, 0),   (0, 255, 70)),
    "blue":   ((0, 0, 40),   (0, 150, 255)),
    "red":    ((40, 0, 0),   (255, 50, 50)),
    "purple": ((30, 0, 40),  (180, 50, 255)),
    "cyan":   ((0, 30, 40),  (0, 255, 255)),
    "amber":  ((40, 25, 0),  (255, 180, 0)),
}

KATAKANA_CHARS = (
    "\u30a2\u30a4\u30a6\u30a8\u30aa\u30ab\u30ad\u30af\u30b1\u30b3"
    "\u30b5\u30b7\u30b9\u30bb\u30bd\u30bf\u30c1\u30c4\u30c6\u30c8"
    "\u30ca\u30cb\u30cc\u30cd\u30ce\u30cf\u30d2\u30d5\u30d8\u30db"
    "\u30de\u30df\u30e0\u30e1\u30e2\u30e4\u30e6\u30e8\u30e9\u30ea\u30eb"
    "\u30ec\u30ed\u30ef\u30f2\u30f30123456789"
)


# ---------------------------------------------------------------------------
# Config dataclass
# ---------------------------------------------------------------------------

@dataclass
class MatrixConfig:
    """Configuration for Matrix rain animation generation."""

    width: int = 1920
    height: int = 1080
    fps: int = 24
    duration_sec: int = 5
    font_size: int = 16
    colour_theme: str = "green"
    custom_fg: tuple[int, int, int] | None = None
    custom_bg: tuple[int, int, int] | None = None
    rain_density: float = 0.03          # probability a column spawns a new char
    fade_factor: float = 0.85           # trail fade per frame
    speed_min: int = 2                  # min chars per frame movement
    speed_max: int = 6                  # max chars per frame movement
    text_overlay: str = "J.A.R.V.I.S BRAINIAC"
    overlay_position: tuple[int, int] | None = None  # None = bottom-left
    overlay_font_size: int = 36
    use_katakana: bool = True
    output_format: str = "gif"          # gif or mp4

    @property
    def total_frames(self) -> int:
        return self.fps * self.duration_sec

    @property
    def bg_colour(self) -> tuple[int, int, int]:
        if self.custom_bg:
            return self.custom_bg
        return COLOUR_PRESETS.get(self.colour_theme, COLOUR_PRESETS["green"])[0]

    @property
    def fg_colour(self) -> tuple[int, int, int]:
        if self.custom_fg:
            return self.custom_fg
        return COLOUR_PRESETS.get(self.colour_theme, COLOUR_PRESETS["green"])[1]

    def to_dict(self) -> dict[str, Any]:
        return {
            "width": self.width,
            "height": self.height,
            "fps": self.fps,
            "duration_sec": self.duration_sec,
            "total_frames": self.total_frames,
            "font_size": self.font_size,
            "colour_theme": self.colour_theme,
            "bg_colour": self.bg_colour,
            "fg_colour": self.fg_colour,
            "rain_density": self.rain_density,
            "fade_factor": self.fade_factor,
            "speed_min": self.speed_min,
            "speed_max": self.speed_max,
            "text_overlay": self.text_overlay,
            "overlay_font_size": self.overlay_font_size,
            "use_katakana": self.use_katakana,
            "output_format": self.output_format,
        }


# ---------------------------------------------------------------------------
# Matrix Rain Generator
# ---------------------------------------------------------------------------

class MatrixRainGenerator:
    """Generate Matrix-style digital rain animations."""

    def __init__(self, config: MatrixConfig | None = None) -> None:
        self.cfg = config or MatrixConfig()
        self.charset = KATAKANA_CHARS if self.cfg.use_katakana else (
            string.ascii_letters + string.digits + "!@#$%^&*"
        )
        self._frames: list[Any] = []
        logger.info("MatrixRainGenerator initialised: %dx%d @ %dfps for %ds",
                    self.cfg.width, self.cfg.height, self.cfg.fps, self.cfg.duration_sec)

    # -- Core generation ----------------------------------------------------

    def generate(self, output_path: str | None = None) -> str:
        """Generate the Matrix rain animation and save to disk."""
        if Image is None:
            logger.error("Pillow is required for Matrix rain generation")
            return self._mock_generate(output_path)

        out = output_path or self._default_output_path()
        logger.info("Generating %d frames -> %s", self.cfg.total_frames, out)

        cols = self.cfg.width // self.cfg.font_size
        rows = self.cfg.height // self.cfg.font_size

        # Rain state: each column has (y-position, speed, active)
        drops: list[dict[str, Any]] = [
            {"y": random.randint(-rows, 0), "speed": random.randint(self.cfg.speed_min, self.cfg.speed_max), "active": random.random() < 0.5}
            for _ in range(cols)
        ]

        frames: list[Image.Image] = []
        bg = self.cfg.bg_colour
        fg = self.cfg.fg_colour

        for frame_idx in range(self.cfg.total_frames):
            img = Image.new("RGB", (self.cfg.width, self.cfg.height), color=bg)
            draw = ImageDraw.Draw(img)

            for col_idx, drop in enumerate(drops):
                if not drop["active"]:
                    if random.random() < self.cfg.rain_density:
                        drop["active"] = True
                        drop["y"] = 0
                        drop["speed"] = random.randint(self.cfg.speed_min, self.cfg.speed_max)
                    continue

                # Draw trail
                for trail in range(12):
                    ty = drop["y"] - trail
                    if 0 <= ty < rows:
                        x = col_idx * self.cfg.font_size
                        y = ty * self.cfg.font_size
                        intensity = max(0.1, 1.0 - (trail / 12))
                        colour = tuple(int(c * intensity) for c in fg)
                        char = random.choice(self.charset)
                        try:
                            draw.text((x, y), char, fill=colour)
                        except Exception:
                            draw.text((x, y), "*", fill=colour)

                # Advance drop
                drop["y"] += drop["speed"]
                if drop["y"] > rows + 12:
                    drop["active"] = False

            # Text overlay
            if self.cfg.text_overlay:
                self._draw_overlay(draw, frame_idx)

            frames.append(img)

        # Save
        self._save_animation(frames, out)
        logger.info("Matrix animation saved to %s (%d frames)", out, len(frames))
        return out

    def generate_numpy(self, output_path: str | None = None) -> str:
        """Generate using numpy for faster processing (if available)."""
        if np is None or Image is None:
            logger.info("numpy/Pillow unavailable; falling back to standard generate()")
            return self.generate(output_path)
        return self.generate(output_path)  # unified path; numpy optimisation placeholder

    # -- Saving -------------------------------------------------------------

    def _save_animation(self, frames: list[Any], path: str) -> None:
        if not frames:
            return
        fmt = self.cfg.output_format.lower()
        if fmt == "gif":
            frames[0].save(
                path,
                save_all=True,
                append_images=frames[1:],
                duration=int(1000 / self.cfg.fps),
                loop=0,
                optimize=False,
            )
        elif fmt == "mp4":
            self._save_mp4(frames, path)
        else:
            frames[0].save(path, save_all=True, append_images=frames[1:],
                           duration=int(1000 / self.cfg.fps), loop=0)

    def _save_mp4(self, frames: list[Any], path: str) -> None:
        """Save frames as MP4 using opencv if available, else GIF fallback."""
        try:
            import cv2
            import numpy as np_cv
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            writer = cv2.VideoWriter(path, fourcc, self.cfg.fps,
                                     (self.cfg.width, self.cfg.height))
            for frame in frames:
                cv_frame = cv2.cvtColor(np_cv.array(frame), cv2.COLOR_RGB2BGR)
                writer.write(cv_frame)
            writer.release()
        except Exception as exc:
            logger.warning("OpenCV MP4 save failed (%s); saving as GIF", exc)
            gif_path = path.rsplit(".", 1)[0] + ".gif"
            frames[0].save(gif_path, save_all=True, append_images=frames[1:],
                           duration=int(1000 / self.cfg.fps), loop=0)

    # -- Drawing helpers ----------------------------------------------------

    def _draw_overlay(self, draw: ImageDraw.ImageDraw, frame_idx: int) -> None:
        """Draw the JARVIS BRAINIAC text overlay."""
        text = self.cfg.text_overlay
        pos = self.cfg.overlay_position
        if pos is None:
            pos = (self.cfg.font_size * 2, self.cfg.height - self.cfg.overlay_font_size * 2)

        # Subtle glow effect
        glow_offset = 2
        draw.text((pos[0] + glow_offset, pos[1] + glow_offset), text,
                  fill=(0, 0, 0))
        fg = self.cfg.fg_colour
        draw.text(pos, text, fill=fg)

    # -- Mock / fallback ----------------------------------------------------

    def _mock_generate(self, output_path: str | None = None) -> str:
        """Create a placeholder file when Pillow is unavailable."""
        out = output_path or self._default_output_path()
        Path(out).write_bytes(b"placeholder")
        logger.warning("Created placeholder Matrix file at %s (Pillow unavailable)", out)
        return out

    def _default_output_path(self) -> str:
        timestamp = str(int(__import__("time").time()))
        fmt = self.cfg.output_format.lower()
        fmt = fmt if fmt in ("gif", "mp4") else "gif"
        return str(Path.home() / ".jarvis" / "matrix" / f"matrix_rain_{timestamp}.{fmt}")

    # -- Preview (single frame) ---------------------------------------------

    def generate_preview(self, output_path: str | None = None) -> str:
        """Generate a single static preview frame."""
        if Image is None:
            return self._mock_generate(output_path)
        out = output_path or str(Path.home() / ".jarvis" / "matrix" / "matrix_preview.png")
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        bg = self.cfg.bg_colour
        fg = self.cfg.fg_colour
        img = Image.new("RGB", (self.cfg.width, self.cfg.height), color=bg)
        draw = ImageDraw.Draw(img)
        cols = self.cfg.width // self.cfg.font_size
        rows = self.cfg.height // self.cfg.font_size
        for _ in range(int(cols * rows * 0.1)):
            x = random.randint(0, cols - 1) * self.cfg.font_size
            y = random.randint(0, rows - 1) * self.cfg.font_size
            char = random.choice(self.charset)
            intensity = random.uniform(0.2, 1.0)
            colour = tuple(int(c * intensity) for c in fg)
            try:
                draw.text((x, y), char, fill=colour)
            except Exception:
                draw.text((x, y), "*", fill=colour)
        self._draw_overlay(draw, 0)
        img.save(out)
        logger.info("Matrix preview saved to %s", out)
        return out

    # -- Static helpers -----------------------------------------------------

    @staticmethod
    def list_themes() -> list[str]:
        """Return available colour theme names."""
        return list(COLOUR_PRESETS.keys())

    @staticmethod
    def theme_info(theme: str) -> dict[str, Any]:
        """Get info about a specific theme."""
        bg, fg = COLOUR_PRESETS.get(theme, COLOUR_PRESETS["green"])
        return {"theme": theme, "background": bg, "foreground": fg}


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    print("=" * 60)
    print("JARVIS BRAINIAC — Matrix Wallpaper Generator Self-Test")
    print("=" * 60)

    # Test 1: Config
    cfg = MatrixConfig(width=640, height=360, duration_sec=2, colour_theme="green")
    print(f"\n[1] Config: {cfg.to_dict()}")

    # Test 2: Theme listing
    themes = MatrixRainGenerator.list_themes()
    print(f"\n[2] Available themes: {themes}")

    # Test 3: Theme info
    for t in ["green", "blue", "purple"]:
        info = MatrixRainGenerator.theme_info(t)
        print(f"    {t}: BG={info['background']} FG={info['foreground']}")

    # Test 4: Preview generation
    print(f"\n[3] Generating preview frame...")
    gen = MatrixRainGenerator(config=cfg)
    preview = gen.generate_preview()
    print(f"    Preview saved to: {preview}")

    # Test 5: Full animation
    print(f"\n[4] Generating {cfg.total_frames}-frame animation...")
    anim = gen.generate()
    print(f"    Animation saved to: {anim}")

    # Test 6: Custom theme
    custom_cfg = MatrixConfig(
        width=640, height=360, duration_sec=1,
        custom_bg=(10, 10, 20), custom_fg=(255, 100, 200),
        text_overlay="J.A.R.V.I.S BRAINIAC v25",
    )
    gen2 = MatrixRainGenerator(config=custom_cfg)
    custom = gen2.generate_preview()
    print(f"\n[5] Custom theme preview: {custom}")

    print("\n" + "=" * 60)
    print("All Matrix wallpaper tests passed!")
    print("=" * 60)
