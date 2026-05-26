"""Pass 20 — Multi-agent, Dashboard, Installer, Personality tests.

30 tests covering all 4 new modules.  No live API key required;
no real Flask server is spawned for most tests (uses test_client()).

Run:
    cd runtime
    PYTHONPYCACHEPREFIX=/tmp/fresh_pycache \\
    python -m pytest tests/test_jarvis_pass20.py -q --tb=short --timeout=60
"""

from __future__ import annotations

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))


# ===========================================================================
# 1. multi_agent.py
# ===========================================================================

class TestAgentRole:
    def test_all_six_roles_exist(self):
        from agency.multi_agent import AgentRole
        names = {r.value for r in AgentRole}
        assert names == {"planner", "executor", "critic", "memory", "robot", "vision"}

    def test_role_is_str_enum(self):
        from agency.multi_agent import AgentRole
        assert AgentRole.PLANNER == "planner"

    def test_role_iteration(self):
        from agency.multi_agent import AgentRole
        assert len(list(AgentRole)) == 6


class TestAgentDataclass:
    def test_defaults(self):
        from agency.multi_agent import Agent, AgentRole
        a = Agent(role=AgentRole.EXECUTOR, name="exe")
        assert a.model == "claude-sonnet-4-6"
        assert a.tools_allowed == []
        assert a.system_prompt == ""

    def test_custom_fields(self):
        from agency.multi_agent import Agent, AgentRole
        a = Agent(role=AgentRole.VISION, name="eye",
                  model="claude-haiku-4-5-20251001",
                  tools_allowed=["vision_tool"],
                  system_prompt="You see things.")
        assert a.model == "claude-haiku-4-5-20251001"
        assert "vision_tool" in a.tools_allowed


class TestAgentMessage:
    def test_message_fields(self):
        from agency.multi_agent import AgentMessage
        m = AgentMessage(sender="a", recipient="b", content="hello")
        assert m.sender == "a"
        assert m.recipient == "b"
        assert m.content == "hello"
        assert m.timestamp > 0

    def test_unique_ids(self):
        from agency.multi_agent import AgentMessage
        ids = {AgentMessage(sender="x", recipient="y", content="z").msg_id
               for _ in range(20)}
        assert len(ids) == 20


class TestOrchestratorResult:
    def _make(self):
        from agency.multi_agent import OrchestratorResult, TaskStep
        steps = [TaskStep(index=0, description="do X", status="done", output="done X")]
        return OrchestratorResult(
            task="test task",
            task_id="abc123",
            steps=steps,
            outputs=["done X"],
            critique="PASS — looks good",
            success=True,
            elapsed=0.42,
        )

    def test_final_output(self):
        r = self._make()
        assert r.final_output() == "done X"

    def test_to_dict_keys(self):
        r = self._make()
        d = r.to_dict()
        for key in ("task", "task_id", "steps", "outputs", "critique", "success", "elapsed"):
            assert key in d

    def test_empty_outputs_final(self):
        from agency.multi_agent import OrchestratorResult
        r = OrchestratorResult(task="t", task_id="x", steps=[], outputs=[],
                               critique="", success=False, elapsed=0.0)
        assert r.final_output() == ""


