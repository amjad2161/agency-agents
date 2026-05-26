"""Pass 7 — performance, documentation, and production-hardening tests."""
from __future__ import annotations

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
        """100 route() calls must complete in < 5 s."""
        start = time.perf_counter()
        for _ in range(100):
            brain.skill_for("build a react component with typescript tailwind")
        elapsed = time.perf_counter() - start
        assert elapsed < 5.0, f"100 route() calls took {elapsed:.2f}s — too slow"

    def test_50_varied_requests_under_5_seconds(self, brain):
        """Diverse queries must not expose O(n^2) edge cases."""
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
        ] * 5
        start = time.perf_counter()
        for q in queries:
            brain.skill_for(q)
        elapsed = time.perf_counter() - start
        assert elapsed < 5.0, f"50 varied calls took {elapsed:.2f}s"

    def test_single_call_under_100ms(self, brain):
        """A single routing call should be well under 100 ms."""
        brain.skill_for("warmup")
        start = time.perf_counter()
        brain.skill_for("build a react dashboard with charts")
        elapsed = time.perf_counter() - start
        assert elapsed < 0.1, f"Single call took {elapsed*1000:.1f}ms"


# ---------------------------------------------------------------------------
# Boost pre-filter correctness
# ---------------------------------------------------------------------------

class TestBoostPreFilter:

    def test_react_routes_positively(self, brain):
        result = brain.skill_for("build a react app")
        assert result.score > 0

    def test_debug_routes_positively(self, brain):
        result = brain.skill_for("debug this python traceback")
        assert result.score > 0

    def test_translate_routes_positively(self, brain):
        result = brain.skill_for("translate this text to Arabic")
        assert result.score > 0

    def test_no_boost_match_still_returns_result(self, brain):
        result = brain.skill_for("general advice please")
        assert result.skill is not None

    def test_prefilter_determinism(self, brain):
        """Same request returns same slug every time."""
        slug_a = brain.skill_for("build a react component").skill.slug
        slug_b = brain.skill_for("build a react component").skill.slug
        slug_c = brain.skill_for("build a react component").skill.slug
        assert slug_a == slug_b == slug_c

    def test_high_boost_term_outscores_generic(self, brain):
        """'create a website' boost (10.0) should produce a high score."""
        result = brain.skill_for("create a website for my startup")
        assert result.score >= 10.0


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

    def test_top_k_returns_at_most_k(self, brain):
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
        with pytest.raises(Exception):
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

    def test_batched_idf_correctness(self, tmp_path):
        """Batched IDF query must rank results correctly."""
        from agency.vector_memory import VectorMemory
        vm2 = VectorMemory(db_path=tmp_path / "idf_test.db")
        for i, text in enumerate([
            "the quick brown fox",
            "quick lazy dog jumps",
            "fox runs through forest",
            "python async event loop",
        ]):
            vm2.upsert(f"doc-{i}", text)
        hits = vm2.search("quick fox", k=4)
        assert len(hits) >= 2
        top_id = hits[0].id
        assert top_id in ("doc-0", "doc-1")
        vm2.close()

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

    def test_all_ids_most_recent_first(self, vm):
        vm.upsert("first", "alpha")
        time.sleep(0.01)
        vm.upsert("second", "beta")
        ids = vm.all_ids()
        assert ids[0] == "second"

    def test_close_idempotent(self, vm):
        vm.close()
        vm.close()


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
    """Resolve the agency CLI entry point.

    Prefer invoking via `python -c` so the test does not depend on a
    globally-installed `agency` console script — it just needs the package
    importable, which `_cli_env()` arranges via PYTHONPATH.
    """
    return [sys.executable, "-c", "from agency.cli import main; main()"]


def _cli_env() -> dict[str, str]:
    """Subprocess env that ensures `agency` is importable from the source tree."""
    import os

    runtime_root = Path(__file__).resolve().parent.parent
    existing = os.environ.get("PYTHONPATH", "")
    pypath = str(runtime_root) + (os.pathsep + existing if existing else "")
    return {**os.environ, "PYTHONPATH": pypath}


class TestCLI:

    def test_agency_help_exits_zero(self):
        result = subprocess.run(
            _agency_cmd() + ["--help"],
            capture_output=True, text=True, env=_cli_env(),
        )
        assert result.returncode == 0, f"--help exited {result.returncode}: {result.stderr}"

    def test_agency_help_mentions_run(self):
        result = subprocess.run(
            _agency_cmd() + ["--help"],
            capture_output=True, text=True, env=_cli_env(),
        )
        output = result.stdout + result.stderr
        assert "run" in output.lower(), "CLI help should mention 'run' command"

    def test_agency_list_exits_zero(self):
        result = subprocess.run(
            _agency_cmd() + ["list"],
            capture_output=True, text=True, env=_cli_env(),
        )
        assert result.returncode == 0, f"'list' exited {result.returncode}: {result.stderr}"


# ---------------------------------------------------------------------------
# pyproject.toml conformance
# ---------------------------------------------------------------------------

class TestProjectConfig:

    @pytest.fixture(scope="class")
    def pyproject(self):
        try:
            import tomllib as _toml
        except ModuleNotFoundError:
            import tomli as _toml  # type: ignore[no-redef]
        p = Path(__file__).parent.parent / "pyproject.toml"
        assert p.exists(), "pyproject.toml not found"
        with p.open("rb") as f:
            return _toml.load(f)

    def test_python_version_constraint(self, pyproject):
        req = pyproject["project"]["requires-python"]
        assert "3.10" in req or "3.1" in req, f"Unexpected: {req}"

    def test_entry_point_defined(self, pyproject):
        scripts = pyproject["project"]["scripts"]
        assert "agency" in scripts

    def test_entry_point_correct_module(self, pyproject):
        ep = pyproject["project"]["scripts"]["agency"]
        assert "agency.cli" in ep, f"Unexpected entry point: {ep}"

    def test_anthropic_dep_listed(self, pyproject):
        deps = " ".join(pyproject["project"]["dependencies"])
        assert "anthropic" in deps

    def test_dev_extras_has_pytest(self, pyproject):
        dev_deps = " ".join(pyproject["project"]["optional-dependencies"]["dev"])
        assert "pytest" in dev_deps
