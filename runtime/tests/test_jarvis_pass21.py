"""Pass 21 — Code Gen REPL, Self-Improvement, ROS2 Bridge, Balance Controller, Emotions.

35 tests covering all 5 new modules.  Zero external dependencies required —
uses MOCK backends for robotics and no real LLM / ROS2 installation.

Run:
    cd runtime
    PYTHONPYCACHEPREFIX=/tmp/fresh_pycache \\
    python -m pytest tests/test_jarvis_pass21.py -q --tb=short --timeout=60
"""

from __future__ import annotations

import pathlib
import sys
import tempfile

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))


# ===========================================================================
# 1. code_repl.py — CodeREPL
# ===========================================================================

class TestREPLResult:
    def test_ok_when_no_error(self):
        from agency.code_repl import REPLResult
        r = REPLResult(stdout="hi")
        assert r.ok is True

    def test_not_ok_when_error(self):
        from agency.code_repl import REPLResult
        r = REPLResult(error="ZeroDivisionError: division by zero")
        assert r.ok is False

    def test_not_ok_when_timed_out(self):
        from agency.code_repl import REPLResult
        r = REPLResult(timed_out=True)
        assert r.ok is False

    def test_duration_ms_defaults_to_zero(self):
        from agency.code_repl import REPLResult
        r = REPLResult()
        assert r.duration_ms == 0.0


class TestCodeREPL:
    def test_simple_expression(self):
        from agency.code_repl import CodeREPL
        repl = CodeREPL()
        r = repl.execute("1 + 1")
        assert r.return_value == 2
        assert r.ok

    def test_assignment_and_recall(self):
        from agency.code_repl import CodeREPL
        repl = CodeREPL()
        repl.execute("x = 42")
        r = repl.execute("x")
        assert r.return_value == 42

    def test_namespace_persists_across_calls(self):
        from agency.code_repl import CodeREPL
        repl = CodeREPL()
        repl.execute("total = 0")
        for i in range(5):
            repl.execute(f"total += {i}")
        r = repl.execute("total")
        assert r.return_value == 10

    def test_stdout_captured(self):
        from agency.code_repl import CodeREPL
        repl = CodeREPL()
        r = repl.execute("print('hello world')")
        assert "hello world" in r.stdout

    def test_syntax_error_returns_error_result(self):
        from agency.code_repl import CodeREPL
        repl = CodeREPL()
        r = repl.execute("def broken(")
        assert r.ok is False
        assert r.error is not None

    def test_runtime_error_captured(self):
        from agency.code_repl import CodeREPL
        repl = CodeREPL()
        r = repl.execute("1 / 0")
        assert r.ok is False
        assert "ZeroDivisionError" in (r.error or "")

    def test_blocked_import_in_sandbox(self):
        from agency.code_repl import CodeREPL
        repl = CodeREPL(trust_mode="off")
        r = repl.execute("import os")
        assert r.ok is False or "blocked" in (r.error or "").lower() or "ImportError" in (r.error or "")

    def test_math_available_by_default(self):
        from agency.code_repl import CodeREPL
        repl = CodeREPL()
        r = repl.execute("math.pi")
        assert abs(r.return_value - 3.14159) < 0.001

    def test_reset_clears_namespace(self):
        from agency.code_repl import CodeREPL
        repl = CodeREPL()
        repl.execute("secret = 'hello'")
        repl.reset()
        r = repl.execute("secret")
        assert r.ok is False  # NameError after reset

    def test_history_records_calls(self):
        from agency.code_repl import CodeREPL
        repl = CodeREPL()
        repl.execute("1 + 1")
        repl.execute("2 + 2")
        assert len(repl.history) == 2

    def test_empty_code_returns_ok(self):
        from agency.code_repl import CodeREPL
        repl = CodeREPL()
        r = repl.execute("   ")
        assert r.ok

    def test_multiline_exec(self):
        from agency.code_repl import CodeREPL
        repl = CodeREPL()
        code = "result = 0\nfor i in range(10):\n    result += i"
        r = repl.execute(code)
        assert r.ok
        r2 = repl.execute("result")
        assert r2.return_value == 45

    def test_namespace_property_is_copy(self):
        from agency.code_repl import CodeREPL
        repl = CodeREPL()
        repl.execute("a = 1")
        ns = repl.namespace
        ns["a"] = 999
        r = repl.execute("a")
        assert r.return_value == 1   # original unchanged

    def test_generate_and_run_fallback(self):
        """Without LLM, generate_and_run should still return a REPLResult."""
        from agency.code_repl import CodeREPL
        repl = CodeREPL()
        r = repl.generate_and_run("print hello world")
        # Should not raise; result is a REPLResult regardless of LLM availability
        from agency.code_repl import REPLResult
        assert isinstance(r, REPLResult)


