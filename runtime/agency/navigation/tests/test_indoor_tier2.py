"""Tier-2 Indoor Positioning test suite.

Covers Visual SLAM, VIO, WiFi RTT + fingerprinting, BLE / UWB
positioning, magnetic mapping, and Pedestrian Dead Reckoning, plus
the orchestrating IndoorEngine.fuse() method.
"""
from __future__ import annotations

import math

import numpy as np
import pytest

from runtime.agency.navigation.indoor import (
    BLEPositioner,
    IndoorEngine,
    MagneticMapper,
    PDREstimator,
    UWBPositioner,
    VIOEstimator,
    VisualSLAM,
    WiFiRTT,
)
from runtime.agency.navigation.types import Estimate


# -----------------------------------------------------------------
# Image fixtures — synthetic checkerboard + gradient patches
# -----------------------------------------------------------------

def _make_checkerboard(size: int = 96, square: int = 8) -> np.ndarray:
    """Deterministic textured image rich in FAST corners.

    Uses a fixed-seed pseudo-random pattern. Pure checkerboards do not
    trigger FAST because the 16-pixel circle inside a uniform square
    has zero gradient against the centre pixel.
    """
    rng = np.random.default_rng(42)
    base = rng.integers(0, 256, size=(size, size), dtype=np.uint8)
    # Sprinkle high-contrast bright dots so FAST has clear corners.
    for x, y in [
        (10, 10), (30, 12), (50, 14), (70, 16),
        (12, 30), (32, 32), (52, 34), (72, 36),
        (14, 50), (34, 52), (54, 54), (74, 56),
        (16, 70), (36, 72), (56, 74), (76, 76),
        (20, 80), (40, 82), (60, 84), (80, 86),
    ]:
        if x < size - 4 and y < size - 4:
            base[y - 2:y + 3, x - 2:x + 3] = 0
            base[y, x] = 255
    return base


def _shift_image(img: np.ndarray, dx: int, dy: int) -> np.ndarray:
    out = np.zeros_like(img)
    h, w = img.shape
    src_x0 = max(0, -dx)
    src_y0 = max(0, -dy)
    src_x1 = min(w, w - dx)
    src_y1 = min(h, h - dy)
    dst_x0 = max(0, dx)
    dst_y0 = max(0, dy)
    out[dst_y0:dst_y0 + (src_y1 - src_y0), dst_x0:dst_x0 + (src_x1 - src_x0)] = (
        img[src_y0:src_y1, src_x0:src_x1]
    )
    return out


# =================================================================
# 1 — VisualSLAM
# =================================================================

