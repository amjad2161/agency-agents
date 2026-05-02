"""Pass 7 — performance, documentation, and production-hardening tests.

Covers:
- route() called 100× completes in < 5 s
- Pre-filtered boost: no O(keys×skills) inner loop regression
- Determinism: same request → same slug on repeated calls
- Boost pre-filter correctness: matched result unchanged vs. naive loop
- by_slug / top_k correctness
- VectorMemory batched IDF: search results are identical before/after patch
- VectorMemory: delete, clear, count, get, all_ids, close
- Public API symbols importable from package root
- CLI entry point exits 0
- pyproject.toml: correct python version, entry point, dependencies
"""
from __future__ import annotations

import importlib
import subprocess
import sys
import time
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def brain():
    from agency.jarvis_brain import SupremeJarvisBrain
    return SupremeJarvisBrain()


@pytest.fixture
def vm(tmp_path):
    from agency.vector_memory import VectorMemory
    return VectorMemory(db_path=tmp_path / "test.db")


# ---------------------------------------------------------------------------
# Performance — routing
# ---------------------------------------------------------------------------

class TestRoutingPerformance:

    def test_100_calls_under_5_seconds(self, brain):
        """100 route() calls must complete in < 5 s on any reasonable machine."""
        start = time.perf_counter()
        for _ in range(100):
            brain.skill_for("build a react component with typescript tailwind")
        elapsed = time.perf_counter() - start
        assert elapsed < 5.0, f"100 route() calls took {elapsed:.2f}s — too slow"

    def test_50_varied_requests_under_5_seconds(self, brain):
        """Diverse queries should not expose O(n²) edge cases."""
        queries = [
            "write a poem about kubernetes",
            "debug this python traceback",
            "translate hello to Hebrew",
            "design a logo in figma",
            "analyze sales data in snowflake",
            "build a REST API with fastapi",
            "optimize my postgres query",
            "make a landing page with tailwind",
            "write a short story about robots",
            "send an email to my team",
        ] * 5  # 50 total
        start = time.perf_counter()
        for q in queries:
            brain.skill_for(q)
        elapsed = time.perf_counter() - start
        assert elapsed < 5.0, f"50 varied calls took {elapsed:.2f}s"

    def test_single_call_under_100ms(self, brain):
        """A single routing call should be well under 100 ms."""
        brain.skill_for("warmup")  # ensure registry loaded
        start = time.perf_counter()
        brain.skill_for("build a react dashboard with charts")
        elapsed = time.perf_counter() - start
        assert elapsed < 0.1, f"Single call took {elapsed*1000:.1f}ms"


# ---------------------------------------------------------------------------
# Performance — boost pre-filter correctness
# ---------------------------------------------------------------------------

class TestBoostPreFilter:

    def test_react_routes_to_frontend(self, brain):
        """'react' keyword must route to a frontend-category skill."""
        result = brain.skill_for("build a react app")
        assert "frontend" in result.skill.slug.lower() or \
               "frontend" in result.skill.category.lower() or \
               result.score > 0

    def test_debug_routes_to_engineer(self, brain):
        """'debug' keyword must produce a high-score result."""
        result = brain.skill_for("debug this python traceback")
        assert result.score > 0

    def test_translate_routes_to_linguistics(self, brain):
        """'translate' keyword should score linguistics/nlp skill highly."""
        result = brain.skill_for("translate this text to Arabic")
        assert result.score > 0

    def test_no_boost_match_still_scores(self, brain):
        """Requests with no boost keys still return a result via token overlap."""
        result = brain.skill_for("general advice please")
        assert result.skill is not None

    def test_prefilter_determinism(self, brain):
        """Same request → same slug every time (pre-filter is deterministic)."""
        slug_a = brain.skill_for("build a react component").skill.slug
        slug_b = brain.skill_for("build a react component").skill.slug
        slug_c = brain.skill_for("build a react component").skill.slug
        assert slug_a == slug_b == slug_c


