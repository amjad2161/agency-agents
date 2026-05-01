"""Plugin registry: load, install, remove .py plugins from ~/.agency/plugins/."""

from __future__ import annotations

import ast
import importlib.util
import shutil
from pathlib import Path
from typing import Any


_PLUGINS_DIR = Path.home() / ".agency" / "plugins"


def _plugins_dir() -> Path:
    _PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
    return _PLUGINS_DIR


def _read_meta_ast(path: Path) -> dict:
    """Extract PLUGIN_META from a .py file using AST — no code execution."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return {"name": path.stem, "version": "?", "description": "syntax error"}
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "PLUGIN_META"
            and isinstance(node.value, ast.Dict)
        ):
            try:
                return ast.literal_eval(node.value)  # type: ignore[return-value]
            except ValueError:
                break
    return {"name": path.stem, "version": "0.0.0", "description": ""}


class PluginRegistry:
    """Manages .py plugin files in ~/.agency/plugins/.

    Metadata is read via AST (no code execution) in list_plugins() and
    install(). Actual plugin code runs only when load_all() is called.
    """

    def __init__(self, plugins_dir: Path | None = None) -> None:
        self._dir = Path(plugins_dir) if plugins_dir else _plugins_dir()
        self._dir.mkdir(parents=True, exist_ok=True)
        self._loaded: dict[str, Any] = {}  # name -> module

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def install(self, path_or_url: str) -> dict:
        """Copy a local .py plugin file into the plugins directory.

        Remote URLs must use HTTPS. Metadata is read via AST after copy
        (no code execution at install time).
        """
        if path_or_url.startswith("http://"):
            raise ValueError("Only HTTPS URLs are accepted for plugin install")
        if path_or_url.startswith("https://"):
            import urllib.request
            filename = path_or_url.split("/")[-1] or "plugin.py"
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

        meta = _read_meta_ast(dest)
        return {"installed": dest.name, "meta": meta}

    def list_plugins(self) -> list[dict]:
        """Return info dicts for every plugin. Reads metadata via AST only."""
        results = []
        for path in sorted(self._dir.glob("*.py")):
            meta = _read_meta_ast(path)
            results.append({"file": path.name, "meta": meta})
        return results

    def remove(self, name: str) -> bool:
        """Delete the plugin file matching *name* (with or without .py suffix)."""
        if not name.endswith(".py"):
            name = name + ".py"
        target = self._dir / name
        if not target.exists():
            for path in self._dir.glob("*.py"):
                meta = _read_meta_ast(path)
                if meta.get("name") == name.replace(".py", ""):
                    target = path
                    break
        if target.exists():
            target.unlink()
            self._loaded.pop(target.stem, None)
            return True
        return False

    def load_all(self) -> list[dict]:
        """Import every plugin and call activate(registry) on each.

        This is the only method that executes plugin code.
        """
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
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _import_plugin(path: Path) -> Any:
        spec = importlib.util.spec_from_file_location(f"_agency_plugin_{path.stem}", path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load plugin from {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # type: ignore[union-attr]
        return module
