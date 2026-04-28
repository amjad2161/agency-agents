"""Agency runtime config file support.

Loads ~/.agency/config.toml (preferred) or ~/.agency/config.json.
Resolution order (highest to lowest priority):
  1. CLI flags (caller applies after loading this config)
  2. Config file   (~/.agency/config.toml or config.json)
  3. Env vars      (AGENCY_MODEL, AGENCY_TRUST_MODE, …)
  4. Hard defaults
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Config directory helpers
# ---------------------------------------------------------------------------

def agency_dir() -> Path:
    """Return ~/.agency, creating it if absent."""
    d = Path.home() / ".agency"
    d.mkdir(parents=True, exist_ok=True)
    return d


def config_path_toml() -> Path:
    return agency_dir() / "config.toml"


def config_path_json() -> Path:
    return agency_dir() / "config.json"


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------

@dataclass
class AgencyConfig:
    """Persistent configuration for the agency runtime.

    Fields mirror the most-common env vars so users can set them once
    in a config file instead of exporting them on every shell.
    """

    model: str | None = None
    trust_mode: str | None = None          # off | on-my-machine | yolo
    max_tokens: int | None = None
    temperature: float | None = None       # 0.0 – 1.0
    backend_url: str | None = None         # override Anthropic API base URL

    # Extra keys that don't map to a known field are stored here so we
    # can round-trip them without data loss and warn the user.
    _unknown: dict[str, Any] = field(default_factory=dict, repr=False)

    # ------------------------------------------------------------------
    # Factory methods
    # ------------------------------------------------------------------

    @classmethod
    def load(cls, path: Path | None = None) -> "AgencyConfig":
        """Load config from *path*, or auto-detect toml then json.

        Returns a default (empty) config if no file exists.
        """
        if path is not None:
            return cls._from_file(path)

        toml_p = config_path_toml()
        if toml_p.exists():
            return cls._from_file(toml_p)

        json_p = config_path_json()
        if json_p.exists():
            return cls._from_file(json_p)

        return cls()

    @classmethod
    def _from_file(cls, path: Path) -> "AgencyConfig":
        suffix = path.suffix.lower()
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError:
            return cls()

        if suffix == ".toml":
            data = cls._parse_toml(raw)
        elif suffix == ".json":
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                return cls()
        else:
            # Try toml first, then json
            data = cls._parse_toml(raw)
            if data is None:
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    return cls()

        if not isinstance(data, dict):
            return cls()

        return cls._from_dict(data)

    @staticmethod
    def _parse_toml(raw: str) -> dict[str, Any] | None:
        """Parse TOML using stdlib tomllib (3.11+) or fallback."""
        # Python 3.11+ stdlib
        try:
            import tomllib  # type: ignore[import]
            return tomllib.loads(raw)
        except ImportError:
            pass
        # Python 3.10- fallback: try tomli third-party
        try:
            import tomli  # type: ignore[import]
            return tomli.loads(raw)
        except ImportError:
            pass
        # Final fallback: very minimal TOML parser for simple key=value
        # (no sections, no arrays — good enough for our flat config)
        result: dict[str, Any] = {}
        for line in raw.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("["):
                continue
            if "=" in line:
                k, _, v = line.partition("=")
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                result[k] = v
        return result or None

    @classmethod
    def _from_dict(cls, data: dict[str, Any]) -> "AgencyConfig":
        known = {"model", "trust_mode", "max_tokens", "temperature", "backend_url"}
        cfg = cls()
        unknown: dict[str, Any] = {}
        for k, v in data.items():
            if k in known:
                try:
                    if k == "max_tokens":
                        object.__setattr__(cfg, k, int(v))
                    elif k == "temperature":
                        object.__setattr__(cfg, k, float(v))
                    else:
                        object.__setattr__(cfg, k, str(v) if v is not None else None)
                except (ValueError, TypeError):
                    pass  # silently ignore bad types
            else:
                unknown[k] = v
        cfg._unknown = unknown
        return cfg

    # ------------------------------------------------------------------
    # Apply to LLMConfig / env
    # ------------------------------------------------------------------

    def apply_to_llm_config(self, llm_cfg: Any) -> None:
        """Overlay this config onto an LLMConfig *only* if fields are not
        already set from env vars (i.e. still at their default values).

        Callers should call this *before* applying CLI flags so the
        precedence chain is: CLI > config-file > env > default.
        """
        from .llm import DEFAULT_MODEL, DEFAULT_MAX_TOKENS

        # model: config file wins over default, but env AGENCY_MODEL already
        # applied in LLMConfig.from_env() — skip if it differs from default.
        if self.model is not None and llm_cfg.model == DEFAULT_MODEL:
            # Only override if env didn't already change it
            if not os.environ.get("AGENCY_MODEL"):
                llm_cfg.model = self.model

        if self.max_tokens is not None and llm_cfg.max_tokens == DEFAULT_MAX_TOKENS:
            if not os.environ.get("AGENCY_MAX_TOKENS"):
                llm_cfg.max_tokens = self.max_tokens

        # temperature is not on LLMConfig yet; skip silently

    def effective_model(self, env_model: str, default_model: str) -> str:
        """Return the model to use given env and default values.

        Priority: env (already applied) > config file > default.
        """
        if env_model != default_model:
            return env_model          # env override in effect
        if self.model:
            return self.model         # config file
        return default_model

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save_toml(self, path: Path | None = None) -> Path:
        """Write this config to a TOML file."""
        target = path or config_path_toml()
        lines = ["# Agency runtime configuration\n"]
        if self.model is not None:
            lines.append(f'model = "{self.model}"\n')
        if self.trust_mode is not None:
            lines.append(f'trust_mode = "{self.trust_mode}"\n')
        if self.max_tokens is not None:
            lines.append(f"max_tokens = {self.max_tokens}\n")
        if self.temperature is not None:
            lines.append(f"temperature = {self.temperature}\n")
        if self.backend_url is not None:
            lines.append(f'backend_url = "{self.backend_url}"\n')
        target.write_text("".join(lines), encoding="utf-8")
        return target

    def save_json(self, path: Path | None = None) -> Path:
        """Write this config to a JSON file."""
        target = path or config_path_json()
        data: dict[str, Any] = {}
        if self.model is not None:
            data["model"] = self.model
        if self.trust_mode is not None:
            data["trust_mode"] = self.trust_mode
        if self.max_tokens is not None:
            data["max_tokens"] = self.max_tokens
        if self.temperature is not None:
            data["temperature"] = self.temperature
        if self.backend_url is not None:
            data["backend_url"] = self.backend_url
        target.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return target