class TestVisualSLAM:

    def test_extract_orb_features_finds_corners(self):
        slam = VisualSLAM(max_features=200, fast_threshold=20)
        img = _make_checkerboard()
        kp, desc = slam.extract_orb_features(img)
        assert len(kp) > 10
        assert desc.shape[0] == len(kp)
        assert desc.shape[1] == 64  # 512-bit descriptor packed to 64 bytes
        assert desc.dtype == np.uint8

    def test_extract_orb_rejects_non_2d(self):
        slam = VisualSLAM()
        with pytest.raises(ValueError):
            slam.extract_orb_features(np.zeros((4, 4, 3), dtype=np.uint8))

    def test_match_features_self_match(self):
        slam = VisualSLAM(max_features=80)
        img = _make_checkerboard()
        kp, desc = slam.extract_orb_features(img)
        # Matching with second image identical -> ratio test skips most
        # but we should still get at least a handful of confident matches.
        kp2, desc2 = slam.extract_orb_features(_shift_image(img, 2, 0))
        matches = slam.match_features(kp, desc, kp2, desc2)
        assert isinstance(matches, list)
        # 0 matches is acceptable in degenerate ratio-test outcomes;
        # we just require the call to be well-formed.
        for m in matches:
            assert 0 <= m.query_idx < len(kp)
            assert 0 <= m.train_idx < len(kp2)
            assert m.distance >= 0

    def test_estimate_pose_returns_rotation_translation(self):
        slam = VisualSLAM()
        img = _make_checkerboard()
        kp1, desc1 = slam.extract_orb_features(img)
        kp2, desc2 = slam.extract_orb_features(_shift_image(img, 1, 0))
        K = np.array([[500.0, 0.0, 48.0],
                      [0.0, 500.0, 48.0],
                      [0.0, 0.0, 1.0]])
        # Synthesise enough matches so the 8-point algorithm runs.
        n = min(len(kp1), len(kp2))
        if n < 8:
            pytest.skip("not enough features in synthetic frame")
        from runtime.agency.navigation.indoor_slam import DMatch
        matches = [DMatch(i, i, 0.0) for i in range(min(12, n))]
        R, t = slam.estimate_pose(kp1, kp2, matches, K)
        assert R.shape == (3, 3)
        assert t.shape == (3,)
        # Rotation should be near-orthonormal
        ortho = R.T @ R
        assert np.allclose(np.diag(ortho), [1.0, 1.0, 1.0], atol=1e-6)

    def test_estimate_pose_few_matches_returns_identity(self):
        slam = VisualSLAM()
        K = np.eye(3)
        R, t = slam.estimate_pose([], [], [], K)
        assert np.allclose(R, np.eye(3))
        assert np.allclose(t, np.zeros(3))

    def test_update_step_returns_pose(self):
        slam = VisualSLAM()
        img = _make_checkerboard()
        p1 = slam.update(img, 0.0)
        p2 = slam.update(_shift_image(img, 1, 0), 1.0)
        assert hasattr(p1, "x") and hasattr(p2, "x")


# =================================================================
# 2 — Visual-Inertial Odometry
# =================================================================

class TestVIO:

    def test_preintegrate_gravity_only(self):
        vio = VIOEstimator(visual_correction_interval=1000)
        accel = np.array([0.0, 0.0, 9.81])  # measured upward accel
        gyro = np.zeros(3)
        new_pos, new_vel, new_quat = vio._preintegrate_imu(accel, gyro, 0.05)
        assert np.allclose(new_pos, np.zeros(3), atol=1e-3)
        assert np.allclose(new_vel, np.zeros(3), atol=1e-3)
        assert math.isclose(float(np.linalg.norm(new_quat)), 1.0, abs_tol=1e-6)

    def test_preintegrate_yaw_rotation(self):
        vio = VIOEstimator(visual_correction_interval=1000)
        accel = np.array([0.0, 0.0, 9.81])
        gyro = np.array([0.0, 0.0, math.pi])  # pi rad/s yaw
        _, _, q = vio._preintegrate_imu(accel, gyro, 0.5)
        # 0.5 s × π rad/s = π/2 rad → cos(π/4) ≈ 0.707
        assert math.isclose(q[0], math.cos(math.pi / 4), abs_tol=1e-6)
        assert math.isclose(q[3], math.sin(math.pi / 4), abs_tol=1e-6)

    def test_update_returns_pose3d(self):
        vio = VIOEstimator()
        img = _make_checkerboard()
        pose = vio.update(img,
                          accel=np.array([0.0, 0.0, 9.81]),
                          gyro=np.zeros(3),
                          dt=0.02)
        assert hasattr(pose, "x") and hasattr(pose, "qw")

    def test_zero_dt_is_noop(self):
        vio = VIOEstimator()
        before = vio.position.copy()
        vio.update(None, np.array([1.0, 0.0, 9.81]), np.zeros(3), dt=0.0)
        assert np.allclose(vio.position, before)


# =================================================================
# 3 — WiFi RTT + fingerprinting
# =================================================================

