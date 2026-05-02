"""Tests for the Matrix wallpaper bridge — all run without launching a browser."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from agency.bridges.matrix_wallpaper import (
    MatrixWallpaperBridge,
    get_matrix_wallpaper_bridge,
)


@pytest.fixture()
def bridge(tmp_path: Path) -> MatrixWallpaperBridge:
    return get_matrix_wallpaper_bridge(assets_dir=tmp_path / "wallpaper")


def test_factory_returns_unstarted_bridge(tmp_path: Path) -> None:
    b = get_matrix_wallpaper_bridge(assets_dir=tmp_path)
    assert isinstance(b, MatrixWallpaperBridge)
    assert b.is_running is False
    assert b.html_path is None
    status = b.get_status()
    assert status["running"] is False
    assert status["pid"] is None


def test_generate_html_writes_file_with_defaults(bridge: MatrixWallpaperBridge) -> None:
    out = bridge.generate_html()
    assert out.exists()
    assert out.name == "matrix.html"
    text = out.read_text(encoding="utf-8")
    assert "<canvas" in text
    assert "#00ff41" in text
    assert "JARVIS" in text
    assert bridge.html_path == out


def test_generate_html_respects_color_speed_density(bridge: MatrixWallpaperBridge) -> None:
    out = bridge.generate_html(color="#ff00aa", speed=2.5, density=0.4, language="hebrew")
    text = out.read_text(encoding="utf-8")
    assert "#ff00aa" in text
    assert "2.5000" in text
    assert "0.4000" in text
    assert "hebrew" in text


def test_generate_html_rejects_bad_color(bridge: MatrixWallpaperBridge) -> None:
    with pytest.raises(ValueError):
        bridge.generate_html(color="not-a-color")


def test_generate_html_rejects_bad_speed(bridge: MatrixWallpaperBridge) -> None:
    with pytest.raises(ValueError):
        bridge.generate_html(speed=999.0)


def test_generate_html_rejects_bad_density(bridge: MatrixWallpaperBridge) -> None:
    with pytest.raises(ValueError):
        bridge.generate_html(density=2.0)


def test_generate_html_rejects_bad_language(bridge: MatrixWallpaperBridge) -> None:
    with pytest.raises(ValueError):
        bridge.generate_html(language="klingon")


def test_set_as_wallpaper_writes_bmp_or_reports_unsupported(
    bridge: MatrixWallpaperBridge,
) -> None:
    result = bridge.set_as_wallpaper()
    assert isinstance(result, dict)
    if bridge.platform_supports_wallpaper:
        assert "bmp_path" in result
        assert Path(result["bmp_path"]).exists()
    else:
        assert result["applied"] is False
        assert "unsupported platform" in result["reason"]


def test_start_screensaver_with_no_browser(
    bridge: MatrixWallpaperBridge, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(bridge, "_browser_candidates", lambda: ["__definitely_no_browser__"])
    result = bridge.start_screensaver()
    assert result["ok"] is False
    assert result["running"] is False
    assert "no kiosk-capable browser" in result["reason"]


def test_start_and_stop_screensaver_with_fake_process(
    bridge: MatrixWallpaperBridge, monkeypatch: pytest.MonkeyPatch
) -> None:
    bridge.generate_html()

    class _FakeProc:
        def __init__(self) -> None:
            self.pid = 4242
            self._alive = True

        def poll(self) -> Any:
            return None if self._alive else 0

        def terminate(self) -> None:
            self._alive = False

        def wait(self, timeout: float = 0) -> int:
            self._alive = False
            return 0

        def kill(self) -> None:
            self._alive = False

    fake = _FakeProc()

    def fake_popen(cmd: Any, **kwargs: Any) -> Any:
        return fake

    monkeypatch.setattr(
        bridge, "_build_kiosk_command", lambda url: ["__fake_browser__", url]
    )
    monkeypatch.setattr("subprocess.Popen", fake_popen)

    started = bridge.start_screensaver(duration_seconds=1.0)
    assert started["ok"] is True
    assert started["running"] is True
    assert started["pid"] == 4242
    assert started["duration_seconds"] == 1.0
    assert bridge.is_running is True

    stopped = bridge.stop_screensaver()
    assert stopped["ok"] is True
    assert stopped["pid"] == 4242
    assert bridge.is_running is False


def test_stop_screensaver_when_no_process(bridge: MatrixWallpaperBridge) -> None:
    out = bridge.stop_screensaver()
    assert out["ok"] is True
    assert out["running"] is False


def test_invoke_dispatches_actions(bridge: MatrixWallpaperBridge) -> None:
    out = bridge.invoke("generate_html", color="#00ff41")
    assert out["ok"] is True
    assert "matrix.html" in out["path"]

    status = bridge.invoke("get_status")
    assert status["running"] is False


def test_invoke_rejects_unknown_action(bridge: MatrixWallpaperBridge) -> None:
    with pytest.raises(ValueError):
        bridge.invoke("does_not_exist")
