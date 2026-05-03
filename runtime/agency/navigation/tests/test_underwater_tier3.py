"""GODSKILL Nav v11 — Tier 3 underwater tests."""
from __future__ import annotations

import math

import numpy as np
import pytest

from runtime.agency.navigation.underwater import (
    BathymetricMatcher,
    DVLNavigator,
    INSNavigator,
    LBLPositioner,
    Landmark,
    Pose3D,
    SonarSLAM,
    USBLPositioner,
    UnderwaterPositioner,
)


# ---------------------------------------------------------------------------
# INS
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_ins_static_gravity_compensated() -> None:
    """At rest with gravity-only specific force, position must not drift much."""
    ins = INSNavigator(schuler_damping=False)
    accel = np.array([0.0, 0.0, 9.80665])
    gyro = np.zeros(3)
    for _ in range(100):
        ins.update(accel, gyro, 0.01)
    assert abs(ins.pose.x) < 1e-6
    assert abs(ins.pose.y) < 1e-6
    assert abs(ins.pose.z) < 1e-6


@pytest.mark.unit
def test_ins_constant_acceleration_integration() -> None:
    """1 m/s^2 surge over 1 s should produce ~0.5 m forward."""
    ins = INSNavigator(schuler_damping=False)
    # Body x forward, z down. Specific force = a + g.
    accel = np.array([1.0, 0.0, 9.80665])
    for _ in range(100):
        ins.update(accel, np.zeros(3), 0.01)
    # Position is in nav frame; with yaw=0 nav-x == body-x.
    assert ins.pose.x == pytest.approx(0.5, rel=0.05)
    assert abs(ins.pose.y) < 1e-3
    assert abs(ins.pose.z) < 1e-3


@pytest.mark.unit
def test_ins_yaw_rotation_updates_dcm() -> None:
    """A pure yaw rate must rotate the DCM by the integrated angle."""
    ins = INSNavigator()
    yaw_rate = math.pi / 2.0  # rad/s, 90 deg/s
    for _ in range(100):
        ins.update(np.array([0.0, 0.0, 9.80665]), np.array([0.0, 0.0, yaw_rate]), 0.01)
    assert ins.pose.yaw == pytest.approx(math.pi / 2.0, rel=0.05)


@pytest.mark.unit
def test_ins_drift_grows_with_time() -> None:
    """With biased accel and no aiding, INS-only drift must grow.

    Closed-form for constant bias `a` over time `T`: x = 0.5 * a * T**2.
    a=0.05 m/s^2, T=10 s -> ~2.5 m, growing with T^2. Verify monotonic growth.
    """
    ins = INSNavigator(schuler_damping=False)
    bias = 0.05
    accel = np.array([bias, 0.0, 9.80665])
    samples = []
    for i in range(1, 1001):
        ins.update(accel, np.zeros(3), 0.01)
        if i % 100 == 0:
            samples.append(ins.pose.x)
    # Monotonic increase, and final magnitude consistent with 0.5 a t^2.
    assert all(samples[i] < samples[i + 1] for i in range(len(samples) - 1))
    assert samples[-1] == pytest.approx(0.5 * bias * 10.0 ** 2, rel=0.05)


@pytest.mark.unit
def test_ins_reset_returns_to_initial_pose() -> None:
    ins = INSNavigator()
    ins.update(np.array([1.0, 0, 9.80665]), np.zeros(3), 0.5)
    ins.reset(Pose3D(x=10.0, y=20.0, z=-5.0, yaw=1.0))
    assert ins.pose.x == 10.0
    assert ins.pose.y == 20.0
    assert ins.pose.z == -5.0
    assert ins.pose.yaw == 1.0


# ---------------------------------------------------------------------------
# DVL
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_dvl_velocity_integration_straight_line() -> None:
    dvl = DVLNavigator(Pose3D(yaw=0.0))
    for _ in range(10):
        dvl.update(np.array([1.0, 0.0, 0.0]), depth=-5.0, dt=0.5)
    # 10 steps * 0.5 s * 1 m/s = 5 m east-of-body == nav-x (yaw=0).
    assert dvl.pose.x == pytest.approx(5.0, rel=1e-3)
    assert dvl.pose.z == pytest.approx(-5.0)


@pytest.mark.unit
def test_dvl_attitude_correction_yaw_90deg() -> None:
    """At yaw=90 deg, body-x velocity should map to nav-y."""
    pose = Pose3D(yaw=math.pi / 2.0)
    dvl = DVLNavigator(pose)
    dvl.update(np.array([1.0, 0.0, 0.0]), depth=-2.0, dt=1.0)
    assert abs(dvl.pose.x) < 1e-6
    assert dvl.pose.y == pytest.approx(1.0, rel=1e-6)


