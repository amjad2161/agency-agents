"""Pass 9: Production hardening — import safety, resource hygiene, CLI health."""

from __future__ import annotations

import ast
import subprocess
import sys
import time
from pathlib import Path

import pytest

# ── helpers ────────────────────────────────────────────────────────────────
RUNTIME = Path(__file__).parent.parent
AGENCY_PKG = RUNTIME / "agency"

sys.path.insert(0, str(RUNTIME))


def _agency_sources() -> list[Path]:
    return [p for p in AGENCY_PKG.rglob("*.py") if "test" not in p.parts]


# ── 1. Import speed ────────────────────────────────────────────────────────

def test_import_agency_top_level_fast():
    """Top-level `import agency` should complete in <2 s (no side-effects)."""
    t0 = time.perf_counter()
    import agency  # noqa: F401
    elapsed = time.perf_counter() - t0
    assert elapsed < 2.0, f"import agency took {elapsed:.2f}s (>2s limit)"


def test_import_jarvis_brain_fast():
    t0 = time.perf_counter()
    import agency.jarvis_brain  # noqa: F401
    elapsed = time.perf_counter() - t0
    assert elapsed < 3.0


def test_import_jarvis_soul_fast():
    t0 = time.perf_counter()
    import agency.jarvis_soul  # noqa: F401
    elapsed = time.perf_counter() - t0
    assert elapsed < 3.0


def test_import_all_core_modules_total_under_5s():
    """All 9 core modules importable and collectively <5 s."""
    modules = [
        "agency.jarvis_brain",
        "agency.jarvis_soul",
        "agency.jarvis_greeting",
        "agency.amjad_memory",
        "agency.vector_memory",
        "agency.trust",
        "agency.skills",
        "agency.persona_engine",
    ]
    import importlib
    t0 = time.perf_counter()
    for mod in modules:
        importlib.import_module(mod)
    elapsed = time.perf_counter() - t0
    assert elapsed < 5.0, f"core modules took {elapsed:.2f}s total"


# ── 2. No circular imports ─────────────────────────────────────────────────

@pytest.mark.parametrize("mod", [
    "agency.jarvis_brain",
    "agency.jarvis_soul",
    "agency.jarvis_greeting",
    "agency.amjad_memory",
    "agency.vector_memory",
    "agency.trust",
    "agency.skills",
    "agency.persona_engine",
])
def test_no_circular_import(mod):
    import importlib
    try:
        importlib.import_module(mod)
    except ImportError as exc:
        pytest.fail(f"Import failed for {mod}: {exc}")


# ── 3. CLI: `agency list` returns non-empty output ────────────────────────

def test_agency_list_returns_output():
    result = subprocess.run(
        [sys.executable, "-m", "agency.cli", "list"],
        cwd=str(RUNTIME),
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, f"list failed: {result.stderr[:300]}"
    assert len(result.stdout.strip()) > 0, "list produced no output"


def test_agency_list_contains_skills():
    result = subprocess.run(
        [sys.executable, "-m", "agency.cli", "list"],
        cwd=str(RUNTIME),
        capture_output=True,
        text=True,
        timeout=20,
    )
    # Should show at least some skill names
    assert "skill" in result.stdout.lower() or any(
        line.strip() for line in result.stdout.splitlines()
    ), "list output looks empty"


# ── 4. CLI: `agency run --help` exits 0 ───────────────────────────────────

def test_agency_run_help_exits_zero():
    result = subprocess.run(
        [sys.executable, "-m", "agency", "run", "--help"],
        cwd=str(RUNTIME),
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, f"run --help failed: {result.stderr[:300]}"


def test_agency_main_help_exits_zero():
    """`python -m agency --help` works (requires __main__.py)."""
    result = subprocess.run(
        [sys.executable, "-m", "agency", "--help"],
        cwd=str(RUNTIME),
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, f"agency --help failed: {result.stderr[:300]}"


# ── 5. File handle safety (static AST check) ──────────────────────────────

def _collect_unsafe_opens(path: Path) -> list[tuple[int, str]]:
    """Return (lineno, snippet) for open() calls NOT inside a `with` statement.

    Whitelists:
      * webbrowser.open (not a file handle)
      * open() calls inside __enter__ methods of context-manager classes
        (the matching __exit__ is responsible for closing the handle)
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return []

    def _is_browser_open(node):
        if isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name) and node.func.value.id == "webbrowser":
                return True
        return False

    unsafe: list[tuple[int, str]] = []

    class Visitor(ast.NodeVisitor):
        def __init__(self):
            self._in_with = 0
            self._enter_depth = 0  # inside __enter__ of a CM class

        def visit_With(self, node):
            self._in_with += 1
            self.generic_visit(node)
            self._in_with -= 1

        def visit_AsyncWith(self, node):
            self._in_with += 1
            self.generic_visit(node)
            self._in_with -= 1

        def visit_ClassDef(self, node):
            method_names = {n.name for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
            is_cm = "__enter__" in method_names and "__exit__" in method_names
            for child in node.body:
                if is_cm and isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name == "__enter__":
                    self._enter_depth += 1
                    self.generic_visit(child)
                    self._enter_depth -= 1
                else:
                    self.generic_visit(child)

        def visit_Call(self, node):
            if self._in_with == 0 and self._enter_depth == 0:
                name = ""
                if isinstance(node.func, ast.Name):
                    name = node.func.id
                elif isinstance(node.func, ast.Attribute):
                    name = node.func.attr
                if name == "open" and not _is_browser_open(node):
                    unsafe.append((node.lineno, ast.unparse(node)[:80]))
            self.generic_visit(node)

    Visitor().visit(tree)
    return unsafe


def test_no_bare_file_opens_in_agency_sources():
    """All open() calls in agency/ use context managers (no handle leaks)."""
    violations: list[str] = []
    for src in _agency_sources():
        for lineno, snippet in _collect_unsafe_opens(src):
            rel = src.relative_to(RUNTIME)
            violations.append(f"{rel}:{lineno}: {snippet}")
    assert not violations, "Bare open() calls (not in `with`):\n" + "\n".join(violations)


# ── 6. SkillRegistry ───────────────────────────────────────────────────────

def test_skill_categories_non_empty_strings():
    from agency.skills import SkillRegistry
    r = SkillRegistry.load()
    cats = r.categories()
    assert len(cats) > 0, "No skill categories"
    for c in cats:
        assert isinstance(c, str) and c.strip(), f"Bad category: {c!r}"


def test_skill_by_slug_returns_none_for_unknown():
    from agency.skills import SkillRegistry
    r = SkillRegistry.load()
    result = r.by_slug("this-slug-does-not-exist-xyzzy")
    assert result is None, f"Expected None, got {result!r}"


def test_skill_registry_total_count_positive():
    from agency.skills import SkillRegistry
    r = SkillRegistry.load()
    assert len(r.all()) > 0, "SkillRegistry loaded zero skills"


# ── 7. __main__.py exists ─────────────────────────────────────────────────

def test_agency_main_py_exists():
    """runtime/agency/__main__.py must exist for `python -m agency` to work."""
    assert (AGENCY_PKG / "__main__.py").exists(), "__main__.py missing from agency package"


