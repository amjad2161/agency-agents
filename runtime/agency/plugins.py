"""Plugin system for the Agency runtime.

Plugins extend the runtime with new CLI commands or skills.
Each plugin is described in ~/.agency/plugins.json and ships either
a Python dotted-path entry-point or a skill YAML file.
"""

from __future__ import annotations

import importlib
import json
import shutil
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def plugins_dir() -> Path:
    d = Path.home() / ".agency" / "plugins"
    d.mkdir(parents=True, exist_ok=True)
    return d


def plugins_manifest_path() -> Path:
    return Path.home() / ".agency" / "plugins.json"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Plugin:
    """Metadata for a single installed plugin."""
    name: str
    version: str = "0.1.0"
    description: str = ""
    entry_point: str = ""           # Python dotted path, e.g. "mypkg.plugin:register"
    skill_files: list[str] = field(default_factory=list)  # relative to plugins_dir()
    enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Plugin":
        return cls(
            name=d.get("name", ""),
            version=d.get("version", "0.1.0"),
            description=d.get("description", ""),
            entry_point=d.get("entry_point", ""),
            skill_files=d.get("skill_files", []),
            enabled=d.get("enabled", True),
        )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class PluginRegistry:
    """Loads, stores, and activates installed plugins."""

    def __init__(self, manifest: Path | None = None) -> None:
        self._manifest = manifest or plugins_manifest_path()
        self._plugins: dict[str, Plugin] = {}
        self._loaded = False

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def load(self) -> "PluginRegistry":
        """Read manifest from disk; idempotent."""
        if not self._manifest.exists():
            self._plugins = {}
            self._loaded = True
            return self
        try:
            raw = json.loads(self._manifest.read_text(encoding="utf-8"))
            if not isinstance(raw, list):
                raw = []
            self._plugins = {
                p.name: p
                for item in raw
                if isinstance(item, dict)
                if (p := Plugin.from_dict(item)).name
            }
        except (json.JSONDecodeError, OSError):
            self._plugins = {}
        self._loaded = True
        return self

    def _save(self) -> None:
        self._manifest.parent.mkdir(parents=True, exist_ok=True)
        data = [p.to_dict() for p in self._plugins.values()]
        self._manifest.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.load()

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def install(
        self,
        name: str,
        source: Path | None = None,
        *,
        version: str = "0.1.0",
        description: str = "",
        entry_point: str = "",
    ) -> Plugin:
        """Install or update a plugin.

        If *source* is a file (YAML skill or .py module) it is copied into
        plugins_dir() and registered.  If *source* is None the plugin entry
        is created with just metadata (useful for entry-point-only plugins).
        """
        self._ensure_loaded()
        skill_files: list[str] = []

        if source is not None:
            source = Path(source)
            if not source.exists():
                raise FileNotFoundError(f"plugin source not found: {source}")
            dest = plugins_dir() / source.name
            shutil.copy2(source, dest)
            skill_files = [source.name]

        plugin = Plugin(
            name=name,
            version=version,
            description=description,
            entry_point=entry_point,
            skill_files=skill_files,
            enabled=True,
        )
        self._plugins[name] = plugin
        self._save()
        return plugin

    def remove(self, name: str) -> bool:
        """Uninstall a plugin by name.  Returns True if it existed."""
        self._ensure_loaded()
        plugin = self._plugins.pop(name, None)
        if plugin is None:
            return False
        # Remove any copied skill files
        for fname in plugin.skill_files:
            target = plugins_dir() / fname
            if target.exists():
                target.unlink()
        self._save()
        return True

    def get(self, name: str) -> Plugin | None:
        self._ensure_loaded()
        return self._plugins.get(name)

    def list_plugins(self) -> list[Plugin]:
        self._ensure_loaded()
        return list(self._plugins.values())

    def __len__(self) -> int:
        self._ensure_loaded()
        return len(self._plugins)

    # ------------------------------------------------------------------
    # Activation
    # ------------------------------------------------------------------

    def activate(self) -> list[str]:
        """Call each enabled plugin's entry_point (if set).

        The entry_point must be a dotted-path to a callable:
          "mypkg.plugin:register"
        The callable receives this registry as its sole argument so it can
        add CLI commands or dynamically register skills.

        Returns list of names of plugins that were activated.
        """
        self._ensure_loaded()
        activated: list[str] = []
        for plugin in self._plugins.values():
            if not plugin.enabled or not plugin.entry_point:
                continue
            try:
                module_path, _, attr = plugin.entry_point.partition(":")
                mod = importlib.import_module(module_path)
                fn = getattr(mod, attr) if attr else None
                if callable(fn):
                    fn(self)
                activated.append(plugin.name)
            except Exception:  # noqa: BLE001
                pass  # activation failures are non-fatal
        return activated


# ---------------------------------------------------------------------------
# CLI helpers (called from cli.py)
# ---------------------------------------------------------------------------

def plugin_install_cmd(name: str, source: str | None, version: str, description: str) -> None:
    """Thin wrapper for use from the Click plugin install command."""
    registry = PluginRegistry().load()
    src = Path(source) if source else None
    plugin = registry.install(
        name=name, source=src, version=version, description=description
    )
    print(f"✓ Installed plugin \"{plugin.name}\" v{plugin.version}")
    if plugin.skill_files:
        for f in plugin.skill_files:
            print(f"  skill file: {plugins_dir() / f}")


def plugin_list_cmd() -> None:
    """Print installed plugins."""
    registry = PluginRegistry().load()
    plugins = registry.list_plugins()
    if not plugins:
        print("No plugins installed.")
        return
    print(f"{'NAME':<20} {'VERSION':<10} {'ENABLED':<8} DESCRIPTION")
    print("-" * 70)
    for p in plugins:
        enabled = "yes" if p.enabled else "no"
        print(f"{p.name:<20} {p.version:<10} {enabled:<8} {p.description}")


def plugin_remove_cmd(name: str) -> None:
    """Remove a plugin by name."""
    registry = PluginRegistry().load()
    if registry.remove(name):
        print(f"✓ Removed plugin \"{name}\"")
    else:
        print(f"Plugin \"{name}\" not found.")
        raise SystemExit(1)