# ===========================================================================
# 2. self_improver.py — SelfImprover
# ===========================================================================

class TestImprovementSuggestion:
    def test_to_dict_has_required_keys(self):
        from agency.self_improver import ImprovementSuggestion
        s = ImprovementSuggestion(keyword="kubectl", slug="devops", weight=6.0, reason="test")
        d = s.to_dict()
        for k in ("keyword", "slug", "weight", "reason", "created_at"):
            assert k in d

    def test_default_created_at_is_iso_string(self):
        from agency.self_improver import ImprovementSuggestion
        s = ImprovementSuggestion(keyword="x", slug="y", weight=5.0, reason="r")
        assert "T" in s.created_at  # ISO 8601 contains T separator


class TestSelfImprover:
    def test_instantiation(self):
        from agency.self_improver import SelfImprover
        imp = SelfImprover()
        assert imp is not None

    def test_analyze_slow_routes_returns_list(self):
        from agency.self_improver import SelfImprover
        imp = SelfImprover()
        result = imp.analyze_slow_routes()
        assert isinstance(result, list)

    def test_suggest_boost_keys_devops(self):
        from agency.self_improver import SelfImprover
        imp = SelfImprover()
        suggestions = imp.suggest_boost_keys("devops")
        assert len(suggestions) > 0
        assert all(s.slug == "devops" for s in suggestions)

    def test_suggest_boost_keys_unknown_slug_fallback(self):
        from agency.self_improver import SelfImprover
        imp = SelfImprover()
        suggestions = imp.suggest_boost_keys("unknown-skill-xyz")
        # Should return something via generic token extraction or empty list
        assert isinstance(suggestions, list)

    def test_auto_improve_dry_run(self):
        from agency.self_improver import SelfImprover
        imp = SelfImprover()
        suggestions = imp.auto_improve(dry_run=True)
        assert isinstance(suggestions, list)

    def test_improvement_report_returns_list(self):
        from agency.self_improver import SelfImprover
        import tempfile
        from pathlib import Path
        log = Path(tempfile.mktemp(suffix=".jsonl"))
        imp = SelfImprover(log_path=log)
        report = imp.improvement_report()
        assert isinstance(report, list)

    def test_apply_suggestion_missing_brain(self):
        from agency.self_improver import SelfImprover, ImprovementSuggestion
        from pathlib import Path
        imp = SelfImprover(brain_path=Path("/nonexistent/jarvis_brain.py"))
        s = ImprovementSuggestion(keyword="test", slug="test", weight=5.0, reason="x")
        result = imp.apply_suggestion(s)
        assert result is False


# ===========================================================================
# 3. robotics/ros2_bridge.py — MockROS2Bridge
# ===========================================================================

class TestMockROS2Bridge:
    def test_is_not_available(self):
        from agency.robotics.ros2_bridge import MockROS2Bridge
        b = MockROS2Bridge()
        assert b.is_available() is False

    def test_publish_joint_command_recorded(self):
        from agency.robotics.ros2_bridge import MockROS2Bridge
        b = MockROS2Bridge()
        b.publish_joint_command("left_knee", 0.5)
        cmds = b.get_published_commands()
        assert len(cmds) == 1
        assert cmds[0].joint_name == "left_knee"
        assert cmds[0].value == pytest.approx(0.5)

    def test_publish_velocity_recorded(self):
        from agency.robotics.ros2_bridge import MockROS2Bridge
        b = MockROS2Bridge()
        b.publish_velocity(0.3, 0.1)
        vels = b.get_published_velocities()
        assert len(vels) == 1
        assert vels[0].linear_x == pytest.approx(0.3)

    def test_subscribe_joint_states_and_inject(self):
        from agency.robotics.ros2_bridge import MockROS2Bridge, JointState
        b = MockROS2Bridge()
        received = []
        b.subscribe_joint_states(received.append)
        b.inject_joint_state(JointState(joint_name="left_knee", position=1.2))
        assert len(received) == 1
        assert received[0].joint_name == "left_knee"

    def test_status_dict(self):
        from agency.robotics.ros2_bridge import MockROS2Bridge
        b = MockROS2Bridge()
        s = b.status()
        assert s["available"] is False
        assert s["backend"] == "mock"

    def test_clear_resets_state(self):
        from agency.robotics.ros2_bridge import MockROS2Bridge
        b = MockROS2Bridge()
        b.publish_joint_command("neck_yaw", 0.1)
        b.clear()
        assert len(b.get_published_commands()) == 0

    def test_get_ros2_bridge_returns_mock(self):
        from agency.robotics.ros2_bridge import get_ros2_bridge, MockROS2Bridge
        bridge = get_ros2_bridge()
        # ROS2 not installed in CI → must return MockROS2Bridge
        assert isinstance(bridge, MockROS2Bridge)