@pytest.mark.unit
def test_dvl_bottom_track_threshold() -> None:
    dvl = DVLNavigator()
    assert dvl.bottom_track_available(altitude=2.0) is True
    assert dvl.bottom_track_available(altitude=0.4) is False


@pytest.mark.unit
def test_dvl_uncertainty_grows_with_distance() -> None:
    dvl = DVLNavigator()
    for _ in range(100):
        dvl.update(np.array([1.0, 0.0, 0.0]), depth=-1.0, dt=1.0)
    # 100 m travelled -> 0.001 * 100 = 0.1 m
    assert dvl.position_uncertainty() == pytest.approx(0.1, rel=1e-2)


# ---------------------------------------------------------------------------
# LBL trilateration
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_lbl_trilateration_with_known_positions() -> None:
    lbl = LBLPositioner()
    lbl.add_transponder("a", [0.0, 0.0, 0.0])
    lbl.add_transponder("b", [100.0, 0.0, 0.0])
    lbl.add_transponder("c", [50.0, 100.0, 0.0])
    target = np.array([50.0, 50.0, 0.0])
    ranges = {
        "a": float(np.linalg.norm(target - np.array([0.0, 0.0, 0.0]))),
        "b": float(np.linalg.norm(target - np.array([100.0, 0.0, 0.0]))),
        "c": float(np.linalg.norm(target - np.array([50.0, 100.0, 0.0]))),
    }
    out = lbl.update(ranges)
    assert out[0] == pytest.approx(50.0, abs=0.5)
    assert out[1] == pytest.approx(50.0, abs=0.5)


@pytest.mark.unit
def test_lbl_requires_three_transponders() -> None:
    lbl = LBLPositioner()
    lbl.add_transponder("a", [0.0, 0.0, 0.0])
    lbl.add_transponder("b", [10.0, 0.0, 0.0])
    with pytest.raises(ValueError):
        lbl.update({"a": 5.0, "b": 5.0})


@pytest.mark.unit
def test_lbl_overdetermined_least_squares() -> None:
    lbl = LBLPositioner()
    pts = {
        "a": [0.0, 0.0, 0.0], "b": [100.0, 0.0, 0.0],
        "c": [0.0, 100.0, 0.0], "d": [100.0, 100.0, 0.0],
    }
    for k, v in pts.items():
        lbl.add_transponder(k, v)
    target = np.array([42.0, 17.0, 0.0])
    ranges = {k: float(np.linalg.norm(target - np.asarray(v)))
              for k, v in pts.items()}
    out = lbl.update(ranges)
    assert out[0] == pytest.approx(42.0, abs=1.0)
    assert out[1] == pytest.approx(17.0, abs=1.0)


# ---------------------------------------------------------------------------
# USBL
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_usbl_geometry_north() -> None:
    """Azimuth=0 (North), elevation=0 -> target north of ship."""
    usbl = USBLPositioner()
    out = usbl.update(angle_azimuth=0.0, angle_elevation=0.0,
                      slant_range=100.0, surface_position=[0.0, 0.0, 0.0])
    assert out[0] == pytest.approx(0.0, abs=1e-6)
    assert out[1] == pytest.approx(100.0, abs=1e-6)


@pytest.mark.unit
def test_usbl_geometry_east_below() -> None:
    """Azimuth=90 deg = East, elevation=30 deg below."""
    usbl = USBLPositioner()
    out = usbl.update(angle_azimuth=math.pi / 2.0,
                      angle_elevation=math.radians(30.0),
                      slant_range=100.0, surface_position=[10.0, 5.0, 0.0])
    horiz = 100.0 * math.cos(math.radians(30.0))
    assert out[0] == pytest.approx(10.0 + horiz, abs=1e-3)
    assert out[1] == pytest.approx(5.0, abs=1e-3)
    assert out[2] == pytest.approx(100.0 * math.sin(math.radians(30.0)), abs=1e-3)


# ---------------------------------------------------------------------------
# Sonar SLAM
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_sonar_slam_landmark_detection() -> None:
    slam = SonarSLAM(peak_threshold=0.5, association_radius=1.0)
    # 1-D scan with a clear close return at the centre.
    angles = np.linspace(-math.pi / 4, math.pi / 4, 21)
    ranges = np.full_like(angles, 50.0)
    ranges[10] = 10.0  # peak (closer)
    landmarks = slam.process_scan(ranges, angles, Pose3D(x=0.0, y=0.0, yaw=0.0))
    assert len(landmarks) == 1
    # body-frame x ~= 10, y ~= 0 (angle 0)
    assert landmarks[0].x == pytest.approx(10.0, abs=1e-3)
    assert abs(landmarks[0].y) < 1e-3


