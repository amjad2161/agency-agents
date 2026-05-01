"""Tests for agency.multi_agent_orchestrator — MultiAgentOrchestrator."""

from __future__ import annotations

import pytest

from agency.multi_agent_orchestrator import (
    AgentMessage,
    AgentRole,
    MultiAgentOrchestrator,
)


class TestAgentRoleEnum:
    def test_values_are_strings(self):
        for role in AgentRole:
            assert isinstance(role.value, str)

    def test_all_roles_present(self):
        values = {r.value for r in AgentRole}
        assert {"planner", "executor", "critic", "coordinator"}.issubset(values)


class TestAgentMessage:
    def test_to_dict_has_required_keys(self):
        msg = AgentMessage(role=AgentRole.PLANNER, content="plan it")
        d = msg.to_dict()
        assert set(d.keys()) == {"role", "content", "ts"}

    def test_ts_is_iso_format(self):
        msg = AgentMessage(role=AgentRole.CRITIC, content="critique")
        assert "T" in msg.ts or "-" in msg.ts  # basic ISO-8601 check


class TestMultiAgentOrchestrator:
    # ------------------------------------------------------------------
    # new_session
    # ------------------------------------------------------------------

    def test_new_session_returns_string(self):
        orch = MultiAgentOrchestrator()
        sid = orch.new_session()
        assert isinstance(sid, str) and len(sid) > 0

    def test_multiple_sessions_are_unique(self):
        orch = MultiAgentOrchestrator()
        ids = {orch.new_session() for _ in range(5)}
        assert len(ids) == 5

    # ------------------------------------------------------------------
    # plan / execute_step / critique
    # ------------------------------------------------------------------

    def test_plan_returns_string(self):
        orch = MultiAgentOrchestrator()
        sid = orch.new_session()
        result = orch.plan("deploy a service", sid)
        assert isinstance(result, str) and len(result) > 0

    def test_plan_mock_contains_steps(self):
        orch = MultiAgentOrchestrator(mock=True)
        sid = orch.new_session()
        plan = orch.plan("do something", sid)
        assert "Step" in plan

    def test_execute_step_echoes_step(self):
        orch = MultiAgentOrchestrator()
        sid = orch.new_session()
        result = orch.execute_step("Step 1: Analyze", sid)
        assert "Step 1" in result or "Analyze" in result or "Executed" in result

    def test_critique_returns_quality_info(self):
        orch = MultiAgentOrchestrator()
        sid = orch.new_session()
        feedback = orch.critique("all steps done", sid)
        assert isinstance(feedback, str) and len(feedback) > 0

    # ------------------------------------------------------------------
    # run_pipeline
    # ------------------------------------------------------------------

    def test_run_pipeline_returns_all_keys(self):
        orch = MultiAgentOrchestrator()
        result = orch.run_pipeline("build a REST API")
        for key in ("session_id", "goal", "plan", "execution", "critique", "status"):
            assert key in result

    def test_run_pipeline_status_completed(self):
        orch = MultiAgentOrchestrator()
        result = orch.run_pipeline("automate deployment")
        assert result["status"] == "completed"

    def test_run_pipeline_goal_preserved(self):
        orch = MultiAgentOrchestrator()
        goal = "create a dashboard"
        result = orch.run_pipeline(goal)
        assert result["goal"] == goal

    # ------------------------------------------------------------------
    # get_session
    # ------------------------------------------------------------------

    def test_get_session_contains_messages(self):
        orch = MultiAgentOrchestrator()
        result = orch.run_pipeline("analyse logs")
        messages = orch.get_session(result["session_id"])
        assert len(messages) >= 3  # coordinator + planner + at least one executor + critic

    def test_get_session_unknown_id_returns_empty(self):
        orch = MultiAgentOrchestrator()
        assert orch.get_session("nonexistent-id") == []

    def test_get_session_messages_are_dicts(self):
        orch = MultiAgentOrchestrator()
        result = orch.run_pipeline("test goal")
        for msg in orch.get_session(result["session_id"]):
            assert isinstance(msg, dict)
            assert "role" in msg and "content" in msg