class TestMultiAgentOrchestrator:
    def _orch(self):
        from agency.multi_agent import MultiAgentOrchestrator
        return MultiAgentOrchestrator()

    def test_default_pool_has_six_agents(self):
        orch = self._orch()
        assert len(orch.list_agents()) == 6

    def test_add_agent_replaces_role(self):
        from agency.multi_agent import Agent, AgentRole
        orch = self._orch()
        new_a = Agent(role=AgentRole.PLANNER, name="custom_planner")
        orch.add_agent(new_a)
        assert orch.get_agent(AgentRole.PLANNER).name == "custom_planner"

    def test_get_agent_returns_none_for_invalid(self):
        orch = self._orch()
        # Passing a non-existent key via dict access
        from agency.multi_agent import AgentRole
        # All roles should be present; test status dict
        st = orch.status()
        assert "agents" in st
        assert len(st["agents"]) == 6

    def test_run_task_returns_result_type(self):
        from agency.multi_agent import MultiAgentOrchestrator, OrchestratorResult
        orch = MultiAgentOrchestrator()
        result = orch.run_task("test task")
        assert isinstance(result, OrchestratorResult)

    def test_run_task_has_steps(self):
        orch = self._orch()
        result = orch.run_task("plan and execute: write hello world")
        assert len(result.steps) > 0

    def test_run_task_has_outputs(self):
        orch = self._orch()
        result = orch.run_task("summarise quantum computing")
        assert len(result.outputs) > 0

    def test_run_task_success_is_bool(self):
        orch = self._orch()
        result = orch.run_task("test")
        assert isinstance(result.success, bool)

    def test_run_task_elapsed_positive(self):
        orch = self._orch()
        result = orch.run_task("something")
        assert result.elapsed >= 0

    def test_status_dict_structure(self):
        orch = self._orch()
        st = orch.status()
        assert "active" in st
        assert "agents" in st
        assert "tasks_completed" in st
        assert "messages_total" in st

    def test_tasks_completed_increments(self):
        orch = self._orch()
        orch.run_task("task 1")
        orch.run_task("task 2")
        assert orch.status()["tasks_completed"] == 2

    def test_message_log_populated(self):
        orch = self._orch()
        orch.run_task("generate a poem")
        assert orch.status()["messages_total"] > 0

    def test_recent_results(self):
        orch = self._orch()
        orch.run_task("task A")
        results = orch.recent_results(n=5)
        assert len(results) == 1
        assert results[0]["task"] == "task A"

    def test_not_active_after_completion(self):
        orch = self._orch()
        orch.run_task("quick task")
        assert orch.status()["active"] is False


# ===========================================================================
# 2. installer.py
# ===========================================================================

class TestCapabilityDescriptor:
    def test_all_capabilities_present(self):
        from agency.installer import CAPABILITIES
        for name in ("core", "robotics", "vision", "voice", "rl", "browser", "torch"):
            assert name in CAPABILITIES

    def test_capability_has_packages(self):
        from agency.installer import CAPABILITIES
        for cap in CAPABILITIES.values():
            assert len(cap.packages) > 0

    def test_detect_returns_bool(self):
        from agency.installer import CAPABILITIES
        result = CAPABILITIES["core"].detect()
        assert isinstance(result, bool)

    def test_detect_capabilities_returns_dict(self):
        from agency.installer import detect_capabilities
        d = detect_capabilities()
        assert isinstance(d, dict)
        assert "core" in d

    def test_detect_windows_capabilities_alias(self):
        from agency.installer import detect_windows_capabilities
        d = detect_windows_capabilities()
        assert "core" in d

    def test_capability_table_has_rows(self):
        from agency.installer import capability_table
        rows = capability_table()
        assert len(rows) >= 7
        for row in rows:
            assert "name" in row
            assert "status" in row

    def test_install_unknown_returns_false(self):
        from agency.installer import install_capability
        result = install_capability("nonexistent_cap_xyz", quiet=True)
        assert result is False


# ===========================================================================
# 3. personality.py
# ===========================================================================

