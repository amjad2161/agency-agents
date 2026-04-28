"""Pass 10-C: comprehensive regression tests for JARVIS runtime.

Covers: MemoryStore persistence, Session/TurnRecord model, SkillRegistry,
Planner routing, Skill tool policy, planner JSON parsing, and static health.

Run:
    cd runtime && pytest tests/test_jarvis_pass10c.py -v
"""

from __future__ import annotations

from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_memory_root(tmp_path: Path) -> Path:
    return tmp_path / "sessions"


@pytest.fixture()
def memory_store(tmp_memory_root: Path):
    from agency.memory import MemoryStore

    return MemoryStore(tmp_memory_root)


@pytest.fixture()
def sample_session():
    from agency.memory import Session

    return Session(session_id="test-abc-123", skill_slug="engineering-lead")


@pytest.fixture()
def registry():
    from agency.skills import SkillRegistry, discover_repo_root

    root = discover_repo_root()
    return SkillRegistry.load(root)


# ---------------------------------------------------------------------------
# Part 1 — MemoryStore persistence (6 tests)
# ---------------------------------------------------------------------------


class TestMemoryStorePersistence:
    def test_load_nonexistent_returns_none(self, memory_store) -> None:
        assert memory_store.load("no-such-session") is None

    def test_save_and_load_roundtrip(self, memory_store, sample_session) -> None:
        memory_store.save(sample_session)
        loaded = memory_store.load(sample_session.session_id)
        assert loaded is not None
        assert loaded.session_id == sample_session.session_id

    def test_save_preserves_skill_slug(self, memory_store, sample_session) -> None:
        memory_store.save(sample_session)
        loaded = memory_store.load(sample_session.session_id)
        assert loaded is not None
        assert loaded.skill_slug == "engineering-lead"

    def test_save_creates_file_on_disk(
        self, memory_store, sample_session, tmp_memory_root: Path
    ) -> None:
        memory_store.save(sample_session)
        files = list(tmp_memory_root.rglob("*.jsonl"))
        assert len(files) >= 1

    def test_overwrite_preserves_latest_turns(
        self, memory_store, sample_session
    ) -> None:
        from agency.memory import TurnRecord

        memory_store.save(sample_session)
        sample_session.turns.append(TurnRecord(role="user", content="hello"))
        memory_store.save(sample_session)
        loaded = memory_store.load(sample_session.session_id)
        assert loaded is not None
        assert len(loaded.turns) == 1

    def test_multiple_sessions_independent(self, memory_store) -> None:
        from agency.memory import Session

        s1 = Session(session_id="session-one", skill_slug="alpha")
        s2 = Session(session_id="session-two", skill_slug="beta")
        memory_store.save(s1)
        memory_store.save(s2)
        r1 = memory_store.load("session-one")
        r2 = memory_store.load("session-two")
        assert r1 is not None and r1.skill_slug == "alpha"
        assert r2 is not None and r2.skill_slug == "beta"


# ---------------------------------------------------------------------------
# Part 2 — Session / TurnRecord model (4 tests)
# ---------------------------------------------------------------------------


class TestSessionModel:
    def test_session_default_turns_empty(self) -> None:
        from agency.memory import Session

        s = Session(session_id="x", skill_slug="y")
        assert s.turns == []

    def test_turn_record_fields(self) -> None:
        from agency.memory import TurnRecord

        t = TurnRecord(role="assistant", content="Hi there!")
        assert t.role == "assistant"
        assert t.content == "Hi there!"

    def test_session_id_preserved(self) -> None:
        from agency.memory import Session

        s = Session(session_id="unique-id-999", skill_slug="test-skill")
        assert s.session_id == "unique-id-999"

    def test_turns_append_multiple(self, sample_session) -> None:
        from agency.memory import TurnRecord

        sample_session.turns.append(TurnRecord(role="user", content="question"))
        sample_session.turns.append(TurnRecord(role="assistant", content="answer"))
        assert len(sample_session.turns) == 2


# ---------------------------------------------------------------------------
# Part 3 — SkillRegistry (9 tests)
# ---------------------------------------------------------------------------


class TestSkillRegistry:
    def test_registry_loads_skills(self, registry) -> None:
        assert len(registry) > 0

    def test_registry_all_returns_list(self, registry) -> None:
        skills = registry.all()
        assert isinstance(skills, list)
        assert len(skills) > 0

    def test_registry_by_slug_known(self, registry) -> None:
        slug = registry.all()[0].slug
        skill = registry.by_slug(slug)
        assert skill is not None
        assert skill.slug == slug

    def test_registry_by_slug_missing_returns_none(self, registry) -> None:
        assert registry.by_slug("no-such-skill-xyzzy-42") is None

    def test_registry_categories_nonempty(self, registry) -> None:
        cats = registry.categories()
        assert isinstance(cats, list)
        assert len(cats) > 0

    def test_registry_categories_sorted(self, registry) -> None:
        cats = registry.categories()
        assert cats == sorted(cats)

    def test_registry_by_category_filters(self, registry) -> None:
        cat = registry.categories()[0]
        skills = registry.by_category(cat)
        assert len(skills) > 0
        assert all(s.category == cat for s in skills)

    def test_registry_search_returns_results(self, registry) -> None:
        results = registry.search("engineer")
        assert len(results) > 0

    def test_registry_search_empty_returns_empty(self, registry) -> None:
        assert registry.search("") == []


