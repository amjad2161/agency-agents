"""Mission B audit tests — Pass 10B.

Covers:
- YAML/frontmatter validator: 0 errors on all skill MDs
- Routing accuracy: >= 70% on 20 representative queries
- Soul filter: no false positives on legitimate content
- README: exists, contains key sections
- Truncated file fixes: core .py files parse clean
"""

from __future__ import annotations

import ast
import pathlib
import re
import sys
import yaml

# Ensure runtime is importable
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

REPO_ROOT = pathlib.Path(__file__).parent.parent.parent
RUNTIME_AGENCY = pathlib.Path(__file__).parent.parent / "agency"

FRONTMATTER = re.compile(r"^---\r?\n(.*?)\r?\n---\r?\n", re.DOTALL)
CATEGORIES = [
    "academic", "design", "engineering", "finance", "game-development",
    "jarvis", "marketing", "paid-media", "product", "project-management",
    "sales", "science", "spatial-computing", "specialized", "strategy",
    "support", "testing",
]


# ---------------------------------------------------------------------------
# Part 1: YAML frontmatter validator
# ---------------------------------------------------------------------------

def _collect_skill_errors() -> list[str]:
    errors: list[str] = []
    seen: dict[str, pathlib.Path] = {}
    for cat in CATEGORIES:
        cat_path = REPO_ROOT / cat
        if not cat_path.exists():
            continue
        for f in sorted(cat_path.glob("*.md")):
            text = f.read_text(encoding="utf-8")
            m = FRONTMATTER.match(text)
            if not m:
                continue  # non-skill MDs (READMEs, etc.) — skip
            try:
                meta = yaml.safe_load(m.group(1)) or {}
            except yaml.YAMLError as e:
                errors.append(f"{f.name}: YAML parse error: {e}")
                continue
            if not isinstance(meta, dict):
                errors.append(f"{f.name}: frontmatter not a dict")
                continue
            slug = f.stem
            if not str(meta.get("name") or "").strip():
                errors.append(f"{f.name}: missing name")
            if not str(meta.get("description") or "").strip():
                errors.append(f"{f.name}: missing description")
            if slug in seen:
                errors.append(f"{f.name}: duplicate slug '{slug}' also in {seen[slug].name}")
            else:
                seen[slug] = f
    return errors


def test_yaml_validator_zero_errors():
    errors = _collect_skill_errors()
    assert errors == [], f"YAML errors found:\n" + "\n".join(errors[:20])


def test_yaml_skill_count():
    seen: set[str] = set()
    for cat in CATEGORIES:
        cat_path = REPO_ROOT / cat
        if not cat_path.exists():
            continue
        for f in cat_path.glob("*.md"):
            text = f.read_text(encoding="utf-8")
            if FRONTMATTER.match(text):
                seen.add(f.stem)
    assert len(seen) >= 300, f"Expected >= 300 skill files, got {len(seen)}"


# ---------------------------------------------------------------------------
# Part 2: Routing accuracy
# ---------------------------------------------------------------------------

TEST_CASES = [
    ("fix my Python bug",            "omega-engineer"),
    ("write a React component",      "frontend"),
    ("review my code",               "engineer"),
    ("deploy to production",         "devops"),
    ("write unit tests",             "engineer"),
    ("create a database schema",     "database"),
    ("help me with git",             "engineer"),
    ("write documentation",          "engineer"),
    ("security audit my code",       "security"),
    ("optimize this SQL query",      "database"),
    ("set up CI/CD pipeline",        "devops"),
    ("build a REST API",             "backend"),
    ("refactor this function",       "omega-engineer"),
    ("containerize my app",          "devops"),
    ("machine learning model",       "ml"),
    ("write a bash script",          "engineer"),
    ("design a system architecture", "architect"),
    ("translate this to Hebrew",     "linguist"),
    ("write a short story",          "creative"),
    ("create a marketing campaign",  "marketing"),
]


def test_routing_accuracy():
    from agency.jarvis_brain import SupremeJarvisBrain
    brain = SupremeJarvisBrain()
    correct = 0
    failures: list[str] = []
    for query, expected_kw in TEST_CASES:
        result = brain.skill_for(query)
        slug = result.skill.slug
        if expected_kw.lower() in slug.lower():
            correct += 1
        else:
            failures.append(f"'{query}' → '{slug}' (expected keyword: '{expected_kw}')")
    accuracy = correct / len(TEST_CASES)
    assert accuracy >= 0.70, (
        f"Routing accuracy {correct}/{len(TEST_CASES)} = {accuracy:.0%} < 70%.\n"
        + "\n".join(failures)
    )