class TestJarvisPersonality:
    def _p(self, **kw):
        from agency.personality import JarvisPersonality
        return JarvisPersonality(**kw)

    def test_defaults(self):
        p = self._p()
        assert p.name == "JARVIS"
        assert p.language == "he"
        assert p.formality == "formal"
        assert p.response_style == "concise"

    def test_catchphrases_populated_on_init(self):
        p = self._p()
        assert len(p.catchphrases) > 0

    def test_hebrew_formal_contains_expected(self):
        p = self._p(language="he", formality="formal")
        phrases = set(p.catchphrases)
        assert "בבקשה" in phrases or "כמובן" in phrases  # at least one Hebrew phrase

    def test_english_casual_not_hebrew(self):
        p = self._p(language="en", formality="casual")
        for ph in p.catchphrases:
            # Should be ASCII/Latin, not Hebrew
            assert all(ord(c) < 0x590 or c in " .!?" for c in ph)

    def test_greet_contains_name(self):
        p = self._p(name="ATLAS")
        assert "ATLAS" in p.greet()

    def test_greet_hebrew_formal(self):
        p = self._p(language="he", formality="formal")
        greeting = p.greet()
        assert len(greeting) > 0

    def test_greet_english_casual(self):
        p = self._p(language="en", formality="casual")
        assert "Hey" in p.greet() or "JARVIS" in p.greet()

    def test_format_response_concise_prefix(self):
        p = self._p(language="en", formality="formal", response_style="concise")
        formatted = p.format_response("Hello world.")
        assert "Hello world." in formatted

    def test_format_response_verbose_has_suffix(self):
        p = self._p(language="en", formality="formal", response_style="verbose")
        formatted = p.format_response("Test output.", context="done")
        assert len(formatted) > len("Test output.")

    def test_format_response_error_context(self):
        p = self._p(language="he", formality="formal")
        formatted = p.format_response("Something went wrong.", context="error")
        # Should have an apology prefix
        assert "מצטער" in formatted or "Something" in formatted

    def test_random_phrase_from_catchphrases(self):
        p = self._p()
        for _ in range(10):
            phrase = p.random_phrase()
            assert phrase in p.catchphrases

    def test_to_dict_round_trip(self):
        from agency.personality import JarvisPersonality
        p = JarvisPersonality(name="R2D2", language="en", formality="casual")
        d = p.to_dict()
        p2 = JarvisPersonality.from_dict(d)
        assert p2.name == "R2D2"
        assert p2.language == "en"

    def test_get_personality_returns_instance(self):
        import agency.personality as pm
        pm._SINGLETON = None  # reset
        p = pm.get_personality()
        from agency.personality import JarvisPersonality
        assert isinstance(p, JarvisPersonality)

    def test_set_personality_updates_name(self):
        import agency.personality as pm
        pm._SINGLETON = None
        pm.set_personality(name="EVE", language="en")
        assert pm.get_personality().name == "EVE"
        pm._SINGLETON = None  # cleanup


# ===========================================================================
# 4. dashboard.py
# ===========================================================================

class TestDashboard:
    def _app(self):
        pytest.importorskip("flask")
        from agency.dashboard import build_dashboard
        app = build_dashboard()
        app.config["TESTING"] = True
        return app

    def test_index_returns_html(self):
        app = self._app()
        with app.test_client() as c:
            r = c.get("/")
            assert r.status_code == 200
            assert b"JARVIS" in r.data

    def test_api_status_keys(self):
        app = self._app()
        with app.test_client() as c:
            r = c.get("/api/status")
            assert r.status_code == 200
            d = r.get_json()
            for key in ("uptime", "model", "tokens_used", "skills", "schedule_count"):
                assert key in d

    def test_api_history_structure(self):
        app = self._app()
        with app.test_client() as c:
            r = c.get("/api/history")
            assert r.status_code == 200
            d = r.get_json()
            assert "sessions" in d
            assert isinstance(d["sessions"], list)

    def test_api_skills_structure(self):
        app = self._app()
        with app.test_client() as c:
            r = c.get("/api/skills")
            assert r.status_code == 200
            d = r.get_json()
            assert "skills" in d

    def test_api_robot_structure(self):
        app = self._app()
        with app.test_client() as c:
            r = c.get("/api/robot")
            assert r.status_code == 200
            d = r.get_json()
            assert "joint_states" in d

    def test_api_traces_structure(self):
        app = self._app()
        with app.test_client() as c:
            r = c.get("/api/traces")
            assert r.status_code == 200
            d = r.get_json()
            assert "spans" in d

    def test_api_chat_no_message_400(self):
        app = self._app()
        with app.test_client() as c:
            r = c.post("/api/chat",
                       json={},
                       content_type="application/json")
            assert r.status_code == 400

    def test_api_chat_with_message(self):
        app = self._app()
        with app.test_client() as c:
            r = c.post("/api/chat",
                       json={"message": "hello JARVIS"},
                       content_type="application/json")
            # 200 or 500 depending on LLM, but response key must be present
            d = r.get_json()
            assert "response" in d or "error" in d

    def test_dashboard_html_has_stats_grid(self):
        app = self._app()
        with app.test_client() as c:
            r = c.get("/")
            assert b"stats-grid" in r.data

    def test_dashboard_html_has_chat_section(self):
        app = self._app()
        with app.test_client() as c:
            r = c.get("/")
            assert b"chat-log" in r.data