@pytest.mark.unit
def test_sonar_slam_map_update_associates_observations() -> None:
    slam = SonarSLAM(peak_threshold=0.5, association_radius=2.0)
    a = [Landmark(id=-1, x=10.0, y=0.0)]
    b = [Landmark(id=-1, x=10.2, y=0.1)]   # near a -> associate
    c = [Landmark(id=-1, x=50.0, y=50.0)]  # far -> new entry
    slam.update_map(a, Pose3D())
    slam.update_map(b, Pose3D())
    slam.update_map(c, Pose3D())
    assert len(slam.landmarks) == 2
    fused = next(lm for lm in slam.landmarks if lm.x < 20.0)
    assert fused.observations == 2


@pytest.mark.unit
def test_sonar_slam_icp_recovers_translation() -> None:
    rng = np.random.default_rng(0)
    truth_pts = rng.uniform(-50.0, 50.0, size=(20, 2))
    # Apply a small known translation; ICP should recover (-2, -3).
    tx, ty = 2.0, 3.0
    moved = truth_pts + np.array([tx, ty])
    R, t = SonarSLAM._icp(moved, truth_pts, max_iter=50)
    assert t[0] == pytest.approx(-tx, abs=0.1)
    assert t[1] == pytest.approx(-ty, abs=0.1)


# ---------------------------------------------------------------------------
# Bathymetric correlation
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_bathymetric_correlation_perfect_match() -> None:
    matcher = BathymetricMatcher()
    a = np.array([1.0, 2.0, 3.0, 2.5, 1.5])
    score = matcher._terrain_correlation(a, a)
    assert score == pytest.approx(1.0, abs=1e-9)


@pytest.mark.unit
def test_bathymetric_correlation_anticorrelated() -> None:
    matcher = BathymetricMatcher()
    a = np.array([1.0, 2.0, 3.0, 4.0])
    b = -a
    score = matcher._terrain_correlation(a, b)
    assert score == pytest.approx(-1.0, abs=1e-9)


@pytest.mark.unit
def test_bathymetric_match_locates_profile_in_grid() -> None:
    """Build a depth grid with a per-row unique signature, then verify the
    matcher recovers the correct row index when given that row's profile."""
    rows, cols = 10, 10
    j = np.arange(cols, dtype=float)
    # Each row's profile is a parabola whose minimum sits at column = row index.
    # That makes every row uniquely identifiable up to NCC.
    grid = np.array([(j - i) ** 2 for i in range(rows)], dtype=float)
    matcher = BathymetricMatcher()
    matcher.load_map(grid, origin_lat=0.0, origin_lon=0.0, resolution_m=1.0)
    profile = grid[4, :5].copy()                # length 5 along east
    lat, _lon = matcher.match(profile, heading=math.pi / 2.0, speed=1.0)
    # Expected dy_m = 4 * 1.0 m -> 4/111320 deg.
    assert lat == pytest.approx(4.0 / 111_320.0, rel=1e-2)


# ---------------------------------------------------------------------------
# Fusion
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_fusion_priority_acoustic_wins() -> None:
    fuser = UnderwaterPositioner()
    pose = fuser.fuse(
        dvl=Pose3D(x=10.0, y=10.0),
        ins=Pose3D(x=20.0, y=20.0),
        acoustic=np.array([100.0, 200.0, -50.0]),
        depth=-50.0,
    )
    assert pose.x == 100.0 and pose.y == 200.0
    assert fuser.last_source == "acoustic"


@pytest.mark.unit
def test_fusion_priority_dvl_then_ins() -> None:
    fuser = UnderwaterPositioner()
    p1 = fuser.fuse(dvl=Pose3D(x=1.0, y=2.0), ins=Pose3D(x=99.0, y=99.0),
                    acoustic=None, depth=-3.0)
    assert (p1.x, p1.y, p1.z) == (1.0, 2.0, -3.0)
    assert fuser.last_source == "dvl-ins"
    p2 = fuser.fuse(dvl=None, ins=Pose3D(x=7.0, y=8.0, z=-9.0),
                    acoustic=None, depth=None)
    assert (p2.x, p2.y, p2.z) == (7.0, 8.0, -9.0)
    assert fuser.last_source == "ins"
