"""Shared diagnostic helpers used by `agency doctor` and `/api/health`.

Single source of truth for:
- Which optional-deps groups exist and what they install.
- How to probe one without crashing on weird import-time errors.

Keeping this in one place stops `doctor` and `health` from drifting if a
new optional extra is added to pyproject.toml.
"""

from __future__ import annotations

# group name → list of importable module names that signal "installed"
OPTIONAL_DEP_GROUPS: dict[str, tuple[str, ...]] = {
    "docs": ("pypdf", "docx", "openpyxl"),
    "computer": ("pyautogui", "PIL"),
}


def optional_deps_status() -> dict[str, dict]:
    """Probe every optional-dep group and report installed / missing / errors.

    Catches the broadest exception class on import — some optional libs
    (e.g. pyautogui in a headless container) can raise things other than
    ImportError when they look up resources at import time. We treat any
    failure as "not usable" so callers (k8s probes, doctor) get a stable
    answer instead of a 500.
    """
    import importlib

    result: dict[str, dict] = {}
    for group, mods in OPTIONAL_DEP_GROUPS.items():
        missing: list[str] = []
        errors: dict[str, str] = {}
        for m in mods:
            try:
                importlib.import_module(m)
            except ImportError:
                missing.append(m)
            except Exception as e:  # noqa: BLE001 — see docstring
                errors[m] = f"{type(e).__name__}: {e}"
        result[group] = {
            "installed": not missing and not errors,
            "missing": missing,
            "errors": errors,
        }
    return result