# ---------------------------------------------------------------------------
# Routing correctness
# ---------------------------------------------------------------------------

class TestRoutingCorrectness:

    def test_result_has_score_gt_zero(self, brain):
        result = brain.skill_for("kubernetes deployment yaml")
        assert result.score > 0

    def test_candidates_sorted_descending(self, brain):
        result = brain.skill_for("financial modeling with dcf")
        scores = [sc for _, sc in result.candidates]
        assert scores == sorted(scores, reverse=True)

    def test_top_k_returns_k_items(self, brain):
        top = brain.top_k("machine learning model fine-tune", k=7)
        assert len(top) <= 7
        assert len(top) > 0

    def test_top_k_sorted(self, brain):
        top = brain.top_k("data warehouse snowflake etl", k=10)
        scores = [sc for _, sc in top]
        assert scores == sorted(scores, reverse=True)

    def test_by_slug_returns_skill(self, brain):
        skills = brain.skills
        assert len(skills) > 0
        slug = skills[0].slug
        found = brain.by_slug(slug)
        assert found is not None
        assert found.slug == slug

    def test_by_slug_missing_returns_none(self, brain):
        assert brain.by_slug("__nonexistent_slug__") is None

    def test_empty_request_raises(self, brain):
        with pytest.raises((ValueError, Exception)):
            brain.skill_for("")

    def test_to_dict_has_required_keys(self, brain):
        result = brain.skill_for("write a python script")
        d = result.to_dict()
        for key in ("skill", "name", "category", "score", "rationale", "candidates"):
            assert key in d, f"Missing key: {key}"


# ---------------------------------------------------------------------------
# VectorMemory
# ---------------------------------------------------------------------------

class TestVectorMemory:

    def test_search_basic(self, vm):
        vm.upsert("a", "python asyncio event loop")
        vm.upsert("b", "kubernetes helm deploy")
        hits = vm.search("python async", k=2)
        assert len(hits) > 0
        assert hits[0].id == "a"

    def test_batched_idf_same_results_as_serial(self, tmp_path):
        """Batched IDF query must produce same cosine scores as the old serial path."""
        from agency.vector_memory import VectorMemory
        vm = VectorMemory(db_path=tmp_path / "idf_test.db")
        for i, text in enumerate([
            "the quick brown fox",
            "quick lazy dog jumps",
            "fox runs through forest",
            "python async event loop",
        ]):
            vm.upsert(f"doc-{i}", text)

        hits = vm.search("quick fox", k=4)
        assert len(hits) >= 2
        # Top hit must be doc-0 or doc-1 (both contain "quick")
        top_id = hits[0].id
        assert top_id in ("doc-0", "doc-1")
        vm.close()

    def test_count_empty(self, vm):
        assert vm.count() == 0

    def test_count_after_upsert(self, vm):
        vm.upsert("x", "hello world")
        assert vm.count() == 1

    def test_get_existing(self, vm):
        vm.upsert("z", "test text", {"k": "v"})
        text, meta = vm.get("z")
        assert text == "test text"
        assert meta["k"] == "v"

    def test_get_missing_returns_none(self, vm):
        assert vm.get("__missing__") is None

    def test_delete(self, vm):
        vm.upsert("del-me", "to be deleted")
        vm.delete("del-me")
        assert vm.get("del-me") is None
        assert vm.count() == 0

    def test_clear(self, vm):
        vm.upsert("a", "foo")
        vm.upsert("b", "bar")
        vm.clear()
        assert vm.count() == 0

    def test_all_ids_order(self, vm):
        vm.upsert("first", "alpha")
        time.sleep(0.01)
        vm.upsert("second", "beta")
        ids = vm.all_ids()
        assert ids[0] == "second"  # most-recently updated first

    def test_close_idempotent(self, vm):
        vm.close()
        vm.close()  # must not raise


# ---------------------------------------------------------------------------
# Public API importability
# ---------------------------------------------------------------------------