# ===========================================================================
# 4. robotics/balance.py — BalanceController
# ===========================================================================

class TestVector3:
    def test_add(self):
        from agency.robotics.balance import Vector3
        v = Vector3(1, 2, 3) + Vector3(4, 5, 6)
        assert v.x == 5 and v.y == 7 and v.z == 9

    def test_mul(self):
        from agency.robotics.balance import Vector3
        v = Vector3(1, 2, 3) * 2
        assert v.x == 2 and v.y == 4 and v.z == 6

    def test_norm(self):
        from agency.robotics.balance import Vector3
        v = Vector3(3, 4, 0)
        assert abs(v.norm() - 5.0) < 1e-9

    def test_to_tuple(self):
        from agency.robotics.balance import Vector3
        assert Vector3(1, 2, 3).to_tuple() == (1.0, 2.0, 3.0)


class TestCoMEstimator:
    def test_neutral_pose_com_near_centre(self):
        from agency.robotics.balance import CoMEstimator
        est = CoMEstimator()
        com = est.estimate({})  # all joints at 0
        # CoM x should be ≈ 0 for neutral pose
        assert abs(com.x) < 0.1

    def test_com_z_positive(self):
        from agency.robotics.balance import CoMEstimator
        com = CoMEstimator().estimate({})
        assert com.z > 0.5   # should be roughly at pelvis height


class TestZMPCalculator:
    def test_static_com_zmp_equals_com_x(self):
        from agency.robotics.balance import ZMPCalculator, Vector3
        zmp_calc = ZMPCalculator()
        com = Vector3(0.0, 0.0, 1.0)
        zmp = zmp_calc.calculate(com)
        # With zero acceleration, ZMP ≈ (com.x, com.y, 0)
        assert abs(zmp.x - com.x) < 0.001
        assert zmp.z == pytest.approx(0.0)

    def test_zmp_shifts_with_forward_accel(self):
        from agency.robotics.balance import ZMPCalculator, Vector3
        zmp_calc = ZMPCalculator()
        com = Vector3(0.0, 0.0, 1.0)
        accel = Vector3(x=1.0, y=0.0, z=0.0)   # forward accel
        zmp = zmp_calc.calculate(com, accel)
        assert zmp.x < 0.0   # ZMP shifts backwards


class TestPIDController:
    def test_proportional_only(self):
        from agency.robotics.balance import PIDController
        pid = PIDController(kp=2.0, ki=0.0, kd=0.0)
        out = pid.compute(error=1.0, dt=0.01)
        assert abs(out - 2.0) < 1e-6

    def test_output_clamping(self):
        from agency.robotics.balance import PIDController
        pid = PIDController(kp=100.0, output_min=-1.0, output_max=1.0)
        out = pid.compute(error=10.0, dt=0.01)
        assert out == pytest.approx(1.0)

    def test_reset_clears_integral(self):
        from agency.robotics.balance import PIDController
        pid = PIDController(kp=1.0, ki=1.0)
        pid.compute(error=1.0, dt=0.1)
        pid.reset()
        out = pid.compute(error=0.0, dt=0.1)
        assert abs(out) < 1e-6


class TestBalanceController:
    def test_stabilize_returns_control_action(self):
        from agency.robotics.balance import get_balance_controller, ControlAction
        ctrl = get_balance_controller()
        action = ctrl.stabilize()
        assert isinstance(action, ControlAction)

    def test_control_action_has_com_and_zmp(self):
        from agency.robotics.balance import get_balance_controller
        ctrl = get_balance_controller()
        action = ctrl.stabilize()
        assert action.com is not None
        assert action.zmp is not None

    def test_walking_pattern_returns_trajectories(self):
        from agency.robotics.balance import get_balance_controller, JointTrajectory
        ctrl = get_balance_controller()
        trajs = ctrl.walking_pattern_generator(n_steps=2)
        assert len(trajs) == 6  # 6 leg joints
        assert all(isinstance(t, JointTrajectory) for t in trajs)

    def test_trajectory_lengths_match(self):
        from agency.robotics.balance import get_balance_controller
        ctrl = get_balance_controller(dt=0.02)
        trajs = ctrl.walking_pattern_generator(n_steps=4, step_duration=0.4)
        expected_samples = int(0.4 / 0.02) * 4   # 80
        for t in trajs:
            assert len(t.timestamps) == expected_samples

    def test_status_returns_stable_key(self):
        from agency.robotics.balance import get_balance_controller
        ctrl = get_balance_controller()
        s = ctrl.status()
        assert "stable" in s
        assert "com" in s
        assert "zmp" in s