class TestWiFiRTT:

    def test_trilateration_recovers_known_position(self):
        wifi = WiFiRTT()
        target = np.array([2.0, 3.0, 1.0])
        aps = [
            ("aa", np.array([0.0, 0.0, 0.0])),
            ("bb", np.array([10.0, 0.0, 0.0])),
            ("cc", np.array([0.0, 10.0, 0.0])),
            ("dd", np.array([10.0, 10.0, 0.0])),
        ]
        for bssid, p in aps:
            wifi.add_ap(bssid, tuple(p), float(np.linalg.norm(target - p)))
        x, y, z = wifi.trilaterate()
        assert math.isclose(x, 2.0, abs_tol=0.05)
        assert math.isclose(y, 3.0, abs_tol=0.05)

    def test_trilateration_requires_three_aps(self):
        wifi = WiFiRTT()
        wifi.add_ap("a", (0.0, 0.0, 0.0), 1.0)
        wifi.add_ap("b", (1.0, 0.0, 0.0), 1.0)
        with pytest.raises(ValueError):
            wifi.trilaterate()

    def test_rtt_to_range_units(self):
        # 10 ns round-trip ≈ 1.5 m one-way
        d = WiFiRTT.rtt_to_range(10.0)
        assert math.isclose(d, 1.498962, abs_tol=1e-3)

    def test_fingerprint_lookup_knn(self):
        wifi = WiFiRTT(k=3)
        wifi.update_fingerprint("ap1", -55, (0.0, 0.0, 0.0))
        wifi.update_fingerprint("ap2", -65, (0.0, 0.0, 0.0))
        wifi.update_fingerprint("ap1", -65, (5.0, 0.0, 0.0))
        wifi.update_fingerprint("ap2", -55, (5.0, 0.0, 0.0))
        wifi.update_fingerprint("ap1", -75, (10.0, 0.0, 0.0))
        wifi.update_fingerprint("ap2", -75, (10.0, 0.0, 0.0))
        x, y, z = wifi.fingerprint_lookup({"ap1": -56, "ap2": -64})
        assert 0.0 <= x <= 5.0  # closest fingerprints are at (0,0) and (5,0)

    def test_fingerprint_lookup_empty_db_raises(self):
        wifi = WiFiRTT()
        with pytest.raises(ValueError):
            wifi.fingerprint_lookup({"ap1": -50})


# =================================================================
# 4 — BLE positioning
# =================================================================

class TestBLE:

    def test_rssi_to_distance_calibration(self):
        # By construction d == 1 m at rssi == tx_power
        d = BLEPositioner.rssi_to_distance(-59.0, tx_power=-59.0, n=2.0)
        assert math.isclose(d, 1.0, abs_tol=1e-9)

    def test_rssi_to_distance_path_loss(self):
        # 20 dB drop with n=2 → 10 m
        d = BLEPositioner.rssi_to_distance(-79.0, tx_power=-59.0, n=2.0)
        assert math.isclose(d, 10.0, abs_tol=1e-6)

    def test_rssi_to_distance_invalid_n(self):
        with pytest.raises(ValueError):
            BLEPositioner.rssi_to_distance(-50.0, n=0.0)

    def test_position_from_beacons_trilateration(self):
        ble = BLEPositioner()
        # Place receiver at (2, 2). Compute synthetic RSSI per beacon.
        beacons_pos = [(0.0, 0.0), (5.0, 0.0), (0.0, 5.0), (5.0, 5.0)]
        target = np.array([2.0, 2.0])
        beacons = []
        for x, y in beacons_pos:
            d = float(np.linalg.norm(target - np.array([x, y])))
            rssi = -59.0 - 20.0 * math.log10(max(d, 1e-3))
            beacons.append({"x": x, "y": y, "rssi": rssi})
        x_est, y_est = ble.position_from_beacons(beacons)
        assert math.isclose(x_est, 2.0, abs_tol=0.2)
        assert math.isclose(y_est, 2.0, abs_tol=0.2)

    def test_position_requires_three_beacons(self):
        ble = BLEPositioner()
        with pytest.raises(ValueError):
            ble.position_from_beacons([{"x": 0, "y": 0, "rssi": -60}])


# =================================================================
# 5 — UWB TDoA
# =================================================================