# ---------------------------------------------------------------------------
# Part 4 — Skill properties (3 tests)
# ---------------------------------------------------------------------------


class TestSkillProperties:
    def test_skill_system_prompt_nonempty(self, registry) -> None:
        s = registry.all()[0]
        assert len(s.system_prompt.strip()) > 0

    def test_skill_summary_contains_name(self, registry) -> None:
        s = registry.all()[0]
        assert s.name in s.summary()

    def test_skill_summary_contains_emoji(self, registry) -> None:
        s = registry.all()[0]
        assert s.emoji in s.summary()


# ---------------------------------------------------------------------------
# Part 5 — Skill tool policy (3 tests)
# ---------------------------------------------------------------------------


class TestSkillToolPolicy:
    def test_no_policy_allows_all_tools(self, registry) -> None:
        # Pick a skill without explicit tool policy
        candidates = [s for s in registry.all() if s.tools_allowed is None]
        if not candidates:
            pytest.skip("No skills without tool policy in this registry")
        s = candidates[0]
        assert s.tool_is_allowed("read_file") is True
        assert s.tool_is_allowed("bash") is True

    def test_tools_denied_blocks_named_tool(self) -> None:
        from agency.skills import Skill

        s = Skill(
            slug="t",
            name="T",
            description="",
            category="test",
            color="white",
            emoji="🤖",
            vibe="",
            body="",
            path=Path("/tmp/t.md"),
            tools_denied=("bash",),
        )
        assert s.tool_is_allowed("bash") is False
        assert s.tool_is_allowed("read_file") is True

    def test_tools_allowed_restricts_to_allowlist(self) -> None:
        from agency.skills import Skill

        s = Skill(
            slug="t",
            name="T",
            description="",
            category="test",
            color="white",
            emoji="🤖",
            vibe="",
            body="",
            path=Path("/tmp/t.md"),
            tools_allowed=("read_file",),
        )
        assert s.tool_is_allowed("read_file") is True
        assert s.tool_is_allowed("bash") is False


# ---------------------------------------------------------------------------
# Part 6 — Planner JSON parsing (5 tests)
# ---------------------------------------------------------------------------


class TestPlannerParsing:
    def test_parse_clean_json_choice(self) -> None:
        from agency.planner import _parse_choice

        idx, rationale = _parse_choice('{"choice": 2, "rationale": "best match"}')
        assert idx == 1  # 1-indexed → 0-indexed
        assert "best match" in rationale

    def test_parse_json_embedded_in_prose(self) -> None:
        from agency.planner import _parse_choice

        idx, _ = _parse_choice('Sure! {"choice": 1, "rationale": "top pick"} done.')
        assert idx == 0

    def test_parse_missing_json_returns_zero(self) -> None:
        from agency.planner import _parse_choice

        idx, _ = _parse_choice("no json here at all")
        assert idx == 0

    def test_parse_choice_1_indexed(self) -> None:
        from agency.planner import _parse_choice

        # choice=3 → index 2
        idx, _ = _parse_choice('{"choice": 3, "rationale": "third"}')
        assert idx == 2

    def test_parse_invalid_json_returns_zero(self) -> None:
        from agency.planner import _parse_choice

        idx, _ = _parse_choice("{broken json !!}")
        assert idx == 0


# ---------------------------------------------------------------------------
# Part 7 — _parse_tool_list (3 tests)
# ---------------------------------------------------------------------------


class TestParseToolList:
    def test_none_returns_none(self) -> None:
        from agency.skills import _parse_tool_list

        assert _parse_tool_list(None) is None

    def test_comma_string_parsed(self) -> None:
        from agency.skills import _parse_tool_list

        result = _parse_tool_list("read_file, bash, write_file")
        assert result == ("read_file", "bash", "write_file")

    def test_list_input_converted(self) -> None:
        from agency.skills import _parse_tool_list

        result = _parse_tool_list(["tool_a", "tool_b"])
        assert result == ("tool_a", "tool_b")


# ---------------------------------------------------------------------------
# Part 8 — Planner routing (2 tests, offline / no API key needed)
# ---------------------------------------------------------------------------


class TestPlannerRouting:
    def test_hint_slug_bypasses_llm(self, registry) -> None:
        from agency.planner import Planner

        slug = registry.all()[0].slug
        planner = Planner(registry, llm=None)
        result = planner.plan("anything at all", hint_slug=slug)
        assert result.skill.slug == slug
        assert result.rationale == "explicit user choice"

    def test_planner_returns_plan_result(self, registry) -> None:
        from agency.planner import Planner, PlanResult

        planner = Planner(registry, llm=None)
        result = planner.plan("write some python code")
        assert isinstance(result, PlanResult)
        assert result.skill is not None
        assert len(result.candidates) > 0