def test_routing_non_empty_result():
    from agency.jarvis_brain import SupremeJarvisBrain
    brain = SupremeJarvisBrain()
    result = brain.skill_for("help me debug this error")
    assert result.skill is not None
    assert result.score > 0
    assert result.skill.slug


# ---------------------------------------------------------------------------
# Part 3: Soul filter — no false positives on legitimate content
# ---------------------------------------------------------------------------

LEGIT_CONTENT = [
    "Here is the solution: use a hash map.",
    "The function takes two arguments.",
    "Install with: pip install agency",
    "The error occurs at line 42.",
    "Use `git commit -m 'fix: resolve memory leak'`",
    "The API returns a JSON object with keys: name, value, timestamp.",
    "In Hebrew: שלום עולם — Hello World",
    "Cannot connect to database — check your connection string.",
    "The model cannot process images larger than 4MB.",
    "Step 1: Install dependencies. Step 2: Configure environment.",
    "Run: docker-compose up -d",
    "Of course the algorithm has O(n log n) complexity.",
    "Use async/await for non-blocking I/O.",
    "The error: TypeError: 'NoneType' object is not subscriptable",
]

FORBIDDEN_CONTENT = [
    "As an AI, I cannot do that.",
    "I'm sorry, but I cannot help with that.",
    "I apologize for the confusion.",
    "Great! Let me help you with that.",
    "Feel free to ask me anything.",
    "Hope this helps!",
    "I don't have feelings about this topic.",
]


def test_soul_filter_no_false_positives():
    from agency.jarvis_soul import filter_response
    false_positives = []
    for text in LEGIT_CONTENT:
        result = filter_response(text)
        if result.strip() != text.strip():
            false_positives.append((text, result))
    assert not false_positives, (
        f"{len(false_positives)} false positives:\n"
        + "\n".join(f"  '{a}' → '{b}'" for a, b in false_positives)
    )


def test_soul_filter_catches_forbidden():
    from agency.jarvis_soul import filter_response
    caught = 0
    for text in FORBIDDEN_CONTENT:
        result = filter_response(text)
        if result.strip() != text.strip():
            caught += 1
    assert caught == len(FORBIDDEN_CONTENT), (
        f"Filter only caught {caught}/{len(FORBIDDEN_CONTENT)} forbidden phrases"
    )


# ---------------------------------------------------------------------------
# Part 4: README exists with key sections
# ---------------------------------------------------------------------------

def test_readme_exists():
    readme = REPO_ROOT / "runtime" / "README.md"
    assert readme.exists(), "runtime/README.md not found"


def test_readme_key_sections():
    readme = (REPO_ROOT / "runtime" / "README.md").read_text(encoding="utf-8")
    required = ["## Install", "## Use", "## Trust", "## Architecture", "agency run", "agency list"]
    missing = [s for s in required if s not in readme]
    assert not missing, f"README missing sections/content: {missing}"


def test_readme_skill_count_updated():
    readme = (REPO_ROOT / "runtime" / "README.md").read_text(encoding="utf-8")
    # Should NOT say "180+" anymore — was updated to 320+
    assert "180+" not in readme, "README still shows stale '180+' skill count"


# ---------------------------------------------------------------------------
# Part 5: Truncated file fixes — core .py files parse clean
# ---------------------------------------------------------------------------

CORE_PY_FILES = [
    "runtime/agency/amjad_jarvis_cli.py",
    "runtime/agency/cli.py",
    "runtime/agency/logging.py",
    "runtime/agency/supervisor.py",
    "runtime/agency/executor.py",
    "runtime/agency/skills.py",
    "runtime/agency/managed_agents.py",
    "runtime/agency/jarvis_brain.py",
    "runtime/agency/jarvis_soul.py",
    "runtime/agency/planner.py",
    "runtime/agency/server.py",
]


def test_core_files_parse():
    errors = []
    for rel in CORE_PY_FILES:
        f = REPO_ROOT / rel
        if not f.exists():
            errors.append(f"{rel}: file missing")
            continue
        try:
            ast.parse(f.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError as e:
            errors.append(f"{rel}: SyntaxError: {e}")
    assert not errors, "Syntax errors in core files:\n" + "\n".join(errors)


def test_no_truncated_exports():
    """Ensure __all__ lists are complete (not cut off mid-string)."""
    bad = []
    for rel in CORE_PY_FILES:
        f = REPO_ROOT / rel
        if not f.exists():
            continue
        last_line = f.read_bytes().rstrip().split(b"\n")[-1]
        if b"__all__" in last_line and not last_line.strip().endswith(b"]"):
            bad.append(f"{rel}: truncated __all__: {last_line!r}")
    assert not bad, "Truncated __all__ found:\n" + "\n".join(bad)
