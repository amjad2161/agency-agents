"""Tier 6 AI/ML enhancement tests — RadioMapNet, SceneClassifier,
NeuralSLAMEstimator, LSTMPredictor, UncertaintyEstimator,
EnvironmentAdapter (Tier 6 methods), AIEnhancement.

Numpy-only. No torch / tensorflow / sklearn.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

try:
    from runtime.agency.navigation.ai_enhance import (  # type: ignore
        AIEnhancement,
        EnvironmentAdapter,
        LSTMPredictor,
        NeuralSLAMEstimator,
        Pose3D,
        RadioMapNet,
        SceneClassifier,
        UncertaintyEstimator,
    )
except ModuleNotFoundError:
    from agency.navigation.ai_enhance import (  # noqa: F401
    AIEnhancement,
    EnvironmentAdapter,
    LSTMPredictor,
    NeuralSLAMEstimator,
    Pose3D,
    RadioMapNet,
    SceneClassifier,
    UncertaintyEstimator,
)


# ---------------------------------------------------------------------------
# RadioMapNet
# ---------------------------------------------------------------------------

class TestRadioMapNet:
    def test_forward_shape_single(self):
        net = RadioMapNet(input_dim=8, hidden_dim=16, output_dim=2)
        x = np.zeros(8)
        out = net.forward(x)
        assert out.shape == (2,)

    def test_forward_shape_batch(self):
        net = RadioMapNet(input_dim=8, hidden_dim=16, output_dim=2)
        X = np.zeros((5, 8))
        out = net.forward(X)
        assert out.shape == (5, 2)

    def test_he_init_weights_finite(self):
        net = RadioMapNet(input_dim=8, hidden_dim=16, output_dim=2)
        assert np.all(np.isfinite(net.W1))
        assert np.all(np.isfinite(net.W2))
        # He std for fan_in=8 ≈ 0.5; sample std should be O(0.5)
        assert 0.1 < float(net.W1.std()) < 1.0

    def test_train_reduces_loss(self):
        rng = np.random.default_rng(0)
        # Synthetic linear-ish map: y = A x + b + noise
        A = rng.normal(size=(8, 2))
        b = rng.normal(size=2)
        X = rng.normal(size=(64, 8))
        y = X @ A + b + 0.01 * rng.normal(size=(64, 2))
        net = RadioMapNet(input_dim=8, hidden_dim=32, output_dim=2)
        history = net.train(X, y, epochs=80, lr=0.01, batch_size=8)
        assert len(history) == 80
        assert history[-1] < history[0] * 0.5  # loss halved at minimum

    def test_predict_returns_tuple(self):
        net = RadioMapNet(input_dim=8, hidden_dim=16, output_dim=2)
        x, y = net.predict(np.zeros(8))
        assert isinstance(x, float)
        assert isinstance(y, float)

    def test_predict_wrong_dim_raises(self):
        net = RadioMapNet(input_dim=8, hidden_dim=16, output_dim=2)
        with pytest.raises(ValueError):
            net.predict(np.zeros(5))


# ---------------------------------------------------------------------------
# SceneClassifier
# ---------------------------------------------------------------------------

class TestSceneClassifier:
    def test_outdoor_open_sky(self):
        sc = SceneClassifier()
        label = sc.classify({
            "gnss_count": 9, "wifi_count": 0, "cell_count": 1,
            "altitude_m": 50.0, "light_lux": 50000.0,
        })
        assert label in ("outdoor", "rural")
        assert 0.0 <= sc.confidence() <= 1.0

    def test_indoor_office(self):
        sc = SceneClassifier()
        label = sc.classify({
            "gnss_count": 0, "wifi_count": 12, "cell_count": 2,
            "altitude_m": 5.0, "light_lux": 400.0,
        })
        assert label == "indoor"

    def test_underground_negative_altitude(self):
        sc = SceneClassifier()
        label = sc.classify({
            "gnss_count": 0, "wifi_count": 0, "altitude_m": -25.0,
            "light_lux": 5.0, "pressure_hpa": 1015.0, "magnetic_uT": 90.0,
        })
        assert label == "underground"

    def test_underwater_pressure(self):
        sc = SceneClassifier()
        label = sc.classify({
            "depth_m": 12.0, "pressure_hpa": 2200.0,
            "gnss_count": 0, "wifi_count": 0, "light_lux": 1.0,
        })
        assert label == "underwater"

    def test_urban_dense(self):
        sc = SceneClassifier()
        label = sc.classify({
            "gnss_count": 5, "wifi_count": 20, "cell_count": 8,
            "altitude_m": 10.0, "light_lux": 30000.0,
        })
        assert label in ("urban", "outdoor")

    def test_confidence_in_range(self):
        sc = SceneClassifier()
        sc.classify({})  # all defaults
        c = sc.confidence()
        assert 0.0 <= c <= 1.0

    def test_label_in_known_set(self):
        sc = SceneClassifier()
        for feats in [{}, {"gnss_count": 10}, {"depth_m": 30}]:
            label = sc.classify(feats)
            assert label in SceneClassifier.LABELS


# ---------------------------------------------------------------------------
# NeuralSLAMEstimator
# ---------------------------------------------------------------------------

class TestNeuralSLAM:
    def test_encode_observation_shape_normalized(self):
        slam = NeuralSLAMEstimator()
        v = slam.encode_observation({"ax": 0.1, "gnss_count": 5})
        assert v.shape == (NeuralSLAMEstimator.FEATURE_DIM,)
        assert math.isclose(float(np.linalg.norm(v)), 1.0, abs_tol=1e-6) or float(np.linalg.norm(v)) == 0.0

    def test_update_pose_graph_returns_pose3d(self):
        slam = NeuralSLAMEstimator()
        v = slam.encode_observation({"ax": 0.1})
        p = slam.update_pose_graph(v, Pose3D())
        assert isinstance(p, Pose3D)

    def test_pose_advances_when_observation_changes(self):
        slam = NeuralSLAMEstimator()
        v1 = slam.encode_observation({"ax": 0.0})
        slam.update_pose_graph(v1, Pose3D())
        v2 = slam.encode_observation({"ax": 5.0, "gnss_count": 9, "wifi_count": 11})
        p2 = slam.update_pose_graph(v2)
        # New pose should differ from origin once a different observation lands
        assert (abs(p2.x) + abs(p2.y)) > 0.0

    def test_loop_closure_detects_repeat(self):
        slam = NeuralSLAMEstimator(loop_threshold=0.95)
        # Create 10 distinct frames
        for i in range(10):
            obs = slam.encode_observation({"ax": float(i), "gnss_count": i})
            slam.update_pose_graph(obs)
        # Re-observe frame 0 — should match keyframe 0
        repeat = slam.encode_observation({"ax": 0.0, "gnss_count": 0})
        found, idx = slam.detect_loop_closure(repeat)
        assert found is True
        assert idx == 0

    def test_loop_closure_skips_with_few_keyframes(self):
        slam = NeuralSLAMEstimator()
        v = slam.encode_observation({"ax": 1.0})
        slam.update_pose_graph(v)
        found, idx = slam.detect_loop_closure(v)
        assert found is False
        assert idx == -1

    def test_apply_loop_correction_blends(self):
        slam = NeuralSLAMEstimator()
        for i in range(6):
            slam.update_pose_graph(slam.encode_observation({"ax": float(i)}))
        # Force a known target by calling apply_loop_correction with idx=0
        current = Pose3D(x=10.0, y=10.0)
        target = slam._poses[0]
        corrected = slam.apply_loop_correction(0, current)
        assert math.isclose(corrected.x, 0.5 * (current.x + target.x), abs_tol=1e-9)
        assert math.isclose(corrected.y, 0.5 * (current.y + target.y), abs_tol=1e-9)


# ---------------------------------------------------------------------------
# LSTMPredictor
# ---------------------------------------------------------------------------

class TestLSTMPredictor:
    def test_forward_shape(self):
        lstm = LSTMPredictor(input_dim=4, hidden_dim=8, output_dim=2)
        out = lstm.forward(np.array([0.0, 0.0, 1.0, 0.0]))
        assert out.shape == (2,)

    def test_reset_state_zeros(self):
        lstm = LSTMPredictor(input_dim=4, hidden_dim=8, output_dim=2)
        lstm.forward(np.array([1.0, 1.0, 1.0, 1.0]))
        assert np.linalg.norm(lstm.h) > 0.0
        lstm.reset_state()
        assert np.allclose(lstm.h, 0.0)
        assert np.allclose(lstm.c, 0.0)

    def test_predict_trajectory_length(self):
        lstm = LSTMPredictor(input_dim=4, hidden_dim=8, output_dim=2)
        history = np.array([
            [0.0, 0.0, 1.0, 0.0],
            [1.0, 0.0, 1.0, 0.0],
            [2.0, 0.0, 1.0, 0.0],
        ])
        traj = lstm.predict_trajectory(history, steps=5)
        assert traj.shape == (5, 2)

    def test_predict_trajectory_finite(self):
        lstm = LSTMPredictor(input_dim=4, hidden_dim=16, output_dim=2)
        history = np.random.default_rng(0).normal(size=(8, 4))
        traj = lstm.predict_trajectory(history, steps=10)
        assert np.all(np.isfinite(traj))


# ---------------------------------------------------------------------------
# UncertaintyEstimator
# ---------------------------------------------------------------------------

class TestUncertaintyEstimator:
    def test_compute_position_uncertainty_mean(self):
        ue = UncertaintyEstimator()
        pts = [np.array([0.0, 0.0]), np.array([2.0, 4.0])]
        mean, cov = ue.compute_position_uncertainty(pts)
        assert np.allclose(mean, [1.0, 2.0])
        assert cov.shape == (2, 2)

    def test_compute_position_uncertainty_empty(self):
        ue = UncertaintyEstimator()
        mean, cov = ue.compute_position_uncertainty([])
        assert mean.shape == (2,)
        assert np.isinf(cov).any()

    def test_hdop_well_distributed(self):
        ue = UncertaintyEstimator()
        sats = [
            np.array([1.0, 0.0, 0.3]),
            np.array([-1.0, 0.0, 0.7]),
            np.array([0.0, 1.0, 0.4]),
            np.array([0.0, -1.0, 0.6]),
            np.array([0.5, 0.5, 0.9]),
        ]
        h = ue.hdop(sats)
        assert math.isfinite(h)
        assert h > 0.0

    def test_hdop_too_few_satellites(self):
        ue = UncertaintyEstimator()
        h = ue.hdop([np.array([1.0, 0.0, 0.5]), np.array([0.0, 1.0, 0.5])])
        assert math.isinf(h)

    def test_confidence_ellipse_isotropic(self):
        ue = UncertaintyEstimator()
        cov = np.eye(2) * 4.0  # std=2 along each axis
        sm, sn, ang = ue.confidence_ellipse(cov, confidence=0.95)
        # Chi-square 2-dof at 0.95 ≈ 5.991
        expected = math.sqrt(5.991 * 4.0)
        assert math.isclose(sm, expected, rel_tol=1e-3)
        assert math.isclose(sn, expected, rel_tol=1e-3)

    def test_confidence_ellipse_anisotropic_orientation(self):
        ue = UncertaintyEstimator()
        cov = np.array([[9.0, 0.0], [0.0, 1.0]])
        sm, sn, _ang = ue.confidence_ellipse(cov, confidence=0.95)
        assert sm > sn  # major axis > minor

    def test_reliability_score_range(self):
        ue = UncertaintyEstimator()
        sources = [
            {"quality": 1.0, "weight": 2.0, "valid": True},
            {"quality": 0.0, "weight": 1.0, "valid": True},
        ]
        r = ue.reliability_score(sources)
        # Weighted mean = (2*1 + 1*0) / 3 = 0.667
        assert math.isclose(r, 2.0 / 3.0, rel_tol=1e-6)

    def test_reliability_score_empty(self):
        ue = UncertaintyEstimator()
        assert ue.reliability_score([]) == 0.0


# ---------------------------------------------------------------------------
# EnvironmentAdapter (Tier 6 methods)
# ---------------------------------------------------------------------------

class TestEnvironmentAdapterTier6:
    def test_store_and_adapt_picks_closest(self):
        ea = EnvironmentAdapter()
        ea.store_reference("indoor", np.array([1.0, 0.0, 0.0]))
        ea.store_reference("outdoor", np.array([0.0, 1.0, 0.0]))
        match = ea.adapt(np.array([0.9, 0.1, 0.0]))
        assert match == "indoor"

    def test_adapt_empty_refs_returns_blank(self):
        ea = EnvironmentAdapter()
        assert ea.adapt(np.array([1.0, 0.0])) == ""

    def test_fine_tune_reduces_loss(self):
        net = RadioMapNet(input_dim=4, hidden_dim=8, output_dim=2)
        rng = np.random.default_rng(2)
        samples = [(rng.normal(size=4), rng.normal(size=2)) for _ in range(8)]
        ea = EnvironmentAdapter()
        history = ea.fine_tune(net, samples, epochs=20, lr=0.005)
        assert len(history) == 20
        assert history[-1] <= history[0] + 1e-6  # non-increasing on average


# ---------------------------------------------------------------------------
# AIEnhancement orchestration
# ---------------------------------------------------------------------------

class TestAIEnhancement:
    def test_enhance_returns_dict_with_keys(self):
        ai = AIEnhancement()
        out = ai.enhance(
            sensor_dict={"gnss_count": 6, "wifi_count": 0},
            position_estimate={"x": 1.0, "y": 2.0},
        )
        assert "scene" in out
        assert "scene_confidence" in out
        assert "slam_pose" in out
        assert "loop_closed" in out
        assert "uncertainty_ellipse_m" in out
        assert "reliability" in out

    def test_enhance_preserves_input_position(self):
        ai = AIEnhancement()
        out = ai.enhance(
            sensor_dict={"gnss_count": 6},
            position_estimate={"x": 3.0, "y": 4.0},
        )
        assert out["x"] == 3.0
        assert out["y"] == 4.0

    def test_enhance_handles_empty_inputs(self):
        ai = AIEnhancement()
        out = ai.enhance(sensor_dict={}, position_estimate={})
        assert out["scene"] in SceneClassifier.LABELS
        assert isinstance(out["loop_closed"], bool)

    def test_enhance_reliability_from_sources(self):
        ai = AIEnhancement()
        out = ai.enhance(
            sensor_dict={
                "gnss_count": 6,
                "sources": [
                    {"quality": 0.9, "weight": 1.0, "valid": True},
                    {"quality": 0.7, "weight": 1.0, "valid": True},
                ],
            },
            position_estimate={"x": 0.0, "y": 0.0},
        )
        assert 0.0 <= out["reliability"] <= 1.0
        assert out["reliability"] > 0.5