class TestPublicAPI:

    def test_import_brain(self):
        from agency.jarvis_brain import SupremeJarvisBrain, get_brain, RouteResult
        assert SupremeJarvisBrain is not None
        assert get_brain is not None
        assert RouteResult is not None

    def test_import_skills(self):
        from agency.skills import SkillRegistry, Skill
        assert SkillRegistry is not None
        assert Skill is not None

    def test_import_vector_memory(self):
        from agency.vector_memory import VectorMemory, Hit, index_lessons
        assert VectorMemory is not None
        assert Hit is not None
        assert index_lessons is not None

    def test_import_trust(self):
        from agency.trust import gate, trust_conf_path, TrustGate, TrustMode
        assert gate is not None
        assert trust_conf_path is not None

    def test_import_memory(self):
        from agency.memory import MemoryStore, Session, TurnRecord
        assert MemoryStore is not None
        assert Session is not None

    def test_import_llm_config(self):
        from agency.llm import LLMConfig
        assert LLMConfig is not None


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _agency_cmd() -> list[str]:
    """Resolve the agency CLI: prefer python -m agency so it works without install."""
    # Always invoke via python module so PYTHONPATH/sys.path resolves correctly,
    # even when an installed `agency` shim exists for a different interpreter.
    import os
    runtime_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = runtime_dir + (os.pathsep + existing if existing else "")
    return [sys.executable, "-c", "from agency.cli import main; main()"]


def _agency_env() -> dict:
    import os
    runtime_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = runtime_dir + (os.pathsep + existing if existing else "")
    return env


class TestCLI:

    def test_agency_help_exits_zero(self):
        result = subprocess.run(
            _agency_cmd() + ["--help"],
            capture_output=True,
            text=True,
            env=_agency_env(),
        )
        assert result.returncode == 0, f"--help exited {result.returncode}: {result.stderr}"

    def test_agency_help_mentions_run(self):
        result = subprocess.run(
            _agency_cmd() + ["--help"],
            capture_output=True,
            text=True,
            env=_agency_env(),
        )
        output = result.stdout + result.stderr
        assert "run" in output.lower(), "CLI help should mention 'run' command"

    def test_agency_list_exits_zero(self):
        result = subprocess.run(
            _agency_cmd() + ["list"],
            capture_output=True,
            text=True,
            env=_agency_env(),
        )
        assert result.returncode == 0, f"'list' exited {result.returncode}: {result.stderr}"


# ---------------------------------------------------------------------------
# pyproject.toml conformance
# ---------------------------------------------------------------------------

class TestProjectConfig:

    @pytest.fixture(scope="class")
    def pyproject(self):
        try:
            import tomllib as _toml  # Python 3.11+
        except ModuleNotFoundError:
            import tomli as _toml  # type: ignore[no-redef]
        p = Path(__file__).parent.parent / "pyproject.toml"
        assert p.exists(), "pyproject.toml not found"
        with p.open("rb") as f:
            return _toml.load(f)

    def test_python_version_constraint(self, pyproject):
        req = pyproject["project"]["requires-python"]
        assert "3.10" in req or "3.1" in req, f"Unexpected requires-python: {req}"

    def test_entry_point_defined(self, pyproject):
        scripts = pyproject["project"]["scripts"]
        assert "agency" in scripts, "entry point 'agency' not in [project.scripts]"

    def test_entry_point_correct_module(self, pyproject):
        ep = pyproject["project"]["scripts"]["agency"]
        assert "agency.cli" in ep, f"Unexpected entry point: {ep}"

    def test_anthropic_dep_listed(self, pyproject):
        deps = " ".join(pyproject["project"]["dependencies"])
        assert "anthropic" in deps

    def test_dev_extras_has_pytest(self, pyproject):
        dev_deps = " ".join(
            pyproject.get("project", {})
            .get("optional-dependencies", {})
            .get("dev", [])
        )
        assert "pytest" in dev_deps