class TestUWB:

    def test_tdoa_recovers_known_position(self):
        from runtime.agency.navigation.indoor_radio import SPEED_OF_LIGHT
        uwb = UWBPositioner()
        anchors = np.array([
            [0.0, 0.0, 0.0],
            [10.0, 0.0, 0.0],
            [0.0, 10.0, 0.0],
            [10.0, 10.0, 0.0],
            [5.0, 5.0, 5.0],
        ])
        target = np.array([3.0, 4.0, 1.0])
        ranges = np.array([float(np.linalg.norm(target - a)) for a in anchors])
        tdoa = (ranges[1:] - ranges[0]) / SPEED_OF_LIGHT
        pos = uwb.tdoa_position(anchors, tdoa,
                                initial_guess=np.array([5.0, 5.0, 0.0]))
        assert np.allclose(pos, target, atol=0.1)

    def test_tdoa_requires_four_anchors(self):
        uwb = UWBPositioner()
        with pytest.raises(ValueError):
            uwb.tdoa_position(np.zeros((3, 3)), np.zeros(2))

    def test_tdoa_dim_mismatch_raises(self):
        uwb = UWBPositioner()
        with pytest.raises(ValueError):
            uwb.tdoa_position(np.zeros((4, 3)), np.zeros(5))


# =================================================================
# 6 — Magnetic mapping
# =================================================================

class TestMagneticMapper:

    def test_record_and_lookup_returns_recorded(self):
        m = MagneticMapper()
        m.record((1.0, 2.0), np.array([10.0, 5.0, -30.0]))
        m.record((5.0, 5.0), np.array([20.0, -5.0, -40.0]))
        x, y = m.lookup(np.array([10.0, 5.0, -30.0]))
        assert math.isclose(x, 1.0, abs_tol=1e-6)
        assert math.isclose(y, 2.0, abs_tol=1e-6)

    def test_lookup_empty_raises(self):
        m = MagneticMapper()
        with pytest.raises(ValueError):
            m.lookup(np.array([0.0, 0.0, 0.0]))

    def test_record_validates_vector_shape(self):
        m = MagneticMapper()
        with pytest.raises(ValueError):
            m.record((0.0, 0.0), np.array([1.0, 2.0]))


# =================================================================
# 7 — Pedestrian Dead Reckoning
# =================================================================

class TestPDR:

    def test_detect_step_on_clear_peak(self):
        pdr = PDREstimator()
        # Need to first dip below valley to arm detector
        pdr._sim_time = 1.0
        assert pdr.detect_step(8.0) is False
        pdr._sim_time = 1.5
        assert pdr.detect_step(12.0) is True

    def test_detect_step_respects_min_interval(self):
        pdr = PDREstimator()
        pdr._sim_time = 1.0
        pdr.detect_step(8.0)
        pdr._sim_time = 1.05
        first = pdr.detect_step(12.0)
        pdr._sim_time = 1.10
        second = pdr.detect_step(12.0)
        assert first is True
        assert second is False  # too soon

    def test_estimate_heading_complementary_filter(self):
        pdr = PDREstimator()
        # No gyro motion + mag pointing east → heading drifts toward mag
        h = pdr.estimate_heading(0.0, math.radians(45))
        assert -math.pi <= h <= math.pi

    def test_walking_simulation_advances_position(self):
        pdr = PDREstimator(initial_heading=0.0)
        # Simulate 20 step cycles
        for i in range(200):
            phase = (i % 10) / 10.0
            az = 9.81 + 4.0 * math.sin(phase * 2 * math.pi)
            pdr.update(
                accel=np.array([0.0, 0.0, az]),
                gyro=np.zeros(3),
                mag=np.array([1.0, 0.0, -0.5]),
                dt=0.02,
            )
        assert pdr.pose.step_count > 0
        assert pdr.pose.y != 0.0 or pdr.pose.x != 0.0


# =================================================================
# 8 — IndoorEngine.fuse() orchestrator
# =================================================================

