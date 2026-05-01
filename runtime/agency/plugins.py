"""Plugin registry: load, install, remove .py plugins from ~/.agency/plugins/."""

from __future__ import annotations

import importlib.util
import shutil
import sys
from pathlib import Path
from typing import Any


_PLUGINS_DIR = Path.home() / ".agency" / "plugins"


def _plugins_dir() -> Path:
    _PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
    return _PLUGINS_DIR


class PluginRegistry:
    """Manages .py plugin files in ~/.agency/plugins/."""

    def __init__(self, plugins_dir: Path | None = None) -> None:
        self._dir = Path(plugins_dir) if plugins_dir else _plugins_dir()
        self._dir.mkdir(parents=True, exist_ok=True)
        self._loaded: dict[str, Any] = {}  # name -> module

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def install(self, path_or_url: str) -> dict:
        """Copy a local .py plugin file into the plugins directory.

        For simplicity, URLs are downloaded via urllib if they start with
        http(s)://; otherwise the argument is treated as a local path.
        """
        if path_or_url.startswith(("http://", "https://")):
            import urllib.request
            filename = path_or_url.split("/")[-1]
            if not filename.endswith(".py"):
                filename += ".py"
            dest = self._dir / filename
            urllib.request.urlretrieve(path_or_url, dest)  # noqa: S310
        else:
            src = Path(path_or_url)
            if not src.exists():
                raise FileNotFoundError(f"Plugin file not found: {src}")
            dest = self._dir / src.name
            shutil.copy2(src, dest)

        meta = self._load_meta(dest)
        return {"installed": dest.name, "meta": meta}

    def list_plugins(self) -> list[dict]:
        """Return a list of info dicts for every plugin in the plugins dir."""
        results = []
        for path in sorted(self._dir.glob("*.py")):
            try:
                meta = self._load_meta(path)
            except Exception as exc:  # noqa: BLE001
                meta = {"name": path.stem, "version": "?", "description": str(exc)}
            results.append({"file": path.name, "meta": meta})
        return results

    def remove(self, name: str) -> bool:
        """Delete the plugin file matching *name* (with or without .py suffix)."""
        if not name.endswith(".py"):
            name = name + ".py"
        target = self._dir / name
        if not target.exists():
            # Try to find by PLUGIN_META name
            for path in self._dir.glob("*.py"):
                try:
                    meta = self._load_meta(path)
                    if meta.get("name") == name.replace(".py", ""):
                        target = path
                        break
                except Exception:  # noqa: BLE001
                    continue
        if target.exists():
            target.unlink()
            self._loaded.pop(target.stem, None)
            return True
        return False

    def load_all(self) -> list[dict]:
        """Load every plugin and call activate(registry) on each."""
        loaded = []
        for path in sorted(self._dir.glob("*.py")):
            try:
                module = self._import_plugin(path)
                activate = getattr(module, "activate", None)
                if callable(activate):
                    activate(self)
                meta = getattr(module, "PLUGIN_META", {"name": path.stem})
                self._loaded[path.stem] = module
                loaded.append({"file": path.name, "meta": meta, "status": "ok"})
            except Exception as exc:  # noqa: BLE001
                loaded.append({"file": path.name, "status": f"error: {exc}"})
        return loaded

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_meta(self, path: Path) -> dict:
        module = self._import_plugin(path)
        meta = getattr(module, "PLUGIN_META", None)
        if not isinstance(meta, dict):
            return {"name": path.stem, "version": "0.0.0", "description": ""}
        return meta

    @staticmethod
    def _import_plugin(path: Path) -> Any:
        spec = importlib.util.spec_from_file_location(f"_agency_plugin_{path.stem}", path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load plugin from {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # type: ignore[union-attr]
        return module
