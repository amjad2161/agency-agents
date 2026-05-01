"""Tests for agency.plugins.PluginRegistry."""

from __future__ import annotations

from pathlib import Path

import pytest

from agency.plugins import PluginRegistry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_plugin(directory: Path, filename: str, name: str, activate_side_effect: str = "") -> Path:
    """Write a minimal valid plugin file."""
    path = directory / filename
    path.write_text(
        f'PLUGIN_META = {{"name": "{name}", "version": "1.0.0", "description": "Test plugin"}}\n'
        f'def activate(registry):\n'
        f'    {activate_side_effect or "pass"}\n',
        encoding="utf-8",
    )
    return path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPluginRegistry:
    def test_list_empty_when_no_plugins(self, tmp_path: Path):
        reg = PluginRegistry(plugins_dir=tmp_path)
        assert reg.list_plugins() == []

    def test_install_local_file(self, tmp_path: Path):
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        plugin_file = _make_plugin(src_dir, "myplugin.py", "myplugin")

        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()
        reg = PluginRegistry(plugins_dir=plugins_dir)
        result = reg.install(str(plugin_file))

        assert result["installed"] == "myplugin.py"
        assert (plugins_dir / "myplugin.py").exists()

    def test_install_returns_meta(self, tmp_path: Path):
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        plugin_file = _make_plugin(src_dir, "alpha.py", "alpha")

        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()
        reg = PluginRegistry(plugins_dir=plugins_dir)
        result = reg.install(str(plugin_file))

        assert result["meta"]["name"] == "alpha"
        assert result["meta"]["version"] == "1.0.0"

    def test_install_missing_file_raises(self, tmp_path: Path):
        reg = PluginRegistry(plugins_dir=tmp_path)
        with pytest.raises(FileNotFoundError):
            reg.install(str(tmp_path / "nonexistent.py"))

    def test_list_plugins_shows_installed(self, tmp_path: Path):
        _make_plugin(tmp_path, "foo.py", "foo")
        _make_plugin(tmp_path, "bar.py", "bar")
        reg = PluginRegistry(plugins_dir=tmp_path)
        plugins = reg.list_plugins()
        names = {p["file"] for p in plugins}
        assert names == {"foo.py", "bar.py"}

    def test_list_plugins_returns_meta(self, tmp_path: Path):
        _make_plugin(tmp_path, "myplugin.py", "myplugin")
        reg = PluginRegistry(plugins_dir=tmp_path)
        plugins = reg.list_plugins()
        assert plugins[0]["meta"]["name"] == "myplugin"
        assert plugins[0]["meta"]["version"] == "1.0.0"

    def test_remove_existing_plugin(self, tmp_path: Path):
        _make_plugin(tmp_path, "todelete.py", "todelete")
        reg = PluginRegistry(plugins_dir=tmp_path)
        removed = reg.remove("todelete")
        assert removed is True
        assert not (tmp_path / "todelete.py").exists()

    def test_remove_with_py_extension(self, tmp_path: Path):
        _make_plugin(tmp_path, "todelete.py", "todelete")
        reg = PluginRegistry(plugins_dir=tmp_path)
        removed = reg.remove("todelete.py")
        assert removed is True

    def test_remove_nonexistent_returns_false(self, tmp_path: Path):
        reg = PluginRegistry(plugins_dir=tmp_path)
        assert reg.remove("ghost") is False

    def test_load_all_calls_activate(self, tmp_path: Path):
        sentinel = tmp_path / "activated.flag"
        plugin_code = (
            'PLUGIN_META = {"name": "active", "version": "1.0", "description": ""}\n'
            f'def activate(registry):\n'
            f'    open("{sentinel}", "w").close()\n'
        )
        (tmp_path / "active.py").write_text(plugin_code, encoding="utf-8")

        reg = PluginRegistry(plugins_dir=tmp_path)
        results = reg.load_all()
        assert any(r["status"] == "ok" for r in results)
        assert sentinel.exists()

    def test_load_all_reports_errors_gracefully(self, tmp_path: Path):
        (tmp_path / "broken.py").write_text("raise RuntimeError('oops')\n", encoding="utf-8")
        reg = PluginRegistry(plugins_dir=tmp_path)
        results = reg.load_all()
        assert len(results) == 1
        assert "error" in results[0]["status"]

    def test_list_plugins_handles_broken_file_gracefully(self, tmp_path: Path):
        (tmp_path / "bad.py").write_text("raise SyntaxError('broken')", encoding="utf-8")
        reg = PluginRegistry(plugins_dir=tmp_path)
        # Should not raise; broken plugin returns partial info
        plugins = reg.list_plugins()
        assert len(plugins) == 1
        assert "bad.py" == plugins[0]["file"]

    def test_install_from_src_to_plugins_dir(self, tmp_path: Path):
        src = tmp_path / "source"
        src.mkdir()
        dst = tmp_path / "dest"
        dst.mkdir()
        plugin_file = _make_plugin(src, "migrated.py", "migrated")
        reg = PluginRegistry(plugins_dir=dst)
        reg.install(str(plugin_file))
        assert (dst / "migrated.py").exists()
        assert not (src / "migrated.py").samefile(dst / "migrated.py")  # was copied