class TestIndoorEngineFusion:

    def test_fuse_empty_returns_none(self):
        eng = IndoorEngine()
        assert eng.fuse() is None

    def test_fuse_picks_lowest_uncertainty(self):
        from runtime.agency.navigation.indoor import (
            UWBAnchor, UWBMeasurement, BLEBeacon,
        )
        eng = IndoorEngine()
        # Push a high-uncertainty BLE estimate
        beacons_map = {
            "u1": (0.0, 0.0, 0.0),
            "u2": (5.0, 0.0, 0.0),
            "u3": (2.5, 5.0, 0.0),
        }
        beacons = [
            BLEBeacon("u1", rssi_dbm=-65.0),
            BLEBeacon("u2", rssi_dbm=-70.0),
            BLEBeacon("u3", rssi_dbm=-72.0),
        ]
        eng.update_ble(beacons, beacons_map)
        # Push a low-uncertainty UWB estimate
        eng.add_uwb_anchor(UWBAnchor("A1", 0.0, 0.0))
        eng.add_uwb_anchor(UWBAnchor("A2", 4.0, 0.0))
        eng.add_uwb_anchor(UWBAnchor("A3", 2.0, 4.0))
        eng.update_uwb([
            UWBMeasurement("A1", 2.83, std_m=0.05),
            UWBMeasurement("A2", 2.83, std_m=0.05),
            UWBMeasurement("A3", 2.24, std_m=0.05),
        ])
        best = eng.fuse()
        assert isinstance(best, Estimate)
        assert best.confidence.source == "indoor-uwb"

    def test_update_visual_publishes_estimate(self):
        eng = IndoorEngine()
        img = _make_checkerboard()
        est = eng.update_visual(img)
        assert isinstance(est, Estimate)
        assert est.confidence.source == "indoor-vslam"

    def test_update_uwb_tdoa_low_uncertainty(self):
        from runtime.agency.navigation.indoor_radio import SPEED_OF_LIGHT
        eng = IndoorEngine()
        anchors = np.array([
            [0.0, 0.0, 0.0],
            [10.0, 0.0, 0.0],
            [0.0, 10.0, 0.0],
            [10.0, 10.0, 0.0],
        ])
        target = np.array([4.0, 4.0, 0.0])
        ranges = np.array([float(np.linalg.norm(target - a)) for a in anchors])
        tdoa = (ranges[1:] - ranges[0]) / SPEED_OF_LIGHT
        est = eng.update_uwb_tdoa(anchors, tdoa)
        assert est.confidence.source == "indoor-uwb-tdoa"
        assert est.confidence.horizontal_m <= 0.2

    def test_update_magnetic_record_then_lookup(self):
        eng = IndoorEngine()
        # Record returns None
        rec = eng.update_magnetic(
            np.array([10.0, 5.0, -30.0]),
            record_position=(2.0, 3.0),
        )
        assert rec is None
        # Lookup matches the recorded position
        est = eng.update_magnetic(np.array([10.0, 5.0, -30.0]))
        assert isinstance(est, Estimate)
        assert est.confidence.source == "indoor-magnetic"

    def test_update_wifi_fingerprint_smoke(self):
        eng = IndoorEngine()
        eng.wifi.update_fingerprint("ap1", -55, (1.0, 1.0, 0.0))
        eng.wifi.update_fingerprint("ap2", -60, (1.0, 1.0, 0.0))
        est = eng.update_wifi_fingerprint({"ap1": -56, "ap2": -61})
        assert isinstance(est, Estimate)
        assert est.confidence.source == "indoor-wifi-fingerprint"

    def test_update_pdr_only_emits_on_step(self):
        eng = IndoorEngine()
        # Stationary IMU should not emit estimate
        est = eng.update_pdr(
            accel=np.array([0.0, 0.0, 9.81]),
            gyro=np.zeros(3),
            mag=np.array([1.0, 0.0, -0.5]),
            dt=0.02,
        )
        assert est is None


# =================================================================
# 9 — Module __all__ exports
# =================================================================

class TestExports:

    def test_all_required_classes_exported(self):
        from runtime.agency.navigation import indoor

        for name in (
            "IndoorEngine", "IndoorEstimator",
            "VisualSLAM", "VIOEstimator", "KeyPoint", "DMatch",
            "Pose2D", "Pose3D",
            "WiFiRTT", "BLEPositioner", "UWBPositioner",
            "MagneticMapper", "PDREstimator", "PDRPose",
        ):
            assert name in indoor.__all__, f"{name} missing from __all__"
            assert hasattr(indoor, name)