# ===========================================================================
# 5. emotion_state.py — JarvisEmotion
# ===========================================================================

class TestEmotionState:
    def test_all_six_states_exist(self):
        from agency.emotion_state import EmotionState
        names = {s.value for s in EmotionState}
        assert names == {"neutral", "curious", "focused", "alert", "satisfied", "uncertain"}

    def test_state_is_str_enum(self):
        from agency.emotion_state import EmotionState
        assert EmotionState.CURIOUS == "curious"


class TestJarvisEmotion:
    def test_initial_state_neutral(self):
        from agency.emotion_state import JarvisEmotion, EmotionState
        e = JarvisEmotion()
        assert e.current == EmotionState.NEUTRAL

    def test_question_trigger_curious(self):
        from agency.emotion_state import JarvisEmotion, EmotionState
        e = JarvisEmotion()
        e.update("what is the meaning of life?")
        assert e.current == EmotionState.CURIOUS

    def test_error_trigger_alert(self):
        from agency.emotion_state import JarvisEmotion, EmotionState
        e = JarvisEmotion()
        e.update("error occurred in module")
        assert e.current == EmotionState.ALERT

    def test_task_complete_trigger_satisfied(self):
        from agency.emotion_state import JarvisEmotion, EmotionState
        e = JarvisEmotion()
        e.update("task_complete")
        assert e.current == EmotionState.SATISFIED

    def test_phrase_returns_string(self):
        from agency.emotion_state import JarvisEmotion
        e = JarvisEmotion()
        p = e.phrase()
        assert isinstance(p, str)
        assert len(p) > 0

    def test_hebrew_phrase_for_curious(self):
        from agency.emotion_state import JarvisEmotion, EmotionState
        e = JarvisEmotion(language="he")
        e.current = EmotionState.CURIOUS
        phrases = ["מעניין!", "שאלה טובה", "זה מרתק", "אחקור את זה"]
        p = e.phrase()
        assert p in phrases

    def test_style_hint_returns_dict(self):
        from agency.emotion_state import JarvisEmotion
        e = JarvisEmotion()
        hint = e.style_hint()
        assert "state" in hint
        assert "confidence" in hint
        assert "urgency" in hint

    def test_alert_urgency_flag(self):
        from agency.emotion_state import JarvisEmotion, EmotionState
        e = JarvisEmotion()
        e.current = EmotionState.ALERT
        assert e.style_hint()["urgency"] is True

    def test_non_alert_not_urgent(self):
        from agency.emotion_state import JarvisEmotion, EmotionState
        e = JarvisEmotion()
        e.current = EmotionState.SATISFIED
        assert e.style_hint()["urgency"] is False

    def test_history_records_transitions(self):
        from agency.emotion_state import JarvisEmotion
        e = JarvisEmotion()
        e.update("error found")
        e.update("task complete")
        assert len(e.history) >= 1

    def test_reset_back_to_neutral(self):
        from agency.emotion_state import JarvisEmotion, EmotionState
        e = JarvisEmotion()
        e.update("error")
        e.reset()
        assert e.current == EmotionState.NEUTRAL
        assert e.history == []

    def test_update_count_increments(self):
        from agency.emotion_state import JarvisEmotion
        e = JarvisEmotion()
        e.update("hello")
        e.update("world")
        assert e.update_count == 2

    def test_english_phrase_fallback(self):
        from agency.emotion_state import JarvisEmotion, EmotionState
        e = JarvisEmotion(language="en")
        e.current = EmotionState.ALERT
        p = e.phrase(language="en")
        assert "Alert" in p or "Attention" in p or "Issue" in p

    def test_repr_contains_state(self):
        from agency.emotion_state import JarvisEmotion
        e = JarvisEmotion()
        assert "neutral" in repr(e)
